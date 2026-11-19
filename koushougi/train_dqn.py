"""同じ採点NNとαβ探索を使い、自己対戦中にDouble DQNで学習する。"""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, fields
import fcntl
import hashlib
import json
from math import isfinite
from pathlib import Path
from random import Random

import torch
from torch.nn import functional as F

from . import Piece
from .board import Board
from .game import Game, outcome
from .players.alpha_beta import analyze_search
from .train_value import TrainingNetwork, get_device
from .value_network import PIECES, SCALE, SIZE, STATES, ValueNetwork, encode_board, load_network


def encode_afterstate(game):
    """行動後の盤面を、次の手番側を黒にそろえて保存する。"""
    return bytes(encode_board(game.board, game.turn))


def restore_afterstate(encoded):
    game = Game()
    game.board = Board()
    for cell, token in enumerate(encoded):
        if token:
            name, flags = divmod(token - 1, 4)
            game.board[cell % SIZE, cell // SIZE] = Piece(
                "white" if flags // 2 else "black", PIECES[name], bool(flags % 2))
    game.turn = "black"
    return game


@dataclass(frozen=True)
class Transition:
    # 決定的なゲームなので、Q(s,a)の入力には行動結果T(s,a)を使える。
    afterstate: bytes
    reward: float
    terminated: bool

    def __post_init__(self):
        if (not isinstance(self.afterstate, bytes) or len(self.afterstate) != SIZE * SIZE
                or any(token >= STATES for token in self.afterstate)):
            raise ValueError("行動後の盤面が不正です")
        if self.reward not in (-1, 0, 1) or type(self.terminated) is not bool:
            raise ValueError("報酬または終局フラグが不正です")
        if not self.terminated and self.reward != 0:
            raise ValueError("終局前の報酬は0です")


class ReplayBuffer:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("経験を保存する件数は正の整数にしてください")
        self.capacity, self.position = capacity, 0
        self.rows = []

    def __len__(self):
        return len(self.rows)

    def push(self, transition):
        if len(self.rows) < self.capacity:
            self.rows.append(transition)
        else:
            self.rows[self.position] = transition
        self.position = (self.position + 1) % self.capacity

    def sample(self, count, rng):
        return rng.sample(self.rows, count)

    def state_dict(self):
        return {"capacity": self.capacity, "position": self.position,
                "rows": [asdict(row) for row in self.rows]}

    @classmethod
    def from_state_dict(cls, state):
        buffer = cls(state["capacity"])
        buffer.rows = [Transition(**row) for row in state["rows"]]
        buffer.position = state["position"]
        if len(buffer.rows) > buffer.capacity or not 0 <= buffer.position < buffer.capacity:
            raise ValueError("経験の保存状態が不正です")
        return buffer


class DoubleDQN:
    def __init__(self, model, *, device="cpu", gamma=0.99, learning_rate=0.001,
                 target_interval=1000, inference_batch_size=256):
        if (not isfinite(gamma) or not 0 <= gamma <= 1 or not isfinite(learning_rate)
                or learning_rate <= 0 or min(target_interval, inference_batch_size) < 1):
            raise ValueError("DQNの学習条件が不正です")
        self.device = torch.device(device)
        self.gamma, self.target_interval = gamma, target_interval
        self.inference_batch_size = inference_batch_size
        self.online = TrainingNetwork(model).to(self.device)
        self.target = TrainingNetwork(model).to(self.device).eval()
        self.target.requires_grad_(False)
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=learning_rate)
        self.updates, self.target_updates = 0, 0
        self._policy_model = model

    @property
    def policy_model(self):
        if self._policy_model is None:
            self._policy_model = self.online.export()
        return self._policy_model

    def q_values(self, network, afterstates):
        encoded = torch.tensor([list(board) for board in afterstates], dtype=torch.long,
                               device=self.device)
        # NNは次の手番側の評価を返す。Qは今指した側の評価なので符号を反転する。
        return -(network(encoded) / SCALE).tanh()

    @torch.no_grad()
    def best_reply_value(self, game):
        """全合法手からonlineで選び、その同じ手をtargetで評価する。"""
        best_score, selected, selected_reward = float("-inf"), None, None
        batch, rewards = [], []

        def consider():
            nonlocal best_score, selected, selected_reward
            scores = self.q_values(self.online, batch).tolist()
            for board, score, reward in zip(batch, scores, rewards):
                score = score if reward is None else reward
                if score > best_score:
                    best_score, selected, selected_reward = score, board, reward
            batch.clear()
            rewards.clear()

        for _, child in game.successors():
            winner = outcome(child.board)
            reward = None if winner is None else (1.0 if winner == game.turn else -1.0)
            batch.append(encode_afterstate(child))
            rewards.append(reward)
            if len(batch) >= self.inference_batch_size:
                consider()
        if batch:
            consider()
        if selected is None:
            # 合法手なしの勝敗は未定義。引き分けの教師値は作らない。
            return None
        if selected_reward is not None:
            return selected_reward
        return self.q_values(self.target, [selected]).item()

    @torch.no_grad()
    def targets(self, transitions):
        values = []
        for row in transitions:
            if row.terminated:
                values.append(float(row.reward))
            else:
                reply = self.best_reply_value(restore_afterstate(row.afterstate))
                # 次の行動者は相手なので、通常のDQNの加算を減算にする。
                values.append(None if reply is None else row.reward - self.gamma * reply)
        return values

    def train_batch(self, transitions):
        targets = self.targets(transitions)
        rows = [(row, target) for row, target in zip(transitions, targets) if target is not None]
        skipped = len(transitions) - len(rows)
        if not rows:
            return {"loss": None, "samples": 0, "skipped_no_legal_move": skipped}
        expected = torch.tensor([target for _, target in rows], dtype=torch.float32,
                                device=self.device)
        prediction = self.q_values(self.online, [row.afterstate for row, _ in rows])
        loss = F.smooth_l1_loss(prediction, expected)
        if not torch.isfinite(loss):
            raise ValueError("DQNの損失が有限ではありません")
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.online.parameters(), 10.0, error_if_nonfinite=True)
        self.optimizer.step()
        self._policy_model = None
        self.updates += 1
        if self.updates % self.target_interval == 0:
            self.target.load_state_dict(self.online.state_dict())
            self.target_updates += 1
        return {"loss": loss.item(), "samples": len(rows), "skipped_no_legal_move": skipped}

    def state_dict(self):
        return {"online": self.online.state_dict(), "target": self.target.state_dict(),
                "optimizer": self.optimizer.state_dict(), "updates": self.updates,
                "target_updates": self.target_updates, "width": self.online.export().width}

    def load_state_dict(self, state):
        self.online.load_state_dict(state["online"])
        self.target.load_state_dict(state["target"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.updates, self.target_updates = state["updates"], state["target_updates"]
        self._policy_model = None


@dataclass(frozen=True)
class Config:
    games: int = 20
    max_plies: int = 1500
    seconds: float = 2.0
    depth: int = 3
    seed: int = 0
    gamma: float = 0.99
    learning_rate: float = 0.001
    batch_size: int = 16
    replay_capacity: int = 10000
    warmup: int = 64
    train_every: int = 4
    target_interval: int = 1000
    epsilon_start: float = 0.2
    epsilon_end: float = 0.02
    epsilon_steps: int = 10000
    checkpoint_every: int = 100
    inference_batch_size: int = 256

    def __post_init__(self):
        positive = (self.games, self.max_plies, self.depth, self.batch_size, self.replay_capacity,
                    self.warmup, self.train_every, self.target_interval, self.epsilon_steps,
                    self.checkpoint_every, self.inference_batch_size)
        if min(positive) < 1 or not isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("件数、深さ、思考時間には正の値を指定してください")
        if not self.batch_size <= self.warmup <= self.replay_capacity:
            raise ValueError("batch-size ≤ warmup ≤ replay-capacity にしてください")
        if not 0 <= self.epsilon_end <= self.epsilon_start <= 1:
            raise ValueError("探索確率は0〜1で、終了時を開始時以下にしてください")
        if (not isfinite(self.gamma) or not 0 <= self.gamma <= 1
                or not isfinite(self.learning_rate) or self.learning_rate <= 0):
            raise ValueError("割引率または学習率が不正です")

    def epsilon(self, steps):
        fraction = min(1.0, steps / self.epsilon_steps)
        return self.epsilon_start + fraction * (self.epsilon_end - self.epsilon_start)


def choose_move(game, learner, rng, epsilon, config):
    if rng.random() < epsilon:
        selected = None
        for count, (move, _) in enumerate(game.successors(), 1):
            if rng.randrange(count) == 0:
                selected = move
        return selected, None, True
    result = analyze_search(game, model=learner.policy_model,
                            time_limit=config.seconds, max_depth=config.depth)
    return (rng.choice(result.best_moves), result.depth, False) if result else (None, None, False)


def save_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def source_digest():
    root = Path(__file__).parent
    names = ("__init__.py", "board.py", "game.py", "evaluation.py", "search.py", "move_ordering.py",
             "value_network.py", "train_value.py", "train_dqn.py", "players/alpha_beta.py")
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def game_state(game):
    return {"turn": game.turn, "pieces": [[x, y, p.side, p.name, p.promoted]
                                           for (x, y), p in game.board.items()]}


def restore_game(state):
    game = Game()
    game.turn = state["turn"]
    game.board = Board({(x, y): Piece(side, name, promoted)
                        for x, y, side, name, promoted in state["pieces"]})
    return game


def train(output, config, *, device="cpu", model=None, resume=False):
    """呼出元がrun.lockを保持して実行する。再開時は保存時の条件を使う。"""
    rng = Random(config.seed)
    torch.manual_seed(config.seed)
    run_source_hash = source_digest()
    checkpoint = output / "checkpoint.pt"
    if resume:
        state = torch.load(checkpoint, map_location=device, weights_only=True)
        if state["format"] != 1 or state["source_sha256"] != run_source_hash:
            raise ValueError("再開時の実行コードが保存時と異なります")
        if state["config"] != asdict(config):
            raise ValueError("再開時の学習条件が保存時と異なります")
        model = ValueNetwork(width=state["learner"]["width"])
    else:
        state = None
        model = load_network(model)
        model.save(output / "initial.json")
        save_json(output / "config.json", asdict(config))
    learner = DoubleDQN(model, device=device, gamma=config.gamma, learning_rate=config.learning_rate,
                        target_interval=config.target_interval,
                        inference_batch_size=config.inference_batch_size)
    replay, game = ReplayBuffer(config.replay_capacity), Game()
    steps = ply = explored = skipped = 0
    depths, results = Counter(), []
    last_loss = None
    if state is not None:
        learner.load_state_dict(state["learner"])
        replay = ReplayBuffer.from_state_dict(state["replay"])
        rng.setstate(state["rng"])
        torch.set_rng_state(state["torch_rng"].cpu())
        game = restore_game(state["game"])
        steps, ply, explored, skipped = (state[key] for key in ("steps", "ply", "explored", "skipped"))
        depths, results, last_loss = Counter(state["depths"]), state["results"], state["last_loss"]

    def save(status):
        saved = {"format": 1, "source_sha256": run_source_hash, "config": asdict(config),
                 "learner": learner.state_dict(), "replay": replay.state_dict(),
                 "rng": rng.getstate(), "torch_rng": torch.get_rng_state(), "game": game_state(game),
                 "steps": steps, "ply": ply, "explored": explored, "skipped": skipped,
                 "depths": dict(depths), "results": results, "last_loss": last_loss}
        temporary = checkpoint.with_suffix(".pt.tmp")
        torch.save(saved, temporary)
        temporary.replace(checkpoint)
        temporary_model = output / "candidate.json.tmp"
        # ValueNetwork.saveは既存ファイルを拒否するので、上書きは別の一時ファイルで行う。
        with temporary_model.open("w", encoding="utf-8") as destination:
            native = learner.policy_model
            json.dump({"format": 2, "pieces": PIECES, "width": native.width,
                       "parameters": native.parameters}, destination, ensure_ascii=False, allow_nan=False)
        temporary_model.replace(output / "candidate.json")
        report = {"algorithm": "afterstate_double_dqn", "status": status, "config": asdict(config),
                  "source_sha256": saved["source_sha256"], "device": str(device),
                  "games_played": len(results),
                  "games_decided": sum(row["winner"] is not None for row in results),
                  "outcomes": dict(Counter(row["winner"] or row["reason"] for row in results)),
                  "environment_steps": steps, "active_ply": ply, "replay_size": len(replay),
                  "updates": learner.updates, "target_updates": learner.target_updates,
                  "exploratory_moves": explored, "search_depths": dict(depths),
                  "epsilon": config.epsilon(steps), "last_td_loss": last_loss,
                  "skipped_no_legal_move": skipped, "results": results}
        save_json(output / "report.json", report)
        print(json.dumps({key: value for key, value in report.items()
                          if key not in ("config", "results", "source_sha256")}, ensure_ascii=False), flush=True)

    save("running" if len(results) < config.games else "complete")
    while len(results) < config.games:
        move, depth, exploratory = choose_move(game, learner, rng, config.epsilon(steps), config)
        winner, reason = None, None
        if move is None:
            reason = "no_legal_move"
        else:
            side = game.turn
            game.play(*move)
            winner = outcome(game.board)
            replay.push(Transition(encode_afterstate(game),
                                   0.0 if winner is None else (1.0 if winner == side else -1.0),
                                   winner is not None))
            steps += 1
            ply += 1
            explored += int(exploratory)
            if depth is not None:
                depths[depth] += 1
            if len(replay) >= config.warmup and steps % config.train_every == 0:
                metrics = learner.train_batch(replay.sample(config.batch_size, rng))
                skipped += metrics["skipped_no_legal_move"]
                if metrics["loss"] is not None:
                    last_loss = metrics["loss"]
            if winner is not None:
                reason = "win"
            elif ply >= config.max_plies:
                reason = "ply_limit"
        if reason is not None:
            results.append({"game": len(results), "winner": winner, "reason": reason, "plies": ply})
            game, ply = Game(), 0
        if reason is not None or steps % config.checkpoint_every == 0:
            save("complete" if len(results) >= config.games else "running")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="新規実験ディレクトリ")
    parser.add_argument("--model", type=Path, help="開始時のformat 2モデル")
    parser.add_argument("--resume", action="store_true", help="output内のcheckpoint.ptから再開")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    for field in fields(Config):
        parser.add_argument("--" + field.name.replace("_", "-"), type=field.type)
    args = parser.parse_args()
    try:
        device = get_device(args.device)
        torch.set_num_threads(1)
        specified = {field.name: getattr(args, field.name) for field in fields(Config)
                     if getattr(args, field.name) is not None}
        if args.resume:
            if args.model is not None:
                raise ValueError("再開時は--modelを指定しないでください")
            saved = json.loads((args.output / "config.json").read_text(encoding="utf-8"))
            if any(saved[key] != value for key, value in specified.items()):
                raise ValueError("再開時は保存済みの学習条件を変更できません")
            config = Config(**saved)
        else:
            config = Config(**specified)
            args.output.mkdir(parents=True, exist_ok=False)
        with (args.output / "run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            train(args.output, config, device=device, model=args.model, resume=args.resume)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

"""Minimax対戦による強化学習スクリプト（フェーズ分離型）

NNがMinimaxと対戦し、その結果から学習する。
各フェーズごとに経験を記録し、個別に学習する。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(line_buffering=True)

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from pathlib import Path
import time
import json
import random
from collections import deque

from ai.neural.model import create_model, encode_board, pos_to_index, index_to_pos, NUM_SQUARES
from ai.neural.player import NeuralPlayer
from ai.minimax.player import MinimaxPlayer
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state


class PhaseExperience:
    """フェーズごとの経験"""
    def __init__(self, state, action_idx, phase):
        self.state = state
        self.action_idx = action_idx
        self.phase = phase
        self.reward = 0.0


class ReplayBuffer:
    """経験再生バッファ（フェーズ別）"""

    def __init__(self, capacity=10000):
        self.buffers = {
            "piece": deque(maxlen=capacity),
            "dest": deque(maxlen=capacity),
            "promo": deque(maxlen=capacity),
            "shoot": deque(maxlen=capacity),
        }

    def push(self, exp: PhaseExperience):
        """経験を保存"""
        self.buffers[exp.phase].append(exp)

    def sample(self, phase: str, batch_size: int):
        """バッチをサンプリング"""
        buffer = self.buffers[phase]
        if len(buffer) < batch_size:
            return None

        batch = random.sample(list(buffer), batch_size)
        states = torch.stack([e.state for e in batch])
        actions = torch.tensor([e.action_idx for e in batch], dtype=torch.long)
        rewards = torch.tensor([e.reward for e in batch], dtype=torch.float32)
        return states, actions, rewards

    def __len__(self):
        return sum(len(b) for b in self.buffers.values())

    def len_phase(self, phase: str):
        return len(self.buffers[phase])


def play_game(nn_player: NeuralPlayer, minimax_player: MinimaxPlayer, nn_is_first: bool):
    """1ゲームをプレイ

    Returns:
        experiences: フェーズごとの経験リスト
        winner: 0 or 1 or None
        nn_player_id: NNが担当したプレイヤー
    """
    engine = GameEngine(create_initial_state())
    nn_player_id = 0 if nn_is_first else 1

    experiences = []
    max_turns = 300

    for turn in range(max_turns):
        if engine.is_game_over:
            break

        current = engine.current_player
        if current == nn_player_id:
            # NNの手番 - 各フェーズを記録
            turn_exps = play_nn_turn(engine, nn_player)
            experiences.extend(turn_exps)
        else:
            # Minimaxの手番
            minimax_player.play_turn(engine)

    winner = engine.winner

    # 報酬を割り当て
    if winner is None:
        reward = 0.0
    elif winner == nn_player_id:
        reward = 1.0
    else:
        reward = -1.0

    # 各経験に報酬を逆伝播
    n = len(experiences)
    for i, exp in enumerate(experiences):
        exp.reward = reward * (0.99 ** (n - i - 1))

    return experiences, winner, nn_player_id


def play_nn_turn(engine: GameEngine, nn_player: NeuralPlayer) -> list[PhaseExperience]:
    """NNの1ターンをプレイし、経験を記録"""
    experiences = []

    # フェーズ1: 駒選択
    state = encode_board(engine)
    piece_pos = nn_player.choose_piece(engine)
    piece_idx = pos_to_index(piece_pos[0], piece_pos[1])
    experiences.append(PhaseExperience(state, piece_idx, "piece"))

    if not engine.select_piece(piece_pos):
        return experiences

    # フェーズ2: 移動先選択
    state = encode_board(engine, selected_piece=engine.selected_piece)
    dest_pos = nn_player.choose_destination(engine)
    dest_idx = pos_to_index(dest_pos[0], dest_pos[1])
    experiences.append(PhaseExperience(state, dest_idx, "dest"))

    result = engine.select_destination(dest_pos)
    if not result.success:
        return experiences

    # フェーズ3: 成り判断
    if engine.phase == GamePhase.PROMOTION:
        state = encode_board(engine)
        promote = nn_player.choose_promotion(engine)
        promo_idx = 1 if promote else 0
        experiences.append(PhaseExperience(state, promo_idx, "promo"))

        result = engine.decide_promotion(promote)
        if not result.success:
            return experiences

    # フェーズ4: 射撃（複数回可能）
    while engine.phase == GamePhase.SHOOTING:
        state = encode_board(engine)
        target = nn_player.choose_shoot_target(engine)

        if target:
            shoot_idx = pos_to_index(target[0], target[1])
            experiences.append(PhaseExperience(state, shoot_idx, "shoot"))
            result = engine.shoot(target)
            if not result.can_shoot:
                break
        else:
            # スキップ
            experiences.append(PhaseExperience(state, NUM_SQUARES, "shoot"))
            engine.skip_shoot()
            break

    return experiences


def train_from_buffer(model, optimizer, replay_buffer, device, batch_size=32):
    """バッファから学習"""
    model.train()
    total_loss = 0.0
    num_phases = 0

    for phase in ["piece", "dest", "promo", "shoot"]:
        batch = replay_buffer.sample(phase, batch_size)
        if batch is None:
            continue

        states, actions, rewards = batch
        states = states.to(device)
        actions = actions.to(device)
        rewards = rewards.to(device).unsqueeze(1)

        optimizer.zero_grad()

        # Forward pass
        policy_logits, value_pred = model(states, phase=phase)

        # Policy loss (REINFORCE)
        log_probs = F.log_softmax(policy_logits, dim=1)
        selected_log_probs = log_probs.gather(1, actions.unsqueeze(1))
        policy_loss = -(selected_log_probs * rewards).mean()

        # Value loss
        value_loss = F.mse_loss(value_pred, rewards)

        loss = policy_loss + value_loss
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        num_phases += 1

    return total_loss / max(num_phases, 1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Minimax対戦による強化学習")
    parser.add_argument("--output", type=str, default="models/koushougi_rl", help="モデル保存先")
    parser.add_argument("--games", type=int, default=500, help="ゲーム数")
    parser.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    parser.add_argument("--lr", type=float, default=0.0001, help="学習率")
    parser.add_argument("--device", type=str, default="cpu", choices=["mps", "cuda", "cpu"])
    parser.add_argument("--lite", action="store_true", help="軽量モデルを使用")
    parser.add_argument("--minimax-depth", type=int, default=2, help="Minimaxの探索深さ")
    parser.add_argument("--epsilon", type=float, default=0.3, help="探索率（初期）")
    parser.add_argument("--epsilon-decay", type=float, default=0.995, help="探索率の減衰")
    parser.add_argument("--epsilon-min", type=float, default=0.05, help="探索率の下限")
    parser.add_argument("--load", type=str, default=None, help="既存モデルを読み込む")
    parser.add_argument("--save-every", type=int, default=50, help="N ゲームごとにモデル保存")
    args = parser.parse_args()

    # 出力ディレクトリ
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== Minimax対戦学習（フェーズ分離型） ===")
    print(f"ゲーム数: {args.games}")
    print(f"Minimax深さ: {args.minimax_depth}")
    print(f"デバイス: {args.device}")

    # デバイス
    if args.device == "mps" and torch.backends.mps.is_available():
        device = torch.device("mps")
    elif args.device == "cuda" and torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print(f"Using: {device}")

    # モデル
    model = create_model(lite=args.lite, device=args.device)
    if args.load:
        checkpoint = torch.load(args.load, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        print(f"モデル読み込み: {args.load}")

    print(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    replay_buffer = ReplayBuffer(capacity=50000)
    minimax = MinimaxPlayer(depth=args.minimax_depth, max_moves=15)

    # 統計
    stats = {
        "wins": 0,
        "losses": 0,
        "draws": 0,
    }

    epsilon = args.epsilon

    for game_idx in range(args.games):
        start_time = time.time()

        nn_is_first = (game_idx % 2 == 0)
        nn_player = NeuralPlayer(model, device, epsilon=epsilon, temperature=1.0)

        # ゲームプレイ
        experiences, winner, nn_player_id = play_game(nn_player, minimax, nn_is_first)

        # 結果を判定
        if winner is None:
            stats["draws"] += 1
            result_str = "引分"
        elif winner == nn_player_id:
            stats["wins"] += 1
            result_str = "勝利"
        else:
            stats["losses"] += 1
            result_str = "敗北"

        # 経験をバッファに追加
        for exp in experiences:
            replay_buffer.push(exp)

        # 学習
        loss = train_from_buffer(model, optimizer, replay_buffer, device, args.batch_size)

        # 探索率を減衰
        epsilon = max(args.epsilon_min, epsilon * args.epsilon_decay)

        elapsed = time.time() - start_time

        # 進捗表示
        if (game_idx + 1) % 10 == 0:
            win_rate = stats["wins"] / (game_idx + 1) * 100
            print(f"ゲーム {game_idx+1}/{args.games}: {result_str} "
                  f"(勝率: {win_rate:.1f}%, ε={epsilon:.3f}, loss={loss:.4f}, {elapsed:.1f}s)")

        # 定期保存
        if (game_idx + 1) % args.save_every == 0:
            checkpoint_path = output_dir / f"checkpoint_{game_idx+1}.pth"
            torch.save({
                "game": game_idx + 1,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "stats": stats,
                "epsilon": epsilon,
            }, checkpoint_path)
            print(f"  チェックポイント保存: {checkpoint_path}")

    # 最終保存
    final_path = output_dir / "final_model.pth"
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "stats": stats,
    }, final_path)

    # 統計保存
    stats_path = output_dir / "training_stats.json"
    with open(stats_path, "w") as f:
        json.dump({
            "wins": stats["wins"],
            "losses": stats["losses"],
            "draws": stats["draws"],
            "win_rate": stats["wins"] / args.games * 100,
        }, f, indent=2)

    print("\n=== 学習完了 ===")
    print(f"勝利: {stats['wins']}, 敗北: {stats['losses']}, 引分: {stats['draws']}")
    print(f"勝率: {stats['wins'] / args.games * 100:.1f}%")
    print(f"モデル保存: {final_path}")


if __name__ == "__main__":
    main()

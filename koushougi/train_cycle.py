"""対局中の深い探索を教師にして、収集・学習・比較を世代ごとに繰り返す。"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from math import isfinite, tanh
import multiprocessing
import os
from pathlib import Path
from random import Random
import shutil
import sys
from time import perf_counter

import torch

from . import Action, Piece
from .board import Board
from .game import Game, outcome
from .players.alpha_beta import analyze_search
from .search import WIN
from .torch_evaluation import TorchEvaluator
from .train_value import TrainingNetwork, get_device
from .value_network import SCALE, encode_board, load_network


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(game):
    return {"turn": game.turn, "pieces": [[x, y, p.side, p.name, p.promoted]
                                          for (x, y), p in game.board.items()]}


def restore(value):
    game = Game()
    game.turn = value["turn"]
    game.board = Board({(x, y): Piece(side, name, promoted)
                        for x, y, side, name, promoted in value["pieces"]})
    return game


def key(value):
    game = restore(value)
    return hashlib.sha256(bytes(encode_board(game.board, game.turn))).hexdigest()


def pack(move):
    action, promote, linked = move
    return {"origin": action.origin, "path": action.path, "shots": action.shots,
            "shot_steps": action.shot_steps,
            "promote": promote, "linked": linked}


def unpack(move):
    return (Action(tuple(move["origin"]), tuple(map(tuple, move["path"])),
                   tuple(map(tuple, move["shots"])), tuple(move.get("shot_steps", ()))),
            move["promote"], tuple(map(tuple, move["linked"])))


def tuples(value):
    return tuple(map(tuples, value)) if isinstance(value, list) else value


@dataclass(frozen=True)
class Config:
    generations: int = 3
    games: int = 6
    chunk_plies: int = 32
    max_game_plies: int = 1500
    workers: int = 2
    seconds: float = 10.0
    depth: int = 5
    min_depth: int = 3
    epsilon: float = 0.1
    seed: int = 20261118
    replay_generations: int = 4
    epochs: int = 40
    patience: int = 8
    batch_size: int = 256
    learning_rate: float = 0.0003
    inference_batch_size: int = 128
    evaluation_pairs: int = 4
    evaluation_seconds: float = 2.0
    evaluation_depth: int = 3
    evaluation_max_plies: int = 1500
    min_decided: int = 4
    promotion_threshold: float = 0.6

    def __post_init__(self):
        integer = [getattr(self, f.name) for f in fields(self) if f.type is int and f.name != "seed"]
        if min(integer) < 1 or self.games < 3 or not 1 <= self.min_depth <= self.depth:
            raise ValueError("正の件数、3局以上、min-depth ≤ depth を指定してください")
        if self.min_decided > 2 * self.evaluation_pairs:
            raise ValueError("min-decidedは評価対局数以下にしてください")
        if any(not isfinite(v) or v <= 0 for v in
               (self.seconds, self.evaluation_seconds, self.learning_rate)):
            raise ValueError("時間と学習率には有限の正の値を指定してください")
        if not 0 <= self.epsilon <= 1 or not 0.5 < self.promotion_threshold <= 1:
            raise ValueError("探索確率は0〜1、昇格の得点率は0.5より大きく1以下にしてください")


def evaluator(path, device, batch_size):
    native = load_network(Path(path))
    return native if device == "native" else TorchEvaluator(native, device=device, batch_size=batch_size)


def saved_result(folder):
    report = read(folder / "result.json")
    frames = sorted(folder.glob("step-*.json"))
    if not frames or len(frames) != report["steps"]:
        raise ValueError("対局結果と保存した一手の件数が一致しません")
    last = read(frames[-1])
    if (report["context"] != last["next_context"] or report["winner"] != last["winner"]
            or report["reason"] != (last["reason"] or "chunk_limit")):
        raise ValueError("対局結果と最後の記録が一致しません")
    return report


def play_chunk(job):
    """一手ずつ保存する。収集中のNNは固定し、同じ探索結果を着手と教師に使う。"""
    torch.set_num_threads(1)
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "job.json"
    normalized = json.loads(json.dumps(job))
    if manifest.exists():
        if read(manifest) != normalized:
            raise ValueError("保存済み対局の条件と再開条件が異なります")
    else:
        save(manifest, normalized)
    if (folder / "result.json").exists():
        return saved_result(folder)
    for path, expected in job["model_hashes"].items():
        if digest(Path(path)) != expected:
            raise ValueError("対局中のモデルが変更されています")
    models = {path: evaluator(path, job["inference_device"], job["inference_batch_size"])
              for path in set(job["models"].values())}
    frames = sorted(folder.glob("step-*.json"))
    context = read(frames[-1])["next_context"] if frames else job["context"]
    rng = Random(job["seed"])
    if context.get("rng") is not None:
        rng.setstate(tuples(context["rng"]))
    game = restore(context["state"])
    episode, episode_ply = context["episode"], context["ply"]
    stopped = bool(frames and read(frames[-1])["stop"])
    for index in range(len(frames), job["steps"]):
        if stopped:
            break
        before, side = state(game), game.turn
        started = perf_counter()
        result = analyze_search(game, model=models[job["models"][side]],
                                time_limit=job["seconds"], max_depth=job["depth"])
        seconds = perf_counter() - started
        move = None
        if result is not None:
            if job["collect"] and rng.random() < job["epsilon"]:
                # 全合法手から一様に選ぶ。深い探索の教師値は選択した手に依存させない。
                for count, (candidate, _) in enumerate(game.successors(), 1):
                    if rng.randrange(count) == 0:
                        move = candidate
            else:
                move = rng.choice(result.best_moves)
            game.play(*move)
            episode_ply += 1
        winner = outcome(game.board)
        reason = ("no_legal_move" if result is None else "win" if winner else
                  "ply_limit" if episode_ply >= job["max_game_plies"] else None)
        after = state(game)
        stopped = bool(reason and not job["collect"])
        used_episode, used_ply = episode, episode_ply
        if reason and job["collect"]:
            game, episode_ply, episode = Game(), 0, episode + 1
        context = {"state": state(game), "episode": episode, "ply": episode_ply, "rng": rng.getstate()}
        frame = {"index": index, "before": before, "after": after,
                 "move": pack(move) if move is not None else None,
                 "score": result.score if result else None, "depth": result.depth if result else None,
                 "seconds": seconds, "episode": used_episode, "ply": used_ply,
                 "winner": winner, "reason": reason, "stop": stopped, "next_context": context,
                 "teacher": job["models"][side], "updated": now()}
        save(folder / f"step-{index:05d}.json", frame)
        save(folder / "progress.json", {"steps": index + 1, "episode": episode, "ply": episode_ply,
                                       "depth": frame["depth"], "updated": now()})
    frames = [read(path) for path in sorted(folder.glob("step-*.json"))]
    final = frames[-1]
    report = {"context": final["next_context"], "steps": len(frames), "winner": final["winner"],
              "reason": final["reason"] or "chunk_limit",
              "outcomes": dict(Counter(row["winner"] or row["reason"] for row in frames if row["reason"])),
              "depths": dict(Counter(row["depth"] for row in frames if row["depth"] is not None)),
              "folder": str(folder), "finished": now()}
    save(folder / "result.json", report)
    return report


def parallel(jobs, workers, root, stage):
    if workers == 1:
        return [play_chunk(job) for job in jobs]
    results = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        pending = {pool.submit(play_chunk, job): index for index, job in enumerate(jobs)}
        while pending:
            done, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                results[pending.pop(future)] = future.result()
            save(root / "progress.json", {"stage": stage, "completed": len(results),
                                           "total": len(jobs), "updated": now()})
    return [results[index] for index in range(len(jobs))]


def prepare_data(root, folder, jobs, generation, config):
    roles_path = root / "position-roles.json"
    ownership = read(roles_path) if roles_path.exists() else {}
    current = {role: {} for role in ("test", "validation", "train")}
    excluded, depths = Counter(), Counter()
    # 検証・最終確認の盤面を先に確保し、同じ入力を別の区分へ混入させない。
    for role in current:
        for job in jobs:
            if job["role"] != role:
                continue
            for path in sorted(Path(job["folder"]).glob("step-*.json")):
                frame = read(path)
                if frame["move"] is None:
                    excluded["no_legal_move"] += 1
                    continue
                game = restore(frame["before"])
                game.play(*unpack(frame["move"]))
                if state(game) != frame["after"] or outcome(game.board) != frame["winner"]:
                    raise ValueError("保存した一手を再生した盤面が一致しません")
                if frame["depth"] < config.min_depth and frame["score"] != WIN:
                    excluded["incomplete_teacher_depth"] += 1
                    continue
                position = key(frame["before"])
                if ownership.setdefault(position, role) != role:
                    excluded["overlap_other_split"] += 1
                    continue
                previous = current[role].get(position)
                row = {"key": position, "pieces": frame["before"]["pieces"],
                       "turn": frame["before"]["turn"], "target": tanh(frame["score"] / SCALE),
                       "search_score": frame["score"], "search_depth": frame["depth"],
                       "generation": generation, "lane": job["lane"], "episode": frame["episode"],
                       "teacher_sha256": job["model_hashes"][frame["teacher"]]}
                if previous is None or previous["search_depth"] < row["search_depth"]:
                    current[role][position] = row
                depths[frame["depth"]] += 1
    datasets = {role: list(values.values()) for role, values in current.items()}
    for role, rows in datasets.items():
        save(folder / (role + ".json"), rows)
    save(roles_path, ownership)
    replay = {}
    for previous in range(max(1, generation - config.replay_generations + 1), generation + 1):
        for row in read(root / f"generation-{previous:03d}" / "train.json"):
            if ownership[row["key"]] != "train":
                raise ValueError("学習データと検証データが重複しています")
            replay[row["key"]] = row
    datasets["train"] = list(replay.values())
    if any(not rows for rows in datasets.values()):
        raise ValueError("学習・検証・最終確認に使える局面が不足しています。記録を残したので、"
                         "新しい実験でchunk-pliesやsecondsを増やしてください。深さは自動では下げません")
    report = {"counts": {role: len(rows) for role, rows in datasets.items()},
              "current_counts": {role: len(rows) for role, rows in current.items()},
              "excluded": dict(excluded), "teacher_depths": dict(depths), "terminal_results_used": False}
    save(folder / "data-summary.json", report)
    return datasets


def save_torch(path, value):
    temporary = path.with_name(path.name + ".tmp")
    torch.save(value, temporary)
    temporary.replace(path)


def save_model(path, model):
    temporary = path.with_name(path.name + ".tmp")
    # 保存形式は既存の対局・ブラウザ用NNと同じ。別名へ確定する。
    from .value_network import PIECES
    save(temporary, {"format": 2, "pieces": PIECES, "width": model.width, "parameters": model.parameters})
    temporary.replace(path)


def fit_generation(folder, datasets, config, device):
    model = load_network(folder / "teacher.json")
    network = TrainingNetwork(model).to(device)
    optimizer = torch.optim.Adam(network.parameters(), lr=config.learning_rate)
    rng = Random(config.seed)
    tensors = {}
    for role, rows in datasets.items():
        encoded = [encode_board({(x, y): Piece(side, name, promoted)
                                  for x, y, side, name, promoted in row["pieces"]}, row["turn"])
                   for row in rows]
        tensors[role] = (torch.tensor(encoded, dtype=torch.long, device=device),
                         torch.tensor([row["target"] for row in rows], device=device))

    def error(role):
        boards, targets = tensors[role]
        total = torch.zeros((), device=device)
        with torch.no_grad():
            for offset in range(0, len(boards), config.batch_size):
                prediction = (network(boards[offset:offset + config.batch_size]) / SCALE).tanh()
                total += (prediction - targets[offset:offset + config.batch_size]).square().sum()
        return total.item() / len(boards)

    baseline = {role: error(role) for role in tensors}
    best_error, best_epoch, epoch = baseline["validation"], 0, 0
    best = {name: value.detach().clone() for name, value in network.state_dict().items()}
    history = []
    checkpoint = folder / "fit-state.pt"
    data_hash = hashlib.sha256(json.dumps(datasets, sort_keys=True).encode()).hexdigest()
    if checkpoint.exists():
        saved = torch.load(checkpoint, map_location=device, weights_only=True)
        if saved["data_hash"] != data_hash:
            raise ValueError("再開する学習データが保存時と異なります")
        network.load_state_dict(saved["network"])
        optimizer.load_state_dict(saved["optimizer"])
        rng.setstate(saved["rng"])
        epoch, best_epoch, best_error = saved["epoch"], saved["best_epoch"], saved["best_error"]
        best, history = saved["best"], saved["history"]
    started = perf_counter()
    boards, targets = tensors["train"]
    while epoch < config.epochs and epoch - best_epoch < config.patience:
        order = list(range(len(boards)))
        rng.shuffle(order)
        network.train()
        for offset in range(0, len(order), config.batch_size):
            indices = torch.tensor(order[offset:offset + config.batch_size], device=device)
            prediction = (network(boards[indices]) / SCALE).tanh()
            loss = (prediction - targets[indices]).square().mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
        network.eval()
        epoch += 1
        validation = error("validation")
        if validation < best_error:
            best_error, best_epoch = validation, epoch
            best = {name: value.detach().clone() for name, value in network.state_dict().items()}
        history.append({"epoch": epoch, "validation_mse": validation})
        save_torch(checkpoint, {"network": network.state_dict(), "optimizer": optimizer.state_dict(),
                               "rng": rng.getstate(), "epoch": epoch, "best": best,
                               "best_epoch": best_epoch, "best_error": best_error,
                               "history": history, "data_hash": data_hash})
    network.load_state_dict(best)
    save_model(folder / "candidate.json", network.export())
    report = {"device": str(device), "epochs": epoch, "selected_epoch": best_epoch,
              "baseline_mse": baseline, "candidate_mse": {role: error(role) for role in tensors},
              "seconds_this_run": perf_counter() - started, "history": history,
              "candidate_sha256": digest(folder / "candidate.json")}
    save(folder / "training.json", report)
    return report


def make_job(folder, models, context, config, device, **extra):
    return {"folder": str(folder), "models": {side: str(path) for side, path in models.items()},
            "model_hashes": {str(path): digest(path) for path in set(models.values())},
            "context": context, "inference_device": device,
            "inference_batch_size": config.inference_batch_size, "epsilon": config.epsilon,
            "max_game_plies": config.max_game_plies, "seconds": config.seconds, "depth": config.depth,
            "steps": config.chunk_plies, **extra}


def opening(folder, pair, teacher, config, device):
    path = folder / f"opening-{pair:03d}.json"
    if path.exists():
        return read(path)
    rng, game = Random(config.seed + pair), Game()
    scoring = evaluator(str(teacher), device, config.inference_batch_size)
    moves = []
    for _ in range(12):
        children = [(move, child) for move, child in game.successors() if outcome(child.board) is None]
        if not children:
            break
        scores = (scoring.score_many([child for _, child in children], game.turn)
                  if hasattr(scoring, "score_many") else [scoring.score(child, game.turn) for _, child in children])
        ranked = sorted(zip(scores, children), key=lambda entry: entry[0], reverse=True)
        _, (move, game) = rng.choice(ranked[:12])
        moves.append(pack(move))
    value = {"state": state(game), "episode": 0, "ply": 0, "moves": moves}
    save(path, value)
    return value


def evaluate_generation(root, folder, config, device):
    jobs = []
    starts = set()
    known = read(root / "position-roles.json")
    for pair in range(config.evaluation_pairs):
        context = opening(folder, pair, folder / "teacher.json", config, device)
        identity = key(context["state"])
        if identity in starts or identity in known:
            raise ValueError("評価の開始局面が他の組または学習・検証局面と重複しています")
        starts.add(identity)
        for side in ("black", "white"):
            models = {color: folder / ("candidate.json" if color == side else "teacher.json")
                      for color in ("black", "white")}
            jobs.append(make_job(folder / "evaluation" / f"pair-{pair:03d}-{side}", models,
                                 context, config, device, collect=False, lane=pair, role="evaluation",
                                 candidate_side=side, seed=config.seed + pair, steps=config.evaluation_max_plies,
                                 max_game_plies=config.evaluation_max_plies,
                                 seconds=config.evaluation_seconds, depth=config.evaluation_depth))
    matches = parallel(jobs, config.workers, root, "evaluation")
    counts = Counter()
    verified = []
    for job, result in zip(jobs, matches):
        game = restore(job["context"]["state"])
        frames = sorted(Path(job["folder"]).glob("step-*.json"))
        if len(frames) != result["steps"]:
            raise ValueError("評価対局の手数が一致しません")
        for path in frames:
            frame = read(path)
            if state(game) != frame["before"]:
                raise ValueError("評価対局の局面が連続していません")
            if frame["move"] is not None:
                game.play(*unpack(frame["move"]))
            if state(game) != frame["after"] or outcome(game.board) != frame["winner"]:
                raise ValueError("評価対局の棋譜を再現できません")
        if outcome(game.board) != result["winner"]:
            raise ValueError("評価対局の最終盤面と勝敗が一致しません")
        label = ("win" if result["winner"] == job["candidate_side"] else "loss") if result["winner"] else result["reason"]
        counts[label] += 1
        verified.append({"candidate_side": job["candidate_side"], "pair": job["lane"],
                         "result": label, "plies": result["steps"]})
    decided = counts["win"] + counts["loss"]
    rate = counts["win"] / decided if decided else None
    promoted = decided >= config.min_decided and rate >= config.promotion_threshold
    report = {"results": dict(counts), "decided": decided, "win_rate_completed": rate,
              "promoted_for_next_generation": promoted, "matches": verified,
              "all_trajectories_replayed": True,
              "promotion_is_statistical_proof": False}
    save(folder / "evaluation.json", report)
    return report


def run_cycle(root, config, device, inference_device):
    torch.set_num_threads(1)
    save(root / "process.json", {"pid": os.getpid(), "started": now(),
                                "training_device": str(device), "inference_device": inference_device})
    for generation in range(1, config.generations + 1):
        folder = root / f"generation-{generation:03d}"
        folder.mkdir(exist_ok=True)
        if (folder / "complete.json").exists():
            completed = read(folder / "complete.json")
            if (digest(folder / "candidate.json") != completed["training"]["candidate_sha256"]
                    or digest(folder / "teacher.json") != completed["teacher_sha256"]):
                raise ValueError("完了した世代のモデルが変更されています")
            continue
        save(root / "progress.json", {"stage": "collection", "generation": generation, "updated": now()})
        teacher = root / "initial.json"
        for previous in range(1, generation):
            previous_folder = root / f"generation-{previous:03d}"
            if read(previous_folder / "complete.json")["evaluation"]["promoted_for_next_generation"]:
                teacher = previous_folder / "candidate.json"
        if not (folder / "teacher.json").exists():
            shutil.copy2(teacher, folder / "teacher.json")
        elif digest(folder / "teacher.json") != digest(teacher):
            raise ValueError("世代の教師モデルが一致しません")
        jobs = []
        for lane in range(config.games):
            role = "test" if lane == config.games - 1 else "validation" if lane == config.games - 2 else "train"
            context = {"state": state(Game()), "episode": 0, "ply": 0}
            if generation > 1:
                context = read(root / f"generation-{generation - 1:03d}" / "selfplay" /
                               f"game-{lane:03d}" / "result.json")["context"]
            models = {side: folder / "teacher.json" for side in ("black", "white")}
            jobs.append(make_job(folder / "selfplay" / f"game-{lane:03d}", models, context,
                                 config, inference_device, collect=True, lane=lane, role=role,
                                 seed=config.seed + lane))
        parallel(jobs, config.workers, root, "collection")
        datasets = prepare_data(root, folder, jobs, generation, config)
        save(root / "progress.json", {"stage": "training", "generation": generation, "updated": now()})
        training = fit_generation(folder, datasets, config, device)
        save(root / "progress.json", {"stage": "evaluation", "generation": generation, "updated": now()})
        evaluation = evaluate_generation(root, folder, config, inference_device)
        report = {"generation": generation, "teacher_sha256": digest(folder / "teacher.json"),
                  "data": read(folder / "data-summary.json"), "training": training,
                  "evaluation": evaluation, "finished": now()}
        save(folder / "complete.json", report)
        print(json.dumps({"generation": generation, "counts": report["data"]["counts"],
                          "evaluation": evaluation["results"],
                          "promoted": evaluation["promoted_for_next_generation"]}), flush=True)
    reports = [read(root / f"generation-{index:03d}" / "complete.json")
               for index in range(1, config.generations + 1)]
    save(root / "complete.json", {"generations": reports, "finished": now()})
    save(root / "progress.json", {"stage": "complete", "updated": now()})


def source_hash(root):
    digestor = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digestor.update(str(path.relative_to(root)).encode())
        digestor.update(path.read_bytes())
    return digestor.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"))
    parser.add_argument("--inference-device", choices=("auto", "cpu", "mps", "cuda", "native"))
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    for field in fields(Config):
        parser.add_argument("--" + field.name.replace("_", "-"), type=field.type)
    args = parser.parse_args()
    root = args.output.resolve()
    try:
        specified = {f.name: getattr(args, f.name) for f in fields(Config) if getattr(args, f.name) is not None}
        if args.resume or args.frozen:
            manifest = read(root / "config.json")
            if args.model or any(manifest["config"][key] != value for key, value in specified.items()):
                raise ValueError("再開時にモデルや訓練条件を変更できません")
            config = Config(**manifest["config"])
        else:
            config = Config(**specified)
            model = load_network(args.model)
            # 明示したGPUが使えない場合は、実験ディレクトリを作る前に失敗させる。
            get_device(args.device or "auto")
            if args.inference_device != "native":
                get_device(args.inference_device or "auto")
            root.mkdir(parents=True)
            shutil.copytree(Path(__file__).parent, root / "source" / "koushougi",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.html", "*.mjs"))
            model.save(root / "initial.json")
            manifest = {"config": asdict(config), "source_sha256": source_hash(root / "source"),
                        "initial_sha256": digest(root / "initial.json"), "device": args.device or "auto",
                        "inference_device": args.inference_device or "auto", "created": now()}
            save(root / "config.json", manifest)
        if not args.frozen:
            environment = {**os.environ, "PYTHONPATH": str(root / "source")}
            # 同じPIDで固定コードへ切り替える。以後、作業中のソース変更に影響されない。
            os.chdir(root)
            command = [sys.executable, "-B", "-u", "-m", "koushougi.train_cycle",
                       "--output", str(root), "--frozen"]
            for option, value in (("--device", args.device), ("--inference-device", args.inference_device)):
                if value:
                    command.extend([option, value])
            os.execve(sys.executable, command, environment)
        if (Path(__file__).resolve().parent != root / "source" / "koushougi"
                or source_hash(root / "source") != manifest["source_sha256"]
                or digest(root / "initial.json") != manifest["initial_sha256"]):
            raise ValueError("固定した実行コードまたは初期モデルが変更されています")
        device = get_device(args.device or manifest["device"])
        inference = args.inference_device or manifest["inference_device"]
        inference = "native" if inference == "native" else str(get_device(inference))
        with (root / "run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                run_cycle(root, config, device, inference)
            except BaseException as error:
                save(root / "failure.json", {"type": type(error).__name__, "message": str(error),
                                              "resolved": False, "time": now()})
                raise
            if (root / "failure.json").exists():
                previous = read(root / "failure.json")
                save(root / "failure.json", {**previous, "resolved": True, "resolved_at": now()})
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

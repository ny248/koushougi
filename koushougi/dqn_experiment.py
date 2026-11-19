"""Double DQNの学習量を増やし、途中のモデルを同じ条件で比較する。"""

import argparse
from collections import Counter
import csv
from dataclasses import asdict, fields
from datetime import datetime, timezone
import fcntl
import hashlib
from itertools import product
import json
import multiprocessing
import os
from pathlib import Path
from random import Random
import shutil
import sys

import torch

from .game import Game, outcome
from .players.alpha_beta import analyze_search
from .search import WIN
from .torch_evaluation import TorchEvaluator
from .train_cycle import pack, unpack, state, restore, tuples
from .train_dqn import Config, train, save_json
from .train_value import get_device
from .value_network import load_network


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(folder):
    return hashlib.sha256(b"".join(
        str(p.relative_to(folder)).encode() + p.read_bytes()
        for p in sorted(folder.rglob("*.py")))).hexdigest()


def progress(root, stage, **details):
    save_json(root / "progress.json", {
        "stage": stage, "updated": datetime.now(timezone.utc).isoformat(), **details})


class AuditedGame(Game):
    def begin_audit(self):
        self.root_id = id(self)
        self.root_count = 0
        self.root_complete = False

    def successors(self, *, captures_only=False):
        root = getattr(self, "root_id", None) == id(self)
        for move, child in super().successors(captures_only=captures_only):
            if root:
                self.root_count += 1
            yield move, child
        if root:
            self.root_complete = True


def audited_restore(value):
    original = restore(value)
    game = AuditedGame()
    game.board, game.turn = original.board, original.turn
    return game


def run_match(job):
    """親が停止した後も残る子プロセスとの二重実行を、対局単位でも防ぐ。"""
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run_match(job)


def _run_match(job):
    """両者ともCPU倍精度、時間・候補数の制限なし。各手から再開できる。"""
    torch.set_num_threads(1)
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "job.json"
    if manifest.exists() and read(manifest) != job:
        raise ValueError("保存済みの評価対局と条件が異なります")
    save_json(manifest, job)
    for path, expected in job["model_hashes"].items():
        if digest(Path(path)) != expected:
            raise ValueError("評価用モデルが変更されています")
    if (folder / "result.json").exists():
        return read(folder / "result.json")
    models = {side: TorchEvaluator(load_network(Path(path)), device="cpu", batch_size=128)
              for side, path in job["models"].items()}
    rngs = {side: Random(job["seed"] + int(side == "white")) for side in ("black", "white")}
    paths = sorted(folder.glob("ply-*.json"))
    previous = read(paths[-1]) if paths else None
    game = audited_restore(previous["after"] if previous else job["start"])
    if previous:
        for side, value in previous["rng"].items():
            rngs[side].setstate(tuples(value))
    plies = len(paths)
    winner, reason = outcome(game.board), "ply_limit"
    if winner:
        reason = "win"
    else:
        for ply in range(plies + 1, job["max_plies"] + 1):
            before, side = state(game), game.turn
            game.begin_audit()
            result = analyze_search(game, model=models[side], time_limit=float("inf"),
                                    candidate_limit=None, max_depth=job["depth"])
            if not game.root_complete or game.root_count != (len(result.moves) if result else 0):
                raise ValueError("合法手の列挙が完了していません")
            if result is None:
                reason = "no_legal_move"
                break
            if result.depth != job["depth"] and abs(result.score) != WIN:
                raise ValueError("指定した深さの探索が完了していません")
            move = rngs[side].choice(result.best_moves)
            game.play(*move)
            winner = outcome(game.board)
            save_json(folder / f"ply-{ply:06d}.json", {
                "ply": ply, "before": before, "after": state(game), "move": pack(move),
                "winner": winner, "depth": result.depth, "score": result.score,
                "root_candidates": game.root_count, "root_enumeration_complete": game.root_complete,
                "rng": {side: rng.getstate() for side, rng in rngs.items()}})
            plies = ply
            save_json(folder / "progress.json", {"plies": plies, "depth": result.depth})
            if winner:
                reason = "win"
                break
    report = {"opening": job["opening"], "seed_index": job["seed_index"],
              "candidate_side": job["candidate_side"], "winner": winner,
              "reason": reason, "plies": plies, "folder": str(folder)}
    save_json(folder / "result.json", report)
    return report


def verify_match(job, result):
    for key in ("opening", "seed_index", "candidate_side", "folder"):
        if result[key] != job[key]:
            raise ValueError("評価対局の識別情報と結果が一致しません")
    if result["reason"] not in {"win", "ply_limit", "no_legal_move"}:
        raise ValueError("評価対局の終了理由が不正です")
    game = restore(job["start"])
    frames = sorted(Path(job["folder"]).glob("ply-*.json"))
    if len(frames) != result["plies"]:
        raise ValueError("棋譜の手数と結果が一致しません")
    depths = Counter()
    for index, path in enumerate(frames, 1):
        frame = read(path)
        if frame["ply"] != index or state(game) != frame["before"]:
            raise ValueError("評価棋譜の局面が連続していません")
        game.play(*unpack(frame["move"]))
        if state(game) != frame["after"] or outcome(game.board) != frame["winner"]:
            raise ValueError("評価棋譜を再現できません")
        if not frame["root_enumeration_complete"] or frame["root_candidates"] < 1:
            raise ValueError("全候補の列挙が記録されていません")
        if frame["depth"] != job["depth"] and abs(frame["score"]) != WIN:
            raise ValueError("評価棋譜の探索深さが不正です")
        depths[str(frame["depth"])] += 1
    if outcome(game.board) != result["winner"]:
        raise ValueError("棋譜の勝敗と結果が一致しません")
    if result["reason"] == "ply_limit" and (result["winner"] or len(frames) != job["max_plies"]):
        raise ValueError("打ち切りの記録が不正です")
    if result["reason"] == "no_legal_move" and next(game.successors(), None) is not None:
        raise ValueError("合法手なしの記録が不正です")
    if result["reason"] == "win" and not result["winner"]:
        raise ValueError("終局の記録が不正です")
    return depths


def make_openings(root, config):
    path = root / "openings.json"
    identity = {"seed": config["seed"], "plies": config["opening_plies"]}
    if path.exists():
        saved = read(path)
        actual = hashlib.sha256(json.dumps(saved["openings"], sort_keys=True).encode()).hexdigest()
        if saved["config"] != identity or saved["sha256"] != actual:
            raise ValueError("保存済みの開始局面が変更されています")
        return saved["openings"]
    rows, seen = [], set()
    for index, plies in enumerate(config["opening_plies"]):
        game, rng, moves = Game(), Random(config["seed"] + index), []
        for _ in range(plies):
            selected = None
            count = 0
            for move, child in game.successors():
                if outcome(child.board) is None:
                    count += 1
                    if rng.randrange(count) == 0:
                        selected = move, child
            if selected is None:
                raise ValueError("指定手数の開始局面を作れません")
            move, game = selected
            moves.append(pack(move))
        start = state(game)
        position_identity = json.dumps([game.turn, sorted(start["pieces"])])
        if position_identity in seen:
            raise ValueError("評価の開始局面が重複しています")
        seen.add(position_identity)
        rows.append({"id": index, "plies": plies, "moves": moves, "state": start})
    save_json(path, {"config": identity, "openings": rows,
                     "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()})
    return read(path)["openings"]


def aggregate(results, opening_count):
    labels = ("win", "loss", "ply_limit", "no_legal_move")
    counts = Counter({name: 0 for name in labels})
    groups = [Counter({name: 0 for name in labels}) for _ in range(opening_count)]
    for row in results:
        label = ("win" if row["winner"] == row["candidate_side"] else "loss") if row["winner"] else row["reason"]
        counts[label] += 1
        groups[row["opening"]][label] += 1
    differences = [group["win"] - group["loss"] for group in groups]
    observed = abs(sum(differences))
    extreme = sum(abs(sum(sign * difference for sign, difference in zip(signs, differences))) >= observed
                  for signs in product((-1, 1), repeat=opening_count))
    decided = counts["win"] + counts["loss"]
    return {"results": dict(counts), "decided": decided,
            "win_rate_completed": counts["win"] / decided if decided else None,
            "by_opening": [dict(group) for group in groups],
            "opening_cluster_label_swap_test": {
                "unit": "opening", "clusters": opening_count,
                "two_sided_p": extreme / 2 ** opening_count,
                "assumption": "model labels exchangeable independently across opening clusters",
                "scope": "one training run at fixed depth; unfinished games excluded"},
            "all_trajectories_replayed": True}


def evaluate(root, snapshot, config, workers):
    candidate = snapshot / "model.json"
    baseline = root / "initial.json"
    jobs = []
    for opening in make_openings(root, config):
        for seed_index in range(config["seeds"]):
            for side in ("black", "white"):
                models = {color: str(candidate if color == side else baseline)
                          for color in ("black", "white")}
                jobs.append({
                    "folder": str(snapshot / "evaluation" / f"opening-{opening['id']:02d}-seed-{seed_index:02d}-{side}"),
                    "models": models,
                    "model_hashes": {path: digest(Path(path)) for path in set(models.values())},
                    "opening": opening["id"], "seed_index": seed_index,
                    "seed": config["seed"] + 1000 * opening["id"] + 2 * seed_index,
                    "start": opening["state"], "candidate_side": side,
                    "max_plies": config["max_plies"], "depth": config["depth"]})
    progress(root, "evaluation", snapshot=snapshot.name, completed=0, total=len(jobs))
    if workers == 1:
        results = []
        for job in jobs:
            results.append(run_match(job))
            progress(root, "evaluation", snapshot=snapshot.name, completed=len(results), total=len(jobs))
    else:
        results_by_folder = {}
        # Poolは例外・Ctrl+Cで子プロセスを終了し、長い対局の終了待ちを残さない。
        with multiprocessing.get_context("spawn").Pool(workers) as pool:
            for result in pool.imap_unordered(run_match, jobs):
                results_by_folder[result["folder"]] = result
                progress(root, "evaluation", snapshot=snapshot.name, completed=len(results_by_folder), total=len(jobs))
        results = [results_by_folder[job["folder"]] for job in jobs]
    depths = Counter()
    for job, result in zip(jobs, results):
        for path, expected in job["model_hashes"].items():
            if digest(Path(path)) != expected:
                raise ValueError("比較中に評価用モデルが変更されています")
        depths.update(verify_match(job, result))
    report = {**aggregate(results, len(config["opening_plies"])), "matches": results,
              "depths": dict(depths), "config": config,
              "candidate_sha256": digest(candidate), "baseline_sha256": digest(baseline)}
    save_json(snapshot / "evaluation.json", report)
    return report


def write_summary(root, milestones):
    rows = []
    for games in milestones:
        folder = root / "snapshots" / f"game-{games:06d}"
        if not (folder / "evaluation.json").exists():
            continue
        training, evaluation = read(folder / "training.json"), read(folder / "evaluation.json")
        rows.append({"games": games, "steps": training["environment_steps"], "updates": training["updates"],
                     **evaluation["results"], "decided_win_rate": evaluation["win_rate_completed"],
                     "opening_cluster_p": evaluation["opening_cluster_label_swap_test"]["two_sided_p"],
                     "model": str(folder / "model.json")})
    save_json(root / "summary.json", {"milestones": rows, "automatic_model_adoption": False})
    if rows:
        path = root / "summary.csv"
        with path.with_suffix(".csv.tmp").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        path.with_suffix(".csv.tmp").replace(path)


def run(root, manifest, device, workers):
    torch.set_num_threads(1)
    config = Config(**manifest["training"])
    training_folder = root / "training"
    training_folder.mkdir(exist_ok=True)

    def on_save(report):
        if digest(root / "initial.json") != manifest["initial_sha256"]:
            raise ValueError("開始モデルが変更されています")
        progress(root, "training", games=report["games_played"], total=config.games,
                 plies=report["active_ply"], steps=report["environment_steps"], updates=report["updates"])
        games = report["games_played"]
        if games not in manifest["milestones"] or report["active_ply"] != 0:
            return
        snapshot = root / "snapshots" / f"game-{games:06d}"
        snapshot.mkdir(parents=True, exist_ok=True)
        model = snapshot / "model.json"
        if model.exists():
            if digest(model) != digest(training_folder / "candidate.json"):
                raise ValueError("保存した途中モデルと学習状態が一致しません")
        else:
            temporary = model.with_suffix(".json.tmp")
            temporary.write_bytes((training_folder / "candidate.json").read_bytes())
            temporary.replace(model)
        save_json(snapshot / "training.json", report)
        # 再開時も各対局のmanifestとモデルのハッシュを照合し、保存済みの局は再計算しない。
        evaluate(root, snapshot, manifest["evaluation"], workers)
        write_summary(root, manifest["milestones"])
        progress(root, "training", games=games, total=config.games,
                 plies=0, steps=report["environment_steps"], updates=report["updates"])

    train(training_folder, config, device=device, model=root / "initial.json",
          resume=(training_folder / "checkpoint.pt").exists(), on_save=on_save)
    write_summary(root, manifest["milestones"])
    save_json(root / "complete.json", read(root / "summary.json"))
    progress(root, "complete", games=config.games)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--device", choices=("cpu", "mps", "cuda", "auto"))
    parser.add_argument("--workers", type=int)
    parser.add_argument("--milestones", nargs="+", type=int)
    parser.add_argument("--evaluation-depth", type=int)
    parser.add_argument("--evaluation-seeds", type=int)
    parser.add_argument("--evaluation-max-plies", type=int)
    parser.add_argument("--opening-plies", nargs="+", type=int)
    for field in fields(Config):
        if field.name != "games":
            parser.add_argument("--" + field.name.replace("_", "-"), type=field.type)
    args = parser.parse_args()
    root = args.output.resolve()
    try:
        if args.status:
            print(json.dumps(read(root / "progress.json"), ensure_ascii=False, indent=2))
            if (root / "summary.json").exists():
                print(json.dumps(read(root / "summary.json"), ensure_ascii=False, indent=2))
            if (root / "failure.json").exists():
                print(json.dumps(read(root / "failure.json"), ensure_ascii=False, indent=2))
            return
        training_args = {f.name: getattr(args, f.name) for f in fields(Config)
                         if f.name != "games" and getattr(args, f.name) is not None}
        evaluation_args = {key: value for key, value in {
            "depth": args.evaluation_depth, "seeds": args.evaluation_seeds,
            "max_plies": args.evaluation_max_plies, "opening_plies": args.opening_plies}.items() if value is not None}
        if args.resume or args.frozen:
            manifest = read(root / "config.json")
            if args.model is not None:
                raise ValueError("再開時は開始モデルを変更できません")
            if any(manifest["training"][key] != value for key, value in training_args.items()):
                raise ValueError("再開時は学習条件を変更できません")
            if any(manifest["evaluation"][key] != value for key, value in evaluation_args.items()):
                raise ValueError("再開時は評価条件を変更できません")
            if args.milestones is not None and manifest["milestones"] != args.milestones:
                raise ValueError("再開時は保存する局数を変更できません")
        else:
            milestones = args.milestones or [20, 50, 100]
            if milestones != sorted(set(milestones)) or min(milestones) < 1:
                raise ValueError("milestonesは正の局数を小さい順に重複なく指定してください")
            config = Config(**{"target_interval": 100, **training_args, "games": max(milestones)})
            evaluation = {"depth": 2, "seeds": 2, "max_plies": 1500,
                          "opening_plies": [0, 4, 8, 12, 16, 20, 24, 32],
                          "seed": config.seed + 1, **evaluation_args}
            opening_plies = evaluation["opening_plies"]
            if min(evaluation["depth"], evaluation["seeds"], evaluation["max_plies"]) < 1 or not 1 <= len(opening_plies) <= 16 or min(opening_plies) < 0 or len(set(opening_plies)) != len(opening_plies):
                raise ValueError("評価条件が不正です（開始局面は重複なく1〜16種類）")
            get_device(args.device or "cpu")
            if args.workers is not None and args.workers < 1:
                raise ValueError("workersは1以上にしてください")
            model = load_network(args.model)
            root.mkdir(parents=True, exist_ok=False)
            shutil.copytree(Path(__file__).parent, root / "source" / "koushougi",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.html", "*.mjs"))
            model.save(root / "initial.json")
            manifest = {"training": asdict(config), "evaluation": evaluation, "milestones": milestones,
                        "device": args.device or "cpu", "workers": args.workers or 4,
                        "source_sha256": source_digest(root / "source"), "initial_sha256": digest(root / "initial.json")}
            save_json(root / "config.json", manifest)
        if not args.frozen:
            os.chdir(root)
            command = [sys.executable, "-B", "-u", "-m", "koushougi.dqn_experiment",
                       "--output", str(root), "--frozen"]
            for name in ("device", "workers"):
                if getattr(args, name) is not None:
                    command.extend(["--" + name, str(getattr(args, name))])
            os.execve(sys.executable, command, {**os.environ, "PYTHONPATH": str(root / "source")})
        if Path(__file__).resolve().parent != root / "source" / "koushougi" or source_digest(root / "source") != manifest["source_sha256"] or digest(root / "initial.json") != manifest["initial_sha256"]:
            raise ValueError("固定した実行コードまたは初期モデルが変更されています")
        device = str(get_device(args.device or manifest["device"]))
        workers = args.workers if args.workers is not None else manifest["workers"]
        if workers < 1:
            raise ValueError("workersは1以上にしてください")
        with (root / "run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                run(root, manifest, device, workers)
            except BaseException as error:
                save_json(root / "failure.json", {"type": type(error).__name__, "message": str(error), "resolved": False})
                raise
            if (root / "failure.json").exists():
                previous = read(root / "failure.json")
                save_json(root / "failure.json", {**previous, "resolved": True})
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

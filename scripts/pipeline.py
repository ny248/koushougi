"""訓練パイプライン

JSON形式の訓練計画を読み込んで実行するオーケストレーター。

Usage:
    # 計画ファイルから実行
    python scripts/pipeline.py run training_plan.json

    # サンプル計画を生成
    python scripts/pipeline.py init --output training_plan.json

    # 計画の検証
    python scripts/pipeline.py validate training_plan.json
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import subprocess
import logging
import json
from pathlib import Path
from datetime import datetime

from scripts.lib.logger import setup_logger


SAMPLE_PLAN = {
    "name": "koushougi_training_v1",
    "description": "広将棋AI訓練計画",
    "output_dir": "models/training_v1",
    "common": {
        "lite": True,
        "game_timeout": 60,
        "minimax_depth": 1,
        "batch_size": 64,
    },
    "phases": [
        {
            "name": "bootstrap",
            "type": "generate",
            "games": 500,
            "mode": "minimax-vs-minimax",
        },
        {
            "name": "supervised",
            "type": "train",
            "method": "supervised",
            "data": "bootstrap",
            "epochs": 20,
            "lr": 0.001,
        },
        {
            "name": "selfplay_1",
            "type": "generate",
            "games": 200,
            "mode": "nn-vs-minimax",
            "model": "supervised",
            "epsilon": 0.5,
        },
        {
            "name": "reinforce_1",
            "type": "train",
            "method": "reinforce",
            "data": ["bootstrap", "selfplay_1"],
            "model": "supervised",
            "epochs": 20,
            "lr": 0.0001,
        },
        {
            "name": "selfplay_2",
            "type": "generate",
            "games": 200,
            "mode": "nn-vs-minimax",
            "model": "reinforce_1",
            "epsilon": 0.3,
        },
        {
            "name": "reinforce_2",
            "type": "train",
            "method": "reinforce",
            "data": ["bootstrap", "selfplay_1", "selfplay_2"],
            "model": "reinforce_1",
            "epochs": 20,
            "lr": 0.0001,
        },
    ],
}


def run_command(cmd: list[str], logger, timeout: int = None) -> bool:
    """コマンドを実行"""
    logger.info(f"実行: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=timeout, capture_output=False)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"タイムアウト: {timeout}秒")
        return False
    except Exception as e:
        logger.error(f"エラー: {e}")
        return False


def resolve_path(plan: dict, phase_name: str, suffix: str) -> Path:
    """フェーズの出力パスを解決"""
    output_dir = Path(plan["output_dir"])
    return output_dir / phase_name / suffix


def resolve_model_path(plan: dict, model_ref: str, completed: dict) -> Path:
    """モデル参照をパスに解決"""
    if model_ref in completed:
        # 完了済みフェーズの出力を参照
        return resolve_path(plan, model_ref, "best_model.pth")
    else:
        # 外部パス
        return Path(model_ref)


def resolve_data_paths(plan: dict, data_ref, completed: dict) -> list[Path]:
    """データ参照をパスリストに解決"""
    if isinstance(data_ref, str):
        data_ref = [data_ref]

    paths = []
    for ref in data_ref:
        if ref in completed:
            paths.append(resolve_path(plan, ref, "games.jsonl"))
        else:
            paths.append(Path(ref))
    return paths


def run_generate_phase(plan: dict, phase: dict, completed: dict, logger) -> bool:
    """棋譜生成フェーズを実行"""
    common = plan.get("common", {})
    phase_name = phase["name"]
    output_dir = resolve_path(plan, phase_name, "")
    output_dir.mkdir(parents=True, exist_ok=True)

    games_file = output_dir / "games.jsonl"

    cmd = [
        "python", "scripts/generate_games.py",
        "--games", str(phase.get("games", 100)),
        "--output", str(games_file),
        "--mode", phase.get("mode", "minimax-vs-minimax"),
        "--minimax-depth", str(phase.get("minimax_depth", common.get("minimax_depth", 1))),
        "--timeout", str(phase.get("game_timeout", common.get("game_timeout", 60))),
        "--epsilon", str(phase.get("epsilon", 0.3)),
    ]

    # モデル指定
    if "model" in phase:
        model_path = resolve_model_path(plan, phase["model"], completed)
        if model_path.exists():
            cmd.extend(["--model", str(model_path)])

    if common.get("lite") or phase.get("lite"):
        cmd.append("--lite")

    timeout = phase.get("games", 100) * phase.get("game_timeout", common.get("game_timeout", 60)) + 300
    return run_command(cmd, logger, timeout=timeout)


def run_train_phase(plan: dict, phase: dict, completed: dict, logger) -> bool:
    """訓練フェーズを実行"""
    common = plan.get("common", {})
    phase_name = phase["name"]
    output_dir = resolve_path(plan, phase_name, "")
    output_dir.mkdir(parents=True, exist_ok=True)

    method = phase.get("method", "supervised")

    # データパス解決
    data_paths = resolve_data_paths(plan, phase["data"], completed)
    existing_paths = [p for p in data_paths if p.exists()]
    if not existing_paths:
        logger.error(f"データが見つかりません: {data_paths}")
        return False

    # 複数データの場合、ディレクトリを指定するか最初のファイルを使用
    if len(existing_paths) == 1:
        data_arg = str(existing_paths[0])
    else:
        # 複数ファイルの場合、シンボリックリンクで統合ディレクトリを作成
        data_dir = output_dir / "data"
        data_dir.mkdir(exist_ok=True)
        for i, p in enumerate(existing_paths):
            link = data_dir / f"{i:03d}_{p.stem}.jsonl"
            if not link.exists():
                link.symlink_to(p.resolve())
        data_arg = str(data_dir)

    cmd = [
        "python", "scripts/train.py", method,
        "--data", data_arg,
        "--output", str(output_dir),
        "--epochs", str(phase.get("epochs", 20)),
        "--batch-size", str(phase.get("batch_size", common.get("batch_size", 64))),
        "--lr", str(phase.get("lr", 0.001 if method == "supervised" else 0.0001)),
    ]

    # モデル指定
    if "model" in phase:
        model_path = resolve_model_path(plan, phase["model"], completed)
        if model_path.exists():
            cmd.extend(["--load", str(model_path)])

    if common.get("lite") or phase.get("lite"):
        cmd.append("--lite")

    timeout = phase.get("epochs", 20) * 600
    return run_command(cmd, logger, timeout=timeout)


def run_plan(plan: dict, logger, resume_from: str = None) -> bool:
    """訓練計画を実行"""
    logger.info(f"=== 訓練計画: {plan.get('name', 'unnamed')} ===")
    logger.info(f"説明: {plan.get('description', '')}")

    output_dir = Path(plan["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 進捗ファイル
    progress_file = output_dir / "progress.json"
    if progress_file.exists():
        with open(progress_file) as f:
            progress = json.load(f)
    else:
        progress = {"completed": [], "started_at": datetime.now().isoformat()}

    completed = {name: True for name in progress["completed"]}

    # レジューム位置を探す
    skip = resume_from is not None
    if resume_from and resume_from not in [p["name"] for p in plan["phases"]]:
        logger.error(f"フェーズが見つかりません: {resume_from}")
        return False

    for phase in plan["phases"]:
        phase_name = phase["name"]

        if skip:
            if phase_name == resume_from:
                skip = False
            else:
                logger.info(f"スキップ: {phase_name}")
                continue

        if phase_name in completed:
            logger.info(f"完了済み: {phase_name}")
            continue

        logger.info(f"--- フェーズ: {phase_name} ({phase['type']}) ---")

        if phase["type"] == "generate":
            success = run_generate_phase(plan, phase, completed, logger)
        elif phase["type"] == "train":
            success = run_train_phase(plan, phase, completed, logger)
        else:
            logger.error(f"不明なフェーズタイプ: {phase['type']}")
            success = False

        if success:
            progress["completed"].append(phase_name)
            completed[phase_name] = True
            with open(progress_file, "w") as f:
                json.dump(progress, f, indent=2)
            logger.info(f"完了: {phase_name}")
        else:
            logger.error(f"失敗: {phase_name}")
            return False

    progress["finished_at"] = datetime.now().isoformat()
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)

    logger.info("=== 訓練計画完了 ===")
    return True


def validate_plan(plan: dict, logger) -> bool:
    """訓練計画を検証"""
    errors = []

    if "output_dir" not in plan:
        errors.append("output_dir が必要です")

    if "phases" not in plan or not plan["phases"]:
        errors.append("phases が必要です")

    phase_names = set()
    for i, phase in enumerate(plan.get("phases", [])):
        if "name" not in phase:
            errors.append(f"phases[{i}]: name が必要です")
        elif phase["name"] in phase_names:
            errors.append(f"phases[{i}]: 重複した名前 '{phase['name']}'")
        else:
            phase_names.add(phase["name"])

        if "type" not in phase:
            errors.append(f"phases[{i}]: type が必要です")
        elif phase["type"] not in ["generate", "train"]:
            errors.append(f"phases[{i}]: 不明なtype '{phase['type']}'")

        if phase.get("type") == "train" and "data" not in phase:
            errors.append(f"phases[{i}]: train には data が必要です")

    if errors:
        for e in errors:
            logger.error(e)
        return False

    logger.info("計画は有効です")
    return True


def init_plan(output: str, logger):
    """サンプル計画を出力"""
    with open(output, "w") as f:
        json.dump(SAMPLE_PLAN, f, indent=2, ensure_ascii=False)
    logger.info(f"サンプル計画を出力: {output}")


def main():
    parser = argparse.ArgumentParser(description="訓練パイプライン")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = subparsers.add_parser("run", help="計画を実行")
    run_p.add_argument("plan", type=str, help="計画ファイル (JSON)")
    run_p.add_argument("--resume-from", type=str, help="指定フェーズから再開")
    run_p.add_argument("--verbose", "-v", action="store_true")

    # init
    init_p = subparsers.add_parser("init", help="サンプル計画を生成")
    init_p.add_argument("--output", "-o", type=str, default="training_plan.json")
    init_p.add_argument("--verbose", "-v", action="store_true")

    # validate
    val_p = subparsers.add_parser("validate", help="計画を検証")
    val_p.add_argument("plan", type=str, help="計画ファイル (JSON)")
    val_p.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("pipeline", level=log_level)

    if args.command == "run":
        with open(args.plan) as f:
            plan = json.load(f)
        if not validate_plan(plan, logger):
            sys.exit(1)
        if not run_plan(plan, logger, args.resume_from):
            sys.exit(1)

    elif args.command == "init":
        init_plan(args.output, logger)

    elif args.command == "validate":
        with open(args.plan) as f:
            plan = json.load(f)
        if not validate_plan(plan, logger):
            sys.exit(1)


if __name__ == "__main__":
    main()

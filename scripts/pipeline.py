"""訓練パイプライン

JSON形式の訓練計画を読み込んで実行するオーケストレーター。
条件分岐とループをサポート。

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
    "description": "広将棋AI訓練計画（条件分岐・ループ対応）",
    "output_dir": "models/training_v1",
    "common": {
        "lite": True,
        "game_timeout": 60,
        "minimax_depth": 1,
        "batch_size": 64,
    },
    "variables": {
        "iteration": 0,
        "best_win_rate": 0.0,
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
            "epochs": 30,
            "lr": 0.001,
        },
        {
            "name": "eval_supervised",
            "type": "eval",
            "model": "supervised",
            "games": 50,
            "target_win_rate": 0.1,
            "on_fail": "supervised",
        },
        {
            "name": "selfplay_loop",
            "type": "loop",
            "max_iterations": 1000,
            "phases": [
                {
                    "name": "selfplay_{iteration}",
                    "type": "generate",
                    "games": 100,
                    "mode": "nn-vs-minimax",
                    "model": "@latest",
                    "epsilon": "{0.5 - iteration * 0.02}",
                    "epsilon_min": 0.1,
                },
                {
                    "name": "reinforce_{iteration}",
                    "type": "train",
                    "method": "reinforce",
                    "data": "@all_games",
                    "model": "@latest",
                    "epochs": 10,
                    "lr": 0.0001,
                },
                {
                    "name": "eval_{iteration}",
                    "type": "eval",
                    "model": "reinforce_{iteration}",
                    "games": 30,
                    "save_if_best": True,
                },
            ],
        },
    ],
}


class PipelineContext:
    """パイプライン実行コンテキスト"""

    def __init__(self, plan: dict, output_dir: Path, logger):
        self.plan = plan
        self.output_dir = output_dir
        self.logger = logger
        self.common = plan.get("common", {})

        # 進捗管理
        self.progress_file = output_dir / "progress.json"
        self.progress = self._load_progress()
        self.completed = set(self.progress.get("completed", []))

        # 変数
        self.variables = plan.get("variables", {}).copy()
        self.variables.update(self.progress.get("variables", {}))

        # 動的参照
        self.latest_model = self.progress.get("latest_model")
        self.best_model = self.progress.get("best_model")
        self.best_win_rate = self.progress.get("best_win_rate", 0.0)
        self.all_game_files = self.progress.get("all_game_files", [])

    def _load_progress(self) -> dict:
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {"completed": [], "started_at": datetime.now().isoformat()}

    def save_progress(self):
        self.progress["completed"] = list(self.completed)
        self.progress["variables"] = self.variables
        self.progress["latest_model"] = self.latest_model
        self.progress["best_model"] = self.best_model
        self.progress["best_win_rate"] = self.best_win_rate
        self.progress["all_game_files"] = self.all_game_files
        with open(self.progress_file, "w") as f:
            json.dump(self.progress, f, indent=2)

    def resolve_name(self, template: str) -> str:
        """変数を展開した名前を返す"""
        result = template
        for key, value in self.variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def resolve_value(self, value):
        """値を解決（式の評価も含む）"""
        if not isinstance(value, str):
            return value

        # 式の評価 {expr}
        if value.startswith("{") and value.endswith("}"):
            expr = value[1:-1]
            try:
                return eval(expr, {"__builtins__": {}}, self.variables)
            except Exception:
                return value

        # 変数展開
        return self.resolve_name(value)

    def resolve_model(self, model_ref: str) -> Path:
        """モデル参照をパスに解決"""
        if model_ref == "@latest":
            if self.latest_model:
                return Path(self.latest_model)
            return None
        elif model_ref == "@best":
            if self.best_model:
                return Path(self.best_model)
            return None
        else:
            resolved = self.resolve_name(model_ref)
            # フェーズ名として解決
            phase_path = self.output_dir / resolved / "best_model.pth"
            if phase_path.exists():
                return phase_path
            # 直接パス
            return Path(resolved) if Path(resolved).exists() else None

    def resolve_data(self, data_ref) -> list[Path]:
        """データ参照をパスリストに解決"""
        if data_ref == "@all_games":
            return [Path(f) for f in self.all_game_files if Path(f).exists()]

        if isinstance(data_ref, str):
            data_ref = [data_ref]

        paths = []
        for ref in data_ref:
            resolved = self.resolve_name(ref)
            phase_path = self.output_dir / resolved / "games.jsonl"
            if phase_path.exists():
                paths.append(phase_path)
            elif Path(resolved).exists():
                paths.append(Path(resolved))
        return paths

    def register_games(self, games_file: Path):
        """棋譜ファイルを登録"""
        path_str = str(games_file)
        if path_str not in self.all_game_files:
            self.all_game_files.append(path_str)

    def update_model(self, model_path: Path):
        """最新モデルを更新"""
        self.latest_model = str(model_path)


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


def run_generate_phase(ctx: PipelineContext, phase: dict) -> bool:
    """棋譜生成フェーズを実行"""
    phase_name = ctx.resolve_name(phase["name"])
    output_dir = ctx.output_dir / phase_name
    output_dir.mkdir(parents=True, exist_ok=True)

    games_file = output_dir / "games.jsonl"

    # epsilon計算
    epsilon = ctx.resolve_value(phase.get("epsilon", 0.3))
    epsilon_min = phase.get("epsilon_min", 0.1)
    epsilon = max(epsilon, epsilon_min)

    cmd = [
        "python", "scripts/generate_games.py",
        "--games", str(phase.get("games", 100)),
        "--output", str(games_file),
        "--mode", phase.get("mode", "minimax-vs-minimax"),
        "--minimax-depth", str(phase.get("minimax_depth", ctx.common.get("minimax_depth", 1))),
        "--timeout", str(phase.get("game_timeout", ctx.common.get("game_timeout", 60))),
        "--epsilon", str(epsilon),
    ]

    # モデル指定
    if "model" in phase:
        model_path = ctx.resolve_model(phase["model"])
        if model_path and model_path.exists():
            cmd.extend(["--model", str(model_path)])

    if ctx.common.get("lite") or phase.get("lite"):
        cmd.append("--lite")

    timeout = phase.get("games", 100) * phase.get("game_timeout", ctx.common.get("game_timeout", 60)) + 300
    success = run_command(cmd, ctx.logger, timeout=timeout)

    if success and games_file.exists():
        ctx.register_games(games_file)

    return success


def run_train_phase(ctx: PipelineContext, phase: dict) -> bool:
    """訓練フェーズを実行"""
    phase_name = ctx.resolve_name(phase["name"])
    output_dir = ctx.output_dir / phase_name
    output_dir.mkdir(parents=True, exist_ok=True)

    method = phase.get("method", "supervised")

    # データパス解決
    data_paths = ctx.resolve_data(phase["data"])
    if not data_paths:
        ctx.logger.error(f"データが見つかりません: {phase['data']}")
        return False

    # 複数データの場合
    if len(data_paths) == 1:
        data_arg = str(data_paths[0])
    else:
        data_dir = output_dir / "data"
        data_dir.mkdir(exist_ok=True)
        for i, p in enumerate(data_paths):
            link = data_dir / f"{i:03d}_{p.stem}.jsonl"
            if not link.exists():
                link.symlink_to(p.resolve())
        data_arg = str(data_dir)

    cmd = [
        "python", "scripts/train.py", method,
        "--data", data_arg,
        "--output", str(output_dir),
        "--epochs", str(phase.get("epochs", 20)),
        "--batch-size", str(phase.get("batch_size", ctx.common.get("batch_size", 64))),
        "--lr", str(phase.get("lr", 0.001 if method == "supervised" else 0.0001)),
    ]

    # モデル指定
    if "model" in phase:
        model_path = ctx.resolve_model(phase["model"])
        if model_path and model_path.exists():
            cmd.extend(["--load", str(model_path)])

    if ctx.common.get("lite") or phase.get("lite"):
        cmd.append("--lite")

    timeout = phase.get("epochs", 20) * 600
    success = run_command(cmd, ctx.logger, timeout=timeout)

    if success:
        best_model = output_dir / "best_model.pth"
        if best_model.exists():
            ctx.update_model(best_model)

    return success


def run_eval_phase(ctx: PipelineContext, phase: dict) -> dict:
    """評価フェーズを実行

    Returns:
        {"success": bool, "win_rate": float, "passed": bool}
    """
    phase_name = ctx.resolve_name(phase["name"])
    output_dir = ctx.output_dir / phase_name
    output_dir.mkdir(parents=True, exist_ok=True)

    games = phase.get("games", 30)
    games_file = output_dir / "eval_games.jsonl"

    # モデルで対戦
    model_path = ctx.resolve_model(phase["model"])
    if not model_path or not model_path.exists():
        ctx.logger.error(f"評価モデルが見つかりません: {phase['model']}")
        return {"success": False, "win_rate": 0, "passed": False}

    cmd = [
        "python", "scripts/generate_games.py",
        "--games", str(games),
        "--output", str(games_file),
        "--mode", "nn-vs-minimax",
        "--minimax-depth", str(phase.get("minimax_depth", ctx.common.get("minimax_depth", 1))),
        "--timeout", str(phase.get("game_timeout", ctx.common.get("game_timeout", 60))),
        "--epsilon", "0.0",
        "--model", str(model_path),
    ]

    if ctx.common.get("lite") or phase.get("lite"):
        cmd.append("--lite")

    timeout = games * phase.get("game_timeout", ctx.common.get("game_timeout", 60)) + 300
    success = run_command(cmd, ctx.logger, timeout=timeout)

    if not success or not games_file.exists():
        return {"success": False, "win_rate": 0, "passed": False}

    # 勝率計算
    stats = _collect_game_stats(games_file)
    win_rate = stats.get("nn_win_rate", 0)

    ctx.logger.info(f"評価結果: 勝率 {win_rate:.1%} ({stats['nn_wins']}/{stats['total']})")

    # 結果保存
    with open(output_dir / "eval_result.json", "w") as f:
        json.dump({
            "win_rate": win_rate,
            "stats": stats,
            "model": str(model_path),
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)

    # ベストモデル更新
    if phase.get("save_if_best") and win_rate > ctx.best_win_rate:
        ctx.best_win_rate = win_rate
        ctx.best_model = str(model_path)
        ctx.logger.info(f"新ベスト: {win_rate:.1%}")

    # 閾値チェック
    target = phase.get("target_win_rate", 0)
    passed = win_rate >= target

    return {"success": True, "win_rate": win_rate, "passed": passed}


def run_loop_phase(ctx: PipelineContext, phase: dict) -> bool:
    """ループフェーズを実行"""
    max_iterations = phase.get("max_iterations", 100)
    inner_phases = phase.get("phases", [])

    ctx.logger.info(f"ループ開始: 最大 {max_iterations} イテレーション")

    for i in range(max_iterations):
        ctx.variables["iteration"] = i
        ctx.logger.info(f"=== イテレーション {i + 1}/{max_iterations} ===")

        for inner in inner_phases:
            result = run_phase(ctx, inner)

            if isinstance(result, dict):
                # eval結果
                if not result["success"]:
                    return False
            elif not result:
                return False

        ctx.save_progress()

    return True


def run_phase(ctx: PipelineContext, phase: dict):
    """フェーズを実行"""
    phase_type = phase["type"]
    phase_name = ctx.resolve_name(phase["name"])

    if phase_name in ctx.completed and phase_type != "loop":
        ctx.logger.info(f"完了済み: {phase_name}")
        return True

    ctx.logger.info(f"--- フェーズ: {phase_name} ({phase_type}) ---")

    if phase_type == "generate":
        success = run_generate_phase(ctx, phase)
    elif phase_type == "train":
        success = run_train_phase(ctx, phase)
    elif phase_type == "eval":
        result = run_eval_phase(ctx, phase)
        if not result["success"]:
            return False
        if not result["passed"] and "on_fail" in phase:
            # 閾値未達成時のジャンプ
            ctx.logger.warning(f"閾値未達成、{phase['on_fail']} へ戻る")
            # 該当フェーズを未完了に
            ctx.completed.discard(phase["on_fail"])
            return True
        success = True
    elif phase_type == "loop":
        success = run_loop_phase(ctx, phase)
    else:
        ctx.logger.error(f"不明なフェーズタイプ: {phase_type}")
        return False

    if success:
        ctx.completed.add(phase_name)
        ctx.save_progress()
        ctx.logger.info(f"完了: {phase_name}")

    return success


def run_plan(plan: dict, logger, resume_from: str = None) -> bool:
    """訓練計画を実行"""
    logger.info(f"=== 訓練計画: {plan.get('name', 'unnamed')} ===")
    logger.info(f"説明: {plan.get('description', '')}")

    output_dir = Path(plan["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(plan, output_dir, logger)

    # レジューム
    skip = resume_from is not None
    if resume_from:
        all_names = [p["name"] for p in plan["phases"]]
        if resume_from not in all_names:
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

        result = run_phase(ctx, phase)
        if isinstance(result, dict):
            if not result["success"]:
                return False
        elif not result:
            return False

    ctx.progress["finished_at"] = datetime.now().isoformat()
    ctx.save_progress()

    logger.info("=== 訓練計画完了 ===")
    return True


def _collect_game_stats(games_file: Path) -> dict:
    """棋譜ファイルから統計を収集"""
    stats = {
        "total": 0,
        "sente_wins": 0,
        "gote_wins": 0,
        "draws": 0,
        "nn_wins": 0,
        "minimax_wins": 0,
    }

    if not games_file.exists():
        return stats

    with open(games_file) as f:
        for line in f:
            game = json.loads(line)
            stats["total"] += 1

            winner = game.get("kifu", {}).get("winner")
            players = game.get("players", {})

            if winner == 0:
                stats["sente_wins"] += 1
                if "neural" in players.get("sente", ""):
                    stats["nn_wins"] += 1
                else:
                    stats["minimax_wins"] += 1
            elif winner == 1:
                stats["gote_wins"] += 1
                if "neural" in players.get("gote", ""):
                    stats["nn_wins"] += 1
                else:
                    stats["minimax_wins"] += 1
            else:
                stats["draws"] += 1

    if stats["total"] > 0:
        stats["nn_win_rate"] = stats["nn_wins"] / stats["total"]
        stats["minimax_win_rate"] = stats["minimax_wins"] / stats["total"]

    return stats


def validate_plan(plan: dict, logger) -> bool:
    """訓練計画を検証"""
    errors = []

    if "output_dir" not in plan:
        errors.append("output_dir が必要です")

    if "phases" not in plan or not plan["phases"]:
        errors.append("phases が必要です")

    def validate_phases(phases, prefix=""):
        for i, phase in enumerate(phases):
            loc = f"{prefix}phases[{i}]"
            if "name" not in phase:
                errors.append(f"{loc}: name が必要です")
            if "type" not in phase:
                errors.append(f"{loc}: type が必要です")
            elif phase["type"] not in ["generate", "train", "eval", "loop"]:
                errors.append(f"{loc}: 不明なtype '{phase['type']}'")

            if phase.get("type") == "train" and "data" not in phase:
                errors.append(f"{loc}: train には data が必要です")

            if phase.get("type") == "eval" and "model" not in phase:
                errors.append(f"{loc}: eval には model が必要です")

            if phase.get("type") == "loop":
                if "phases" not in phase:
                    errors.append(f"{loc}: loop には phases が必要です")
                else:
                    validate_phases(phase["phases"], f"{loc}.")

    validate_phases(plan.get("phases", []))

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

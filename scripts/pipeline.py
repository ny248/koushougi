"""訓練パイプライン

棋譜生成と訓練を繰り返すオーケストレーションスクリプト。

Usage:
    # Phase 1: Minimax同士で教師データ生成 → 教師あり学習
    python scripts/pipeline.py bootstrap --games 500 --output models/bootstrap_v1

    # Phase 2: NN vs Minimax で自己対戦 → 強化学習（繰り返し）
    python scripts/pipeline.py selfplay --model models/bootstrap_v1 --output models/rl_v1 --iterations 10

    # フルパイプライン（bootstrap → selfplay）
    python scripts/pipeline.py full --output models/full_v1 --bootstrap-games 500 --selfplay-iterations 10
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


def bootstrap(args, logger):
    """Phase 1: Minimax同士で教師データ → 教師あり学習"""
    logger.info("=== Bootstrap Phase ===")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # 棋譜生成
    games_file = data_dir / "bootstrap_games.jsonl"
    logger.info(f"棋譜生成: {args.games}ゲーム")

    cmd = [
        "python", "scripts/generate_games.py",
        "--games", str(args.games),
        "--output", str(games_file),
        "--mode", "minimax-vs-minimax",
        "--minimax-depth", str(args.minimax_depth),
        "--timeout", str(args.game_timeout),
    ]
    if args.lite:
        cmd.append("--lite")

    if not run_command(cmd, logger, timeout=args.games * args.game_timeout + 300):
        logger.error("棋譜生成失敗")
        return False

    # 教師あり学習
    logger.info(f"教師あり学習: {args.epochs}エポック")

    cmd = [
        "python", "scripts/train.py", "supervised",
        "--data", str(games_file),
        "--output", str(output_dir),
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--lr", str(args.lr),
    ]
    if args.lite:
        cmd.append("--lite")

    if not run_command(cmd, logger, timeout=args.epochs * 300):
        logger.error("教師あり学習失敗")
        return False

    logger.info(f"Bootstrap完了: {output_dir}")
    return True


def selfplay(args, logger):
    """Phase 2: NN vs Minimax で自己対戦 → 強化学習"""
    logger.info("=== Self-Play Phase ===")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # 初期モデル
    if args.model:
        current_model = Path(args.model) / "best_model.pth"
        if not current_model.exists():
            current_model = Path(args.model) / "final_model.pth"
    else:
        current_model = None

    stats = {
        "iterations": [],
        "start_time": datetime.now().isoformat(),
    }

    for iteration in range(1, args.iterations + 1):
        logger.info(f"--- Iteration {iteration}/{args.iterations} ---")

        iter_data = data_dir / f"iter_{iteration:03d}.jsonl"

        # 棋譜生成（NN vs Minimax）
        logger.info(f"棋譜生成: {args.games_per_iter}ゲーム")

        cmd = [
            "python", "scripts/generate_games.py",
            "--games", str(args.games_per_iter),
            "--output", str(iter_data),
            "--mode", "nn-vs-minimax",
            "--minimax-depth", str(args.minimax_depth),
            "--epsilon", str(args.epsilon),
            "--timeout", str(args.game_timeout),
        ]
        if current_model and current_model.exists():
            cmd.extend(["--model", str(current_model)])
        if args.lite:
            cmd.append("--lite")

        if not run_command(cmd, logger, timeout=args.games_per_iter * args.game_timeout + 300):
            logger.warning(f"Iteration {iteration}: 棋譜生成に問題あり、スキップ")
            continue

        # 統計収集
        iter_stats = _collect_game_stats(iter_data)
        logger.info(f"  勝率: {iter_stats.get('nn_win_rate', 0):.1%}")

        # 強化学習
        logger.info(f"強化学習: {args.epochs_per_iter}エポック")

        cmd = [
            "python", "scripts/train.py", "reinforce",
            "--data", str(data_dir),
            "--output", str(output_dir),
            "--epochs", str(args.epochs_per_iter),
            "--batch-size", str(args.batch_size),
            "--lr", str(args.lr),
            "--resume",
        ]
        if args.lite:
            cmd.append("--lite")

        if not run_command(cmd, logger, timeout=args.epochs_per_iter * 300):
            logger.warning(f"Iteration {iteration}: 学習に問題あり")

        # モデル更新
        current_model = output_dir / "best_model.pth"

        # 統計記録
        iter_stats["iteration"] = iteration
        stats["iterations"].append(iter_stats)

        with open(output_dir / "pipeline_stats.json", "w") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    stats["end_time"] = datetime.now().isoformat()
    with open(output_dir / "pipeline_stats.json", "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info(f"Self-Play完了: {output_dir}")
    return True


def full_pipeline(args, logger):
    """フルパイプライン（bootstrap → selfplay）"""
    logger.info("=== Full Pipeline ===")

    output_dir = Path(args.output)

    # Bootstrap
    bootstrap_args = argparse.Namespace(
        output=str(output_dir / "bootstrap"),
        games=args.bootstrap_games,
        epochs=args.bootstrap_epochs,
        batch_size=args.batch_size,
        lr=0.001,
        minimax_depth=args.minimax_depth,
        game_timeout=args.game_timeout,
        lite=args.lite,
    )
    if not bootstrap(bootstrap_args, logger):
        return False

    # Self-Play
    selfplay_args = argparse.Namespace(
        output=str(output_dir / "selfplay"),
        model=str(output_dir / "bootstrap"),
        iterations=args.selfplay_iterations,
        games_per_iter=args.selfplay_games,
        epochs_per_iter=args.selfplay_epochs,
        batch_size=args.batch_size,
        lr=0.0001,
        epsilon=args.epsilon,
        minimax_depth=args.minimax_depth,
        game_timeout=args.game_timeout,
        lite=args.lite,
    )
    if not selfplay(selfplay_args, logger):
        return False

    logger.info(f"フルパイプライン完了: {output_dir}")
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


def main():
    parser = argparse.ArgumentParser(description="訓練パイプライン")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Bootstrap
    bp = subparsers.add_parser("bootstrap", help="Minimax同士で教師データ生成 → 教師あり学習")
    bp.add_argument("--output", "-o", type=str, default="models/bootstrap", help="出力ディレクトリ")
    bp.add_argument("--games", type=int, default=500, help="生成ゲーム数")
    bp.add_argument("--epochs", type=int, default=20, help="学習エポック数")
    bp.add_argument("--batch-size", type=int, default=64)
    bp.add_argument("--lr", type=float, default=0.001)
    bp.add_argument("--minimax-depth", type=int, default=1)
    bp.add_argument("--game-timeout", type=int, default=60)
    bp.add_argument("--lite", action="store_true")
    bp.add_argument("--verbose", "-v", action="store_true")

    # Self-Play
    sp = subparsers.add_parser("selfplay", help="NN vs Minimax で自己対戦 → 強化学習")
    sp.add_argument("--output", "-o", type=str, default="models/selfplay", help="出力ディレクトリ")
    sp.add_argument("--model", type=str, help="初期モデルのディレクトリ")
    sp.add_argument("--iterations", type=int, default=10, help="イテレーション回数")
    sp.add_argument("--games-per-iter", type=int, default=100, help="イテレーションあたりのゲーム数")
    sp.add_argument("--epochs-per-iter", type=int, default=10, help="イテレーションあたりのエポック数")
    sp.add_argument("--batch-size", type=int, default=64)
    sp.add_argument("--lr", type=float, default=0.0001)
    sp.add_argument("--epsilon", type=float, default=0.3, help="探索率")
    sp.add_argument("--minimax-depth", type=int, default=1)
    sp.add_argument("--game-timeout", type=int, default=60)
    sp.add_argument("--lite", action="store_true")
    sp.add_argument("--verbose", "-v", action="store_true")

    # Full Pipeline
    fp = subparsers.add_parser("full", help="フルパイプライン")
    fp.add_argument("--output", "-o", type=str, default="models/full", help="出力ディレクトリ")
    fp.add_argument("--bootstrap-games", type=int, default=500)
    fp.add_argument("--bootstrap-epochs", type=int, default=20)
    fp.add_argument("--selfplay-iterations", type=int, default=10)
    fp.add_argument("--selfplay-games", type=int, default=100)
    fp.add_argument("--selfplay-epochs", type=int, default=10)
    fp.add_argument("--batch-size", type=int, default=64)
    fp.add_argument("--epsilon", type=float, default=0.3)
    fp.add_argument("--minimax-depth", type=int, default=1)
    fp.add_argument("--game-timeout", type=int, default=60)
    fp.add_argument("--lite", action="store_true")
    fp.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("pipeline", level=log_level)

    if args.mode == "bootstrap":
        bootstrap(args, logger)
    elif args.mode == "selfplay":
        selfplay(args, logger)
    elif args.mode == "full":
        full_pipeline(args, logger)


if __name__ == "__main__":
    main()

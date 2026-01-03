"""訓練パイプライン

Pythonネイティブな訓練計画を実行するオーケストレーター。

Usage:
    # モデルディレクトリの training_config.py を実行
    python scripts/pipeline.py run --dir models/training_v1

    # 進捗をリセットして最初から実行
    python scripts/pipeline.py run --dir models/training_v1 --reset

    # 詳細ログ
    python scripts/pipeline.py run --dir models/training_v1 -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import importlib.util
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from scripts.lib.logger import setup_logger
from scripts.lib.training_context import (
    PROGRESS_FILENAME,
    TrainingProgress,
    load_progress,
    save_progress,
)
from scripts.lib.phases import Phase, PhaseContext


CONFIG_FILENAME = "training_config.py"


def load_config(config_path: Path) -> Tuple[str, str, List[Phase]]:
    """Pythonファイルから訓練計画をロード

    Args:
        config_path: training_config.py のパス

    Returns:
        (name, description, phases)
    """
    spec = importlib.util.spec_from_file_location("training_config", config_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    name = getattr(module, "NAME", "unnamed")
    description = getattr(module, "DESCRIPTION", "")
    phases = getattr(module, "PHASES", [])

    return name, description, phases


def create_context(
    output_dir: Path, progress: TrainingProgress, logger, save_callback=None
) -> PhaseContext:
    """進捗からPhaseContextを作成"""
    ctx = PhaseContext(
        output_dir=output_dir,
        logger=logger,
        latest_model=Path(progress.latest_model) if progress.latest_model else None,
        best_model=Path(progress.best_model) if progress.best_model else None,
        best_win_rate=progress.best_win_rate,
        all_game_files=[Path(f) for f in progress.all_game_files],
        variables=dict(progress.variables),
        save_callback=save_callback,
        completed_phases=list(progress.completed_phases),
    )

    # フェーズ内進捗を復元
    if progress.current_phase:
        ctx.current_phase_name = progress.current_phase.phase_name
        ctx.current_phase_type = progress.current_phase.phase_type
        ctx.current_phase_completed = progress.current_phase.completed_count
        ctx.current_phase_total = progress.current_phase.total_count

    return ctx


def sync_progress(ctx: PhaseContext, progress: TrainingProgress):
    """PhaseContextから進捗を同期"""
    from scripts.lib.training_context import PhaseProgress

    progress.latest_model = str(ctx.latest_model) if ctx.latest_model else None
    progress.best_model = str(ctx.best_model) if ctx.best_model else None
    progress.best_win_rate = ctx.best_win_rate
    progress.all_game_files = [str(f) for f in ctx.all_game_files]
    progress.variables = dict(ctx.variables)
    progress.completed_phases = list(ctx.completed_phases)

    # フェーズ内進捗を同期
    if ctx.current_phase_name:
        progress.current_phase = PhaseProgress(
            phase_name=ctx.current_phase_name,
            phase_type=ctx.current_phase_type or "",
            completed_count=ctx.current_phase_completed,
            total_count=ctx.current_phase_total,
        )
    else:
        progress.current_phase = None


def run_plan(
    config_path: Path,
    output_dir: Path,
    logger,
    reset: bool = False,
) -> bool:
    """訓練計画を実行

    Args:
        config_path: training_config.py のパス
        output_dir: 出力ディレクトリ
        logger: ロガー
        reset: Trueなら進捗をリセット

    Returns:
        成功したかどうか
    """
    name, description, phases = load_config(config_path)

    logger.info(f"=== {name} ===")
    if description:
        logger.info(f"説明: {description}")

    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / PROGRESS_FILENAME

    # 進捗ロード
    if reset or not progress_path.exists():
        progress = TrainingProgress(started_at=datetime.now().isoformat())
    else:
        progress = load_progress(progress_path)
        logger.info(f"進捗をロード: {len(progress.completed_phases)}フェーズ完了済み")
        if progress.current_phase:
            logger.info(
                f"フェーズ内進捗: {progress.current_phase.phase_name} "
                f"({progress.current_phase.completed_count}/{progress.current_phase.total_count})"
            )

    # 進捗保存コールバック
    def save_callback():
        sync_progress(ctx, progress)
        save_progress(progress, progress_path)

    ctx = create_context(output_dir, progress, logger, save_callback=save_callback)

    for phase in phases:
        phase_name = phase.get_name(ctx)

        if ctx.is_phase_completed(phase_name):
            logger.info(f"スキップ: {phase_name}")
            continue

        logger.info(f"--- フェーズ: {phase_name} ---")
        result = phase.execute(ctx)

        if not result.success:
            logger.error(f"失敗: {phase_name}")
            # 進捗保存してから終了
            sync_progress(ctx, progress)
            save_progress(progress, progress_path)
            return False

        # 進捗更新
        ctx.mark_phase_completed(phase_name)
        sync_progress(ctx, progress)
        save_progress(progress, progress_path)
        logger.info(f"完了: {phase_name}")

    # 完了
    progress.finished_at = datetime.now().isoformat()
    save_progress(progress, progress_path)
    logger.info("=== 訓練計画完了 ===")
    return True


def main():
    parser = argparse.ArgumentParser(description="訓練パイプライン")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = subparsers.add_parser("run", help="訓練計画を実行")
    run_p.add_argument(
        "--dir", "-d", type=str, required=True, help="モデルディレクトリ"
    )
    run_p.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="訓練設定ファイル（デフォルト: DIR/training_config.py）",
    )
    run_p.add_argument(
        "--reset", action="store_true", help="進捗をリセットして最初から実行"
    )
    run_p.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("pipeline", level=log_level)

    if args.command == "run":
        output_dir = Path(args.dir)

        if args.config:
            config_path = Path(args.config)
        else:
            config_path = output_dir / CONFIG_FILENAME

        if not config_path.exists():
            logger.error(f"設定ファイルが見つかりません: {config_path}")
            sys.exit(1)

        if not run_plan(config_path, output_dir, logger, reset=args.reset):
            sys.exit(1)


if __name__ == "__main__":
    main()

"""ログ出力ユーティリティ"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import LOG_LEVEL


def setup_logger(
    name: str = "koushougi",
    level: int = LOG_LEVEL,
    log_file: Optional[Path] = None,
    console: bool = True,
) -> logging.Logger:
    """ロガーをセットアップ

    Args:
        name: ロガー名
        level: ログレベル
        log_file: ログファイルパス（Noneならファイル出力なし）
        console: コンソール出力するか

    Returns:
        設定済みロガー
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_log_path(prefix: str, output_dir: Optional[Path] = None) -> Path:
    """タイムスタンプ付きログファイルパスを生成"""
    if output_dir is None:
        output_dir = Path("logs")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{prefix}_{timestamp}.log"


class GameLogger:
    """ゲーム実行用ロガー（ターンごとの詳細ログ）"""

    def __init__(self, logger: logging.Logger, verbose: bool = False):
        self.logger = logger
        self.verbose = verbose
        self.game_id = 0
        self.turn = 0

    def new_game(self, game_id: int):
        """新しいゲーム開始"""
        self.game_id = game_id
        self.turn = 0
        if self.verbose:
            self.logger.debug(f"=== Game {game_id} start ===")

    def log_turn(self, player: int, phase: str, action: str, elapsed_ms: float = 0):
        """ターンログ"""
        self.turn += 1
        if self.verbose:
            player_name = "先手" if player == 0 else "後手"
            self.logger.debug(
                f"G{self.game_id} T{self.turn}: {player_name} {phase} {action} ({elapsed_ms:.1f}ms)"
            )

    def log_turn_timeout(self, player: int, phase: str, elapsed_ms: float):
        """タイムアウト警告"""
        player_name = "先手" if player == 0 else "後手"
        self.logger.warning(
            f"G{self.game_id} T{self.turn}: {player_name} {phase} SLOW ({elapsed_ms:.1f}ms)"
        )

    def log_game_end(self, winner: Optional[int], total_turns: int, elapsed_ms: float):
        """ゲーム終了ログ"""
        if winner is None:
            result = "引分"
        else:
            result = "先手勝" if winner == 0 else "後手勝"
        self.logger.info(
            f"Game {self.game_id}: {result} ({total_turns}手, {elapsed_ms:.1f}ms)"
        )

    def log_error(self, message: str):
        """エラーログ"""
        self.logger.error(f"G{self.game_id} T{self.turn}: {message}")

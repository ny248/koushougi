"""ゲーム実行・棋譜記録"""

import time
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json

from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state
from backend.domain.kifu import Kifu
from ai.base import BaseAI
from .logger import GameLogger


# 1ターンのタイムアウト警告閾値（ミリ秒）
TURN_TIMEOUT_WARN_MS = 5000


@dataclass
class GameRecord:
    """対局記録"""
    game_id: int = 0
    winner: Optional[int] = None
    total_turns: int = 0
    elapsed_ms: float = 0
    kifu: Kifu = field(default_factory=Kifu)
    sente_name: str = ""
    gote_name: str = ""

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "winner": self.winner,
            "total_turns": self.total_turns,
            "elapsed_ms": self.elapsed_ms,
            "sente": self.sente_name,
            "gote": self.gote_name,
            "kifu": self.kifu.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameRecord":
        return cls(
            game_id=data.get("game_id", 0),
            winner=data.get("winner"),
            total_turns=data.get("total_turns", 0),
            elapsed_ms=data.get("elapsed_ms", 0),
            sente_name=data.get("sente", ""),
            gote_name=data.get("gote", ""),
            kifu=Kifu.from_dict(data.get("kifu", {})),
        )


def run_game(
    sente_ai: BaseAI,
    gote_ai: BaseAI,
    game_id: int = 0,
    max_turns: int = 300,
    logger: Optional[GameLogger] = None,
) -> GameRecord:
    """1ゲームを実行

    Args:
        sente_ai: 先手AI
        gote_ai: 後手AI
        game_id: ゲームID（ログ用）
        max_turns: 最大ターン数
        logger: ゲームロガー

    Returns:
        GameRecord: 対局記録（棋譜含む）
    """
    engine = GameEngine(create_initial_state())
    record = GameRecord(
        game_id=game_id,
        sente_name=type(sente_ai).__name__,
        gote_name=type(gote_ai).__name__,
    )

    if logger:
        logger.new_game(game_id)

    start_time = time.perf_counter()
    turn = 0

    while turn < max_turns and not engine.is_game_over:
        player = engine.current_player
        ai = sente_ai if player == 0 else gote_ai

        turn_start = time.perf_counter()

        # 1ターン実行
        success = _play_turn_with_logging(engine, ai, player, logger)

        turn_elapsed_ms = (time.perf_counter() - turn_start) * 1000

        if turn_elapsed_ms > TURN_TIMEOUT_WARN_MS and logger:
            logger.log_turn_timeout(player, engine.phase.name, turn_elapsed_ms)

        if not success:
            if logger:
                logger.log_error(f"Turn failed at phase {engine.phase.name}")
            break

        turn += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    record.winner = engine.winner
    record.total_turns = turn
    record.elapsed_ms = elapsed_ms
    record.kifu = engine.state.kifu

    if logger:
        logger.log_game_end(record.winner, record.total_turns, record.elapsed_ms)

    return record


def _play_turn_with_logging(
    engine: GameEngine,
    ai: BaseAI,
    player: int,
    logger: Optional[GameLogger],
) -> bool:
    """1ターンを実行（ログ付き）"""

    # フェーズ1: 駒選択
    if engine.phase != GamePhase.PIECE_SELECT:
        return False

    piece_pos = ai.choose_piece(engine)
    if not engine.select_piece(piece_pos):
        if logger:
            logger.log_error(f"select_piece failed: {piece_pos}")
        return False

    if logger:
        logger.log_turn(player, "PIECE", f"{piece_pos}")

    # フェーズ2: 移動先選択
    dest_pos = ai.choose_destination(engine)
    result = engine.select_destination(dest_pos)
    if not result.success:
        if logger:
            logger.log_error(f"select_destination failed: {dest_pos}")
        return False

    if logger:
        logger.log_turn(player, "DEST", f"{dest_pos}")

    # フェーズ3: 成り判断
    if engine.phase == GamePhase.PROMOTION:
        promote = ai.choose_promotion(engine)
        result = engine.decide_promotion(promote)
        if not result.success:
            if logger:
                logger.log_error(f"decide_promotion failed")
            return False

        if logger:
            logger.log_turn(player, "PROMO", f"{'成' if promote else '不成'}")

    # フェーズ4: 射撃（複数回可能）
    shoot_count = 0
    while engine.phase == GamePhase.SHOOTING:
        target = ai.choose_shoot_target(engine)
        if target:
            result = engine.shoot(target)
            if not result.success:
                if logger:
                    logger.log_error(f"shoot failed: {target}")
                return False
            shoot_count += 1
            if logger:
                logger.log_turn(player, "SHOOT", f"{target}")
            if not result.can_shoot:
                break
        else:
            engine.skip_shoot()
            if logger:
                logger.log_turn(player, "SHOOT", "skip")
            break

    return True


def run_games(
    sente_ai: BaseAI,
    gote_ai: BaseAI,
    n_games: int,
    max_turns: int = 300,
    logger: Optional[GameLogger] = None,
    progress_callback=None,
) -> list[GameRecord]:
    """複数ゲームを実行

    Args:
        sente_ai: 先手AI
        gote_ai: 後手AI
        n_games: 対局数
        max_turns: 最大ターン数
        logger: ゲームロガー
        progress_callback: 進捗コールバック fn(game_idx, record, stats)

    Returns:
        list[GameRecord]: 対局記録リスト
    """
    records = []
    stats = {"wins": 0, "losses": 0, "draws": 0}

    for i in range(n_games):
        record = run_game(sente_ai, gote_ai, game_id=i + 1, max_turns=max_turns, logger=logger)
        records.append(record)

        if record.winner == 0:
            stats["wins"] += 1
        elif record.winner == 1:
            stats["losses"] += 1
        else:
            stats["draws"] += 1

        if progress_callback:
            progress_callback(i, record, stats)

    return records


def save_records(records: list[GameRecord], output_path: Path) -> None:
    """対局記録を保存"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "games": [r.to_dict() for r in records],
        "summary": {
            "total": len(records),
            "sente_wins": sum(1 for r in records if r.winner == 0),
            "gote_wins": sum(1 for r in records if r.winner == 1),
            "draws": sum(1 for r in records if r.winner is None),
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_records(input_path: Path) -> list[GameRecord]:
    """対局記録を読み込み"""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [GameRecord.from_dict(g) for g in data.get("games", [])]

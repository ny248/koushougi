"""AI同士の対戦 + 棋譜出力

Usage:
    python scripts/battle.py --player1 minimax --player2 random -n 10 -o data/battles/test.json
    python scripts/battle.py --player1 minimax:depth=2 --player2 greedy -n 100 -o games.jsonl --format jsonl
    python scripts/battle.py -p1 random -p2 random -n 5 --game-timeout 60
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import time
import threading
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from scripts.lib.logger import setup_logger, GameLogger
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state
from backend.domain.kifu import Kifu
from ai.base import BaseAI
from ai.random.player import RandomPlayer
from ai.greedy.player import GreedyPlayer
from ai.minimax.player import MinimaxPlayer
from config import AI_GAME_TIMEOUT_SEC


# === ゲーム実行 ===

TURN_TIMEOUT_SEC = 30.0
TURN_TIMEOUT_WARN_MS = 5000


class TurnTimeoutError(Exception):
    pass


class GameTimeoutError(Exception):
    pass


@dataclass
class GameRecord:
    game_id: int = 0
    winner: Optional[int] = None
    total_turns: int = 0
    elapsed_ms: float = 0
    kifu: Kifu = field(default_factory=Kifu)
    sente_name: str = ""
    gote_name: str = ""
    error: Optional[str] = None
    timed_out: bool = False

    def to_dict(self) -> dict:
        d = {
            "game_id": self.game_id,
            "winner": self.winner,
            "total_turns": self.total_turns,
            "elapsed_ms": self.elapsed_ms,
            "sente": self.sente_name,
            "gote": self.gote_name,
            "kifu": self.kifu.to_dict(),
        }
        if self.error:
            d["error"] = self.error
        if self.timed_out:
            d["timed_out"] = True
        return d


def run_game(
    sente_ai: BaseAI,
    gote_ai: BaseAI,
    game_id: int = 0,
    logger: Optional[GameLogger] = None,
    turn_timeout: float = TURN_TIMEOUT_SEC,
    game_timeout: float = AI_GAME_TIMEOUT_SEC,
) -> GameRecord:
    """1ゲームを実行"""
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

    try:
        while not engine.is_game_over:
            elapsed_total = time.perf_counter() - start_time
            if elapsed_total > game_timeout:
                raise GameTimeoutError(f"Game timeout after {elapsed_total:.1f}s")

            player = engine.current_player
            ai = sente_ai if player == 0 else gote_ai

            turn_start = time.perf_counter()
            success = _play_turn_with_timeout(engine, ai, player, logger, turn_timeout)
            turn_elapsed_ms = (time.perf_counter() - turn_start) * 1000

            if turn_elapsed_ms > TURN_TIMEOUT_WARN_MS and logger:
                logger.log_turn_timeout(player, engine.phase.name, turn_elapsed_ms)

            if not success:
                if logger:
                    logger.log_error(f"Turn failed at phase {engine.phase.name}")
                break

            turn += 1

    except TurnTimeoutError as e:
        record.error = str(e)
        record.timed_out = True
        if logger:
            logger.log_error(f"Turn timeout: {e}")

    except GameTimeoutError as e:
        record.error = str(e)
        record.timed_out = True
        if logger:
            logger.log_error(f"Game timeout: {e}")

    except Exception as e:
        record.error = f"Unexpected error: {e}"
        if logger:
            logger.log_error(f"Unexpected error: {e}")

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    record.winner = engine.winner
    record.total_turns = turn
    record.elapsed_ms = elapsed_ms
    record.kifu = engine.state.kifu

    if logger:
        logger.log_game_end(record.winner, record.total_turns, record.elapsed_ms)

    return record


def _play_turn_with_timeout(engine, ai, player, logger, timeout):
    result = [False]
    exception = [None]

    def run_turn():
        try:
            result[0] = _play_turn(engine, ai, player, logger)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=run_turn)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise TurnTimeoutError(f"Turn timeout after {timeout}s (player {player})")

    if exception[0]:
        raise exception[0]

    return result[0]


def _play_turn(engine, ai, player, logger):
    """1ターン分を処理（相手の手番になるまでplay_stepを繰り返す）"""
    while not engine.is_game_over and engine.current_player == player:
        if not ai.play_step(engine):
            if logger:
                logger.log_error(f"play_step failed at phase {engine.phase}")
            return False
    return True


def run_games(sente_ai, gote_ai, n_games, logger=None,
              progress_callback=None, turn_timeout=TURN_TIMEOUT_SEC,
              game_timeout=AI_GAME_TIMEOUT_SEC):
    """複数ゲームを実行"""
    records = []
    stats = {"wins": 0, "losses": 0, "draws": 0, "timeouts": 0}

    for i in range(n_games):
        record = run_game(sente_ai, gote_ai, game_id=i + 1,
                          logger=logger, turn_timeout=turn_timeout,
                          game_timeout=game_timeout)
        records.append(record)

        if record.timed_out:
            stats["timeouts"] += 1
        elif record.winner == 0:
            stats["wins"] += 1
        elif record.winner == 1:
            stats["losses"] += 1
        else:
            stats["draws"] += 1

        if progress_callback:
            progress_callback(i, record, stats)

    return records


def save_records(records, output_path, format="json"):
    """対局記録を保存"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "jsonl":
        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                data = {
                    "game_id": record.game_id,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "players": {"sente": record.sente_name, "gote": record.gote_name},
                    "kifu": record.kifu.to_dict(),
                }
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
    else:
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


# === CLI ===

def parse_player(spec: str) -> BaseAI:
    parts = spec.split(":")
    name = parts[0].lower()

    options = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
            options[key] = value

    if name == "random":
        return RandomPlayer()
    elif name == "greedy":
        return GreedyPlayer()
    elif name == "minimax":
        depth = options.get("depth", 3)
        max_moves = options.get("max_moves", 15)
        epsilon = options.get("epsilon", 0.0)
        return MinimaxPlayer(depth=depth, max_moves=max_moves, epsilon=epsilon)
    else:
        raise ValueError(f"Unknown player type: {name}")


def main():
    parser = argparse.ArgumentParser(description="AI同士の対戦と棋譜出力")
    parser.add_argument("--player1", "-p1", type=str, default="random",
                        help="先手AI (random/greedy/minimax[:depth=N:epsilon=E])")
    parser.add_argument("--player2", "-p2", type=str, default="random",
                        help="後手AI")
    parser.add_argument("-n", "--games", type=int, default=10, help="対局数")
    parser.add_argument("-o", "--output", type=str, help="棋譜出力ファイル")
    parser.add_argument("--format", type=str, default="json",
                        choices=["json", "jsonl"], help="出力形式")
    parser.add_argument("--turn-timeout", type=float, default=30.0,
                        help="1手あたりのタイムアウト（秒）")
    parser.add_argument("--game-timeout", type=float, default=AI_GAME_TIMEOUT_SEC,
                        help="ゲーム全体のタイムアウト（秒）")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("battle", level=log_level)
    game_logger = GameLogger(logger, verbose=args.verbose)

    try:
        sente_ai = parse_player(args.player1)
        gote_ai = parse_player(args.player2)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"先手: {args.player1}")
    logger.info(f"後手: {args.player2}")
    logger.info(f"対局数: {args.games}")

    def on_progress(game_idx, record, stats):
        if (game_idx + 1) % 10 == 0 or game_idx == args.games - 1:
            win_rate = stats["wins"] / (game_idx + 1) * 100
            logger.info(
                f"Game {game_idx + 1}/{args.games}: "
                f"先手{stats['wins']} - 後手{stats['losses']} - 引分{stats['draws']} "
                f"(先手勝率: {win_rate:.1f}%)"
            )

    records = run_games(
        sente_ai, gote_ai,
        n_games=args.games,
        logger=game_logger,
        progress_callback=on_progress,
        turn_timeout=args.turn_timeout,
        game_timeout=args.game_timeout,
    )

    sente_wins = sum(1 for r in records if r.winner == 0 and not r.timed_out)
    gote_wins = sum(1 for r in records if r.winner == 1 and not r.timed_out)
    draws = sum(1 for r in records if r.winner is None and not r.timed_out)
    timeouts = sum(1 for r in records if r.timed_out)
    total_ms = sum(r.elapsed_ms for r in records)

    logger.info("=== 結果 ===")
    logger.info(f"先手勝利: {sente_wins} ({100*sente_wins/args.games:.1f}%)")
    logger.info(f"後手勝利: {gote_wins} ({100*gote_wins/args.games:.1f}%)")
    logger.info(f"引き分け: {draws} ({100*draws/args.games:.1f}%)")
    if timeouts > 0:
        logger.info(f"タイムアウト: {timeouts}")
    logger.info(f"総時間: {total_ms:.1f}ms")

    if args.output:
        output_path = Path(args.output)
        save_records(records, output_path, format=args.format)
        logger.info(f"棋譜保存: {output_path} ({args.format})")


if __name__ == "__main__":
    main()

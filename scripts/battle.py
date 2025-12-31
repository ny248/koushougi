"""AI同士の対戦 + 棋譜出力

Usage:
    python scripts/battle.py --player1 minimax --player2 random -n 10 -o data/battles/test.json
    python scripts/battle.py --player1 minimax:depth=2 --player2 greedy -n 100 --verbose
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
from pathlib import Path

from scripts.lib.logger import setup_logger, get_log_path, GameLogger
from scripts.lib.game_runner import run_games, save_records
from ai.random.player import RandomPlayer
from ai.greedy.player import GreedyPlayer
from ai.minimax.player import MinimaxPlayer
from ai.base import BaseAI
from config import AI_MAX_TURNS


def parse_player(spec: str) -> BaseAI:
    """プレイヤー指定をパース

    Examples:
        "random" -> RandomPlayer()
        "minimax" -> MinimaxPlayer(depth=3)
        "minimax:depth=2" -> MinimaxPlayer(depth=2)
        "greedy" -> GreedyPlayer()
    """
    parts = spec.split(":")
    name = parts[0].lower()

    # オプション解析
    options = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            # 数値変換を試みる
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
        return MinimaxPlayer(depth=depth, max_moves=max_moves)
    else:
        raise ValueError(f"Unknown player type: {name}")


def main():
    parser = argparse.ArgumentParser(
        description="AI同士の対戦と棋譜出力",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/battle.py --player1 minimax --player2 random -n 10
  python scripts/battle.py --player1 minimax:depth=2 --player2 greedy -n 100 -o results.json
  python scripts/battle.py --player1 random --player2 random -n 1000 --verbose
        """
    )
    parser.add_argument("--player1", "-p1", type=str, default="random",
                        help="先手AI (random/greedy/minimax[:depth=N])")
    parser.add_argument("--player2", "-p2", type=str, default="random",
                        help="後手AI (random/greedy/minimax[:depth=N])")
    parser.add_argument("-n", "--games", type=int, default=10,
                        help="対局数")
    parser.add_argument("-o", "--output", type=str,
                        help="棋譜出力ファイル（JSON）")
    parser.add_argument("--max-turns", type=int, default=AI_MAX_TURNS,
                        help="1局の最大ターン数")
    parser.add_argument("--turn-timeout", type=float, default=30.0,
                        help="1ターンのタイムアウト（秒）")
    parser.add_argument("--game-timeout", type=float, default=300.0,
                        help="1ゲームのタイムアウト（秒）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細ログ出力")
    parser.add_argument("--log-file", type=str,
                        help="ログファイル出力先")
    args = parser.parse_args()

    # ロガー設定
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file = Path(args.log_file) if args.log_file else None
    logger = setup_logger("battle", level=log_level, log_file=log_file)
    game_logger = GameLogger(logger, verbose=args.verbose)

    # プレイヤー作成
    try:
        sente_ai = parse_player(args.player1)
        gote_ai = parse_player(args.player2)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"先手: {args.player1} ({type(sente_ai).__name__})")
    logger.info(f"後手: {args.player2} ({type(gote_ai).__name__})")
    logger.info(f"対局数: {args.games}, 最大ターン: {args.max_turns}")

    # 進捗表示コールバック
    def on_progress(game_idx, record, stats):
        if (game_idx + 1) % 10 == 0 or game_idx == args.games - 1:
            win_rate = stats["wins"] / (game_idx + 1) * 100
            logger.info(
                f"Game {game_idx + 1}/{args.games}: "
                f"先手{stats['wins']} - 後手{stats['losses']} - 引分{stats['draws']} "
                f"(先手勝率: {win_rate:.1f}%)"
            )

    # 対戦実行
    records = run_games(
        sente_ai, gote_ai,
        n_games=args.games,
        max_turns=args.max_turns,
        logger=game_logger,
        progress_callback=on_progress,
        turn_timeout=args.turn_timeout,
        game_timeout=args.game_timeout,
    )

    # 結果サマリー
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
        logger.info(f"タイムアウト: {timeouts} ({100*timeouts/args.games:.1f}%)")
    logger.info(f"総時間: {total_ms:.1f}ms ({total_ms/args.games:.2f}ms/局)")

    # 棋譜保存
    if args.output:
        output_path = Path(args.output)
        save_records(records, output_path)
        logger.info(f"棋譜保存: {output_path}")


if __name__ == "__main__":
    main()

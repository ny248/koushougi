#!/usr/bin/env python3
"""棋譜収集スクリプト - AI同士で対戦して棋譜を出力（並列実行対応）"""

import argparse
import json
import os
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path

from ai.battle import run_battle, GameRecord
from ai.random import RandomPlayer
from ai.greedy import GreedyPlayer
from config import AI_MAX_TURNS


AI_CLASSES = {
    "random": RandomPlayer,
    "greedy": GreedyPlayer,
}


def run_single_game(args: tuple) -> dict:
    """1対局を実行（並列処理用）"""
    sente_type, gote_type, max_turns, game_id = args

    # 各プロセスでAIインスタンスを生成
    sente_ai = AI_CLASSES[sente_type]()
    gote_ai = AI_CLASSES[gote_type]()

    record = run_battle(sente_ai, gote_ai, max_turns)
    return record.to_dict()


def main():
    parser = argparse.ArgumentParser(description="棋譜収集（並列実行対応）")
    parser.add_argument("-n", "--games", type=int, default=100, help="対局数")
    parser.add_argument("-o", "--output", type=str, required=True, help="出力ファイル（JSON）")
    parser.add_argument("--sente", type=str, default="greedy", choices=AI_CLASSES.keys(), help="先手AI")
    parser.add_argument("--gote", type=str, default="greedy", choices=AI_CLASSES.keys(), help="後手AI")
    parser.add_argument("--max-turns", type=int, default=AI_MAX_TURNS, help="最大ターン数")
    parser.add_argument("-j", "--jobs", type=int, default=0, help="並列数（0=CPU数）")
    parser.add_argument("-q", "--quiet", action="store_true", help="進捗非表示")
    args = parser.parse_args()

    n_jobs = args.jobs if args.jobs > 0 else cpu_count()

    print(f"対戦: {args.sente} vs {args.gote}")
    print(f"対局数: {args.games}")
    print(f"並列数: {n_jobs}")
    print(f"最大ターン: {args.max_turns}")

    # 並列実行用の引数リスト
    game_args = [
        (args.sente, args.gote, args.max_turns, i)
        for i in range(args.games)
    ]

    start_time = time.perf_counter()

    # 並列実行
    with Pool(n_jobs) as pool:
        if args.quiet:
            results = pool.map(run_single_game, game_args)
        else:
            # 進捗表示付き
            results = []
            for i, result in enumerate(pool.imap_unordered(run_single_game, game_args)):
                results.append(result)
                if (i + 1) % 10 == 0 or i + 1 == args.games:
                    elapsed = time.perf_counter() - start_time
                    wins = sum(1 for r in results if r["winner"] == 0)
                    losses = sum(1 for r in results if r["winner"] == 1)
                    draws = sum(1 for r in results if r["winner"] is None)
                    print(f"Game {i + 1}/{args.games}: 先手{wins} - 後手{losses} - 引分{draws} ({elapsed:.1f}s)")

    elapsed = time.perf_counter() - start_time

    # 集計
    sente_wins = sum(1 for r in results if r["winner"] == 0)
    gote_wins = sum(1 for r in results if r["winner"] == 1)
    draws = sum(1 for r in results if r["winner"] is None)

    print(f"\n=== 結果 ===")
    print(f"対局数: {args.games}")
    print(f"先手勝利: {sente_wins} ({100*sente_wins/args.games:.1f}%)")
    print(f"後手勝利: {gote_wins} ({100*gote_wins/args.games:.1f}%)")
    print(f"引き分け: {draws} ({100*draws/args.games:.1f}%)")
    print(f"総時間: {elapsed:.1f}s ({elapsed/args.games:.2f}s/局, 実効{elapsed/args.games*n_jobs:.2f}s/局)")

    # 出力
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "meta": {
            "sente_ai": args.sente,
            "gote_ai": args.gote,
            "max_turns": args.max_turns,
            "n_jobs": n_jobs,
        },
        "games": results,
        "summary": {
            "total_games": len(results),
            "sente_wins": sente_wins,
            "gote_wins": gote_wins,
            "draws": draws,
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n棋譜を保存: {output_path}")


if __name__ == "__main__":
    main()

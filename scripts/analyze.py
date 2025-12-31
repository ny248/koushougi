"""棋譜分析・評価値更新

Usage:
    # 棋譜を分析して統計表示
    python scripts/analyze.py stats data/battles/*.json

    # 駒の評価値を棋譜から推定
    python scripts/analyze.py piece-values data/battles/*.json --output ai/greedy/piece_values_learned.py

    # 棋譜のサマリー表示
    python scripts/analyze.py summary data/battles/test.json
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import logging
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

from scripts.lib.logger import setup_logger
from scripts.lib.game_runner import load_records
from backend.domain.piece_registry import get_piece


@dataclass
class CaptureStats:
    """駒が取られた時の統計"""
    piece_id: int
    piece_name: str = ""
    times_captured: int = 0
    captured_by_winner: int = 0
    captured_by_loser: int = 0

    @property
    def loss_rate(self) -> float:
        """取られた時の敗北率"""
        if self.times_captured == 0:
            return 0.5
        return self.captured_by_winner / self.times_captured


@dataclass
class AnalysisResult:
    """分析結果"""
    total_games: int = 0
    decisive_games: int = 0
    sente_wins: int = 0
    gote_wins: int = 0
    draws: int = 0
    total_turns: int = 0
    capture_stats: dict[int, CaptureStats] = field(default_factory=dict)

    def get_stats(self, piece_id: int) -> CaptureStats:
        if piece_id not in self.capture_stats:
            try:
                name = get_piece(piece_id).name
            except:
                name = f"ID:{piece_id}"
            self.capture_stats[piece_id] = CaptureStats(piece_id=piece_id, piece_name=name)
        return self.capture_stats[piece_id]


def analyze_records(records, logger) -> AnalysisResult:
    """対局記録を分析"""
    result = AnalysisResult()

    for record in records:
        result.total_games += 1
        result.total_turns += record.total_turns

        if record.winner is None:
            result.draws += 1
        elif record.winner == 0:
            result.sente_wins += 1
            result.decisive_games += 1
        else:
            result.gote_wins += 1
            result.decisive_games += 1

        # 棋譜から駒取りを集計
        winner = record.winner
        if winner is None:
            continue

        for move in record.kifu.moves:
            # 通常の駒取り
            if move.captured_piece:
                stats = result.get_stats(move.captured_piece)
                stats.times_captured += 1
                if move.player == winner:
                    stats.captured_by_winner += 1
                else:
                    stats.captured_by_loser += 1

            # 経路上の駒取り
            for pos, piece_id, _ in move.path_kills:
                stats = result.get_stats(piece_id)
                stats.times_captured += 1
                if move.player == winner:
                    stats.captured_by_winner += 1
                else:
                    stats.captured_by_loser += 1

    return result


def cmd_stats(args, logger):
    """統計分析"""
    all_records = []
    for path in args.files:
        p = Path(path)
        if p.is_file():
            all_records.extend(load_records(p))
        elif p.is_dir():
            for f in p.glob("*.json"):
                all_records.extend(load_records(f))

    if not all_records:
        logger.error("対局データがありません")
        return

    logger.info(f"対局数: {len(all_records)}")

    result = analyze_records(all_records, logger)

    # サマリー表示
    print("\n=== 対局統計 ===")
    print(f"総対局数: {result.total_games}")
    print(f"先手勝利: {result.sente_wins} ({100*result.sente_wins/result.total_games:.1f}%)")
    print(f"後手勝利: {result.gote_wins} ({100*result.gote_wins/result.total_games:.1f}%)")
    print(f"引き分け: {result.draws} ({100*result.draws/result.total_games:.1f}%)")
    print(f"平均手数: {result.total_turns / result.total_games:.1f}")

    if result.capture_stats:
        print("\n=== 駒取り統計 ===")
        print(f"{'駒名':8s} | {'取られ':>6s} | {'敗北率':>6s}")
        print("-" * 30)

        sorted_stats = sorted(
            result.capture_stats.values(),
            key=lambda s: s.loss_rate,
            reverse=True
        )
        for stats in sorted_stats:
            if stats.times_captured >= 5:
                print(f"{stats.piece_name:8s} | {stats.times_captured:6d} | {stats.loss_rate:6.1%}")


def cmd_piece_values(args, logger):
    """駒の評価値を棋譜から推定"""
    all_records = []
    for path in args.files:
        p = Path(path)
        if p.is_file():
            all_records.extend(load_records(p))

    if not all_records:
        logger.error("対局データがありません")
        return

    result = analyze_records(all_records, logger)

    # 敗北率から評価値を推定
    # loss_rate が高い = 重要な駒 = 高評価
    values = {}
    base_value = 100

    for piece_id in range(1, 70):  # 駒IDの範囲
        if piece_id in result.capture_stats:
            stats = result.capture_stats[piece_id]
            if stats.times_captured >= 10:
                # 敗北率50%を基準に、高ければ価値が高い
                importance = stats.loss_rate
                values[piece_id] = int(base_value * (0.5 + importance))
            else:
                values[piece_id] = base_value
        else:
            values[piece_id] = base_value

    # 出力
    print("\n=== 推定評価値 ===")
    for piece_id, value in sorted(values.items()):
        try:
            name = get_piece(piece_id).name
        except:
            name = f"ID:{piece_id}"
        print(f"{name}: {value}")

    if args.output:
        # Pythonファイルとして出力
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write('"""棋譜から推定した駒の評価値"""\n\n')
            f.write("LEARNED_PIECE_VALUES = {\n")
            for piece_id, value in sorted(values.items()):
                try:
                    name = get_piece(piece_id).name
                except:
                    name = f"ID:{piece_id}"
                f.write(f"    {piece_id}: {value},  # {name}\n")
            f.write("}\n")

        logger.info(f"評価値を保存: {output_path}")


def cmd_summary(args, logger):
    """棋譜サマリー表示"""
    for path in args.files:
        records = load_records(Path(path))

        print(f"\n=== {path} ===")
        print(f"対局数: {len(records)}")

        for i, record in enumerate(records[:5]):  # 最初の5局
            winner_str = "先手勝" if record.winner == 0 else "後手勝" if record.winner == 1 else "引分"
            print(f"  {i+1}. {winner_str} ({record.total_turns}手, {record.elapsed_ms:.0f}ms)")

        if len(records) > 5:
            print(f"  ... (残り {len(records) - 5} 局)")


def main():
    parser = argparse.ArgumentParser(description="棋譜分析")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # stats
    stats_p = subparsers.add_parser("stats", help="統計分析")
    stats_p.add_argument("files", nargs="+", help="棋譜ファイル or ディレクトリ")
    stats_p.add_argument("-v", "--verbose", action="store_true")

    # piece-values
    pv_p = subparsers.add_parser("piece-values", help="駒評価値推定")
    pv_p.add_argument("files", nargs="+", help="棋譜ファイル")
    pv_p.add_argument("-o", "--output", help="出力ファイル (.py)")
    pv_p.add_argument("-v", "--verbose", action="store_true")

    # summary
    sum_p = subparsers.add_parser("summary", help="棋譜サマリー")
    sum_p.add_argument("files", nargs="+", help="棋譜ファイル")
    sum_p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("analyze", level=log_level)

    if args.cmd == "stats":
        cmd_stats(args, logger)
    elif args.cmd == "piece-values":
        cmd_piece_values(args, logger)
    elif args.cmd == "summary":
        cmd_summary(args, logger)


if __name__ == "__main__":
    main()

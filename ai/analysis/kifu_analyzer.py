"""棋譜分析 - 対局データから統計を抽出"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict


@dataclass
class CaptureStats:
    """駒が取られた時の統計"""
    piece_id: int
    times_captured: int = 0          # 取られた総回数
    times_captured_by_winner: int = 0  # 勝者に取られた回数
    times_captured_by_loser: int = 0   # 敗者に取られた回数

    @property
    def loss_rate_when_captured(self) -> float:
        """この駒が取られた時の敗北率（取られた側から見て）"""
        if self.times_captured == 0:
            return 0.5  # データなし
        # 勝者に取られた = 取られた側は負けた
        return self.times_captured_by_winner / self.times_captured


@dataclass
class AnalysisResult:
    """分析結果"""
    total_games: int = 0
    decisive_games: int = 0  # 勝敗がついた対局数
    capture_stats: dict[int, CaptureStats] = field(default_factory=dict)

    def get_stats(self, piece_id: int) -> CaptureStats:
        if piece_id not in self.capture_stats:
            self.capture_stats[piece_id] = CaptureStats(piece_id=piece_id)
        return self.capture_stats[piece_id]


class KifuAnalyzer:
    """棋譜分析器"""

    def __init__(self):
        self.result = AnalysisResult()

    def analyze_file(self, filepath: str | Path) -> None:
        """JSONファイルを分析"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        games = data.get("games", [])
        for game in games:
            self._analyze_game(game)

    def analyze_files(self, filepaths: list[str | Path]) -> None:
        """複数ファイルを分析"""
        for fp in filepaths:
            self.analyze_file(fp)

    def _analyze_game(self, game: dict) -> None:
        """1対局を分析"""
        self.result.total_games += 1

        winner = game.get("winner")
        if winner is None:
            return  # 引き分けはスキップ

        self.result.decisive_games += 1
        loser = 1 - winner

        moves = game.get("moves", [])
        for move in moves:
            captured = move.get("captured")
            if captured is None:
                continue

            player = move.get("player")  # 取った側
            stats = self.result.get_stats(captured)
            stats.times_captured += 1

            if player == winner:
                stats.times_captured_by_winner += 1
            else:
                stats.times_captured_by_loser += 1

            # 射撃による駒取りも集計
            shoot_kills = move.get("shoot_kills")
            if shoot_kills:
                for killed_piece in shoot_kills:
                    kill_stats = self.result.get_stats(killed_piece)
                    kill_stats.times_captured += 1
                    if player == winner:
                        kill_stats.times_captured_by_winner += 1
                    else:
                        kill_stats.times_captured_by_loser += 1

    def get_result(self) -> AnalysisResult:
        return self.result

    def print_summary(self) -> None:
        """分析結果のサマリーを表示"""
        r = self.result
        print(f"=== 棋譜分析結果 ===")
        print(f"総対局数: {r.total_games}")
        print(f"決着対局: {r.decisive_games}")
        print(f"引き分け: {r.total_games - r.decisive_games}")
        print()

        if not r.capture_stats:
            print("駒取りデータなし")
            return

        print("駒ID | 取られ回数 | 敗北率")
        print("-" * 35)

        # 敗北率でソート
        sorted_stats = sorted(
            r.capture_stats.values(),
            key=lambda s: s.loss_rate_when_captured,
            reverse=True
        )

        for stats in sorted_stats:
            if stats.times_captured > 0:
                print(f"{stats.piece_id:5d} | {stats.times_captured:10d} | {stats.loss_rate_when_captured:.2%}")

"""価値学習 - 分析結果から駒の価値を計算"""

from ai.analysis.kifu_analyzer import AnalysisResult
from ai.greedy.piece_values import PIECE_VALUES


# 駒名（出力用）
PIECE_NAMES = {
    1: "将", 2: "記室", 3: "参謀", 4: "親兵", 5: "力士",
    6: "舎人", 7: "舎餘", 8: "軍吏", 9: "軍匠", 10: "高道",
    11: "神僧", 12: "前衝", 13: "後衝", 14: "中軍", 15: "鼓",
    16: "旗", 17: "把総", 18: "百総", 19: "護兵", 20: "千総",
    21: "騎総", 22: "仏狼機", 23: "象", 24: "弓", 25: "弩",
    26: "砲", 27: "馬兵", 28: "歩兵", 29: "歩総", 30: "牌",
    31: "牌総", 32: "車", 33: "車総", 34: "先鋒", 35: "帥",
    36: "軍師", 37: "旗鼓", 38: "千戸", 39: "百戸", 40: "副司",
    41: "毒火", 42: "天網", 43: "地網", 44: "五里霧", 45: "聖燈",
    46: "霹靂", 47: "招揺", 48: "龍驤", 49: "虎翼", 50: "鷹揚",
    51: "彍騎", 52: "弩騎", 53: "砲車", 54: "神機車", 55: "天馬",
    56: "都司", 57: "天塁",
}


class ValueLearner:
    """駒価値の学習器"""

    def __init__(self, base_values: dict[int, int] | None = None):
        """
        Args:
            base_values: ベースとなる価値（デフォルトはPIECE_VALUES）
        """
        self.base_values = base_values or PIECE_VALUES.copy()

    def learn(self, result: AnalysisResult, min_samples: int = 5,
              scale_factor: float = 100.0, max_adjustment: float = 50.0) -> dict[int, int]:
        """
        分析結果から新しい価値を計算

        加法方式: 敗北率の偏差に基づいて価値を調整
        adjustment = (loss_rate - avg_loss_rate) * scale_factor
        new_value = base_value + adjustment

        Args:
            result: KifuAnalyzerの分析結果
            min_samples: この回数以上取られた駒のみ調整
            scale_factor: 敗北率偏差を価値に変換する係数
            max_adjustment: 1回の学習での最大調整幅

        Returns:
            新しい駒価値の辞書
        """
        # 平均敗北率を計算（サンプル数で重み付け）
        total_captures = 0
        weighted_loss_sum = 0.0

        for piece_id, stats in result.capture_stats.items():
            if stats.times_captured >= min_samples:
                total_captures += stats.times_captured
                weighted_loss_sum += stats.times_captured * stats.loss_rate_when_captured

        if total_captures == 0:
            return self.base_values.copy()

        avg_loss_rate = weighted_loss_sum / total_captures

        # 新しい価値を計算
        new_values = self.base_values.copy()

        for piece_id, stats in result.capture_stats.items():
            if stats.times_captured < min_samples:
                continue  # サンプル不足はスキップ

            if piece_id not in self.base_values:
                continue  # 不明な駒はスキップ

            loss_rate = stats.loss_rate_when_captured
            deviation = loss_rate - avg_loss_rate  # -0.5 〜 +0.5
            adjustment = deviation * scale_factor

            # 極端な値を防ぐ
            adjustment = max(-max_adjustment, min(max_adjustment, adjustment))

            new_value = self.base_values[piece_id] + int(adjustment)
            # 最低値は1
            new_values[piece_id] = max(1, new_value)

        return new_values

    def generate_python_code(self, values: dict[int, int]) -> str:
        """Pythonコードとして出力"""
        lines = [
            '"""学習された駒の価値"""',
            "",
            "# 棋譜分析により自動生成",
            "# 方式: 取られた時の敗北率ベース",
            "",
            "LEARNED_PIECE_VALUES = {",
        ]

        for piece_id in sorted(values.keys()):
            value = values[piece_id]
            name = PIECE_NAMES.get(piece_id, "???")
            base = self.base_values.get(piece_id, 0)
            diff = value - base
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            lines.append(f"    {piece_id}: {value},  # {name} (base: {base}, {diff_str})")

        lines.append("}")
        lines.append("")
        lines.append("")
        lines.append("def get_learned_piece_value(piece_id: int) -> int:")
        lines.append('    """学習された駒の価値を取得"""')
        lines.append("    return LEARNED_PIECE_VALUES.get(piece_id, 0)")
        lines.append("")

        return "\n".join(lines)

    def print_comparison(self, new_values: dict[int, int], result: AnalysisResult) -> None:
        """ベース値との比較を表示"""
        print("=== 価値の変化 ===")
        print("駒ID | 駒名    | 基準値 | 新値  | 変化  | 敗北率  | 取られ数")
        print("-" * 70)

        changes = []
        for piece_id in sorted(self.base_values.keys()):
            base = self.base_values[piece_id]
            new = new_values.get(piece_id, base)
            diff = new - base

            stats = result.capture_stats.get(piece_id)
            if stats:
                loss_rate = stats.loss_rate_when_captured
                captures = stats.times_captured
            else:
                loss_rate = 0.5
                captures = 0

            changes.append((abs(diff), piece_id, base, new, diff, loss_rate, captures))

        # 変化量の大きい順にソート
        changes.sort(reverse=True)

        for _, piece_id, base, new, diff, loss_rate, captures in changes:
            name = PIECE_NAMES.get(piece_id, "???")
            diff_str = f"+{diff:4d}" if diff > 0 else f"{diff:5d}"
            print(f"{piece_id:5d} | {name:7s} | {base:6d} | {new:5d} | {diff_str} | {loss_rate:6.1%} | {captures:8d}")

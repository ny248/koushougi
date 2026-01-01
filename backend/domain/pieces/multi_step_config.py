"""マルチステップ移動の設定"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class MultiStepConfig:
    """マルチステップ移動の設定

    Attributes:
        total_steps: 総ステップ数
        can_stop_early: 途中停止可能か
        first_directions: 1ステップ目の方向リスト [(dx, dy), ...]
        next_directions_fn: 1ステップ目の方向 → 次ステップの方向リスト を返す関数
        has_path_kills: 経路取りがあるか（霹靂、招揺など）
    """
    total_steps: int
    can_stop_early: bool
    first_directions: list[tuple[int, int]]
    next_directions_fn: Callable[[tuple[int, int]], list[tuple[int, int]]]
    has_path_kills: bool = False

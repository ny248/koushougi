"""αβ探索で候補手を並べる規則。"""

from collections.abc import Callable
from dataclasses import dataclass

from .game import Game


@dataclass(frozen=True)
class MoveOrdering:
    """盤面の点数で候補を並べ、必要なら現在の局面だけ別の優先度を使う。"""

    # 指定された側にとって良い盤面ほど高い点数を返す。
    position_score: Callable[[Game, str], int]
    # (現在の対局, 候補手の列) を受け取り、各手の優先度を入力順に返す。
    root_priority: Callable | None = None
    # 浅い探索の結果を次の深さで優先する。評価だけを比較する場合は無効にできる。
    use_previous_iteration: bool = True

    def rank_root(self, game, candidates):
        if self.root_priority is None:
            return candidates
        moves = tuple(move for _, move, _ in candidates)
        return [candidate for _, candidate in sorted(
            zip(self.root_priority(game, moves), candidates, strict=True),
            key=lambda item: item[0], reverse=True,
        )]

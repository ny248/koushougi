"""既存コード向けの着手・評価インターフェース。"""

from types import SimpleNamespace

from .evaluation import VALUES as VALUES, material_points as material_points
from .players.alpha_beta import (
    DEFAULT_ORDERING as DEFAULT_ORDERING,
    analyze_search as analyze_search,
    select_move as choose_search_move,
)
from .search import WIN as WIN, SearchResult as SearchResult, SearchTimeout as SearchTimeout
from .search import terminal_score
from .value_network import DEFAULT_NETWORK


def evaluate(board, side):
    """勝敗が確定した盤面を含め、指定された側から見た点数を返す。"""
    terminal = terminal_score(board, side)
    if terminal is not None:
        return terminal
    return DEFAULT_NETWORK.score(SimpleNamespace(board=board, turn=side), side)

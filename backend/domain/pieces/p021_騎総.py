"""騎総（きそう）- ID: 21 - 馬兵の成り、特殊二著"""

from .utils import can_promote_by_zone, multi_step_moves

ID = 21
NAME = "騎総"
READING = "きそう"
PROMOTES_TO = 55

# 馬兵と同じ（桂馬飛び8方向）
KNIGHT_MOVES = [
    (1, 2), (-1, 2), (1, -2), (-1, -2),
    (2, 1), (-2, 1), (2, -1), (-2, -1),
]


def _next_directions(first_dir):
    """1手目の方向から2手目の方向を決定"""
    dx, dy = first_dir
    if abs(dx) == 2:
        # 横方向に2マスだったので、さらに横に桂馬飛び
        return [(dx, 1), (dx, -1)]
    else:
        # 縦方向に2マスだったので、さらに縦に桂馬飛び
        return [(1, dy), (-1, dy)]


def get_moves(pos, board, player):
    """桂馬飛び後、縦横の同じ方向に桂馬飛びするか1手目で止まる"""
    return multi_step_moves(pos, board, player, steps=2,
                            first_directions=KNIGHT_MOVES,
                            next_directions_fn=_next_directions)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

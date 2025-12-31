"""前衝（ぜんしょう）- ID: 12

前（y負方向）にはいくらでも走れる、後ろは1マス
"""

from .utils import can_promote_by_zone, slide_moves_oriented

ID = 12
NAME = "前衝"
READING = "ぜんしょう"
PROMOTES_TO = 42


def get_moves(pos, board, player):
    moves = []
    # 前（y負方向）：無限に走れる
    moves.extend(slide_moves_oriented(pos, [(0, -1)], board, player, max_distance=-1))
    # 後（y正方向）：1マスのみ
    moves.extend(slide_moves_oriented(pos, [(0, 1)], board, player, max_distance=1))
    return moves


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

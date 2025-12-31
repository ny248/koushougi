"""後衝（ごしょう）- ID: 13

後ろ（y正方向）にはいくらでも走れる、前は1マス
"""

from .utils import can_promote_by_zone, slide_moves_oriented

ID = 13
NAME = "後衝"
READING = "ごしょう"
PROMOTES_TO = 43


def get_moves(pos, board, player):
    moves = []
    # 後（y正方向）：無限に走れる
    moves.extend(slide_moves_oriented(pos, [(0, 1)], board, player, max_distance=-1))
    # 前（y負方向）：1マスのみ
    moves.extend(slide_moves_oriented(pos, [(0, -1)], board, player, max_distance=1))
    return moves


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

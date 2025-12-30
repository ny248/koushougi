"""牌総（はいそう）- ID: 31 - 全射撃無効"""

from .utils import can_promote_by_zone, slide_moves, step_moves

ID = 31
NAME = "牌総"
READING = "はいそう"
PROMOTES_TO = 57  # 天塁

STEP_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

SLIDE_DIRECTIONS = [
    (1, 0), (-1, 0),
]

# 被射撃無効（全ての射撃駒）
NO_SHOT_BY = [24, 25, 51, 52, 26, 53, 22, 54]


def get_moves(pos, board, player):
    moves = []
    moves.extend(step_moves(pos, STEP_DIRECTIONS, board, player))
    moves.extend(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    return moves


def get_shot_immunity():
    """被射撃無効情報"""
    return {"no_shot_by": NO_SHOT_BY}


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

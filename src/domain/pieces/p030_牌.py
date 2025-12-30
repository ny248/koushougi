"""牌（はい）- ID: 30 - 弓・弩に射られない"""

from .utils import can_promote_by_zone, step_moves

ID = 30
NAME = "牌"
READING = "はい"
PROMOTES_TO = 31  # 牌総

STEP_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 被射撃無効
NO_SHOT_BY = [24, 25, 51, 52]  # 弓, 弩, 彍騎, 弩騎には射られない


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def get_shot_immunity():
    """被射撃無効情報"""
    return {"no_shot_by": NO_SHOT_BY}


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

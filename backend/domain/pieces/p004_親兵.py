"""親兵（しんへい）- ID: 4 - 後ろ以外の7方向に1路"""

from .utils import can_promote_by_zone, step_moves_oriented

ID = 4
NAME = "親兵"
READING = "しんへい"
PROMOTES_TO = 17

# player=0基準: 後ろ(0, 1)以外の7方向
# 前(0, -1), 左右, 斜め4方向
STEP_DIRECTIONS = [
    (0, -1),   # 前
    (1, 0),    # 右
    (-1, 0),   # 左
    (1, -1),   # 斜め右前
    (-1, -1),  # 斜め左前
    (1, 1),    # 斜め右後
    (-1, 1),   # 斜め左後
]


def get_moves(pos, board, player):
    return step_moves_oriented(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

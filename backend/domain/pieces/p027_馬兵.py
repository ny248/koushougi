"""馬兵（ばへい）- ID: 27"""

from .utils import can_promote_by_zone, jump_moves

ID = 27
NAME = "馬兵"
READING = "ばへい"
PROMOTES_TO = 21

STEP_DIRECTIONS = [
    (1, 2),
    (-1, 2),
    (1, -2),
    (-1, -2),
    (2, 1),
    (-2, 1),
    (2, -1),
    (-2, -1),
]


def get_moves(pos, board, player):
    return jump_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    # 敵陣で成れる
    if can_promote_by_zone(from_pos, to_pos, player):
        return True
    # 仏狼機を取ると成れる
    if captured_piece == 22:
        return True
    return False

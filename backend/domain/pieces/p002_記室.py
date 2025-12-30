"""記室（きしつ）- ID: 2"""

from .utils import can_promote_by_zone, jump_moves

ID = 2
NAME = "記室"
READING = "きしつ"
PROMOTES_TO = 36

STEP_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
    (0, 2),
    (0, -2),
    (2, 0),
    (-2, 0),
]


def get_moves(pos, board, player):
    return jump_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

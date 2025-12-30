"""参謀（さんぼう）- ID: 3"""

from .utils import can_promote_by_zone, jump_moves

ID = 3
NAME = "参謀"
READING = "さんぼう"
PROMOTES_TO = 37

STEP_DIRECTIONS = [
    (0, 1),
    (0, -1),
    (1, 0),
    (-1, 0),
    (2, 2),
    (-2, 2),
    (2, -2),
    (-2, -2),
]


def get_moves(pos, board, player):
    return jump_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

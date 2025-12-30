"""舎人（しゃじん）- ID: 6"""

from .utils import can_promote_by_zone, step_moves

ID = 6
NAME = "舎人"
READING = "しゃじん"
PROMOTES_TO = 38

STEP_DIRECTIONS = [
    (0, 1),
    (0, -1),
    (1, 0),
    (-1, 0),
    (1, 1),
    (-1, 1),
]


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

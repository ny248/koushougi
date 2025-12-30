"""千総（せんそう）- ID: 20"""

from .utils import can_promote_by_zone, slide_moves

ID = 20
NAME = "千総"
READING = "せんそう"
PROMOTES_TO = 48

SLIDE_DIRECTIONS = [
    (0, 1),
    (0, -1),
    (1, 0),
    (-1, 0),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

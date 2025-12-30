"""歩総（ぶそう）- ID: 29"""

from .utils import can_promote_by_zone, slide_moves, step_moves

ID = 29
NAME = "歩総"
READING = "ぶそう"
PROMOTES_TO = 56

STEP_DIRECTIONS = [
    (1, 0),
    (-1, 0),
]

SLIDE_DIRECTIONS = [
    (0, 1),
    (0, -1),
]


def get_moves(pos, board, player):
    moves = []
    moves.extend(step_moves(pos, STEP_DIRECTIONS, board, player))
    moves.extend(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    return moves


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

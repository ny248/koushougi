"""天網（てんもう）- ID: 42"""

from .utils import slide_moves, step_moves

ID = 42
NAME = "天網"
READING = "てんもう"

STEP_DIRECTIONS = [
    (0, -1),
]

SLIDE_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, 0),
    (-1, 0),
]


def get_moves(pos, board, player):
    moves = []
    moves.extend(step_moves(pos, STEP_DIRECTIONS, board, player))
    moves.extend(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    return moves

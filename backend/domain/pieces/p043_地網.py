"""地網（じもう）- ID: 43"""

from .utils import slide_moves, step_moves

ID = 43
NAME = "地網"
READING = "じもう"

STEP_DIRECTIONS = [
    (0, 1),
]

SLIDE_DIRECTIONS = [
    (1, -1),
    (-1, -1),
    (1, 0),
    (-1, 0),
]


def get_moves(pos, board, player):
    moves = []
    moves.extend(step_moves(pos, STEP_DIRECTIONS, board, player))
    moves.extend(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    return moves

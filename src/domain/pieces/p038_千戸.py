"""千戸（せんこ）- ID: 38"""

from .utils import slide_moves, step_moves

ID = 38
NAME = "千戸"
READING = "せんこ"

STEP_DIRECTIONS = [
    (1, 0),
    (-1, 0),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
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

"""百戸（ひゃっこ）- ID: 39"""

from .utils import slide_moves, step_moves

ID = 39
NAME = "百戸"
READING = "ひゃっこ"

STEP_DIRECTIONS = [
    (0, 1),
    (0, -1),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]

SLIDE_DIRECTIONS = [
    (1, 0),
    (-1, 0),
]


def get_moves(pos, board, player):
    moves = []
    moves.extend(step_moves(pos, STEP_DIRECTIONS, board, player))
    moves.extend(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    return moves

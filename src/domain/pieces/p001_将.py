"""将（しょう）- ID: 1"""

from .utils import step_moves

ID = 1
NAME = "将"
READING = "しょう"

STEP_DIRECTIONS = [
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
    return step_moves(pos, STEP_DIRECTIONS, board, player)

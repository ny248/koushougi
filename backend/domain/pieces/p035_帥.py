"""帥（すい）- ID: 35"""

from .utils import step_moves

ID = 35
NAME = "帥"
READING = "すい"

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

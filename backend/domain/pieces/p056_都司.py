"""都司（とし）- ID: 56"""

from .utils import slide_moves

ID = 56
NAME = "都司"
READING = "とし"

SLIDE_DIRECTIONS = [
    (0, 1),
    (0, -1),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)

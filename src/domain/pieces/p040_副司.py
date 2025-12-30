"""副司（ふくし）- ID: 40"""

from .utils import slide_moves

ID = 40
NAME = "副司"
READING = "ふくし"

SLIDE_DIRECTIONS = [
    (0, 1),
    (1, 1),
    (-1, 1),
]


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)

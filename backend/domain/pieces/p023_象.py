"""象（ぞう）- ID: 23"""

from .utils import slide_moves

ID = 23
NAME = "象"
READING = "ぞう"

SLIDE_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)

"""力士（りきし）- ID: 5 - 二著する駒"""

from .utils import lion_moves

ID = 5
NAME = "力士"
READING = "りきし"

# 将と同じ8方向
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


def get_moves(pos, board, player):
    return lion_moves(pos, DIRECTIONS, board, player, jump=False)

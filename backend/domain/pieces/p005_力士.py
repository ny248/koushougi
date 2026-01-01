"""力士（りきし）- ID: 5 - 二著する駒"""

from .utils import multi_step_moves

ID = 5
NAME = "力士"
READING = "りきし"

# 将と同じ8方向
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


def get_moves(pos, board, player):
    return multi_step_moves(pos, board, player, steps=2,
                            first_directions=DIRECTIONS,
                            next_directions_fn=lambda d: DIRECTIONS)

"""天馬（てんば）- ID: 55 - 騎総の成り、二著する駒"""

from .utils import multi_step_moves

ID = 55
NAME = "天馬"
READING = "てんば"

# 馬兵と同じ（桂馬飛び8方向）
DIRECTIONS = [
    (1, 2), (-1, 2), (1, -2), (-1, -2),
    (2, 1), (-2, 1), (2, -1), (-2, -1),
]


def get_moves(pos, board, player):
    return multi_step_moves(pos, board, player, steps=2,
                            first_directions=DIRECTIONS,
                            next_directions_fn=lambda d: DIRECTIONS)

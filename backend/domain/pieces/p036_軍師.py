"""軍師（ぐんし）- ID: 36 - 記室の成り、二著する駒"""

from .utils import multi_step_moves

ID = 36
NAME = "軍師"
READING = "ぐんし"

# 記室と同じ: 斜め1マス + 縦横2マス跳び
DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
    (0, 2), (0, -2), (2, 0), (-2, 0),
]


def get_moves(pos, board, player):
    return multi_step_moves(pos, board, player, steps=2,
                            first_directions=DIRECTIONS,
                            next_directions_fn=lambda d: DIRECTIONS)

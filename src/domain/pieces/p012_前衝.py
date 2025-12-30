"""前衝（ぜんしょう）- ID: 12"""

from .utils import can_promote_by_zone, slide_moves

ID = 12
NAME = "前衝"
READING = "ぜんしょう"
PROMOTES_TO = 42

SLIDE_DIRECTIONS = [
    (0, 1),
    (0, -1),
]
SLIDE_MAX = 1


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player, SLIDE_MAX)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

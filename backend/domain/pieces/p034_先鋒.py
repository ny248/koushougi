"""先鋒（せんぽう）- ID: 34 - 前に5路まで"""

from .utils import can_promote_by_zone, slide_moves_oriented

ID = 34
NAME = "先鋒"
READING = "せんぽう"
PROMOTES_TO = 56

# player=0基準: 前は-y方向
SLIDE_DIRECTIONS = [
    (0, -1),
]
SLIDE_MAX = 5


def get_moves(pos, board, player):
    return slide_moves_oriented(pos, SLIDE_DIRECTIONS, board, player, SLIDE_MAX)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

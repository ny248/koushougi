"""虎翼（こよく）- ID: 49 - 把総の成り"""

from .utils import slide_moves, lion_moves

ID = 49
NAME = "虎翼"
READING = "こよく"

# 縦横スライド
SLIDE_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]

# 牌の動き（斜め1マス）を二著
LION_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


def get_moves(pos, board, player):
    moves = set()
    # 縦横スライド
    moves.update(slide_moves(pos, SLIDE_DIRECTIONS, board, player))
    # 牌の動きを二著
    moves.update(lion_moves(pos, LION_DIRECTIONS, board, player, jump=False))
    return list(moves)

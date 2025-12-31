"""鷹揚（ようよう）- ID: 50 - 百総の成り"""

from .utils import slide_moves, lion_moves

ID = 50
NAME = "鷹揚"
READING = "ようよう"

# 斜めスライド
SLIDE_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 縦横1マスの二著（方向転換可能、居食いあり）
LION_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]


def get_moves(pos, board, player):
    """斜めスライド + 縦横1マスを二著（方向転換可、居食いあり）"""
    moves = set()

    # 斜めスライド
    moves.update(slide_moves(pos, SLIDE_DIRECTIONS, board, player))

    # 縦横1マスの二著（lion_movesはジャンプなし、方向転換可、居食いあり）
    moves.update(lion_moves(pos, LION_DIRECTIONS, board, player, jump=False))

    return list(moves)

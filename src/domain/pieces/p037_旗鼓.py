"""旗鼓（きこ）- ID: 37 - 参謀の成り、二著する駒"""

from .utils import lion_moves

ID = 37
NAME = "旗鼓"
READING = "きこ"

# 参謀と同じ: 縦横1マス + 斜め2マス跳び
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (2, 2), (-2, 2), (2, -2), (-2, -2),
]


def get_moves(pos, board, player):
    return lion_moves(pos, DIRECTIONS, board, player, jump=True)

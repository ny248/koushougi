"""虎翼（こよく）- ID: 49 - 把総の成り"""

from .utils import slide_moves, multi_step_moves

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
    moves.update(multi_step_moves(pos, board, player, steps=2,
                                  first_directions=LION_DIRECTIONS,
                                  next_directions_fn=lambda d: LION_DIRECTIONS))
    return list(moves)

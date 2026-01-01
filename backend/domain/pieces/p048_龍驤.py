"""龍驤（りゅうじょう）- ID: 48 - 千総の成り、千総+力士の動き"""

from .utils import multi_step_moves, slide_moves

ID = 48
NAME = "龍驤"
READING = "りゅうじょう"

# 8方向すべて
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


def get_moves(pos, board, player):
    moves = set()
    # 千総の動き（8方向スライド）
    moves.update(slide_moves(pos, DIRECTIONS, board, player))
    # 力士の動き（二著）
    moves.update(multi_step_moves(pos, board, player, steps=2,
                                  first_directions=DIRECTIONS,
                                  next_directions_fn=lambda d: DIRECTIONS))
    return list(moves)

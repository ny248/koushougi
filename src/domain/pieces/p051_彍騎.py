"""彍騎（こうき）- ID: 51 - 弓の成り、3路射"""

from .utils import jump_moves, shoot_targets

ID = 51
NAME = "彍騎"
READING = "こうき"

KNIGHT_MOVES = [
    (1, 2), (-1, 2), (1, -2), (-1, -2),
    (2, 1), (-2, 1), (2, -1), (-2, -1),
]

# 射撃設定（弓と同じ）
SHOOT_RANGE = 3
SHOOT_COUNT = 1
SHOOT_IMMUNE = [57, 30, 31, 32, 33, 53, 44]


def get_moves(pos, board, player):
    return jump_moves(pos, KNIGHT_MOVES, board, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE,
                            penetrate=False,
                            immune=SHOOT_IMMUNE)
    if targets:
        return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}
    return None

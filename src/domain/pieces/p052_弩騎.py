"""弩騎（どき）- ID: 52 - 弩の成り、5路射"""

from .utils import jump_moves, shoot_targets

ID = 52
NAME = "弩騎"
READING = "どき"

KNIGHT_MOVES = [
    (1, 2), (-1, 2), (1, -2), (-1, -2),
    (2, 1), (-2, 1), (2, -1), (-2, -1),
]

# 射撃設定（弩と同じ）
SHOOT_RANGE = 5
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

"""弩（ど）- ID: 25 - 5路射"""

from .utils import can_promote_by_zone, step_moves, shoot_targets

ID = 25
NAME = "弩"
READING = "ど"
PROMOTES_TO = 52  # 弩騎

STEP_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]

# 射撃設定
SHOOT_RANGE = 5
SHOOT_COUNT = 1
# 天塁, 牌, 牌総, 車, 車総, 砲車, 五里霧には射れない
SHOOT_IMMUNE = [57, 30, 31, 32, 33, 53, 44]


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE,
                            penetrate=False,
                            immune=SHOOT_IMMUNE)
    if targets:
        return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}
    return None

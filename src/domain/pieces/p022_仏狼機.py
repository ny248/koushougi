"""仏狼機（ぶつろうき）- ID: 22 - 7路射×2"""

from .utils import can_promote_by_zone, step_moves, shoot_targets

ID = 22
NAME = "仏狼機"
READING = "ぶつろうき"
PROMOTES_TO = 54  # 神機車

STEP_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]

# 射撃設定
SHOOT_RANGE = 7
SHOOT_COUNT = 2
# 天塁, 牌総には射れない。五里霧は6路以上なら射れる
SHOOT_IMMUNE = [57, 31]
SHOOT_MIN_RANGE = {44: 6}  # 五里霧は6路以上離れていれば射れる


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃（2発まで）"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE,
                            penetrate=False,
                            immune=SHOOT_IMMUNE,
                            min_range=SHOOT_MIN_RANGE)
    if targets:
        return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}
    return None

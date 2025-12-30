"""砲（ほう）- ID: 26 - 5路射、貫通"""

from .utils import can_promote_by_zone, step_moves, shoot_targets

ID = 26
NAME = "砲"
READING = "ほう"
PROMOTES_TO = 53  # 砲車

STEP_DIRECTIONS = [
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]

# 射撃設定
SHOOT_RANGE = 5
SHOOT_COUNT = 1
SHOOT_PENETRATE = True
SHOOT_PENETRATE_BLOCK = [31, 57]  # 牌総, 天塁で貫通ブロック
# 天塁, 牌総, 五里霧には射れない
SHOOT_IMMUNE = [57, 31, 44]


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃（貫通）"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE,
                            penetrate=SHOOT_PENETRATE,
                            penetrate_block=SHOOT_PENETRATE_BLOCK,
                            immune=SHOOT_IMMUNE)
    if targets:
        return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}
    return None

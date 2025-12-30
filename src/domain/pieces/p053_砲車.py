"""砲車（ほうしゃ）- ID: 53 - 砲の成り、5路射貫通"""

from .utils import slide_moves, shoot_targets

ID = 53
NAME = "砲車"
READING = "ほうしゃ"

SLIDE_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]
SLIDE_MAX = 5

# 射撃設定（砲と同じ）
SHOOT_RANGE = 5
SHOOT_COUNT = 1
SHOOT_PENETRATE = True
SHOOT_PENETRATE_BLOCK = [31, 57]  # 牌総, 天塁
SHOOT_IMMUNE = [57]  # 天塁には射れない

# 制限
NO_CAPTURE = [57]  # 天塁は取れない
NO_SHOT_BY = [24, 25, 51, 52]  # 弓, 弩, 彍騎, 弩騎には射られない


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player, SLIDE_MAX)


def get_capture_restriction():
    """取れない駒のリスト"""
    return NO_CAPTURE


def get_shot_immunity():
    """被射撃無効情報"""
    return {"no_shot_by": NO_SHOT_BY}


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

"""神機車（しんきしゃ）- ID: 54 - 仏狼機の成り、7路射×2"""

from .utils import slide_moves, shoot_targets

ID = 54
NAME = "神機車"
READING = "しんきしゃ"

SLIDE_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]
SLIDE_MAX = 5

# 射撃設定（仏狼機と同じ）
SHOOT_RANGE = 7
SHOOT_COUNT = 2
SHOOT_IMMUNE = [57]  # 天塁には射れない
SHOOT_MIN_RANGE = {44: 6}  # 五里霧は6路以上

# 制限
NO_CAPTURE = [57]  # 天塁は取れない


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player, SLIDE_MAX)


def get_capture_restriction():
    """取れない駒のリスト"""
    return NO_CAPTURE


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

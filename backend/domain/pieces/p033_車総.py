"""車総（しゃそう）- ID: 33 - 天塁取れない、弓・弩に射られない"""

from .utils import can_promote_by_zone, slide_moves

ID = 33
NAME = "車総"
READING = "しゃそう"
PROMOTES_TO = 20  # 千総

SLIDE_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]

# 制限
NO_CAPTURE = [57]  # 天塁は取れない
NO_SHOT_BY = [24, 25, 51, 52]  # 弓, 弩, 彍騎, 弩騎には射られない


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)


def get_capture_restriction():
    """取れない駒のリスト"""
    return NO_CAPTURE


def get_shot_immunity():
    """被射撃無効情報"""
    return {"no_shot_by": NO_SHOT_BY}


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

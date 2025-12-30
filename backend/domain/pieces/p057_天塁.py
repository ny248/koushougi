"""天塁（てんるい）- ID: 57 - 全射撃無効、車系に取られない"""

from .utils import slide_moves

ID = 57
NAME = "天塁"
READING = "てんるい"

SLIDE_DIRECTIONS = [
    (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 被射撃無効（全ての射撃駒）
NO_SHOT_BY = [24, 25, 51, 52, 26, 53, 22, 54]
# 取られない（車, 車総, 砲車, 神機車）
NO_CAPTURED_BY = [32, 33, 53, 54]


def get_moves(pos, board, player):
    return slide_moves(pos, SLIDE_DIRECTIONS, board, player)


def get_shot_immunity():
    """被射撃無効情報"""
    return {"no_shot_by": NO_SHOT_BY}


def get_capture_immunity():
    """取られない駒のリスト"""
    return NO_CAPTURED_BY

"""神僧（しんそう）- ID: 11 - 1路射、取れるのは高道・神僧のみ"""

from .utils import can_promote_by_zone, jump_moves, shoot_targets

ID = 11
NAME = "神僧"
READING = "しんそう"
PROMOTES_TO = 45  # 聖燈

JUMP_DIRECTIONS = [
    (0, 2), (0, -2), (2, 0), (-2, 0),
    (2, 2), (-2, 2), (2, -2), (-2, -2),
]

# 高道と神僧以外は取れない
ONLY_CAPTURE = [10, 11]

# 射撃設定
SHOOT_RANGE = 1
SHOOT_COUNT = 1


def get_moves(pos, board, player):
    return jump_moves(pos, JUMP_DIRECTIONS, board, player)


def get_capture_filter():
    """取れる駒の制限（高道・神僧のみ）"""
    return ONLY_CAPTURE


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃（1路射）- 全ての駒を射れる"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE,
                            penetrate=True)
    if targets:
        return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}
    return None

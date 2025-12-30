"""五里霧（ごりむ）- ID: 44 - 高道の成り、二著する駒"""

from .utils import lion_moves, shoot_targets

ID = 44
NAME = "五里霧"
READING = "ごりむ"

# 高道と同じ: 8方向に2マス跳び
DIRECTIONS = [
    (0, 2), (0, -2), (2, 0), (-2, 0),
    (2, 2), (-2, 2), (2, -2), (-2, -2),
]

# 高道と神僧以外は取れない
ONLY_CAPTURE = [10, 11]  # 高道, 神僧

# 射撃無効: なし（全て射れる）
SHOOT_RANGE = 1
SHOOT_COUNT = 2

# 被射撃無効
NO_SHOT_BY = [24, 25, 51, 52, 26, 53]  # 弓, 弩, 彍騎, 弩騎, 砲, 砲車
# 仏狼機・神機車は6路以上離れていないと射れない
NO_SHOT_BY_RANGE = {22: 5, 54: 5}  # 5路以内は射れない

# 聖燈から5路以内にいると高道に戻る
REVERT_TRIGGER = 45  # 聖燈
REVERT_RANGE = 5
REVERT_TO = 10  # 高道


def get_moves(pos, board, player):
    # 敵駒は取れない（高道・神僧以外）ので、移動可能位置のみ返す
    return lion_moves(pos, DIRECTIONS, board, player, jump=True)


def get_capture_filter():
    """取れる駒の制限"""
    return ONLY_CAPTURE


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃（1路射×2）"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE, penetrate=True)
    # 最大2つまで選択可能（UI側で処理）
    return {"shoot": {"targets": targets, "count": SHOOT_COUNT}}


def get_shot_immunity():
    """被射撃無効情報"""
    return {
        "no_shot_by": NO_SHOT_BY,
        "no_shot_by_range": NO_SHOT_BY_RANGE,
    }


def check_revert(game_state, pos, player):
    """成り戻りチェック: 敵の聖燈から5路以内にいるか"""
    x, y = pos
    enemy = 1 - player
    for ex in range(19):
        for ey in range(19):
            piece = game_state.board.get(ex, ey)
            if piece and piece[0] == REVERT_TRIGGER and piece[1] == enemy:
                dist = max(abs(ex - x), abs(ey - y))
                if dist <= REVERT_RANGE:
                    return REVERT_TO
    return None

"""聖燈（しょうとう）- ID: 45 - 神僧の成り、二著する駒"""

from .utils import multi_step_moves, shoot_targets
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 45
NAME = "聖燈"
READING = "しょうとう"

# 神僧と同じ: 8方向に2マス跳び
DIRECTIONS = [
    (0, 2), (0, -2), (2, 0), (-2, 0),
    (2, 2), (-2, 2), (2, -2), (-2, -2),
]

# 高道と神僧以外は取れない
ONLY_CAPTURE = [10, 11]  # 高道, 神僧

# 射撃無効: なし（全て射れる）
SHOOT_RANGE = 1
SHOOT_COUNT = 2

# オーラ効果: 5路以内の敵の五里霧を高道に戻す
AURA_TARGET = 44  # 五里霧
AURA_RANGE = 5
AURA_REVERT_TO = 10  # 高道


def get_multi_step_config():
    """マルチステップ設定"""
    return MultiStepConfig(
        total_steps=2,
        can_stop_early=True,
        first_directions=DIRECTIONS,
        next_directions_fn=lambda d: DIRECTIONS,
        has_path_kills=False,
    )


def get_next_step_options(current_pos, board, player, step_index, first_direction):
    """次ステップの移動先候補を取得"""
    config = get_multi_step_config()
    if step_index == 0:
        directions = config.first_directions
    else:
        directions = config.next_directions_fn(first_direction)
    return _get_next_step_options(current_pos, directions, board, player)


def get_moves(pos, board, player):
    """移動先リストを取得"""
    return multi_step_moves(pos, board, player, steps=2,
                            first_directions=DIRECTIONS,
                            next_directions_fn=lambda d: DIRECTIONS)


def get_capture_filter():
    """取れる駒の制限"""
    return ONLY_CAPTURE


def after_move(game_state, from_pos, to_pos, player):
    """移動後に射撃（1路射×2）"""
    targets = shoot_targets(to_pos, game_state.board, player,
                            shoot_range=SHOOT_RANGE, penetrate=True)
    return {"shoot": {
        "targets": targets,
        "count": SHOOT_COUNT,
        "params": {
            "shoot_range": SHOOT_RANGE,
            "penetrate": True,
        }
    }}


def get_aura_effect():
    """オーラ効果情報"""
    return {
        "target": AURA_TARGET,
        "range": AURA_RANGE,
        "revert_to": AURA_REVERT_TO,
    }

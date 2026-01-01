"""旗鼓（きこ）- ID: 37 - 参謀の成り、二著する駒"""

from .utils import multi_step_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 37
NAME = "旗鼓"
READING = "きこ"

# 参謀と同じ: 縦横1マス + 斜め2マス跳び
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (2, 2), (-2, 2), (2, -2), (-2, -2),
]


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

"""軍師（ぐんし）- ID: 36 - 記室の成り、二著する駒"""

from .utils import multi_step_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 36
NAME = "軍師"
READING = "ぐんし"

# 記室と同じ: 斜め1マス + 縦横2マス跳び
DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
    (0, 2), (0, -2), (2, 0), (-2, 0),
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

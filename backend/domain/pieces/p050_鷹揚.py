"""鷹揚（ようよう）- ID: 50 - 百総の成り"""

from .utils import slide_moves, multi_step_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 50
NAME = "鷹揚"
READING = "ようよう"

# 斜めスライド
SLIDE_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 縦横1マスの二著（方向転換可能、居食いあり）
LION_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]


def get_multi_step_config():
    """マルチステップ設定（二著部分のみ）"""
    return MultiStepConfig(
        total_steps=2,
        can_stop_early=True,
        first_directions=LION_DIRECTIONS,
        next_directions_fn=lambda d: LION_DIRECTIONS,
        has_path_kills=False,
    )


def get_next_step_options(current_pos, board, player, step_index, first_direction):
    """次ステップの移動先候補を取得（二著部分）"""
    config = get_multi_step_config()
    if step_index == 0:
        directions = config.first_directions
    else:
        directions = config.next_directions_fn(first_direction)
    return _get_next_step_options(current_pos, directions, board, player)


def get_moves(pos, board, player):
    """斜めスライド + 縦横1マスを二著（後方互換用）"""
    moves = set()

    # 斜めスライド
    moves.update(slide_moves(pos, SLIDE_DIRECTIONS, board, player))

    # 縦横1マスの二著
    moves.update(multi_step_moves(pos, board, player, steps=2,
                                  first_directions=LION_DIRECTIONS,
                                  next_directions_fn=lambda d: LION_DIRECTIONS))

    return list(moves)

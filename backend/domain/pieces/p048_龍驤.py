"""龍驤（りゅうじょう）- ID: 48 - 千総の成り、千総+力士の動き"""

from .utils import multi_step_moves, slide_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 48
NAME = "龍驤"
READING = "りゅうじょう"

# 8方向すべて
DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


def get_multi_step_config():
    """マルチステップ設定（二著部分のみ）"""
    return MultiStepConfig(
        total_steps=2,
        can_stop_early=True,
        first_directions=DIRECTIONS,
        next_directions_fn=lambda d: DIRECTIONS,
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
    """スライド移動 + 二著の移動先リストを取得"""
    moves = set()
    # 千総の動き（8方向スライド）
    moves.update(slide_moves(pos, DIRECTIONS, board, player))
    # 力士の動き（二著）
    moves.update(multi_step_moves(pos, board, player, steps=2,
                                  first_directions=DIRECTIONS,
                                  next_directions_fn=lambda d: DIRECTIONS))
    return list(moves)

"""招揺（しょうよう）- ID: 47 - 旗の成り、通り道の敵を全て倒す"""

from .utils import multi_step_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 47
NAME = "招揺"
READING = "しょうよう"

ORTHOGONAL = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]

# 高道が死ぬと旗に戻る
REVERT_ON_DEATH = 10  # 高道
REVERT_TO = 16  # 旗


def get_multi_step_config():
    """マルチステップ設定"""
    return MultiStepConfig(
        total_steps=5,
        can_stop_early=True,
        first_directions=ORTHOGONAL,
        next_directions_fn=lambda d: [d],  # 方向固定
        has_path_kills=True,
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
    """縦横5著まで移動可能（後方互換用）"""
    return multi_step_moves(pos, board, player, steps=5,
                            first_directions=ORTHOGONAL,
                            next_directions_fn=lambda d: [d],
                            can_stop_early=True)


def get_path_kills(pos, board, player, to_pos):
    """経路上の敵を取得"""
    x, y = pos
    tx, ty = to_pos

    # 方向を特定
    dx = 0 if tx == x else (1 if tx > x else -1)
    dy = 0 if ty == y else (1 if ty > y else -1)

    kills = []
    dist = max(abs(tx - x), abs(ty - y))
    for i in range(1, dist + 1):
        nx, ny = x + dx * i, y + dy * i
        if board.has_enemy(nx, ny, player):
            kills.append((nx, ny))

    return kills


def check_revert(game_state, pos, player):
    """高道が死んでいたら旗に戻る"""
    for x in range(19):
        for y in range(19):
            piece = game_state.board.get(x, y)
            if piece and piece[0] == REVERT_ON_DEATH and piece[1] == player:
                return None  # 高道が生きている
    return REVERT_TO  # 旗に戻る

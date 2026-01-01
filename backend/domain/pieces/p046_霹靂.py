"""霹靂（へきれき）- ID: 46 - 鼓の成り、縦横1マス×5回移動"""

from .utils import multi_step_moves
from .utils import get_next_step_options as _get_next_step_options
from .multi_step_config import MultiStepConfig

ID = 46
NAME = "霹靂"
READING = "へきれき"

# 高道が死ぬと鼓に戻る
REVERT_ON_DEATH = 10  # 高道
REVERT_TO = 15  # 鼓

# 縦横の4方向（各ステップで選択可能）
ORTHOGONAL = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def get_multi_step_config():
    """マルチステップ設定"""
    return MultiStepConfig(
        total_steps=5,
        can_stop_early=False,  # 途中停止不可
        first_directions=ORTHOGONAL,
        next_directions_fn=lambda d: ORTHOGONAL,
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
    """縦横1マスを5回繰り返す移動"""
    return multi_step_moves(pos, board, player, steps=5,
                            first_directions=ORTHOGONAL,
                            next_directions_fn=lambda d: ORTHOGONAL,
                            can_stop_early=False)


def get_path_kills(pos, board, player, to_pos):
    """経路上の敵を取得（最初に見つかった有効経路を使用）"""

    def dfs(current_pos, step, kills):
        if step == 5:
            if current_pos == to_pos:
                return kills
            return None

        for dx, dy in ORTHOGONAL:
            nx, ny = current_pos[0] + dx, current_pos[1] + dy
            if not board.is_valid(nx, ny):
                continue
            if board.has_ally(nx, ny, player):
                continue
            new_kills = kills[:]
            if board.has_enemy(nx, ny, player):
                new_kills.append((nx, ny))
            result = dfs((nx, ny), step + 1, new_kills)
            if result is not None:
                return result
        return None

    result = dfs(pos, 0, [])
    return result if result is not None else []


def check_revert(game_state, pos, player):
    """高道が死んでいたら鼓に戻る"""
    # 自分の高道が生きているか確認
    for x in range(19):
        for y in range(19):
            piece = game_state.board.get(x, y)
            if piece and piece[0] == REVERT_ON_DEATH and piece[1] == player:
                return None  # 高道が生きている
    return REVERT_TO  # 鼓に戻る

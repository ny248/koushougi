"""毒火（どくか）- ID: 41 - 軍匠の成り、周囲破壊"""

from .utils import step_moves_oriented, area_kill_targets

ID = 41
NAME = "毒火"
READING = "どくか"

# player=0基準: 前、後ろ、斜め前2方向
STEP_DIRECTIONS = [
    (0, 1), (0, -1),
    (1, 1), (-1, 1),
]


def get_moves(pos, board, player):
    return step_moves_oriented(pos, STEP_DIRECTIONS, board, player)


def after_move(game_state, from_pos, to_pos, player):
    """移動後に周囲8マスの全駒（敵味方問わず）を破壊"""
    targets = area_kill_targets(to_pos, game_state.board, player)
    if targets:
        return {"area_kill": targets}
    return None

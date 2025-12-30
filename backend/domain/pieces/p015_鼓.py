"""鼓（こ）- ID: 15 - 高道が死ぬと成れない"""

from .utils import can_promote_by_zone, step_moves

ID = 15
NAME = "鼓"
READING = "こ"
PROMOTES_TO = 46  # 霹靂

# 横と斜め
STEP_DIRECTIONS = [
    (1, 0), (-1, 0),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 高道が死んでいると成れない
REQUIRE_ALIVE = 10  # 高道


def get_moves(pos, board, player):
    return step_moves(pos, STEP_DIRECTIONS, board, player)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    # 高道が生きているか確認
    for x in range(19):
        for y in range(19):
            piece = game_state.board.get(x, y)
            if piece and piece[0] == REQUIRE_ALIVE and piece[1] == player:
                return can_promote_by_zone(from_pos, to_pos, player)
    return False  # 高道が死んでいる

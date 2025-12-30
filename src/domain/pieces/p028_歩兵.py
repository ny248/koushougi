"""歩兵（ふひょう）- ID: 28 - 鼓が死ぬと前に進めない"""

from .utils import can_promote_by_zone

ID = 28
NAME = "歩兵"
READING = "ふひょう"
PROMOTES_TO = 29  # 歩総

# 全方向
ALL_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]

# 鼓が死んだ時に無効になる方向（前）
FORWARD_DIRECTION = (0, 1)
DEPENDS_ON = 15  # 鼓


def get_moves(pos, board, player):
    """縦横に1路進める。ただし鼓が死ぬと前に進めなくなる"""
    x, y = pos
    moves = []

    # 鼓が生きているか確認
    ko_alive = False
    for bx in range(19):
        for by in range(19):
            piece = board.get(bx, by)
            if piece and piece[0] == DEPENDS_ON and piece[1] == player:
                ko_alive = True
                break
        if ko_alive:
            break

    for dx, dy in ALL_DIRECTIONS:
        # 鼓が死んでいたら前方向は無効
        if not ko_alive and (dx, dy) == FORWARD_DIRECTION:
            # プレイヤーによって前の方向が変わる
            actual_dy = dy if player == 0 else -dy
            if actual_dy > 0 if player == 0 else actual_dy < 0:
                continue

        actual_dy = dy if player == 0 else -dy
        nx, ny = x + dx, y + actual_dy
        if board.is_valid(nx, ny) and not board.has_ally(nx, ny, player):
            moves.append((nx, ny))

    return moves


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

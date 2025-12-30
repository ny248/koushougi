"""鷹揚（ようよう）- ID: 50 - 百総の成り"""

from .utils import slide_moves, step_moves

ID = 50
NAME = "鷹揚"
READING = "ようよう"

# 斜めスライド
SLIDE_DIRECTIONS = [
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

# 縦横に1～2マス（2マス目で敵を2個取れる）
STEP_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]


def get_moves(pos, board, player):
    """斜めスライド + 縦横1～2マス"""
    x, y = pos
    moves = set()

    # 斜めスライド
    moves.update(slide_moves(pos, SLIDE_DIRECTIONS, board, player))

    # 縦横1マス
    moves.update(step_moves(pos, STEP_DIRECTIONS, board, player))

    # 縦横2マス（1マス目に味方がいなければ）
    for dx, dy in STEP_DIRECTIONS:
        nx1, ny1 = x + dx, y + dy
        if not board.is_valid(nx1, ny1):
            continue
        if board.has_ally(nx1, ny1, player):
            continue  # 味方は飛び越えられない

        nx2, ny2 = nx1 + dx, ny1 + dy
        if board.is_valid(nx2, ny2) and not board.has_ally(nx2, ny2, player):
            moves.add((nx2, ny2))

    return list(moves)


def get_double_capture_info():
    """2マス目移動時の情報（1マス目と2マス目の両方の敵を取れる）"""
    return {"directions": STEP_DIRECTIONS, "can_capture_both": True}

"""騎総（きそう）- ID: 21 - 馬兵の成り、特殊二著"""

from .utils import can_promote_by_zone

ID = 21
NAME = "騎総"
READING = "きそう"
PROMOTES_TO = 55

# 馬兵と同じ（桂馬飛び8方向）
KNIGHT_MOVES = [
    (1, 2), (-1, 2), (1, -2), (-1, -2),
    (2, 1), (-2, 1), (2, -1), (-2, -1),
]


def get_moves(pos, board, player):
    """桂馬飛び後、縦横の同じ方向に桂馬飛びするか1手目で止まる。元の位置には戻れない"""
    x, y = pos
    moves = set()

    for dx1, dy1 in KNIGHT_MOVES:
        nx1, ny1 = x + dx1, y + dy1
        if not board.is_valid(nx1, ny1):
            continue
        if board.has_ally(nx1, ny1, player):
            continue

        # 1手目で止まる
        moves.add((nx1, ny1))

        # 2手目: 縦横の同じ方向に桂馬飛び
        # dx1の絶対値で縦横方向を決定
        if abs(dx1) == 2:
            # 横方向に2マスだったので、さらに横に桂馬飛び
            second_moves = [(dx1, 1), (dx1, -1)]
        else:
            # 縦方向に2マスだったので、さらに縦に桂馬飛び
            second_moves = [(1, dy1), (-1, dy1)]

        for dx2, dy2 in second_moves:
            nx2, ny2 = nx1 + dx2, ny1 + dy2
            if not board.is_valid(nx2, ny2):
                continue
            if board.has_ally(nx2, ny2, player):
                continue
            # 元の位置には戻れない
            if (nx2, ny2) == (x, y):
                continue
            moves.add((nx2, ny2))

    return list(moves)


def can_promote(game_state, from_pos, to_pos, captured_piece, player):
    return can_promote_by_zone(from_pos, to_pos, player)

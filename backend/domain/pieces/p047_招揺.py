"""招揺（しょうよう）- ID: 47 - 旗の成り、通り道の敵を全て倒す"""

ID = 47
NAME = "招揺"
READING = "しょうよう"

SLIDE_DIRECTIONS = [
    (0, 1), (0, -1), (1, 0), (-1, 0),
]
SLIDE_MAX = 5

# 高道が死ぬと旗に戻る
REVERT_ON_DEATH = 10  # 高道
REVERT_TO = 16  # 旗


def get_moves(pos, board, player):
    """縦横5路まで移動可能（通り道の敵を全て倒しながら）"""
    x, y = pos
    moves = []

    for dx, dy in SLIDE_DIRECTIONS:
        for dist in range(1, SLIDE_MAX + 1):
            nx, ny = x + dx * dist, y + dy * dist
            if not board.is_valid(nx, ny):
                break
            if board.has_ally(nx, ny, player):
                break  # 味方は飛び越えられない
            # 敵がいてもそのまま進める（通り道で倒す）
            moves.append((nx, ny))

    return moves


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

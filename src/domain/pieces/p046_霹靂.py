"""霹靂（へきれき）- ID: 46 - 鼓の成り、ジグザグ5路移動"""

ID = 46
NAME = "霹靂"
READING = "へきれき"

# 経路定義: 各経路は相対座標のリスト（途中で止まれない）
# 高道が死ぬと鼓に戻る
REVERT_ON_DEATH = 10  # 高道
REVERT_TO = 15  # 鼓

# 直線5路
STRAIGHT_PATHS = [
    [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0)],      # 右
    [(-1, 0), (-2, 0), (-3, 0), (-4, 0), (-5, 0)],  # 左
    [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5)],      # 上
    [(0, -1), (0, -2), (0, -3), (0, -4), (0, -5)],  # 下
]

# L字型5路（3路直進後、90度曲がって2路）
L_PATHS = [
    [(1, 0), (2, 0), (3, 0), (3, 1), (3, 2)],      # 右→上
    [(1, 0), (2, 0), (3, 0), (3, -1), (3, -2)],    # 右→下
    [(-1, 0), (-2, 0), (-3, 0), (-3, 1), (-3, 2)],  # 左→上
    [(-1, 0), (-2, 0), (-3, 0), (-3, -1), (-3, -2)],# 左→下
    [(0, 1), (0, 2), (0, 3), (1, 3), (2, 3)],      # 上→右
    [(0, 1), (0, 2), (0, 3), (-1, 3), (-2, 3)],    # 上→左
    [(0, -1), (0, -2), (0, -3), (1, -3), (2, -3)],  # 下→右
    [(0, -1), (0, -2), (0, -3), (-1, -3), (-2, -3)],# 下→左
]

ALL_PATHS = STRAIGHT_PATHS + L_PATHS


def get_moves(pos, board, player):
    """ジグザグ5路移動（途中では止まれない、通り道の敵を全て倒す）"""
    x, y = pos
    moves = []

    for path in ALL_PATHS:
        valid = True
        for dx, dy in path:
            nx, ny = x + dx, y + dy
            if not board.is_valid(nx, ny):
                valid = False
                break
            if board.has_ally(nx, ny, player):
                valid = False
                break
        if valid:
            # 最終地点を追加
            final_dx, final_dy = path[-1]
            moves.append((x + final_dx, y + final_dy))

    return moves


def get_path_kills(pos, board, player, to_pos):
    """経路上の敵を取得"""
    x, y = pos
    tx, ty = to_pos

    for path in ALL_PATHS:
        final_dx, final_dy = path[-1]
        if (x + final_dx, y + final_dy) == (tx, ty):
            # この経路を使用
            kills = []
            for dx, dy in path:
                nx, ny = x + dx, y + dy
                if board.has_enemy(nx, ny, player):
                    kills.append((nx, ny))
            return kills
    return []


def check_revert(game_state, pos, player):
    """高道が死んでいたら鼓に戻る"""
    # 自分の高道が生きているか確認
    for x in range(19):
        for y in range(19):
            piece = game_state.board.get(x, y)
            if piece and piece[0] == REVERT_ON_DEATH and piece[1] == player:
                return None  # 高道が生きている
    return REVERT_TO  # 鼓に戻る

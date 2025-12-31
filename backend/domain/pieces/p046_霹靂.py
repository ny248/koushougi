"""霹靂（へきれき）- ID: 46 - 鼓の成り、縦横1マス×5回移動"""

ID = 46
NAME = "霹靂"
READING = "へきれき"

# 高道が死ぬと鼓に戻る
REVERT_ON_DEATH = 10  # 高道
REVERT_TO = 15  # 鼓

# 縦横の4方向（各ステップで選択可能）
ORTHOGONAL = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def _generate_all_paths():
    """5回の縦横移動の全パターンを事前生成（4^5 = 1024通り）"""
    paths = []

    def dfs(steps, current_path):
        if steps == 5:
            # 相対座標列として保存
            paths.append(list(current_path))
            return
        for dx, dy in ORTHOGONAL:
            current_path.append((dx, dy))
            dfs(steps + 1, current_path)
            current_path.pop()

    dfs(0, [])
    return paths


# 全経路を事前計算
ALL_PATHS = _generate_all_paths()


def get_moves(pos, board, player):
    """縦横1マスを5回繰り返す移動（途中では止まれない、通り道の敵を全て倒す）"""
    x, y = pos
    moves = set()

    for path in ALL_PATHS:
        valid = True
        cx, cy = x, y
        for dx, dy in path:
            cx, cy = cx + dx, cy + dy
            if not board.is_valid(cx, cy):
                valid = False
                break
            if board.has_ally(cx, cy, player):
                valid = False
                break
        if valid:
            moves.add((cx, cy))

    return list(moves)


def get_path_kills(pos, board, player, to_pos):
    """経路上の敵を取得（最初に見つかった有効経路を使用）"""
    x, y = pos
    tx, ty = to_pos

    for path in ALL_PATHS:
        cx, cy = x, y
        valid = True
        kills = []

        for dx, dy in path:
            cx, cy = cx + dx, cy + dy
            if not board.is_valid(cx, cy):
                valid = False
                break
            if board.has_ally(cx, cy, player):
                valid = False
                break
            if board.has_enemy(cx, cy, player):
                kills.append((cx, cy))

        if valid and (cx, cy) == (tx, ty):
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

"""駒の移動パターン共通処理"""


def step_moves(pos, directions, board, player):
    """1マス移動の共通処理

    Args:
        pos: 現在位置 (x, y)
        directions: 移動方向リスト [(dx, dy), ...]
        board: 盤面
        player: プレイヤー (0 or 1)

    Returns:
        移動可能な位置のリスト [(x, y), ...]
    """
    x, y = pos
    moves = []
    for dx, dy in directions:
        nx, ny = x + dx, y + dy
        if board.is_valid(nx, ny) and not board.has_ally(nx, ny, player):
            moves.append((nx, ny))
    return moves


def step_moves_oriented(pos, directions, board, player):
    """1マス移動（プレイヤーによって前後反転）

    Args:
        pos: 現在位置 (x, y)
        directions: 移動方向リスト [(dx, dy), ...] player=0基準
        board: 盤面
        player: プレイヤー (0 or 1)

    Returns:
        移動可能な位置のリスト [(x, y), ...]
    """
    x, y = pos
    moves = []
    for dx, dy in directions:
        actual_dy = dy if player == 0 else -dy
        nx, ny = x + dx, y + actual_dy
        if board.is_valid(nx, ny) and not board.has_ally(nx, ny, player):
            moves.append((nx, ny))
    return moves


def in_enemy_zone(pos, player):
    """敵陣にいるか判定

    盤面配置:
    - 先手（player=0）: 下側（y=13〜18が自陣）、上側（y=0〜5が敵陣）
    - 後手（player=1）: 上側（y=0〜5が自陣）、下側（y=13〜18が敵陣）

    Args:
        pos: 位置 (x, y)
        player: プレイヤー (0 or 1)

    Returns:
        敵陣内ならTrue
    """
    _, y = pos
    if player == 0:
        return y <= 5  # 先手の敵陣は上側
    else:
        return y >= 13  # 後手の敵陣は下側


def can_promote_by_zone(from_pos, to_pos, player):
    """敵陣侵入/内移動で成れるか判定"""
    return in_enemy_zone(from_pos, player) or in_enemy_zone(to_pos, player)


def slide_moves(pos, directions, board, player, max_distance=-1):
    """スライド移動（飛び越え不可）

    Args:
        pos: 現在位置 (x, y)
        directions: 移動方向リスト [(dx, dy), ...]
        board: 盤面
        player: プレイヤー (0 or 1)
        max_distance: 最大移動距離（-1なら無限）

    Returns:
        移動可能な位置のリスト [(x, y), ...]
    """
    x, y = pos
    moves = []
    for dx, dy in directions:
        dist = 1
        while max_distance == -1 or dist <= max_distance:
            nx, ny = x + dx * dist, y + dy * dist
            if not board.is_valid(nx, ny):
                break
            if board.has_ally(nx, ny, player):
                break
            moves.append((nx, ny))
            if board.has_enemy(nx, ny, player):
                break  # 敵を取ったら止まる
            dist += 1
    return moves


def slide_moves_oriented(pos, directions, board, player, max_distance=-1):
    """スライド移動（プレイヤーによって前後反転）"""
    x, y = pos
    moves = []
    for dx, dy in directions:
        actual_dy = dy if player == 0 else -dy
        dist = 1
        while max_distance == -1 or dist <= max_distance:
            nx, ny = x + dx * dist, y + actual_dy * dist
            if not board.is_valid(nx, ny):
                break
            if board.has_ally(nx, ny, player):
                break
            moves.append((nx, ny))
            if board.has_enemy(nx, ny, player):
                break
            dist += 1
    return moves


def jump_moves(pos, cells, board, player):
    """跳び移動（桂馬飛びなど）

    Args:
        pos: 現在位置 (x, y)
        cells: 移動先の相対位置リスト [(dx, dy), ...]
        board: 盤面
        player: プレイヤー (0 or 1)

    Returns:
        移動可能な位置のリスト [(x, y), ...]
    """
    x, y = pos
    moves = []
    for dx, dy in cells:
        nx, ny = x + dx, y + dy
        if board.is_valid(nx, ny) and not board.has_ally(nx, ny, player):
            moves.append((nx, ny))
    return moves


def multi_step_moves(pos, board, player, steps, first_directions, next_directions_fn, can_stop_early=True):
    """複数著移動の共通処理

    Args:
        pos: 現在位置 (x, y)
        board: 盤面
        player: プレイヤー (0 or 1)
        steps: 著数（移動回数）
        first_directions: 1手目の方向リスト [(dx, dy), ...]
        next_directions_fn: 1手目の方向 → 2手目以降の方向リスト を返す関数
        can_stop_early: 途中で止まれるか

    Returns:
        移動可能な位置のリスト [(x, y), ...]
    """
    origin = pos
    moves = set()

    def dfs(current_pos, step, first_dir):
        """深さ優先探索で全経路を探索"""
        if step == steps:
            # 最終ステップに到達
            if current_pos != origin:
                moves.add(current_pos)
            return

        # 方向リストを決定
        if step == 0:
            directions = first_directions
        else:
            directions = next_directions_fn(first_dir)

        for dx, dy in directions:
            nx, ny = current_pos[0] + dx, current_pos[1] + dy
            if not board.is_valid(nx, ny):
                continue
            if board.has_ally(nx, ny, player):
                continue

            # 途中で止まれる場合、現在位置を候補に追加
            if can_stop_early and step >= 0 and (nx, ny) != origin:
                moves.add((nx, ny))

            # 次のステップへ
            new_first_dir = (dx, dy) if step == 0 else first_dir
            dfs((nx, ny), step + 1, new_first_dir)

    dfs(pos, 0, None)
    return list(moves)


def shoot_targets(pos, board, player, shoot_range, penetrate=False,
                  penetrate_block=None, immune=None, min_range=None):
    """射撃可能な対象を取得

    Args:
        pos: 現在位置 (x, y)
        board: 盤面
        player: プレイヤー (0 or 1)
        shoot_range: 射程
        penetrate: 貫通するか
        penetrate_block: 貫通を止める駒IDリスト
        immune: 射撃無効な駒IDリスト
        min_range: 駒ID -> 最小射程 の辞書

    Returns:
        射撃可能な位置のリスト [(x, y), ...]
    """
    if immune is None:
        immune = []
    if penetrate_block is None:
        penetrate_block = []
    if min_range is None:
        min_range = {}

    x, y = pos
    targets = []

    # 8方向
    directions = [
        (0, 1), (0, -1), (1, 0), (-1, 0),
        (1, 1), (-1, 1), (1, -1), (-1, -1),
    ]

    for dx, dy in directions:
        blocked = False
        for dist in range(1, shoot_range + 1):
            nx, ny = x + dx * dist, y + dy * dist
            if not board.is_valid(nx, ny):
                break

            piece = board.get(nx, ny)
            if piece is None:
                continue

            piece_id, piece_player = piece

            # 味方は射れない
            if piece_player == player:
                if not penetrate:
                    break
                # 貫通なら味方を飛び越えて射撃可能
                continue

            # 敵駒
            if blocked:
                continue  # すでにブロックされている

            # 最小射程チェック
            if piece_id in min_range and dist < min_range[piece_id]:
                if not penetrate:
                    break
                continue

            # 射撃無効チェック
            if piece_id in immune:
                if not penetrate:
                    break
                # immune駒がpenetrate_blockでもある場合、貫通をブロック
                if piece_id in penetrate_block:
                    blocked = True
                continue

            # 射撃可能
            targets.append((nx, ny))

            # 貫通判定
            if not penetrate:
                break
            if piece_id in penetrate_block:
                blocked = True

    return targets


def area_kill_targets(pos, board, player):
    """周囲8マスの全駒（敵味方問わず）を取得

    Args:
        pos: 現在位置 (x, y)
        board: 盤面
        player: プレイヤー (0 or 1) - 未使用だが統一のため

    Returns:
        周囲の駒がある位置のリスト [(x, y), ...]
    """
    x, y = pos
    targets = []
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if board.is_valid(nx, ny) and board.get(nx, ny) is not None:
                targets.append((nx, ny))
    return targets

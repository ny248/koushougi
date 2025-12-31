"""移動ルールの処理"""

from typing import Optional
from backend.domain.board import Board
from backend.domain.game_state import GameState
from backend.domain.piece_registry import get_piece


def get_legal_moves(state: GameState, pos: tuple[int, int]) -> list[tuple[int, int]]:
    """指定位置の駒の合法手を取得

    Args:
        state: ゲーム状態
        pos: 駒の位置

    Returns:
        合法手のリスト [(x, y), ...]
    """
    x, y = pos
    piece_data = state.board.get(x, y)
    if piece_data is None:
        return []

    piece_id, player = piece_data
    if player != state.current_player:
        return []  # 自分の駒でない

    piece = get_piece(piece_id)
    moves = piece.get_moves(pos, state.board, player)

    # 駒取り制限を適用
    filtered_moves = []
    for move in moves:
        if _can_capture_at(state, piece_id, player, move):
            filtered_moves.append(move)

    return filtered_moves


def _can_capture_at(state: GameState, piece_id: int, player: int, to_pos: tuple[int, int]) -> bool:
    """指定位置で駒を取れるか判定

    Args:
        state: ゲーム状態
        piece_id: 移動する駒のID
        player: プレイヤー
        to_pos: 移動先

    Returns:
        移動可能ならTrue
    """
    target = state.board.get(to_pos[0], to_pos[1])
    if target is None:
        return True  # 空きマスには移動可能

    target_id, target_player = target
    if target_player == player:
        return False  # 味方は取れない

    piece = get_piece(piece_id)
    target_piece = get_piece(target_id)

    # 取れない駒チェック (no_capture)
    restriction = piece.get_capture_restriction()
    if target_id in restriction:
        return False

    # 取れる駒フィルタ (only_capture)
    capture_filter = piece.get_capture_filter()
    if capture_filter is not None and target_id not in capture_filter:
        return False

    # この駒を取れない駒チェック (no_captured_by)
    immunity = target_piece.get_capture_immunity()
    if piece_id in immunity:
        return False

    return True


def execute_move(state: GameState, from_pos: tuple[int, int],
                 to_pos: tuple[int, int]) -> dict:
    """移動を実行

    Args:
        state: ゲーム状態（変更される）
        from_pos: 移動元
        to_pos: 移動先

    Returns:
        結果情報 {
            "captured": 取った駒ID or None,
            "path_kills": 経路上で取った駒のリスト,
            "after_effect": 移動後効果（射撃など）
        }
    """
    result = {
        "captured": None,
        "path_kills": [],
        "after_effect": None,
    }

    fx, fy = from_pos
    tx, ty = to_pos

    piece_data = state.board.get(fx, fy)
    if piece_data is None:
        raise ValueError(f"No piece at {from_pos}")

    piece_id, player = piece_data
    piece = get_piece(piece_id)

    # 経路上の敵を取る（霹靂、招揺用）
    path_kills = piece.get_path_kills(from_pos, state.board, player, to_pos)
    for kill_pos in path_kills:
        killed_piece = state.board.get(kill_pos[0], kill_pos[1])
        if killed_piece:
            state.board.remove(kill_pos[0], kill_pos[1])
            result["path_kills"].append((kill_pos, killed_piece[0]))

    # 移動先の敵を取る
    target = state.board.get(tx, ty)
    if target is not None:
        target_id, _ = target
        result["captured"] = target_id

    # 駒を移動
    state.board.remove(fx, fy)
    state.board.set(tx, ty, piece_id, player)

    # 移動後効果（射撃、毒火など）
    after_effect = piece.after_move(state, from_pos, to_pos, player)
    if after_effect:
        result["after_effect"] = after_effect

    return result


def execute_shoot(state: GameState, shooter_pos: tuple[int, int],
                  targets: list[tuple[int, int]], player: int) -> list[tuple[tuple[int, int], int]]:
    """射撃を実行

    Args:
        state: ゲーム状態
        shooter_pos: 射撃する駒の位置
        targets: 射撃対象の位置リスト
        player: プレイヤー

    Returns:
        取った駒のリスト [(位置, 駒ID), ...]
    """
    killed = []
    for target_pos in targets:
        piece = state.board.get(target_pos[0], target_pos[1])
        if piece and piece[1] != player:  # 敵駒のみ
            state.board.remove(target_pos[0], target_pos[1])
            killed.append((target_pos, piece[0]))
    return killed


def execute_area_kill(state: GameState, pos: tuple[int, int],
                      targets: list[tuple[int, int]], player: int) -> list[tuple[tuple[int, int], int]]:
    """周囲破壊を実行（毒火用）

    Args:
        state: ゲーム状態
        pos: 毒火の位置
        targets: 破壊対象の位置リスト
        player: プレイヤー

    Returns:
        取った駒のリスト [(位置, 駒ID), ...]
    """
    killed = []
    for target_pos in targets:
        piece = state.board.get(target_pos[0], target_pos[1])
        if piece:
            # 敵味方問わず破壊
            state.board.remove(target_pos[0], target_pos[1])
            killed.append((target_pos, piece[0]))
    return killed


def check_revert_all(state: GameState) -> list[tuple[tuple[int, int], int, int]]:
    """全駒の成り戻りをチェック

    Returns:
        成り戻る駒のリスト [(pos, old_id, new_id), ...]
    """
    reverts = []
    for x in range(19):
        for y in range(19):
            piece_data = state.board.get(x, y)
            if piece_data is None:
                continue

            piece_id, player = piece_data
            piece = get_piece(piece_id)

            revert_to = piece.check_revert(state, (x, y), player)
            if revert_to is not None:
                reverts.append(((x, y), piece_id, revert_to))

    # 成り戻り実行
    for pos, old_id, new_id in reverts:
        state.board.set(pos[0], pos[1], new_id, state.board.get(pos[0], pos[1])[1])

    return reverts


def end_turn(state: GameState) -> None:
    """ターン終了処理

    - 手番交代
    - 成り戻りチェック
    """
    state.switch_player()
    check_revert_all(state)

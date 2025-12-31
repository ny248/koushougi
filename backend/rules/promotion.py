"""成りルールの処理"""

from typing import Optional
from backend.domain.game_state import GameState
from backend.domain.piece_registry import get_piece


# 特定駒を取った時に成れる条件
# 1路しか進めない駒が力士/龍驤/招揺/霹靂を取ると成る
ONE_STEP_PIECES = [4, 19, 22, 24, 25, 26, 28, 30, 14, 15, 16]  # 親兵,護兵,仏狼機,弓,弩,砲,歩兵,牌,中軍,鼓,旗
STRONG_PIECES = [5, 48, 47, 46]  # 力士,龍驤,招揺,霹靂

# 将/中軍/旗/鼓を取ると成る
BOSS_PIECES = [1, 14, 16, 15]  # 将,中軍,旗,鼓

# 馬兵が仏狼機を取ると成る
UMAHE_ID = 27
BUTSUROUKI_ID = 22


def can_promote(state: GameState, from_pos: tuple[int, int],
                to_pos: tuple[int, int], captured_piece: Optional[int],
                player: int) -> bool:
    """成れるかどうか判定

    Args:
        state: ゲーム状態
        from_pos: 移動元
        to_pos: 移動先
        captured_piece: 取った駒ID（なければNone）
        player: プレイヤー

    Returns:
        成れるならTrue
    """
    piece_data = state.board.get(to_pos[0], to_pos[1])
    if piece_data is None:
        return False

    piece_id, piece_player = piece_data
    if piece_player != player:
        return False

    piece = get_piece(piece_id)

    # 成り先がない駒は成れない
    if piece.promotes_to is None:
        return False

    # 駒固有の成り判定（高道生存チェックなど）
    if not piece.can_promote(state, from_pos, to_pos, captured_piece, player):
        return False

    # 特定駒を取った時の成り
    if captured_piece is not None:
        # 将/中軍/旗/鼓を取ると成る
        if captured_piece in BOSS_PIECES:
            return True

        # 1路駒が力士/龍驤/招揺/霹靂を取ると成る
        if piece_id in ONE_STEP_PIECES and captured_piece in STRONG_PIECES:
            return True

        # 馬兵が仏狼機を取ると成る
        if piece_id == UMAHE_ID and captured_piece == BUTSUROUKI_ID:
            return True

    return True  # 敵陣での成りは駒のcan_promoteで判定済み


def execute_promotion(state: GameState, pos: tuple[int, int]) -> Optional[int]:
    """成りを実行

    Args:
        state: ゲーム状態
        pos: 成る駒の位置

    Returns:
        成り先の駒ID（成らなければNone）
    """
    piece_data = state.board.get(pos[0], pos[1])
    if piece_data is None:
        return None

    piece_id, player = piece_data
    piece = get_piece(piece_id)

    if piece.promotes_to is None:
        return None

    # 成りを実行（is_promoted=Trueでセット）
    state.board.set(pos[0], pos[1], piece.promotes_to, player, is_promoted=True)
    return piece.promotes_to


def check_triggered_promotions(state: GameState, promoted_piece_id: int,
                               player: int) -> list[tuple[tuple[int, int], int, int]]:
    """連鎖成りをチェック

    記室が軍師に成ると、前衝と後衝も成る

    Args:
        state: ゲーム状態
        promoted_piece_id: 成った駒のID
        player: プレイヤー

    Returns:
        連鎖で成った駒のリスト [(pos, old_id, new_id), ...]
    """
    result = []

    # 記室(2) -> 軍師(36) の場合、前衝(12)と後衝(13)も成る
    if promoted_piece_id == 36:  # 軍師
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data is None:
                    continue

                pid, p = piece_data
                if p != player:
                    continue

                # 前衝(12) -> 天網(42)
                if pid == 12:
                    state.board.set(x, y, 42, player, is_promoted=True)
                    result.append(((x, y), 12, 42))

                # 後衝(13) -> 地網(43)
                if pid == 13:
                    state.board.set(x, y, 43, player, is_promoted=True)
                    result.append(((x, y), 13, 43))

        # 敵の毒火(41)を破壊
        enemy = 1 - player
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[0] == 41 and piece_data[1] == enemy:
                    state.board.remove(x, y)
                    state.captured.add(player, 41)

    return result

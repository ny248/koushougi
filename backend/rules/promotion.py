"""成りルールの処理

成り条件（GAMERULE.mdより）:
1. 敵陣に入る/内で移動する（駒固有のcan_promoteで判定）
2. 将/中軍/旗/鼓を取ると成る（全駒共通）
3. 1路しか進めない駒が力士/龍驤/招揺/霹靂を取ると成る
4. 馬兵が仏狼機を取ると天馬に成る
"""

from typing import Optional
from backend.domain.game_state import GameState
from backend.domain.piece_registry import get_piece

# === 駒ID定数 ===
# ルール判定に必要な駒IDを明示的に定義

# 王将クラス（取ると成れる）
SHOU_ID = 1       # 将
CHUUGUN_ID = 14   # 中軍
HATA_ID = 16      # 旗
TSUZUMI_ID = 15   # 鼓

# 強力駒（1路駒がこれを取ると成れる）
RIKISHI_ID = 5    # 力士
RYUUJOU_ID = 48   # 龍驤
SHOUYOU_ID = 47   # 招揺
HEKIREKI_ID = 46  # 霹靂

# 特殊成り条件
UMAHE_ID = 27         # 馬兵
BUTSUROUKI_ID = 22    # 仏狼機

# 連鎖成り関連
GUNSHI_ID = 36        # 軍師（記室の成り）
ZENSHOU_ID = 12       # 前衝
KOUSHOU_ID = 13       # 後衝
TENMOU_ID = 42        # 天網（前衝の成り）
CHIMOU_ID = 43        # 地網（後衝の成り）
DOKUKA_ID = 41        # 毒火（軍師成りで破壊される）

# === ルール用定数 ===

# 将/中軍/旗/鼓を取ると成る（全駒共通）
BOSS_PIECES = [SHOU_ID, CHUUGUN_ID, HATA_ID, TSUZUMI_ID]

# 力士/龍驤/招揺/霹靂（1路駒がこれを取ると成る）
STRONG_PIECES = [RIKISHI_ID, RYUUJOU_ID, SHOUYOU_ID, HEKIREKI_ID]

# 1路しか進めない駒（強力駒を取ると成れる）
# 親兵(4), 護兵(19), 仏狼機(22), 弓(24), 弩(25), 砲(26), 歩兵(28), 牌(30), 中軍(14), 鼓(15), 旗(16)
ONE_STEP_PIECES = [4, 19, 22, 24, 25, 26, 28, 30, CHUUGUN_ID, TSUZUMI_ID, HATA_ID]


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

    # 記室 -> 軍師 の場合、前衝と後衝も成る
    if promoted_piece_id == GUNSHI_ID:
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data is None:
                    continue

                pid, p = piece_data
                if p != player:
                    continue

                # 前衝 -> 天網
                if pid == ZENSHOU_ID:
                    state.board.set(x, y, TENMOU_ID, player, is_promoted=True)
                    result.append(((x, y), ZENSHOU_ID, TENMOU_ID))

                # 後衝 -> 地網
                if pid == KOUSHOU_ID:
                    state.board.set(x, y, CHIMOU_ID, player, is_promoted=True)
                    result.append(((x, y), KOUSHOU_ID, CHIMOU_ID))

        # 敵の毒火を破壊
        enemy = 1 - player
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[0] == DOKUKA_ID and piece_data[1] == enemy:
                    state.board.remove(x, y)

    return result

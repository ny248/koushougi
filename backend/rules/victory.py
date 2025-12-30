"""勝敗判定ルール"""

from typing import Optional
from backend.domain.game_state import GameState


# 駒ID
SHOU_ID = 1      # 将
CHUGUN_ID = 14   # 中軍
SUI_ID = 35      # 帥
HATA_ID = 16     # 旗


def check_victory(state: GameState) -> Optional[int]:
    """勝敗判定

    勝利条件（GAMERULE.mdより）:
    - 敵の「将」と「中軍と旗のどちらか」を取ると勝ち
    - ただし中軍が帥に成っていれば、将と旗が取られても負けにならない

    つまり敵が負ける条件:
    - 帥がいない AND 将がいない AND (中軍がいない OR 旗がいない)

    Args:
        state: ゲーム状態

    Returns:
        勝者のプレイヤー番号（0 or 1）、決着がついていなければNone
    """
    for player in [0, 1]:
        enemy = 1 - player

        # 敵の帥が生きているか（中軍の成り）
        has_sui = state.has_piece_alive(SUI_ID, enemy)

        # 帥がいる場合は負けにならない
        if has_sui:
            continue

        # 敵の将が生きているか
        has_shou = state.has_piece_alive(SHOU_ID, enemy)

        # 敵の中軍が生きているか
        has_chugun = state.has_piece_alive(CHUGUN_ID, enemy)

        # 敵の旗が生きているか
        has_hata = state.has_piece_alive(HATA_ID, enemy)

        # 将がいない場合
        if not has_shou:
            # 中軍と旗の両方が残っていれば負けにならない
            if has_chugun and has_hata:
                continue
            # 中軍または旗のどちらかがいなければ負け
            state.winner = player
            return player

        # 将がいる場合、中軍と旗の両方がいなければ負け
        if not has_chugun and not has_hata:
            state.winner = player
            return player

    return None


def is_game_over(state: GameState) -> bool:
    """ゲームが終了しているか"""
    return state.winner is not None

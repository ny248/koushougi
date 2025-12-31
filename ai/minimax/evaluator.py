"""盤面評価関数"""

from backend.rules.game_engine import GameEngine
from ai.greedy.piece_values import get_piece_value


def evaluate(engine: GameEngine, player: int) -> float:
    """
    盤面の評価値を計算（playerから見た有利さ）

    Args:
        engine: ゲームエンジン
        player: 評価する側のプレイヤー（0=先手, 1=後手）

    Returns:
        評価値（正=有利, 負=不利, ±∞=勝敗確定）
    """
    # 勝敗判定
    if engine.is_game_over:
        if engine.winner == player:
            return float('inf')
        elif engine.winner is not None:
            return float('-inf')
        else:
            return 0  # 引き分け

    # 駒の価値の合計
    score = 0
    for x in range(19):
        for y in range(19):
            piece_data = engine.state.board.get(x, y)
            if piece_data is None:
                continue

            piece_id, owner = piece_data
            value = get_piece_value(piece_id)

            if owner == player:
                score += value
            else:
                score -= value

    return score

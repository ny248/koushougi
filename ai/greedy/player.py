"""貪欲AI - 最も価値の高い駒を取る"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine
from ai.base import BaseAI
from ai.greedy.piece_values import get_piece_value, get_promotion_value


class GreedyPlayer(BaseAI):
    """最も価値の高い駒を取るAI（ε-greedy）"""

    def __init__(self, epsilon: float = 0.05):
        """
        Args:
            epsilon: ランダムに手を選ぶ確率（探索用）
        """
        self.epsilon = epsilon

    def choose_move(self, engine: GameEngine) -> Optional[dict]:
        """最も価値の高い駒を取れる手を選択（ε確率でランダム）"""
        moves = self.get_all_moves(engine)
        if not moves:
            return None

        # ε確率でランダムに選択（探索）
        if random.random() < self.epsilon:
            return random.choice(moves)

        # 各手の評価値を計算
        scored_moves = []
        for move in moves:
            from_pos = move["from"]
            to_pos = move["to"]
            value = 0

            # 駒取りの価値
            target = engine.state.board.get(to_pos[0], to_pos[1])
            if target:
                target_id, _ = target
                value += get_piece_value(target_id)

            # 成りの価値（成った後の価値 - 成る前の価値）
            if move.get("promote"):
                piece_data = engine.state.board.get(from_pos[0], from_pos[1])
                if piece_data:
                    piece_id, _ = piece_data
                    value += get_promotion_value(piece_id)

            scored_moves.append((value, move))

        # 最高価値の手を抽出
        max_value = max(v for v, _ in scored_moves)
        best_moves = [m for v, m in scored_moves if v == max_value]

        # 同価値なら成りを優先
        promoting_moves = [m for m in best_moves if m.get("promote")]
        if promoting_moves:
            return random.choice(promoting_moves)

        return random.choice(best_moves)

    def choose_shoot(self, engine: GameEngine, targets: list[tuple[int, int]]) -> Optional[tuple[int, int]]:
        """最も価値の高い駒を射撃"""
        if not targets:
            return None

        # 射撃対象の価値を評価
        scored_targets = []
        for pos in targets:
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                piece_id, _ = target
                value = get_piece_value(piece_id)
                scored_targets.append((value, pos))

        if not scored_targets:
            return None

        # 最高価値のターゲットを選択
        max_value = max(v for v, _ in scored_targets)

        # 価値が低すぎる場合はスキップ（歩兵以下）
        if max_value < 20:
            return None

        best_targets = [p for v, p in scored_targets if v == max_value]
        return random.choice(best_targets)

"""貪欲AI - 最も価値の高い駒を取る（フェーズ分離型）"""

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
        self._best_destination: Optional[tuple[int, int]] = None
        self._should_promote: bool = False

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """最も価値の高い手が打てる駒を選択"""
        movable = engine.get_movable_pieces()
        if not movable:
            return (0, 0)  # フェールセーフ

        # ε確率でランダム
        if random.random() < self.epsilon:
            piece = random.choice(movable)
            # ランダムな移動先も決める
            engine.select_piece(piece)
            dests = engine.get_legal_destinations()
            engine.cancel_piece_selection()
            if dests:
                self._best_destination = random.choice(dests)
                self._should_promote = random.choice([True, False])
            return piece

        # 全ての駒×移動先の組み合わせを評価
        best_value = float('-inf')
        best_piece = movable[0]
        best_dest = None
        best_promote = False

        for piece_pos in movable:
            engine.select_piece(piece_pos)
            destinations = engine.get_legal_destinations()
            engine.cancel_piece_selection()

            piece_data = engine.state.board.get(piece_pos[0], piece_pos[1])
            if not piece_data:
                continue
            piece_id, _ = piece_data

            for to_pos in destinations:
                # 駒取りの価値
                value = 0
                target = engine.state.board.get(to_pos[0], to_pos[1])
                if target:
                    target_id, _ = target
                    value += get_piece_value(target_id)

                # 成りの価値
                promo_value = get_promotion_value(piece_id)
                value_with_promo = value + promo_value if promo_value > 0 else value

                if value_with_promo > best_value:
                    best_value = value_with_promo
                    best_piece = piece_pos
                    best_dest = to_pos
                    best_promote = (promo_value > 0)
                elif value > best_value:
                    best_value = value
                    best_piece = piece_pos
                    best_dest = to_pos
                    best_promote = False

        self._best_destination = best_dest
        self._should_promote = best_promote
        return best_piece

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """事前に計算した最適な移動先を返す"""
        if self._best_destination:
            return self._best_destination

        # フォールバック: ランダム
        dests = engine.get_legal_destinations()
        return random.choice(dests) if dests else (0, 0)

    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうか（基本的に成る）"""
        return self._should_promote or True  # Greedyは基本的に成る

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """最も価値の高い駒を射撃"""
        targets = engine.get_shoot_targets()
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

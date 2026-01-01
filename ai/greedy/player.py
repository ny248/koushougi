"""貪欲AI - 最も価値の高い駒を取る（フェーズ分離型）"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine
from ai.base import BaseAI
from ai.greedy.piece_values import get_piece_value, get_promotion_value, select_best_shoot_target


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
        return select_best_shoot_target(targets, engine.state.board)

    def choose_next_step(self, engine: GameEngine) -> tuple[int, int]:
        """最も価値の高い駒を取れるステップを選択"""
        options = engine.get_next_step_options()
        if not options:
            return (0, 0)

        # 敵を取れるステップを優先
        best_option = options[0]
        best_value = 0
        for pos in options:
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                target_id, _ = target
                value = get_piece_value(target_id)
                if value > best_value:
                    best_value = value
                    best_option = pos

        return best_option

    def choose_stop(self, engine: GameEngine) -> bool:
        """停止するか選択: 残りステップで取れる駒がなければ停止"""
        if not engine.can_stop_now():
            return False

        # 次のステップで取れる駒があるか確認
        options = engine.get_next_step_options()
        for pos in options:
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                return False  # 取れる駒があるなら続行

        return True  # 取れる駒がないなら停止

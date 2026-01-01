"""Minimax AI with Alpha-Beta Pruning（状態遷移単位）"""

import random
from typing import Optional, Union
from backend.rules.game_engine import GameEngine, GamePhase
from ai.base import BaseAI
from ai.minimax.evaluator import evaluate
from ai.greedy.piece_values import get_piece_value, select_best_shoot_target


class MinimaxPlayer(BaseAI):
    """Minimax探索を行うAI

    設計原則:
    - 探索は状態遷移単位で行う
    - 各フェーズで可能な選択肢を列挙し、1つずつ適用→評価→undo
    - 1状態遷移 = 1棋譜エントリ = 1回のundo
    """

    def __init__(self, depth: int = 3, epsilon: float = 0.0, max_moves: int = 20):
        """
        Args:
            depth: 探索の深さ（状態遷移の回数）
            epsilon: ランダムに手を選ぶ確率
            max_moves: 各深さで探索する最大選択肢数（枝刈り）
        """
        self.depth = depth
        self.epsilon = epsilon
        self.max_moves = max_moves
        # 探索結果をキャッシュ（1ターン内で使用）
        self._cached_plan: list[dict] = []

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """Minimax探索で最善の駒を選択"""
        if engine.phase != GamePhase.PIECE_SELECT:
            raise ValueError("Not in PIECE_SELECT phase")

        # ε確率でランダム
        if self.epsilon > 0 and random.random() < self.epsilon:
            movable = engine.get_movable_pieces()
            if movable:
                return random.choice(movable)

        # 探索して最善のアクションを決定
        best_action = self._search_best_action(engine)
        if best_action and best_action.get("type") == "select_piece":
            return best_action["pos"]

        # フォールバック
        movable = engine.get_movable_pieces()
        return movable[0] if movable else (0, 0)

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """移動先を選択"""
        if engine.phase != GamePhase.DEST_SELECT:
            raise ValueError("Not in DEST_SELECT phase")

        best_action = self._search_best_action(engine)
        if best_action and best_action.get("type") == "select_destination":
            return best_action["pos"]

        # フォールバック
        dests = engine.get_legal_destinations()
        return random.choice(dests) if dests else (0, 0)

    def choose_next_step(self, engine: GameEngine) -> tuple[int, int]:
        """マルチステップの次の移動先を選択"""
        if engine.phase != GamePhase.MULTI_STEP_MOVE:
            raise ValueError("Not in MULTI_STEP_MOVE phase")

        best_action = self._search_best_action(engine)
        if best_action and best_action.get("type") == "select_next_step":
            return best_action["pos"]

        # フォールバック: 敵を取れるステップを優先
        options = engine.get_next_step_options()
        if not options:
            return (0, 0)

        best_option = options[0]
        best_value = -1
        for pos in options:
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                value = get_piece_value(target[0])
                if value > best_value:
                    best_value = value
                    best_option = pos

        return best_option

    def choose_stop(self, engine: GameEngine) -> bool:
        """停止するか選択"""
        if engine.phase != GamePhase.MULTI_STEP_MOVE:
            return False

        if not engine.can_stop_now():
            return False

        best_action = self._search_best_action(engine)
        if best_action:
            return best_action.get("type") == "stop_move"

        # フォールバック: 取れる駒がなければ停止
        options = engine.get_next_step_options()
        for pos in options:
            if engine.state.board.get(pos[0], pos[1]):
                return False
        return True

    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうか"""
        if engine.phase != GamePhase.PROMOTION:
            return False

        best_action = self._search_best_action(engine)
        if best_action and best_action.get("type") == "decide_promotion":
            return best_action["promote"]

        # フォールバック: 常に成る
        return True

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """射撃先を選択"""
        if engine.phase != GamePhase.SHOOTING:
            return None

        best_action = self._search_best_action(engine)
        if best_action:
            if best_action.get("type") == "shoot":
                return best_action["target"]
            elif best_action.get("type") == "skip_shoot":
                return None

        # フォールバック: 最高価値を選択
        targets = engine.get_shoot_targets()
        return select_best_shoot_target(targets, engine.state.board)

    def _search_best_action(self, engine: GameEngine) -> Optional[dict]:
        """現在のフェーズで最善のアクションを探索"""
        actions = self._get_actions(engine)
        if not actions:
            return None

        player = engine.current_player
        best_actions = []
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')

        # アクションをスコアでソート
        scored_actions = self._order_actions(engine, actions)[:self.max_moves]

        for action in scored_actions:
            # アクションを適用
            if not self._apply_action(engine, action):
                continue

            # Minimax探索
            value = self._minimax(engine, self.depth - 1, alpha, beta, False, player)

            # 取り消し
            self._undo_action(engine, action)

            if value > best_value:
                best_value = value
                best_actions = [action]
            elif value == best_value:
                best_actions.append(action)

            alpha = max(alpha, value)

        return random.choice(best_actions) if best_actions else None

    def _minimax(self, engine: GameEngine, depth: int, alpha: float, beta: float,
                 maximizing: bool, original_player: int) -> float:
        """Minimax with Alpha-Beta Pruning（状態遷移単位）"""
        if depth == 0 or engine.is_game_over:
            return evaluate(engine, original_player)

        actions = self._get_actions(engine)
        if not actions:
            return evaluate(engine, original_player)

        scored_actions = self._order_actions(engine, actions)[:self.max_moves]

        if maximizing:
            value = float('-inf')
            for action in scored_actions:
                if not self._apply_action(engine, action):
                    continue

                value = max(value, self._minimax(engine, depth - 1, alpha, beta, False, original_player))
                self._undo_action(engine, action)

                alpha = max(alpha, value)
                if beta <= alpha:
                    break

            return value
        else:
            value = float('inf')
            for action in scored_actions:
                if not self._apply_action(engine, action):
                    continue

                value = min(value, self._minimax(engine, depth - 1, alpha, beta, True, original_player))
                self._undo_action(engine, action)

                beta = min(beta, value)
                if beta <= alpha:
                    break

            return value

    def _get_actions(self, engine: GameEngine) -> list[dict]:
        """現在のフェーズで可能なアクションを取得"""
        phase = engine.phase

        if phase == GamePhase.PIECE_SELECT:
            return self._get_piece_select_actions(engine)
        elif phase == GamePhase.DEST_SELECT:
            return self._get_dest_select_actions(engine)
        elif phase == GamePhase.MULTI_STEP_MOVE:
            return self._get_multi_step_actions(engine)
        elif phase == GamePhase.PROMOTION:
            return self._get_promotion_actions(engine)
        elif phase == GamePhase.SHOOTING:
            return self._get_shooting_actions(engine)
        else:
            return []

    def _get_piece_select_actions(self, engine: GameEngine) -> list[dict]:
        """駒選択フェーズのアクション"""
        actions = []
        for pos in engine.get_movable_pieces():
            actions.append({"type": "select_piece", "pos": pos})
        return actions

    def _get_dest_select_actions(self, engine: GameEngine) -> list[dict]:
        """移動先選択フェーズのアクション"""
        actions = []
        for pos in engine.get_legal_destinations():
            actions.append({"type": "select_destination", "pos": pos})
        return actions

    def _get_multi_step_actions(self, engine: GameEngine) -> list[dict]:
        """マルチステップフェーズのアクション"""
        actions = []

        # 停止可能なら停止アクションを追加
        if engine.can_stop_now():
            actions.append({"type": "stop_move"})

        # 次のステップの選択肢
        for pos in engine.get_next_step_options():
            actions.append({"type": "select_next_step", "pos": pos})

        return actions

    def _get_promotion_actions(self, engine: GameEngine) -> list[dict]:
        """成り判断フェーズのアクション"""
        return [
            {"type": "decide_promotion", "promote": True},
            {"type": "decide_promotion", "promote": False},
        ]

    def _get_shooting_actions(self, engine: GameEngine) -> list[dict]:
        """射撃フェーズのアクション"""
        actions = []

        # スキップ
        actions.append({"type": "skip_shoot"})

        # 各ターゲットへの射撃
        for target in engine.get_shoot_targets():
            actions.append({"type": "shoot", "target": target})

        return actions

    def _apply_action(self, engine: GameEngine, action: dict) -> bool:
        """アクションを適用

        Note: select_pieceは棋譜を記録しない（盤面を変えない）ので、
        undoではなくcancel_piece_selectionを使う
        """
        action_type = action.get("type")

        if action_type == "select_piece":
            return engine.select_piece(action["pos"])

        elif action_type == "select_destination":
            result = engine.select_destination(action["pos"])
            return result.success

        elif action_type == "select_next_step":
            result = engine.select_next_step(action["pos"])
            return result.success

        elif action_type == "stop_move":
            result = engine.stop_move()
            return result.success

        elif action_type == "decide_promotion":
            result = engine.decide_promotion(action["promote"])
            return result.success

        elif action_type == "shoot":
            result = engine.shoot(action["target"])
            return result.success

        elif action_type == "skip_shoot":
            result = engine.skip_shoot()
            return result.success

        return False

    def _undo_action(self, engine: GameEngine, action: dict) -> bool:
        """アクションを取り消す

        全てのアクションは棋譜に記録されるため、undoで取り消せる
        """
        return engine.undo()

    def _order_actions(self, engine: GameEngine, actions: list[dict]) -> list[dict]:
        """アクションをスコアでソート（枝刈り効率化）"""
        scored = []
        for action in actions:
            score = self._estimate_action_value(engine, action)
            scored.append((score, action))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [a for _, a in scored]

    def _estimate_action_value(self, engine: GameEngine, action: dict) -> float:
        """アクションの推定価値（ヒューリスティック）"""
        action_type = action.get("type")

        if action_type == "select_piece":
            # 動かす駒自体の価値は低い（何を取れるかが重要）
            return 0

        elif action_type == "select_destination":
            pos = action["pos"]
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                return get_piece_value(target[0])
            return 0

        elif action_type == "select_next_step":
            pos = action["pos"]
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                return get_piece_value(target[0])
            return 0

        elif action_type == "stop_move":
            return -10  # 停止は低優先度

        elif action_type == "decide_promotion":
            return 50 if action["promote"] else 0

        elif action_type == "shoot":
            target_pos = action["target"]
            target = engine.state.board.get(target_pos[0], target_pos[1])
            if target:
                return get_piece_value(target[0])
            return 0

        elif action_type == "skip_shoot":
            return -5  # スキップは低優先度

        return 0

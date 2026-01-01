"""Minimax AI（GameStateコピー方式）"""

import random
import logging
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import GameState
from backend.domain.kifu import KifuMode
from ai.base import BaseAI
from ai.minimax.evaluator import evaluate
from ai.greedy.piece_values import get_piece_value, select_best_shoot_target

logger = logging.getLogger('MinimaxPlayer')


class MinimaxPlayer(BaseAI):
    """Minimax探索を行うAI

    設計原則:
    - GameStateをコピーして探索（undoは不要）
    - 各フェーズで可能な選択肢を列挙し、コピーに対して適用→評価
    - 元のGameStateは変更しない
    """

    def __init__(self, depth: int = 8, max_moves: int = 50, epsilon: float = 0.0):
        """
        Args:
            depth: 探索の深さ（状態遷移の回数）
            max_moves: 各ノードで探索する最大手数
            epsilon: ランダムに手を選ぶ確率
        """
        self.depth = depth
        self.max_moves = max_moves
        self.epsilon = epsilon

    def play_step(self, engine: GameEngine) -> bool:
        """1状態遷移を処理（探索中はストリーミングを停止）

        BaseAIのplay_stepをオーバーライドし、探索前後でモード切り替えを行う。
        """
        logger.debug(f"play_step開始: player={engine.current_player}, phase={engine.phase}, kifu_mode={engine._kifu_mode}")

        # ε確率でランダム（親クラスのplay_stepを使用）
        if self.epsilon > 0 and random.random() < self.epsilon:
            logger.debug("epsilon: ランダム手を使用")
            return super().play_step(engine)

        # 探索前にモードを保存してNONEに切り替え
        original_mode = engine._kifu_mode
        engine._kifu_mode = KifuMode.NONE

        try:
            # 最善のアクションを探索
            best_action = self._search_best_action(engine)
        finally:
            # モードを復元
            engine._kifu_mode = original_mode

        logger.debug(f"探索結果: best_action={best_action}")

        if not best_action:
            # フォールバック: 親クラスのplay_stepを使用
            logger.warning("best_actionがNone、フォールバック使用")
            return super().play_step(engine)

        # 探索結果のアクションを実行（これはストリーミング有効状態で実行）
        before_player = engine.current_player
        before_phase = engine.phase
        result = self._apply_action(engine, best_action)
        logger.debug(f"_apply_action: ({before_player},{before_phase}) -> ({engine.current_player},{engine.phase}), result={result}")
        return result

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """フォールバック用: ランダムに駒を選択"""
        movable = engine.get_movable_pieces()
        return random.choice(movable) if movable else (0, 0)

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """フォールバック用: ランダムに移動先を選択"""
        dests = engine.get_legal_destinations()
        return random.choice(dests) if dests else (0, 0)

    def choose_next_step(self, engine: GameEngine) -> tuple[int, int]:
        """フォールバック用: 敵を取れるステップを優先"""
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
        """フォールバック用: 取れる駒がなければ停止"""
        if not engine.can_stop_now():
            return False
        options = engine.get_next_step_options()
        for pos in options:
            if engine.state.board.get(pos[0], pos[1]):
                return False
        return True

    def choose_promotion(self, engine: GameEngine) -> bool:
        """フォールバック用: 常に成る"""
        return True

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """フォールバック用: 最高価値を選択"""
        targets = engine.get_shoot_targets()
        return select_best_shoot_target(targets, engine.state.board)

    def _search_best_action(self, engine: GameEngine) -> Optional[dict]:
        """現在のフェーズで最善のアクションを探索

        GameStateをコピーして探索を行う。元のstateは変更しない。
        """
        state = engine.state
        actions = self._get_actions_from_state(state)
        if not actions:
            return None

        player = state.current_player
        best_actions = []
        best_value = float('-inf')

        logger.debug(f"_search_best_action開始: player={player}, phase={state.phase}")

        for action in actions:
            # 状態をコピーして探索用engineを作成
            search_state = state.copy()
            search_engine = GameEngine(state=search_state, kifu_mode=KifuMode.NONE)

            # アクションを適用
            apply_result = self._apply_action(search_engine, action)
            if not apply_result:
                logger.debug(f"  action={action} apply失敗")
                continue

            logger.debug(f"  action={action} apply成功: phase={search_state.phase}")

            # Minimax探索（プレイヤーが変わったかでmaximizingを決定）
            next_maximizing = search_state.current_player == player
            value = self._minimax(search_state, self.depth - 1, next_maximizing, player)

            logger.debug(f"    value={value}")

            if value > best_value:
                best_value = value
                best_actions = [action]
            elif value == best_value:
                best_actions.append(action)

        logger.debug(f"_search_best_action終了: best_value={best_value}")

        return random.choice(best_actions) if best_actions else None

    def _minimax(self, state: GameState, depth: int,
                 maximizing: bool, original_player: int) -> float:
        """Minimax（GameStateコピー方式）

        stateは呼び出し元で既にコピーされているので、直接変更可能。
        """
        # 終了条件
        if depth == 0 or state.winner is not None:
            return self._evaluate_state(state, original_player)

        actions = self._get_actions_from_state(state)
        if not actions:
            return self._evaluate_state(state, original_player)

        if maximizing:
            value = float('-inf')
            for action in actions:
                # 状態をコピー
                child_state = state.copy()
                child_engine = GameEngine(state=child_state, kifu_mode=KifuMode.NONE)

                if not self._apply_action(child_engine, action):
                    continue

                # プレイヤーが変わったときだけmaximizingを切り替える
                next_maximizing = child_state.current_player == original_player
                value = max(value, self._minimax(child_state, depth - 1, next_maximizing, original_player))

            return value
        else:
            value = float('inf')
            for action in actions:
                # 状態をコピー
                child_state = state.copy()
                child_engine = GameEngine(state=child_state, kifu_mode=KifuMode.NONE)

                if not self._apply_action(child_engine, action):
                    continue

                # プレイヤーが変わったときだけmaximizingを切り替える
                next_maximizing = child_state.current_player == original_player
                value = min(value, self._minimax(child_state, depth - 1, next_maximizing, original_player))

            return value

    def _evaluate_state(self, state: GameState, player: int) -> float:
        """GameStateを評価"""
        # 一時的にengineを作成して評価
        temp_engine = GameEngine(state=state, kifu_mode=KifuMode.NONE)
        return evaluate(temp_engine, player)

    def _get_actions(self, engine: GameEngine) -> list[dict]:
        """現在のフェーズで可能なアクションを取得（engine版）"""
        return self._get_actions_from_state(engine.state)

    def _get_actions_from_state(self, state: GameState) -> list[dict]:
        """GameStateから可能なアクションを取得"""
        phase = state.phase

        if phase == GamePhase.PIECE_SELECT:
            return self._get_piece_select_actions_from_state(state)
        elif phase == GamePhase.DEST_SELECT:
            return self._get_dest_select_actions_from_state(state)
        elif phase == GamePhase.MULTI_STEP_MOVE:
            return self._get_multi_step_actions_from_state(state)
        elif phase == GamePhase.PROMOTION:
            return self._get_promotion_actions_from_state(state)
        elif phase == GamePhase.SHOOTING:
            return self._get_shooting_actions_from_state(state)
        else:
            return []

    def _get_piece_select_actions(self, engine: GameEngine) -> list[dict]:
        """駒選択フェーズのアクション（engine版）"""
        return self._get_piece_select_actions_from_state(engine.state)

    def _get_piece_select_actions_from_state(self, state: GameState) -> list[dict]:
        """駒選択フェーズのアクション"""
        from backend.rules import movement
        actions = []
        player = state.current_player
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[1] == player:
                    moves = movement.get_legal_moves(state, (x, y))
                    if moves:
                        actions.append({"type": "select_piece", "pos": (x, y)})
        return actions

    def _get_dest_select_actions(self, engine: GameEngine) -> list[dict]:
        """移動先選択フェーズのアクション（engine版）"""
        return self._get_dest_select_actions_from_state(engine.state)

    def _get_dest_select_actions_from_state(self, state: GameState) -> list[dict]:
        """移動先選択フェーズのアクション"""
        from backend.rules import movement
        actions = []
        if state.selected_piece:
            for pos in movement.get_legal_moves(state, state.selected_piece):
                actions.append({"type": "select_destination", "pos": pos})
        return actions

    def _get_multi_step_actions(self, engine: GameEngine) -> list[dict]:
        """マルチステップフェーズのアクション（engine版）"""
        return self._get_multi_step_actions_from_state(engine.state)

    def _get_multi_step_actions_from_state(self, state: GameState) -> list[dict]:
        """マルチステップフェーズのアクション"""
        from backend.domain.piece_registry import get_piece
        actions = []

        if state.multi_step_state is None:
            return actions

        ms_state = state.multi_step_state

        # 停止可能なら停止アクションを追加
        if ms_state.get("can_stop_early", False):
            actions.append({"type": "stop_move"})

        # 次のステップの選択肢
        piece = get_piece(ms_state["piece_id"])
        step_index = piece.get_multi_step_config().total_steps - ms_state["remaining_steps"]
        next_options = piece.get_next_step_options(
            ms_state["current_pos"],
            state.board,
            state.current_player,
            step_index,
            ms_state.get("first_direction")
        )
        for pos in next_options:
            actions.append({"type": "select_next_step", "pos": pos})

        return actions

    def _get_promotion_actions(self, engine: GameEngine) -> list[dict]:
        """成り判断フェーズのアクション（engine版）"""
        return self._get_promotion_actions_from_state(engine.state)

    def _get_promotion_actions_from_state(self, state: GameState) -> list[dict]:
        """成り判断フェーズのアクション"""
        return [
            {"type": "decide_promotion", "promote": True},
            {"type": "decide_promotion", "promote": False},
        ]

    def _get_shooting_actions(self, engine: GameEngine) -> list[dict]:
        """射撃フェーズのアクション（engine版）"""
        return self._get_shooting_actions_from_state(engine.state)

    def _get_shooting_actions_from_state(self, state: GameState) -> list[dict]:
        """射撃フェーズのアクション"""
        actions = []

        # スキップ
        actions.append({"type": "skip_shoot"})

        # 各ターゲットへの射撃
        if state.pending_shoot:
            for target in state.pending_shoot.get("targets", []):
                actions.append({"type": "shoot", "target": target})

        return actions

    def _apply_action(self, engine: GameEngine, action: dict) -> bool:
        """アクションを適用"""
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


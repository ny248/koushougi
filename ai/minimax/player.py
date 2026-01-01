"""Minimax AI（GameStateコピー方式）"""

import random
import logging
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import GameState
from backend.domain.kifu import KifuMode
from backend.domain.action import (
    Action, SelectPieceAction, SelectDestinationAction,
    StopMoveAction, SelectNextStepAction,
    DecidePromotionAction, ShootAction, SkipShootAction
)
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

    def choose_action(self, state: GameState) -> Action:
        """現在の状態から次のアクションを選択"""
        # ε確率でランダム
        if self.epsilon > 0 and random.random() < self.epsilon:
            return self._choose_random_action(state)

        # 最善のアクションを探索
        best_action = self._search_best_action_from_state(state)

        if best_action is None:
            # フォールバック: ランダム
            return self._choose_random_action(state)

        return best_action

    def _choose_random_action(self, state: GameState) -> Action:
        """ランダムにアクションを選択（フォールバック用）"""
        actions = self._get_actions_from_state(state)
        if not actions:
            # どうしようもない場合のデフォルト
            return SelectPieceAction(pos=(0, 0))
        return random.choice(actions)

    def play_step(self, engine: GameEngine) -> bool:
        """1状態遷移を処理（探索中はストリーミングを停止）"""
        logger.debug(f"play_step開始: player={engine.current_player}, phase={engine.phase}")

        if engine.phase == GamePhase.GAME_OVER:
            return False

        # 探索前にモードを保存してNONEに切り替え
        original_mode = engine._kifu_mode
        engine._kifu_mode = KifuMode.NONE

        try:
            action = self.choose_action(engine.state)
        finally:
            engine._kifu_mode = original_mode

        logger.debug(f"探索結果: action={action}")

        result = engine.apply_action(action)
        return result.success

    def _search_best_action_from_state(self, state: GameState) -> Optional[Action]:
        """現在の状態で最善のアクションを探索

        GameStateをコピーして探索を行う。元のstateは変更しない。
        """
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
            result = search_engine.apply_action(action)
            if not result.success:
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

                result = child_engine.apply_action(action)
                if not result.success:
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

                result = child_engine.apply_action(action)
                if not result.success:
                    continue

                # プレイヤーが変わったときだけmaximizingを切り替える
                next_maximizing = child_state.current_player == original_player
                value = min(value, self._minimax(child_state, depth - 1, next_maximizing, original_player))

            return value

    def _evaluate_state(self, state: GameState, player: int) -> float:
        """GameStateを評価"""
        temp_engine = GameEngine(state=state, kifu_mode=KifuMode.NONE)
        return evaluate(temp_engine, player)

    def _get_actions_from_state(self, state: GameState) -> list[Action]:
        """GameStateから可能なアクションを取得"""
        phase = state.phase

        if phase == GamePhase.PIECE_SELECT:
            return self._get_piece_select_actions(state)
        elif phase == GamePhase.DEST_SELECT:
            return self._get_dest_select_actions(state)
        elif phase == GamePhase.MULTI_STEP_MOVE:
            return self._get_multi_step_actions(state)
        elif phase == GamePhase.PROMOTION:
            return self._get_promotion_actions(state)
        elif phase == GamePhase.SHOOTING:
            return self._get_shooting_actions(state)
        else:
            return []

    def _get_piece_select_actions(self, state: GameState) -> list[Action]:
        """駒選択フェーズのアクション"""
        from backend.rules import movement
        actions: list[Action] = []
        player = state.current_player
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[1] == player:
                    moves = movement.get_legal_moves(state, (x, y))
                    if moves:
                        actions.append(SelectPieceAction(pos=(x, y)))
        return actions

    def _get_dest_select_actions(self, state: GameState) -> list[Action]:
        """移動先選択フェーズのアクション"""
        from backend.rules import movement
        actions: list[Action] = []
        if state.selected_piece:
            for pos in movement.get_legal_moves(state, state.selected_piece):
                actions.append(SelectDestinationAction(pos=pos))
        return actions

    def _get_multi_step_actions(self, state: GameState) -> list[Action]:
        """マルチステップフェーズのアクション"""
        from backend.domain.piece_registry import get_piece
        actions: list[Action] = []

        if state.multi_step_state is None:
            return actions

        ms_state = state.multi_step_state

        # 停止可能なら停止アクションを追加
        if ms_state.get("can_stop_early", False):
            actions.append(StopMoveAction())

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
            actions.append(SelectNextStepAction(pos=pos))

        return actions

    def _get_promotion_actions(self, state: GameState) -> list[Action]:
        """成り判断フェーズのアクション"""
        return [
            DecidePromotionAction(promote=True),
            DecidePromotionAction(promote=False),
        ]

    def _get_shooting_actions(self, state: GameState) -> list[Action]:
        """射撃フェーズのアクション"""
        actions: list[Action] = []

        # スキップ
        actions.append(SkipShootAction())

        # 各ターゲットへの射撃
        if state.pending_shoot:
            for target in state.pending_shoot.get("targets", []):
                actions.append(ShootAction(target=target))

        return actions


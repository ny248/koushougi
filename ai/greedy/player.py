"""貪欲AI - 最も価値の高い駒を取る"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import GameState
from backend.domain.action import (
    Action, SelectPieceAction, SelectDestinationAction,
    StopMoveAction, SelectNextStepAction,
    DecidePromotionAction, ShootAction, SkipShootAction
)
from backend.rules import movement
from backend.domain.piece_registry import get_piece
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

    def choose_action(self, state: GameState) -> Action:
        """現在の状態から次のアクションを選択"""
        phase = state.phase

        if phase == GamePhase.PIECE_SELECT:
            return self._choose_piece_action(state)
        elif phase == GamePhase.DEST_SELECT:
            return self._choose_dest_action(state)
        elif phase == GamePhase.MULTI_STEP_MOVE:
            return self._choose_multi_step_action(state)
        elif phase == GamePhase.PROMOTION:
            return self._choose_promotion_action(state)
        elif phase == GamePhase.SHOOTING:
            return self._choose_shoot_action(state)
        else:
            return SelectPieceAction(pos=(0, 0))

    def _choose_piece_action(self, state: GameState) -> Action:
        """最も価値の高い手が打てる駒を選択"""
        player = state.current_player
        movable = []
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[1] == player:
                    moves = movement.get_legal_moves(state, (x, y))
                    if moves:
                        movable.append((x, y))

        if not movable:
            return SelectPieceAction(pos=(0, 0))

        # ε確率でランダム
        if random.random() < self.epsilon:
            piece = random.choice(movable)
            moves = movement.get_legal_moves(state, piece)
            if moves:
                self._best_destination = random.choice(moves)
                self._should_promote = random.choice([True, False])
            return SelectPieceAction(pos=piece)

        # 全ての駒×移動先の組み合わせを評価
        best_value = float('-inf')
        best_piece = movable[0]
        best_dest = None
        best_promote = False

        for piece_pos in movable:
            piece_data = state.board.get(piece_pos[0], piece_pos[1])
            if not piece_data:
                continue
            piece_id, _ = piece_data

            destinations = movement.get_legal_moves(state, piece_pos)

            for to_pos in destinations:
                # 駒取りの価値
                value = 0
                target = state.board.get(to_pos[0], to_pos[1])
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
        return SelectPieceAction(pos=best_piece)

    def _choose_dest_action(self, state: GameState) -> Action:
        """事前に計算した最適な移動先を返す"""
        if self._best_destination:
            return SelectDestinationAction(pos=self._best_destination)

        # フォールバック: ランダム
        if state.selected_piece:
            dests = movement.get_legal_moves(state, state.selected_piece)
            if dests:
                return SelectDestinationAction(pos=random.choice(dests))
        return SelectDestinationAction(pos=(0, 0))

    def _choose_multi_step_action(self, state: GameState) -> Action:
        """最も価値の高い駒を取れるステップを選択"""
        if state.multi_step_state is None:
            return StopMoveAction()

        ms_state = state.multi_step_state

        # 次のステップの選択肢を取得
        piece = get_piece(ms_state["piece_id"])
        step_index = piece.get_multi_step_config().total_steps - ms_state["remaining_steps"]
        options = piece.get_next_step_options(
            ms_state["current_pos"],
            state.board,
            state.current_player,
            step_index,
            ms_state.get("first_direction")
        )

        if not options:
            if ms_state.get("can_stop_early", False):
                return StopMoveAction()
            return SelectNextStepAction(pos=(0, 0))

        # 敵を取れるステップを優先
        best_option = options[0]
        best_value = 0
        has_target = False

        for pos in options:
            target = state.board.get(pos[0], pos[1])
            if target:
                has_target = True
                target_id, _ = target
                value = get_piece_value(target_id)
                if value > best_value:
                    best_value = value
                    best_option = pos

        # 取れる駒がなく、停止可能なら停止
        if not has_target and ms_state.get("can_stop_early", False):
            return StopMoveAction()

        return SelectNextStepAction(pos=best_option)

    def _choose_promotion_action(self, state: GameState) -> Action:
        """成るかどうか（基本的に成る）"""
        return DecidePromotionAction(promote=self._should_promote or True)

    def _choose_shoot_action(self, state: GameState) -> Action:
        """最も価値の高い駒を射撃"""
        if state.pending_shoot:
            targets = state.pending_shoot.get("targets", [])
            best = select_best_shoot_target(targets, state.board)
            if best:
                return ShootAction(target=best)
        return SkipShootAction()

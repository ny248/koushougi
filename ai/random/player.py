"""ランダムAI - ランダムに合法手を選ぶ"""

import random
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


class RandomPlayer(BaseAI):
    """ランダムに手を選ぶAI"""

    def choose_action(self, state: GameState) -> Action:
        """現在の状態からランダムにアクションを選択"""
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
            # フォールバック
            return SelectPieceAction(pos=(0, 0))

    def _choose_piece_action(self, state: GameState) -> Action:
        """ランダムに駒を選択"""
        player = state.current_player
        movable = []
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data and piece_data[1] == player:
                    moves = movement.get_legal_moves(state, (x, y))
                    if moves:
                        movable.append((x, y))

        if movable:
            pos = random.choice(movable)
            return SelectPieceAction(pos=pos)
        return SelectPieceAction(pos=(0, 0))

    def _choose_dest_action(self, state: GameState) -> Action:
        """ランダムに移動先を選択"""
        if state.selected_piece:
            dests = movement.get_legal_moves(state, state.selected_piece)
            if dests:
                pos = random.choice(dests)
                return SelectDestinationAction(pos=pos)
        return SelectDestinationAction(pos=(0, 0))

    def _choose_multi_step_action(self, state: GameState) -> Action:
        """ランダムに次のステップを選択"""
        if state.multi_step_state is None:
            return StopMoveAction()

        ms_state = state.multi_step_state

        # 50%で停止
        if ms_state.get("can_stop_early", False) and random.random() < 0.5:
            return StopMoveAction()

        # 次のステップの選択肢
        piece = get_piece(ms_state["piece_id"])
        step_index = piece.get_multi_step_config().total_steps - ms_state["remaining_steps"]
        options = piece.get_next_step_options(
            ms_state["current_pos"],
            state.board,
            state.current_player,
            step_index,
            ms_state.get("first_direction")
        )

        if options:
            pos = random.choice(options)
            return SelectNextStepAction(pos=pos)
        return StopMoveAction()

    def _choose_promotion_action(self, state: GameState) -> Action:
        """ランダムに成るか選択（50%で成る）"""
        return DecidePromotionAction(promote=random.random() < 0.5)

    def _choose_shoot_action(self, state: GameState) -> Action:
        """ランダムに射撃先を選択（50%でスキップ）"""
        if state.pending_shoot:
            targets = state.pending_shoot.get("targets", [])
            if targets and random.random() < 0.5:
                target = random.choice(targets)
                return ShootAction(target=target)
        return SkipShootAction()

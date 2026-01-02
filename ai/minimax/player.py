"""Minimax AI（undo方式 + 反復深化 + Transposition Table）"""

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
from ai.minimax.transposition_table import TranspositionTable, TTEntryType

logger = logging.getLogger('MinimaxPlayer')


class MinimaxPlayer(BaseAI):
    """Minimax探索を行うAI

    設計原則:
    - 探索開始時に1回だけstate.copy()
    - 探索中はapply_action→再帰→undoで状態を戻す
    - 反復深化で浅い深さから順に探索し、ムーブオーダリングを改善
    - Transposition Tableで同一局面の再計算を防ぐ
    """

    def __init__(self, depth: int = 8, max_moves: int = 50, epsilon: float = 0.0,
                 use_iterative_deepening: bool = True, use_tt: bool = True,
                 tt_size: int = 1 << 20):
        """
        Args:
            depth: 探索の深さ（状態遷移の回数）
            max_moves: 各ノードで探索する最大手数（未使用、将来用）
            epsilon: ランダムに手を選ぶ確率
            use_iterative_deepening: 反復深化を使うか
            use_tt: Transposition Tableを使うか
            tt_size: Transposition Tableのサイズ
        """
        self.depth = depth
        self.max_moves = max_moves
        self.epsilon = epsilon
        self.use_iterative_deepening = use_iterative_deepening
        self.use_tt = use_tt
        # TTは対局を通じて保持（先手/後手で共有）
        self.tt = TranspositionTable(tt_size) if use_tt else None

    def choose_action(self, state: GameState) -> Action:
        """現在の状態から次のアクションを選択"""
        # ε確率でランダム
        if self.epsilon > 0 and random.random() < self.epsilon:
            return self._choose_random_action(state)

        # 最善のアクションを探索
        best_action = self._search_best_action(state)

        if best_action is None:
            # フォールバック: ランダム
            return self._choose_random_action(state)

        return best_action

    def _choose_random_action(self, state: GameState) -> Action:
        """ランダムにアクションを選択（フォールバック用）"""
        actions = self._get_actions(state)
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

    def _search_best_action(self, state: GameState) -> Optional[Action]:
        """現在の状態で最善のアクションを探索

        探索開始時に1回だけコピーし、以降はundo方式で探索。
        反復深化を使用する場合は浅い深さから順に探索。
        """
        # 探索用に1回だけコピー
        search_state = state.copy()
        search_engine = GameEngine(state=search_state, kifu_mode=KifuMode.NONE)

        actions = self._get_actions(search_state)
        if not actions:
            return None

        player = search_state.current_player

        if self.use_iterative_deepening:
            return self._iterative_deepening_search(search_engine, actions, player)
        else:
            return self._fixed_depth_search(search_engine, actions, player, self.depth)

    def _iterative_deepening_search(self, engine: GameEngine, actions: list[Action],
                                     player: int) -> Optional[Action]:
        """反復深化探索

        深さ1から始めて徐々に深くし、前回の結果でムーブオーダリングを改善。
        """
        best_action = None
        ordered_actions = actions  # 最初は元の順序

        for current_depth in range(1, self.depth + 1):
            # 前回の最善手を先頭に持ってくる
            if best_action is not None:
                ordered_actions = [best_action] + [a for a in ordered_actions if a != best_action]

            result = self._search_at_depth(engine, ordered_actions, player, current_depth)
            if result is not None:
                best_action = result
                # 次の反復のために、この深さでの評価順に並べ替え
                ordered_actions = self._order_actions(engine, actions, player, maximizing=True)

        return best_action

    def _fixed_depth_search(self, engine: GameEngine, actions: list[Action],
                            player: int, depth: int) -> Optional[Action]:
        """固定深さ探索（反復深化を使わない場合）"""
        # ムーブオーダリング
        actions = self._order_actions(engine, actions, player, maximizing=True)
        return self._search_at_depth(engine, actions, player, depth)

    def _search_at_depth(self, engine: GameEngine, actions: list[Action],
                         player: int, depth: int) -> Optional[Action]:
        """指定深さで探索を実行"""
        best_actions = []
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')
        best_action_for_tt: Optional[Action] = None

        for action in actions:
            result = engine.apply_action(action)
            if not result.success:
                continue

            # Alpha-Beta探索
            next_maximizing = engine.state.current_player == player
            value = self._alphabeta(engine, depth - 1, alpha, beta, next_maximizing, player)

            engine.undo()

            if value > best_value:
                best_value = value
                best_actions = [action]
                best_action_for_tt = action
            elif value == best_value:
                best_actions.append(action)

            alpha = max(alpha, value)

        return random.choice(best_actions) if best_actions else None

    def _order_actions(self, engine: GameEngine, actions: list[Action],
                       original_player: int, maximizing: bool,
                       tt_best: Optional[Action] = None) -> list[Action]:
        """ムーブオーダリング

        TTからの最善手がある場合はそれを先頭に。
        それ以外は1手読みの評価値でソート。
        """
        # TTからの最善手を先頭に
        if tt_best is not None and tt_best in actions:
            remaining = [a for a in actions if a != tt_best]
            # 残りを評価値でソート
            scored = []
            for action in remaining:
                result = engine.apply_action(action)
                if result.success:
                    score = self._evaluate(engine, original_player)
                    engine.undo()
                    scored.append((score, action))
            scored.sort(key=lambda x: x[0], reverse=maximizing)
            return [tt_best] + [a for _, a in scored]

        # TTからの情報がない場合は従来通り
        scored_actions = []
        for action in actions:
            result = engine.apply_action(action)
            if result.success:
                score = self._evaluate(engine, original_player)
                engine.undo()
                scored_actions.append((score, action))

        scored_actions.sort(key=lambda x: x[0], reverse=maximizing)
        return [action for _, action in scored_actions]

    def _alphabeta(self, engine: GameEngine, depth: int,
                   alpha: float, beta: float,
                   maximizing: bool, original_player: int) -> float:
        """Alpha-Beta枝刈り付きMinimax（undo方式 + TT）

        Args:
            engine: 探索用エンジン（状態を共有）
            depth: 残り探索深さ
            alpha: 最大化側の下限値
            beta: 最小化側の上限値
            maximizing: 最大化ノードかどうか
            original_player: 評価の基準となるプレイヤー
        """
        state = engine.state
        hash_key = state.zobrist_hash
        original_alpha = alpha

        # TTを参照
        tt_value = None
        tt_best_action = None
        if self.tt is not None:
            tt_value, tt_best_action = self.tt.probe(hash_key, depth, alpha, beta)
            if tt_value is not None:
                return tt_value

        # 終了条件
        if depth == 0 or state.winner is not None:
            return self._evaluate(engine, original_player)

        actions = self._get_actions(state)
        if not actions:
            return self._evaluate(engine, original_player)

        # ムーブオーダリング（TTからの最善手を優先）
        actions = self._order_actions(engine, actions, original_player, maximizing, tt_best_action)

        best_action: Optional[Action] = None

        if maximizing:
            value = float('-inf')
            for action in actions:
                result = engine.apply_action(action)
                if not result.success:
                    continue

                # プレイヤーが変わったときだけmaximizingを切り替える
                next_maximizing = state.current_player == original_player
                child_value = self._alphabeta(
                    engine, depth - 1, alpha, beta, next_maximizing, original_player
                )

                engine.undo()

                if child_value > value:
                    value = child_value
                    best_action = action

                alpha = max(alpha, value)
                if alpha >= beta:
                    break  # Beta cut-off
        else:
            value = float('inf')
            for action in actions:
                result = engine.apply_action(action)
                if not result.success:
                    continue

                next_maximizing = state.current_player == original_player
                child_value = self._alphabeta(
                    engine, depth - 1, alpha, beta, next_maximizing, original_player
                )

                engine.undo()

                if child_value < value:
                    value = child_value
                    best_action = action

                beta = min(beta, value)
                if alpha >= beta:
                    break  # Alpha cut-off

        # TTに格納
        if self.tt is not None:
            if value <= original_alpha:
                entry_type = TTEntryType.UPPER_BOUND
            elif value >= beta:
                entry_type = TTEntryType.LOWER_BOUND
            else:
                entry_type = TTEntryType.EXACT
            self.tt.store(hash_key, depth, value, entry_type, best_action)

        return value

    def _evaluate(self, engine: GameEngine, player: int) -> float:
        """盤面を評価"""
        return evaluate(engine, player)

    def get_tt_stats(self) -> Optional[dict]:
        """TT統計情報を取得"""
        if self.tt is None:
            return None
        return self.tt.get_stats()

    def clear_tt(self) -> None:
        """TTをクリア（新しい対局開始時に呼ぶ）"""
        if self.tt is not None:
            self.tt.clear()

    def _get_actions(self, state: GameState) -> list[Action]:
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
                piece_data = state.get_piece(x, y)
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

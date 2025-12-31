"""Minimax AI with Alpha-Beta Pruning（フェーズ分離型）"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state
from ai.base import BaseAI
from ai.minimax.evaluator import evaluate
from ai.greedy.piece_values import get_piece_value


class MinimaxPlayer(BaseAI):
    """Minimax探索を行うAI"""

    def __init__(self, depth: int = 3, epsilon: float = 0.0, max_moves: int = 20):
        """
        Args:
            depth: 探索の深さ
            epsilon: ランダムに手を選ぶ確率
            max_moves: 各深さで探索する最大手数（枝刈り）
        """
        self.depth = depth
        self.epsilon = epsilon
        self.max_moves = max_moves
        self._best_destination: Optional[tuple[int, int]] = None
        self._should_promote: bool = False

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """Minimax探索で最善の駒を選択"""
        # ε確率でランダム
        if self.epsilon > 0 and random.random() < self.epsilon:
            movable = engine.get_movable_pieces()
            if movable:
                piece = random.choice(movable)
                engine.select_piece(piece)
                dests = engine.get_legal_destinations()
                engine.cancel_piece_selection()
                if dests:
                    self._best_destination = random.choice(dests)
                    self._should_promote = random.choice([True, False])
                return piece

        # 全手を評価
        best_move = self._find_best_move(engine)
        if best_move:
            self._best_destination = best_move["to"]
            self._should_promote = best_move.get("promote", False)
            return best_move["from"]

        # フォールバック
        movable = engine.get_movable_pieces()
        return movable[0] if movable else (0, 0)

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """事前に計算した最適な移動先を返す"""
        if self._best_destination:
            return self._best_destination

        # フォールバック
        dests = engine.get_legal_destinations()
        return random.choice(dests) if dests else (0, 0)

    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうか"""
        return self._should_promote

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """射撃先を選択（最高価値を選択）"""
        targets = engine.get_shoot_targets()
        if not targets:
            return None

        scored_targets = []
        for pos in targets:
            target = engine.state.board.get(pos[0], pos[1])
            if target:
                piece_id, _ = target
                value = get_piece_value(piece_id)
                scored_targets.append((value, pos))

        if not scored_targets:
            return None

        max_value = max(v for v, _ in scored_targets)
        if max_value < 20:
            return None

        best_targets = [p for v, p in scored_targets if v == max_value]
        return random.choice(best_targets)

    def _find_best_move(self, engine: GameEngine) -> Optional[dict]:
        """Minimax探索で最善手を見つける"""
        moves = self._get_all_moves(engine)
        if not moves:
            return None

        player = engine.current_player
        best_move = None
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')

        # 手を評価値でソート（良さそうな手を先に探索 = 枝刈り効率UP）
        scored_moves = self._order_moves(engine, moves)[:self.max_moves]

        for move in scored_moves:
            # 手を適用
            if not self._apply_move(engine, move):
                continue

            # Minimax探索
            value = self._minimax(engine, self.depth - 1, alpha, beta, False, player)

            # undo
            engine.undo()

            if value > best_value:
                best_value = value
                best_move = move

            alpha = max(alpha, value)

        return best_move

    def _minimax(self, engine: GameEngine, depth: int, alpha: float, beta: float,
                 maximizing: bool, original_player: int) -> float:
        """Minimax with Alpha-Beta Pruning"""
        if depth == 0 or engine.is_game_over:
            return evaluate(engine, original_player)

        moves = self._get_all_moves(engine)
        if not moves:
            return evaluate(engine, original_player)

        scored_moves = self._order_moves(engine, moves)[:self.max_moves]

        if maximizing:
            value = float('-inf')
            for move in scored_moves:
                if not self._apply_move(engine, move):
                    continue

                value = max(value, self._minimax(engine, depth - 1, alpha, beta, False, original_player))
                engine.undo()

                alpha = max(alpha, value)
                if beta <= alpha:
                    break

            return value
        else:
            value = float('inf')
            for move in scored_moves:
                if not self._apply_move(engine, move):
                    continue

                value = min(value, self._minimax(engine, depth - 1, alpha, beta, True, original_player))
                engine.undo()

                beta = min(beta, value)
                if beta <= alpha:
                    break

            return value

    def _get_all_moves(self, engine: GameEngine) -> list[dict]:
        """現在のプレイヤーの全合法手を取得"""
        from backend.rules import promotion

        player = engine.current_player
        all_moves = []

        for x in range(19):
            for y in range(19):
                piece_data = engine.state.board.get(x, y)
                if piece_data is None:
                    continue
                piece_id, owner = piece_data
                if owner != player:
                    continue

                from_pos = (x, y)
                moves = engine.get_legal_moves(from_pos)

                for to_pos in moves:
                    can_promote = self._can_promote(engine, from_pos, to_pos)

                    if can_promote:
                        all_moves.append({"from": from_pos, "to": to_pos, "promote": False})
                        all_moves.append({"from": from_pos, "to": to_pos, "promote": True})
                    else:
                        all_moves.append({"from": from_pos, "to": to_pos, "promote": False})

        return all_moves

    def _can_promote(self, engine: GameEngine, from_pos: tuple[int, int], to_pos: tuple[int, int]) -> bool:
        """成れるか判定"""
        from backend.domain.piece_registry import get_piece
        from backend.rules import promotion

        piece_data = engine.state.board.get(from_pos[0], from_pos[1])
        if piece_data is None:
            return False

        piece_id, player = piece_data
        piece = get_piece(piece_id)
        if piece.promotes_to is None:
            return False

        target = engine.state.board.get(to_pos[0], to_pos[1])
        captured_piece = target[0] if target else None

        return promotion.can_promote(engine.state, from_pos, to_pos, captured_piece, player)

    def _order_moves(self, engine: GameEngine, moves: list[dict]) -> list[dict]:
        """手を評価値でソート（枝刈り効率化）"""
        scored = []
        for move in moves:
            to_pos = move["to"]
            target = engine.state.board.get(to_pos[0], to_pos[1])
            score = 0

            if target:
                piece_id, _ = target
                score += get_piece_value(piece_id)

            if move.get("promote"):
                score += 50

            scored.append((score, move))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [m for _, m in scored]

    def _apply_move(self, engine: GameEngine, move: dict) -> bool:
        """手を適用（フェーズ分離型API使用）"""
        from_pos = move["from"]
        to_pos = move["to"]
        promote = move.get("promote", False)

        # 駒選択
        if not engine.select_piece(from_pos):
            return False

        # 移動先選択
        result = engine.select_destination(to_pos)
        if not result.success:
            return False

        # 成り判断
        if engine.phase == GamePhase.PROMOTION:
            result = engine.decide_promotion(promote)
            if not result.success:
                return False

        # 射撃はスキップ（簡略化）
        if engine.phase == GamePhase.SHOOTING:
            engine.skip_shoot()

        return True

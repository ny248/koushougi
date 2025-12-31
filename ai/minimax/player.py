"""Minimax AI with Alpha-Beta Pruning"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine
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

    def choose_move(self, engine: GameEngine) -> Optional[dict]:
        """最善手を選択"""
        moves = self.get_all_moves(engine)
        if not moves:
            return None

        # ε確率でランダム
        if self.epsilon > 0 and random.random() < self.epsilon:
            return random.choice(moves)

        player = engine.current_player
        best_move = None
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')

        # 手を評価値でソート（良さそうな手を先に探索 = 枝刈り効率UP）
        scored_moves = self._order_moves(engine, moves)[:self.max_moves]

        for move in scored_moves:
            # 手を適用（undo方式）
            if not self._apply_move_inplace(engine, move):
                continue

            # Minimax探索
            value = self._minimax(engine, self.depth - 1, alpha, beta, False, player)

            # undo
            engine.pop_state()

            if value > best_value:
                best_value = value
                best_move = move

            alpha = max(alpha, value)

        return best_move

    def choose_shoot(self, engine: GameEngine, targets: list[tuple[int, int]]) -> Optional[tuple[int, int]]:
        """射撃先を選択（Greedyと同様に最高価値を選択）"""
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

    def _minimax(self, engine: GameEngine, depth: int, alpha: float, beta: float,
                 maximizing: bool, original_player: int) -> float:
        """
        Minimax with Alpha-Beta Pruning

        Args:
            engine: 現在の盤面
            depth: 残り探索深さ
            alpha: α値（最大化側の下限）
            beta: β値（最小化側の上限）
            maximizing: 最大化プレイヤーのターンか
            original_player: 元のプレイヤー（評価の視点）

        Returns:
            評価値
        """
        # 終端条件
        if depth == 0 or engine.is_game_over:
            return evaluate(engine, original_player)

        moves = self.get_all_moves(engine)
        if not moves:
            return evaluate(engine, original_player)

        # 手を評価値でソート（上位のみ探索）
        scored_moves = self._order_moves(engine, moves)[:self.max_moves]

        if maximizing:
            value = float('-inf')
            for move in scored_moves:
                if not self._apply_move_inplace(engine, move):
                    continue

                value = max(value, self._minimax(engine, depth - 1, alpha, beta, False, original_player))
                engine.pop_state()

                alpha = max(alpha, value)
                if beta <= alpha:
                    break  # β枝刈り

            return value
        else:
            value = float('inf')
            for move in scored_moves:
                if not self._apply_move_inplace(engine, move):
                    continue

                value = min(value, self._minimax(engine, depth - 1, alpha, beta, True, original_player))
                engine.pop_state()

                beta = min(beta, value)
                if beta <= alpha:
                    break  # α枝刈り

            return value

    def _order_moves(self, engine: GameEngine, moves: list[dict]) -> list[dict]:
        """手を評価値でソート（枝刈り効率化）"""
        scored = []
        for move in moves:
            to_pos = move["to"]
            target = engine.state.board.get(to_pos[0], to_pos[1])
            score = 0

            # 駒取りは高評価
            if target:
                piece_id, _ = target
                score += get_piece_value(piece_id)

            # 成りも加点
            if move.get("promote"):
                score += 50

            scored.append((score, move))

        # 降順ソート
        scored.sort(reverse=True, key=lambda x: x[0])
        return [m for _, m in scored]

    def _apply_move_inplace(self, engine: GameEngine, move: dict) -> bool:
        """手を適用（in-place、undo可能）

        Returns:
            成功したかどうか
        """
        # 状態を保存
        engine.push_state()

        from_pos = move["from"]
        to_pos = move["to"]
        promote = move.get("promote", False)

        result = engine.move(from_pos, to_pos, promote=promote)
        if not result.success:
            # 失敗したら元に戻す
            engine.pop_state()
            return False

        # 射撃はスキップ（簡略化）
        shoot_targets = engine.get_shoot_targets()
        if shoot_targets:
            engine.skip_shoot()

        return True

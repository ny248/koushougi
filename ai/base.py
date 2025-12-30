"""AI基底クラス - GameEngineを直接操作"""

from abc import ABC, abstractmethod
from typing import Optional
from backend.rules.game_engine import GameEngine


class BaseAI(ABC):
    """AI基底クラス"""

    @abstractmethod
    def choose_move(self, engine: GameEngine) -> Optional[dict]:
        """
        手を選択する

        Args:
            engine: ゲームエンジン（状態参照用、変更しない）

        Returns:
            選択した手: {"from": (x, y), "to": (x, y), "promote": bool}
            または None（手なし）
        """
        pass

    @abstractmethod
    def choose_shoot(self, engine: GameEngine, targets: list[tuple[int, int]]) -> Optional[tuple[int, int]]:
        """
        射撃先を選択する

        Args:
            engine: ゲームエンジン
            targets: 射撃可能な位置のリスト

        Returns:
            射撃先座標、またはNone（スキップ）
        """
        pass

    def get_all_moves(self, engine: GameEngine) -> list[dict]:
        """現在のプレイヤーの全合法手を取得"""
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

"""AI基底クラス - フェーズ分離型アーキテクチャ"""

from abc import ABC, abstractmethod
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase


class BaseAI(ABC):
    """AI基底クラス - 各フェーズごとに決定を行う"""

    @abstractmethod
    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """動かす駒を選択

        Args:
            engine: ゲームエンジン（PIECE_SELECTフェーズ）

        Returns:
            選択した駒の位置 (x, y)
        """
        pass

    @abstractmethod
    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """移動先を選択

        Args:
            engine: ゲームエンジン（DEST_SELECTフェーズ）
                   engine.selected_piece で選択中の駒位置を取得可能

        Returns:
            移動先の位置 (x, y)
        """
        pass

    @abstractmethod
    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうかを選択

        Args:
            engine: ゲームエンジン（PROMOTIONフェーズ）

        Returns:
            成る場合True
        """
        pass

    @abstractmethod
    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """射撃先を選択

        Args:
            engine: ゲームエンジン（SHOOTINGフェーズ）
                   engine.get_shoot_targets() で射撃可能位置を取得可能

        Returns:
            射撃先の位置、またはNone（スキップ）
        """
        pass

    def play_turn(self, engine: GameEngine) -> bool:
        """1ターンをプレイ（フェーズに応じて自動で処理）

        Args:
            engine: ゲームエンジン

        Returns:
            ターンが正常に完了したか
        """
        # フェーズ1: 駒選択
        if engine.phase != GamePhase.PIECE_SELECT:
            return False

        piece_pos = self.choose_piece(engine)
        if not engine.select_piece(piece_pos):
            return False

        # フェーズ2: 移動先選択
        dest_pos = self.choose_destination(engine)
        result = engine.select_destination(dest_pos)
        if not result.success:
            return False

        # フェーズ3: 成り判断（必要な場合）
        if engine.phase == GamePhase.PROMOTION:
            promote = self.choose_promotion(engine)
            result = engine.decide_promotion(promote)
            if not result.success:
                return False

        # フェーズ4: 射撃（必要な場合）
        if engine.phase == GamePhase.SHOOTING:
            target = self.choose_shoot_target(engine)
            if target:
                result = engine.shoot(target)
            else:
                result = engine.skip_shoot()
            if not result.success:
                return False

        return True

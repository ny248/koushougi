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

    @abstractmethod
    def choose_next_step(self, engine: GameEngine) -> tuple[int, int]:
        """マルチステップ移動の次のステップを選択

        Args:
            engine: ゲームエンジン（MULTI_STEP_MOVEフェーズ）
                   engine.get_next_step_options() で次のステップ候補を取得可能

        Returns:
            次の移動先の位置 (x, y)
        """
        pass

    @abstractmethod
    def choose_stop(self, engine: GameEngine) -> bool:
        """マルチステップ移動を途中で止めるかどうかを選択

        Args:
            engine: ゲームエンジン（MULTI_STEP_MOVEフェーズ）
                   engine.can_stop_now() で停止可能か確認可能

        Returns:
            停止する場合True、続ける場合False
        """
        pass

    def play_step(self, engine: GameEngine) -> bool:
        """1状態遷移を処理

        Args:
            engine: ゲームエンジン

        Returns:
            成功したか
        """
        phase = engine.phase

        if phase == GamePhase.PIECE_SELECT:
            pos = self.choose_piece(engine)
            return engine.select_piece(pos)

        elif phase == GamePhase.DEST_SELECT:
            pos = self.choose_destination(engine)
            return engine.select_destination(pos).success

        elif phase == GamePhase.MULTI_STEP_MOVE:
            if engine.can_stop_now() and self.choose_stop(engine):
                return engine.stop_move().success
            pos = self.choose_next_step(engine)
            return engine.select_next_step(pos).success

        elif phase == GamePhase.PROMOTION:
            promote = self.choose_promotion(engine)
            return engine.decide_promotion(promote).success

        elif phase == GamePhase.SHOOTING:
            target = self.choose_shoot_target(engine)
            if target:
                return engine.shoot(target).success
            else:
                return engine.skip_shoot().success

        return False

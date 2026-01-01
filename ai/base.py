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

        # フェーズ2.5: マルチステップ移動（必要な場合）
        while engine.phase == GamePhase.MULTI_STEP_MOVE:
            # 停止可能なら停止判断
            if engine.can_stop_now():
                if self.choose_stop(engine):
                    result = engine.stop_move()
                    if not result.success:
                        return False
                    break

            # 次のステップを選択
            next_pos = self.choose_next_step(engine)
            result = engine.select_next_step(next_pos)
            if not result.success:
                return False

            # ステップ完了でループ継続（まだMULTI_STEP_MOVEならループ続行）

        # フェーズ3: 成り判断（必要な場合）
        if engine.phase == GamePhase.PROMOTION:
            promote = self.choose_promotion(engine)
            result = engine.decide_promotion(promote)
            if not result.success:
                return False

        # フェーズ4: 射撃（必要な場合、複数回可能）
        while engine.phase == GamePhase.SHOOTING:
            target = self.choose_shoot_target(engine)
            if target:
                result = engine.shoot(target)
                if not result.success:
                    return False
                # まだ射撃可能ならループ継続
                if not result.can_shoot:
                    break
            else:
                result = engine.skip_shoot()
                if not result.success:
                    return False
                break

        return True

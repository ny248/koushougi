"""AI基底クラス - Actionベースアーキテクチャ"""

from abc import ABC, abstractmethod
from typing import Optional
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import GameState
from backend.domain.action import (
    Action, SelectPieceAction, SelectDestinationAction,
    StopMoveAction, SelectNextStepAction,
    DecidePromotionAction, ShootAction, SkipShootAction
)


class BaseAI(ABC):
    """AI基底クラス - Actionを返すインターフェース"""

    @abstractmethod
    def choose_action(self, state: GameState) -> Action:
        """現在の状態から次のアクションを選択

        Args:
            state: 現在のゲーム状態

        Returns:
            次に実行すべきアクション
        """
        pass

    def play_step(self, engine: GameEngine) -> bool:
        """1状態遷移を処理

        Args:
            engine: ゲームエンジン

        Returns:
            成功したか
        """
        if engine.phase == GamePhase.GAME_OVER:
            return False

        action = self.choose_action(engine.state)
        result = engine.apply_action(action)
        return result.success

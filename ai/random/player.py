"""ランダムAI - ランダムに合法手を選ぶ（フェーズ分離型API対応）"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine
from ai.base import BaseAI


class RandomPlayer(BaseAI):
    """ランダムに手を選ぶAI"""

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """ランダムに駒を選択"""
        movable = engine.get_movable_pieces()
        return random.choice(movable) if movable else (0, 0)

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """ランダムに移動先を選択"""
        dests = engine.get_legal_destinations()
        return random.choice(dests) if dests else (0, 0)

    def choose_promotion(self, engine: GameEngine) -> bool:
        """ランダムに成るか選択（50%で成る）"""
        return random.random() < 0.5

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """ランダムに射撃先を選択（50%でスキップ）"""
        targets = engine.get_shoot_targets()
        if not targets:
            return None
        if random.random() < 0.5:
            return random.choice(targets)
        return None  # スキップ

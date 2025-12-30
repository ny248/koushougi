"""ランダムAI - ランダムに合法手を選ぶ"""

import random
from typing import Optional
from backend.rules.game_engine import GameEngine
from ai.base import BaseAI


class RandomPlayer(BaseAI):
    """ランダムに手を選ぶAI"""

    def choose_move(self, engine: GameEngine) -> Optional[dict]:
        """ランダムに手を選択"""
        moves = self.get_all_moves(engine)
        if not moves:
            return None
        return random.choice(moves)

    def choose_shoot(self, engine: GameEngine, targets: list[tuple[int, int]]) -> Optional[tuple[int, int]]:
        """ランダムに射撃先を選択（50%でスキップ）"""
        if not targets:
            return None
        if random.random() < 0.5:
            return random.choice(targets)
        return None  # スキップ

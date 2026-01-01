"""AI - GameEngineを直接操作するAIモジュール"""

from ai.base import BaseAI
from ai.random import RandomPlayer
from ai.greedy import GreedyPlayer
from ai.minimax import MinimaxPlayer


def get_ai_player(ai_type: str, **kwargs) -> BaseAI:
    """AIプレイヤーファクトリー

    Args:
        ai_type: AIの種類 ("random", "greedy", "minimax", "neural")
        **kwargs: AI固有のパラメータ

    Returns:
        BaseAI のインスタンス
    """
    if ai_type == "random":
        return RandomPlayer(**kwargs)
    elif ai_type == "greedy":
        return GreedyPlayer(**kwargs)
    elif ai_type == "minimax":
        return MinimaxPlayer(**kwargs)
    elif ai_type == "neural":
        from ai.neural import NeuralPlayer
        return NeuralPlayer(**kwargs)
    else:
        raise ValueError(f"Unknown AI type: {ai_type}")


__all__ = ["BaseAI", "RandomPlayer", "GreedyPlayer", "MinimaxPlayer", "get_ai_player"]

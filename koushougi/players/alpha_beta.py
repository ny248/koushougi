"""αβ探索の最善手から一手を選ぶ。"""

import random

from ..move_ordering import MoveOrdering
from ..search import alpha_beta
from ..value_network import DEFAULT_NETWORK


DEFAULT_ORDERING = MoveOrdering(DEFAULT_NETWORK.score)


def analyze_search(game, time_limit=2.0, candidate_limit=None, max_depth=3, priority=None, *,
                   evaluator=None, ordering=None, capture_depth=0, model=None):
    """対戦用の既定値で探索する。盤面評価と候補順は個別に指定できる。"""
    if evaluator is None:
        evaluator = DEFAULT_ORDERING.position_score if model is None else model.score
    if ordering is None:
        ordering = MoveOrdering(evaluator, root_priority=priority)
    elif priority is not None:
        raise ValueError("priority と ordering は同時に指定できません")
    return alpha_beta(game, evaluator=evaluator, ordering=ordering, time_limit=time_limit,
                      candidate_limit=candidate_limit, max_depth=max_depth,
                      capture_depth=capture_depth)


def select_move(game, time_limit=2.0, candidate_limit=None, max_depth=3, rng=random, *,
                priority=None, evaluator=None, ordering=None, capture_depth=0, model=None):
    result = analyze_search(game, time_limit, candidate_limit, max_depth, priority,
                            evaluator=evaluator, ordering=ordering, capture_depth=capture_depth, model=model)
    return rng.choice(result.best_moves) if result else None

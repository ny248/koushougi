"""指定された盤面評価と候補順を使うαβ探索。"""

from collections.abc import Callable
from copy import copy
from dataclasses import dataclass
from time import monotonic

from .game import outcome
from .move_ordering import MoveOrdering

WIN = 1_000_000
DEFAULT_WIDTHS = (10, 5, 3)


def terminal_score(board, side):
    winner = outcome(board)
    if winner is None:
        return None
    return WIN if winner == side else -WIN


def _game_terminal_score(game, side):
    if getattr(game, "is_draw", False):
        return 0
    return terminal_score(game.board, side)


@dataclass(frozen=True)
class SearchResult:
    moves: tuple
    best_moves: tuple
    score: int
    depth: int


class SearchTimeout(Exception):
    pass


@dataclass(frozen=True)
class AlphaBetaReader:
    """評価と候補の選び方を保持し、各局面を独立して読む。

    widths は現在の手、相手の応手、次の手…で残す候補数。
    指定した段数を超えたら最後の上限を使い、Noneなら全候補を読む。
    capture_depth は通常の末端から駒を取る手だけを追加で読む深さ。
    """

    evaluator: Callable
    widths: tuple[int, ...] | None = DEFAULT_WIDTHS
    max_depth: int = 3
    ordering: MoveOrdering | None = None
    capture_depth: int = 0
    candidate_limit: int | None = None

    def __post_init__(self):
        if self.widths is not None:
            widths = tuple(self.widths)
            if not widths or any(type(limit) is not int or limit < 1 for limit in widths):
                raise ValueError("各段の候補数上限には正の整数を指定してください")
            object.__setattr__(self, "widths", widths)
        if self.ordering is None:
            object.__setattr__(self, "ordering", MoveOrdering(self.evaluator))

    def width_at(self, ply):
        return self.widths[min(ply, len(self.widths) - 1)] if self.widths else None

    def analyze(self, game, time_limit=2.0):
        """局面を変更せず、今回の制限時間内に得た探索結果を返す。"""
        return _analyze(game, self, time_limit)


def alpha_beta(game, *, evaluator, ordering, time_limit=2.0, candidate_limit=None, max_depth=3,
               capture_depth=0, branch_limits=None):
    """従来の引数による呼び出しを読み手へ渡す。"""
    return AlphaBetaReader(evaluator=evaluator, ordering=ordering, widths=branch_limits,
                           max_depth=max_depth, capture_depth=capture_depth,
                           candidate_limit=candidate_limit).analyze(game, time_limit=time_limit)


def _limited_children(game, side, deadline, preferred, evaluator, ordering, limit):
    """全合法手を採点し、手番側から見た上位だけを次の探索へ渡す。"""
    children, pending = [], []

    def flush():
        if monotonic() >= deadline:
            raise SearchTimeout
        games = [child for _, child, terminal in pending if terminal is None]
        values = iter(_many(ordering.position_score, games, side)) if games else iter(())
        for move, child, terminal in pending:
            score = terminal if terminal is not None else next(values)
            static = score if terminal is not None or ordering.position_score is evaluator else None
            children.append((score, move, child, static))
        pending.clear()

    for move, child in game.successors():
        if monotonic() >= deadline:
            raise SearchTimeout
        pending.append((move, child, _game_terminal_score(child, side)))
        if len(pending) >= _batch_size(ordering.position_score):
            flush()
    if pending:
        flush()
    children.sort(key=lambda row: row[0], reverse=game.turn == side)
    truncated = len(children) > limit
    selected = [(move, child, static) for _, move, child, static in children[:limit]]
    if preferred is not None:
        selected.sort(key=lambda row: row[0] != preferred)
    return selected, truncated


def _many(evaluator, games, side):
    owner = getattr(evaluator, "__self__", evaluator)
    batch = getattr(owner, "score_many", None)
    return batch(games, side) if batch is not None else [evaluator(game, side) for game in games]


def _batch_size(evaluator):
    owner = getattr(evaluator, "__self__", evaluator)
    return getattr(owner, "batch_size", 1) if hasattr(owner, "score_many") else 1


def _ordered_children(game, side, depth, deadline, preferred, evaluator, ordering):
    if preferred is not None:
        child = copy(game)
        child.play(*preferred)
        yield preferred, child, None

    maximizing = game.turn == side
    ordered = []
    unscored = []
    leaves = []

    def evaluated_leaves():
        terminal = [_game_terminal_score(child, side) for _, child in leaves]
        pending = [child for (_, child), score in zip(leaves, terminal) if score is None]
        values = iter(_many(evaluator, pending, side)) if pending else iter(())
        return [(move, child, next(values) if score is None else score)
                for (move, child), score in zip(leaves, terminal)]

    for move, child in game.successors():
        if move == preferred:
            continue
        if depth == 1:
            if _batch_size(evaluator) == 1:
                yield move, child, None
            else:
                leaves.append((move, child))
                if len(leaves) >= _batch_size(evaluator):
                    if monotonic() >= deadline:
                        raise SearchTimeout
                    yield from evaluated_leaves()
                    leaves.clear()
            continue
        if monotonic() >= deadline:
            raise SearchTimeout
        terminal = _game_terminal_score(child, side)
        if terminal == (WIN if maximizing else -WIN):
            yield move, child, terminal
            return
        if _batch_size(ordering.position_score) == 1:
            order_score = ordering.position_score(child, side) if terminal is None else terminal
            static = order_score if ordering.position_score is evaluator else terminal
            ordered.append((order_score, move, child, static))
        else:
            unscored.append((terminal, move, child))
    if leaves:
        if monotonic() >= deadline:
            raise SearchTimeout
        yield from evaluated_leaves()
    pending = [child for terminal, _, child in unscored if terminal is None]
    values = iter(_many(ordering.position_score, pending, side)) if pending else iter(())
    for terminal, move, child in unscored:
        order_score = next(values) if terminal is None else terminal
        static = order_score if ordering.position_score is evaluator else terminal
        ordered.append((order_score, move, child, static))
    ordered.sort(key=lambda entry: entry[0], reverse=maximizing)
    for _, move, child, static in ordered:
        yield move, child, static


def _capture_search(game, side, remaining, alpha, beta, deadline, evaluator, score=None):
    if monotonic() >= deadline:
        raise SearchTimeout
    if score is None:
        score = _game_terminal_score(game, side)
        if score is None:
            score = evaluator(game, side)
    if remaining == 0 or abs(score) == WIN:
        return score
    maximizing = game.turn == side
    if (maximizing and score >= beta) or (not maximizing and score <= alpha):
        return score
    for _, child in game.successors(captures_only=True):
        if maximizing:
            alpha = max(alpha, score)
        else:
            beta = min(beta, score)
        value = _capture_search(child, side, remaining - 1, alpha, beta, deadline, evaluator)
        score = max(score, value) if maximizing else min(score, value)
        if (maximizing and score >= beta) or (not maximizing and score <= alpha):
            break
    if monotonic() >= deadline:
        raise SearchTimeout
    return score


def _search(game, side, depth, alpha, beta, deadline, reader, *, static=None,
            preferred=None, ply=1):
    if monotonic() >= deadline:
        raise SearchTimeout
    if static is None:
        static = _game_terminal_score(game, side)
    if static in (WIN, -WIN):
        return static, None
    if depth == 0:
        score = reader.evaluator(game, side) if static is None else static
        if reader.capture_depth:
            score = _capture_search(game, side, reader.capture_depth, alpha, beta, deadline,
                                    reader.evaluator, score)
        return score, None

    maximizing = game.turn == side
    best = float("-inf") if maximizing else float("inf")
    reply = None
    limit = reader.width_at(ply)
    if limit is None:
        children = _ordered_children(game, side, depth, deadline, preferred, reader.evaluator, reader.ordering)
        truncated = False
    else:
        children, truncated = _limited_children(game, side, deadline, preferred,
                                                reader.evaluator, reader.ordering, limit)
    for move, child, child_score in children:
        score, _ = _search(child, side, depth - 1, alpha, beta, deadline, reader,
                           static=child_score, ply=ply + 1)
        if maximizing:
            if score > best:
                best, reply = score, move
            alpha = max(alpha, best)
        else:
            if score < best:
                best, reply = score, move
            beta = min(beta, best)
        if alpha >= beta or best == (WIN if maximizing else -WIN):
            break
    if reply is not None:
        # 自分の手を省いた負け、相手の応手を省いた勝ちは証明できていない。
        if truncated and best == (-WIN if maximizing else WIN):
            best += 1 if maximizing else -1
        return best, reply
    return (reader.evaluator(game, side) if static is None else static), None


def _analyze(game, reader, time_limit):
    """同評価の最善手と、制限時間内に完了した深さを返す。

    evaluator(game, side) は勝敗が未確定の局面に対して -WIN より大きく
    WIN より小さい整数を返す。勝敗点はルールに従って探索が付ける。
    """
    evaluator, ordering = reader.evaluator, reader.ordering
    deadline = monotonic() + time_limit
    side = game.turn
    candidates = []
    buffered = []

    def flush():
        pending = [child for _, child, terminal in buffered if terminal is None]
        values = iter(_many(evaluator, pending, side)) if pending else iter(())
        priorities = (iter(_many(ordering.position_score, pending, side))
                      if pending and ordering.position_score is not evaluator else None)
        for move, child, terminal in buffered:
            score = next(values) if terminal is None else terminal
            priority = next(priorities) if terminal is None and priorities is not None else score
            candidates.append((priority, score, move, child))
        buffered.clear()

    for move, child in game.successors():
        terminal = _game_terminal_score(child, side)
        buffered.append((move, child, terminal))
        if len(buffered) >= _batch_size(evaluator):
            flush()
        if monotonic() >= deadline:
            break
    if buffered:
        flush()
    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    ranked = [(score, move, child) for _, score, move, child in candidates]
    moves = tuple(move for _, move, _ in ranked)
    score = max(value for value, _, _ in ranked)
    result = SearchResult(moves, tuple(move for value, move, _ in ranked if value == score),
                          score, 1)
    if score == WIN:
        return result

    if ordering.root_priority is not None and monotonic() < deadline:
        ranked = ordering.rank_root(game, ranked)
    if reader.candidate_limit is not None:
        ranked = ranked[:max(1, reader.candidate_limit)]
    root_limit = reader.width_at(0)
    if root_limit is not None:
        ranked = ranked[:root_limit]
    root_truncated = len(ranked) < len(candidates)
    replies = {}
    for depth in range(2, reader.max_depth + 1):
        scores = []
        best = float("-inf")
        try:
            for _, move, child in ranked:
                # 評価値は整数。最善手と同点の候補は枝刈りで落とさない。
                score, reply = _search(child, side, depth - 1, best - 1, float("inf"), deadline,
                                       reader, preferred=replies.get(move))
                if ordering.use_previous_iteration:
                    replies[move] = reply
                scores.append((score, move, child))
                best = max(best, score)
        except SearchTimeout:
            if depth == 2 and scores and best > -WIN:
                result = SearchResult(moves, tuple(move for value, move, _ in scores if value == best),
                                      best, 1)
            elif depth == 2 and scores:
                # 負けが確定した候補より、まだ応手を読めていない候補を優先する。
                score, move, _ = ranked[len(scores)]
                result = SearchResult(moves, (move,), score, 1)
            break
        if ordering.use_previous_iteration:
            ranked = sorted(scores, key=lambda item: item[0], reverse=True)
        result = SearchResult(moves, tuple(move for value, move, _ in scores if value == best),
                              -WIN + 1 if root_truncated and best == -WIN else best, depth)
        if abs(result.score) == WIN:
            break

    return result

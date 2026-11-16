"""無作為と探索による対戦AI。"""

import random
from copy import copy
from time import monotonic

from . import resolve_movement
from .game import outcome, promotion


def choose_move(game, rng=random):
    """移動経路と射撃を選び、可能な成りも無作為に選ぶ。"""
    actions = [
        action
        for cell, piece in game.board.items()
        if piece.side == game.turn
        for action in game.actions(cell)
    ]
    if not actions:
        return None

    action = rng.choice(actions)
    promoted = promotion(game.board, action)
    promote = promoted is not None and bool(rng.getrandbits(1))
    linked = ()
    if promote and promoted == "軍師":
        board, _ = resolve_movement(game.board, action)
        linked = tuple(
            cell for cell, piece in board.items()
            if piece.side == game.turn and piece.name in {"前衝", "後衝"}
            and rng.getrandbits(1)
        )
    return action, promote, linked


# 歩兵を100とした暫定値。長距離移動、射撃、特殊能力を加味する。
VALUES = {
    "歩兵": 100, "牌": 115, "先鋒": 130, "軍匠": 145, "軍吏": 180,
    "親兵": 200, "護兵": 200, "舎人": 200, "舎餘": 180,
    "前衝": 220, "後衝": 180, "馬兵": 250, "歩総": 270, "車": 300,
    "牌総": 340, "象": 330, "弓": 320, "弩": 380, "砲": 475,
    "仏狼機": 650, "記室": 240, "参謀": 240, "神僧": 240, "高道": 330,
    "力士": 450, "車総": 430, "百総": 465, "把総": 500, "騎総": 475,
    "都司": 520, "天塁": 600, "天馬": 680, "彍騎": 460, "弩騎": 520,
    "砲車": 650, "神機車": 850, "鷹揚": 670, "虎翼": 700,
    "千総": 730, "龍驤": 970, "軍師": 540, "旗鼓": 480,
    "千戸": 390, "百戸": 380, "副司": 450, "毒火": 560,
    "五里霧": 550, "聖燈": 450, "天網": 470, "地網": 460,
    "鼓": 340, "霹靂": 800, "旗": 700, "招揺": 850,
    "中軍": 850, "帥": 1500, "将": 1400,
}
WIN = 1_000_000


def evaluate(board, side):
    winner = outcome(board)
    if winner:
        return WIN if winner == side else -WIN
    return sum(
        (VALUES[piece.name] * 20 + (18 - y if piece.side == "black" else y))
        * (1 if piece.side == side else -1)
        for (_, y), piece in board.items()
    )


def successors(game):
    for origin, piece in game.board.items():
        if piece.side != game.turn:
            continue
        for action in game.actions(origin):
            promoted = promotion(game.board, action)
            options = [(False, ())]
            if promoted:
                linked = ()
                if promoted == "軍師":
                    board, _ = resolve_movement(game.board, action)
                    linked = tuple(
                        cell for cell, p in board.items()
                        if p.side == game.turn and p.name in {"前衝", "後衝"}
                    )
                options.append((True, linked))
            for promote, linked in options:
                child = copy(game)
                child.play(action, promote, linked)
                yield (action, promote, linked), child


class SearchTimeout(Exception):
    pass


def _search(game, side, depth, alpha, beta, deadline):
    if monotonic() >= deadline:
        raise SearchTimeout
    static = evaluate(game.board, side)
    if depth == 0 or abs(static) == WIN:
        return static

    maximizing = game.turn == side
    best = float("-inf") if maximizing else float("inf")
    children = successors(game)
    if depth > 1:
        ordered = []
        for _, child in children:
            if monotonic() >= deadline:
                raise SearchTimeout
            score = evaluate(child.board, side)
            if score == (WIN if maximizing else -WIN):
                return score
            ordered.append((score, child))
        ordered.sort(key=lambda entry: entry[0], reverse=maximizing)
        children = ((None, child) for _, child in ordered)
    for _, child in children:
        score = _search(child, side, depth - 1, alpha, beta, deadline)
        if maximizing:
            best = max(best, score)
            alpha = max(alpha, best)
        else:
            best = min(best, score)
            beta = min(beta, best)
        if alpha >= beta:
            break
    return best if abs(best) != float("inf") else static


def choose_search_move(game, time_limit=2.0, candidate_limit=8, max_depth=3, rng=random):
    """有力な候補を順に読み、同評価の最善手から無作為に選ぶ。"""
    deadline = monotonic() + time_limit
    side = game.turn
    ranked = []
    for move, child in successors(game):
        ranked.append((evaluate(child.board, side), move, child))
        if monotonic() >= deadline:
            break
    if not ranked:
        return None

    rng.shuffle(ranked)
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked[0][0] == WIN:
        return ranked[0][1]

    ranked = ranked[:max(1, candidate_limit)]
    for depth in range(2, max_depth + 1):
        scores = []
        best = float("-inf")
        try:
            for _, move, child in ranked:
                # 評価値は整数。最善手と同点の候補は枝刈りで落とさない。
                score = _search(child, side, depth - 1, best - 1, float("inf"), deadline)
                scores.append((score, move, child))
                best = max(best, score)
        except SearchTimeout:
            # 最初の応手まで読めた候補があれば、静的評価だけの候補より優先する。
            if depth == 2 and scores:
                ranked = sorted(scores, key=lambda item: item[0], reverse=True)
            break
        ranked = sorted(scores, key=lambda item: item[0], reverse=True)

    return rng.choice([move for score, move, _ in ranked if score == ranked[0][0]])

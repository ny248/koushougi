"""同じαβ探索で、採点NNの重みが異なるモデルを比較する。"""

import argparse
from collections import Counter
import json
from math import isfinite
from pathlib import Path
from random import Random

from .game import Game, outcome
from .players.alpha_beta import select_move
from .value_network import load_network


def match(candidate, baseline, max_plies, seed, candidate_side, *, seconds=2.0, depth=3):
    game = Game()
    random_by_side = {"black": Random(seed), "white": Random(seed + 1)}
    for _ in range(max_plies):
        model = candidate if game.turn == candidate_side else baseline
        move = select_move(game, model=model, rng=random_by_side[game.turn],
                           time_limit=seconds, max_depth=depth)
        if move is None:
            return "no_legal_move"
        game.play(*move)
        winner = outcome(game.board)
        if winner:
            return "win" if winner == candidate_side else "loss"
    return "ply_limit"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=400)
    parser.add_argument("--max-plies", type=int, default=1500)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--depth", type=int, default=3)
    args = parser.parse_args()
    if min(args.pairs, args.max_plies, args.depth) < 1 or not isfinite(args.seconds) or args.seconds <= 0:
        parser.error("対局組数・手数・探索深さ・思考時間には正の値を指定してください")
    candidate, baseline = load_network(args.candidate), load_network(args.baseline)
    results = Counter({key: 0 for key in ("win", "loss", "ply_limit", "no_legal_move")})
    for pair in range(args.pairs):
        for side in ("black", "white"):
            result = match(candidate, baseline, args.max_plies, args.seed + 2 * pair, side,
                           seconds=args.seconds, depth=args.depth)
            results[result] += 1
            print(json.dumps({"pair": pair + 1, "candidate_side": side, "result": result}), flush=True)
    print(json.dumps({"games": 2 * args.pairs, "seed": args.seed, **results}))


if __name__ == "__main__":
    main()

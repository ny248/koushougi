"""学習済みの局面評価を同じ条件で対戦させる。"""

import argparse
from collections import Counter
import json
from pathlib import Path
from random import Random

from .ai import choose_move
from .game import Game, outcome
from .selfplay import model_move
from .train_value import load_weights


def match(candidate, baseline, max_plies, seed, candidate_side):
    game = Game()
    random_by_side = {"black": Random(seed), "white": Random(seed + 1)}
    for _ in range(max_plies):
        weights = candidate if game.turn == candidate_side else baseline
        rng = random_by_side[game.turn]
        move = choose_move(game, rng) if weights is None else model_move(game, rng, weights)
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
    args = parser.parse_args()
    if args.pairs < 1 or args.max_plies < 1:
        parser.error("--pairs と --max-plies には正の整数を指定してください")
    candidate, baseline = load_weights(args.candidate), load_weights(args.baseline)
    results = Counter({key: 0 for key in ("win", "loss", "ply_limit", "no_legal_move")})
    for pair in range(args.pairs):
        for side in ("black", "white"):
            result = match(candidate, baseline, args.max_plies, args.seed + 2 * pair, side)
            results[result] += 1
            print(json.dumps({"pair": pair + 1, "candidate_side": side, "result": result}),
                  flush=True)
    print(json.dumps({"games": 2 * args.pairs, "seed": args.seed, **results}))


if __name__ == "__main__":
    main()

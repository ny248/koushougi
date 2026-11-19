"""採点NNとαβ探索による自己対戦から、勝敗付きの学習局面を保存する。"""

import argparse
import json
from math import isfinite
from pathlib import Path
from random import Random
from time import perf_counter

from .game import Game, outcome
from .players.alpha_beta import analyze_search
from .value_network import load_network


def selfplay(rng, max_plies, model=None, *, seconds=2.0, depth=3):
    game = Game()
    positions = []
    for _ in range(max_plies):
        result = analyze_search(game, model=model, time_limit=seconds, max_depth=depth)
        if result is None:
            return positions, None, "no_legal_move"
        positions.append((game.turn, game.board, result.score, result.depth))
        game.play(*rng.choice(result.best_moves))
        winner = outcome(game.board)
        if winner:
            return positions, winner, "completed"
    return positions, None, "ply_limit"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--max-plies", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--depth", type=int, default=3)
    args = parser.parse_args()
    if min(args.games, args.max_plies, args.depth) < 1 or not isfinite(args.seconds) or args.seconds <= 0:
        parser.error("局数・手数・探索深さ・思考時間には正の値を指定してください")
    model = load_network(args.model)
    rng = Random(args.seed)
    counts = {"black": 0, "white": 0, "ply_limit": 0, "no_legal_move": 0}
    total_plies = samples = 0
    started = perf_counter()
    with args.output.open("x", encoding="utf-8") as output:
        for game_id in range(args.games):
            positions, winner, reason = selfplay(rng, args.max_plies, model,
                                                 seconds=args.seconds, depth=args.depth)
            total_plies += len(positions)
            counts[winner or reason] += 1
            if winner is None:
                continue
            for ply, (turn, board, score, depth) in enumerate(positions):
                sample = {
                    "game": game_id, "ply": ply, "turn": turn,
                    "value": 1 if winner == turn else -1,
                    "search_score": score, "search_depth": depth,
                    "pieces": [[x, y, p.side, p.name, p.promoted]
                               for (x, y), p in sorted(board.items())],
                }
                print(json.dumps(sample, ensure_ascii=False), file=output)
                samples += 1
    elapsed = perf_counter() - started
    print(json.dumps({"games": args.games, "seed": args.seed, "max_plies": args.max_plies,
                      "model": str(args.model) if args.model else None,
                      "seconds_per_move": args.seconds, "max_depth": args.depth,
                      **counts, "plies": total_plies, "samples": samples,
                      "seconds": round(elapsed, 2),
                      "plies_per_second": round(total_plies / elapsed, 1)}))


if __name__ == "__main__":
    main()

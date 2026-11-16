"""広将棋の自己対戦を実行し、勝敗付きの局面を出力する。"""

import argparse
import json
from pathlib import Path
from copy import copy
from random import Random
from time import perf_counter

from .ai import choose_move
from .game import Game, outcome, promotion
from .train_value import features, load_weights, predict


def model_move(game, rng, weights):
    """候補を無作為に絞り、盤面評価が良い手を選ぶ。"""
    if rng.random() < 0.15:
        return choose_move(game, rng)
    moves = [
        action
        for cell, piece in game.board.items()
        if piece.side == game.turn
        for action in game.actions(cell)
    ]
    best = None
    best_score = -float("inf")
    for action in rng.sample(moves, min(8, len(moves))):
        for promote in (False, True) if promotion(game.board, action) else (False,):
            child = copy(game)
            child.play(action, promote)
            winner = outcome(child.board)
            if winner:
                score = 2 if winner == game.turn else -2
            else:
                pieces = ((x, y, p.side, p.name, p.promoted)
                          for (x, y), p in child.board.items())
                score = predict(weights, features(pieces, game.turn))
            if score > best_score:
                best_score = score
                best = action, promote, ()
    return best


def selfplay(rng, max_plies, weights=None):
    game = Game()
    positions = []
    for _ in range(max_plies):
        choice = choose_move(game, rng) if weights is None else model_move(game, rng, weights)
        if choice is None:
            return positions, None, "no_legal_move"
        positions.append((game.turn, game.board))
        game.play(*choice)
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
    args = parser.parse_args()
    if args.games < 1 or args.max_plies < 1:
        parser.error("--games と --max-plies は正の整数を指定してください")

    weights = load_weights(args.model)
    rng = Random(args.seed)
    counts = {"black": 0, "white": 0, "ply_limit": 0, "no_legal_move": 0}
    total_plies = samples = 0
    started = perf_counter()
    with args.output.open("x", encoding="utf-8") as output:
        for game_id in range(args.games):
            positions, winner, reason = selfplay(rng, args.max_plies, weights)
            total_plies += len(positions)
            counts[winner or reason] += 1
            if winner is None:
                continue
            for ply, (turn, board) in enumerate(positions):
                sample = {
                    "game": game_id, "ply": ply, "turn": turn,
                    "value": 1 if winner == turn else -1,
                    "pieces": [[x, y, p.side, p.name, p.promoted]
                               for (x, y), p in sorted(board.items())],
                }
                print(json.dumps(sample, ensure_ascii=False), file=output)
                samples += 1
    elapsed = perf_counter() - started
    print(json.dumps({"games": args.games, "seed": args.seed, "max_plies": args.max_plies,
                      "model": str(args.model) if args.model else None,
                      **counts, "plies": total_plies, "samples": samples,
                      "seconds": round(elapsed, 2),
                      "plies_per_second": round(total_plies / elapsed, 1)}))


if __name__ == "__main__":
    main()

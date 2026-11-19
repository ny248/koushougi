"""自己対戦の探索評価と勝敗から、局面を採点する1つのNNを学習する。"""

import argparse
import json
from math import isfinite, tanh
from pathlib import Path
from random import Random

import torch
from torch import nn

from . import Piece
from .value_network import SIZE, SCALE, ValueNetwork, encode_board, load_network


class TrainingNetwork(nn.Module):
    """対局用NNと同じパラメータと計算を持つ、勾配計算用の実装。"""

    def __init__(self, model):
        super().__init__()
        self.weights = nn.ParameterDict({name: nn.Parameter(torch.tensor(values, dtype=torch.float32))
                                        for name, values in model.parameters.items()})
        self.register_buffer("ranks", torch.arange(SIZE * SIZE).div(SIZE, rounding_mode="floor"))

    def forward(self, boards):
        weights = self.weights
        occupied = boards != 0
        linear = ((weights["base"][boards] + weights["advance"][boards] * self.ranks) * occupied).sum(dim=1)
        local = weights["piece"][boards] * weights["square"]
        hidden = (local * occupied.unsqueeze(-1)).sum(dim=1) / SIZE + weights["hidden_bias"]
        nonlinear = (hidden.tanh() * weights["output"]).sum(dim=1) + weights["output_bias"][0]
        return linear + SCALE * nonlinear

    def export(self):
        parameters = {name: values.detach().cpu().tolist() for name, values in self.weights.items()}
        return ValueNetwork(parameters, width=len(parameters["output"]))


def get_device(requested):
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDAが使えません")
    if requested == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPSが使えません")
    return torch.device(requested)


def read_samples(path, search_weight):
    games = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            sample = json.loads(line)
            pieces = {(x, y): Piece(side, name, promoted) for x, y, side, name, promoted in sample["pieces"]}
            value = sample["value"]
            if value not in (-1, 0, 1):
                raise ValueError("勝敗の教師値は-1、0、1にしてください")
            if "search_score" in sample:
                if not isfinite(sample["search_score"]):
                    raise ValueError("探索評価値が不正です")
                value = (1 - search_weight) * value + search_weight * tanh(sample["search_score"] / SCALE)
            row = encode_board(pieces, sample["turn"]), value
            games.setdefault(sample["game"], []).append(row)
    if len(games) < 2:
        raise ValueError("学習と検証には、勝敗がついた対局が2局以上必要です")
    return games


def fit(model, rows, validation, *, epochs, batch_size, device, seed):
    torch.manual_seed(seed)
    network = TrainingNetwork(model).to(device)
    optimizer = torch.optim.Adam(network.parameters(), lr=0.001)
    rng = Random(seed)
    for _ in range(epochs):
        rng.shuffle(rows)
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset:offset + batch_size]
            boards = torch.tensor([row[0] for row in batch], dtype=torch.long, device=device)
            targets = torch.tensor([row[1] for row in batch], dtype=torch.float32, device=device)
            prediction = (network(boards) / SCALE).tanh()
            loss = (prediction - targets).square().mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
    with torch.inference_mode():
        error = 0.0
        for offset in range(0, len(validation), batch_size):
            batch = validation[offset:offset + batch_size]
            boards = torch.tensor([row[0] for row in batch], dtype=torch.long, device=device)
            targets = torch.tensor([row[1] for row in batch], dtype=torch.float32, device=device)
            error += ((network(boards) / SCALE).tanh() - targets).square().sum().item()
    return network.export(), error / len(validation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--search-weight", type=float, default=0.5)
    args = parser.parse_args()
    if min(args.epochs, args.batch_size) < 1 or not 0 <= args.search_weight <= 1:
        parser.error("学習回数とバッチ数は正の整数、探索評価の比率は0〜1にしてください")
    if args.output.exists():
        parser.error("出力先には新しいファイル名を指定してください")
    try:
        model = load_network(args.model)
        device = get_device(args.device)
        games = read_samples(args.dataset, args.search_weight)
        ids = list(games)
        Random(args.seed).shuffle(ids)
        split = max(1, len(ids) // 5)
        validation = [row for game in ids[:split] for row in games[game]]
        rows = [row for game in ids[split:] for row in games[game]]
        model, error = fit(model, rows, validation, epochs=args.epochs, batch_size=args.batch_size,
                           device=device, seed=args.seed)
        model.save(args.output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({"training_games": len(ids) - split, "validation_games": split,
                      "training_positions": len(rows), "validation_positions": len(validation),
                      "device": str(device), "validation_mse": error, "model_format": 2}))


if __name__ == "__main__":
    main()

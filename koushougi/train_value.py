"""自己対戦の勝敗から線形の局面評価を学習する。"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from random import Random


def features(pieces, turn):
    counts = Counter()
    for _, y, side, name, _ in pieces:
        sign = 1 if side == turn else -1
        counts[name] += sign / 10
        counts["advance"] += sign * (18 - y if side == "black" else y) / 180
    return counts


def predict(weights, row):
    score = sum(weights.get(name, 0) * value for name, value in row.items())
    return math.tanh(score)


def load_weights(path):
    if path is None:
        return None
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("format") != 1:
        raise ValueError("未対応のモデル形式です")
    return model["weights"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    games = {}
    with args.dataset.open(encoding="utf-8") as source:
        for line in source:
            sample = json.loads(line)
            games.setdefault(sample["game"], []).append((features(sample["pieces"], sample["turn"]), sample["value"]))
    if len(games) < 2:
        parser.error("学習と検証には勝敗がついた対局が2局以上必要です")
    rng = Random(0)
    game_ids = list(games)
    rng.shuffle(game_ids)
    split = max(1, len(game_ids) // 5)
    validation = [row for game in game_ids[:split] for row in games[game]]
    training = [row for game in game_ids[split:] for row in games[game]]
    weights = Counter()
    for _ in range(5):
        rng.shuffle(training)
        for row, target in training:
            value = predict(weights, row)
            gradient = 0.015 * (target - value) * (1 - value * value)
            for name, feature in row.items():
                weights[name] += gradient * feature
    mse = sum((predict(weights, row) - target) ** 2
              for row, target in validation) / len(validation)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({"format": 1, "weights": weights}, output, ensure_ascii=False, indent=2)
    print(json.dumps({"training_games": len(games) - split, "validation_games": split,
                      "training_positions": len(training), "validation_positions": len(validation),
                      "validation_mse": round(mse, 4), "zero_prediction_mse": 1.0}))


if __name__ == "__main__":
    main()

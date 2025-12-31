#!/usr/bin/env python3
"""訓練実行スクリプト"""

import argparse

from ai.analysis.trainer import Trainer, TrainingConfig
from config import AI_MAX_TURNS


def main():
    parser = argparse.ArgumentParser(description="駒価値の継続的訓練")
    parser.add_argument("-r", "--rounds", type=int, default=10, help="訓練ラウンド数")
    parser.add_argument("-g", "--games", type=int, default=200, help="1ラウンドあたりの対局数")
    parser.add_argument("-j", "--jobs", type=int, default=0, help="並列数（0=CPU数）")
    parser.add_argument("-e", "--epsilon", type=float, default=0.05, help="探索率")
    parser.add_argument("--scale", type=float, default=100.0, help="価値調整スケール")
    parser.add_argument("--max-adj", type=float, default=50.0, help="最大調整幅")
    parser.add_argument("--min-samples", type=int, default=10, help="最小サンプル数")
    parser.add_argument("--max-turns", type=int, default=AI_MAX_TURNS, help="対局の最大ターン数")
    parser.add_argument("-o", "--output", type=str, default="data/training", help="出力ディレクトリ")
    parser.add_argument("-q", "--quiet", action="store_true", help="進捗非表示")
    args = parser.parse_args()

    config = TrainingConfig(
        games_per_round=args.games,
        max_rounds=args.rounds,
        min_samples=args.min_samples,
        scale_factor=args.scale,
        max_adjustment=args.max_adj,
        epsilon=args.epsilon,
        n_jobs=args.jobs,
        max_turns=args.max_turns,
        output_dir=args.output,
    )

    trainer = Trainer(config)
    final_values = trainer.run(verbose=not args.quiet)

    print(f"\n=== 訓練完了 ===")
    print(f"ラウンド: {args.rounds}")
    print(f"総対局数: {args.rounds * args.games}")


if __name__ == "__main__":
    main()

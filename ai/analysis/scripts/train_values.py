#!/usr/bin/env python3
"""価値学習スクリプト - 棋譜から駒の価値を学習"""

import argparse
from pathlib import Path
import glob

from ai.analysis.kifu_analyzer import KifuAnalyzer
from ai.analysis.value_learner import ValueLearner


def main():
    parser = argparse.ArgumentParser(description="棋譜から駒の価値を学習")
    parser.add_argument("-i", "--input", type=str, nargs="+", required=True,
                        help="入力ファイル（JSON、ワイルドカード対応）")
    parser.add_argument("-o", "--output", type=str, help="出力ファイル（.py）")
    parser.add_argument("--min-samples", type=int, default=5,
                        help="最小サンプル数（これ未満は調整しない）")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細表示")
    args = parser.parse_args()

    # ファイル収集（ワイルドカード展開）
    input_files = []
    for pattern in args.input:
        matches = glob.glob(pattern)
        if matches:
            input_files.extend(matches)
        else:
            input_files.append(pattern)  # パターンが直接ファイル名の場合

    if not input_files:
        print("エラー: 入力ファイルがありません")
        return 1

    print(f"入力ファイル: {len(input_files)}個")
    for f in input_files:
        print(f"  - {f}")

    # 分析
    analyzer = KifuAnalyzer()
    for fp in input_files:
        try:
            analyzer.analyze_file(fp)
        except Exception as e:
            print(f"警告: {fp} の読み込み失敗: {e}")

    result = analyzer.get_result()
    print()
    analyzer.print_summary()

    if result.decisive_games == 0:
        print("\nエラー: 決着のついた対局がありません")
        return 1

    # 学習
    learner = ValueLearner()
    new_values = learner.learn(result, min_samples=args.min_samples)

    if args.verbose:
        print()
        learner.print_comparison(new_values, result)

    # 出力
    if args.output:
        output_path = Path(args.output)
        code = learner.generate_python_code(new_values)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"\n学習結果を保存: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())

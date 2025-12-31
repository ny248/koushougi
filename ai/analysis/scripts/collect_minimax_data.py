"""Minimaxプレイヤーの指し手を教師データとして収集"""

import json
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.rules.game_engine import GameEngine
from ai.minimax.player import MinimaxPlayer


def encode_board_state(engine: GameEngine) -> dict:
    """盤面状態をエンコード"""
    board_state = []
    for y in range(19):
        for x in range(19):
            piece = engine.state.board.get(x, y)
            if piece:
                piece_id, owner = piece
                board_state.append({
                    "x": x,
                    "y": y,
                    "piece_id": piece_id,
                    "owner": owner
                })

    return {
        "board": board_state,
        "current_player": engine.state.current_player,
        "move_count": engine.state.move_count
    }


def play_one_game(game_id: int, max_moves: int = 200) -> dict:
    """1局プレイしてデータ収集"""
    engine = GameEngine()
    player = MinimaxPlayer(depth=2)

    positions = []  # (盤面, 選んだ手) のリスト

    for move_num in range(max_moves):
        if engine.state.winner is not None:
            break

        # 現在の盤面を保存
        board_state = encode_board_state(engine)

        # Minimaxが手を選ぶ
        move = player.choose_move(engine)
        if not move:
            break

        # 手を記録
        position_data = {
            "board_state": board_state,
            "move": move,
            "move_number": move_num
        }
        positions.append(position_data)

        # 手を実行
        from_pos = move["from"]
        to_pos = move["to"]
        promote = move.get("promote", False)

        result = engine.move(from_pos, to_pos, promote=promote)
        if not result.success:
            break

        # 射撃がある場合
        if result.can_shoot:
            shoot_move = player.choose_shoot(engine)
            if shoot_move:
                engine.shoot(shoot_move["target"])

    # 最終結果
    winner = engine.state.winner

    return {
        "game_id": game_id,
        "positions": positions,
        "winner": winner,
        "total_moves": len(positions)
    }


def collect_games_batch(start_id: int, count: int, max_moves: int) -> list:
    """バッチでゲームを収集"""
    games = []
    for i in range(count):
        game_id = start_id + i
        print(f"  ゲーム {game_id}/{start_id + count - 1} プレイ中...")
        game_data = play_one_game(game_id, max_moves)
        games.append(game_data)
        print(f"    完了: {game_data['total_moves']}手, 勝者={game_data['winner']}")
    return games


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Minimaxプレイヤーの教師データ収集")
    parser.add_argument("--games", type=int, default=5000, help="収集するゲーム数")
    parser.add_argument("--max-moves", type=int, default=200, help="1ゲームの最大手数")
    parser.add_argument("--workers", type=int, default=8, help="並列ワーカー数")
    parser.add_argument("--output", type=str, default="data/minimax_training", help="出力ディレクトリ")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Minimaxデータ収集開始 ===")
    print(f"ゲーム数: {args.games}")
    print(f"最大手数: {args.max_moves}")
    print(f"並列数: {args.workers}")
    print(f"出力先: {output_dir}")
    print()

    start_time = time.time()
    all_games = []

    # 並列実行
    batch_size = max(1, args.games // args.workers)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for i in range(0, args.games, batch_size):
            count = min(batch_size, args.games - i)
            future = executor.submit(collect_games_batch, i, count, args.max_moves)
            futures.append(future)

        for i, future in enumerate(futures):
            print(f"バッチ {i+1}/{len(futures)} 待機中...")
            games = future.result()
            all_games.extend(games)
            print(f"バッチ {i+1} 完了: {len(games)}ゲーム")

    elapsed = time.time() - start_time

    # 統計情報
    total_positions = sum(len(g["positions"]) for g in all_games)
    avg_moves = total_positions / len(all_games) if all_games else 0
    winner_counts = {}
    for g in all_games:
        w = g["winner"]
        winner_counts[w] = winner_counts.get(w, 0) + 1

    print()
    print(f"=== 収集完了 ===")
    print(f"総ゲーム数: {len(all_games)}")
    print(f"総局面数: {total_positions}")
    print(f"平均手数: {avg_moves:.1f}")
    print(f"勝者分布: {winner_counts}")
    print(f"経過時間: {elapsed:.1f}秒 ({elapsed/60:.1f}分)")
    print(f"速度: {len(all_games)/(elapsed/60):.1f}ゲーム/分")

    # データ保存
    output_file = output_dir / "training_data.jsonl"
    print(f"\nデータ保存中: {output_file}")

    with open(output_file, "w") as f:
        for game in all_games:
            f.write(json.dumps(game, ensure_ascii=False) + "\n")

    # メタデータ保存
    meta_file = output_dir / "metadata.json"
    metadata = {
        "total_games": len(all_games),
        "total_positions": total_positions,
        "avg_moves_per_game": avg_moves,
        "winner_distribution": winner_counts,
        "collection_time_sec": elapsed,
        "max_moves_per_game": args.max_moves,
        "minimax_depth": 2,
        "use_learned_values": True
    }
    with open(meta_file, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"完了！")
    print(f"  データ: {output_file}")
    print(f"  メタデータ: {meta_file}")


if __name__ == "__main__":
    main()

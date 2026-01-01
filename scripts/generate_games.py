"""棋譜生成スクリプト

サブプロセスで試合を実行し、タイムアウトでキルする安全な棋譜生成。
棋譜はKifuクラスと互換のJSONL形式で保存。

Usage:
    # NN vs Minimax
    python scripts/generate_games.py --games 100 --output data/games/batch_001.jsonl

    # Minimax同士（教師データ生成用）
    python scripts/generate_games.py --games 100 --mode minimax-vs-minimax

    # 既存モデルを使用
    python scripts/generate_games.py --games 100 --model models/rl_v1/best_model.pth
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import time
import logging
import multiprocessing as mp
from pathlib import Path
from datetime import datetime
from typing import Optional

from scripts.lib.logger import setup_logger


def play_single_game(args_tuple) -> Optional[dict]:
    """単一ゲームをプレイ（ワーカープロセス用）

    Returns:
        棋譜データ（Kifu互換形式）またはNone（エラー時）
    """
    game_id, mode, model_path, minimax_depth, epsilon, lite = args_tuple

    # 各プロセスでimport（forkセーフ）
    import torch
    from backend.rules.game_engine import GameEngine, GamePhase
    from backend.domain.game_state import create_initial_state
    from backend.domain.kifu import Kifu, Move
    from ai.minimax.player import MinimaxPlayer
    from ai.neural.player import NeuralPlayer
    from ai.neural.model import create_model

    try:
        # プレイヤー設定
        if mode == "nn-vs-minimax":
            device = torch.device("cpu")  # サブプロセスではCPU
            model = create_model(lite=lite, device="cpu")
            if model_path:
                checkpoint = torch.load(model_path, map_location=device)
                model.load_state_dict(checkpoint["model_state_dict"])
            player_a = NeuralPlayer(model, device, epsilon=epsilon, temperature=1.0)
            player_b = MinimaxPlayer(depth=minimax_depth, max_moves=15)
            player_a_type = "neural"
            player_b_type = "minimax"
        else:  # minimax-vs-minimax
            player_a = MinimaxPlayer(depth=minimax_depth, max_moves=15)
            player_b = MinimaxPlayer(depth=minimax_depth, max_moves=15)
            player_a_type = "minimax"
            player_b_type = "minimax"

        # 先後交互
        a_is_first = (game_id % 2 == 0)
        sente = player_a if a_is_first else player_b
        gote = player_b if a_is_first else player_a
        sente_type = player_a_type if a_is_first else player_b_type
        gote_type = player_b_type if a_is_first else player_a_type

        engine = GameEngine(create_initial_state())
        kifu = Kifu()

        for turn in range(300):
            if engine.is_game_over:
                break

            current = engine.current_player
            player = sente if current == 0 else gote

            if engine.phase != GamePhase.PIECE_SELECT:
                continue

            # 駒選択
            piece_pos = player.choose_piece(engine)
            if not engine.select_piece(piece_pos):
                break

            # 移動先
            dest_pos = player.choose_destination(engine)
            result = engine.select_destination(dest_pos)
            if not result.success:
                break

            piece_data = engine.state.board.get(dest_pos[0], dest_pos[1])
            piece_id = piece_data[0] if piece_data else None

            # 成り
            promoted = False
            if engine.phase == GamePhase.PROMOTION:
                promote = player.choose_promotion(engine)
                result = engine.decide_promotion(promote)
                if not result.success:
                    break
                promoted = promote

            # 移動を記録
            move = Move(
                player=current,
                move_type="move",
                from_pos=piece_pos,
                to_pos=dest_pos,
                piece_id=piece_id,
                promoted=promoted,
            )
            kifu.append(move)

            # 射撃
            while engine.phase == GamePhase.SHOOTING:
                target = player.choose_shoot_target(engine)
                if target:
                    target_piece = engine.state.board.get(target[0], target[1])
                    result = engine.shoot(target)
                    shoot_move = Move(
                        player=current,
                        move_type="shoot",
                        captured_piece=target_piece[0] if target_piece else None,
                        captured_pos=target,
                    )
                    kifu.append(shoot_move)
                    if not result.can_shoot:
                        break
                else:
                    engine.skip_shoot()
                    break

        # 結果を記録
        kifu.winner = engine.winner

        # 棋譜データを構築
        game_record = {
            "game_id": game_id,
            "timestamp": datetime.now().isoformat(),
            "players": {
                "sente": sente_type,
                "gote": gote_type,
            },
            "kifu": kifu.to_dict(),
        }

        return game_record

    except Exception as e:
        return {"game_id": game_id, "error": str(e)}


def generate_games(args, logger):
    """ゲームを生成して棋譜を保存"""

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== 棋譜生成 ===")
    logger.info(f"ゲーム数: {args.games}")
    logger.info(f"出力: {output_path}")
    logger.info(f"モード: {args.mode}")
    logger.info(f"タイムアウト: {args.timeout}秒")

    # 統計
    stats = {"completed": 0, "timeouts": 0, "errors": 0}
    results_by_player = {"sente": 0, "gote": 0, "draw": 0}

    # ゲーム引数を準備
    game_args = [
        (i + 1, args.mode, args.model, args.minimax_depth, args.epsilon, args.lite)
        for i in range(args.games)
    ]

    with open(output_path, "a") as f:
        # 1ゲームずつサブプロセスで実行（タイムアウト制御）
        for i, game_arg in enumerate(game_args):
            game_id = game_arg[0]
            start_time = time.time()

            # サブプロセスで実行
            ctx = mp.get_context("spawn")  # fork問題回避
            pool = ctx.Pool(1)
            async_result = pool.apply_async(play_single_game, (game_arg,))

            try:
                result = async_result.get(timeout=args.timeout)
                elapsed = time.time() - start_time

                if result is None or "error" in result:
                    stats["errors"] += 1
                    error_msg = result.get("error", "Unknown") if result else "None returned"
                    logger.warning(f"Game {game_id}: エラー ({error_msg})")
                else:
                    # 成功
                    stats["completed"] += 1
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()

                    # 勝者集計
                    winner = result["kifu"].get("winner")
                    if winner == 0:
                        results_by_player["sente"] += 1
                    elif winner == 1:
                        results_by_player["gote"] += 1
                    else:
                        results_by_player["draw"] += 1

                    if (i + 1) % 10 == 0:
                        logger.info(
                            f"ゲーム {i + 1}/{args.games}: "
                            f"先手{results_by_player['sente']}勝, "
                            f"後手{results_by_player['gote']}勝, "
                            f"引分{results_by_player['draw']} "
                            f"({elapsed:.1f}s)"
                        )

            except mp.TimeoutError:
                stats["timeouts"] += 1
                logger.warning(f"Game {game_id}: タイムアウト ({args.timeout}秒)")

            finally:
                pool.terminate()
                pool.join()

    logger.info(f"完了: {output_path}")
    logger.info(f"成功: {stats['completed']}, タイムアウト: {stats['timeouts']}, エラー: {stats['errors']}")
    logger.info(f"先手勝: {results_by_player['sente']}, 後手勝: {results_by_player['gote']}, 引分: {results_by_player['draw']}")


def main():
    parser = argparse.ArgumentParser(description="棋譜生成")
    parser.add_argument("--output", "-o", type=str, default="data/games/games.jsonl",
                        help="出力ファイル (JSONL)")
    parser.add_argument("--games", "-n", type=int, default=100, help="生成ゲーム数")
    parser.add_argument("--mode", type=str, default="nn-vs-minimax",
                        choices=["nn-vs-minimax", "minimax-vs-minimax"],
                        help="対戦モード")
    parser.add_argument("--model", type=str, help="NNモデルのパス")
    parser.add_argument("--minimax-depth", type=int, default=1, help="Minimax探索深さ")
    parser.add_argument("--epsilon", type=float, default=0.3, help="NN探索率")
    parser.add_argument("--timeout", type=int, default=60, help="ゲームタイムアウト秒")
    parser.add_argument("--lite", action="store_true", help="軽量モデル")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("generate", level=log_level)

    generate_games(args, logger)


if __name__ == "__main__":
    main()

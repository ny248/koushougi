"""棋譜を学習用経験データに変換

棋譜(JSONL)を読み込み、各手の盤面状態・行動・報酬を計算して
バイナリ形式(.pt)で保存する。学習時は再生不要で高速に読み込める。

Usage:
    python scripts/convert_kifu.py --input games.jsonl --output experiences.pt
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

import torch

from scripts.lib.logger import setup_logger
from ai.neural.model import encode_board, pos_to_index
from ai.greedy.piece_values import get_piece_value
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state
from backend.domain.kifu import Kifu


BATCH_SIZE = 5000  # バッチ処理のサイズ


def convert_kifu_file(input_path: Path, output_path: Path, logger) -> dict:
    """棋譜ファイルを経験データに変換（メモリ効率化版）

    Returns:
        統計情報
    """
    # フェーズ別のバッファ（バッチ処理用）
    buffers = {
        "piece": {"states": [], "actions": [], "rewards": []},
        "dest": {"states": [], "actions": [], "rewards": []},
        "promo": {"states": [], "actions": [], "rewards": []},
        "shoot": {"states": [], "actions": [], "rewards": []},
    }

    # バッチ処理済みテンソルのリスト
    batches = {
        "piece": {"states": [], "actions": [], "rewards": []},
        "dest": {"states": [], "actions": [], "rewards": []},
        "promo": {"states": [], "actions": [], "rewards": []},
        "shoot": {"states": [], "actions": [], "rewards": []},
    }

    stats = {"games": 0, "experiences": 0, "errors": 0}

    def flush_buffers():
        """バッファをテンソルに変換してバッチリストに追加"""
        for phase in buffers:
            if buffers[phase]["states"]:
                batches[phase]["states"].append(torch.stack(buffers[phase]["states"]))
                batches[phase]["actions"].append(torch.tensor(buffers[phase]["actions"], dtype=torch.long))
                batches[phase]["rewards"].append(torch.tensor(buffers[phase]["rewards"], dtype=torch.float32))
                # バッファをクリア
                buffers[phase]["states"] = []
                buffers[phase]["actions"] = []
                buffers[phase]["rewards"] = []

    with open(input_path) as f:
        for line_no, line in enumerate(f, 1):
            try:
                game_data = json.loads(line)
                kifu_dict = game_data.get("kifu", {})
                winner = kifu_dict.get("winner")

                # 1ゲームを処理
                game_exps = _process_single_game(kifu_dict, winner)

                # フェーズ別に追加
                for phase, exps in game_exps.items():
                    for exp in exps:
                        buffers[phase]["states"].append(exp["state"])
                        buffers[phase]["actions"].append(exp["action"])
                        buffers[phase]["rewards"].append(exp["reward"])
                        stats["experiences"] += 1

                stats["games"] += 1

                # バッファがBATCH_SIZEを超えたらフラッシュ
                total_buffered = sum(len(buffers[p]["states"]) for p in buffers)
                if total_buffered >= BATCH_SIZE:
                    flush_buffers()
                    logger.info(f"処理中: {stats['games']}ゲーム, {stats['experiences']}経験")

            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"行{line_no}でエラー: {e}")

    # 残りのバッファをフラッシュ
    flush_buffers()

    # バッチを結合して保存
    output_data = {}
    for phase in batches:
        if batches[phase]["states"]:
            output_data[f"{phase}_states"] = torch.cat(batches[phase]["states"], dim=0)
            output_data[f"{phase}_actions"] = torch.cat(batches[phase]["actions"], dim=0)
            output_data[f"{phase}_rewards"] = torch.cat(batches[phase]["rewards"], dim=0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(output_data, output_path)

    return stats


def _process_single_game(kifu_dict: dict, winner: Optional[int]) -> dict:
    """1ゲームの棋譜を経験データに変換"""
    # フェーズ別に経験を収集
    exps_by_phase = {
        "piece": [],
        "dest": [],
        "promo": [],
        "shoot": [],
    }

    # プレイヤー別の経験リスト（報酬計算用）
    player_exps = {0: [], 1: []}

    kifu = Kifu.from_dict(kifu_dict)
    engine = GameEngine(create_initial_state())

    # 中間報酬用: 駒価値の追跡
    prev_scores = {
        0: _calc_material_score(engine, 0),
        1: _calc_material_score(engine, 1)
    }

    for move in kifu.moves:
        if engine.is_game_over:
            break

        player = move.player

        if move.move_type == "move":
            # 駒選択の経験
            state = encode_board(engine)
            action = pos_to_index(*move.from_pos)
            exp = {"state": state, "action": action, "reward": 0.0, "phase": "piece"}
            exps_by_phase["piece"].append(exp)
            player_exps[player].append(exp)

            # エンジンを進める
            engine.select_piece(move.from_pos)

            # 移動先選択の経験
            state = encode_board(engine, selected_piece=move.from_pos)
            action = pos_to_index(*move.to_pos)
            exp = {"state": state, "action": action, "reward": 0.0, "phase": "dest"}
            exps_by_phase["dest"].append(exp)
            player_exps[player].append(exp)

            engine.select_destination(move.to_pos)

            # 成り判断の経験
            if engine.phase == GamePhase.PROMOTION:
                state = encode_board(engine)
                action = 1 if move.promoted else 0
                exp = {"state": state, "action": action, "reward": 0.0, "phase": "promo"}
                exps_by_phase["promo"].append(exp)
                player_exps[player].append(exp)
                engine.decide_promotion(move.promoted)

            # 中間報酬: 駒価値の変化
            curr_score = _calc_material_score(engine, player)
            score_delta = (curr_score - prev_scores[player]) / 10000.0
            # 直近の経験に中間報酬を付与
            if player_exps[player]:
                player_exps[player][-1]["reward"] = score_delta
            prev_scores[player] = curr_score

            # 射撃フェーズをスキップ
            while engine.phase == GamePhase.SHOOTING:
                engine.skip_shoot()

        elif move.move_type == "shoot":
            # 射撃は現状スキップ
            pass

    # 最終報酬を付与（減衰付き）
    for player_id in [0, 1]:
        exps = player_exps[player_id]
        n = len(exps)

        if winner == player_id:
            final_reward = 1.0
        elif winner is None:
            final_reward = 0.0
        else:
            final_reward = -1.0

        for i, exp in enumerate(exps):
            decay = 0.99 ** (n - i - 1)
            # 中間報酬 + 最終報酬の組み合わせ
            exp["reward"] = 0.5 * exp["reward"] + 0.5 * final_reward * decay

    return exps_by_phase


def _calc_material_score(engine, player: int) -> float:
    """駒価値の合計を計算"""
    my_score = 0
    opp_score = 0
    for x in range(19):
        for y in range(19):
            piece_data = engine.state.board.get(x, y)
            if piece_data:
                piece_id, owner = piece_data
                value = get_piece_value(piece_id)
                if piece_id in [1, 35]:  # 将/帥は除外
                    continue
                if owner == player:
                    my_score += value
                else:
                    opp_score += value
    return my_score - opp_score


def main():
    parser = argparse.ArgumentParser(description="棋譜を学習用データに変換")
    parser.add_argument("--input", "-i", type=str, required=True,
                        help="入力棋譜ファイル(JSONL)またはディレクトリ")
    parser.add_argument("--output", "-o", type=str, required=True,
                        help="出力ファイル(.pt)")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("convert", level=log_level)

    input_path = Path(args.input)
    output_path = Path(args.output)

    logger.info("=== 棋譜変換 ===")
    logger.info(f"入力: {input_path}")
    logger.info(f"出力: {output_path}")

    if input_path.is_file():
        stats = convert_kifu_file(input_path, output_path, logger)
    elif input_path.is_dir():
        # ディレクトリ内の全JSONLを処理
        all_stats = {"games": 0, "experiences": 0, "errors": 0}
        for jsonl_file in input_path.glob("*.jsonl"):
            logger.info(f"ファイル: {jsonl_file.name}")
            stats = convert_kifu_file(jsonl_file, output_path, logger)
            for k in all_stats:
                all_stats[k] += stats[k]
        stats = all_stats
    else:
        logger.error(f"入力が見つかりません: {input_path}")
        return

    logger.info("=== 完了 ===")
    logger.info(f"ゲーム数: {stats['games']}")
    logger.info(f"経験数: {stats['experiences']}")
    logger.info(f"エラー: {stats['errors']}")

    # 出力ファイルのサイズ
    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"ファイルサイズ: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()

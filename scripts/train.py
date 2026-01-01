"""モデル訓練スクリプト

棋譜ファイル（JSONL/Kifu形式）から教師あり学習または強化学習を行う。
棋譜生成は generate_games.py で行う。

Usage:
    # 棋譜から教師あり学習（勝者の手を真似る）
    python scripts/train.py supervised --data data/games/ --output models/sl_v1 --lite

    # 棋譜から強化学習（RL + IL）
    python scripts/train.py reinforce --data data/games/ --output models/rl_v1 --lite

    # 既存モデルを追加学習
    python scripts/train.py reinforce --data data/games/ --load models/rl_v1 --output models/rl_v2 --lite
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import json
import time
import gc
import random
from pathlib import Path
from typing import Optional
from collections import deque
from dataclasses import dataclass, field

import torch
import torch.optim as optim
import torch.nn.functional as F

from scripts.lib.logger import setup_logger
from ai.neural.model import create_model, encode_board, pos_to_index, NUM_SQUARES
from ai.greedy.piece_values import get_piece_value
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state
from backend.domain.kifu import Kifu, Move


@dataclass
class Experience:
    """訓練用経験データ"""
    state: torch.Tensor  # エンコード済み盤面
    action: int
    phase: str
    reward: float = 0.0
    is_expert: bool = False


def train_supervised(args, logger):
    """教師あり学習（棋譜から）"""
    logger.info("=== 教師あり学習 ===")
    logger.info(f"データ: {args.data}")
    logger.info(f"出力: {args.output}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = _get_device(args.device)
    logger.info(f"デバイス: {device}")

    # モデル
    model = create_model(lite=args.lite, device=str(device))
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    logger.info(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    # 既存モデル読み込み
    if args.load:
        checkpoint = torch.load(args.load, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        logger.info(f"モデル読み込み: {args.load}")

    # データ読み込み（棋譜から経験を生成）
    experiences = _load_experiences_for_sl(args.data, args.winner_only)
    logger.info(f"経験数: {len(experiences)}")

    if not experiences:
        logger.error("訓練データがありません")
        return

    # フェーズごとに分割
    phase_data = {"piece": [], "dest": [], "promo": [], "shoot": []}
    for exp in experiences:
        phase_data[exp.phase].append(exp)

    for phase, data in phase_data.items():
        logger.info(f"  {phase}: {len(data)}")

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(args.epochs):
        start = time.time()
        total_loss = 0
        n_batches = 0

        for phase in ["piece", "dest", "promo", "shoot"]:
            if len(phase_data[phase]) < args.batch_size:
                continue

            random.shuffle(phase_data[phase])
            for i in range(0, len(phase_data[phase]) - args.batch_size, args.batch_size):
                batch = phase_data[phase][i:i + args.batch_size]
                loss = _train_batch_supervised(model, optimizer, batch, phase, device)
                total_loss += loss
                n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        elapsed = time.time() - start

        logger.info(f"Epoch {epoch+1}/{args.epochs}: loss={avg_loss:.4f} ({elapsed:.1f}s)")
        history.append({"epoch": epoch + 1, "loss": avg_loss})

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({"model_state_dict": model.state_dict()}, output_dir / "best_model.pth")
            logger.info(f"  -> best model saved")

        # メモリクリア
        if device.type == "mps":
            torch.mps.empty_cache()
            gc.collect()

    # 最終保存
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict()
    }, output_dir / "final_model.pth")

    with open(output_dir / "history.json", "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"完了: {output_dir}")


def train_reinforce(args, logger):
    """強化学習（棋譜から RL + IL）"""
    logger.info("=== 強化学習 (RL + IL) ===")
    logger.info(f"データ: {args.data}")
    logger.info(f"出力: {args.output}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = _get_device(args.device)
    logger.info(f"デバイス: {device}")

    # モデル
    model = create_model(lite=args.lite, device=str(device))
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # 統計
    start_epoch = 0
    stats = {"total_games": 0, "epochs_completed": 0}

    # 既存モデル読み込み
    if args.load:
        checkpoint = torch.load(args.load, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        logger.info(f"モデル読み込み: {args.load}")

    if args.resume:
        checkpoints = sorted(output_dir.glob("checkpoint_*.pth"))
        if checkpoints:
            latest = checkpoints[-1]
            checkpoint = torch.load(latest, map_location=device)
            model.load_state_dict(checkpoint["model_state_dict"])
            if "optimizer_state_dict" in checkpoint:
                optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            stats = checkpoint.get("stats", stats)
            start_epoch = checkpoint.get("epoch", 0)
            logger.info(f"再開: {latest} (エポック {start_epoch} から)")

    logger.info(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    # データ読み込み（棋譜から経験を生成 + 報酬計算）
    rl_buffers, il_buffers, baseline = _load_experiences_for_rl(args.data)

    rl_total = sum(len(b) for b in rl_buffers.values())
    il_total = sum(len(b) for b in il_buffers.values())
    logger.info(f"RLバッファ: {rl_total}")
    logger.info(f"ILバッファ: {il_total}")
    logger.info(f"ベースライン: {baseline:.3f}")

    if rl_total == 0 and il_total == 0:
        logger.error("訓練データがありません")
        return

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(start_epoch, args.epochs):
        start = time.time()
        total_loss = 0
        n_updates = 0

        # 各フェーズを学習
        for phase in ["piece", "dest", "promo", "shoot"]:
            # RL
            if len(rl_buffers[phase]) >= args.batch_size:
                for _ in range(args.updates_per_epoch):
                    batch = random.sample(list(rl_buffers[phase]), args.batch_size)
                    loss = _train_batch_rl(model, optimizer, batch, phase, baseline, device)
                    total_loss += loss
                    n_updates += 1

            # IL
            if len(il_buffers[phase]) >= args.batch_size:
                for _ in range(args.updates_per_epoch):
                    batch = random.sample(list(il_buffers[phase]), args.batch_size)
                    loss = _train_batch_il(model, optimizer, batch, phase, device)
                    total_loss += loss
                    n_updates += 1

        avg_loss = total_loss / max(n_updates, 1)
        elapsed = time.time() - start

        logger.info(f"Epoch {epoch+1}/{args.epochs}: loss={avg_loss:.4f}, baseline={baseline:.3f} ({elapsed:.1f}s)")
        history.append({"epoch": epoch + 1, "loss": avg_loss, "baseline": baseline})

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({"model_state_dict": model.state_dict()}, output_dir / "best_model.pth")
            logger.info(f"  -> best model saved")

        # チェックポイント
        if (epoch + 1) % args.save_every == 0:
            stats["epochs_completed"] = epoch + 1
            _save_checkpoint(output_dir, epoch + 1, model, optimizer, stats, logger)

        # メモリクリア
        if device.type == "mps":
            torch.mps.empty_cache()
            gc.collect()

    # 最終保存
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "stats": stats
    }, output_dir / "final_model.pth")

    with open(output_dir / "history.json", "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"完了: {output_dir}")


def _load_experiences_for_sl(data_path: str, winner_only: bool) -> list[Experience]:
    """教師あり学習用に棋譜から経験を生成"""
    experiences = []
    data_path = Path(data_path)

    files = [data_path] if data_path.is_file() else list(data_path.glob("*.jsonl"))

    for file_path in files:
        with open(file_path) as f:
            for line in f:
                game_data = json.loads(line)
                kifu_dict = game_data.get("kifu", {})
                winner = kifu_dict.get("winner")

                # 棋譜を再生しながら経験を収集
                game_exps = _replay_kifu_for_experiences(kifu_dict)

                for exp in game_exps:
                    # winner_onlyモードでは勝者の手のみ
                    if winner_only:
                        # expのplayer情報が必要だが、Experienceにはない
                        # 簡略化: 全ての手を使う（minimax同士の場合は勝者側が教師）
                        pass
                    experiences.append(exp)

    return experiences


def _load_experiences_for_rl(data_path: str) -> tuple[dict, dict, float]:
    """強化学習用に棋譜から経験を生成（報酬計算含む）"""
    rl_buffers = {p: deque(maxlen=100000) for p in ["piece", "dest", "promo", "shoot"]}
    il_buffers = {p: deque(maxlen=100000) for p in ["piece", "dest", "promo", "shoot"]}
    all_rewards = []

    data_path = Path(data_path)
    files = [data_path] if data_path.is_file() else list(data_path.glob("*.jsonl"))

    for file_path in files:
        with open(file_path) as f:
            for line in f:
                game_data = json.loads(line)
                kifu_dict = game_data.get("kifu", {})
                players = game_data.get("players", {})
                winner = kifu_dict.get("winner")

                # 勝者のプレイヤータイプを取得
                if winner == 0:
                    winner_type = players.get("sente", "")
                elif winner == 1:
                    winner_type = players.get("gote", "")
                else:
                    winner_type = None

                # 棋譜を再生して経験を収集（報酬付き）
                exps_by_player = _replay_kifu_with_rewards(kifu_dict, winner)

                for player_id, exps in exps_by_player.items():
                    player_type = players.get("sente" if player_id == 0 else "gote", "")
                    is_winner = (player_id == winner)

                    # Minimaxの勝者の手 → IL用（教師データ）
                    # それ以外 → RL用
                    is_expert = is_winner and "minimax" in player_type

                    for exp in exps:
                        if is_expert:
                            il_buffers[exp.phase].append(exp)
                        else:
                            rl_buffers[exp.phase].append(exp)
                            all_rewards.append(exp.reward)

    baseline = sum(all_rewards) / len(all_rewards) if all_rewards else 0
    return rl_buffers, il_buffers, baseline


def _replay_kifu_for_experiences(kifu_dict: dict) -> list[Experience]:
    """棋譜を再生して経験を収集（教師あり学習用）"""
    experiences = []
    kifu = Kifu.from_dict(kifu_dict)

    engine = GameEngine(create_initial_state())

    for move in kifu.moves:
        if engine.is_game_over:
            break

        if move.move_type == "move":
            # 駒選択
            state = encode_board(engine)
            action = pos_to_index(*move.from_pos)
            experiences.append(Experience(state=state, action=action, phase="piece"))

            # エンジンを進める
            engine.select_piece(move.from_pos)

            # 移動先選択
            state = encode_board(engine, selected_piece=move.from_pos)
            action = pos_to_index(*move.to_pos)
            experiences.append(Experience(state=state, action=action, phase="dest"))

            engine.select_destination(move.to_pos)

            # 成り
            if engine.phase == GamePhase.PROMOTION:
                state = encode_board(engine)
                action = 1 if move.promoted else 0
                experiences.append(Experience(state=state, action=action, phase="promo"))
                engine.decide_promotion(move.promoted)

            # 射撃フェーズをスキップ（簡略化）
            while engine.phase == GamePhase.SHOOTING:
                engine.skip_shoot()

        elif move.move_type == "shoot":
            # 射撃は現状スキップ（moveの後に続く射撃は別途処理必要）
            pass

    return experiences


def _replay_kifu_with_rewards(kifu_dict: dict, winner: Optional[int]) -> dict[int, list[Experience]]:
    """棋譜を再生して報酬付き経験を収集（強化学習用）"""
    exps_by_player = {0: [], 1: []}
    kifu = Kifu.from_dict(kifu_dict)

    engine = GameEngine(create_initial_state())

    # 中間報酬用: 各プレイヤーのスコア追跡
    prev_scores = {0: _calc_material_score(engine, 0), 1: _calc_material_score(engine, 1)}

    for move in kifu.moves:
        if engine.is_game_over:
            break

        player = move.player

        if move.move_type == "move":
            # 駒選択
            state = encode_board(engine)
            action = pos_to_index(*move.from_pos)
            exps_by_player[player].append(Experience(state=state, action=action, phase="piece"))

            engine.select_piece(move.from_pos)

            # 移動先選択
            state = encode_board(engine, selected_piece=move.from_pos)
            action = pos_to_index(*move.to_pos)
            exps_by_player[player].append(Experience(state=state, action=action, phase="dest"))

            engine.select_destination(move.to_pos)

            # 成り
            if engine.phase == GamePhase.PROMOTION:
                state = encode_board(engine)
                action = 1 if move.promoted else 0
                exps_by_player[player].append(Experience(state=state, action=action, phase="promo"))
                engine.decide_promotion(move.promoted)

            # 中間報酬計算
            curr_score = _calc_material_score(engine, player)
            score_delta = (curr_score - prev_scores[player]) / 10000.0
            if exps_by_player[player]:
                exps_by_player[player][-1].reward = score_delta
            prev_scores[player] = curr_score

            # 射撃フェーズをスキップ
            while engine.phase == GamePhase.SHOOTING:
                engine.skip_shoot()

    # 最終報酬を付与
    for player_id in [0, 1]:
        exps = exps_by_player[player_id]
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
            exp.reward = 0.5 * exp.reward + 0.5 * final_reward * decay

    return exps_by_player


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


def _train_batch_supervised(model, optimizer, batch, phase, device):
    """教師あり学習バッチ"""
    model.train()

    states = torch.stack([e.state for e in batch]).to(device)
    actions = torch.tensor([e.action for e in batch], dtype=torch.long, device=device)

    optimizer.zero_grad()
    policy_logits, _ = model(states, phase=phase)
    loss = F.cross_entropy(policy_logits, actions)
    loss.backward()
    optimizer.step()

    return loss.item()


def _train_batch_rl(model, optimizer, batch, phase, baseline, device):
    """強化学習バッチ（REINFORCE）"""
    model.train()

    states = torch.stack([e.state for e in batch]).to(device)
    actions = torch.tensor([e.action for e in batch], dtype=torch.long, device=device)
    rewards = torch.tensor([e.reward for e in batch], dtype=torch.float32, device=device)
    advantages = (rewards - baseline).unsqueeze(1)

    optimizer.zero_grad()
    policy_logits, value_pred = model(states, phase=phase)
    log_probs = F.log_softmax(policy_logits, dim=1)
    selected_log_probs = log_probs.gather(1, actions.unsqueeze(1))
    policy_loss = -(selected_log_probs * advantages).mean()
    value_loss = F.mse_loss(value_pred, rewards.unsqueeze(1))
    loss = policy_loss + 0.5 * value_loss
    loss.backward()
    optimizer.step()

    return loss.item()


def _train_batch_il(model, optimizer, batch, phase, device):
    """模倣学習バッチ"""
    model.train()

    states = torch.stack([e.state for e in batch]).to(device)
    actions = torch.tensor([e.action for e in batch], dtype=torch.long, device=device)

    optimizer.zero_grad()
    policy_logits, _ = model(states, phase=phase)
    loss = F.cross_entropy(policy_logits, actions)
    loss.backward()
    optimizer.step()

    return loss.item()


def _save_checkpoint(output_dir, epoch, model, optimizer, stats, logger):
    """チェックポイント保存"""
    path = output_dir / f"checkpoint_{epoch}.pth"
    torch.save({
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "stats": stats,
    }, path)
    logger.info(f"  チェックポイント: {path}")


def _get_device(device_str: str) -> torch.device:
    """デバイス取得"""
    if device_str == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        elif torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    elif device_str == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    elif device_str == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def main():
    parser = argparse.ArgumentParser(description="モデル訓練")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # 教師あり学習
    sup = subparsers.add_parser("supervised", help="教師あり学習")
    sup.add_argument("--data", "-d", type=str, required=True, help="棋譜ファイル/ディレクトリ")
    sup.add_argument("--output", "-o", type=str, default="models/supervised", help="出力ディレクトリ")
    sup.add_argument("--winner-only", action="store_true", help="勝者の手のみ学習")
    sup.add_argument("--epochs", type=int, default=20, help="エポック数")
    sup.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    sup.add_argument("--lr", type=float, default=0.001, help="学習率")
    sup.add_argument("--load", type=str, help="既存モデル読み込み")
    sup.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    sup.add_argument("--lite", action="store_true", help="軽量モデル")
    sup.add_argument("--verbose", "-v", action="store_true")

    # 強化学習
    rl = subparsers.add_parser("reinforce", help="強化学習")
    rl.add_argument("--data", "-d", type=str, required=True, help="棋譜ファイル/ディレクトリ")
    rl.add_argument("--output", "-o", type=str, default="models/reinforce", help="出力ディレクトリ")
    rl.add_argument("--epochs", type=int, default=100, help="エポック数")
    rl.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    rl.add_argument("--updates-per-epoch", type=int, default=10, help="エポックあたりの更新回数")
    rl.add_argument("--lr", type=float, default=0.0001, help="学習率")
    rl.add_argument("--load", type=str, help="既存モデル読み込み")
    rl.add_argument("--resume", action="store_true", help="最新チェックポイントから再開")
    rl.add_argument("--save-every", type=int, default=10, help="保存間隔（エポック）")
    rl.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    rl.add_argument("--lite", action="store_true", help="軽量モデル")
    rl.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("train", level=log_level)

    if args.mode == "supervised":
        train_supervised(args, logger)
    elif args.mode == "reinforce":
        train_reinforce(args, logger)


if __name__ == "__main__":
    main()

"""モデル訓練スクリプト

Usage:
    # 棋譜から教師あり学習
    python scripts/train.py supervised --data data/kifu.json --output models/nn_v1

    # Minimax対戦で強化学習
    python scripts/train.py reinforce --output models/rl_v1 --games 500

    # 既存モデルを追加学習
    python scripts/train.py reinforce --load models/rl_v1 --output models/rl_v2
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import json
import time
import gc
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from scripts.lib.logger import setup_logger, GameLogger
from scripts.lib.game_runner import run_game
from ai.neural.model import create_model, encode_board, pos_to_index, NUM_SQUARES
from ai.neural.player import NeuralPlayer
from ai.minimax.player import MinimaxPlayer
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state


def train_supervised(args, logger):
    """教師あり学習（棋譜から）"""
    from ai.neural.dataset import create_dataloader

    logger.info("=== 教師あり学習 ===")
    logger.info(f"データ: {args.data}")
    logger.info(f"出力: {args.output}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # デバイス
    device = _get_device(args.device)
    logger.info(f"デバイス: {device}")

    # モデル
    model = create_model(lite=args.lite, device=str(device))
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    logger.info(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    # データローダー
    train_loader = create_dataloader(args.data, batch_size=args.batch_size, shuffle=True)

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(args.epochs):
        start = time.time()
        train_loss = _train_supervised_epoch(model, train_loader, optimizer, device)
        elapsed = time.time() - start

        logger.info(f"Epoch {epoch+1}/{args.epochs}: loss={train_loss:.4f} ({elapsed:.1f}s)")
        history.append({"epoch": epoch + 1, "loss": train_loss})

        if train_loss < best_loss:
            best_loss = train_loss
            torch.save({"model_state_dict": model.state_dict()}, output_dir / "best_model.pth")
            logger.info(f"  -> best model saved")

    # 最終保存
    torch.save({"model_state_dict": model.state_dict()}, output_dir / "final_model.pth")
    with open(output_dir / "history.json", "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"完了: {output_dir}")


def _train_supervised_epoch(model, dataloader, optimizer, device):
    """教師あり学習1エポック"""
    model.train()
    total_loss = 0
    n_batches = 0

    for board, target_policy, target_value, _ in dataloader:
        board = board.to(device)
        target_policy = target_policy.to(device)
        target_value = target_value.to(device)

        optimizer.zero_grad()
        policy_logits, value_pred = model(board)

        policy_loss = F.cross_entropy(policy_logits, target_policy)
        value_loss = F.mse_loss(value_pred, target_value)
        loss = policy_loss + 0.5 * value_loss

        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def train_reinforce(args, logger):
    """強化学習（Minimax対戦）"""
    from collections import deque
    from dataclasses import dataclass
    import random

    logger.info("=== 強化学習 (RL + IL) ===")
    logger.info(f"ゲーム数: {args.games}")
    logger.info(f"Minimax深さ: {args.minimax_depth}")
    logger.info(f"出力: {args.output}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # デバイス
    device = _get_device(args.device)
    logger.info(f"デバイス: {device}")

    # モデル
    model = create_model(lite=args.lite, device=str(device))
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # 既存モデル読み込み
    start_game = 0
    stats = {"wins": 0, "losses": 0, "draws": 0}
    epsilon = args.epsilon

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
            epsilon = checkpoint.get("epsilon", epsilon)
            start_game = checkpoint.get("game", 0)
            logger.info(f"再開: {latest} (ゲーム {start_game} から)")

    logger.info(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    # バッファ
    @dataclass
    class Experience:
        state: torch.Tensor
        action: int
        phase: str
        reward: float = 0.0
        is_expert: bool = False

    rl_buffers = {p: deque(maxlen=50000) for p in ["piece", "dest", "promo", "shoot"]}
    il_buffers = {p: deque(maxlen=50000) for p in ["piece", "dest", "promo", "shoot"]}
    reward_history = deque(maxlen=1000)

    minimax = MinimaxPlayer(depth=args.minimax_depth, max_moves=15)
    game_logger = GameLogger(logger, verbose=args.verbose)

    # 訓練ループ
    for game_idx in range(start_game, args.games):
        start_time = time.time()

        nn_is_first = (game_idx % 2 == 0)
        nn_player = NeuralPlayer(model, device, epsilon=epsilon, temperature=1.0)

        # ゲーム実行・経験収集
        nn_exps, mm_exps, winner, nn_id = _play_game_with_recording(
            nn_player, minimax, nn_is_first, model, device, game_logger, game_idx + 1
        )

        # 結果判定
        if winner is None:
            stats["draws"] += 1
            result_str = "引分"
            nn_reward = 0.0
        elif winner == nn_id:
            stats["wins"] += 1
            result_str = "勝利"
            nn_reward = 1.0
        else:
            stats["losses"] += 1
            result_str = "敗北"
            nn_reward = -1.0

        # 経験をバッファに追加
        n = len(nn_exps)
        for i, exp in enumerate(nn_exps):
            exp.reward = nn_reward * (0.99 ** (n - i - 1))
            rl_buffers[exp.phase].append(exp)
            reward_history.append(exp.reward)

        if nn_reward <= 0:
            for exp in mm_exps:
                exp.reward = 1.0
                il_buffers[exp.phase].append(exp)

        # 学習
        baseline = sum(reward_history) / max(len(reward_history), 1)
        loss = _train_from_buffers(model, optimizer, rl_buffers, il_buffers, baseline, device, args.batch_size)

        # ε減衰
        epsilon = max(args.epsilon_min, epsilon * args.epsilon_decay)

        elapsed = time.time() - start_time

        # 進捗表示
        if (game_idx + 1) % 10 == 0:
            win_rate = stats["wins"] / (game_idx + 1) * 100
            logger.info(
                f"ゲーム {game_idx+1}/{args.games}: {result_str} "
                f"(勝率: {win_rate:.1f}%, ε={epsilon:.3f}, loss={loss:.4f}, baseline={baseline:.3f}, {elapsed:.1f}s)"
            )

        # メモリクリア
        if device.type == "mps" and (game_idx + 1) % 5 == 0:
            torch.mps.empty_cache()
            gc.collect()

        # チェックポイント保存
        if (game_idx + 1) % args.save_every == 0:
            _save_checkpoint(output_dir, game_idx + 1, model, optimizer, stats, epsilon, logger)

    # 最終保存
    torch.save({"model_state_dict": model.state_dict(), "stats": stats}, output_dir / "final_model.pth")
    logger.info(f"完了: {output_dir}")
    logger.info(f"勝利: {stats['wins']}, 敗北: {stats['losses']}, 引分: {stats['draws']}")


def _play_game_with_recording(nn_player, minimax, nn_is_first, model, device, game_logger, game_id):
    """ゲームをプレイし、両者の経験を記録"""
    from dataclasses import dataclass

    @dataclass
    class Experience:
        state: torch.Tensor
        action: int
        phase: str
        reward: float = 0.0
        is_expert: bool = False

    engine = GameEngine(create_initial_state())
    nn_id = 0 if nn_is_first else 1
    nn_exps = []
    mm_exps = []

    game_logger.new_game(game_id)

    for turn in range(300):
        if engine.is_game_over:
            break

        current = engine.current_player
        is_nn = (current == nn_id)
        ai = nn_player if is_nn else minimax
        exps = nn_exps if is_nn else mm_exps

        # 各フェーズを記録
        if engine.phase != GamePhase.PIECE_SELECT:
            continue

        # 駒選択
        state = encode_board(engine)
        piece_pos = ai.choose_piece(engine)
        if not engine.select_piece(piece_pos):
            break
        exps.append(Experience(state, pos_to_index(*piece_pos), "piece", is_expert=not is_nn))

        # 移動先
        state = encode_board(engine, selected_piece=engine.selected_piece)
        dest_pos = ai.choose_destination(engine)
        result = engine.select_destination(dest_pos)
        if not result.success:
            break
        exps.append(Experience(state, pos_to_index(*dest_pos), "dest", is_expert=not is_nn))

        # 成り
        if engine.phase == GamePhase.PROMOTION:
            state = encode_board(engine)
            promote = ai.choose_promotion(engine)
            result = engine.decide_promotion(promote)
            if not result.success:
                break
            exps.append(Experience(state, 1 if promote else 0, "promo", is_expert=not is_nn))

        # 射撃
        while engine.phase == GamePhase.SHOOTING:
            state = encode_board(engine)
            target = ai.choose_shoot_target(engine)
            if target:
                idx = pos_to_index(*target)
                result = engine.shoot(target)
                exps.append(Experience(state, idx, "shoot", is_expert=not is_nn))
                if not result.can_shoot:
                    break
            else:
                exps.append(Experience(state, NUM_SQUARES, "shoot", is_expert=not is_nn))
                engine.skip_shoot()
                break

    game_logger.log_game_end(engine.winner, turn, 0)
    return nn_exps, mm_exps, engine.winner, nn_id


def _train_from_buffers(model, optimizer, rl_buffers, il_buffers, baseline, device, batch_size):
    """バッファから学習"""
    import random

    model.train()
    total_loss = 0
    n_updates = 0

    for phase in ["piece", "dest", "promo", "shoot"]:
        # RL
        if len(rl_buffers[phase]) >= batch_size:
            batch = random.sample(list(rl_buffers[phase]), batch_size)
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
            total_loss += loss.item()
            n_updates += 1

        # IL
        if len(il_buffers[phase]) >= batch_size:
            batch = random.sample(list(il_buffers[phase]), batch_size)
            states = torch.stack([e.state for e in batch]).to(device)
            actions = torch.tensor([e.action for e in batch], dtype=torch.long, device=device)

            optimizer.zero_grad()
            policy_logits, _ = model(states, phase=phase)
            loss = F.cross_entropy(policy_logits, actions)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_updates += 1

    return total_loss / max(n_updates, 1)


def _save_checkpoint(output_dir, game, model, optimizer, stats, epsilon, logger):
    """チェックポイント保存"""
    path = output_dir / f"checkpoint_{game}.pth"
    torch.save({
        "game": game,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "stats": stats,
        "epsilon": epsilon,
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
    sup.add_argument("--data", "-d", type=str, required=True, help="訓練データ (JSON/JSONL)")
    sup.add_argument("--output", "-o", type=str, default="models/supervised", help="出力ディレクトリ")
    sup.add_argument("--epochs", type=int, default=20, help="エポック数")
    sup.add_argument("--batch-size", type=int, default=32, help="バッチサイズ")
    sup.add_argument("--lr", type=float, default=0.001, help="学習率")
    sup.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    sup.add_argument("--lite", action="store_true", help="軽量モデル")
    sup.add_argument("--verbose", "-v", action="store_true")

    # 強化学習
    rl = subparsers.add_parser("reinforce", help="強化学習")
    rl.add_argument("--output", "-o", type=str, default="models/reinforce", help="出力ディレクトリ")
    rl.add_argument("--games", "-n", type=int, default=500, help="ゲーム数")
    rl.add_argument("--minimax-depth", type=int, default=2, help="Minimax探索深さ")
    rl.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    rl.add_argument("--lr", type=float, default=0.0001, help="学習率")
    rl.add_argument("--epsilon", type=float, default=0.3, help="探索率")
    rl.add_argument("--epsilon-decay", type=float, default=0.995, help="探索率減衰")
    rl.add_argument("--epsilon-min", type=float, default=0.1, help="探索率下限")
    rl.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    rl.add_argument("--lite", action="store_true", help="軽量モデル")
    rl.add_argument("--load", type=str, help="既存モデル読み込み")
    rl.add_argument("--resume", action="store_true", help="最新チェックポイントから再開")
    rl.add_argument("--save-every", type=int, default=50, help="保存間隔")
    rl.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    # ロガー
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("train", level=log_level)

    if args.mode == "supervised":
        train_supervised(args, logger)
    elif args.mode == "reinforce":
        train_reinforce(args, logger)


if __name__ == "__main__":
    main()

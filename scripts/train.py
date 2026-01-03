"""モデル訓練スクリプト

経験データファイル(.pt)から教師あり学習または強化学習を行う。
経験データは convert_kifu.py で棋譜から生成する。

Usage:
    # 経験データから教師あり学習
    python scripts/train.py supervised --data experiences.pt --output models/sl_v1 --lite

    # 経験データから強化学習
    python scripts/train.py reinforce --data experiences.pt --output models/rl_v1 --lite

    # 既存モデルを追加学習
    python scripts/train.py reinforce --data experiences.pt --load models/rl_v1 --output models/rl_v2 --lite
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

import torch
import torch.optim as optim
import torch.nn.functional as F

from scripts.lib.logger import setup_logger
from ai.neural.model import create_model


def _load_experience_data(data_arg: str, logger) -> dict:
    """経験データを読み込む（複数ファイル対応）

    Args:
        data_arg: ファイルパス（カンマ区切りで複数可）
        logger: ロガー

    Returns:
        フェーズ別のデータ辞書
    """
    # 複数ファイルをカンマで分割
    file_paths = [p.strip() for p in data_arg.split(",")]
    logger.info(f"データファイル: {len(file_paths)}件")

    # フェーズ別にデータを結合
    phase_data = {phase: None for phase in ["piece", "dest", "promo", "shoot", "step"]}
    phase_lists = {phase: {"states": [], "actions": [], "rewards": []} for phase in phase_data}

    for file_path in file_paths:
        data = torch.load(file_path)
        logger.info(f"  読み込み: {file_path}")

        for phase in phase_data:
            key = f"{phase}_states"
            if key in data:
                phase_lists[phase]["states"].append(data[f"{phase}_states"])
                phase_lists[phase]["actions"].append(data[f"{phase}_actions"])
                phase_lists[phase]["rewards"].append(data[f"{phase}_rewards"])

    # 結合
    for phase in phase_data:
        if phase_lists[phase]["states"]:
            phase_data[phase] = {
                "states": torch.cat(phase_lists[phase]["states"], dim=0),
                "actions": torch.cat(phase_lists[phase]["actions"], dim=0),
                "rewards": torch.cat(phase_lists[phase]["rewards"], dim=0),
            }
            logger.info(f"  {phase}: {len(phase_data[phase]['states'])}")

    return phase_data


def train_supervised(args, logger):
    """教師あり学習（経験データから）"""
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

    # 経験データ読み込み（複数ファイル対応）
    phase_data = _load_experience_data(args.data, logger)

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(args.epochs):
        start = time.time()
        total_loss = 0
        n_batches = 0

        for phase in ["piece", "dest", "promo", "shoot", "step"]:
            if phase_data[phase] is None:
                continue

            states = phase_data[phase]["states"]
            actions = phase_data[phase]["actions"]
            n = len(states)

            if n < args.batch_size:
                continue

            # シャッフル用インデックス
            indices = torch.randperm(n)

            for i in range(0, n - args.batch_size, args.batch_size):
                batch_idx = indices[i:i + args.batch_size]
                batch_states = states[batch_idx].to(device)
                batch_actions = actions[batch_idx].to(device)

                loss = _train_batch_supervised(model, optimizer, batch_states, batch_actions, phase)
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
    """強化学習（経験データから）"""
    logger.info("=== 強化学習 ===")
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
    stats = {"epochs_completed": 0}

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

    # 経験データ読み込み（複数ファイル対応）
    phase_data = _load_experience_data(args.data, logger)

    # ベースライン（全報酬の平均）
    all_rewards = []
    for phase in ["piece", "dest", "promo", "shoot", "step"]:
        if phase_data[phase] is not None:
            all_rewards.append(phase_data[phase]["rewards"])
    if all_rewards:
        baseline = torch.cat(all_rewards).mean().item()
    else:
        baseline = 0.0
    logger.info(f"ベースライン: {baseline:.3f}")

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(start_epoch, args.epochs):
        start = time.time()
        total_loss = 0
        n_updates = 0

        for phase in ["piece", "dest", "promo", "shoot", "step"]:
            if phase_data[phase] is None:
                continue

            states = phase_data[phase]["states"]
            actions = phase_data[phase]["actions"]
            rewards = phase_data[phase]["rewards"]
            n = len(states)

            if n < args.batch_size:
                continue

            # ランダムサンプリングで複数回更新
            for _ in range(args.updates_per_epoch):
                batch_idx = torch.randint(0, n, (args.batch_size,))
                batch_states = states[batch_idx].to(device)
                batch_actions = actions[batch_idx].to(device)
                batch_rewards = rewards[batch_idx].to(device)

                loss = _train_batch_rl(model, optimizer, batch_states, batch_actions, batch_rewards, phase, baseline)
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


def _train_batch_supervised(model, optimizer, states, actions, phase):
    """教師あり学習バッチ"""
    model.train()

    optimizer.zero_grad()
    policy_logits, _ = model(states, phase=phase)
    loss = F.cross_entropy(policy_logits, actions)
    loss.backward()
    optimizer.step()

    return loss.item()


def _train_batch_rl(model, optimizer, states, actions, rewards, phase, baseline):
    """強化学習バッチ（REINFORCE）"""
    model.train()

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


def train_td(args, logger):
    """TD学習（価値関数の改善）

    V(s) <- V(s) + α * (target - V(s))
    target = reward (終端) or γ * V(s') (非終端)
    """
    logger.info("=== TD学習 ===")
    logger.info(f"データ: {args.data}")
    logger.info(f"出力: {args.output}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = _get_device(args.device)
    logger.info(f"デバイス: {device}")

    # モデル
    model = create_model(lite=args.lite, device=str(device))
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # 既存モデル読み込み
    if args.load:
        checkpoint = torch.load(args.load, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        logger.info(f"モデル読み込み: {args.load}")

    logger.info(f"パラメータ数: {sum(p.numel() for p in model.parameters()):,}")

    # 経験データ読み込み（複数ファイル対応）
    phase_data = _load_experience_data(args.data, logger)

    gamma = args.gamma
    logger.info(f"γ (割引率): {gamma}")

    # 学習ループ
    best_loss = float("inf")
    history = []

    for epoch in range(args.epochs):
        start = time.time()
        total_loss = 0
        n_batches = 0

        for phase in ["piece", "dest", "promo", "shoot", "step"]:
            if phase_data[phase] is None:
                continue

            states = phase_data[phase]["states"]
            rewards = phase_data[phase]["rewards"]
            n = len(states)

            if n < args.batch_size + 1:
                continue

            # シャッフル用インデックス
            indices = torch.randperm(n - 1)  # 次状態が必要なので-1

            for i in range(0, len(indices) - args.batch_size, args.batch_size):
                batch_idx = indices[i:i + args.batch_size]
                batch_states = states[batch_idx].to(device)
                batch_next_states = states[batch_idx + 1].to(device)
                batch_rewards = rewards[batch_idx].to(device)

                loss = _train_batch_td(
                    model, optimizer, batch_states, batch_next_states,
                    batch_rewards, phase, gamma
                )
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


def _train_batch_td(model, optimizer, states, next_states, rewards, phase, gamma):
    """TD(0)学習バッチ

    target = reward + γ * V(s')  (非終端)
           = reward              (終端: reward != 0)
    """
    model.train()

    optimizer.zero_grad()

    # 現在状態の価値予測
    _, value_pred = model(states, phase=phase)

    # 次状態の価値（勾配なし）
    with torch.no_grad():
        _, next_value = model(next_states, phase=phase)

    # TD target: 報酬が0でない場合は終端状態とみなす
    # 終端状態では次状態の価値は使わない
    is_terminal = (rewards != 0).float().unsqueeze(1)
    td_target = rewards.unsqueeze(1) + gamma * next_value * (1 - is_terminal)

    # TD誤差
    loss = F.mse_loss(value_pred, td_target)
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
    sup.add_argument("--data", "-d", type=str, required=True, help="経験データファイル(.pt)")
    sup.add_argument("--output", "-o", type=str, default="models/supervised", help="出力ディレクトリ")
    sup.add_argument("--epochs", type=int, default=20, help="エポック数")
    sup.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    sup.add_argument("--lr", type=float, default=0.001, help="学習率")
    sup.add_argument("--load", type=str, help="既存モデル読み込み")
    sup.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    sup.add_argument("--lite", action="store_true", help="軽量モデル")
    sup.add_argument("--verbose", "-v", action="store_true")

    # 強化学習
    rl = subparsers.add_parser("reinforce", help="強化学習")
    rl.add_argument("--data", "-d", type=str, required=True, help="経験データファイル(.pt)")
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

    # TD学習
    td = subparsers.add_parser("td", help="TD学習（価値関数改善）")
    td.add_argument("--data", "-d", type=str, required=True, help="経験データファイル(.pt)")
    td.add_argument("--output", "-o", type=str, default="models/td", help="出力ディレクトリ")
    td.add_argument("--epochs", type=int, default=20, help="エポック数")
    td.add_argument("--batch-size", type=int, default=64, help="バッチサイズ")
    td.add_argument("--lr", type=float, default=0.0001, help="学習率")
    td.add_argument("--gamma", type=float, default=0.99, help="割引率")
    td.add_argument("--load", type=str, help="既存モデル読み込み")
    td.add_argument("--device", type=str, default="auto", choices=["auto", "mps", "cuda", "cpu"])
    td.add_argument("--lite", action="store_true", help="軽量モデル")
    td.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger("train", level=log_level)

    if args.mode == "supervised":
        train_supervised(args, logger)
    elif args.mode == "reinforce":
        train_reinforce(args, logger)
    elif args.mode == "td":
        train_td(args, logger)


if __name__ == "__main__":
    main()

"""ニューラルネットワークの学習スクリプト"""

import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
import time
import json

from model import create_model
from dataset import create_dataloader


def train_epoch(model, dataloader, optimizer, device, policy_weight=1.0, value_weight=1.0):
    """1エポック学習"""
    model.train()

    total_loss = 0.0
    total_policy_loss = 0.0
    total_value_loss = 0.0
    num_batches = 0

    policy_criterion = nn.CrossEntropyLoss()
    value_criterion = nn.MSELoss()

    for batch_idx, (board, target_move, target_value) in enumerate(dataloader):
        board = board.to(device)
        target_move = target_move.to(device)
        target_value = target_value.to(device)

        optimizer.zero_grad()

        # Forward pass
        policy_logits, value_pred = model(board)

        # Loss計算
        policy_loss = policy_criterion(policy_logits, target_move)
        value_loss = value_criterion(value_pred, target_value)

        loss = policy_weight * policy_loss + value_weight * value_loss

        # Backward pass
        loss.backward()
        optimizer.step()

        # 統計
        total_loss += loss.item()
        total_policy_loss += policy_loss.item()
        total_value_loss += value_loss.item()
        num_batches += 1

        if (batch_idx + 1) % 100 == 0:
            avg_loss = total_loss / num_batches
            avg_policy = total_policy_loss / num_batches
            avg_value = total_value_loss / num_batches
            print(f"  バッチ {batch_idx+1}/{len(dataloader)}: "
                  f"Loss={avg_loss:.4f} (Policy={avg_policy:.4f}, Value={avg_value:.4f})")

    avg_loss = total_loss / num_batches
    avg_policy = total_policy_loss / num_batches
    avg_value = total_value_loss / num_batches

    return avg_loss, avg_policy, avg_value


def evaluate(model, dataloader, device):
    """評価"""
    model.eval()

    total_loss = 0.0
    total_policy_loss = 0.0
    total_value_loss = 0.0
    num_batches = 0

    policy_criterion = nn.CrossEntropyLoss()
    value_criterion = nn.MSELoss()

    with torch.no_grad():
        for board, target_move, target_value in dataloader:
            board = board.to(device)
            target_move = target_move.to(device)
            target_value = target_value.to(device)

            policy_logits, value_pred = model(board)

            policy_loss = policy_criterion(policy_logits, target_move)
            value_loss = value_criterion(value_pred, target_value)

            total_loss += (policy_loss + value_loss).item()
            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            num_batches += 1

    avg_loss = total_loss / num_batches
    avg_policy = total_policy_loss / num_batches
    avg_value = total_value_loss / num_batches

    return avg_loss, avg_policy, avg_value


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NN学習")
    parser.add_argument("--data", type=str, required=True, help="training_data.jsonl のパス")
    parser.add_argument("--output", type=str, default="models/koushougi_net", help="モデル保存先")
    parser.add_argument("--epochs", type=int, default=20, help="エポック数")
    parser.add_argument("--batch-size", type=int, default=32, help="バッチサイズ")
    parser.add_argument("--lr", type=float, default=0.001, help="学習率")
    parser.add_argument("--device", type=str, default="mps", choices=["mps", "cuda", "cpu"], help="デバイス")
    parser.add_argument("--lite", action="store_true", help="軽量モデルを使用")
    parser.add_argument("--val-split", type=float, default=0.1, help="検証データの割合")
    args = parser.parse_args()

    # 出力ディレクトリ作成
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== NN学習開始 ===")
    print(f"データ: {args.data}")
    print(f"出力先: {output_dir}")
    print(f"エポック数: {args.epochs}")
    print(f"バッチサイズ: {args.batch_size}")
    print(f"学習率: {args.lr}")
    print(f"デバイス: {args.device}")
    print(f"軽量モデル: {args.lite}")
    print()

    # デバイス設定
    if args.device == "mps" and torch.backends.mps.is_available():
        device = torch.device("mps")
        print("Using MPS (Apple Silicon)")
    elif args.device == "cuda" and torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"Using CUDA: {torch.cuda.get_device_name(0)}")
    else:
        device = torch.device("cpu")
        print("Using CPU")

    # モデル作成
    print("\nモデル作成中...")
    model = create_model(lite=args.lite, device=args.device)
    num_params = sum(p.numel() for p in model.parameters())
    print(f"パラメータ数: {num_params:,}")

    # データローダー作成
    print("\nデータローダー作成中...")
    train_loader = create_dataloader(args.data, batch_size=args.batch_size, shuffle=True, num_workers=0)

    # オプティマイザ
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # 学習
    print("\n=== 学習開始 ===")
    history = {
        "train_loss": [],
        "train_policy": [],
        "train_value": []
    }

    best_loss = float("inf")

    for epoch in range(args.epochs):
        print(f"\nエポック {epoch+1}/{args.epochs}")
        start_time = time.time()

        train_loss, train_policy, train_value = train_epoch(
            model, train_loader, optimizer, device
        )

        elapsed = time.time() - start_time

        print(f"  完了: {elapsed:.1f}秒")
        print(f"  Train Loss: {train_loss:.4f} (Policy={train_policy:.4f}, Value={train_value:.4f})")

        history["train_loss"].append(train_loss)
        history["train_policy"].append(train_policy)
        history["train_value"].append(train_value)

        # モデル保存
        if train_loss < best_loss:
            best_loss = train_loss
            checkpoint_path = output_dir / "best_model.pth"
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "train_loss": train_loss,
            }, checkpoint_path)
            print(f"  ベストモデル保存: {checkpoint_path}")

    # 最終モデル保存
    final_path = output_dir / "final_model.pth"
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
    }, final_path)

    # 学習履歴保存
    history_path = output_dir / "training_history.json"
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    print("\n=== 学習完了 ===")
    print(f"ベストモデル: {output_dir / 'best_model.pth'}")
    print(f"最終モデル: {final_path}")
    print(f"学習履歴: {history_path}")


if __name__ == "__main__":
    main()

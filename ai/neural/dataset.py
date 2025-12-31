"""Minimax教師データのDataset"""

import json
import torch
from torch.utils.data import Dataset
from pathlib import Path


class MinimaxDataset(Dataset):
    """Minimaxの指し手を教師データとして使うDataset"""

    def __init__(self, data_file: str, num_piece_types=58):
        """
        Args:
            data_file: training_data.jsonl のパス
            num_piece_types: 駒の種類数
        """
        self.data_file = Path(data_file)
        self.num_piece_types = num_piece_types
        self.positions = []

        # データ読み込み
        print(f"データ読み込み中: {data_file}")
        with open(data_file, "r") as f:
            for line in f:
                game = json.loads(line)
                winner = game["winner"]

                for pos_data in game["positions"]:
                    board_state = pos_data["board_state"]
                    move = pos_data["move"]

                    # 勝者情報を追加
                    self.positions.append({
                        "board_state": board_state,
                        "move": move,
                        "winner": winner
                    })

        print(f"読み込み完了: {len(self.positions)}局面")

    def __len__(self):
        return len(self.positions)

    def __getitem__(self, idx):
        """
        Returns:
            board_tensor: [117, 19, 19] 盤面テンソル
            target_move: [361] 目標の手（one-hot）
            target_value: [1] 目標の評価値（勝率）
        """
        position = self.positions[idx]
        board_state = position["board_state"]
        move = position["move"]
        winner = position["winner"]
        current_player = board_state["current_player"]

        # 盤面をテンソルに変換
        board_tensor = self._encode_board(board_state)

        # 手をone-hotに変換
        to_x, to_y = move["to"]
        target_idx = to_y * 19 + to_x
        target_move = torch.zeros(19 * 19)
        target_move[target_idx] = 1.0

        # 評価値（勝率）を設定
        if winner is None:
            # 引き分け
            target_value = torch.tensor([0.0])
        elif winner == current_player:
            # 勝ち
            target_value = torch.tensor([1.0])
        else:
            # 負け
            target_value = torch.tensor([-1.0])

        return board_tensor, target_move, target_value

    def _encode_board(self, board_state):
        """
        盤面をテンソルに変換

        Returns:
            tensor: [117, 19, 19]
                - チャンネル 0-57: プレイヤー0の各駒種
                - チャンネル 58-115: プレイヤー1の各駒種
                - チャンネル 116: 現在のプレイヤー（0 or 1で埋める）
        """
        tensor = torch.zeros(2 * self.num_piece_types + 1, 19, 19)

        # 駒を配置
        for piece_info in board_state["board"]:
            x = piece_info["x"]
            y = piece_info["y"]
            piece_id = piece_info["piece_id"]
            owner = piece_info["owner"]

            # チャンネルインデックス
            channel = owner * self.num_piece_types + piece_id
            tensor[channel, y, x] = 1.0

        # 現在のプレイヤー
        current_player = board_state["current_player"]
        tensor[2 * self.num_piece_types, :, :] = float(current_player)

        return tensor


def create_dataloader(data_file: str, batch_size=32, shuffle=True, num_workers=4):
    """
    DataLoaderを作成

    Args:
        data_file: training_data.jsonl のパス
        batch_size: バッチサイズ
        shuffle: シャッフルするか
        num_workers: データローダーのワーカー数

    Returns:
        dataloader: torch.utils.data.DataLoader
    """
    dataset = MinimaxDataset(data_file)

    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True
    )

    return dataloader


if __name__ == "__main__":
    # テスト
    import sys
    if len(sys.argv) < 2:
        print("Usage: python dataset.py <data_file>")
        sys.exit(1)

    dataloader = create_dataloader(sys.argv[1], batch_size=8)

    print(f"データローダー作成完了")
    print(f"バッチ数: {len(dataloader)}")

    # 最初のバッチを確認
    for batch_idx, (board, move, value) in enumerate(dataloader):
        print(f"\nバッチ {batch_idx}:")
        print(f"  Board shape: {board.shape}")
        print(f"  Move shape: {move.shape}")
        print(f"  Value shape: {value.shape}")
        print(f"  Value range: [{value.min():.2f}, {value.max():.2f}]")
        break

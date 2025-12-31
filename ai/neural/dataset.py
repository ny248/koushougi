"""訓練データのDataset"""

import json
import torch
from torch.utils.data import Dataset
from pathlib import Path

from .model import NUM_PIECE_TYPES, BOARD_SIZE, NUM_SQUARES, move_to_policy_index


class MinimaxDataset(Dataset):
    """Minimaxの指し手を教師データとして使うDataset"""

    def __init__(self, data_file: str):
        """
        Args:
            data_file: training_data.jsonl のパス
        """
        self.data_file = Path(data_file)
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
            target_policy: int - 目標の手（駒ID * 361 + to_idx）
            target_value: [1] 目標の評価値（勝率）
            target_capture: [1] 取った駒の価値
        """
        position = self.positions[idx]
        board_state = position["board_state"]
        move = position["move"]
        winner = position["winner"]
        current_player = board_state["current_player"]

        # 盤面をテンソルに変換
        board_tensor = self._encode_board(board_state)

        # 移動元の駒IDを取得
        from_x, from_y = move["from"]
        piece_id = self._get_piece_id_at(board_state, from_x, from_y)

        # 手をpolicy indexに変換
        to_x, to_y = move["to"]
        target_policy = move_to_policy_index(piece_id, to_x, to_y)

        # 評価値（勝率）を設定
        if winner is None:
            target_value = torch.tensor([0.0])
        elif winner == current_player:
            target_value = torch.tensor([1.0])
        else:
            target_value = torch.tensor([-1.0])

        # 取った駒の価値
        captured_value = self._get_capture_value(board_state, to_x, to_y)
        target_capture = torch.tensor([captured_value])

        return board_tensor, target_policy, target_value, target_capture

    def _encode_board(self, board_state):
        """盤面をテンソルに変換"""
        tensor = torch.zeros(2 * NUM_PIECE_TYPES + 1, BOARD_SIZE, BOARD_SIZE)

        for piece_info in board_state["board"]:
            x = piece_info["x"]
            y = piece_info["y"]
            piece_id = piece_info["piece_id"]
            owner = piece_info["owner"]

            channel = owner * NUM_PIECE_TYPES + piece_id
            tensor[channel, y, x] = 1.0

        current_player = board_state["current_player"]
        tensor[2 * NUM_PIECE_TYPES, :, :] = float(current_player)

        return tensor

    def _get_piece_id_at(self, board_state, x, y):
        """指定位置の駒IDを取得"""
        for piece_info in board_state["board"]:
            if piece_info["x"] == x and piece_info["y"] == y:
                return piece_info["piece_id"]
        return 0  # 見つからない場合

    def _get_capture_value(self, board_state, to_x, to_y):
        """移動先の駒の価値を取得（取る駒がなければ0）"""
        from ai.greedy.piece_values import get_piece_value

        for piece_info in board_state["board"]:
            if piece_info["x"] == to_x and piece_info["y"] == to_y:
                return get_piece_value(piece_info["piece_id"]) / 1000.0  # 正規化
        return 0.0


def create_dataloader(data_file: str, batch_size=32, shuffle=True, num_workers=0):
    """DataLoaderを作成"""
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
    import sys
    if len(sys.argv) < 2:
        print("Usage: python dataset.py <data_file>")
        sys.exit(1)

    dataloader = create_dataloader(sys.argv[1], batch_size=8)

    print(f"データローダー作成完了")
    print(f"バッチ数: {len(dataloader)}")

    for batch_idx, (board, policy, value, capture) in enumerate(dataloader):
        print(f"\nバッチ {batch_idx}:")
        print(f"  Board shape: {board.shape}")
        print(f"  Policy shape: {policy.shape}")
        print(f"  Value shape: {value.shape}")
        print(f"  Capture shape: {capture.shape}")
        break

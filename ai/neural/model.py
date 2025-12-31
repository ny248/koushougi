"""広将棋用のニューラルネットワークモデル - 階層的フェーズ分離型

各フェーズごとに軽量な出力を行う:
- 駒選択: 361次元（どの位置の駒を動かすか）
- 移動先選択: 361次元（どこへ動かすか）
- 成り判断: 2次元（成る/成らない）
- 射撃選択: 362次元（射撃先 or スキップ）
- 価値: 1次元（局面評価 -1〜1）
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


# 定数
NUM_PIECE_TYPES = 58  # 駒の種類数（0=空、1-57=駒）
BOARD_SIZE = 19
NUM_SQUARES = BOARD_SIZE * BOARD_SIZE  # 361


class ResidualBlock(nn.Module):
    """残差ブロック"""

    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x):
        residual = x
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.bn2(self.conv2(x))
        x += residual
        x = F.relu(x)
        return x


class PolicyHead(nn.Module):
    """ポリシーヘッド（軽量）"""

    def __init__(self, in_channels, out_size):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, 16, kernel_size=1)
        self.bn = nn.BatchNorm2d(16)
        self.fc = nn.Linear(16 * NUM_SQUARES, out_size)

    def forward(self, x):
        x = F.relu(self.bn(self.conv(x)))
        x = x.view(x.size(0), -1)
        return self.fc(x)


class ValueHead(nn.Module):
    """価値ヘッド"""

    def __init__(self, in_channels):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, 8, kernel_size=1)
        self.bn = nn.BatchNorm2d(8)
        self.fc1 = nn.Linear(8 * NUM_SQUARES, 64)
        self.fc2 = nn.Linear(64, 1)

    def forward(self, x):
        x = F.relu(self.bn(self.conv(x)))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        return torch.tanh(self.fc2(x))


class KoushougiNet(nn.Module):
    """
    広将棋用の階層的Policy-Valueネットワーク

    共有バックボーン + フェーズ別ヘッド
    """

    def __init__(self, channels=64, num_res_blocks=3):
        """
        Args:
            channels: 中間層のチャンネル数
            num_res_blocks: 残差ブロック数
        """
        super().__init__()

        # 入力チャンネル:
        # - 各プレイヤーの駒配置 (2 * NUM_PIECE_TYPES)
        # - 手番 (1)
        # - コンテキスト: 選択済み駒位置 (1)
        # = 118
        self.input_channels = 2 * NUM_PIECE_TYPES + 2

        # 入力層
        self.input_conv = nn.Conv2d(self.input_channels, channels, kernel_size=3, padding=1)
        self.input_bn = nn.BatchNorm2d(channels)

        # 残差ブロック（共有）
        self.res_blocks = nn.ModuleList([
            ResidualBlock(channels) for _ in range(num_res_blocks)
        ])

        # フェーズ別ヘッド
        self.piece_head = PolicyHead(channels, NUM_SQUARES)      # 駒選択: 361
        self.dest_head = PolicyHead(channels, NUM_SQUARES)       # 移動先: 361
        self.promo_head = PolicyHead(channels, 2)                # 成り: 2
        self.shoot_head = PolicyHead(channels, NUM_SQUARES + 1)  # 射撃: 362 (361 + skip)

        # 価値ヘッド（共有）
        self.value_head = ValueHead(channels)

    def forward(self, x, phase="piece"):
        """
        Args:
            x: [batch, 118, 19, 19] 盤面テンソル + コンテキスト
            phase: "piece", "dest", "promo", "shoot"

        Returns:
            policy: フェーズに応じた出力
            value: [batch, 1] 局面評価値
        """
        # 共有バックボーン
        x = F.relu(self.input_bn(self.input_conv(x)))
        for block in self.res_blocks:
            x = block(x)

        # 価値（常に出力）
        value = self.value_head(x)

        # フェーズ別ポリシー
        if phase == "piece":
            policy = self.piece_head(x)
        elif phase == "dest":
            policy = self.dest_head(x)
        elif phase == "promo":
            policy = self.promo_head(x)
        elif phase == "shoot":
            policy = self.shoot_head(x)
        else:
            raise ValueError(f"Unknown phase: {phase}")

        return policy, value


class KoushougiNetLite(nn.Module):
    """軽量版"""

    def __init__(self, channels=32, num_res_blocks=2):
        super().__init__()

        self.input_channels = 2 * NUM_PIECE_TYPES + 2

        # 入力層
        self.input_conv = nn.Conv2d(self.input_channels, channels, kernel_size=3, padding=1)
        self.input_bn = nn.BatchNorm2d(channels)

        # 残差ブロック
        self.res_blocks = nn.ModuleList([
            ResidualBlock(channels) for _ in range(num_res_blocks)
        ])

        # フェーズ別ヘッド
        self.piece_head = PolicyHead(channels, NUM_SQUARES)
        self.dest_head = PolicyHead(channels, NUM_SQUARES)
        self.promo_head = PolicyHead(channels, 2)
        self.shoot_head = PolicyHead(channels, NUM_SQUARES + 1)

        # 価値ヘッド
        self.value_head = ValueHead(channels)

    def forward(self, x, phase="piece"):
        x = F.relu(self.input_bn(self.input_conv(x)))
        for block in self.res_blocks:
            x = block(x)

        value = self.value_head(x)

        if phase == "piece":
            policy = self.piece_head(x)
        elif phase == "dest":
            policy = self.dest_head(x)
        elif phase == "promo":
            policy = self.promo_head(x)
        elif phase == "shoot":
            policy = self.shoot_head(x)
        else:
            raise ValueError(f"Unknown phase: {phase}")

        return policy, value


def create_model(lite=True, device="mps"):
    """モデルを作成"""
    if lite:
        model = KoushougiNetLite()
    else:
        model = KoushougiNet()

    # デバイスに移動
    if device == "mps" and torch.backends.mps.is_available():
        model = model.to("mps")
    elif device == "cuda" and torch.cuda.is_available():
        model = model.to("cuda")
    else:
        model = model.to("cpu")

    return model


def encode_board(engine, selected_piece=None) -> torch.Tensor:
    """盤面をテンソルにエンコード

    Args:
        engine: GameEngine
        selected_piece: 選択中の駒位置 (x, y) or None

    Returns:
        tensor: [118, 19, 19]
    """
    tensor = torch.zeros(2 * NUM_PIECE_TYPES + 2, BOARD_SIZE, BOARD_SIZE)

    # 駒配置
    for x in range(BOARD_SIZE):
        for y in range(BOARD_SIZE):
            piece_data = engine.state.board.get(x, y)
            if piece_data:
                piece_id, owner = piece_data
                channel = owner * NUM_PIECE_TYPES + piece_id
                tensor[channel, y, x] = 1.0

    # 手番
    tensor[2 * NUM_PIECE_TYPES, :, :] = float(engine.current_player)

    # 選択中の駒位置（コンテキスト）
    if selected_piece:
        sx, sy = selected_piece
        tensor[2 * NUM_PIECE_TYPES + 1, sy, sx] = 1.0

    return tensor


def pos_to_index(x: int, y: int) -> int:
    """座標をインデックスに変換"""
    return y * BOARD_SIZE + x


def index_to_pos(idx: int) -> tuple[int, int]:
    """インデックスを座標に変換"""
    return idx % BOARD_SIZE, idx // BOARD_SIZE


if __name__ == "__main__":
    # テスト
    print("Testing KoushougiNet (Hierarchical)...")
    model = create_model(lite=True, device="cpu")

    # ダミー入力
    batch_size = 4
    x = torch.randn(batch_size, 118, 19, 19)

    # 各フェーズをテスト
    for phase in ["piece", "dest", "promo", "shoot"]:
        policy, value = model(x, phase=phase)
        print(f"Phase '{phase}': policy shape = {policy.shape}")

    print(f"Value shape: {value.shape}")
    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

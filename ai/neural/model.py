"""広将棋用のニューラルネットワークモデル"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class KoushougiNet(nn.Module):
    """
    広将棋用のPolicy-Valueネットワーク

    入力: 19x19の盤面（チャンネル = 駒の種類 × 所有者）
    出力1 (policy): 各マスへの移動確率 (19x19)
    出力2 (value): 局面評価値 (勝率 0-1)
    """

    def __init__(self, num_piece_types=58, channels=128):
        """
        Args:
            num_piece_types: 駒の種類数（空マス含む）
            channels: 中間層のチャンネル数
        """
        super().__init__()

        # 入力: 各プレイヤーの駒配置 (2 * num_piece_types channels)
        # + 現在のプレイヤー (1 channel) = 2 * 58 + 1 = 117 channels
        input_channels = 2 * num_piece_types + 1

        # Convolutional layers
        self.conv1 = nn.Conv2d(input_channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)

        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

        self.conv3 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(channels)

        # Residual blocks
        self.res1 = ResidualBlock(channels)
        self.res2 = ResidualBlock(channels)
        self.res3 = ResidualBlock(channels)

        # Policy head (次の手の確率分布)
        self.policy_conv = nn.Conv2d(channels, 32, kernel_size=1)
        self.policy_bn = nn.BatchNorm2d(32)
        self.policy_fc = nn.Linear(32 * 19 * 19, 19 * 19)

        # Value head (局面評価値)
        self.value_conv = nn.Conv2d(channels, 16, kernel_size=1)
        self.value_bn = nn.BatchNorm2d(16)
        self.value_fc1 = nn.Linear(16 * 19 * 19, 256)
        self.value_fc2 = nn.Linear(256, 1)

    def forward(self, x):
        """
        Args:
            x: [batch, channels, 19, 19] 盤面テンソル

        Returns:
            policy: [batch, 19*19] 各マスへの移動確率（logits）
            value: [batch, 1] 局面評価値（勝率 0-1）
        """
        # Feature extraction
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))

        # Residual blocks
        x = self.res1(x)
        x = self.res2(x)
        x = self.res3(x)

        # Policy head
        policy = F.relu(self.policy_bn(self.policy_conv(x)))
        policy = policy.view(policy.size(0), -1)
        policy = self.policy_fc(policy)

        # Value head
        value = F.relu(self.value_bn(self.value_conv(x)))
        value = value.view(value.size(0), -1)
        value = F.relu(self.value_fc1(value))
        value = torch.tanh(self.value_fc2(value))

        return policy, value


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


class KoushougiNetLite(nn.Module):
    """
    軽量版: メモリ節約、学習高速化
    Residual blockを減らし、チャンネル数も削減
    """

    def __init__(self, num_piece_types=58, channels=64):
        super().__init__()

        input_channels = 2 * num_piece_types + 1

        # Simpler architecture
        self.conv1 = nn.Conv2d(input_channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)

        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

        # Just one residual block
        self.res1 = ResidualBlock(channels)

        # Policy head
        self.policy_conv = nn.Conv2d(channels, 16, kernel_size=1)
        self.policy_bn = nn.BatchNorm2d(16)
        self.policy_fc = nn.Linear(16 * 19 * 19, 19 * 19)

        # Value head
        self.value_conv = nn.Conv2d(channels, 8, kernel_size=1)
        self.value_bn = nn.BatchNorm2d(8)
        self.value_fc1 = nn.Linear(8 * 19 * 19, 128)
        self.value_fc2 = nn.Linear(128, 1)

    def forward(self, x):
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = self.res1(x)

        # Policy head
        policy = F.relu(self.policy_bn(self.policy_conv(x)))
        policy = policy.view(policy.size(0), -1)
        policy = self.policy_fc(policy)

        # Value head
        value = F.relu(self.value_bn(self.value_conv(x)))
        value = value.view(value.size(0), -1)
        value = F.relu(self.value_fc1(value))
        value = torch.tanh(self.value_fc2(value))

        return policy, value


def create_model(lite=True, device="mps"):
    """
    モデルを作成

    Args:
        lite: Trueなら軽量版、Falseなら通常版
        device: "mps" (Apple M1/M2), "cuda", or "cpu"

    Returns:
        model: KoushougiNet or KoushougiNetLite
    """
    if lite:
        model = KoushougiNetLite()
    else:
        model = KoushougiNet()

    # デバイスに移動
    if device == "mps" and torch.backends.mps.is_available():
        model = model.to("mps")
        print(f"Using MPS (Apple Silicon)")
    elif device == "cuda" and torch.cuda.is_available():
        model = model.to("cuda")
        print(f"Using CUDA")
    else:
        model = model.to("cpu")
        print(f"Using CPU")

    return model


if __name__ == "__main__":
    # テスト
    model = create_model(lite=True)

    # ダミー入力
    batch_size = 4
    x = torch.randn(batch_size, 117, 19, 19)

    # デバイスに移動
    device = next(model.parameters()).device
    x = x.to(device)

    # Forward pass
    policy, value = model(x)

    print(f"Input shape: {x.shape}")
    print(f"Policy shape: {policy.shape}")
    print(f"Value shape: {value.shape}")
    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

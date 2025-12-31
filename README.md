# 広将棋 (Koushougi)

広将棋を人間同士またはAIと対戦できるプロジェクトです。

## 概要

- 19x19の盤面で34種類の駒を使う歴史的な将棋variant
- Pygame GUIでの対戦
- 複数のAIプレイヤー（Random, Greedy, Minimax, Neural）

## インストール

```bash
pip install pygame torch
```

## 使い方

### GUI対戦

```bash
python frontend/pygame/game_app.py
```

### AI同士の対戦

```bash
python scripts/battle.py --player1 minimax --player2 greedy --games 10
```

### ニューラルネットワーク訓練

```bash
# Minimaxとの対戦で強化学習
python scripts/training/train_vs_minimax.py --games 500 --lite --eval-every 100

# 評価履歴の確認
cat models/koushougi_rl/training_stats.json
```

### テスト

```bash
python -m pytest tests/ -v
```

## ディレクトリ構成

```
.
├── backend/                 # ゲームロジック
│   ├── domain/              # 盤面・駒・ゲーム状態
│   │   ├── board.py
│   │   ├── game_state.py
│   │   ├── kifu.py          # 棋譜（undo用）
│   │   ├── piece_registry.py
│   │   └── pieces/          # 34種+成り駒の定義
│   └── rules/               # ルール処理
│       ├── game_engine.py   # フェーズ分離型ゲームエンジン
│       ├── movement.py
│       ├── promotion.py
│       └── victory.py
│
├── frontend/                # UI
│   └── pygame/              # Pygame GUI
│       ├── game_app.py
│       ├── renderer.py
│       └── menu.py
│
├── ai/                      # AIプレイヤー（実行時）
│   ├── base.py              # BaseAI抽象クラス
│   ├── random/              # ランダムAI
│   │   └── player.py
│   ├── greedy/              # Greedy AI（駒価値ベース）
│   │   ├── player.py
│   │   └── piece_values.py
│   ├── minimax/             # Minimax AI（Alpha-Beta枝刈り）
│   │   ├── player.py
│   │   └── evaluator.py
│   └── neural/              # ニューラルネットワークAI
│       ├── player.py        # NeuralPlayer
│       └── model.py         # 階層的NNモデル
│
├── scripts/                 # 訓練・分析スクリプト（開発時）
│   ├── training/            # 訓練スクリプト
│   │   ├── train_vs_minimax.py  # Minimax対戦による強化学習
│   │   └── train_values.py      # 駒価値学習
│   ├── analysis/            # 分析スクリプト
│   │   ├── collect_kifu.py
│   │   └── kifu_analyzer.py
│   └── battle.py            # AI対戦評価
│
├── models/                  # 学習済みモデル
│   └── koushougi_rl/        # 強化学習モデル
│       ├── checkpoint_*.pth
│       ├── final_model.pth
│       └── training_stats.json  # 評価履歴
│
├── tests/
│   └── unit/
├── docs/
│   └── notes/
├── GAMERULE.md              # 完全なゲームルール
└── config.py
```

## アーキテクチャ

### フェーズ分離型ゲームエンジン

ゲームの状態遷移を明確なフェーズで管理：

```
PIECE_SELECT → DEST_SELECT → PROMOTION → SHOOTING → (次のターン)
```

- `select_piece()`: 動かす駒を選択
- `select_destination()`: 移動先を選択
- `decide_promotion()`: 成るか否かを決定
- `shoot()` / `skip_shoot()`: 射撃（複数回可能な駒もある）

### AIインターフェース

全てのAIは`BaseAI`を継承し、フェーズごとに決定を行う：

```python
class BaseAI(ABC):
    def choose_piece(self, engine) -> tuple[int, int]
    def choose_destination(self, engine) -> tuple[int, int]
    def choose_promotion(self, engine) -> bool
    def choose_shoot_target(self, engine) -> Optional[tuple[int, int]]
    def play_turn(self, engine) -> bool  # 1ターン分を自動処理
```

### 階層的ニューラルネットワーク

フェーズごとに専用のポリシーヘッドを持つ軽量アーキテクチャ：

- 入力: 118チャンネル（駒配置 + メタ情報）
- 共有バックボーン: CNN + ResBlocks
- 出力ヘッド: piece(361), dest(361), promo(2), shoot(362)
- パラメータ数: 約650万（軽量版）

## 主要機能

### 実装済み

- 34種類の駒の移動ルール
- 成り・成り戻り
- 勝利条件（将+中軍/旗の捕獲）
- 特殊能力（射撃、経路上捕獲、周囲破壊など）
- 棋譜ベースのUndo
- Pygame GUI
- AI（Random, Greedy, Minimax, Neural）
- Minimax対戦による強化学習
- 定期評価による性能追跡

## ゲームルール

詳細は [GAMERULE.md](GAMERULE.md) を参照。

### 勝利条件

相手の「将」と「中軍」（または「旗」）を両方取ると勝利。ただし「中軍」が「帥」に成ると単独で勝利条件駒になる。

### 駒の種類

| カテゴリ | 駒 |
|---------|-----|
| 指揮 | 将, 記室, 参謀, 中軍, 鼓, 旗 |
| 護衛 | 親兵, 力士, 舎人, 舎餘, 護兵 |
| 将校 | 軍吏, 軍匠, 高道, 神僧, 把総, 百総, 千総, 騎総 |
| 前線 | 前衝, 後衝, 先鋒 |
| 兵科 | 歩兵, 歩総, 馬兵, 牌, 牌総, 車, 車総, 象 |
| 射撃 | 弓, 弩, 砲, 仏狼機 |

## ライセンス

MIT License

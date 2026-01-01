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
# 基本的な対戦
python scripts/battle.py --player1 minimax --player2 greedy -n 10

# JSONL形式で棋譜を出力（学習用）
python scripts/battle.py -p1 minimax:depth=2 -p2 random -n 100 -o data/games.jsonl --format jsonl

# タイムアウト設定（デフォルト: ゲーム300秒、1手30秒）
python scripts/battle.py -p1 random -p2 random -n 5 --game-timeout 60
```

### ニューラルネットワーク訓練

```bash
# 1. 棋譜を経験データに変換
python scripts/convert_kifu.py -i data/games.jsonl -o data/experiences.pt

# 2. 経験データから学習
python scripts/train.py supervised --data data/experiences.pt --output models/sl_v1 --lite
python scripts/train.py reinforce --data data/experiences.pt --output models/rl_v1 --lite
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
├── scripts/                 # スクリプト（開発時）
│   ├── battle.py            # AI対戦・棋譜出力
│   ├── convert_kifu.py      # 棋譜→経験データ変換
│   ├── train.py             # モデル訓練（教師あり/強化学習）
│   ├── analyze.py           # 対戦結果分析
│   ├── pipeline.py          # 対戦→変換→学習パイプライン
│   └── lib/                 # 共通ライブラリ
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

### ゲーム状態モデル

ゲーム状態は3要素の組で表される:

```
State = (Board, Player, Phase)
```

- **Board**: 19x19の盤面（各マスに駒情報または空）
- **Player**: 手番（0=先手, 1=後手）
- **Phase**: 現在のフェーズ（属性付き）

### フェーズ

フェーズは「次にどのような選択が可能か」を決定する:

| Phase | 説明 | 主な属性 |
|-------|------|----------|
| `PieceSelect` | 駒選択 | - |
| `DestSelect` | 移動先選択 | selected_piece |
| `MultiStep` | マルチステップ移動中 | current_pos, remaining_steps |
| `Promotion` | 成り判断 | piece_pos, promotes_to |
| `Shooting` | 射撃 | shooter_pos, remaining_shots |
| `GameOver` | 終了 | winner, reason |

### 設計原則

1. **駒定義ファイル**（`pieces/*.py`）は各フェーズでの選択肢を計算するための情報源
2. **棋譜**は状態遷移ごとに1エントリ記録
3. **undo()**は直前の1エントリをpopし、対応する遷移を逆転

### GameEngine API

- `select_piece()`: 動かす駒を選択
- `select_destination()`: 移動先を選択
- `select_next_step()`: マルチステップの次の移動先を選択
- `stop_move()`: マルチステップを途中で停止
- `decide_promotion()`: 成るか否かを決定
- `shoot()` / `skip_shoot()`: 射撃

### AIインターフェース

全てのAIは`BaseAI`を継承し、フェーズごとに決定を行う：

```python
class BaseAI(ABC):
    def choose_piece(self, engine) -> tuple[int, int]
    def choose_destination(self, engine) -> tuple[int, int]
    def choose_promotion(self, engine) -> bool
    def choose_shoot_target(self, engine) -> Optional[tuple[int, int]]
    def play_step(self, engine) -> bool  # 1状態遷移を処理
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

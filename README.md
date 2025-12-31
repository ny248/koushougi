# 広将棋 (Koushougi)

広将棋を人間同士またはAIと対戦できるプロジェクトです。

## 概要

- 19x19の盤面で34種類の駒を使う歴史的な将棋variant
- Pygame GUIでの対戦
- 複数のAIプレイヤー（Random, Greedy, Minimax）

## インストール

```bash
pip install pygame
```

## 使い方

### GUI対戦

```bash
python frontend/pygame/game_app.py
```

### AI同士の対戦

```bash
python ai/battle.py --player1 minimax --player2 greedy --games 10
```

### テスト

```bash
python -m pytest tests/ -v
```

## ディレクトリ構成

```
.
├── backend/
│   ├── domain/          # 盤面・駒・ゲーム状態
│   │   ├── board.py
│   │   ├── game_state.py
│   │   ├── kifu.py      # 棋譜（undo用）
│   │   ├── piece_registry.py
│   │   └── pieces/      # 34種+成り駒の定義
│   └── rules/           # ルール処理
│       ├── game_engine.py
│       ├── movement.py
│       ├── promotion.py
│       └── victory.py
├── frontend/
│   ├── pygame/          # Pygame GUI
│   │   ├── game_app.py
│   │   ├── renderer.py
│   │   └── menu.py
│   └── cli/             # CLIインターフェース
├── ai/
│   ├── base.py          # AIベースクラス
│   ├── battle.py        # AI対戦スクリプト
│   ├── random/          # ランダムAI
│   ├── greedy/          # Greedy AI（駒価値ベース）
│   ├── minimax/         # Minimax AI（Alpha-Beta枝刈り）
│   │   ├── player.py
│   │   └── evaluator.py
│   ├── neural/          # NN訓練用（開発中）
│   │   ├── model.py
│   │   ├── dataset.py
│   │   └── train.py
│   └── analysis/        # 分析スクリプト
├── tests/
│   └── unit/
├── docs/
│   └── notes/
├── GAMERULE.md          # 完全なゲームルール
└── config.py
```

## 主要機能

### 実装済み

- 34種類の駒の移動ルール
- 成り・成り戻り
- 勝利条件（将+中軍/旗の捕獲）
- 特殊能力（射撃、経路上捕獲、周囲破壊など）
- 棋譜ベースのUndo
- Pygame GUI
- AI（Random, Greedy, Minimax）

### 開発中

- ニューラルネットワークAI

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

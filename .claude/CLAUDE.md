# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

広将棋 (Koushougi) GUI Battle Project - A Python application for playing Koushougi (a historical Japanese board game invented by Ogyū Sorai) with GUI and AI opponents.

**Current Status**: Fully playable with pygame GUI, CLI interface, and multiple AI implementations (Random, Greedy, Minimax, Neural).

## Development Commands

Run the main application:
```bash
python main.py          # GUI版（pygame）
python main.py --cli    # CLI版
```

Run tests:
```bash
python -m pytest tests/unit/ -q
```

Run AI battles:
```bash
python scripts/battle.py
```

**Dependencies**: pygame, torch (for neural AI)

## Architecture

### Directory Structure
```
koushougi/
├── backend/              # ゲームロジック
│   ├── domain/           # 状態管理（Board, GameState, Kifu）
│   │   ├── pieces/       # 57種類の駒定義（p001_将.py ～ p057_天塁.py）
│   │   └── piece_registry.py  # 駒定義の一元管理
│   └── rules/            # ルール処理（GameEngine, Movement, Promotion, Victory）
├── frontend/             # UI実装
│   ├── pygame/           # GUI（game_app.py, renderer.py, menu.py）
│   └── cli/              # CUI（game_cli.py）
├── ai/                   # AIプレイヤー
│   ├── base.py           # 抽象基底クラス
│   ├── random/           # ランダムAI
│   ├── greedy/           # 貪欲AI（駒価値ベース）
│   ├── minimax/          # Minimax探索AI
│   └── neural/           # ニューラルネットワークAI
├── scripts/              # 開発・分析用スクリプト
│   ├── battle.py         # AI対戦実行
│   ├── train.py          # NN訓練
│   └── lib/              # 共有ライブラリ
├── tests/unit/           # ユニットテスト
├── config.py             # グローバル設定（BOARD_SIZE等）
└── main.py               # エントリーポイント
```

### Key Concepts
- **19x19 intersection grid** - Pieces placed on intersections (like Go/Xiangqi), not squares
- **57 piece types** - 34 base pieces + promoted forms (see GAMERULE.md)
- **No captured piece reuse** - Unlike Shogi, captured pieces cannot be dropped back
- **Promotion system** - Pieces promote when entering enemy territory or capturing specific pieces
- **Win condition** - Capture opponent's 将 (General) + either 中軍/旗 (Central Army/Flag), unless 中軍 promotes to 帥

### Game State Model

ゲーム状態は3要素の組で表される: `State = (Board, Player, Phase)`

- **Board**: 19x19の盤面
- **Player**: 手番（0=先手, 1=後手）
- **Phase**: 現在のフェーズ（属性付き）

フェーズは「次にどのような選択が可能か」を決定する：

| Phase | 説明 | 属性 |
|-------|------|------|
| `PieceSelect` | 駒選択 | なし |
| `DestSelect` | 移動先選択 | `selected_piece` |
| `MultiStep` | マルチステップ移動中 | `current_pos`, `remaining_steps`, `can_stop`, etc. |
| `Promotion` | 成り判断 | `piece_pos`, `piece_id`, `promotes_to` |
| `Shooting` | 射撃 | `shooter_pos`, `targets`, `remaining_shots` |
| `GameOver` | 終了 | `winner`, `reason` |

**設計原則**:
1. 駒定義ファイル（`pieces/*.py`）は各フェーズでの選択肢を計算するための情報源
2. 棋譜は状態遷移ごとに1エントリ記録
3. `undo()`は直前の1エントリをpopし、対応する遷移を逆転

詳細: [docs/notes/kifu_and_undo_design.md](../docs/notes/kifu_and_undo_design.md)

## Key Files

- [GAMERULE.md](../GAMERULE.md) - Complete game rules with all piece movements and special abilities
- [config.py](../config.py) - Global constants (BOARD_SIZE, AI settings, GUI settings)

## Working Guidelines

- **Priority**: Game playability and AI development
- **Language**: Python
- **Efficiency**: Minimize web access, store data locally, avoid redundant requests
- **Communication**: Keep concise, confirm before major changes

## Development Notes

- 判断に迷う点や後で見直すべき点は `docs/notes/dev_notes.md` にメモして先に進む
- ユーティリティやヘルパーは実際の使用場面が明確になってから作成する
- 必要だと分かっていながら実装をサボらない。あまりに大変そうならユーザに確認を取る

## アンチパターン

### 二重管理の禁止

駒の定義（ID、名前、成り先、移動パターンなど）は `backend/domain/` に一元管理されている。
他の場所で同じ情報を再定義してはならない。

**悪い例:**
```python
# ai/greedy/piece_values.py で成り関係を再定義
PROMOTION_MAP = {
    1: 35,   # 将 → 帥
    2: 36,   # 記室 → 軍師
    ...
}
```

**良い例:**
```python
# backend/domain/piece_registry から取得
from backend.domain.piece_registry import get_piece

piece = get_piece(piece_id)
promoted_id = piece.promotes_to  # 成り先ID
```

### データの権威ある出典

| データ | 出典 |
|--------|------|
| ゲームルール | `GAMERULE.md` |
| 駒の定義 | `backend/domain/piece_registry.py` |
| 駒の詳細 | `backend/domain/pieces/*.py` |
| 設定定数 | `config.py` |
| 駒の価値（AI用） | `ai/greedy/piece_values.py` |

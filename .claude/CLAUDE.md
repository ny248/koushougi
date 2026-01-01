# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**注意: README.md と CLAUDE.md は別物**
- `README.md`: プロジェクトの設計思想・アーキテクチャ・使い方を記述（人間向け）
- `CLAUDE.md`: Claude Code への指示・作業ガイドライン（AI向け）

設計やアーキテクチャの変更は README.md に反映すること。

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

### オブジェクトの分類

**サービス（状態を持たない、渡されない）**:
- `GameEngine` - 状態遷移を計算する純粋関数群
- `movement` - 合法手計算
- `promotion` - 成り判定
- `victory` - 勝敗判定

**やりとりされるオブジェクト（状態を持つ、渡される）**:
- `GameState` - ゲームの完全な状態（Board, Player, Phase, Kifu）
- `Board` - 19x19の盤面
- `Kifu` - 棋譜

**設計原則**:
```
AIは GameState を受け取り、手を選び、新しい GameState を得る。
GameEngine はサービスとして「この状態でこの手を指したらどうなるか」を計算する。
GameState を変更するのではなく、新しい GameState を返す。
```

### Directory Structure
```
koushougi/
├── backend/              # ゲームロジック
│   ├── domain/           # やりとりされるオブジェクト
│   │   ├── game_state.py # GameState（状態の完全な表現）
│   │   ├── board.py      # Board（盤面）
│   │   ├── kifu.py       # Kifu（棋譜）
│   │   ├── pieces/       # 57種類の駒定義
│   │   └── piece_registry.py
│   └── rules/            # サービス（状態遷移計算）
│       ├── game_engine.py
│       ├── movement.py
│       ├── promotion.py
│       └── victory.py
├── frontend/             # UI実装
│   ├── pygame/           # GUI
│   └── cli/              # CUI
├── ai/                   # AIプレイヤー
│   ├── base.py           # 抽象基底クラス
│   ├── random/
│   ├── greedy/
│   ├── minimax/
│   └── neural/
├── scripts/              # 開発・分析用スクリプト
├── tests/unit/           # ユニットテスト
├── config.py             # グローバル設定
└── main.py               # エントリーポイント
```

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

### Key Concepts
- **19x19 intersection grid** - Pieces placed on intersections (like Go/Xiangqi), not squares
- **57 piece types** - 34 base pieces + promoted forms (see GAMERULE.md)
- **No captured piece reuse** - Unlike Shogi, captured pieces cannot be dropped back
- **Promotion system** - Pieces promote when entering enemy territory or capturing specific pieces
- **Win condition** - Capture opponent's 将 (General) + either 中軍/旗 (Central Army/Flag), unless 中軍 promotes to 帥

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

### 確認なしの実装禁止

ユーザーが指示していない機能や関数を勝手に実装してはならない。特に：

- 新しいヘルパー関数やユーティリティの追加
- アルゴリズムの「改善」や「最適化」
- 「便利そう」という理由での機能追加

**必ずユーザーに確認を取ってから実装すること。**

無能な働き者が一番害悪。確認を怠って勝手に動くな。

### 二重管理の禁止

駒の定義（ID、名前、成り先、移動パターンなど）は `backend/domain/` に一元管理されている。
他の場所で同じ情報を再定義してはならない。

### データの権威ある出典

| データ | 出典 |
|--------|------|
| ゲームルール | `GAMERULE.md` |
| 駒の定義 | `backend/domain/piece_registry.py` |
| 駒の詳細 | `backend/domain/pieces/*.py` |
| 設定定数 | `config.py` |
| 駒の価値（AI用） | `ai/greedy/piece_values.py` |

# 広将棋 (Koushougi)

広将棋を人間同士またはAIと対戦できるプロジェクトです。Pygame GUIと複数AI、棋譜出力、学習パイプラインまでを含みます。

## 特徴

- 19x19の盤面で34種類の駒を使う歴史的な将棋variant
- Pygame GUIでの対戦
- 複数のAIプレイヤー（Random, Greedy, Minimax, Neural）
- 棋譜(JSONL)と学習データ変換

## セットアップ

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

## アーキテクチャ

### オブジェクトの分類

このプロジェクトでは、オブジェクトを**サービス**と**やりとりされるオブジェクト**に厳格に分離します。

#### サービス（状態を持たない、渡されない）

状態遷移を計算する純粋関数群。インスタンス化して渡すのではなく、関数として呼び出す。

| サービス | 役割 |
|----------|------|
| `GameEngine` | 状態遷移の計算（`apply_move(state, action) -> new_state`） |
| `movement` | 合法手の計算 |
| `promotion` | 成り判定 |
| `victory` | 勝敗判定 |

#### やりとりされるオブジェクト（状態を持つ、渡される）

ゲームの状態を表現するデータ。関数間で受け渡しされる。

| オブジェクト | 役割 |
|--------------|------|
| `GameState` | ゲームの完全な状態（Board, Player, Phase, Kifu） |
| `Board` | 19x19の盤面 |
| `Kifu` | 棋譜 |
| `Move` | 1手の記録 |

#### 設計原則

```
AIは GameState を受け取り、手を選び、新しい GameState を得る。
GameEngine はサービスとして「この状態でこの手を指したらどうなるか」を計算する。
GameState を変更するのではなく、新しい GameState を返す。
```

```python
# 良い例: GameStateを渡して新しいGameStateを得る
new_state = GameEngine.apply_action(state, action)

# 悪い例: GameEngineを渡して内部状態を変更する
engine.apply_action(action)  # 内部のstateが変更される
```

### ディレクトリ構成

```
.
├── backend/                 # ゲームロジック
│   ├── domain/              # やりとりされるオブジェクト
│   │   ├── board.py         # Board（盤面）
│   │   ├── game_state.py    # GameState（状態の完全な表現）
│   │   ├── kifu.py          # Kifu, Move（棋譜）
│   │   ├── piece_registry.py
│   │   └── pieces/          # 34種+成り駒の定義
│   └── rules/               # サービス（状態遷移計算）
│       ├── game_engine.py   # GameEngine
│       ├── movement.py      # 合法手計算
│       ├── promotion.py     # 成り判定
│       └── victory.py       # 勝敗判定
│
├── frontend/                # UI
│   └── pygame/              # Pygame GUI
│       ├── game_app.py
│       ├── renderer.py
│       └── menu.py
│
├── ai/                      # AIプレイヤー
│   ├── base.py              # BaseAI抽象クラス
│   ├── random/
│   ├── greedy/
│   ├── minimax/
│   └── neural/
│
├── scripts/                 # 開発用スクリプト
│   ├── battle.py            # AI対戦・棋譜出力
│   ├── convert_kifu.py      # 棋譜→経験データ変換
│   ├── train.py             # モデル訓練
│   └── lib/                 # 共通ライブラリ
│
├── models/                  # 学習済みモデル
├── tests/
├── docs/
├── GAMERULE.md              # 完全なゲームルール
└── config.py
```

### ゲーム状態モデル

ゲーム状態は3要素の組で表されます。

```
State = (Board, Player, Phase)
```

- **Board**: 19x19の盤面
- **Player**: 手番（0=先手, 1=後手）
- **Phase**: 現在のフェーズ（`GamePhase`）

### フェーズ

| Phase            | 説明                 | 主な属性                     |
| ---------------- | -------------------- | ---------------------------- |
| `PIECE_SELECT`   | 駒選択               | -                            |
| `DEST_SELECT`    | 移動先選択           | selected_piece               |
| `MULTI_STEP_MOVE`| マルチステップ移動中 | current_pos, remaining_steps |
| `PROMOTION`      | 成り判断             | piece_pos, promotes_to       |
| `SHOOTING`       | 射撃                 | shooter_pos, remaining_shots |
| `GAME_OVER`      | 終了                 | winner, reason               |

### GameEngine API

GameEngineはサービスとして、GameStateとアクションを受け取り、新しいGameStateを返す。

```python
# 状態遷移
new_state = GameEngine.select_piece(state, pos)
new_state = GameEngine.select_destination(state, pos)
new_state = GameEngine.decide_promotion(state, promote=True)
new_state = GameEngine.shoot(state, target)

# 情報取得（純粋関数）
moves = GameEngine.get_legal_moves(state, pos)
pieces = GameEngine.get_movable_pieces(state)
```

### AIインターフェース

AIはGameStateを受け取り、アクションを返す。

```python
class BaseAI(ABC):
    def choose_action(self, state: GameState) -> Action:
        """現在の状態から最善のアクションを選択"""
        pass
```

探索AIの場合:
```python
# Minimax探索
def search(state: GameState, depth: int) -> tuple[Action, float]:
    if depth == 0 or GameEngine.is_game_over(state):
        return None, evaluate(state)

    best_action = None
    best_value = float('-inf')

    for action in GameEngine.get_legal_actions(state):
        new_state = GameEngine.apply_action(state, action)
        _, value = search(new_state, depth - 1)
        if value > best_value:
            best_value = value
            best_action = action

    return best_action, best_value
```

### 階層的ニューラルネットワーク

フェーズごとに専用のポリシーヘッドを持つ軽量アーキテクチャです。

- 入力: 118チャンネル（駒配置 + メタ情報）
- 共有バックボーン: CNN + ResBlocks
- 出力ヘッド: piece(361), dest(361), promo(2), shoot(362)
- パラメータ数: 約650万（軽量版）

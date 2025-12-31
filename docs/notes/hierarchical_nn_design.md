# 階層的NN推論の設計

## 概要

ゲームの状態遷移に合わせてNN推論を細分化し、各フェーズで軽量な出力を行う。

## 現状の問題

### 1. 巨大な出力空間
- 現在: 駒ID(58) × 移動先(361) = 20,938次元
- 1回の推論で全てを決定しようとしている
- パラメータ数: 約2.4億 → 推論が重い

### 2. GameEngineとのミスマッチ
- GameEngineは既に状態遷移を持っている（射撃待ち等）
- AIは1回で全て決定 → 構造を活かせていない

## 提案: フェーズ分離型アーキテクチャ

### ゲームの状態遷移

```
┌─────────────────┐
│  駒選択待ち      │ ← ターン開始
│  (PIECE_SELECT) │
└────────┬────────┘
         │ select_piece(from_pos)
         ▼
┌─────────────────┐
│  移動先選択待ち   │
│  (DEST_SELECT)  │
└────────┬────────┘
         │ select_destination(to_pos)
         ▼
┌─────────────────┐
│  成り判断待ち     │ ← 成れる場合のみ
│  (PROMOTION)    │
└────────┬────────┘
         │ decide_promotion(bool)
         ▼
┌─────────────────┐
│  射撃待ち        │ ← 射撃可能な場合のみ
│  (SHOOTING)     │
└────────┬────────┘
         │ shoot(target) or skip()
         ▼
┌─────────────────┐
│  ターン終了      │
└─────────────────┘
```

### 各フェーズの出力

| フェーズ | 出力 | サイズ | 説明 |
|----------|------|--------|------|
| PIECE_SELECT | from位置 | 361 | 動かす駒の位置 |
| DEST_SELECT | to位置 | 361 | 移動先の位置 |
| PROMOTION | 成る/成らない | 2 | 成り判断 |
| SHOOTING | 射撃先 or スキップ | 362 | 射撃対象選択 |

**合計最大出力: 362（1フェーズあたり）**
**現状比: 20,938 → 362 = 約58分の1**

## モデル設計

### 共有バックボーン + フェーズ別ヘッド

```
入力: 盤面テンソル [B, 117, 19, 19]
      + フェーズ情報
      + コンテキスト（選択済み駒位置など）
         │
         ▼
┌─────────────────────────┐
│    共有バックボーン       │
│  (Conv + ResBlocks)     │
│  パラメータを共有         │
└────────────┬────────────┘
             │
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Piece │ │ Dest │ │Promo │ │Shoot │
│ Head │ │ Head │ │ Head │ │ Head │
└──────┘ └──────┘ └──────┘ └──────┘
  361      361       2       362

+ Value Head (局面評価, 全フェーズ共通)
```

### 入力の拡張

各フェーズで追加情報を入力に含める：

```python
# 基本入力: 117チャンネル
# - ch 0-57: プレイヤー0の駒
# - ch 58-115: プレイヤー1の駒
# - ch 116: 手番

# フェーズ別追加入力
# DEST_SELECT: 選択した駒の位置 (1ch)
# SHOOTING: 射撃可能位置マスク (1ch)
```

## GameEngine の変更

### 新しいAPI

```python
class GameEngine:
    # 現在のフェーズを取得
    @property
    def phase(self) -> GamePhase:
        """PIECE_SELECT, DEST_SELECT, PROMOTION, SHOOTING"""

    # フェーズ1: 駒選択
    def get_movable_pieces(self) -> list[tuple[int, int]]:
        """動かせる駒の位置リスト"""

    def select_piece(self, pos: tuple[int, int]) -> bool:
        """駒を選択 → DEST_SELECTへ遷移"""

    # フェーズ2: 移動先選択
    def get_legal_destinations(self) -> list[tuple[int, int]]:
        """選択中の駒の合法移動先"""

    def select_destination(self, pos: tuple[int, int]) -> MoveResult:
        """移動先を選択 → PROMOTION or SHOOTING or ターン終了"""

    # フェーズ3: 成り判断
    def can_promote_now(self) -> bool:
        """現在成り判断待ちか"""

    def decide_promotion(self, promote: bool) -> MoveResult:
        """成り判断 → SHOOTING or ターン終了"""

    # フェーズ4: 射撃（既存APIを維持）
    def get_shoot_targets(self) -> list[tuple[int, int]]
    def shoot(self, target) -> MoveResult
    def skip_shoot() -> MoveResult
```

### 後方互換性

既存の `move(from, to, promote)` は内部で上記APIを呼ぶラッパーとして維持：

```python
def move(self, from_pos, to_pos, promote=False):
    """後方互換用ラッパー"""
    self.select_piece(from_pos)
    result = self.select_destination(to_pos)
    if self.can_promote_now():
        result = self.decide_promotion(promote)
    return result
```

## AI Interface の変更

### 新しいBaseAI

```python
class BaseAI(ABC):
    @abstractmethod
    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """動かす駒を選択"""

    @abstractmethod
    def choose_destination(self, engine: GameEngine, from_pos: tuple[int, int]) -> tuple[int, int]:
        """移動先を選択"""

    @abstractmethod
    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうか"""

    @abstractmethod
    def choose_shoot(self, engine: GameEngine, targets: list) -> Optional[tuple[int, int]]:
        """射撃先を選択（既存）"""

    # 後方互換ラッパー
    def choose_move(self, engine: GameEngine) -> dict:
        """従来のAPIをシミュレート"""
        from_pos = self.choose_piece(engine)
        to_pos = self.choose_destination(engine, from_pos)
        promote = False
        # 成り判定は実際の移動後に行う
        return {"from": from_pos, "to": to_pos, "promote": promote}
```

## NNモデル実装

### KoushougiNetHierarchical

```python
class KoushougiNetHierarchical(nn.Module):
    def __init__(self, channels=64):
        # 共有バックボーン
        self.backbone = nn.Sequential(
            nn.Conv2d(118, channels, 3, padding=1),  # +1ch for context
            nn.BatchNorm2d(channels),
            nn.ReLU(),
            ResidualBlock(channels),
            ResidualBlock(channels),
        )

        # フェーズ別ヘッド（全て軽量）
        self.piece_head = PolicyHead(channels, 361)   # どの駒
        self.dest_head = PolicyHead(channels, 361)    # どこへ
        self.promo_head = PolicyHead(channels, 2)     # 成るか
        self.shoot_head = PolicyHead(channels, 362)   # 射撃先

        # 価値ヘッド
        self.value_head = ValueHead(channels)

    def forward(self, x, phase, context=None):
        # コンテキストを入力に追加
        if context is not None:
            x = torch.cat([x, context], dim=1)

        features = self.backbone(x)
        value = self.value_head(features)

        if phase == "piece":
            policy = self.piece_head(features)
        elif phase == "dest":
            policy = self.dest_head(features)
        elif phase == "promo":
            policy = self.promo_head(features)
        elif phase == "shoot":
            policy = self.shoot_head(features)

        return policy, value
```

### パラメータ数の比較

| モデル | パラメータ数 |
|--------|-------------|
| 現在のKoushougiNetLite | 約2.4億 |
| 提案のHierarchical | 約200万（推定） |

**約100分の1に削減**

## 訓練方法

### 教師あり学習

各フェーズの正解を別々に学習：

```python
# データ形式
{
    "board": [...],
    "phase": "piece",
    "target": 123,  # from位置のindex
    "value": 0.7
}
{
    "board": [...],
    "phase": "dest",
    "context": {"selected_piece": (5, 3)},
    "target": 256,  # to位置のindex
    "value": 0.7
}
```

### 強化学習

各フェーズの選択に対してrewardを割り当て：
- ゲーム勝利 → 全フェーズの選択にpositive reward
- ゲーム敗北 → 全フェーズの選択にnegative reward

## 実装計画

### Phase 1: GameEngine拡張
1. `GamePhase` enumを追加
2. 新しい状態遷移APIを実装
3. 後方互換ラッパーで既存コードを維持

### Phase 2: NNモデル
1. `KoushougiNetHierarchical` を実装
2. 各フェーズのヘッドを実装
3. 推論ベンチマーク

### Phase 3: AI Interface
1. `BaseAI` を拡張
2. `NeuralPlayer` を新アーキテクチャに対応
3. 既存AI（Greedy, Minimax）のアダプター

### Phase 4: 訓練
1. データ形式の変換スクリプト
2. フェーズ別訓練ループ
3. Minimax対戦学習

### Phase 5: Frontend対応（オプション）
1. pygameのUI更新
2. フェーズ表示

## リスクと対策

| リスク | 対策 |
|--------|------|
| 後方互換性の破壊 | ラッパーAPIで既存コード維持 |
| 訓練データの変換 | 既存データから自動生成 |
| フェーズ間の依存 | コンテキスト入力で情報伝達 |

## 次のステップ

1. この設計のレビュー
2. Phase 1 (GameEngine拡張) の実装開始

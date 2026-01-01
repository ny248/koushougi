# ゲーム状態リファクタリング計画

## 目的

ゲーム状態管理を設計原則（`kifu_and_undo_design.md`）に従って整理し、Minimax AIのundo問題を根本的に解決する。

## 現状の問題

1. **棋譜エントリの粒度が不統一**: マルチステップ移動で複数エントリが作成される
2. **undoが一部のmove_typeに未対応**: "step", "stop"タイプを処理できない
3. **フェーズ状態がGameEngineの内部変数に分散**: `_phase`, `_selected_piece`, `_multi_step_state`, `_pending_shoot`

## 修正方針

**1状態遷移 = 1棋譜エントリ**を徹底し、undoを全遷移に対応させる。

---

## フェーズ1: 棋譜とundoの修正（最優先）

### 1.1 Move構造の拡張

`backend/domain/kifu.py`:

```python
@dataclass
class Move:
    player: int
    move_type: str  # "select", "move", "step", "stop", "promote", "shoot", "skip_shoot"

    # 共通
    from_pos: Optional[tuple[int, int]] = None
    to_pos: Optional[tuple[int, int]] = None
    piece_id: Optional[int] = None

    # 移動時
    captured_piece: Optional[int] = None
    captured_was_promoted: bool = False
    path_kills: list = field(default_factory=list)

    # 成り時
    promoted: bool = False
    promoted_from: Optional[int] = None  # 成り前の駒ID

    # 連鎖・道連れ・退化
    chain_promotions: list = field(default_factory=list)
    collateral_kills: list = field(default_factory=list)
    demotions: list = field(default_factory=list)
```

### 1.2 undoの全move_type対応

`backend/rules/game_engine.py`:

```python
def undo(self) -> bool:
    last_move = self.state.kifu.pop()
    if last_move is None:
        return False

    # 共通の逆転処理
    self._reverse_side_effects(last_move)

    match last_move.move_type:
        case "select":
            # 駒選択を取り消し → PieceSelectに戻る
            self._phase = GamePhase.PIECE_SELECT
            self._selected_piece = None

        case "move":
            # 駒を元の位置に戻す、取った駒を復元
            self._undo_move(last_move)

        case "step":
            # マルチステップの1ステップを戻す
            self._undo_step(last_move)

        case "stop":
            # 停止を取り消し → MultiStepに戻る
            self._undo_stop(last_move)

        case "promote":
            # 成りを取り消し
            self._undo_promote(last_move)

        case "shoot":
            # 射撃を取り消し
            self._undo_shoot(last_move)

        case "skip_shoot":
            # 射撃スキップを取り消し
            self._undo_skip_shoot(last_move)

    return True
```

### 1.3 棋譜記録タイミングの統一

各フェーズ遷移で1エントリ記録:

| 遷移 | move_type | 記録内容 |
|------|-----------|----------|
| `select_piece()` | "select" | selected_piece |
| `select_destination()` | "move" | from, to, captured, path_kills |
| `select_next_step()` | "step" | from, to, captured |
| `stop_move()` | "stop" | current_pos |
| `decide_promotion(True)` | "promote" | piece_pos, promoted_from, promoted_to |
| `decide_promotion(False)` | (記録なし、または"no_promote") | |
| `shoot()` | "shoot" | shooter_pos, target, captured |
| `skip_shoot()` | "skip_shoot" | shooter_pos |

---

## フェーズ2: Phase型の再定義（推奨）

### 2.1 属性付きPhaseクラス

`backend/domain/phase.py` (新規):

```python
from dataclasses import dataclass
from typing import Optional
from abc import ABC

@dataclass
class Phase(ABC):
    pass

@dataclass
class PieceSelect(Phase):
    pass

@dataclass
class DestSelect(Phase):
    selected_piece: tuple[int, int]

@dataclass
class MultiStep(Phase):
    original_pos: tuple[int, int]
    current_pos: tuple[int, int]
    remaining_steps: int
    can_stop: bool
    first_direction: tuple[int, int]
    path_kills: list
    step_history: list
    piece_id: int
    already_promoted: bool

@dataclass
class Promotion(Phase):
    piece_pos: tuple[int, int]
    piece_id: int
    promotes_to: int

@dataclass
class Shooting(Phase):
    shooter_pos: tuple[int, int]
    targets: list[tuple[int, int]]
    remaining_shots: int
    params: Optional[dict] = None

@dataclass
class GameOver(Phase):
    winner: int
    reason: str
```

### 2.2 GameStateへの統合

```python
@dataclass
class GameState:
    board: Board
    current_player: int
    move_count: int
    phase: Phase = field(default_factory=PieceSelect)
    kifu: Kifu = field(default_factory=Kifu)
    winner: Optional[int] = None
```

---

## フェーズ3: GameEngineの簡素化

### 3.1 内部状態の削除

`_selected_piece`, `_multi_step_state`, `_pending_shoot`を削除し、`state.phase`に統合。

### 3.2 フェーズ遷移の明確化

```python
def select_piece(self, pos):
    if not isinstance(self.state.phase, PieceSelect):
        return False
    # ... 検証 ...
    self.state.phase = DestSelect(selected_piece=pos)
    self.state.kifu.append(Move(move_type="select", ...))
    return True
```

---

## 影響範囲

### 修正が必要なファイル

| ファイル | 修正内容 |
|----------|----------|
| `backend/domain/kifu.py` | Move構造の拡張 |
| `backend/domain/phase.py` | 新規作成 |
| `backend/domain/game_state.py` | phase フィールド追加 |
| `backend/rules/game_engine.py` | undo全対応、フェーズ管理の移行 |
| `ai/minimax/player.py` | undo呼び出しの簡素化（問題解消後） |
| `frontend/pygame/game_app.py` | undo呼び出し（変更不要の見込み） |
| `tests/unit/test_undo.py` | テストケース追加 |

### 後方互換性

- 既存の棋譜JSONファイルは読み込み時にマイグレーション
- `Move.from_dict()`で不足フィールドにデフォルト値を設定

---

## 実装順序

1. **Move構造の拡張** - 新フィールド追加、デフォルト値設定
2. **undo()の全move_type対応** - 各タイプの逆転処理を実装
3. **棋譜記録の修正** - 各遷移で適切なmove_typeを記録
4. **テスト追加・修正** - 全遷移のundo/redoをテスト
5. **Phase型の再定義**（オプション） - 時間があれば
6. **README.md更新** - アーキテクチャセクションの更新
7. **CLAUDE.md確認** - 設計原則との整合性確認

---

## テスト計画

### 追加すべきテストケース

1. マルチステップ移動のundo（複数回）
2. 成り + 射撃の組み合わせのundo
3. 経路取り（path_kills）のundo
4. 連鎖成り（chain_promotions）のundo
5. MinimaxPlayerの探索後に盤面が不変であること（既存テストの修正）

---

## リスク

1. **影響範囲が広い**: GameEngineの変更はAI、GUI、テストすべてに影響
2. **既存棋譜の互換性**: 古い形式の棋譜が読み込めなくなる可能性

### 軽減策

- 段階的に実装し、各ステップでテストを通す
- 棋譜のバージョン管理を導入（将来的に）

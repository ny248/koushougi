# ゲーム状態と棋譜の設計

## 設計原則

### 原則1: ゲーム状態の定義

ゲーム状態は以下の3要素の組で表される：

```
State = (Board, Player, Phase)
```

- **Board**: 19x19の盤面（各マスに駒情報または空）
- **Player**: 手番（0=先手, 1=後手）
- **Phase**: 現在のフェーズ（追加属性を持つ）

### 原則2: フェーズと属性

フェーズは「次にどのような選択が可能か」を決定する。各フェーズは必要な属性を持つ。

| フェーズ | 説明 | 属性 |
|----------|------|------|
| `PieceSelect` | 動かす駒を選ぶ | なし |
| `DestSelect` | 移動先を選ぶ | `selected_piece: (x, y)` |
| `MultiStep` | マルチステップ移動中 | `current_pos`, `remaining_steps`, `can_stop`, `first_direction`, `path_kills`, `step_history` |
| `Promotion` | 成り/不成りを選ぶ | `piece_pos: (x, y)`, `piece_id`, `promotes_to` |
| `Shooting` | 射撃対象を選ぶ | `shooter_pos: (x, y)`, `targets: [(x,y),...]`, `remaining_shots`, `shoot_params` |
| `GameOver` | ゲーム終了 | `winner`, `reason` |

### 原則3: 駒定義の役割

駒定義ファイル（`backend/domain/pieces/*.py`）は、各フェーズにおいてどの選択が可能かを計算するための情報源：

- `get_moves()`: DestSelectで選択可能な移動先を計算
- `get_multi_step_config()`: MultiStepの属性を決定
- `can_promote()`: Promotionフェーズへの遷移可否を判定
- `after_move()`: Shootingフェーズへの遷移とその属性を決定

### 原則4: 棋譜の記録

**棋譜は、ゲーム状態が遷移するたびに1エントリ記録する。**

```
State_n --[Action]--> State_n+1  →  Kifu.append(Action)
```

各エントリには遷移を逆転するために必要な情報を含む。

### 原則5: Undoの動作

`undo()`は直前の1エントリをpopし、対応する状態遷移を逆転する。

```
Kifu.pop() → Action_n
State_n+1 --[reverse(Action_n)]--> State_n
```

---

## 状態遷移の例

### 通常移動（成りなし、射撃なし）

```
PieceSelect --(select_piece)--> DestSelect --(select_destination)--> PieceSelect
     ↓                               ↓
  [記録なし]                    [Move記録]
```

### マルチステップ移動

```
PieceSelect --> DestSelect --> MultiStep --> MultiStep --> ... --> PieceSelect
                    ↓              ↓             ↓                     ↓
                 [Move]         [Step]        [Step]          [Stop or 自動終了]
```

### 成りあり

```
DestSelect --> Promotion --> PieceSelect
    ↓              ↓
 [Move]      [Promote決定を記録]
```

### 射撃あり

```
DestSelect --> Shooting --> Shooting --> PieceSelect
    ↓             ↓            ↓
 [Move]       [Shoot]      [Shoot or Skip]
```

---

## 現状からの変更点

### 変更が必要な箇所

1. **Phase型の再定義**: Enumから属性付きデータクラスへ
2. **GameState.phaseの追加**: 現在はGameEngine._phaseで管理しているが、GameStateに移動
3. **棋譜記録タイミングの見直し**: 現状は一部で複数エントリが作られる問題あり
4. **undo()の対応**: 全フェーズ遷移に対応

### 現状の問題

- `select_destination`でマルチステップ開始時にMove記録
- `stop_move()`で追加のStop記録
- → 2エントリになるが、undo()は1回で1エントリしか戻さない

### 解決方針

Option A: 各遷移を独立したエントリとして記録し、undoも各遷移に対応
Option B: ターン全体を1エントリにまとめる

**採用: Option A**（原則4に従う）

理由:
- 状態遷移と棋譜エントリが1:1で対応し、シンプル
- AI探索木の各ノードと自然に対応
- 棋譜再生で途中経過も忠実に再現可能

---

## 実装計画

1. Phase型を属性付きデータクラスとして再定義
2. GameStateにphaseフィールドを追加
3. 各フェーズ遷移で棋譜を記録
4. undo()を全move_typeに対応させる
5. GameEngine._phase等の内部状態をGameState.phaseに統合

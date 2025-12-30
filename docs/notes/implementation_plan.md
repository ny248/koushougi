# 広将棋 GUI 実装計画

## 概要

19x19盤面の広将棋を人間同士でGUI対戦できるようにするための段階的実装計画。
テスト駆動開発を採用し、早期に動作するゲームを目指す。

---

## 現状

- tkinterで19x19盤面の描画済み
- Board/Pieceクラスの基本構造あり
- 駒の選択ロジックあり
- **未実装**: 移動判定、駒取り、成り、勝敗判定、テスト

---

## Phase 1: 基盤構築と基本移動 (3-4日)

**目標**: DDDアーキテクチャへのリファクタリング、単純な駒の移動実装

### 駒定義方式

**YAMLファイル形式を採用** (`src/domain/pieces/*.yaml`)

各駒を個別のYAMLファイルで定義:
- `001.yaml` (将), `002.yaml` (記室), ... `057.yaml` (天塁)
- 移動、射撃、成り、制限を宣言的に記述
- 詳細は `src/domain/pieces/README.md` 参照

### 作成ファイル

```
src/
├── __init__.py
├── main.py                    # エントリーポイント
├── domain/
│   ├── __init__.py
│   ├── types.py               # Player列挙型、基本型
│   ├── position.py            # Position値オブジェクト (0-18, 0-18)
│   ├── piece.py               # Pieceエンティティ（YAMLから読み込んだ定義を参照）
│   ├── piece_loader.py        # YAMLファイルから駒定義を読み込む
│   ├── board.py               # Boardエンティティ
│   ├── game_state.py          # GameState集約
│   └── pieces/
│       ├── README.md          # 駒定義フォーマット仕様 ✓ 作成済み
│       ├── 001.yaml           # 将
│       ├── 002.yaml           # 記室
│       └── ...                # 全57駒分
├── rules/
│   ├── __init__.py
│   └── movement.py            # 駒定義を参照して合法手生成
├── app/
│   ├── __init__.py
│   └── game_app.py            # アプリケーション層
└── ui/
    ├── __init__.py
    ├── board_view.py          # Canvas描画
    └── piece_renderer.py      # 駒描画
```

### Phase 1で実装する駒の動き

**ステップ移動** (`slide: false`, `steps: 1`):
- 将, 中軍, 帥, 親兵, 舎人, 舎餘, 軍吏, 軍匠, 護兵, 旗, 鼓, 弓, 弩, 砲, 仏狼機, 牌, 歩兵

**スライド移動** (`slide: true`):
- 象 (斜め無制限), 千総 (全方向無制限), 把総, 百総, 前衝, 後衝
- 車 (縦横5路), 先鋒 (前5路), 歩総, 牌総, 車総

### テスト

```
tests/
├── __init__.py
├── conftest.py
└── unit/
    ├── test_position.py
    ├── test_piece.py
    ├── test_board.py
    └── test_movement_simple.py
```

### マイルストーン
駒を選択して基本移動ができる。ターン交代あり。取り・成りなし。

---

## Phase 2: 駒取りとターン管理 (2日)

**目標**: 駒取りロジック、ターン管理の完成

### 作成/修正ファイル

- `src/rules/capture.py` - 駒取りルール、取り制限
- `src/domain/game_state.py` - 拡張 (取った駒の管理)
- `src/ui/board_view.py` - 合法手ハイライト、取った駒表示

### 取り制限の実装

- 高道/神僧は移動では高道/神僧以外取れない
- 天塁は車/車総/砲車/神機車に取られない

### テスト

- `tests/unit/test_capture.py`
- `tests/unit/test_game_state.py`
- `tests/integration/test_basic_game.py`

### マイルストーン
駒取り可能な完全なターン制ゲーム（勝敗判定なし）

---

## Phase 3: 成りシステム (3日)

**目標**: 敵陣侵入と特定駒取りによる成り

### 作成ファイル

- `src/rules/promotion.py` - 成り判定ロジック

### 成りトリガー

1. **敵陣侵入**: 相手から見て6路目以内に入る
2. **将/中軍/旗/鼓を取る**: 取った駒がその場で成る
3. **力士/龍驤/招揺/霹靂を取る**: 1路駒のみ成る
4. **馬兵が仏狼機を取る**: その馬兵が成る

### 連鎖成り

- 記室→軍師: 前衝→天網、後衝→地網、敵の毒火が死ぬ

### テスト

- `tests/unit/test_promotion.py`
- `tests/unit/test_chain_promotion.py`

### マイルストーン
成りシステム動作（高道依存除く）

---

## Phase 4: 勝敗判定 (2日)

**目標**: 勝利条件の実装

### 作成ファイル

- `src/rules/victory.py` - 勝敗判定

### 勝利条件

負けになる条件:
1. 将が取られた
2. かつ (中軍が取られた OR 旗が取られた)

例外: 中軍が帥に成っていれば、将と旗を失っても負けにならない

### テスト

- `tests/unit/test_victory.py`
- `tests/integration/test_full_game.py`

### マイルストーン
**完全に遊べるゲーム** (基本ルールのみ)

---

## Phase 5: 二著する駒 (Lion移動) (4日)

**目標**: 獅子のように2手分動ける駒の実装

### 作成ファイル

- `src/rules/double_move.py`

### 対象駒

- 力士 (将の動き×2)
- 軍師 (記室の動き×2)
- 旗鼓 (参謀の動き×2)
- 龍驤 (千総 + 力士)
- 虎翼 (車総 + 牌×2)
- 鷹揚 (象 + 特殊縦横)
- 五里霧 (高道×2 + 射)
- 聖燈 (神僧×2 + 射)
- 騎総 (桂馬→同方向継続 or 戻る)
- 天馬 (桂馬×2)

### ルール

- 1手目で止まれる
- 2個まで取れる
- 1手目で味方は飛び越えられない

### テスト

- `tests/unit/test_double_move.py`
- `tests/unit/test_rikishi.py`
- `tests/unit/test_kisou.py`

---

## Phase 6: 射る駒 (4日)

**目標**: 遠距離攻撃の実装

### 作成ファイル

- `src/rules/shooting.py`

### 射程と対象数

| 駒 | 射程 | 対象数 | 備考 |
|----|------|--------|------|
| 高道/神僧 | 1路 | 1 | 着地点隣接 |
| 五里霧/聖燈 | 1路 | 2 | 各手で1つずつ |
| 弓/彍騎 | 3路 | 1 | |
| 弩/弩騎 | 5路 | 1 | |
| 砲/砲車 | 5路 | 1 | 貫通可 |
| 仏狼機/神機車 | 7路 | 2 | |

### 射撃免疫

- 天塁: 全射撃無効
- 牌総: 弓/弩/砲/仏狼機系無効
- 五里霧: 5路以内の弓/弩/砲/仏狼機無効

### テスト

- `tests/unit/test_shooting.py`
- `tests/unit/test_shooting_immunity.py`

---

## Phase 7: 特殊駒 (5日)

**目標**: 特殊能力を持つ駒の実装

### 作成ファイル

```
src/rules/special/
├── __init__.py
├── hekireki.py    # 霹靂
├── shouyou.py     # 招揺
└── dokuka.py      # 毒火
```

- `src/rules/koudou_effects.py` - 高道依存効果

### 霹靂 (鼓の成り)

- 縦横に左右交互に曲がりながら5路進む
- 途中停止不可、通り道の敵を全て取る

### 招揺 (旗の成り)

- 縦横に5路まで進める
- 通り道の敵を全て取る

### 毒火 (軍匠の成り)

- 斜め前/縦に1路進む
- 着地点の隣接8方向の駒を敵味方問わず全て殺す
- 敵の記室が軍師に成ると死ぬ

### 高道依存効果

- 高道が死ぬと旗/鼓は成れない
- 高道が死ぬと霹靂→鼓、招揺→旗に戻る
- 聖燈から5路以内の五里霧は高道に戻る

### テスト

- `tests/unit/test_hekireki.py`
- `tests/unit/test_shouyou.py`
- `tests/unit/test_dokuka.py`
- `tests/unit/test_koudou_effects.py`

---

## Phase 8: 仕上げ (3日)

**目標**: エッジケース対応、UI改善

### 対応事項

- 鼓が死ぬと歩兵が前進不可
- 全連鎖効果の正確な実装
- 移動履歴表示
- ゲーム終了ダイアログ
- 新規ゲーム開始

### 作成ファイル

- `src/ui/status_panel.py` - ターン表示、取った駒
- `src/ui/dialogs.py` - ダイアログ

### テスト

- `tests/integration/test_edge_cases.py`

---

## 依存関係

```
Phase 1 ─→ Phase 2 ─→ Phase 3 ─→ Phase 4 [遊べるゲーム]
                                    │
                              ┌─────┴─────┐
                              ↓           ↓
                          Phase 5     Phase 6  (並行可能)
                              │           │
                              └─────┬─────┘
                                    ↓
                                Phase 7 ─→ Phase 8
```

---

## テスト実行コマンド

```bash
# pytest インストール
pip install pytest

# 全テスト実行
pytest tests/

# 単体テストのみ
pytest tests/unit/

# 特定テスト
pytest tests/unit/test_movement_simple.py -v

# カバレッジ付き
pip install pytest-cov
pytest --cov=src tests/
```

---

## 重要ファイル

1. **GAMERULE.md** - 全ルールの権威ある出典
2. **src/domain/pieces/*.yaml** - 57種の駒定義（YAML形式）
3. **src/domain/pieces/README.md** - 駒定義フォーマット仕様 ✓ 作成済み
4. **src/domain/piece_loader.py** - YAML読み込みユーティリティ
5. **src/rules/movement.py** - 移動判定エンジン
6. **src/domain/game_state.py** - ゲーム状態管理

---

## 見積もり

| Phase | 内容 | 複雑度 | 日数 |
|-------|------|--------|------|
| 1 | 基盤構築と基本移動 | 中 | 3-4 |
| 2 | 駒取りとターン管理 | 低-中 | 2 |
| 3 | 成りシステム | 中-高 | 3 |
| 4 | 勝敗判定 | 中 | 2 |
| 5 | 二著する駒 | 高 | 4 |
| 6 | 射る駒 | 高 | 4 |
| 7 | 特殊駒 | 非常に高 | 5 |
| 8 | 仕上げ | 中 | 3 |
| **合計** | | | **26-28日** |

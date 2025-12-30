# 広将棋 CLIプロトコル仕様

AIとの通信に使用するテキストベースのプロトコル。

## 概要

- AIは標準入出力(stdin/stdout)を介してゲームエンジンと通信
- 1行1コマンド形式
- レスポンスはJSON形式

## 起動モード

```bash
python main.py cli           # 対話モード（人間用）
python main.py cli --machine # 機械通信モード（AI用）
```

`--machine`モードでは:
- プロンプトなし
- 全出力がJSON形式
- エラーもJSON形式

## コマンド一覧

### state - ゲーム状態取得

```
> state
```

レスポンス:
```json
{
  "turn": 0,
  "player": 0,
  "game_over": false,
  "winner": null,
  "board": {
    "a1": {"piece_id": 1, "player": 1, "name": "将"},
    "j19": {"piece_id": 1, "player": 0, "name": "将"},
    ...
  },
  "captured": {
    "0": [],
    "1": []
  },
  "pending_shoot": null
}
```

### moves - 合法手取得

```
> moves <pos>
```

例:
```
> moves j19
```

レスポンス:
```json
{
  "pos": "j19",
  "piece": {"id": 1, "name": "将", "player": 0},
  "moves": ["i18", "j18", "k18", "i19", "k19"],
  "can_promote": []
}
```

`can_promote`は移動先で成れる位置のリスト。

### allmoves - 全合法手取得

```
> allmoves
```

レスポンス:
```json
{
  "player": 0,
  "moves": [
    {"from": "j19", "to": "i18", "promote": false},
    {"from": "j19", "to": "i18", "promote": true},
    ...
  ]
}
```

### move - 駒を移動

```
> move <from> <to> [promote]
```

例:
```
> move j19 j18
> move e6 e5 promote
```

レスポンス（成功）:
```json
{
  "success": true,
  "from": "j19",
  "to": "j18",
  "captured": null,
  "promoted": false,
  "promoted_to": null,
  "pending_shoot": null,
  "winner": null
}
```

レスポンス（射撃待ち）:
```json
{
  "success": true,
  "from": "k10",
  "to": "k8",
  "captured": null,
  "promoted": false,
  "pending_shoot": {
    "targets": ["k6", "k7"],
    "count": 1
  },
  "winner": null
}
```

レスポンス（失敗）:
```json
{
  "success": false,
  "error": "そこには移動できません"
}
```

### shoot - 射撃

```
> shoot <pos>
> shoot skip
```

レスポンス:
```json
{
  "success": true,
  "target": "k6",
  "killed": [10],
  "winner": null
}
```

### reset - ゲームリセット

```
> reset
```

レスポンス:
```json
{
  "success": true
}
```

### quit - 終了

```
> quit
```

## 座標形式

- 列: a-s (a=0, s=18)
- 行: 1-19 (1=y:0=上端, 19=y:18=下端)
- 例: `a1`=左上(0,0), `s19`=右下(18,18), `j10`=中央(9,9)

## エラー形式

全エラーは以下の形式:
```json
{
  "success": false,
  "error": "エラーメッセージ"
}
```

## AIの実装例

```python
import subprocess
import json

class KoushougiAI:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["python", "main.py", "cli", "--machine"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )

    def send(self, cmd: str) -> dict:
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def get_state(self) -> dict:
        return self.send("state")

    def get_all_moves(self) -> dict:
        return self.send("allmoves")

    def move(self, from_pos: str, to_pos: str, promote: bool = False) -> dict:
        cmd = f"move {from_pos} {to_pos}"
        if promote:
            cmd += " promote"
        return self.send(cmd)

    def play_random(self):
        import random
        moves = self.get_all_moves()["moves"]
        if moves:
            m = random.choice(moves)
            return self.move(m["from"], m["to"], m["promote"])
        return None
```

## 駒ID一覧

| ID | 名前 | ID | 名前 |
|----|------|----|----- |
| 1 | 将 | 35 | 帥 |
| 2 | 記室 | 36 | 軍師 |
| 3 | 参謀 | 37 | 旗鼓 |
| 4 | 親兵 | 38 | 千戸 |
| 5 | 力士 | 39 | 百戸 |
| 6 | 舎人 | 40 | 副司 |
| 7 | 舎餘 | 41 | 毒火 |
| 8 | 軍吏 | 42 | 天網 |
| 9 | 軍匠 | 43 | 地網 |
| 10 | 高道 | 44 | 五里霧 |
| 11 | 神僧 | 45 | 聖燈 |
| 12 | 前衝 | 46 | 霹靂 |
| 13 | 後衝 | 47 | 招揺 |
| 14 | 中軍 | 48 | 龍驤 |
| 15 | 鼓 | 49 | 虎翼 |
| 16 | 旗 | 50 | 鷹揚 |
| 17 | 把総 | 51 | 彍騎 |
| 18 | 百総 | 52 | 弩騎 |
| 19 | 護兵 | 53 | 砲車 |
| 20 | 千総 | 54 | 神機車 |
| 21 | 騎総 | 55 | 天馬 |
| 22 | 仏狼機 | 56 | 都司 |
| 23 | 象 | 57 | 天塁 |
| 24 | 弓 | | |
| 25 | 弩 | | |
| 26 | 砲 | | |
| 27 | 馬兵 | | |
| 28 | 歩兵 | | |
| 29 | 歩総 | | |
| 30 | 牌 | | |
| 31 | 牌総 | | |
| 32 | 車 | | |
| 33 | 車総 | | |
| 34 | 先鋒 | | |

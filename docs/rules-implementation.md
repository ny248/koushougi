# 広将棋の初期配置と代表的な手

`python3 -m koushougi` で初期盤面を表示する。●は先手の黒、○は後手の白。座標は公開棋譜と同じく、列を A〜T（I を除く）、段を 1〜19 とする。白は段番号が増える方向へ進む。

`initial_state()` で初期盤面を取得し、`movement_actions(board, origin)` で指定した駒の移動と射撃を列挙できる。`preview_action(board, action)` は移動・捕獲後の盤面を返す。入力例に使う座標は `square("K7")` のように変換する。

対応する駒の移動と射撃は `movement_actions` が列挙する。`Game.play` は手番、成りの可否、終局を検証してから一手を適用する。勝者は `outcome` で取得できる。弩の遮蔽物は弓と同じ扱いを暫定採用している。敵陣への進入は、敵陣外から移動経路上の着地点で敵陣に入った場合とした。

[基準記事と初期配置図](https://akasaka0x16.blog.fc2.com/blog-entry-116.html)

検証は `python3 -m unittest discover -s tests -v` で実行する。

## ブラウザで盤面を操作する

`python3 -m koushougi.web` を実行し、ブラウザで <http://127.0.0.1:8765> を開く。手番側の駒を選ぶと、移動先が緑色で表示される。さらに移動できる場合は、次の着地点を選ぶか「この位置で移動を終える」を押す。移動後に射撃できる場合は、橙色の対象を選ぶか射撃を省略する。成れる場合は「成る」か「成らない」を選ぶ。すべての選択を確定すると手番が交代し、勝敗が決まった場合は勝者が表示される。「初期配置に戻す」で最初から操作できる。

成った駒の名前は赤文字で表示され、降格すると元の色に戻る。記室が軍師に成るときは、連動して成る味方の前衝・後衝を選べる。毒火による除去、五里霧による射撃制限、聖燈による降格、高道を失った場合の降格には、エンジンが処理した盤面を表示する。

毒火は周囲に別の駒が着地した場合にその駒を除去し、毒火自身が移動または成った場合には周囲の駒を除去する扱いとした。高道・五里霧の隣接捕獲は移動経路の最後で選ぶ。五里霧は距離5以内を射撃不可とし、仏狼機系が距離6以上から射撃できる扱いとした。公開棋譜との照合、反復や合法手がない場合の終局判定は未実施。

「対局相手」で「ランダムAI」を選ぶと、初期配置から人が先手、AIが後手で対局を始める。AIはエンジンが列挙した移動・射撃の候補から一手を無作為に選び、可能な場合は成りも無作為に選ぶ。


## 自己対戦と学習

`python3 -m koushougi.selfplay --games 20 --seed 202 --output random.jsonl` でランダム自己対戦を実行する。勝敗がついた対局だけを保存する。手数上限に達した対局は集計で `ply_limit` に数える。

`python3 -m koushougi.train_value random.jsonl --output generation-1.json` で局面評価を学習する。予測誤差は学習に使わなかった対局で測る。

`python3 -m koushougi.selfplay --games 12 --seed 203 --model generation-1.json --output guided.jsonl` で、その評価を使って次の自己対戦を実行する。通常は無作為に絞った最大8候補を評価し、15%の手番では既存のランダムAIに手を任せる。`python3 -m koushougi.train_value guided.jsonl --output generation-2.json` で次のモデルを学習する。

`python3 -m koushougi.evaluate_value generation-2.json --baseline generation-1.json --pairs 4` で先後を入れ替えて比較する。`--baseline` を省くとランダムAIと対戦する。勝敗と手数上限は個別に集計する。

## ブラウザだけで動く公開版

`python3 -m koushougi.build_static ./dist` で配布用のファイルを生成する。`dist` には未作成のディレクトリ名を指定する。

`python3 -m http.server 8775 --bind 127.0.0.1 --directory ./dist` を実行し、<http://127.0.0.1:8775/> で試せる。初回の読み込みには Pyodide を取得するためのインターネット接続が必要。盤面の計算とAIの応手はブラウザ内で実行する。

公開する場合は `dist` の中身を静的ホスティングへ配置する。

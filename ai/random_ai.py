"""ランダムAI - サブプロセスでCLIと通信"""

import subprocess
import json
import random
import sys
from typing import Optional


class RandomAI:
    """ランダムに合法手を選ぶAI"""

    def __init__(self, player: int = 0):
        """
        Args:
            player: このAIが担当するプレイヤー (0=先手, 1=後手)
        """
        self.player = player
        self.proc: Optional[subprocess.Popen] = None

    def start(self):
        """ゲームプロセスを開始"""
        self.proc = subprocess.Popen(
            [sys.executable, "main.py", "cli", "--machine"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )

    def stop(self):
        """ゲームプロセスを終了"""
        if self.proc:
            try:
                self.send("quit")
            except:
                pass
            self.proc.terminate()
            self.proc = None

    def send(self, cmd: str) -> dict:
        """コマンドを送信してJSONレスポンスを受信"""
        if not self.proc:
            raise RuntimeError("プロセスが開始されていません")

        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def get_state(self) -> dict:
        """ゲーム状態を取得"""
        return self.send("state")

    def get_all_moves(self) -> list:
        """全合法手を取得"""
        result = self.send("allmoves")
        return result.get("moves", [])

    def move(self, from_pos: str, to_pos: str, promote: bool = False) -> dict:
        """駒を移動"""
        cmd = f"move {from_pos} {to_pos}"
        if promote:
            cmd += " promote"
        return self.send(cmd)

    def shoot(self, pos: str) -> dict:
        """射撃"""
        return self.send(f"shoot {pos}")

    def skip_shoot(self) -> dict:
        """射撃をスキップ"""
        return self.send("shoot skip")

    def choose_move(self, moves: list) -> Optional[dict]:
        """ランダムに手を選択"""
        if not moves:
            return None
        return random.choice(moves)

    def play_turn(self) -> Optional[dict]:
        """1ターン分を実行"""
        state = self.get_state()

        # 自分の番でなければスキップ
        if state["player"] != self.player:
            return None

        # ゲーム終了チェック
        if state["game_over"]:
            return None

        # 射撃待ちの処理
        if state.get("pending_shoot"):
            targets = state["pending_shoot"]["targets"]
            if targets:
                # ランダムに射撃先を選択（50%でスキップ）
                if random.random() < 0.5:
                    target = random.choice(targets)
                    return self.shoot(target)
                else:
                    return self.skip_shoot()

        # 通常の移動
        moves = self.get_all_moves()
        chosen = self.choose_move(moves)
        if chosen:
            return self.move(chosen["from"], chosen["to"], chosen.get("promote", False))

        return None


def main():
    """AIを実行（両プレイヤーをランダムAIで対戦）"""
    print("=== ランダムAI対戦 ===")

    ai = RandomAI(player=0)
    ai.start()

    try:
        max_turns = 500  # 無限ループ防止
        turn = 0

        while turn < max_turns:
            state = ai.get_state()

            if state["game_over"]:
                winner = "先手" if state["winner"] == 0 else "後手"
                print(f"\n=== {winner}の勝ち！ ===")
                break

            current = "先手" if state["player"] == 0 else "後手"
            print(f"\nターン {turn + 1}: {current}番")

            # 射撃待ちの処理
            if state.get("pending_shoot"):
                targets = state["pending_shoot"]["targets"]
                if random.random() < 0.5 and targets:
                    target = random.choice(targets)
                    result = ai.shoot(target)
                    print(f"  射撃: {target}")
                else:
                    result = ai.skip_shoot()
                    print("  射撃スキップ")
                continue

            # 通常移動
            moves = ai.get_all_moves()
            if not moves:
                print("  合法手なし - 投了")
                break

            chosen = random.choice(moves)
            result = ai.move(chosen["from"], chosen["to"], chosen.get("promote", False))

            move_desc = f"{chosen['from']} -> {chosen['to']}"
            if chosen.get("promote"):
                move_desc += " (成)"
            if result.get("captured"):
                move_desc += f" [{result['captured']}を取る]"
            print(f"  移動: {move_desc}")

            if result.get("winner") is not None:
                winner = "先手" if result["winner"] == 0 else "後手"
                print(f"\n=== {winner}の勝ち！ ===")
                break

            turn += 1

        else:
            print(f"\n=== {max_turns}ターン経過 - 引き分け ===")

    finally:
        ai.stop()


if __name__ == "__main__":
    main()

"""広将棋 CLIインターフェース"""

import json
import sys
from typing import Optional
from backend.rules.game_engine import GameEngine
from backend.domain.piece_registry import get_piece


class GameCLI:
    """CLIゲームインターフェース"""

    def __init__(self, machine_mode: bool = False):
        self.engine = GameEngine()
        self.machine_mode = machine_mode

    def run(self):
        """メインループ"""
        if not self.machine_mode:
            print("=== 広将棋 CLI ===")
            print("コマンド: move <from> <to> | show | moves <pos> | help | quit")
            print("座標形式: a1, s19 など（a=0列, s=18列）")
            print()
            self.show_board()

        while not self.engine.is_game_over:
            if not self.machine_mode:
                turn = "先手" if self.engine.current_player == 0 else "後手"
                prompt = f"\n{turn}> "
            else:
                prompt = ""

            try:
                if self.machine_mode:
                    line = input().strip()
                else:
                    line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                if not self.machine_mode:
                    print("\n終了します")
                break

            if not line:
                continue

            self.execute_command(line)

        if self.engine.is_game_over and not self.machine_mode:
            winner = "先手" if self.engine.winner == 0 else "後手"
            print(f"\n=== {winner}の勝ち！ ===")

    def output(self, data: dict):
        """出力（machineモードではJSON）"""
        if self.machine_mode:
            print(json.dumps(data, ensure_ascii=False))
            sys.stdout.flush()
        else:
            # 人間用出力は各メソッドで個別に処理
            pass

    def output_error(self, message: str):
        """エラー出力"""
        if self.machine_mode:
            print(json.dumps({"success": False, "error": message}, ensure_ascii=False))
            sys.stdout.flush()
        else:
            print(f"エラー: {message}")

    def execute_command(self, line: str):
        """コマンド実行"""
        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("q", "quit", "exit"):
            if not self.machine_mode:
                print("終了します")
            sys.exit(0)

        elif cmd in ("h", "help", "?"):
            self.show_help()

        elif cmd in ("s", "show", "board"):
            self.show_board()

        elif cmd == "state":
            self.cmd_state()

        elif cmd == "allmoves":
            self.cmd_allmoves()

        elif cmd in ("m", "move"):
            if len(parts) < 3:
                self.output_error("使い方: move <from> <to> [promote]")
                return
            from_str = parts[1]
            to_str = parts[2]
            promote = len(parts) > 3 and parts[3].lower() in ("y", "yes", "promote", "成")
            self.do_move(from_str, to_str, promote)

        elif cmd in ("moves", "legal"):
            if len(parts) < 2:
                self.output_error("使い方: moves <pos>")
                return
            self.show_moves(parts[1])

        elif cmd == "shoot":
            if len(parts) < 2:
                self.output_error("使い方: shoot <pos> または shoot skip")
                return
            if parts[1].lower() in ("skip", "s", "pass"):
                self.do_shoot_skip()
            else:
                self.do_shoot(parts[1])

        elif cmd == "reset":
            self.engine = GameEngine()
            if self.machine_mode:
                self.output({"success": True})
            else:
                print("ゲームをリセットしました")
                self.show_board()

        else:
            # 座標2つならmoveとして解釈
            if len(parts) >= 2:
                from_pos = self.parse_pos(parts[0])
                to_pos = self.parse_pos(parts[1])
                if from_pos and to_pos:
                    promote = len(parts) > 2 and parts[2].lower() in ("y", "yes", "promote", "成")
                    self.do_move(parts[0], parts[1], promote)
                    return
            self.output_error(f"不明なコマンド: {cmd}")

    def cmd_state(self):
        """state コマンド - ゲーム状態をJSON出力"""
        board_data = {}
        for x in range(19):
            for y in range(19):
                piece_data = self.engine.state.board.get(x, y)
                if piece_data:
                    piece_id, player = piece_data
                    pos_str = self.format_pos(x, y)
                    try:
                        name = get_piece(piece_id).name
                    except:
                        name = "?"
                    board_data[pos_str] = {
                        "piece_id": piece_id,
                        "player": player,
                        "name": name
                    }

        captured = {"0": [], "1": []}

        pending_shoot = None
        shoot_targets = self.engine.get_shoot_targets()
        if shoot_targets:
            pending_shoot = {
                "targets": [self.format_pos(x, y) for x, y in shoot_targets]
            }

        data = {
            "turn": self.engine.state.move_count,
            "player": self.engine.current_player,
            "game_over": self.engine.is_game_over,
            "winner": self.engine.winner,
            "board": board_data,
            "captured": captured,
            "pending_shoot": pending_shoot
        }
        self.output(data)

    def cmd_allmoves(self):
        """allmoves コマンド - 全合法手をJSON出力"""
        player = self.engine.current_player
        all_moves = []

        for x in range(19):
            for y in range(19):
                piece_data = self.engine.state.board.get(x, y)
                if piece_data is None:
                    continue
                piece_id, owner = piece_data
                if owner != player:
                    continue

                from_pos = (x, y)
                from_str = self.format_pos(x, y)
                moves = self.engine.get_legal_moves(from_pos)

                for to_pos in moves:
                    to_str = self.format_pos(to_pos[0], to_pos[1])
                    can_promote = self._can_promote(from_pos, to_pos)

                    if can_promote:
                        # 成れる場合は両方の選択肢を出す
                        all_moves.append({"from": from_str, "to": to_str, "promote": False})
                        all_moves.append({"from": from_str, "to": to_str, "promote": True})
                    else:
                        all_moves.append({"from": from_str, "to": to_str, "promote": False})

        self.output({"player": player, "moves": all_moves})

    def _can_promote(self, from_pos: tuple[int, int], to_pos: tuple[int, int]) -> bool:
        """成れるか判定"""
        return self.engine.can_promote_at(from_pos, to_pos)

    def show_help(self):
        """ヘルプ表示"""
        if self.machine_mode:
            self.output({
                "commands": [
                    "state", "allmoves", "moves <pos>",
                    "move <from> <to> [promote]",
                    "shoot <pos>", "shoot skip",
                    "reset", "quit"
                ]
            })
        else:
            print("""
コマンド一覧:
  move <from> <to> [promote]  駒を移動（成りはpromoteを追加）
  <from> <to> [promote]       moveの省略形
  moves <pos>                 指定位置の駒の合法手を表示
  allmoves                    全合法手を表示
  state                       ゲーム状態を表示
  shoot <pos>                 射撃（射撃待ち時）
  shoot skip                  射撃をスキップ
  show                        盤面を表示
  reset                       ゲームをリセット
  help                        このヘルプを表示
  quit                        終了

座標形式:
  列: a-s (a=0, s=18)
  行: 1-19 (1=上端, 19=下端)
  例: a1=左上, s19=右下, j10=中央
""")

    def parse_pos(self, s: str) -> Optional[tuple[int, int]]:
        """座標文字列をパース (例: "e15" -> (4, 14))"""
        s = s.lower().strip()
        if len(s) < 2:
            return None

        col_char = s[0]
        if col_char < 'a' or col_char > 's':
            return None
        x = ord(col_char) - ord('a')

        try:
            row = int(s[1:])
        except ValueError:
            return None

        if row < 1 or row > 19:
            return None
        y = row - 1

        return (x, y)

    def format_pos(self, x: int, y: int) -> str:
        """座標を文字列に変換"""
        col = chr(ord('a') + x)
        row = y + 1
        return f"{col}{row}"

    def do_move(self, from_str: str, to_str: str, promote: bool = False):
        """移動実行"""
        from_pos = self.parse_pos(from_str)
        to_pos = self.parse_pos(to_str)

        if from_pos is None:
            self.output_error(f"無効な座標: {from_str}")
            return
        if to_pos is None:
            self.output_error(f"無効な座標: {to_str}")
            return

        result = self.engine.move(from_pos, to_pos, promote=promote)

        if result.success:
            if self.machine_mode:
                pending_shoot = None
                shoot_targets = self.engine.get_shoot_targets()
                if shoot_targets:
                    pending_shoot = {
                        "targets": [self.format_pos(x, y) for x, y in shoot_targets],
                        "count": 1
                    }

                self.output({
                    "success": True,
                    "from": from_str,
                    "to": to_str,
                    "captured": result.captured,
                    "promoted": result.promoted,
                    "promoted_to": result.promoted_to,
                    "pending_shoot": pending_shoot,
                    "winner": result.winner
                })
            else:
                msg_parts = [f"{from_str} -> {to_str}"]
                if result.captured:
                    try:
                        name = get_piece(result.captured).name
                        msg_parts.append(f"{name}を取った")
                    except:
                        pass
                if result.promoted:
                    msg_parts.append("成り！")
                print(" / ".join(msg_parts))

                targets = self.engine.get_shoot_targets()
                if targets:
                    print(f"射撃可能: {', '.join(self.format_pos(x, y) for x, y in targets)}")
                    print("shoot <pos> で射撃、shoot skip でスキップ")
                    return

                if result.winner is not None:
                    return

                self.show_board()
        else:
            self.output_error(result.error)

    def do_shoot(self, pos_str: str):
        """射撃実行"""
        pos = self.parse_pos(pos_str)
        if pos is None:
            self.output_error(f"無効な座標: {pos_str}")
            return

        result = self.engine.shoot([pos])
        if result.success:
            if self.machine_mode:
                self.output({
                    "success": True,
                    "target": pos_str,
                    "killed": result.path_kills or [],
                    "winner": result.winner
                })
            else:
                print(f"射撃: {pos_str}")
                if result.path_kills:
                    print(f"{len(result.path_kills)}体撃破")
                self.show_board()
        else:
            self.output_error(result.error)

    def do_shoot_skip(self):
        """射撃スキップ"""
        result = self.engine.skip_shoot()
        if result.success:
            if self.machine_mode:
                self.output({
                    "success": True,
                    "target": None,
                    "killed": [],
                    "winner": result.winner
                })
            else:
                print("射撃をスキップ")
                self.show_board()
        else:
            self.output_error(result.error)

    def show_moves(self, pos_str: str):
        """合法手表示"""
        pos = self.parse_pos(pos_str)
        if pos is None:
            self.output_error(f"無効な座標: {pos_str}")
            return

        piece_data = self.engine.state.board.get(pos[0], pos[1])
        if piece_data is None:
            self.output_error(f"{pos_str} に駒がありません")
            return

        piece_id, player = piece_data
        try:
            piece = get_piece(piece_id)
            name = piece.name
        except:
            name = "?"

        moves = self.engine.get_legal_moves(pos)
        move_strs = [self.format_pos(x, y) for x, y in sorted(moves)]

        # 成れる移動先を判定
        can_promote_moves = []
        for to_pos in moves:
            if self._can_promote(pos, to_pos):
                can_promote_moves.append(self.format_pos(to_pos[0], to_pos[1]))

        if self.machine_mode:
            self.output({
                "pos": pos_str,
                "piece": {"id": piece_id, "name": name, "player": player},
                "moves": move_strs,
                "can_promote": can_promote_moves
            })
        else:
            owner = "先手" if player == 0 else "後手"
            print(f"{pos_str}: {owner}の{name}")
            if moves:
                print(f"合法手 ({len(moves)}): {', '.join(move_strs)}")
                if can_promote_moves:
                    print(f"成り可能: {', '.join(can_promote_moves)}")
            else:
                print("合法手なし")

    def show_board(self):
        """盤面表示"""
        if self.machine_mode:
            # machineモードではstateコマンドを使用
            return

        print()
        print("    ", end="")
        for x in range(19):
            print(f" {chr(ord('a') + x)}", end="")
        print()

        print("   +" + "--" * 19 + "+")

        for y in range(19):
            print(f"{y+1:2} |", end="")
            for x in range(19):
                piece_data = self.engine.state.board.get(x, y)
                if piece_data is None:
                    print(" .", end="")
                else:
                    piece_id, player = piece_data
                    try:
                        name = get_piece(piece_id).name
                        char = name[0]
                    except:
                        char = "?"
                    if player == 0:
                        print(f" {char}", end="")
                    else:
                        print(f"'{char}", end="")
            print(" |")

        print("   +" + "--" * 19 + "+")

        turn = "先手" if self.engine.current_player == 0 else "後手"
        print(f"\n{turn}番")


def main():
    """エントリーポイント"""
    machine_mode = "--machine" in sys.argv
    cli = GameCLI(machine_mode=machine_mode)
    cli.run()


if __name__ == "__main__":
    main()

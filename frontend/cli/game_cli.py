"""広将棋 CLIインターフェース"""

import sys
from typing import Optional
from backend.rules.game_engine import GameEngine
from backend.domain.piece_registry import get_piece


class GameCLI:
    """CLIゲームインターフェース"""

    def __init__(self):
        self.engine = GameEngine()

    def run(self):
        """メインループ"""
        print("=== 広将棋 CLI ===")
        print("コマンド: move <from> <to> | show | moves <pos> | help | quit")
        print("座標形式: a1, s19 など（a=0列, s=18列）")
        print()

        self.show_board()

        while not self.engine.is_game_over:
            turn = "先手" if self.engine.current_player == 0 else "後手"
            prompt = f"\n{turn}> "

            try:
                line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n終了します")
                break

            if not line:
                continue

            self.execute_command(line)

        if self.engine.is_game_over:
            winner = "先手" if self.engine.winner == 0 else "後手"
            print(f"\n=== {winner}の勝ち！ ===")

    def execute_command(self, line: str):
        """コマンド実行"""
        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("q", "quit", "exit"):
            print("終了します")
            sys.exit(0)

        elif cmd in ("h", "help", "?"):
            self.show_help()

        elif cmd in ("s", "show", "board"):
            self.show_board()

        elif cmd in ("m", "move"):
            if len(parts) < 3:
                print("使い方: move <from> <to> [promote]")
                print("例: move e15 e14")
                return
            from_str = parts[1]
            to_str = parts[2]
            promote = len(parts) > 3 and parts[3].lower() in ("y", "yes", "promote", "成")
            self.do_move(from_str, to_str, promote)

        elif cmd in ("moves", "legal"):
            if len(parts) < 2:
                print("使い方: moves <pos>")
                return
            self.show_moves(parts[1])

        elif cmd == "shoot":
            if len(parts) < 2:
                print("使い方: shoot <pos> または shoot skip")
                return
            if parts[1].lower() in ("skip", "s", "pass"):
                self.do_shoot_skip()
            else:
                self.do_shoot(parts[1])

        elif cmd == "reset":
            self.engine = GameEngine()
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
            print(f"不明なコマンド: {cmd}")
            print("help でコマンド一覧を表示")

    def show_help(self):
        """ヘルプ表示"""
        print("""
コマンド一覧:
  move <from> <to> [promote]  駒を移動（成りはpromoteを追加）
  <from> <to> [promote]       moveの省略形
  moves <pos>                 指定位置の駒の合法手を表示
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

        # 列: a-s
        col_char = s[0]
        if col_char < 'a' or col_char > 's':
            return None
        x = ord(col_char) - ord('a')

        # 行: 1-19
        try:
            row = int(s[1:])
        except ValueError:
            return None

        if row < 1 or row > 19:
            return None
        y = row - 1  # 1-indexed to 0-indexed

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
            print(f"無効な座標: {from_str}")
            return
        if to_pos is None:
            print(f"無効な座標: {to_str}")
            return

        result = self.engine.move(from_pos, to_pos, promote=promote)

        if result.success:
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

            # 射撃待ち
            targets = self.engine.get_shoot_targets()
            if targets:
                print(f"射撃可能: {', '.join(self.format_pos(x, y) for x, y in targets)}")
                print("shoot <pos> で射撃、shoot skip でスキップ")
                return

            # 勝敗
            if result.winner is not None:
                return

            self.show_board()
        else:
            print(f"エラー: {result.error}")

    def do_shoot(self, pos_str: str):
        """射撃実行"""
        pos = self.parse_pos(pos_str)
        if pos is None:
            print(f"無効な座標: {pos_str}")
            return

        result = self.engine.shoot([pos])
        if result.success:
            print(f"射撃: {pos_str}")
            if result.path_kills:
                print(f"{len(result.path_kills)}体撃破")
            self.show_board()
        else:
            print(f"エラー: {result.error}")

    def do_shoot_skip(self):
        """射撃スキップ"""
        result = self.engine.skip_shoot()
        if result.success:
            print("射撃をスキップ")
            self.show_board()
        else:
            print(f"エラー: {result.error}")

    def show_moves(self, pos_str: str):
        """合法手表示"""
        pos = self.parse_pos(pos_str)
        if pos is None:
            print(f"無効な座標: {pos_str}")
            return

        piece_data = self.engine.state.board.get(pos[0], pos[1])
        if piece_data is None:
            print(f"{pos_str} に駒がありません")
            return

        piece_id, player = piece_data
        try:
            name = get_piece(piece_id).name
        except:
            name = "?"

        owner = "先手" if player == 0 else "後手"
        print(f"{pos_str}: {owner}の{name}")

        moves = self.engine.get_legal_moves(pos)
        if moves:
            move_strs = [self.format_pos(x, y) for x, y in sorted(moves)]
            print(f"合法手 ({len(moves)}): {', '.join(move_strs)}")
        else:
            print("合法手なし")

    def show_board(self):
        """盤面表示"""
        print()
        # 列ラベル
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
                    # 先手は大文字、後手は小文字っぽく表現
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

        # 手番
        turn = "先手" if self.engine.current_player == 0 else "後手"
        print(f"\n{turn}番")

        # 取った駒
        for player in [0, 1]:
            name = "先手" if player == 0 else "後手"
            captured = self.engine.state.captured.get(player)
            if captured:
                pieces = []
                for pid in captured[:10]:
                    try:
                        pieces.append(get_piece(pid).name)
                    except:
                        pass
                if pieces:
                    print(f"{name}の持ち駒: {' '.join(pieces)}")


def main():
    """エントリーポイント"""
    cli = GameCLI()
    cli.run()


if __name__ == "__main__":
    main()

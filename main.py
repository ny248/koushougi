#!/usr/bin/env python3
"""広将棋 - エントリーポイント"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="広将棋")
    parser.add_argument("mode", nargs="?", default="gui",
                        choices=["gui", "cli"],
                        help="実行モード (default: gui)")
    parser.add_argument("--kifu", type=str, default=None,
                        help="棋譜保存先（JSON Lines形式）")

    args = parser.parse_args()

    if args.mode == "cli":
        from frontend.cli.game_cli import main as cli_main
        cli_main()
    else:
        from frontend.pygame.game_app import main as gui_main
        gui_main(kifu_path=args.kifu)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""広将棋 - エントリーポイント"""

import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from frontend.cli.game_cli import main as cli_main
        cli_main()
    else:
        from frontend.pygame.game_app import main as gui_main
        gui_main()

if __name__ == "__main__":
    main()

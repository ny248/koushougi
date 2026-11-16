"""静的ホスティングへ配布する広将棋を組み立てる。"""

import argparse
from pathlib import Path
from shutil import copyfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="新規出力ディレクトリ")
    args = parser.parse_args()
    source = Path(__file__).parent
    args.output.mkdir()
    package = args.output / "koushougi"
    package.mkdir()
    for name in ("__init__.py", "game.py", "ai.py", "position.py"):
        copyfile(source / name, package / name)
    copyfile(source / "static_worker.mjs", args.output / "static_worker.mjs")
    html = (source / "board.html").read_text(encoding="utf-8")
    html = html.replace("<html lang=\"ja\">", '<html lang="ja" data-engine="browser">')
    (args.output / "index.html").write_text(html, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

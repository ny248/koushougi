"""ローカルで初期盤面を表示し、対応する駒を動かす。"""

import json
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .position import position
from .kifu import MAX_RECORD_BYTES, replay_record

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_position(self, history, *, ai=False, human_side="black"):
        try:
            if not isinstance(history, list):
                raise ValueError()
            payload = position(history, ai=ai, human_side=human_side)
            status = 200
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            payload = {"error": "指定された手を適用できません"}
            status = 400
        self.respond(status, "application/json", json.dumps(payload).encode())

    def do_GET(self):
        if self.path == "/":
            page = Path(__file__).with_name("board.html").read_bytes()
            self.respond(200, "text/html; charset=utf-8", page)
        elif self.path == "/position":
            self.send_position([])
        else:
            self.send_error(404)

    def do_POST(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        opponent = query.get("opponent", [""])[0]
        human_side = query.get("human", ["black"])[0]
        if human_side not in {"black", "white"}:
            self.send_error(400)
            return
        if url.path not in {"/position", "/record"} or opponent not in {"", "ai", "search"}:
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_RECORD_BYTES:
                raise ValueError()
            history = json.loads(self.rfile.read(size))
        except ValueError:
            self.send_error(400)
            return
        if url.path == "/record":
            try:
                payload = replay_record(history)
                self.respond(200, "application/json", json.dumps(payload).encode())
            except (ValueError, KeyError, TypeError, IndexError) as error:
                self.respond(400, "application/json", json.dumps({"error": str(error)}).encode())
        else:
            self.send_position(history, ai=opponent, human_side=human_side)


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)
    with ThreadingHTTPServer(address, Handler) as server:
        print("http://127.0.0.1:8765", flush=True)
        server.serve_forever()

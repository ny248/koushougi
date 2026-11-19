"""保存した棋譜を検証し、探索なしで再生する盤面を作る。"""

from . import Action, FILES, square
from .game import Game, outcome

MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_PLIES = 3000


def _cell(value):
    if not isinstance(value, str) or len(value) not in {2, 3}:
        raise ValueError("座標が不正です")
    if value[0] not in FILES or value[1:] not in {str(n) for n in range(1, 20)}:
        raise ValueError("座標が不正です")
    return square(value)


def _snapshot(game):
    return {"pieces": {f"{FILES[x]}{y + 1}": vars(piece)
                       for (x, y), piece in game.board.items()},
            "turn": game.turn, "winner": outcome(game.board), "moves": {}}


def replay_record(record):
    if not isinstance(record, dict) or record.get("format") != "koushougi-kifu" or type(record.get("version")) is not int or record["version"] != 1:
        raise ValueError("対応していない棋譜形式です")
    history = record.get("history")
    if not isinstance(history, list) or len(history) > MAX_PLIES:
        raise ValueError("棋譜は3000手以内にしてください")
    title = record.get("title", "保存した棋譜")
    note = record.get("note", "")
    if not isinstance(title, str) or len(title) > 200 or not isinstance(note, str) or len(note) > 1000:
        raise ValueError("棋譜の説明が不正です")
    opponent = record.get("opponent", "human")
    human_side = record.get("humanSide", "black")
    resigned = record.get("resignedSide")
    end_reason = record.get("endReason")
    if opponent not in ("human", "search") or human_side not in ("black", "white") or resigned not in (None, "black", "white") or end_reason not in (None, "win", "ply_limit", "no_legal_move"):
        raise ValueError("対局情報が不正です")
    game = Game()
    frames = [_snapshot(game)]
    moves = []
    for index, move in enumerate(history, 1):
        try:
            if not isinstance(move, dict) or type(move.get("promote")) is not bool:
                raise ValueError()
            for key, limit in (("path", 5), ("shots", 2), ("linked", 361), ("shot_steps", 2)):
                values = move.get(key, [])
                if not isinstance(values, list) or len(values) > limit:
                    raise ValueError()
            action = Action(_cell(move["from"]), tuple(map(_cell, move["path"])),
                            tuple(map(_cell, move.get("shots", []))), tuple(move.get("shot_steps", [])))
            game.play(action, move["promote"], tuple(map(_cell, move.get("linked", []))))
            moves.append({"from": move["from"], "path": move["path"],
                          "shots": move.get("shots", []), "shot_steps": list(action.shot_steps),
                          "promote": move["promote"], "linked": move.get("linked", [])})
            frames.append(_snapshot(game))
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise ValueError(f"{index}手目を適用できません") from error
    if resigned and outcome(game.board):
        raise ValueError("終局後の投了は記録できません")
    return {"record": {"format": "koushougi-kifu", "version": 1,
                       "title": title, "note": note, "history": moves,
                       "opponent": opponent, "humanSide": human_side,
                       "resignedSide": resigned, "endReason": end_reason},
            "frames": frames}

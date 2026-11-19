"""対局履歴から画面に表示する局面を組み立てる。"""

from . import Action, FILES, movement_actions, resolve_movement, square
from .players.alpha_beta import select_move as choose_search_move
from .game import Game, outcome, promotion


def label(cell):
    x, y = cell
    return f"{FILES[x]}{y + 1}"


def describe_action(board, action):
    promoted = promotion(board, action)
    result, _ = resolve_movement(board, action)
    linked = []
    if promoted == "軍師":
        side = board[action.origin].side
        linked = [label(cell) for cell, piece in result.items()
                  if piece.side == side and piece.name in {"前衝", "後衝"}]
    changes = {
        label(cell): vars(result[cell]) if cell in result else None
        for cell in board.keys() | result.keys()
        if board.get(cell) != result.get(cell)
    }
    sequence = []
    shot_steps = action.shot_steps or (len(action.path),) * len(action.shots)
    for step, cell in enumerate(action.path, 1):
        sequence.append({"kind": "move", "square": label(cell)})
        sequence.extend({"kind": "shoot", "square": label(target)}
                        for target, shot_step in zip(action.shots, shot_steps) if shot_step == step)
    return {"path": list(map(label, action.path)),
            "shots": list(map(label, action.shots)),
            "shot_steps": list(action.shot_steps), "sequence": sequence,
            "promotion": promoted, "linked": linked, "changes": changes}


def position(history, *, ai=False, human_side="black"):
    game = Game()
    for move in history:
        origin = square(move["from"])
        path = tuple(map(square, move["path"]))
        shots = tuple(map(square, move["shots"]))
        promote = move["promote"]
        if type(promote) is not bool:
            raise ValueError("成りの選択が不正です")
        game.play(Action(origin, path, shots, tuple(move.get("shot_steps", ()))),
                  promote, tuple(map(square, move.get("linked", []))))
    ai_move = None
    if ai and game.turn != human_side and not outcome(game.board):
        choice = choose_search_move(game)
        if choice is not None:
            action, promote, linked = choice
            game.play(action, promote, linked)
            ai_move = {"from": label(action.origin), "path": list(map(label, action.path)),
                       "shots": list(map(label, action.shots)), "promote": promote,
                       "shot_steps": list(action.shot_steps),
                       "linked": list(map(label, linked))}
    inspections = {}
    for cell, piece in game.board.items():
        actions = movement_actions(game.board, cell)
        inspections[label(cell)] = {
            "steps": sorted({label(action.path[0]) for action in actions}),
            "shots": sorted({label(target) for action in actions for target in action.shots}),
        }
    return {
        "inspections": inspections,
        "aiMove": ai_move,
        "turn": game.turn,
        "winner": outcome(game.board),
        "pieces": {label(cell): vars(piece) for cell, piece in game.board.items()},
        "moves": {
            label(cell): [
                describe_action(game.board, action)
                for action in game.actions(cell)
            ]
            for cell, piece in game.board.items()
            if piece.side == game.turn
        },
    }

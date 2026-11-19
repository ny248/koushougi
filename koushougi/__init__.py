"""広将棋の初期配置と代表的な手を検証するエンジン。"""

from dataclasses import dataclass
from functools import cache

FILES = "ABCDEFGHJKLMNOPQRST"
ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
DIRECTIONS = ORTHOGONAL + DIAGONAL
KNIGHT = tuple((x, y) for x in (-2, -1, 1, 2)
               for y in (-2, -1, 1, 2) if abs(x) + abs(y) == 3)

# 指定記事の初期配置図。白側の各段を A から T の順に記載する。
WHITE_ROWS = (
    "前衝 神僧 軍匠 軍吏 舎餘 舎人 力士 親兵 記室 将 参謀 親兵 力士 舎人 舎餘 軍吏 軍匠 高道 前衝",
    "後衝 百総 - 把総 - 千総 - 護兵 鼓 中軍 旗 護兵 - 千総 - 把総 - 百総 後衝",
    "象 砲 弩 弓 象 砲 弩 弓 象 仏狼機 象 弓 弩 砲 象 弓 弩 砲 象",
    "騎総 - 馬兵 - 馬兵 - 馬兵 - 馬兵 - 馬兵 - 馬兵 - 馬兵 - 馬兵 - 騎総",
    "- 歩総 - 歩兵 - 歩兵 - 歩兵 - 歩総 - 歩兵 - 歩兵 - 歩兵 - 歩総 -",
    "車総 牌総 車 牌 車 牌 車 牌 車 牌総 車 牌 車 牌 車 牌 車 牌総 車総",
    "- - - - - - - - - 先鋒 - - - - - - - - -",
)

Square = tuple[int, int]


@dataclass(frozen=True)
class Piece:
    side: str
    name: str
    promoted: bool = False


@dataclass(frozen=True)
class Action:
    origin: Square
    path: tuple[Square, ...]
    shots: tuple[Square, ...] = ()
    # 射撃する時点を移動回数で表す。省略時は従来どおり全移動の後に射撃する。
    shot_steps: tuple[int, ...] = ()

    def __post_init__(self):
        if self.shot_steps:
            if (len(self.shot_steps) != len(self.shots)
                    or any(type(step) is not int or not 1 <= step <= len(self.path)
                           for step in self.shot_steps)
                    or tuple(sorted(self.shot_steps)) != self.shot_steps):
                raise ValueError("射撃する移動段階が不正です")
            if all(step == len(self.path) for step in self.shot_steps):
                object.__setattr__(self, "shot_steps", ())


def square(label: str) -> Square:
    """公開棋譜と同じ座標を、0始まりの添字に変換する。"""
    if len(label) < 2 or label[0] not in FILES:
        raise ValueError(label)
    rank = int(label[1:])
    if not 1 <= rank <= 19:
        raise ValueError(label)
    return FILES.index(label[0]), rank - 1


def initial_state() -> dict[Square, Piece]:
    board = {}
    for y, row in enumerate(WHITE_ROWS):
        for x, name in enumerate(row.split()):
            if name != "-":
                board[x, y] = Piece("white", name)
                board[18 - x, 18 - y] = Piece("black", name)
    return board


def render(board: dict[Square, Piece]) -> str:
    rows = ["     " + " ".join(f"{file:^5}" for file in FILES)]
    for y in range(18, -1, -1):
        cells = []
        for x in range(19):
            piece = board.get((x, y))
            cells.append(("●" if piece.side == "black" else "○") + piece.name
                         if piece else "  ·  ")
        rows.append(f"{y + 1:2}   " + " ".join(cells))
    return "\n".join(rows)


def _rays(origin, directions, limit):
    for dx, dy in directions:
        ray = []
        for distance in range(1, limit + 1):
            x, y = origin[0] + dx * distance, origin[1] + dy * distance
            if not (0 <= x < 19 and 0 <= y < 19):
                break
            ray.append((x, y))
        yield ray


SHOT_KIND = {"弓": "弓", "彍騎": "弓", "弩": "弩", "弩騎": "弩",
             "砲": "砲", "砲車": "砲", "仏狼機": "仏狼機", "神機車": "仏狼機"}
SHOT_RANGE = {"弓": 3, "弩": 5, "砲": 5, "仏狼機": 7}
SHIELDS = {"牌総", "天塁"}
ARROW_IMMUNE = SHIELDS | {"牌", "車", "車総", "砲車"}


PRIESTS = {"高道", "五里霧", "神僧", "聖燈"}
DOUBLE_PRIESTS = {"五里霧", "聖燈"}
DOUBLE_DIRECTIONS = tuple((2*x, 2*y) for x, y in DIRECTIONS)
DOUBLE_ORTHOGONAL = DOUBLE_DIRECTIONS[:4]
DOUBLE_DIAGONAL = DOUBLE_DIRECTIONS[4:]


def distance(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def settle(board):
    """強制的に元の駒へ戻る効果を適用する。"""
    locations = getattr(board, "special_squares", None)
    if locations is None:
        affected = [(cell, piece) for cell, piece in board.items()
                    if piece.name in {"招揺", "霹靂", "五里霧"}]
    else:
        affected = [(cell, board[cell]) for name in ("招揺", "霹靂", "五里霧")
                    for cell in locations[name]]
    if not affected:
        return
    if locations is None:
        high_priests = {p.side for p in board.values() if p.name in {"高道", "五里霧"}}
        lamps = [(cell, p.side) for cell, p in board.items() if p.name == "聖燈"]
    else:
        high_priests = {board[cell].side for name in ("高道", "五里霧") for cell in locations[name]}
        lamps = [(cell, board[cell].side) for cell in locations["聖燈"]]
    for cell, piece in affected:
        if piece.name in {"招揺", "霹靂"} and piece.side not in high_priests:
            board[cell] = Piece(piece.side, {"招揺": "旗", "霹靂": "鼓"}[piece.name])
        elif piece.name == "五里霧" and any(
            side != piece.side and distance(cell, lamp) <= 5
            and (cell[0] == lamp[0] or cell[1] == lamp[1]
                 or abs(cell[0] - lamp[0]) == abs(cell[1] - lamp[1]))
            for lamp, side in lamps
        ):
            board[cell] = Piece(piece.side, "高道")


def land(board, origin, target, captures):
    """着地時の捕獲と毒火を処理する。"""
    piece = board.pop(origin)
    victim = board.pop(target, None)
    if victim:
        captures.append(victim)
    board[target] = piece
    if piece.name == "毒火":
        for ray in _rays(target, DIRECTIONS, 1):
            if ray and ray[0] in board:
                captures.append(board.pop(ray[0]))
    else:
        x, y = target
        for dx, dy in DIRECTIONS:
            neighbor = board.get((x + dx, y + dy))
            if neighbor is not None and neighbor.name == "毒火":
                captures.append(board.pop(target))
                break
    settle(board)


def _shots(board, origin, piece):
    kind = SHOT_KIND.get(piece.name)
    if kind is None:
        if piece.name in PRIESTS:
            for ray in _rays(origin, DIRECTIONS, 1):
                if ray and ray[0] in board and board[ray[0]].side != piece.side:
                    yield (ray[0],)
        return
    locations = getattr(board, "special_squares", None)
    fog = board.items() if locations is None else ((cell, board[cell]) for cell in locations["五里霧"])
    if any(p.name == "五里霧" and p.side != piece.side and distance(cell, origin) <= 5
           for cell, p in fog):
        return
    immune = ARROW_IMMUNE if kind in {"弓", "弩"} else SHIELDS
    if kind != "仏狼機":
        immune = immune | {"五里霧"}
    for ray in _rays(origin, DIRECTIONS, SHOT_RANGE[kind]):
        for target in ray:
            occupant = board.get(target)
            if occupant is None:
                continue
            if occupant.side != piece.side and occupant.name not in immune:
                yield (target,)
            if kind != "砲" or occupant.name in SHIELDS:
                break


@cache
def _movement_patterns(side):
    front = (0, 1 if side == "white" else -1)
    back = (0, -front[1])
    horizontal = ((1, 0), (-1, 0))
    vertical = (front, back)
    patterns = {
        "歩兵": ((ORTHOGONAL, 1),),
        "先鋒": (((front,), 5),),
        "車": ((ORTHOGONAL, 5),),
        "車総": ((ORTHOGONAL, 18),),
        "牌": ((DIAGONAL, 1),),
        "牌総": ((DIAGONAL, 1), (((1, 0), (-1, 0)), 18)),
        "象": ((DIAGONAL, 18),),
        "将": ((DIRECTIONS, 1),),
        "中軍": ((DIRECTIONS, 1),),
        "馬兵": ((KNIGHT, 1),),
        "騎総": ((KNIGHT, 1),),
        "天馬": ((KNIGHT, 1),),
        "歩総": ((vertical, 18), (horizontal, 1)),
        "都司": ((vertical + DIAGONAL, 18),),
        "千総": ((DIRECTIONS, 18),),
        "天塁": ((horizontal + DIAGONAL, 18),),
        "帥": ((DIRECTIONS, 1),),
        "彍騎": ((KNIGHT, 1),),
        "弩騎": ((KNIGHT, 1),),
        "砲車": ((ORTHOGONAL, 5),),
        "神機車": ((ORTHOGONAL, 5),),
        "旗": ((horizontal + DIAGONAL, 1),),
        "鼓": ((horizontal + DIAGONAL, 1),),
        "百総": ((DIAGONAL, 18), (ORTHOGONAL, 1)),
        "把総": ((ORTHOGONAL, 18), (DIAGONAL, 1)),
        "力士": ((DIRECTIONS, 1),),
    }
    forward_diagonal = tuple(d for d in DIAGONAL if d[1] == front[1])
    backward_diagonal = tuple(d for d in DIAGONAL if d[1] == back[1])
    all_except = lambda *excluded: tuple(d for d in DIRECTIONS if d not in excluded)
    patterns.update({
        "親兵": ((all_except(back), 1),),
        "護兵": ((all_except(front), 1),),
        "舎人": ((all_except(*backward_diagonal), 1),),
        "舎餘": ((DIAGONAL + (front,), 1),),
        "軍吏": ((DIAGONAL + vertical, 1),),
        "軍匠": ((forward_diagonal + vertical, 1),),
        "毒火": ((forward_diagonal + vertical, 1),),
        "千戸": ((vertical, 18), ((horizontal + DIAGONAL), 1)),
        "百戸": ((horizontal, 18), ((vertical + DIAGONAL), 1)),
        "副司": ((DIAGONAL + (front,), 18),),
        "前衝": (((front,), 18), ((back,), 1)),
        "後衝": (((back,), 18), ((front,), 1)),
        "天網": ((horizontal + forward_diagonal, 18), ((back,), 1)),
        "地網": ((horizontal + backward_diagonal, 18), ((front,), 1)),
        "記室": ((DIAGONAL + DOUBLE_ORTHOGONAL, 1),),
        "軍師": ((DIAGONAL + DOUBLE_ORTHOGONAL, 1),),
        "参謀": ((ORTHOGONAL + DOUBLE_DIAGONAL, 1),),
        "旗鼓": ((ORTHOGONAL + DOUBLE_DIAGONAL, 1),),
        "招揺": ((ORTHOGONAL, 5),),
        "霹靂": ((ORTHOGONAL, 1),),
        "鷹揚": ((DIAGONAL, 18), (ORTHOGONAL, 1)),
        "虎翼": ((ORTHOGONAL, 18), (DIAGONAL, 1)),
        "龍驤": ((DIRECTIONS, 18),),
        **{name: ((DOUBLE_DIRECTIONS, 1),) for name in PRIESTS},
    })
    patterns.update({name: ((DIAGONAL, 1),) for name in SHOT_RANGE})
    return patterns


REPEAT_STEPS = {
    "天馬": (KNIGHT, 2), "力士": (DIRECTIONS, 2), "龍驤": (DIRECTIONS, 2),
    "霹靂": (ORTHOGONAL, 5), "鷹揚": (ORTHOGONAL, 2), "虎翼": (DIAGONAL, 2),
    "軍師": (DIAGONAL + DOUBLE_ORTHOGONAL, 2),
    "旗鼓": (ORTHOGONAL + DOUBLE_DIAGONAL, 2),
    "五里霧": (DOUBLE_DIRECTIONS, 2), "聖燈": (DOUBLE_DIRECTIONS, 2),
}


def _paths(board, origin, piece):
    front = (0, 1 if piece.side == "white" else -1)
    patterns = _movement_patterns(piece.side)
    if piece.name not in patterns:
        raise NotImplementedError(piece.name)

    def can_land(position, cell):
        occupant = position.get(cell)
        return occupant is None or (
            occupant.side != piece.side
            and (piece.name not in PRIESTS or occupant.name in PRIESTS)
            and not (occupant.name == "天塁" and piece.name in {"車", "車総", "砲車", "神機車"})
        )

    def extend(position, path, steps, offset, remaining):
        if not remaining:
            return
        for ray in _rays(path[-1], steps, 1):
            if not ray:
                continue
            target = ray[0]
            if not can_land(position, target):
                continue
            if piece.name in {"天馬", "力士", "鷹揚", "虎翼", "龍驤"} and (
                target == origin and target not in position and not offset
            ):
                continue
            next_path = (*path, target)
            yield next_path
            if remaining > 1:
                moved = position.copy()
                captures = []
                land(moved, path[-1], target, captures)
                if moved.get(target) == piece:
                    yield from extend(moved, next_path, steps, offset or bool(captures), remaining - 1)

    drum = piece.name == "歩兵" and any(
        p.side == piece.side and p.name in {"鼓", "霹靂"} for p in board.values())
    for directions, limit in patterns[piece.name]:
        if piece.name == "歩兵" and not drum:
            directions = tuple(direction for direction in directions if direction != front)
        for ray in _rays(origin, directions, limit):
            for index, target in enumerate(ray):
                if not can_land(board, target):
                    break
                if piece.name == "招揺":
                    yield tuple(ray[:index + 1])
                    if any(p.name == "毒火" and distance(target, cell) == 1
                           and cell not in ray[:index + 1] for cell, p in board.items()):
                        break
                    continue
                yield (target,)
                delta = target[0] - origin[0], target[1] - origin[1]
                steps, count = REPEAT_STEPS.get(piece.name, ((), 1))
                if piece.name == "騎総":
                    # 2路進んだ軸は向きを保ち、1路進む軸は左右を選べる。
                    dx, dy = delta
                    inward = (dx, -dy) if abs(dx) == 2 else (-dx, dy)
                    steps, count = (delta, inward), 2
                if delta in steps:
                    moved = board.copy()
                    captures = []
                    land(moved, origin, target, captures)
                    if moved.get(target) == piece:
                        yield from extend(moved, (target,), steps, bool(captures), count - 1)
                if target in board:
                    break


def _priest_actions(board, origin, piece):
    def extend(position, current, path, shots, shot_steps, remaining):
        for step in _paths(position, current, piece):
            if len(step) != 1:
                continue
            target = step[0]
            moved, _ = resolve_movement(position, Action(current, step))
            next_path = (*path, target)
            options = [(moved, shots, shot_steps)]
            shooter = moved.get(target)
            if shooter is not None:
                for (victim,) in _shots(moved, target, shooter):
                    after_shot = moved.copy()
                    del after_shot[victim]
                    settle(after_shot)
                    options.append((after_shot, (*shots, victim), (*shot_steps, len(next_path))))
            for result, next_shots, next_shot_steps in options:
                yield Action(origin, next_path, next_shots, next_shot_steps)
                if remaining > 1 and result.get(target) == piece:
                    yield from extend(result, target, next_path, next_shots, next_shot_steps, remaining - 1)

    yield from extend(board, origin, (), (), (), 2 if piece.name in DOUBLE_PRIESTS else 1)


def movement_actions(board: dict[Square, Piece], origin: Square) -> tuple[Action, ...]:
    """指定駒の移動経路と射撃を列挙する。"""
    piece = board[origin]
    if piece.name in PRIESTS:
        return tuple(dict.fromkeys(_priest_actions(board, origin, piece)))
    actions = []
    for path in _paths(board, origin, piece):
        base = Action(origin, path)
        actions.append(base)
        if piece.name not in SHOT_KIND:
            continue
        moved, _ = resolve_movement(board, base)
        shooter = moved.get(path[-1])
        if shooter is None:
            continue
        shots = tuple(_shots(moved, path[-1], shooter))
        actions.extend(Action(origin, path, shot) for shot in shots)
        if SHOT_KIND.get(shooter.name) == "仏狼機":
            for (first,) in shots:
                after_first = moved.copy()
                del after_first[first]
                settle(after_first)
                for (second,) in _shots(after_first, path[-1], shooter):
                    actions.append(Action(origin, path, (first, second)))
    return tuple(dict.fromkeys(actions))


def resolve_movement(board, action):
    """列挙された一手の盤面と、取り除かれた駒を返す。"""
    result = board.copy()
    captures = []
    origin = action.origin
    shot_steps = action.shot_steps or (len(action.path),) * len(action.shots)
    for step, target in enumerate(action.path, 1):
        land(result, origin, target, captures)
        origin = target
        for victim, shot_step in zip(action.shots, shot_steps):
            if shot_step == step:
                captures.append(result.pop(victim))
                settle(result)
    return result, captures


def preview_action(board: dict[Square, Piece], action: Action) -> dict[Square, Piece]:
    if action not in movement_actions(board, action.origin):
        raise ValueError("選択した駒では実行できない手です")
    return resolve_movement(board, action)[0]

"""対局の一手と勝敗を扱う。"""

from copy import copy
from itertools import combinations

from . import Piece, initial_state, land, movement_actions, resolve_movement, settle
from .board import Board

PROMOTIONS = {
    "歩兵": "歩総", "歩総": "都司", "先鋒": "都司", "車": "車総",
    "車総": "千総", "牌": "牌総", "牌総": "天塁", "馬兵": "騎総",
    "騎総": "天馬", "弓": "彍騎", "弩": "弩騎", "砲": "砲車",
    "仏狼機": "神機車", "中軍": "帥", "百総": "鷹揚", "把総": "虎翼",
    "千総": "龍驤", "旗": "招揺", "鼓": "霹靂", "記室": "軍師", "参謀": "旗鼓",
    "親兵": "把総", "護兵": "百総", "舎人": "千戸", "舎餘": "百戸",
    "軍吏": "副司", "軍匠": "毒火", "高道": "五里霧", "神僧": "聖燈",
    "前衝": "天網", "後衝": "地網",
}
CAPTURE_PROMOTES = {"将", "中軍", "帥", "旗", "鼓"}
ONE_STEP = {"親兵", "舎人", "舎餘", "軍吏", "軍匠", "中軍", "鼓",
            "護兵", "仏狼機", "弓", "弩", "砲", "歩兵", "牌", "旗"}
LINKABLE = {"前衝", "後衝"}


def promotion(board, action):
    """列挙済みの手について、任意で成れる駒名を返す。"""
    piece = board[action.origin]
    if piece.promoted or piece.name not in PROMOTIONS:
        return None
    result, removed = resolve_movement(board, action)
    return _promotion(piece, action, result, removed)


def _promotion(piece, action, result, removed):
    if piece.promoted:
        return None
    promoted = PROMOTIONS.get(piece.name)
    if promoted is None:
        return None
    if action.path[-1] not in result and piece.name != "記室":
        return None
    if piece.name in {"旗", "鼓"} and not any(
        p.side == piece.side and p.name in {"高道", "五里霧"} for p in result.values()
    ):
        return None
    enemy_zone = range(13, 19) if piece.side == "white" else range(6)
    if action.origin[1] not in enemy_zone and any(y in enemy_zone for _, y in action.path):
        return promoted
    captured = {victim.name for victim in removed if victim.side != piece.side}
    if captured & CAPTURE_PROMOTES:
        return promoted
    if piece.name in ONE_STEP and captured & {"力士", "龍驤", "招揺", "霹靂"}:
        return promoted
    if piece.name == "馬兵" and "仏狼機" in captured:
        return promoted
    return None


def outcome(board):
    """将・中軍（帥）・旗（招揺）の残存状態から勝者を返す。"""
    leaders, commanders, flags = set(), set(), set()
    for piece in board.values():
        if piece.name in {"将", "帥"}:
            leaders.add(piece.side)
            if "black" in leaders and "white" in leaders:
                return None
        elif piece.name == "中軍":
            commanders.add(piece.side)
        elif piece.name in {"旗", "招揺"}:
            flags.add(piece.side)
    for side, opponent in (("black", "white"), ("white", "black")):
        if side not in leaders and (side not in commanders or side not in flags):
            return opponent
    return None


class Game:
    def __init__(self):
        self.board = Board(initial_state())
        self.turn = "black"
        self._last_position = self.position_hash
        self._position_counts = {self._last_position: 1}

    @property
    def position_hash(self):
        board = self.board if isinstance(self.board, Board) else Board(self.board)
        return (board.position_hash << 1) | (self.turn == "white")

    def _sync_repetition(self):
        current = self.position_hash
        if current != self._last_position:
            # 棋譜の途中局面やテスト用の盤面を直接設定した場合は、そこを起点にする。
            self._position_counts = {current: 1}
            self._last_position = current

    @property
    def repetition_count(self):
        self._sync_repetition()
        return self._position_counts[self._last_position]

    @property
    def is_draw(self):
        return self.repetition_count >= 4

    @property
    def result(self):
        return outcome(self.board) or ("draw" if self.is_draw else None)

    def actions(self, origin):
        piece = self.board.get(origin)
        if piece is None or piece.side != self.turn or self.result:
            return ()
        try:
            return movement_actions(self.board, origin)
        except NotImplementedError:
            return ()

    def play(self, action, promote=False, linked=()):
        if action not in self.actions(action.origin):
            raise ValueError("手を適用できません")
        board, removed = resolve_movement(self.board, action)
        promoted = _promotion(self.board[action.origin], action, board, removed) if promote else None
        if promote and promoted is None:
            raise ValueError("この手では成れません")
        self._finish_move(board, action.path[-1], promoted, linked)

    def successors(self, *, captures_only=False):
        """合法手と遷移先を返す。移動・射撃後の盤面は成りの候補間で共有する。"""
        source = self.board if isinstance(self.board, Board) else Board(self.board)
        for origin, piece in self.board.items():
            if piece.side != self.turn:
                continue
            for action in self.actions(origin):
                board, removed = resolve_movement(source, action)
                captures_enemy = captures_only and any(p.side != self.turn for p in removed)
                if not captures_only or captures_enemy:
                    child = copy(self)
                    child._finish_move(board, action.path[-1], None, ())
                    yield (action, False, ()), child
                promoted = _promotion(piece, action, board, removed)
                if promoted is None:
                    continue
                extra_capture = captures_only and not captures_enemy
                if extra_capture and promoted not in {"毒火", "軍師"}:
                    continue
                eligible = tuple(cell for cell, other in sorted(board.items())
                                 if other.side == self.turn and other.name in LINKABLE
                                 ) if promoted == "軍師" else ()
                for count in range(len(eligible) + 1):
                    for linked in combinations(eligible, count):
                        child = copy(self)
                        child._finish_move(board.copy(), action.path[-1], promoted, linked)
                        if extra_capture and not any(
                            target.side != self.turn and cell not in child.board
                            for cell, target in board.items()
                        ):
                            continue
                        yield (action, True, linked), child

    def _finish_move(self, board, destination, promoted, linked):
        self._sync_repetition()
        if linked and promoted != "軍師":
            raise ValueError("連動して成ることはできません")
        for cell in linked:
            piece = board.get(cell)
            if piece is None or piece.side != self.turn or piece.name not in LINKABLE:
                raise ValueError("連動して成る駒が不正です")
            board[cell] = Piece(self.turn, PROMOTIONS[piece.name], True)
        if promoted and destination in board:
            board[destination] = Piece(self.turn, promoted, True)
            if promoted == "毒火":
                land(board, destination, destination, [])
        if promoted == "軍師":
            poison = [cell for cell, piece in board.items()
                      if piece.side != self.turn and piece.name == "毒火"]
            for cell in poison:
                del board[cell]
        if promoted:
            settle(board)
        self.board = board
        self.turn = "white" if self.turn == "black" else "black"
        # 浅いコピーで作る探索の分岐と親局面で、カウンタを共有して変更しない。
        self._position_counts = self._position_counts.copy()
        self._last_position = self.position_hash
        self._position_counts[self._last_position] = self._position_counts.get(self._last_position, 0) + 1

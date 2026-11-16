"""対局の一手と勝敗を扱う。"""

from . import Piece, initial_state, land, movement_actions, resolve_movement, settle

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


def promotion(board, action):
    """列挙済みの手について、任意で成れる駒名を返す。"""
    piece = board[action.origin]
    promoted = PROMOTIONS.get(piece.name)
    if promoted is None:
        return None
    result, removed = resolve_movement(board, action)
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
    for side, opponent in (("black", "white"), ("white", "black")):
        names = {piece.name for piece in board.values() if piece.side == side}
        if "将" not in names and "帥" not in names and (
            "中軍" not in names or not names.intersection({"旗", "招揺"})
        ):
            return opponent
    return None


class Game:
    def __init__(self):
        self.board = initial_state()
        self.turn = "black"

    def actions(self, origin):
        piece = self.board.get(origin)
        if piece is None or piece.side != self.turn or outcome(self.board):
            return ()
        try:
            return movement_actions(self.board, origin)
        except NotImplementedError:
            return ()

    def play(self, action, promote=False, linked=()):
        if action not in self.actions(action.origin):
            raise ValueError("手を適用できません")
        promoted = promotion(self.board, action) if promote else None
        if promote and promoted is None:
            raise ValueError("この手では成れません")
        board, _ = resolve_movement(self.board, action)
        destination = action.path[-1]
        if linked and promoted != "軍師":
            raise ValueError("連動して成ることはできません")
        for cell in linked:
            piece = board.get(cell)
            if piece is None or piece.side != self.turn or piece.name not in {"前衝", "後衝"}:
                raise ValueError("連動して成る駒が不正です")
            board[cell] = Piece(self.turn, PROMOTIONS[piece.name], True)
        if promoted and destination in board:
            board[destination] = Piece(self.turn, promoted, True)
            if promoted == "毒火":
                land(board, destination, destination, [])
        if promoted == "軍師":
            board = {cell: piece for cell, piece in board.items()
                     if piece.side == self.turn or piece.name != "毒火"}
        settle(board)
        self.board = board
        self.turn = "white" if self.turn == "black" else "black"

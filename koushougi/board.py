"""駒の変更に合わせて評価値と特殊効果の位置を更新する盤面。"""

from functools import lru_cache
from hashlib import blake2b

from .evaluation import material_contribution


_MISSING = object()
_SPECIAL_NAMES = ("招揺", "霹靂", "五里霧", "高道", "聖燈")


@lru_cache(maxsize=65536)
def _piece_hash(cell, piece):
    value = f"{cell[0]},{cell[1]},{piece.side},{piece.name},{int(piece.promoted)}"
    return int.from_bytes(blake2b(value.encode(), digest_size=16).digest(), "big")


class Board(dict):
    """辞書として編集でき、コピーした盤面とは集計情報を共有しない。"""

    def __init__(self, pieces=()):
        super().__init__()
        self.material_balance = 0
        self.position_hash = 0
        self.special_squares = {name: set() for name in _SPECIAL_NAMES}
        self.update(pieces)

    def _subtract_piece(self, cell, piece):
        self.material_balance -= material_contribution(cell, piece)
        self.position_hash ^= _piece_hash(cell, piece)
        locations = self.special_squares.get(piece.name)
        if locations is not None:
            locations.remove(cell)

    def __setitem__(self, cell, piece):
        contribution = material_contribution(cell, piece)
        previous = self.get(cell)
        if previous is not None:
            self._subtract_piece(cell, previous)
        super().__setitem__(cell, piece)
        self.material_balance += contribution
        self.position_hash ^= _piece_hash(cell, piece)
        locations = self.special_squares.get(piece.name)
        if locations is not None:
            locations.add(cell)

    def __delitem__(self, cell):
        piece = self[cell]
        super().__delitem__(cell)
        self._subtract_piece(cell, piece)

    def pop(self, cell, default=_MISSING):
        if cell not in self:
            if default is _MISSING:
                raise KeyError(cell)
            return default
        piece = self[cell]
        del self[cell]
        return piece

    def popitem(self):
        cell, piece = super().popitem()
        self._subtract_piece(cell, piece)
        return cell, piece

    def update(self, pieces=(), **kwargs):
        for cell, piece in dict(pieces, **kwargs).items():
            self[cell] = piece

    def setdefault(self, cell, default=None):
        if cell not in self:
            self[cell] = default
        return self[cell]

    def clear(self):
        super().clear()
        self.material_balance = 0
        self.position_hash = 0
        for locations in self.special_squares.values():
            locations.clear()

    def copy(self):
        board = type(self).__new__(type(self))
        dict.__init__(board, self)
        board.material_balance = self.material_balance
        board.position_hash = self.position_hash
        board.special_squares = {name: locations.copy() for name, locations in self.special_squares.items()}
        return board

    def __copy__(self):
        return self.copy()

    def __ior__(self, pieces):
        self.update(pieces)
        return self

    def __reduce_ex__(self, protocol):
        return type(self), (dict(self),)

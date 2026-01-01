"""盤面クラス"""

from config import BOARD_SIZE


class Board:
    """19x19の盤面"""

    def __init__(self):
        # grid[x][y] = (piece_id, player, is_promoted) or None
        # is_promoted: この駒が成った状態かどうか
        self.grid = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

    def is_valid(self, x, y):
        """座標が盤面内か"""
        return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE

    def get(self, x, y):
        """指定位置の駒を取得。(piece_id, player) or None

        Note: is_promotedはget_promoted()で個別に取得する。
        """
        if not self.is_valid(x, y):
            return None
        cell = self.grid[x][y]
        if cell is None:
            return None
        return (cell[0], cell[1])

    def get_promoted(self, x, y):
        """指定位置の駒が成った状態かどうか"""
        if not self.is_valid(x, y):
            return False
        cell = self.grid[x][y]
        if cell is None:
            return False
        return cell[2] if len(cell) > 2 else False

    def set(self, x, y, piece_id, player, is_promoted=False):
        """駒を配置"""
        self.grid[x][y] = (piece_id, player, is_promoted)

    def remove(self, x, y):
        """駒を除去"""
        self.grid[x][y] = None

    def has_ally(self, x, y, player):
        """指定位置に味方駒があるか"""
        piece = self.get(x, y)
        return piece is not None and piece[1] == player

    def has_enemy(self, x, y, player):
        """指定位置に敵駒があるか"""
        piece = self.get(x, y)
        return piece is not None and piece[1] != player

    def is_empty(self, x, y):
        """指定位置が空か"""
        return self.get(x, y) is None

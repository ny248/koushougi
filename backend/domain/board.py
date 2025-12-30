"""盤面クラス"""

BOARD_SIZE = 19


class Board:
    """19x19の盤面"""

    def __init__(self):
        # grid[x][y] = (piece_id, player) or None
        self.grid = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

    def is_valid(self, x, y):
        """座標が盤面内か"""
        return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE

    def get(self, x, y):
        """指定位置の駒を取得。(piece_id, player) or None"""
        if not self.is_valid(x, y):
            return None
        return self.grid[x][y]

    def set(self, x, y, piece_id, player):
        """駒を配置"""
        self.grid[x][y] = (piece_id, player)

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

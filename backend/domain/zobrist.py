"""Zobrist Hashing for board position identification

Zobrist hashは盤面の同一性を高速に判定するためのハッシュ方式。
- 各マス×駒種×プレイヤー×成り状態に対して事前生成した乱数をXOR
- 差分更新が可能（駒の追加/削除はXOR1回）
- 千日手判定やTransposition Tableに使用

Usage:
    from backend.domain.zobrist import ZobristTable
    table = ZobristTable()
    hash_value = table.compute_full_hash(board, current_player)
    # 差分更新
    hash_value ^= table.piece_hash(x, y, piece_id, player, is_promoted)
    hash_value ^= table.turn_hash()
"""

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .board import Board

# 盤面サイズ
BOARD_SIZE = 19
# 駒種の最大ID（57種 + 余裕）
MAX_PIECE_ID = 60
# プレイヤー数
NUM_PLAYERS = 2
# 成り状態数（不成/成）
NUM_PROMOTED_STATES = 2

# 乱数のシード（再現性のため固定）
ZOBRIST_SEED = 20240101


class ZobristTable:
    """Zobrist Hash用の乱数テーブル（シングルトン）"""

    _instance: "ZobristTable | None" = None
    _initialized: bool = False

    def __new__(cls) -> "ZobristTable":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ZobristTable._initialized:
            return
        ZobristTable._initialized = True

        # 乱数生成器（シード固定で再現性確保）
        rng = random.Random(ZOBRIST_SEED)

        # テーブル: table[x][y][piece_id][player][is_promoted]
        # piece_id=0は空マスとして未使用（駒IDは1から）
        self._table = [
            [
                [
                    [
                        [rng.getrandbits(64) for _ in range(NUM_PROMOTED_STATES)]
                        for _ in range(NUM_PLAYERS)
                    ]
                    for _ in range(MAX_PIECE_ID + 1)
                ]
                for _ in range(BOARD_SIZE)
            ]
            for _ in range(BOARD_SIZE)
        ]

        # 手番用のハッシュ値（先手番のときにXOR）
        self._turn_hash = rng.getrandbits(64)

    def piece_hash(self, x: int, y: int, piece_id: int, player: int, is_promoted: bool = False) -> int:
        """指定位置・駒のハッシュ値を取得"""
        return self._table[x][y][piece_id][player][1 if is_promoted else 0]

    def turn_hash(self) -> int:
        """手番用のハッシュ値を取得"""
        return self._turn_hash

    def compute_full_hash(self, board: "Board", current_player: int) -> int:
        """盤面全体のハッシュ値を計算

        Args:
            board: 盤面
            current_player: 現在の手番（0=先手, 1=後手）

        Returns:
            64bit ハッシュ値
        """
        h = 0

        # 全マスをスキャン
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                cell = board.grid[x][y]
                if cell is not None:
                    piece_id, player = cell[0], cell[1]
                    is_promoted = cell[2] if len(cell) > 2 else False
                    h ^= self._table[x][y][piece_id][player][1 if is_promoted else 0]

        # 先手番のときはturn_hashをXOR
        if current_player == 0:
            h ^= self._turn_hash

        return h


# グローバルインスタンス
_zobrist_table: ZobristTable | None = None


def get_zobrist_table() -> ZobristTable:
    """Zobristテーブルを取得"""
    global _zobrist_table
    if _zobrist_table is None:
        _zobrist_table = ZobristTable()
    return _zobrist_table

"""将のテスト"""

import pytest
from backend.domain.board import Board
from backend.domain.pieces import p001_将 as shou


class TestShouMoves:
    """将の移動テスト"""

    def test_center_all_directions(self):
        """中央から8方向に移動可能"""
        board = Board()
        board.set(9, 9, shou.ID, 0)

        moves = shou.get_moves((9, 9), board, player=0)

        assert len(moves) == 8
        assert (9, 10) in moves  # 前
        assert (9, 8) in moves   # 後
        assert (10, 9) in moves  # 右
        assert (8, 9) in moves   # 左
        assert (10, 10) in moves  # 右前
        assert (8, 10) in moves   # 左前
        assert (10, 8) in moves   # 右後
        assert (8, 8) in moves    # 左後

    def test_corner_limited(self):
        """角では移動先が制限される"""
        board = Board()
        board.set(0, 0, shou.ID, 0)

        moves = shou.get_moves((0, 0), board, player=0)

        assert len(moves) == 3
        assert (1, 0) in moves
        assert (0, 1) in moves
        assert (1, 1) in moves

    def test_blocked_by_ally(self):
        """味方駒がある位置には移動不可"""
        board = Board()
        board.set(9, 9, shou.ID, 0)
        board.set(9, 10, 2, 0)  # 前に味方

        moves = shou.get_moves((9, 9), board, player=0)

        assert (9, 10) not in moves
        assert len(moves) == 7

    def test_can_capture_enemy(self):
        """敵駒がある位置には移動可能（取れる）"""
        board = Board()
        board.set(9, 9, shou.ID, 0)
        board.set(9, 10, 2, 1)  # 前に敵

        moves = shou.get_moves((9, 9), board, player=0)

        assert (9, 10) in moves
        assert len(moves) == 8


class TestShouPromotion:
    """将の成りテスト"""

    def test_cannot_promote(self):
        """将はcan_promote関数を持たない"""
        assert not hasattr(shou, 'can_promote')


class TestShouAfterMove:
    """将の移動後処理テスト"""

    def test_no_special_ability(self):
        """将はafter_move関数を持たない"""
        assert not hasattr(shou, 'after_move')

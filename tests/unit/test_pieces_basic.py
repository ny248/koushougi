"""基本的な駒のテスト"""

import pytest
from backend.domain.board import Board
from backend.domain.pieces import p014_中軍 as chugun
from backend.domain.pieces import p035_帥 as sui
from backend.domain.pieces import p004_親兵 as shinpei
from backend.domain.pieces import p019_護兵 as gohei


class TestChugun:
    """中軍のテスト"""

    def test_moves_8_directions(self):
        board = Board()
        moves = chugun.get_moves((9, 9), board, player=0)
        assert len(moves) == 8

    def test_promotes_in_enemy_zone(self):
        # player 0: y <= 5 が敵陣（上側）
        assert chugun.can_promote(None, (9, 6), (9, 5), None, 0) is True
        assert chugun.can_promote(None, (9, 6), (9, 6), None, 0) is False


class TestSui:
    """帥のテスト"""

    def test_moves_8_directions(self):
        board = Board()
        moves = sui.get_moves((9, 9), board, player=0)
        assert len(moves) == 8

    def test_cannot_promote(self):
        # 帥はすでに成り駒なので成れない
        assert not hasattr(sui, 'can_promote') or sui.can_promote(None, (9, 9), (9, 10), None, 0) is False


class TestShinpei:
    """親兵のテスト - 後ろ以外の7方向に1路"""

    def test_moves_7_directions_player0(self):
        board = Board()
        moves = shinpei.get_moves((9, 9), board, player=0)
        assert len(moves) == 7
        # player0: 前は-y方向、後ろは+y方向
        assert (9, 10) not in moves  # 後ろには行けない
        assert (9, 8) in moves  # 前には行ける

    def test_moves_7_directions_player1(self):
        board = Board()
        moves = shinpei.get_moves((9, 9), board, player=1)
        assert len(moves) == 7
        # player1: 前は+y方向、後ろは-y方向
        assert (9, 8) not in moves  # 後ろには行けない
        assert (9, 10) in moves  # 前には行ける


class TestGohei:
    """護兵のテスト - 前以外の7方向に1路"""

    def test_moves_7_directions_player0(self):
        board = Board()
        moves = gohei.get_moves((9, 9), board, player=0)
        assert len(moves) == 7
        # player0: 前は-y方向、後ろは+y方向
        assert (9, 8) not in moves  # 前には行けない
        assert (9, 10) in moves  # 後ろには行ける

    def test_moves_7_directions_player1(self):
        board = Board()
        moves = gohei.get_moves((9, 9), board, player=1)
        assert len(moves) == 7
        # player1: 前は+y方向、後ろは-y方向
        assert (9, 10) not in moves  # 前には行けない
        assert (9, 8) in moves  # 後ろには行ける

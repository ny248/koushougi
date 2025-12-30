"""piece_loader モジュールのテスト"""

import pytest
from pathlib import Path

from src.domain.piece_loader import (
    PieceDefinition,
    MoveDefinition,
    ShootDefinition,
    PromoteDefinition,
    PromoteCondition,
    RestrictDefinition,
    load_piece_definition,
    load_all_pieces,
    PieceRegistry,
)


PIECES_DIR = Path(__file__).parent.parent.parent / "src" / "domain" / "pieces"


class TestLoadPieceDefinition:
    """load_piece_definition のテスト"""

    def test_load_shou(self):
        """将（ID=1）の読み込み"""
        piece = load_piece_definition(PIECES_DIR / "001.yaml")

        assert piece.id == 1
        assert piece.name == "将"
        assert piece.reading == "しょう"

        # 移動: 8方向に1マス
        assert piece.move.steps == 1
        assert piece.move.slide is False
        assert piece.move.jump is False
        assert len(piece.move.cells) == 8
        assert (0, 1) in piece.move.cells  # 前
        assert (0, -1) in piece.move.cells  # 後
        assert (1, 0) in piece.move.cells  # 右
        assert (-1, 0) in piece.move.cells  # 左

        # 射撃なし
        assert piece.shoot is None
        # 成りなし
        assert piece.promote is None

    def test_load_rikishi(self):
        """力士（ID=5）の読み込み - 獅子系"""
        piece = load_piece_definition(PIECES_DIR / "005.yaml")

        assert piece.id == 5
        assert piece.name == "力士"

        # 移動: 2手分
        assert piece.move.steps == 2
        assert piece.move.slide is False
        assert len(piece.move.cells) == 8

    def test_load_koudou(self):
        """高道（ID=10）の読み込み - 射撃あり"""
        piece = load_piece_definition(PIECES_DIR / "010.yaml")

        assert piece.id == 10
        assert piece.name == "高道"

        # 移動: 2マス先にジャンプ
        assert piece.move.steps == 1
        assert piece.move.jump is True
        assert (0, 2) in piece.move.cells
        assert (2, 2) in piece.move.cells

        # 射撃: 1路、1回、貫通可
        assert piece.shoot is not None
        assert piece.shoot.range == 1
        assert piece.shoot.count == 1
        assert piece.shoot.penetrate is True

        # 制限: 高道と神僧のみ取れる
        assert piece.restrict is not None
        assert 10 in piece.restrict.only_capture
        assert 11 in piece.restrict.only_capture

        # 成り: 五里霧へ
        assert piece.promote is not None
        assert piece.promote.to == 44


class TestLoadAllPieces:
    """load_all_pieces のテスト"""

    def test_load_all(self):
        """全駒定義の読み込み"""
        pieces = load_all_pieces(PIECES_DIR)

        # 少なくとも作成済みの駒が読み込まれている
        assert len(pieces) >= 1
        assert 1 in pieces  # 将
        assert pieces[1].name == "将"

    def test_pieces_indexed_by_id(self):
        """駒IDでインデックスされている"""
        pieces = load_all_pieces(PIECES_DIR)

        for piece_id, piece in pieces.items():
            assert piece.id == piece_id


class TestPieceRegistry:
    """PieceRegistry のテスト"""

    def setup_method(self):
        """各テスト前にレジストリをリセット"""
        PieceRegistry.reset()

    def test_singleton(self):
        """シングルトンパターン"""
        reg1 = PieceRegistry()
        reg2 = PieceRegistry()
        assert reg1 is reg2

    def test_get_by_id(self):
        """IDで駒定義を取得"""
        registry = PieceRegistry()
        registry.load(PIECES_DIR)

        piece = registry.get(1)
        assert piece.name == "将"

    def test_get_by_name(self):
        """名前で駒定義を取得"""
        registry = PieceRegistry()
        registry.load(PIECES_DIR)

        piece = registry.get_by_name("将")
        assert piece.id == 1

    def test_get_unknown_id_raises(self):
        """存在しないIDでKeyError"""
        registry = PieceRegistry()
        registry.load(PIECES_DIR)

        with pytest.raises(KeyError):
            registry.get(999)

    def test_get_unknown_name_raises(self):
        """存在しない名前でKeyError"""
        registry = PieceRegistry()
        registry.load(PIECES_DIR)

        with pytest.raises(KeyError):
            registry.get_by_name("存在しない駒")

    def test_lazy_load(self):
        """get時に自動で読み込む"""
        registry = PieceRegistry()
        # load()を呼ばずにget
        piece = registry.get(1)
        assert piece.name == "将"


class TestDataclassImmutability:
    """データクラスの不変性テスト"""

    def test_piece_definition_frozen(self):
        """PieceDefinitionは変更不可"""
        piece = load_piece_definition(PIECES_DIR / "001.yaml")

        with pytest.raises(AttributeError):
            piece.name = "変更"

    def test_move_definition_frozen(self):
        """MoveDefinitionは変更不可"""
        piece = load_piece_definition(PIECES_DIR / "001.yaml")

        with pytest.raises(AttributeError):
            piece.move.steps = 99

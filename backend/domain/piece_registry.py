"""駒定義Pythonモジュールの読み込みユーティリティ"""

import importlib
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pieces.multi_step_config import MultiStepConfig


class PieceModule:
    """駒モジュールのラッパー"""

    def __init__(self, module: Any):
        self._module = module
        self.id: int = module.ID
        self.name: str = module.NAME
        self.reading: str = module.READING
        self.promotes_to: Optional[int] = getattr(module, "PROMOTES_TO", None)

    def get_moves(self, pos: tuple[int, int], board: Any, player: int) -> list[tuple[int, int]]:
        """移動可能な位置を取得"""
        return self._module.get_moves(pos, board, player)

    def can_promote(self, game_state: Any, from_pos: tuple[int, int],
                    to_pos: tuple[int, int], captured_piece: Optional[int],
                    player: int) -> bool:
        """成れるかどうか"""
        if not hasattr(self._module, "can_promote"):
            return False
        return self._module.can_promote(game_state, from_pos, to_pos, captured_piece, player)

    def after_move(self, game_state: Any, from_pos: tuple[int, int],
                   to_pos: tuple[int, int], player: int) -> Optional[dict]:
        """移動後の特殊効果（射撃、周囲破壊など）"""
        if not hasattr(self._module, "after_move"):
            return None
        return self._module.after_move(game_state, from_pos, to_pos, player)

    def get_path_kills(self, pos: tuple[int, int], board: Any,
                       player: int, to_pos: tuple[int, int]) -> list[tuple[int, int]]:
        """経路上で取る駒（招揺、霹靂用）"""
        if not hasattr(self._module, "get_path_kills"):
            return []
        return self._module.get_path_kills(pos, board, player, to_pos)

    def check_revert(self, game_state: Any, pos: tuple[int, int],
                     player: int) -> Optional[int]:
        """成り戻りチェック（高道が死んだ時など）"""
        if not hasattr(self._module, "check_revert"):
            return None
        return self._module.check_revert(game_state, pos, player)

    def get_capture_restriction(self) -> list[int]:
        """取れない駒のリスト"""
        if not hasattr(self._module, "get_capture_restriction"):
            return []
        return self._module.get_capture_restriction()

    def get_capture_filter(self) -> Optional[list[int]]:
        """取れる駒のリスト（Noneなら全部取れる）"""
        if not hasattr(self._module, "get_capture_filter"):
            return None
        return self._module.get_capture_filter()

    def get_capture_immunity(self) -> list[int]:
        """この駒を取れない駒のリスト"""
        if not hasattr(self._module, "get_capture_immunity"):
            return []
        return self._module.get_capture_immunity()

    def is_multi_step(self) -> bool:
        """マルチステップ移動の駒か"""
        return hasattr(self._module, "get_multi_step_config")

    def get_multi_step_config(self) -> Optional["MultiStepConfig"]:
        """マルチステップ設定を取得"""
        if not hasattr(self._module, "get_multi_step_config"):
            return None
        return self._module.get_multi_step_config()

    def get_next_step_options(self, current_pos: tuple[int, int], board: Any,
                               player: int, step_index: int,
                               first_direction: Optional[tuple[int, int]]) -> list[tuple[int, int]]:
        """次ステップの移動先候補を取得"""
        if not hasattr(self._module, "get_next_step_options"):
            return []
        return self._module.get_next_step_options(
            current_pos, board, player, step_index, first_direction
        )


class PieceRegistry:
    """駒定義のレジストリ（シングルトン）"""

    _instance: Optional["PieceRegistry"] = None
    _pieces: dict[int, PieceModule]

    def __new__(cls) -> "PieceRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pieces = {}
        return cls._instance

    def load(self) -> None:
        """全駒定義を読み込む"""
        pieces_dir = Path(__file__).parent / "pieces"

        for py_file in sorted(pieces_dir.glob("p*.py")):
            if py_file.name == "__init__.py":
                continue
            module_name = f"backend.domain.pieces.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "ID"):
                    piece = PieceModule(module)
                    self._pieces[piece.id] = piece
            except Exception as e:
                print(f"Warning: Failed to load {py_file.name}: {e}")

    def get(self, piece_id: int) -> PieceModule:
        """駒定義を取得"""
        if not self._pieces:
            self.load()
        if piece_id not in self._pieces:
            raise KeyError(f"駒ID {piece_id} が見つかりません")
        return self._pieces[piece_id]

    def get_by_name(self, name: str) -> PieceModule:
        """名前で駒定義を取得"""
        if not self._pieces:
            self.load()
        for piece in self._pieces.values():
            if piece.name == name:
                return piece
        raise KeyError(f"駒 '{name}' が見つかりません")

    def all(self) -> dict[int, PieceModule]:
        """全駒定義を取得"""
        if not self._pieces:
            self.load()
        return self._pieces.copy()

    @classmethod
    def reset(cls) -> None:
        """レジストリをリセット（テスト用）"""
        cls._instance = None


# グローバルインスタンス
registry = PieceRegistry()


def get_piece(piece_id: int) -> PieceModule:
    """駒定義を取得するショートカット"""
    return registry.get(piece_id)


def get_piece_by_name(name: str) -> PieceModule:
    """名前で駒定義を取得するショートカット"""
    return registry.get_by_name(name)

"""駒定義YAMLファイルの読み込みユーティリティ"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass(frozen=True)
class MoveDefinition:
    """移動定義"""
    steps: int = 1
    cells: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    slide: bool = False
    jump: bool = False
    path: dict[int, tuple[tuple[int, int], ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ShootDefinition:
    """射撃定義"""
    range: int = 0
    count: int = 1
    penetrate: bool = False
    immune: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PromoteCondition:
    """成り条件"""
    zone: bool = False
    capture: tuple[int, ...] = field(default_factory=tuple)
    trigger: Optional[int] = None


@dataclass(frozen=True)
class PromoteDefinition:
    """成り定義"""
    to: int = 0
    on: tuple[PromoteCondition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RestrictDefinition:
    """制限定義"""
    no_capture: tuple[int, ...] = field(default_factory=tuple)
    only_capture: tuple[int, ...] = field(default_factory=tuple)
    no_capture_except: tuple[int, ...] = field(default_factory=tuple)
    no_captured_by: tuple[int, ...] = field(default_factory=tuple)
    no_shot_by: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PieceDefinition:
    """駒定義"""
    id: int
    name: str
    reading: str
    move: MoveDefinition
    shoot: Optional[ShootDefinition] = None
    promote: Optional[PromoteDefinition] = None
    restrict: Optional[RestrictDefinition] = None


def _parse_move(data: dict) -> MoveDefinition:
    """移動定義をパース"""
    cells = tuple(tuple(c) for c in data.get("cells", []))
    path_raw = data.get("path", {})
    path = {int(k): tuple(tuple(p) for p in v) for k, v in path_raw.items()}
    return MoveDefinition(
        steps=data.get("steps", 1),
        cells=cells,
        slide=data.get("slide", False),
        jump=data.get("jump", False),
        path=path,
    )


def _parse_shoot(data: Optional[dict]) -> Optional[ShootDefinition]:
    """射撃定義をパース"""
    if data is None:
        return None
    return ShootDefinition(
        range=data.get("range", 0),
        count=data.get("count", 1),
        penetrate=data.get("penetrate", False),
        immune=tuple(data.get("immune", [])),
    )


def _parse_promote(data: Optional[dict]) -> Optional[PromoteDefinition]:
    """成り定義をパース"""
    if data is None:
        return None
    conditions = []
    for cond in data.get("on", []):
        conditions.append(PromoteCondition(
            zone=cond.get("zone", False),
            capture=tuple(cond.get("capture", [])),
            trigger=cond.get("trigger"),
        ))
    return PromoteDefinition(
        to=data.get("to", 0),
        on=tuple(conditions),
    )


def _parse_restrict(data: Optional[dict]) -> Optional[RestrictDefinition]:
    """制限定義をパース"""
    if data is None:
        return None
    return RestrictDefinition(
        no_capture=tuple(data.get("no_capture", [])),
        only_capture=tuple(data.get("only_capture", [])),
        no_capture_except=tuple(data.get("no_capture_except", [])),
        no_captured_by=tuple(data.get("no_captured_by", [])),
        no_shot_by=tuple(data.get("no_shot_by", [])),
    )


def load_piece_definition(file_path: Path) -> PieceDefinition:
    """YAMLファイルから駒定義を読み込む"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return PieceDefinition(
        id=data["id"],
        name=data["name"],
        reading=data["reading"],
        move=_parse_move(data.get("move", {})),
        shoot=_parse_shoot(data.get("shoot")),
        promote=_parse_promote(data.get("promote")),
        restrict=_parse_restrict(data.get("restrict")),
    )


def load_all_pieces(pieces_dir: Optional[Path] = None) -> dict[int, PieceDefinition]:
    """全駒定義を読み込む

    Args:
        pieces_dir: 駒定義ディレクトリ。Noneの場合はデフォルトパスを使用

    Returns:
        駒ID -> PieceDefinition のマッピング
    """
    if pieces_dir is None:
        pieces_dir = Path(__file__).parent / "pieces"

    pieces = {}
    for yaml_file in sorted(pieces_dir.glob("*.yaml")):
        piece = load_piece_definition(yaml_file)
        pieces[piece.id] = piece

    return pieces


class PieceRegistry:
    """駒定義のレジストリ（シングルトン的に使用）"""

    _instance: Optional["PieceRegistry"] = None
    _pieces: dict[int, PieceDefinition]

    def __new__(cls) -> "PieceRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pieces = {}
        return cls._instance

    def load(self, pieces_dir: Optional[Path] = None) -> None:
        """駒定義を読み込む"""
        self._pieces = load_all_pieces(pieces_dir)

    def get(self, piece_id: int) -> PieceDefinition:
        """駒定義を取得"""
        if not self._pieces:
            self.load()
        if piece_id not in self._pieces:
            raise KeyError(f"駒ID {piece_id} が見つかりません")
        return self._pieces[piece_id]

    def get_by_name(self, name: str) -> PieceDefinition:
        """名前で駒定義を取得"""
        if not self._pieces:
            self.load()
        for piece in self._pieces.values():
            if piece.name == name:
                return piece
        raise KeyError(f"駒 '{name}' が見つかりません")

    def all(self) -> dict[int, PieceDefinition]:
        """全駒定義を取得"""
        if not self._pieces:
            self.load()
        return self._pieces.copy()

    @classmethod
    def reset(cls) -> None:
        """レジストリをリセット（テスト用）"""
        cls._instance = None

"""棋譜（Kifu）- ゲームの手順を記録・再生するためのクラス"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Move:
    """1手の記録（Undoに必要な全情報を含む）"""

    # 基本情報
    player: int                          # 手番 (0=先手, 1=後手)
    move_type: str                       # "move" or "shoot"

    # 移動の場合
    from_pos: Optional[tuple[int, int]] = None  # 移動元
    to_pos: Optional[tuple[int, int]] = None    # 移動先
    piece_id: Optional[int] = None              # 動かした駒ID
    promoted: bool = False                       # この手で成ったか

    # 取った駒（Undo用）
    captured_piece: Optional[int] = None        # 取った駒ID
    captured_pos: Optional[tuple[int, int]] = None  # 取った位置（射撃の場合）
    captured_was_promoted: bool = False         # 取った駒が成り状態だったか

    # 経路上で取った駒（霹靂・招揺用）
    path_kills: list[tuple[tuple[int, int], int, bool]] = field(default_factory=list)
    # [(位置, 駒ID, is_promoted), ...]

    # 成りで消えた駒（毒火の道連れ用）
    collateral_kills: list[tuple[tuple[int, int], int, bool]] = field(default_factory=list)
    # [(位置, 駒ID, is_promoted), ...]

    # 成りの連鎖（記室→軍師で前衝→前軍など）
    chain_promotions: list[tuple[tuple[int, int], int, int]] = field(default_factory=list)
    # [(位置, 元駒ID, 新駒ID), ...]

    # 退化（高道死亡時の霹靂→鼓、招揺→旗）
    demotions: list[tuple[tuple[int, int], int, int]] = field(default_factory=list)
    # [(位置, 元駒ID, 新駒ID), ...]

    def to_dict(self) -> dict:
        """辞書に変換（JSON保存用）"""
        return {
            "player": self.player,
            "move_type": self.move_type,
            "from": list(self.from_pos) if self.from_pos else None,
            "to": list(self.to_pos) if self.to_pos else None,
            "piece_id": self.piece_id,
            "promoted": self.promoted,
            "captured_piece": self.captured_piece,
            "captured_pos": list(self.captured_pos) if self.captured_pos else None,
            "captured_was_promoted": self.captured_was_promoted,
            "path_kills": [[list(pos), pid, is_prom] for pos, pid, is_prom in self.path_kills],
            "collateral_kills": [[list(pos), pid, is_prom] for pos, pid, is_prom in self.collateral_kills],
            "chain_promotions": [[list(pos), old, new] for pos, old, new in self.chain_promotions],
            "demotions": [[list(pos), old, new] for pos, old, new in self.demotions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Move":
        """辞書から復元"""
        return cls(
            player=data["player"],
            move_type=data["move_type"],
            from_pos=tuple(data["from"]) if data.get("from") else None,
            to_pos=tuple(data["to"]) if data.get("to") else None,
            piece_id=data.get("piece_id"),
            promoted=data.get("promoted", False),
            captured_piece=data.get("captured_piece"),
            captured_pos=tuple(data["captured_pos"]) if data.get("captured_pos") else None,
            captured_was_promoted=data.get("captured_was_promoted", False),
            path_kills=[(tuple(item[0]), item[1], item[2]) for item in data.get("path_kills", [])],
            collateral_kills=[(tuple(item[0]), item[1], item[2]) for item in data.get("collateral_kills", [])],
            chain_promotions=[(tuple(pos), old, new) for pos, old, new in data.get("chain_promotions", [])],
            demotions=[(tuple(pos), old, new) for pos, old, new in data.get("demotions", [])],
        )


@dataclass
class Kifu:
    """棋譜 - ゲーム全体の記録"""

    moves: list[Move] = field(default_factory=list)
    winner: Optional[int] = None
    win_reason: Optional[str] = None  # "capture_chugun", "chugun_entered", "resign", etc.

    def append(self, move: Move) -> None:
        """手を追加"""
        self.moves.append(move)

    def pop(self) -> Optional[Move]:
        """最後の手を取り出す（Undo用）"""
        if self.moves:
            return self.moves.pop()
        return None

    def __len__(self) -> int:
        return len(self.moves)

    def __getitem__(self, idx: int) -> Move:
        return self.moves[idx]

    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "moves": [m.to_dict() for m in self.moves],
            "winner": self.winner,
            "win_reason": self.win_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Kifu":
        """辞書から復元"""
        return cls(
            moves=[Move.from_dict(m) for m in data.get("moves", [])],
            winner=data.get("winner"),
            win_reason=data.get("win_reason"),
        )

    def save(self, filepath: str) -> None:
        """ファイルに保存"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "Kifu":
        """ファイルから読み込み"""
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

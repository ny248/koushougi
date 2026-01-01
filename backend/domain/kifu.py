"""棋譜（Kifu）- ゲームの手順を記録・再生するためのクラス"""

from dataclasses import dataclass, field
from typing import Optional, TextIO
from enum import Enum
import json


class KifuMode(Enum):
    """棋譜保存モード"""
    NONE = "none"           # 保存しない
    STREAMING = "streaming" # 1手ごとに追記（JSON Lines形式）
    BATCH = "batch"         # 終了時に一括保存


class KifuWriter:
    """ストリーミング棋譜書き込み"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._file: Optional[TextIO] = None

    def start(self) -> None:
        """ファイルを開いてヘッダを書き込む"""
        self._file = open(self.filepath, "w", encoding="utf-8")
        header = {"type": "header", "version": 1}
        self._file.write(json.dumps(header, ensure_ascii=False) + "\n")
        self._file.flush()

    def write_move(self, move: "Move") -> None:
        """1手を追記"""
        if self._file is None:
            return
        entry = {"type": "move", "data": move.to_dict()}
        self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._file.flush()

    def finish(self, winner: Optional[int], reason: Optional[str] = None) -> None:
        """ゲーム終了時に結果を書いて閉じる"""
        if self._file is None:
            return
        result = {"type": "result", "winner": winner, "reason": reason}
        self._file.write(json.dumps(result, ensure_ascii=False) + "\n")
        self._file.close()
        self._file = None

    def close(self) -> None:
        """ファイルを閉じる（途中終了時用）"""
        if self._file:
            self._file.close()
            self._file = None


@dataclass
class Move:
    """1手の記録（Undoに必要な全情報を含む）

    move_type:
        - "move": 通常の駒移動（マルチステップの最初の1歩を含む）
        - "step": マルチステップ移動の2歩目以降
        - "stop": マルチステップ移動の早期停止
        - "shoot": 射撃
        - "skip_shoot": 射撃スキップ
    """

    # 基本情報
    player: int                          # 手番 (0=先手, 1=後手)
    move_type: str                       # "move", "step", "stop", "shoot", "skip_shoot"

    # 移動の場合
    from_pos: Optional[tuple[int, int]] = None  # 移動元
    to_pos: Optional[tuple[int, int]] = None    # 移動先
    piece_id: Optional[int] = None              # 動かした駒ID
    promoted: bool = False                       # この手で成ったか

    # 取った駒（Undo用）
    captured_piece: Optional[int] = None        # 取った駒ID
    captured_pos: Optional[tuple[int, int]] = None  # 取った位置（射撃の場合）
    captured_was_promoted: bool = False         # 取った駒が成り状態だったか

    # 成りで消えた駒（毒火の道連れ用）
    collateral_kills: list[tuple[tuple[int, int], int, bool]] = field(default_factory=list)
    # [(位置, 駒ID, is_promoted), ...]

    # 成りの連鎖（記室→軍師で前衝→前軍など）
    chain_promotions: list[tuple[tuple[int, int], int, int]] = field(default_factory=list)
    # [(位置, 元駒ID, 新駒ID), ...]

    # 退化（高道死亡時の霹靂→鼓、招揺→旗）
    demotions: list[tuple[tuple[int, int], int, int]] = field(default_factory=list)
    # [(位置, 元駒ID, 新駒ID), ...]

    # マルチステップ用（stopのundo用）
    multi_step_state: Optional[dict] = None  # 停止前のマルチステップ状態

    # 射撃用（skip_shootのundo用）
    shoot_state: Optional[dict] = None  # スキップ前の射撃状態

    def to_dict(self) -> dict:
        """辞書に変換（JSON保存用）"""
        result = {
            "player": self.player,
            "move_type": self.move_type,
            "from": list(self.from_pos) if self.from_pos else None,
            "to": list(self.to_pos) if self.to_pos else None,
            "piece_id": self.piece_id,
            "promoted": self.promoted,
            "captured_piece": self.captured_piece,
            "captured_pos": list(self.captured_pos) if self.captured_pos else None,
            "captured_was_promoted": self.captured_was_promoted,
            "collateral_kills": [[list(pos), pid, is_prom] for pos, pid, is_prom in self.collateral_kills],
            "chain_promotions": [[list(pos), old, new] for pos, old, new in self.chain_promotions],
            "demotions": [[list(pos), old, new] for pos, old, new in self.demotions],
        }
        # オプショナルフィールド（存在する場合のみ出力）
        if self.multi_step_state:
            result["multi_step_state"] = self.multi_step_state
        if self.shoot_state:
            result["shoot_state"] = self.shoot_state
        return result

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
            collateral_kills=[(tuple(item[0]), item[1], item[2]) for item in data.get("collateral_kills", [])],
            chain_promotions=[(tuple(pos), old, new) for pos, old, new in data.get("chain_promotions", [])],
            demotions=[(tuple(pos), old, new) for pos, old, new in data.get("demotions", [])],
            multi_step_state=data.get("multi_step_state"),
            shoot_state=data.get("shoot_state"),
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

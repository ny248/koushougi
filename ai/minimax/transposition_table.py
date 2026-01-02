"""Transposition Table for Minimax search

Zobrist Hashをキーとして、探索済みの局面の評価値をキャッシュする。
同一局面の再計算を防ぎ、探索を高速化する。

エントリタイプ:
- EXACT: 正確な評価値（Alpha-Beta窓内で確定）
- LOWER_BOUND: 下限値（Beta cutで探索打ち切り）
- UPPER_BOUND: 上限値（Alpha cutで探索打ち切り）
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from backend.domain.action import Action


class TTEntryType(IntEnum):
    """Transposition Tableエントリのタイプ"""
    EXACT = 0       # 正確な値
    LOWER_BOUND = 1 # 下限値（Beta cut）
    UPPER_BOUND = 2 # 上限値（Alpha cut）


@dataclass(slots=True)
class TTEntry:
    """Transposition Tableのエントリ"""
    hash_key: int           # Zobrist Hash（衝突検出用）
    depth: int              # 探索深さ
    value: float            # 評価値
    entry_type: TTEntryType # エントリタイプ
    best_action: Optional[Action] = None  # 最善手（ムーブオーダリング用）


class TranspositionTable:
    """Transposition Table

    固定サイズのハッシュテーブル。衝突時は深さが深い方を優先して上書き。
    """

    def __init__(self, size: int = 1 << 20):
        """
        Args:
            size: テーブルサイズ（デフォルト: 約100万エントリ）
        """
        self.size = size
        self.table: list[Optional[TTEntry]] = [None] * size
        self.hits = 0
        self.misses = 0
        self.overwrites = 0

    def _index(self, hash_key: int) -> int:
        """ハッシュキーからインデックスを計算"""
        return hash_key % self.size

    def probe(self, hash_key: int, depth: int, alpha: float, beta: float
              ) -> tuple[Optional[float], Optional[Action]]:
        """テーブルを参照

        Args:
            hash_key: Zobrist Hash
            depth: 要求する最小探索深さ
            alpha: 現在のAlpha値
            beta: 現在のBeta値

        Returns:
            (value, best_action) のタプル。
            valueがNoneでなければ、その値を使って探索をスキップできる。
            best_actionは常に返す（ムーブオーダリング用）。
        """
        index = self._index(hash_key)
        entry = self.table[index]

        if entry is None or entry.hash_key != hash_key:
            self.misses += 1
            return None, None

        self.hits += 1

        # 深さが足りない場合は値は使えないが、best_actionは使える
        if entry.depth < depth:
            return None, entry.best_action

        # エントリタイプに応じて値を返す
        if entry.entry_type == TTEntryType.EXACT:
            return entry.value, entry.best_action
        elif entry.entry_type == TTEntryType.LOWER_BOUND:
            if entry.value >= beta:
                return entry.value, entry.best_action
        elif entry.entry_type == TTEntryType.UPPER_BOUND:
            if entry.value <= alpha:
                return entry.value, entry.best_action

        return None, entry.best_action

    def store(self, hash_key: int, depth: int, value: float,
              entry_type: TTEntryType, best_action: Optional[Action] = None) -> None:
        """テーブルに格納

        Args:
            hash_key: Zobrist Hash
            depth: 探索深さ
            value: 評価値
            entry_type: エントリタイプ
            best_action: 最善手
        """
        index = self._index(hash_key)
        existing = self.table[index]

        # 置換戦略: 深さが同じか深い場合のみ上書き
        if existing is not None and existing.hash_key == hash_key:
            if existing.depth > depth:
                return  # 既存エントリの方が深いので保持
            self.overwrites += 1

        self.table[index] = TTEntry(
            hash_key=hash_key,
            depth=depth,
            value=value,
            entry_type=entry_type,
            best_action=best_action,
        )

    def clear(self) -> None:
        """テーブルをクリア"""
        self.table = [None] * self.size
        self.hits = 0
        self.misses = 0
        self.overwrites = 0

    def get_stats(self) -> dict:
        """統計情報を取得"""
        total = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "overwrites": self.overwrites,
        }

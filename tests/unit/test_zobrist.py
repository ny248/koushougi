"""Zobrist Hash のテスト"""

import pytest
from backend.domain.game_state import GameState, create_initial_state
from backend.domain.zobrist import get_zobrist_table, ZobristTable
from backend.rules.game_engine import GameEngine
from backend.domain.kifu import KifuMode


class TestZobristTable:
    """Zobrist テーブルの基本テスト"""

    def test_singleton(self):
        """シングルトンであること"""
        t1 = get_zobrist_table()
        t2 = get_zobrist_table()
        assert t1 is t2

    def test_piece_hash_consistency(self):
        """同じ入力には同じハッシュ値"""
        table = get_zobrist_table()
        h1 = table.piece_hash(5, 10, 1, 0, False)
        h2 = table.piece_hash(5, 10, 1, 0, False)
        assert h1 == h2

    def test_piece_hash_differs_by_position(self):
        """位置が違えばハッシュ値も違う"""
        table = get_zobrist_table()
        h1 = table.piece_hash(5, 10, 1, 0, False)
        h2 = table.piece_hash(6, 10, 1, 0, False)
        assert h1 != h2

    def test_piece_hash_differs_by_piece(self):
        """駒が違えばハッシュ値も違う"""
        table = get_zobrist_table()
        h1 = table.piece_hash(5, 10, 1, 0, False)
        h2 = table.piece_hash(5, 10, 2, 0, False)
        assert h1 != h2

    def test_piece_hash_differs_by_player(self):
        """プレイヤーが違えばハッシュ値も違う"""
        table = get_zobrist_table()
        h1 = table.piece_hash(5, 10, 1, 0, False)
        h2 = table.piece_hash(5, 10, 1, 1, False)
        assert h1 != h2

    def test_piece_hash_differs_by_promoted(self):
        """成り状態が違えばハッシュ値も違う"""
        table = get_zobrist_table()
        h1 = table.piece_hash(5, 10, 1, 0, False)
        h2 = table.piece_hash(5, 10, 1, 0, True)
        assert h1 != h2


class TestGameStateZobrist:
    """GameState の Zobrist Hash テスト"""

    def test_initial_state_has_hash(self):
        """初期状態でハッシュが計算されている"""
        state = create_initial_state()
        assert state.zobrist_hash != 0

    def test_same_state_same_hash(self):
        """同じ状態なら同じハッシュ"""
        state1 = create_initial_state()
        state2 = create_initial_state()
        assert state1.zobrist_hash == state2.zobrist_hash

    def test_copy_preserves_hash(self):
        """コピーでハッシュが保持される"""
        state1 = create_initial_state()
        state2 = state1.copy()
        assert state1.zobrist_hash == state2.zobrist_hash

    def test_set_piece_updates_hash(self):
        """駒を置くとハッシュが変わる"""
        state = create_initial_state()
        original_hash = state.zobrist_hash

        # 空いているマスに駒を置く
        state.set_piece(9, 9, 1, 0)  # 将を中央に置く

        assert state.zobrist_hash != original_hash

    def test_remove_piece_updates_hash(self):
        """駒を取り除くとハッシュが変わる"""
        state = create_initial_state()
        original_hash = state.zobrist_hash

        # 駒を除去
        state.remove_piece(9, 18)  # 将を除去

        assert state.zobrist_hash != original_hash

    def test_set_remove_restores_hash(self):
        """置いて除去すると元のハッシュに戻る（XOR性質）"""
        state = create_initial_state()
        original_hash = state.zobrist_hash

        # 空きマスに駒を置いて除去
        state.set_piece(9, 9, 1, 0)
        state.remove_piece(9, 9)

        assert state.zobrist_hash == original_hash

    def test_switch_player_updates_hash(self):
        """手番交代でハッシュが変わる"""
        state = create_initial_state()
        original_hash = state.zobrist_hash

        state.switch_player()

        assert state.zobrist_hash != original_hash

    def test_switch_player_twice_restores_hash(self):
        """手番交代2回で元のハッシュに戻る（XOR性質）"""
        state = create_initial_state()
        original_hash = state.zobrist_hash

        state.switch_player()
        state.switch_player()

        assert state.zobrist_hash == original_hash


class TestGameEngineZobrist:
    """GameEngine での Zobrist Hash 更新テスト"""

    def test_move_and_undo_restores_hash(self):
        """移動→undo でハッシュが復元される"""
        state = create_initial_state()
        engine = GameEngine(state, kifu_mode=KifuMode.NONE)
        original_hash = state.zobrist_hash

        # 先鋒を動かす (9, 12) -> (9, 11)
        engine.select_piece((9, 12))
        engine.select_destination((9, 11))

        # ハッシュが変わっている
        assert state.zobrist_hash != original_hash

        # undo で戻す
        engine.undo()  # move
        engine.undo()  # select

        # ハッシュが復元されている
        assert state.zobrist_hash == original_hash

    def test_incremental_equals_full_compute(self):
        """差分更新と全体計算が一致する"""
        state = create_initial_state()
        engine = GameEngine(state, kifu_mode=KifuMode.NONE)

        # いくつか手を進める
        engine.select_piece((9, 12))
        engine.select_destination((9, 11))

        # 差分更新されたハッシュ
        incremental_hash = state.zobrist_hash

        # 全体を再計算
        full_hash = state.compute_zobrist_hash()

        assert incremental_hash == full_hash

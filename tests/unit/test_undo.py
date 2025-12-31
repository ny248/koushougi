"""undo機能のテスト"""

import pytest
from backend.rules.game_engine import GameEngine
from backend.domain.game_state import create_initial_state


class TestUndo:
    """undo機能のテスト"""

    def test_push_pop_state(self):
        """push/popで状態が復元される"""
        engine = GameEngine()

        # 初期状態を記録
        initial_player = engine.current_player
        initial_move_count = engine.state.move_count

        # 状態を保存
        engine.push_state()

        # 手を指す（先鋒を前進）
        result = engine.move((9, 12), (9, 11))
        assert result.success

        # 手番と手数が変わっている
        assert engine.current_player != initial_player
        assert engine.state.move_count != initial_move_count

        # undoで復元
        assert engine.pop_state() is True

        # 元に戻っている
        assert engine.current_player == initial_player
        assert engine.state.move_count == initial_move_count
        # 駒も元の位置
        assert engine.state.board.get(9, 12) is not None
        assert engine.state.board.get(9, 11) is None

    def test_multiple_push_pop(self):
        """複数回のpush/popが正常に動作する"""
        engine = GameEngine()

        # 3手分保存して戻す
        positions = []

        for i in range(3):
            engine.push_state()
            positions.append(engine.current_player)

            # 適当な手を指す
            moves = []
            for x in range(19):
                for y in range(19):
                    piece = engine.state.board.get(x, y)
                    if piece and piece[1] == engine.current_player:
                        legal = engine.get_legal_moves((x, y))
                        if legal:
                            moves.append(((x, y), legal[0]))

            if moves:
                from_pos, to_pos = moves[0]
                engine.move(from_pos, to_pos)

        # 3回popして戻る
        for i in range(2, -1, -1):
            assert engine.pop_state() is True
            assert engine.current_player == positions[i]

    def test_pop_empty_stack(self):
        """空のスタックからpopするとFalseを返す"""
        engine = GameEngine()
        assert engine.pop_state() is False

    def test_clear_stack(self):
        """clear_stackでスタックが空になる"""
        engine = GameEngine()

        engine.push_state()
        engine.push_state()
        engine.push_state()

        engine.clear_stack()

        assert engine.pop_state() is False

    def test_captured_piece_restored(self):
        """駒を取った後にundoすると取った駒も復元される"""
        engine = GameEngine()

        # 先手の先鋒を前進させる
        engine.move((9, 12), (9, 11))
        engine.move((9, 6), (9, 7))  # 後手も前進
        engine.move((9, 11), (9, 10))
        engine.move((9, 7), (9, 8))
        engine.move((9, 10), (9, 9))
        engine.move((9, 8), (9, 9))  # 後手が先手の先鋒を取る

        # この時点で後手が駒を取っている
        # 後手の取った駒を確認
        captured_before = engine.state.captured.get(1).copy()

        # 次の手の前に保存
        engine.push_state()

        # 先手の何かの手を指す
        for x in range(19):
            for y in range(19):
                piece = engine.state.board.get(x, y)
                if piece and piece[1] == 0:
                    legal = engine.get_legal_moves((x, y))
                    if legal:
                        engine.move((x, y), legal[0])
                        break
            else:
                continue
            break

        # undo
        engine.pop_state()

        # 取った駒リストが変わっていないことを確認
        assert engine.state.captured.get(1) == captured_before


class TestMinimaxWithUndo:
    """MinimaxPlayerがundo機能を使って正常に動作するかテスト"""

    def test_minimax_does_not_corrupt_state(self):
        """Minimaxの探索後に盤面が変わっていないこと"""
        from ai.minimax import MinimaxPlayer

        engine = GameEngine()
        ai = MinimaxPlayer(depth=2, max_moves=10)

        # 初期状態を記録
        initial_grid = [row[:] for row in engine.state.board.grid]
        initial_player = engine.current_player

        # AIに手を選ばせる（探索）
        move = ai.choose_move(engine)

        # 探索後も盤面が変わっていないこと
        assert engine.state.board.grid == initial_grid
        assert engine.current_player == initial_player

        # 手は選べていること
        assert move is not None

    def test_minimax_returns_valid_move(self):
        """Minimaxが合法手を返すこと"""
        from ai.minimax import MinimaxPlayer

        engine = GameEngine()
        ai = MinimaxPlayer(depth=2, max_moves=10)

        move = ai.choose_move(engine)

        assert move is not None
        assert "from" in move
        assert "to" in move

        # 実際に合法手かチェック
        legal_moves = engine.get_legal_moves(move["from"])
        assert move["to"] in legal_moves

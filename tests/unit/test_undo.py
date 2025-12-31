"""undo機能のテスト"""

import pytest
from backend.rules.game_engine import GameEngine
from backend.domain.game_state import create_initial_state


class TestUndo:
    """undo機能のテスト"""

    def test_undo_simple_move(self):
        """undoで状態が復元される"""
        engine = GameEngine()

        # 初期状態を記録
        initial_player = engine.current_player
        initial_move_count = engine.state.move_count

        # 手を指す（先鋒を前進）
        result = engine.move((9, 12), (9, 11))
        assert result.success

        # 手番と手数が変わっている
        assert engine.current_player != initial_player
        assert engine.state.move_count != initial_move_count

        # undoで復元
        assert engine.undo() is True

        # 元に戻っている
        assert engine.current_player == initial_player
        assert engine.state.move_count == initial_move_count
        # 駒も元の位置
        assert engine.state.board.get(9, 12) is not None
        assert engine.state.board.get(9, 11) is None

    def test_multiple_undo(self):
        """複数回のundoが正常に動作する"""
        engine = GameEngine()

        # 3手指す
        moves_played = []
        for i in range(3):
            # 適当な手を指す
            for x in range(19):
                for y in range(19):
                    piece = engine.state.board.get(x, y)
                    if piece and piece[1] == engine.current_player:
                        legal = engine.get_legal_moves((x, y))
                        if legal:
                            from_pos = (x, y)
                            to_pos = legal[0]
                            moves_played.append((from_pos, to_pos, engine.current_player))
                            engine.move(from_pos, to_pos)
                            break
                else:
                    continue
                break

        # 3回undoして戻る
        for i in range(2, -1, -1):
            assert engine.undo() is True
            assert engine.current_player == moves_played[i][2]

    def test_undo_empty_kifu(self):
        """空の棋譜からundoするとFalseを返す"""
        engine = GameEngine()
        assert engine.undo() is False

    def test_captured_piece_restored(self):
        """駒を取った後にundoすると盤面が復元される"""
        engine = GameEngine()

        # 先手の先鋒を前進させる
        engine.move((9, 12), (9, 11))
        engine.move((9, 6), (9, 7))  # 後手も前進
        engine.move((9, 11), (9, 10))
        engine.move((9, 7), (9, 8))
        engine.move((9, 10), (9, 9))

        board_before = [row[:] for row in engine.state.board.grid]
        player_before = engine.current_player

        engine.move((9, 8), (9, 9))  # 後手が先手の先鋒を取る

        # 駒が取られて盤面が変わっている
        assert engine.state.board.get(9, 9) is not None
        assert engine.current_player != player_before

        # undo
        engine.undo()

        # 盤面が復元されている
        assert engine.state.board.grid == board_before
        assert engine.current_player == player_before
        # 先手の先鋒がまだいる
        assert engine.state.board.get(9, 9) is not None
        assert engine.state.board.get(9, 9)[1] == 0  # 先手の駒


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

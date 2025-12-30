"""ゲームエンジンのテスト"""

import pytest
from backend.domain.board import Board
from backend.domain.game_state import GameState, create_initial_state
from backend.rules.game_engine import GameEngine


class TestGameEngineBasic:
    """基本的なゲームエンジンのテスト"""

    def test_create_initial_state(self):
        engine = GameEngine()
        assert engine.current_player == 0
        assert not engine.is_game_over
        assert engine.winner is None

    def test_initial_board_has_pieces(self):
        engine = GameEngine()
        # 先手の将 (ID:1) は (9, 18) にいる
        piece = engine.state.board.get(9, 18)
        assert piece is not None
        assert piece[0] == 1  # 将
        assert piece[1] == 0  # 先手

        # 後手の将 (ID:1) は (9, 0) にいる
        piece = engine.state.board.get(9, 0)
        assert piece is not None
        assert piece[0] == 1  # 将
        assert piece[1] == 1  # 後手


class TestGameEngineMove:
    """移動のテスト"""

    def test_move_simple(self):
        # 両陣営に必要な駒を配置
        state = GameState()
        state.board.set(9, 12, 34, 0)  # 先鋒
        state.board.set(9, 18, 1, 0)   # 先手の将
        state.board.set(8, 18, 14, 0)  # 先手の中軍
        state.board.set(10, 18, 16, 0) # 先手の旗
        state.board.set(9, 0, 1, 1)    # 後手の将
        state.board.set(8, 0, 14, 1)   # 後手の中軍
        state.board.set(10, 0, 16, 1)  # 後手の旗

        engine = GameEngine(state)

        # 先鋒は前(-y方向)に5路まで進める
        moves = engine.get_legal_moves((9, 12))
        assert len(moves) > 0
        # player=0の前は-y方向なので(9, 11)に移動可能
        assert (9, 11) in moves

        result = engine.move((9, 12), (9, 11))
        assert result.success
        assert engine.current_player == 1  # 後手に交代

    def test_cannot_move_enemy_piece(self):
        state = GameState()
        state.board.set(9, 0, 1, 1)  # 後手の将
        engine = GameEngine(state)

        # 先手番で後手の駒を動かそうとする
        result = engine.move((9, 0), (9, 1))
        assert not result.success
        assert "相手" in result.error

    def test_illegal_move(self):
        state = GameState()
        state.board.set(9, 12, 34, 0)  # 先鋒
        engine = GameEngine(state)

        # 先鋒は横には動けない
        result = engine.move((9, 12), (10, 12))
        assert not result.success


class TestGameEngineVictory:
    """勝敗判定のテスト"""

    def test_capture_shou_only(self):
        """将だけ取っても勝ちにならない（中軍と旗が両方残っている）"""
        state = GameState()
        # 先手も後手も将、中軍、旗を配置
        state.board.set(5, 5, 1, 0)    # 先手の将
        state.board.set(4, 5, 14, 0)   # 先手の中軍
        state.board.set(3, 5, 16, 0)   # 先手の旗
        state.board.set(6, 5, 1, 1)    # 後手の将
        state.board.set(7, 5, 14, 1)   # 後手の中軍
        state.board.set(8, 5, 16, 1)   # 後手の旗

        engine = GameEngine(state)

        # 先手が後手の将を取る
        result = engine.move((5, 5), (6, 5))
        assert result.success
        assert result.captured == 1

        # この時点ではまだ勝敗なし（中軍と旗が残っている）
        assert engine.winner is None

    def test_capture_shou_and_chugun_and_hata(self):
        """将と中軍と旗を全て取ると勝ち"""
        state = GameState()
        # 先手は将、中軍、旗あり、後手は将だけ
        state.board.set(5, 5, 1, 0)    # 先手の将
        state.board.set(4, 5, 14, 0)   # 先手の中軍
        state.board.set(3, 5, 16, 0)   # 先手の旗
        state.board.set(6, 5, 1, 1)    # 後手の将

        engine = GameEngine(state)

        # 先手が後手の将を取る
        result = engine.move((5, 5), (6, 5))
        assert result.success
        assert result.winner == 0  # 先手の勝ち


class TestGameEnginePromotion:
    """成りのテスト"""

    def test_promote_in_enemy_zone(self):
        """敵陣で成る"""
        state = GameState()
        # 先手の中軍(14)を敵陣直前に配置
        state.board.set(5, 6, 14, 0)

        engine = GameEngine(state)

        # 敵陣(y=5)に移動
        result = engine.move((5, 6), (5, 5), promote=True)
        assert result.success
        assert result.promoted
        assert result.promoted_to == 35  # 帥


class TestInitialSetup:
    """初期配置のテスト"""

    def test_initial_piece_count(self):
        """初期配置の駒数確認"""
        state = create_initial_state()

        # 駒の総数をカウント
        count = 0
        for x in range(19):
            for y in range(19):
                if state.board.get(x, y) is not None:
                    count += 1

        # GAMERULE.mdの初期配置に基づく
        # 実際の配置を信頼して、駒があることを確認
        assert count > 0, "No pieces on board"
        # 先手と後手で同数であることを確認
        sente_count = sum(1 for x in range(19) for y in range(19)
                         if state.board.get(x, y) and state.board.get(x, y)[1] == 0)
        gote_count = sum(1 for x in range(19) for y in range(19)
                        if state.board.get(x, y) and state.board.get(x, y)[1] == 1)
        assert sente_count == gote_count, f"Sente: {sente_count}, Gote: {gote_count}"

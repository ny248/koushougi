"""undo機能のテスト"""

import pytest
from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import create_initial_state


def do_move(engine, from_pos, to_pos, promote=False):
    """フェーズベースAPIで手を指すヘルパー関数"""
    if not engine.select_piece(from_pos):
        return None

    result = engine.select_destination(to_pos)
    if not result.success:
        return None

    # 成り判断が必要な場合
    if engine.phase == GamePhase.PROMOTION:
        result = engine.decide_promotion(promote)

    # 射撃フェーズはスキップ
    while engine.phase == GamePhase.SHOOTING:
        result = engine.skip_shoot()

    return result


class TestUndo:
    """undo機能のテスト"""

    def test_undo_simple_move(self):
        """undoで状態が復元される"""
        engine = GameEngine()

        # 初期状態を記録
        initial_player = engine.current_player
        initial_move_count = engine.state.move_count

        # 手を指す（先鋒を前進）
        result = do_move(engine, (9, 12), (9, 11))
        assert result is not None
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
        """複数回のundoが正常に動作する

        1状態遷移=1棋譜エントリの設計により、1ターン分を戻すには
        「move」と「select」の2回のundoが必要
        """
        engine = GameEngine()

        # 3手指す
        moves_played = []
        for i in range(3):
            # 適当な手を指す
            found = False
            for x in range(19):
                if found:
                    break
                for y in range(19):
                    piece = engine.state.board.get(x, y)
                    if piece and piece[1] == engine.current_player:
                        legal = engine.get_legal_moves((x, y))
                        if legal:
                            from_pos = (x, y)
                            to_pos = legal[0]
                            moves_played.append((from_pos, to_pos, engine.current_player))
                            do_move(engine, from_pos, to_pos)
                            found = True
                            break

        # 各ターンを完全にundoするには2回のundo（move + select）が必要
        for i in range(2, -1, -1):
            # moveをundo → DEST_SELECTに戻る
            assert engine.undo() is True
            assert engine.phase == GamePhase.DEST_SELECT

            # selectをundo → PIECE_SELECTに戻り、手番も戻る
            assert engine.undo() is True
            assert engine.phase == GamePhase.PIECE_SELECT
            assert engine.current_player == moves_played[i][2]

    def test_undo_empty_kifu(self):
        """空の棋譜からundoするとFalseを返す"""
        engine = GameEngine()
        assert engine.undo() is False

    def test_captured_piece_restored(self):
        """駒を取った後にundoすると盤面が復元される"""
        engine = GameEngine()

        # 先手の先鋒を前進させる
        do_move(engine, (9, 12), (9, 11))
        do_move(engine, (9, 6), (9, 7))  # 後手も前進
        do_move(engine, (9, 11), (9, 10))
        do_move(engine, (9, 7), (9, 8))
        do_move(engine, (9, 10), (9, 9))

        board_before = [row[:] for row in engine.state.board.grid]
        player_before = engine.current_player

        do_move(engine, (9, 8), (9, 9))  # 後手が先手の先鋒を取る

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
        from ai.minimax.player import MinimaxPlayer

        engine = GameEngine()
        ai = MinimaxPlayer(depth=2, max_moves=10)

        # 初期状態を記録
        initial_grid = [row[:] for row in engine.state.board.grid]
        initial_player = engine.current_player

        # AIにアクションを選ばせる（探索が行われる）
        action = ai.choose_action(engine.state)

        # 探索後も盤面が変わっていないこと
        assert engine.state.board.grid == initial_grid
        assert engine.current_player == initial_player

        # アクションは選べていること
        assert action is not None

    def test_minimax_returns_valid_move(self):
        """Minimaxが合法手を返すこと"""
        from ai.minimax.player import MinimaxPlayer
        from backend.domain.action import SelectPieceAction, SelectDestinationAction

        engine = GameEngine()
        ai = MinimaxPlayer(depth=2, max_moves=10)

        # 駒選択アクション
        action = ai.choose_action(engine.state)
        assert action is not None
        assert isinstance(action, SelectPieceAction)

        # 選択を実行
        engine.apply_action(action)

        # 移動先選択アクション
        action2 = ai.choose_action(engine.state)
        assert action2 is not None
        assert isinstance(action2, SelectDestinationAction)

        # 実際に合法手かチェック
        legal_moves = engine.get_legal_destinations()
        assert action2.pos in legal_moves

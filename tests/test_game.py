import unittest

from koushougi import Action, Piece, square
from koushougi.ai import WIN, analyze_search, choose_search_move
from koushougi.game import Game, outcome, promotion
from koushougi.move_ordering import MoveOrdering


class GameTest(unittest.TestCase):
    def test_promoted_piece_cannot_promote_again_after_capturing_a_general(self):
        from koushougi.position import describe_action

        for side, enemy in (("black", "white"), ("white", "black")):
            for name, next_name in (("歩総", "都司"), ("車総", "千総"),
                                    ("千総", "龍驤"), ("騎総", "天馬")):
                with self.subTest(side=side, name=name):
                    game = Game()
                    origin, target = map(square, ("K10", "K11" if name != "騎総" else "L12"))
                    game.board = {origin: Piece(side, name, True), target: Piece(enemy, "将"),
                                  square("A19"): Piece(side, "将"),
                                  square("T1"): Piece(enemy, "帥")}
                    game.turn = side
                    action = Action(origin, (target,))
                    self.assertIn(action, game.actions(origin))
                    self.assertIsNone(promotion(game.board, action))
                    self.assertIsNone(describe_action(game.board, action)["promotion"])
                    choices = [move for move, _ in game.successors() if move[0] == action]
                    self.assertEqual(choices, [(action, False, ())])
                    before = game.board.copy()
                    with self.assertRaises(ValueError):
                        game.play(action, promote=True)
                    self.assertEqual(game.board, before)
                    self.assertEqual(game.turn, side)
                    game.board[origin] = Piece(side, name)
                    self.assertEqual(promotion(game.board, action), next_name)
                    game.board[origin] = Piece(side, name, True)
                    game.play(action)
                    self.assertEqual(game.board[target], Piece(side, name, True))

    def test_promoted_piece_cannot_promote_again_on_entering_enemy_zone(self):
        for side, start, target in (("black", "K7", "K6"), ("white", "K13", "K14")):
            with self.subTest(side=side):
                game = Game()
                origin, landing = map(square, (start, target))
                action = Action(origin, (landing,))
                game.board = {origin: Piece(side, "歩総", True)}
                self.assertIsNone(promotion(game.board, action))
                game.board[origin] = Piece(side, "歩総")
                self.assertEqual(promotion(game.board, action), "都司")

    def setUp(self):
        self.game = Game()
        self.game.board = {
            square(cell): Piece(side, name)
            for cell, side, name in (
                ("K19", "black", "将"),
                ("F4", "white", "将"),
                ("K2", "white", "中軍"),
                ("H7", "white", "旗"),
                ("E8", "black", "砲"),
            )
        }

    def test_shot_can_enable_promotion_and_later_end_the_game(self):
        move = Action(square("E8"), (square("F7"),))
        with self.assertRaises(ValueError):
            self.game.play(move, promote=True)
        self.assertEqual(self.game.turn, "black")

        shot = Action(move.origin, move.path, (square("F4"),))
        captures = dict(self.game.successors(captures_only=True))
        self.assertNotIn((move, False, ()), captures)
        self.assertIn((shot, False, ()), captures)
        self.assertIn((shot, True, ()), captures)
        self.game.play(shot, promote=True)
        self.assertEqual(self.game.board[square("F7")].name, "砲車")
        self.assertIsNone(outcome(self.game.board))

        self.game.play(Action(square("K2"), (square("K3"),)))
        self.game.play(Action(square("F7"), (square("G7"),), (square("H7"),)))
        self.assertEqual(outcome(self.game.board), "black")
        self.assertEqual(self.game.actions(square("K3")), ())

    def test_promoted_commander_preserves_game_until_captured(self):
        board = self.game.board
        del board[square("F4")]
        del board[square("H7")]
        board[square("K2")] = Piece("white", "帥")
        self.assertIsNone(outcome(board))
        del board[square("K2")]
        self.assertEqual(outcome(board), "black")

    def test_search_reads_a_win_after_the_opponents_reply(self):
        self.game.board = {
            square("T19"): Piece("black", "将"),
            square("A1"): Piece("white", "将"),
            square("B2"): Piece("black", "車"),
            square("B3"): Piece("black", "車"),
        }
        board = self.game.board.copy()
        shallow = analyze_search(self.game, max_depth=2)
        extended = analyze_search(self.game, max_depth=2, capture_depth=1)
        deeper = analyze_search(self.game, max_depth=3)
        self.assertLess(shallow.score, WIN)
        self.assertEqual((extended.depth, extended.score), (2, WIN))
        self.assertEqual((deeper.depth, deeper.score), (3, WIN))
        self.assertEqual(self.game.board, board)
        first = Action(square("B2"), (square("C2"),))
        self.assertIn((first, False, ()), extended.best_moves)
        self.assertIn((first, False, ()), deeper.best_moves)
        self.game.play(first)
        replies = list(self.game.successors())
        self.assertTrue(replies)
        for _, reply in replies:
            self.assertTrue(any(outcome(child.board) == "black" for _, child in reply.successors()))

    def test_search_evaluator_can_change_without_changing_candidate_order(self):
        self.game.board = {
            square("T19"): Piece("black", "将"),
            square("A1"): Piece("white", "将"),
            square("D6"): Piece("black", "車"),
        }

        def rook_file(game, side):
            self.assertEqual(side, "black")
            return next(x for (x, _), piece in game.board.items() if piece.name == "車")

        def prefer_left(game, side):
            return -rook_file(game, side)

        ordering = MoveOrdering(prefer_left, use_previous_iteration=False)
        left = analyze_search(self.game, max_depth=1, evaluator=prefer_left, ordering=ordering)
        right = analyze_search(self.game, max_depth=1, evaluator=rook_file, ordering=ordering)
        self.assertEqual(left.moves, right.moves)
        self.assertIn(left.moves[0], left.best_moves)
        self.assertNotIn(right.moves[0], right.best_moves)
        self.assertTrue(set(left.best_moves).isdisjoint(right.best_moves))

    def test_root_priority_can_change_without_changing_evaluator(self):
        def flat_score(game, side):
            return 0

        def reverse_order(game, moves):
            self.assertIs(game, self.game)
            return range(len(moves))

        baseline = MoveOrdering(flat_score)
        reordered = MoveOrdering(flat_score, root_priority=reverse_order)
        options = dict(max_depth=2, candidate_limit=1, evaluator=flat_score)
        result = analyze_search(self.game, ordering=baseline, **options)
        self.assertGreater(len(result.moves), 1)
        self.assertEqual(result.best_moves, result.moves[:1])
        self.assertEqual(choose_search_move(self.game, ordering=reordered, **options),
                         result.moves[-1])

    def test_terminal_positions_take_precedence_over_custom_scores(self):
        self.game.board = {
            square("T19"): Piece("black", "将"),
            square("A1"): Piece("white", "将"),
            square("A2"): Piece("black", "車"),
        }

        def nonterminal_only(game, side):
            self.assertIsNone(outcome(game.board))
            return 0

        choice = analyze_search(self.game, evaluator=nonterminal_only,
                                ordering=MoveOrdering(nonterminal_only))
        self.assertEqual((choice.depth, choice.score), (1, WIN))
        self.game.play(*choice.best_moves[0])
        self.assertEqual(outcome(self.game.board), "black")

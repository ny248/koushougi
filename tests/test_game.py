import unittest

from koushougi import Action, Piece, square
from koushougi.game import Game, outcome


class GameTest(unittest.TestCase):
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

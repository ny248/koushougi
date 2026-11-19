import copy
import pickle
import unittest

from koushougi import Action, Piece, settle, square
from koushougi.board import Board
from koushougi.evaluation import material_points, material_score
from koushougi.game import Game


class BoardTest(unittest.TestCase):
    def assert_totals(self, board):
        for side in ("black", "white"):
            self.assertEqual(material_points(board, side), material_points(dict(board), side))
        for name, locations in board.special_squares.items():
            self.assertEqual(locations, {cell for cell, piece in board.items() if piece.name == name})

    def test_direct_edits_keep_scores_and_special_effects_current(self):
        board = Board({square("E5"): Piece("black", "高道"),
                       square("F6"): Piece("white", "五里霧", True)})
        edits = (
            lambda: board.__setitem__(square("E5"), Piece("black", "五里霧", True)),
            lambda: board.update({square("F6"): Piece("black", "招揺", True)}),
            lambda: board.setdefault(square("F6"), Piece("white", "聖燈", True)),
            lambda: board.setdefault(square("G7"), Piece("white", "聖燈", True)),
            lambda: board.__ior__({square("H8"): Piece("black", "歩兵")}),
            lambda: board.pop(square("E5")),
            lambda: board.pop(square("A1"), None),
            lambda: board.__delitem__(square("G7")),
            lambda: board.popitem(),
            lambda: board.clear(),
        )
        for edit in edits:
            edit()
            self.assert_totals(board)
        with self.assertRaises(KeyError):
            board.pop(square("A1"))
        with self.assertRaises(KeyError):
            del board[square("A1")]
        self.assert_totals(board)

    def test_copies_and_serialization_keep_independent_totals(self):
        priest, banner = map(square, ("E5", "F6"))
        board = Board({priest: Piece("black", "高道"), banner: Piece("black", "招揺", True)})
        for clone in (board.copy(), copy.copy(board), copy.deepcopy(board), pickle.loads(pickle.dumps(board))):
            with self.subTest(clone=type(clone).__name__):
                del clone[priest]
                settle(clone)
                self.assertEqual(clone[banner], Piece("black", "旗"))
                self.assertEqual(board[banner].name, "招揺")
                self.assertIn(priest, board)
                self.assert_totals(clone)
                self.assert_totals(board)

    def test_assigned_dictionary_remains_shared_and_successors_are_independent(self):
        game = Game()
        pieces = {square("K19"): Piece("black", "将"),
                  square("K1"): Piece("white", "将"),
                  square("E8"): Piece("black", "砲")}
        game.board = pieces
        pieces[square("F4")] = Piece("white", "歩兵")
        self.assertIs(game.board, pieces)
        self.assertIn(square("F4"), game.board)
        original = pieces.copy()
        children = list(game.successors())
        self.assertTrue(children)
        for _, child in children:
            self.assert_totals(child.board)
        children[0][1].board.clear()
        self.assertEqual(game.board, original)
        self.assertTrue(children[1][1].board)
        self.assert_totals(children[1][1].board)

    def test_promotion_poison_and_linked_changes_preserve_scores(self):
        game = Game()
        origin, landing, linked, poison = map(square, ("E7", "F6", "A19", "K10"))
        game.board = Board({origin: Piece("black", "記室"),
                            linked: Piece("black", "前衝"),
                            poison: Piece("white", "毒火", True),
                            square("K19"): Piece("black", "将"),
                            square("K1"): Piece("white", "将")})
        before = game.board.copy()
        for _, child in game.successors():
            self.assert_totals(child.board)
        self.assertEqual(game.board, before)
        game.play(Action(origin, (landing,)), promote=True, linked=(linked,))
        self.assertNotIn(poison, game.board)
        self.assertEqual(game.board[linked].name, "天網")
        self.assert_totals(game.board)
        self.assertEqual(material_score(game, "black"), material_points(dict(game.board), "black"))

    def test_invalid_piece_does_not_change_existing_totals(self):
        cell = square("E5")
        board = Board({cell: Piece("black", "高道")})
        before = board.copy()
        with self.assertRaises(KeyError):
            board[cell] = Piece("black", "未定義の駒")
        self.assertEqual(board, before)
        self.assert_totals(board)

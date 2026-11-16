import unittest
from collections import Counter

from koushougi import Action, Piece, initial_state, movement_actions, preview_action, square


class RulesTest(unittest.TestCase):
    def test_initial_position(self):
        board = initial_state()
        self.assertEqual(Counter(piece.side for piece in board.values()),
                         {"black": 90, "white": 90})
        for cell, piece in {"K1": "将", "K3": "仏狼機", "K7": "先鋒",
                            "K19": "将", "K13": "先鋒", "L18": "鼓"}.items():
            self.assertEqual(board[square(cell)].name, piece)
        self.assertEqual(len([cell for cell in board if cell[1] == 9]), 0)

    def test_bow_blocked_but_cannon_can_shoot_over_piece(self):
        start, end, screen, target = map(square, ("E5", "F6", "F7", "F9"))
        shot = Action(start, (end,), (target,))
        board = {start: Piece("white", "弓"), screen: Piece("white", "歩兵"),
                 target: Piece("black", "歩兵")}
        self.assertNotIn(shot, movement_actions(board, start))
        board[start] = Piece("white", "砲")
        result = preview_action(board, shot)
        self.assertNotIn(target, result)
        self.assertEqual(result[screen], board[screen])
        self.assertIn(target, board)
        board[screen] = Piece("white", "牌総")
        self.assertNotIn(shot, movement_actions(board, start))

    def test_cavalry_captures_at_both_landings(self):
        start, first, second = map(square, ("C3", "D5", "E7"))
        action = Action(start, (first, second))
        board = {start: Piece("white", "騎総"), first: Piece("black", "歩兵"),
                 second: Piece("black", "歩兵")}
        self.assertEqual(preview_action(board, action), {second: board[start]})
        board[first] = Piece("white", "歩兵")
        self.assertNotIn(action, movement_actions(board, start))

    def test_cavalry_can_change_short_axis_on_second_jump(self):
        start, first, straight, inward, turn = map(square, ("K10", "L12", "M14", "K14", "N13"))
        board = {start: Piece("white", "騎総")}
        actions = movement_actions(board, start)
        self.assertIn(Action(start, (first, straight)), actions)
        self.assertIn(Action(start, (first, inward)), actions)
        self.assertNotIn(Action(start, (first, turn)), actions)
        self.assertNotIn(Action(start, (first, start)), actions)

    def test_folangji_can_choose_either_ray_first(self):
        start, end, first, second = map(square, ("E5", "F6", "F7", "G6"))
        board = {start: Piece("white", "仏狼機"), first: Piece("black", "歩兵"),
                 second: Piece("black", "歩兵")}
        for targets in ((first, second), (second, first)):
            self.assertEqual(preview_action(board, Action(start, (end,), targets)),
                             {end: board[start]})

    def test_folangji_can_shoot_two_targets_on_same_ray(self):
        start, end, first, second = map(square, ("E5", "F6", "F7", "F9"))
        action = Action(start, (end,), (first, second))
        board = {start: Piece("white", "仏狼機"), first: Piece("black", "歩兵"),
                 second: Piece("black", "歩兵")}
        self.assertEqual(preview_action(board, action), {end: board[start]})

    def test_infantry_without_drum_loses_only_forward_step(self):
        start = square("E5")
        board = {start: Piece("white", "歩兵")}
        forward = Action(start, (square("E6"),))
        self.assertNotIn(forward, movement_actions(board, start))
        board[square("J2")] = Piece("white", "鼓")
        self.assertIn(forward, movement_actions(board, start))

import unittest

from koushougi import Action, Piece, initial_state, movement_actions, preview_action, square
from koushougi.game import Game, PROMOTIONS


class SpecialEffectsTest(unittest.TestCase):
    def test_initial_and_promoted_pieces_have_movement_rules(self):
        names = {piece.name for piece in initial_state().values()} | set(PROMOTIONS.values())
        for name in names:
            with self.subTest(name=name):
                origin = square("K10")
                self.assertTrue(movement_actions({origin: Piece("black", name)}, origin))

    def test_poison_fire_takes_friendly_pieces_and_stops_a_second_step(self):
        origin, landing, ally, enemy = map(square, ("E5", "E6", "D6", "F6"))
        board = {origin: Piece("white", "毒火", True),
                 ally: Piece("white", "歩兵"), enemy: Piece("black", "歩兵")}
        self.assertEqual(preview_action(board, Action(origin, (landing,))),
                         {landing: board[origin]})
        board[origin] = Piece("white", "力士")
        board[enemy] = Piece("black", "毒火", True)
        actions = movement_actions(board, origin)
        self.assertIn(Action(origin, (landing,)), actions)
        self.assertFalse(any(len(a.path) > 1 and a.path[0] == landing for a in actions))

    def test_high_priest_and_fog_can_capture_adjacent_piece_after_moving(self):
        origin, halfway, landing, victim = map(square, ("E5", "G5", "J5", "K6"))
        for name, path in (("高道", (landing,)), ("五里霧", (halfway, landing))):
            with self.subTest(name=name):
                start = halfway if name == "高道" else origin
                board = {start: Piece("white", name), victim: Piece("black", "歩兵")}
                action = Action(start, path, (victim,))
                self.assertEqual(preview_action(board, action), {landing: board[start]})

    def test_sacred_lamp_reverts_fog_without_a_shot(self):
        origin, landing, enemy = map(square, ("E5", "G5", "H5"))
        board = {origin: Piece("white", "聖燈"), enemy: Piece("black", "五里霧", True)}
        actions = movement_actions(board, origin)
        self.assertFalse(any(action.shots for action in actions))
        result = preview_action(board, Action(origin, (landing,)))
        self.assertEqual(result[enemy], Piece("black", "高道"))

    def test_fog_blocks_shooting_and_lamp_restores_high_priest(self):
        origin, landing, target, fog = map(square, ("E7", "F6", "F4", "K6"))
        action = Action(origin, (landing,), (target,))
        board = {origin: Piece("black", "砲"), target: Piece("white", "歩兵"),
                 fog: Piece("white", "五里霧", True)}
        self.assertNotIn(action, movement_actions(board, origin))
        lamp = square("K13")
        board[lamp] = Piece("black", "聖燈", True)
        result = preview_action(board, Action(lamp, (square("K11"),)))
        self.assertEqual(result[fog], Piece("white", "高道"))
        self.assertIn(action, movement_actions(result, origin))

    def test_strategist_promotes_selected_pieces_and_removes_poison(self):
        game = Game()
        origin, landing, linked, unselected, poison = map(
            square, ("E7", "F6", "A19", "T18", "K10"))
        game.board = {origin: Piece("black", "記室"), linked: Piece("black", "前衝"),
                      unselected: Piece("black", "後衝"), poison: Piece("white", "毒火", True),
                      square("K19"): Piece("black", "将"), square("K1"): Piece("white", "将")}
        game.play(Action(origin, (landing,)), promote=True, linked=(linked,))
        self.assertEqual(game.board[landing], Piece("black", "軍師", True))
        self.assertEqual(game.board[linked], Piece("black", "天網", True))
        self.assertEqual(game.board[unselected], Piece("black", "後衝"))
        self.assertNotIn(poison, game.board)

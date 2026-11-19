import unittest
from unittest.mock import patch

from koushougi import Action, Piece, initial_state, movement_actions, preview_action, resolve_movement, square
from koushougi.board import Board
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

    def test_all_priests_can_capture_adjacent_enemy_after_moving(self):
        origin, halfway, landing, victim = map(square, ("E5", "G5", "J5", "K6"))
        ally, distant = map(square, ("J6", "L7"))
        for name in ("高道", "五里霧", "神僧", "聖燈"):
            paths = [(halfway, (landing,))]
            if name in {"五里霧", "聖燈"}:
                paths.append((origin, (halfway, landing)))
            for start, path in paths:
                for side, enemy in (("white", "black"), ("black", "white")):
                    for board_type in (dict, Board):
                        with self.subTest(name=name, path=path, side=side, board_type=board_type):
                            board = board_type({start: Piece(side, name),
                                                victim: Piece(enemy, "歩兵"),
                                                ally: Piece(side, "歩兵"),
                                                distant: Piece(enemy, "歩兵")})
                            actions = movement_actions(board, start)
                            action = Action(start, path, (victim,))
                            self.assertIn(action, actions)
                            self.assertIn(Action(start, path), actions)
                            self.assertNotIn(Action(start, path, (ally,)), actions)
                            self.assertNotIn(Action(start, path, (distant,)), actions)
                            self.assertEqual(preview_action(board, action),
                                             {landing: board[start], ally: board[ally],
                                              distant: board[distant]})

    def test_sacred_lamp_reverts_fog_before_optional_shot(self):
        origin, landing, enemy = map(square, ("E5", "G5", "H5"))
        board = {origin: Piece("white", "聖燈"), enemy: Piece("black", "五里霧", True)}
        actions = movement_actions(board, origin)
        self.assertIn(Action(origin, (landing,), (enemy,)), actions)
        result = preview_action(board, Action(origin, (landing,)))
        self.assertEqual(result[enemy], Piece("black", "高道"))
        self.assertEqual(preview_action(board, Action(origin, (landing,), (enemy,))),
                         {landing: board[origin]})

    def test_double_priests_can_shoot_after_each_independent_move(self):
        origin, first, second, victim1, victim2 = map(square, ("E5", "G5", "J5", "F5", "K5"))
        for name in ("五里霧", "聖燈"):
            for side, enemy in (("black", "white"), ("white", "black")):
                for board_type in (dict, Board):
                    with self.subTest(name=name, side=side, board_type=board_type):
                        board = board_type({origin: Piece(side, name, True),
                                            victim1: Piece(enemy, "歩兵"), victim2: Piece(enemy, "歩兵")})
                        actions = movement_actions(board, origin)
                        both = Action(origin, (first, second), (victim1, victim2), (1, 2))
                        self.assertIn(both, actions)
                        self.assertIn(Action(origin, (first, second), (victim1,), (1,)), actions)
                        self.assertIn(Action(origin, (first, second), (victim2,)), actions)
                        self.assertIn(Action(origin, (first, second)), actions)
                        self.assertIn(Action(origin, (first,), (victim1,)), actions)
                        self.assertEqual(preview_action(board, both), {second: board[origin]})
                        self.assertEqual(preview_action(board, Action(origin, (first, second), (victim1,), (1,))),
                                         {second: board[origin], victim2: board[victim2]})
                        self.assertNotIn(Action(origin, (first,), (victim1, victim2)), actions)
                        self.assertNotIn(Action(origin, (first, second), (victim2,), (1,)), actions)
                        self.assertNotIn(Action(origin, (first, second), (victim1, victim1), (1, 2)), actions)
                        game = Game()
                        game.turn, game.board = side, board.copy()
                        game.board.update({square("A19"): Piece(side, "将"),
                                           square("T1"): Piece(enemy, "将")})
                        move = (both, False, ())
                        successors = dict(game.successors())
                        self.assertIn(move, successors)
                        game.play(*move)
                        self.assertEqual(game.board, successors[move].board)

    def test_intermediate_shot_settles_effects_before_second_move_and_shot(self):
        origin, first, second, priest, banner = map(square, ("E5", "G5", "J5", "F5", "K5"))
        board = Board({origin: Piece("black", "聖燈", True), priest: Piece("white", "高道"),
                       banner: Piece("white", "招揺", True)})
        action = Action(origin, (first, second), (priest, banner), (1, 2))
        self.assertIn(action, movement_actions(board, origin))
        result, captures = resolve_movement(board, action)
        self.assertEqual([piece.name for piece in captures], ["高道", "旗"])
        self.assertEqual(result, {second: board[origin]})

    def test_reverted_or_dead_priest_cannot_continue_after_first_move(self):
        origin, first, second, enemy = map(square, ("E5", "G5", "J5", "F5"))
        board = Board({origin: Piece("black", "五里霧", True), enemy: Piece("white", "聖燈", True)})
        first_shot = Action(origin, (first,), (enemy,))
        self.assertIn(first_shot, movement_actions(board, origin))
        self.assertEqual(preview_action(board, first_shot), {first: Piece("black", "高道")})
        self.assertNotIn(Action(origin, (first, second), (enemy,), (1,)), movement_actions(board, origin))
        poison = square("H5")
        for name in ("五里霧", "聖燈"):
            board = Board({origin: Piece("black", name, True), poison: Piece("white", "毒火", True)})
            actions = movement_actions(board, origin)
            self.assertIn(Action(origin, (first,)), actions)
            self.assertFalse(any(action.path[0] == first and (len(action.path) > 1 or action.shots)
                                 for action in actions))

    def test_intermediate_shots_are_preserved_in_position_and_ai_history(self):
        from koushougi.position import position

        origin, first, second, victim1, victim2 = map(square, ("E5", "G5", "J5", "F5", "K5"))
        for name in ("五里霧", "聖燈"):
            def fixture():
                game = Game()
                game.board = Board({origin: Piece("black", name, True), victim1: Piece("white", "歩兵"),
                                    victim2: Piece("white", "歩兵"), square("A19"): Piece("black", "将"),
                                    square("T1"): Piece("white", "将")})
                return game

            action = Action(origin, (first, second), (victim1, victim2), (1, 2))
            history = {"from": "E5", "path": ["G5", "J5"], "shots": ["F5", "K5"],
                       "shot_steps": [1, 2], "promote": False, "linked": []}
            with self.subTest(name=name), patch("koushougi.position.Game", side_effect=fixture):
                initial = position([])
                description = next(row for row in initial["moves"]["E5"]
                                   if row["path"] == history["path"] and row["shots"] == history["shots"])
                self.assertEqual(description["shot_steps"], [1, 2])
                self.assertEqual(description["sequence"], [
                    {"kind": "move", "square": "G5"}, {"kind": "shoot", "square": "F5"},
                    {"kind": "move", "square": "J5"}, {"kind": "shoot", "square": "K5"}])
                played = position([history])
                self.assertEqual(played["pieces"]["J5"]["name"], name)
                self.assertNotIn("F5", played["pieces"])
                self.assertNotIn("K5", played["pieces"])
                with patch("koushougi.position.choose_search_move", return_value=(action, False, ())):
                    response = position([], ai=True, human_side="white")
                self.assertEqual(response["aiMove"], history)
                self.assertEqual(position([response["aiMove"]])["pieces"], response["pieces"])

    def test_final_shot_steps_remain_compatible_and_invalid_schedules_are_rejected(self):
        origin, first, second, victim = map(square, ("E5", "G5", "J5", "K5"))
        self.assertEqual(Action(origin, (first, second), (victim,), (2,)),
                         Action(origin, (first, second), (victim,)))
        for steps in ((0,), (3,), (True,), (1, 2)):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                Action(origin, (first, second), (victim,), steps)

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

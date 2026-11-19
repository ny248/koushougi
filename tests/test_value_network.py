import importlib.util
import json
from math import tanh
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from koushougi import Action, Piece, square
from koushougi.evaluation import material_score
from koushougi.game import Game
from koushougi.players.alpha_beta import analyze_search
from koushougi.value_network import PIECES, ValueNetwork, encode_board, initial_parameters, load_network


class FinishingGame(Game):
    def __init__(self):
        super().__init__()
        self.board.clear()
        self.board.update({square("A1"): Piece("black", "将"),
                           square("B1"): Piece("white", "将")})

    def actions(self, origin):
        capture = Action(square("A1"), (square("B1"),))
        return tuple(action for action in super().actions(origin) if action == capture)


class ValueNetworkTest(unittest.TestCase):
    def test_initial_network_matches_material_for_every_piece_and_rank(self):
        model = ValueNetwork()
        game = Game()
        for name in PIECES:
            for rank in range(19):
                for side in ("black", "white"):
                    for promoted in (False, True):
                        game.board.clear()
                        game.board[(9, rank)] = Piece(side, name, promoted)
                        for perspective in ("black", "white"):
                            encoded = encode_board(game.board, perspective)
                            self.assertEqual(model.forward(encoded), material_score(game, perspective))
                            self.assertEqual(model.score(game, perspective), material_score(game, perspective))

    def test_initial_network_and_fixed_depth_search_match_existing_evaluation(self):
        rng, game, model = Random(12), Game(), ValueNetwork()
        for _ in range(20):
            choices = list(game.successors())
            if not choices:
                break
            game = rng.choice(choices)[1]
            for side in ("black", "white"):
                self.assertEqual(model.forward(encode_board(game.board, side)), material_score(game, side))
        game.board = {square("T19"): Piece("black", "将"), square("A1"): Piece("white", "将"),
                      square("E8"): Piece("black", "砲"), square("F4"): Piece("white", "歩兵")}
        expected = analyze_search(game, evaluator=material_score, max_depth=2, time_limit=float("inf"))
        actual = analyze_search(game, model=model, max_depth=2, time_limit=float("inf"))
        self.assertEqual((actual.depth, actual.score, actual.best_moves),
                         (expected.depth, expected.score, expected.best_moves))

    def test_save_reload_and_invalid_models(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            model = ValueNetwork(width=8)
            model.save(path)
            self.assertEqual(load_network(path).parameters, model.parameters)
            with self.assertRaises(FileExistsError):
                model.save(path)
            path.write_text(json.dumps({"format": 1, "weights": {}}))
            with self.assertRaises(ValueError):
                load_network(path)
        for bad in (float("nan"), float("inf"), "bad"):
            parameters = initial_parameters(8)
            parameters["output"][0] = bad
            with self.assertRaises(ValueError):
                ValueNetwork(parameters, width=8)

    def test_runtime_uses_learned_weights(self):
        game = Game()
        game.board.clear()
        game.board[square("E5")] = Piece("black", "歩兵")
        parameters = initial_parameters(8)
        parameters["output_bias"][0] = 0.5
        model = ValueNetwork(parameters, width=8)
        self.assertEqual(model.score(game, "black"), material_score(game, "black") + 10_000)
        self.assertEqual(model.score(game, "white"), -model.score(game, "black"))
        parameters["output_bias"][0] = 100.0
        large = ValueNetwork(parameters, width=8)
        from koushougi.search import WIN
        self.assertEqual(large.score(game, "black"), WIN - 1)

    def test_initial_and_learned_models_use_the_full_network(self):
        game = Game()
        expected = material_score(game, "black")
        # 駒得の集計値はNNの推論結果に影響させない。
        game.board.material_balance = 123_456
        for output_weight in (0.0, 0.2):
            parameters = initial_parameters(8)
            parameters["output"][0] = output_weight
            model = ValueNetwork(parameters, width=8)
            with self.subTest(output_weight=output_weight), patch.object(
                model, "forward", wraps=model.forward
            ) as forward, patch("koushougi.value_network.tanh", wraps=tanh) as activation:
                actual = model.score(game, "black")
                forward.assert_called_once_with(encode_board(game.board, game.turn))
                self.assertEqual(activation.call_count, model.width)
            if output_weight == 0:
                self.assertEqual(actual, expected)

    def test_promotion_can_link_any_subset(self):
        game = Game()
        game.board = {square("A19"): Piece("black", "将"), square("T1"): Piece("white", "将"),
                      square("K7"): Piece("black", "記室"), square("A10"): Piece("black", "前衝"),
                      square("T10"): Piece("black", "後衝")}
        action = Action(square("K7"), (square("K5"),))
        children = [(move, child) for move, child in game.successors() if move[0] == action and move[1]]
        self.assertEqual({move[2] for move, _ in children},
                         {(), (square("A10"),), (square("T10"),), (square("A10"), square("T10"))})
        for move, child in children:
            replay = Game()
            replay.board = game.board.copy()
            replay.play(*move)
            self.assertEqual(child.board, replay.board)


@unittest.skipUnless(importlib.util.find_spec("torch"), "学習用のPyTorchが必要")
class TrainingTest(unittest.TestCase):
    def test_both_network_paths_learn(self):
        import torch
        from koushougi.train_value import TrainingNetwork
        from koushougi.value_network import SCALE

        network = TrainingNetwork(ValueNetwork(width=8))
        before = {name: value.detach().clone() for name, value in network.weights.items()}
        encoded = torch.tensor([encode_board(Game().board, "black")])
        optimizer = torch.optim.Adam(network.parameters(), lr=0.01)
        for _ in range(3):
            loss = ((network(encoded) / SCALE).tanh() - 0.5).square().mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        for name in ("base", "advance", "piece", "square", "output"):
            self.assertFalse(torch.equal(before[name], network.weights[name]), name)

    def test_torch_initial_output_and_export_match_runtime(self):
        import torch
        from koushougi.train_value import TrainingNetwork

        model = ValueNetwork(width=8)
        network = TrainingNetwork(model)
        game = Game()
        encoded = [encode_board(game.board, side) for side in ("black", "white")]
        expected = [model.forward(board) for board in encoded]
        self.assertEqual(network(torch.tensor(encoded)).tolist(), expected)
        with torch.no_grad():
            network.weights["output"].fill_(0.2)
            network.weights["output_bias"].fill_(-0.3)
        trained = network.export()
        for board, value in zip(encoded, network(torch.tensor(encoded)).tolist()):
            self.assertAlmostEqual(trained.forward(board), value, delta=0.02)

    def test_selfplay_training_evaluation_and_retraining_entry_points(self):
        import sys
        from koushougi import selfplay, train_value, evaluate_value

        with TemporaryDirectory() as directory:
            dataset = Path(directory) / "selfplay.jsonl"
            output = Path(directory) / "nn.json"
            continued = Path(directory) / "nn-next.json"
            with patch("koushougi.selfplay.Game", FinishingGame), patch.object(sys, "argv", [
                "selfplay", "--games", "2", "--max-plies", "2", "--depth", "1", "--output", str(dataset)
            ]):
                selfplay.main()
            rows = [json.loads(line) for line in dataset.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["value"] == 1 and row["search_score"] > 0 for row in rows))
            initial = ValueNetwork()
            for destination, extra in ((output, []), (continued, ["--model", str(output)])):
                with patch.object(sys, "argv", ["train_value", str(dataset), "--output", str(destination),
                                              "--device", "cpu", "--epochs", "3", *extra]):
                    train_value.main()
            learned = load_network(continued)
            self.assertNotEqual(learned.parameters["output"], initial.parameters["output"])
            with patch("koushougi.evaluate_value.Game", FinishingGame):
                self.assertEqual(evaluate_value.match(learned, initial, 2, 1, "black", depth=1), "win")
                self.assertEqual(evaluate_value.match(learned, initial, 2, 1, "white", depth=1), "loss")

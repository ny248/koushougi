import importlib.util
from io import StringIO
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from koushougi import Piece, square
from koushougi.game import Game
from koushougi.players.alpha_beta import analyze_search
from koushougi.value_network import ValueNetwork, initial_parameters


class SmallGame(Game):
    def __init__(self):
        super().__init__()
        self.board.clear()
        self.board.update({square("A19"): Piece("black", "将"), square("T1"): Piece("white", "将"),
                           square("E12"): Piece("black", "車"), square("N8"): Piece("white", "車")})


@unittest.skipUnless(importlib.util.find_spec("torch"), "学習用のPyTorchが必要")
class TrainCycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(1)

    def learned_model(self):
        params = initial_parameters(8)
        params["output"] = [0.1 * (index - 3) for index in range(8)]
        return ValueNetwork(params, width=8)

    def test_saved_moves_preserve_intermediate_shooting_and_read_legacy_moves(self):
        from koushougi import Action
        from koushougi.train_cycle import pack, unpack

        action = Action(square("E5"), (square("G5"), square("J5")),
                        (square("F5"), square("K5")), (1, 2))
        move = (action, False, ())
        self.assertEqual(unpack(json.loads(json.dumps(pack(move)))), move)
        legacy = pack((Action(action.origin, action.path, (square("K5"),)), False, ()))
        del legacy["shot_steps"]
        self.assertEqual(unpack(json.loads(json.dumps(legacy)))[0].shot_steps, ())

    def test_batch_evaluation_cache_and_perspectives_match_native(self):
        from koushougi.torch_evaluation import TorchEvaluator

        rng, game = Random(5), SmallGame()
        games = []
        for _ in range(12):
            _, game = rng.choice(list(game.successors()))
            games.append(game)
        for model in (ValueNetwork(width=8), self.learned_model()):
            scoring = TorchEvaluator(model, device="cpu", batch_size=4, cache_size=2)
            for side in ("black", "white"):
                expected = [model.score(game, side) for game in games]
                self.assertEqual(scoring.score_many(games, side), expected)
                self.assertEqual(scoring.score_many(games, side), expected)
                self.assertLessEqual(len(scoring.cache), 2)

    def test_batched_search_matches_scalar_at_completed_depths(self):
        from koushougi.torch_evaluation import TorchEvaluator

        model = self.learned_model()
        for game in (SmallGame(), Game()):
            if type(game) is Game:
                game.board = {square("T19"): Piece("black", "将"), square("A1"): Piece("white", "将"),
                              square("E8"): Piece("black", "砲"), square("F4"): Piece("white", "歩兵")}
            for depth in (1, 2, 3):
                expected = analyze_search(game, model=model, time_limit=float("inf"), max_depth=depth)
                actual = analyze_search(game, model=TorchEvaluator(model, device="cpu", batch_size=4),
                                        time_limit=float("inf"), max_depth=depth)
                self.assertEqual((actual.score, actual.depth, set(actual.best_moves)),
                                 (expected.score, expected.depth, set(expected.best_moves)))

    def test_initial_and_learned_batch_evaluation_use_the_network(self):
        from koushougi.torch_evaluation import TorchEvaluator

        game = SmallGame()
        for model in (ValueNetwork(width=8), self.learned_model()):
            scoring = TorchEvaluator(model, device="cpu", cache_size=0)
            expected = model.score(game, "black")
            with patch.object(scoring.network, "forward", wraps=scoring.network.forward) as forward:
                self.assertEqual(scoring.score_many([game], "black"), [expected])
                forward.assert_called_once()

    def test_two_generations_resume_keep_splits_separate_and_reuse_trajectories(self):
        from koushougi import train_cycle as cycle

        config = cycle.Config(generations=2, games=3, chunk_plies=4, workers=1, seconds=10.0,
                              depth=1, min_depth=1, epsilon=1.0, epochs=2, patience=2, batch_size=8,
                              evaluation_pairs=1, evaluation_seconds=10.0, evaluation_depth=1,
                              evaluation_max_plies=2, min_decided=1)
        with TemporaryDirectory() as directory, patch("koushougi.train_cycle.Game", SmallGame), patch(
            "sys.stdout", new_callable=StringIO
        ):
            root = Path(directory)
            ValueNetwork(width=8).save(root / "initial.json")
            cycle.run_cycle(root, config, "cpu", "cpu")
            first = root / "generation-001"
            second = root / "generation-002"
            reports = cycle.read(root / "complete.json")["generations"]
            self.assertEqual(len(reports), 2)
            for folder in (first, second):
                datasets = {name: cycle.read(folder / (name + ".json"))
                            for name in ("train", "validation", "test")}
                self.assertTrue(all(datasets.values()))
                sets = [{r["key"] for r in rows} for rows in datasets.values()]
                self.assertTrue(all(not (a & b) for i, a in enumerate(sets) for b in sets[i + 1:]))
                self.assertTrue(cycle.read(folder / "evaluation.json")["all_trajectories_replayed"])
                self.assertEqual(cycle.read(folder / "evaluation.json")["decided"], 0)
                self.assertFalse(cycle.read(folder / "evaluation.json")["promoted_for_next_generation"])
            previous = cycle.read(first / "selfplay/game-000/result.json")["context"]
            continued = cycle.read(second / "selfplay/game-000/job.json")["context"]
            self.assertEqual(previous, continued)
            self.assertEqual(cycle.read(second / "selfplay/game-000/result.json")["context"]["ply"], 8)
            before = (second / "candidate.json").read_bytes()
            cycle.run_cycle(root, config, "cpu", "cpu")
            self.assertEqual((second / "candidate.json").read_bytes(), before)

    def test_play_chunk_resume_does_not_repeat_recorded_moves(self):
        from koushougi import train_cycle as cycle

        config = cycle.Config(games=3, chunk_plies=5, epsilon=1.0, depth=1, min_depth=1,
                              evaluation_pairs=1, min_decided=1)
        with TemporaryDirectory() as directory, patch("koushougi.train_cycle.Game", SmallGame):
            root = Path(directory)
            teacher = root / "teacher.json"
            ValueNetwork(width=8).save(teacher)
            context = {"state": cycle.state(SmallGame()), "episode": 0, "ply": 0}
            jobs = [cycle.make_job(root / name, {side: teacher for side in ("black", "white")},
                                   context, config, "cpu", collect=True, lane=0, role="train", seed=7)
                    for name in ("full", "resume")]
            expected = cycle.play_chunk(jobs[0])
            real_save = cycle.save

            def interrupt(path, value):
                real_save(path, value)
                if path.name == "step-00001.json":
                    raise KeyboardInterrupt

            with patch("koushougi.train_cycle.save", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cycle.play_chunk(jobs[1])
            actual = cycle.play_chunk(jobs[1])
            self.assertEqual(actual["context"], expected["context"])
            self.assertEqual(actual["steps"], 5)
            full = [cycle.read(p)["move"] for p in sorted((root / "full").glob("step-*.json"))]
            resumed = [cycle.read(p)["move"] for p in sorted((root / "resume").glob("step-*.json"))]
            self.assertEqual(full, resumed)

    def test_epoch_checkpoint_resume_matches_continuous_training(self):
        from koushougi import train_cycle as cycle
        from koushougi.value_network import encode_board

        config = cycle.Config(epochs=4, patience=4, games=3, evaluation_pairs=1, min_decided=1)
        game = SmallGame()
        rows = [{"pieces": cycle.state(game)["pieces"], "turn": game.turn, "target": 0.6}]
        data = {name: list(rows) for name in ("train", "validation", "test")}
        with TemporaryDirectory() as directory:
            full, resumed = (Path(directory) / name for name in ("full", "resume"))
            for folder in (full, resumed):
                folder.mkdir()
                ValueNetwork(width=8).save(folder / "teacher.json")
            cycle.fit_generation(full, data, config, "cpu")
            real_save = cycle.save_torch

            def interrupt(path, value):
                real_save(path, value)
                if value["epoch"] == 2:
                    raise KeyboardInterrupt

            with patch("koushougi.train_cycle.save_torch", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cycle.fit_generation(resumed, data, config, "cpu")
            cycle.fit_generation(resumed, data, config, "cpu")
            self.assertEqual(cycle.read(full / "candidate.json"), cycle.read(resumed / "candidate.json"))


if __name__ == "__main__":
    unittest.main()

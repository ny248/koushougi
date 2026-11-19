import importlib.util
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.test_dqn import QuietGame
from koushougi.value_network import ValueNetwork


@unittest.skipUnless(importlib.util.find_spec("torch"), "PyTorchが必要")
class DQNExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(1)

    def setup_run(self, root):
        from dataclasses import asdict
        from koushougi.train_dqn import Config
        root.mkdir()
        ValueNetwork(width=4).save(root / "initial.json")
        training = Config(games=2, max_plies=2, batch_size=2, warmup=2, train_every=1,
                          epsilon_start=1, epsilon_end=1, target_interval=2, checkpoint_every=1)
        from koushougi.dqn_experiment import digest
        return {"training": asdict(training), "milestones": [1, 2],
                "initial_sha256": digest(root / "initial.json"),
                "evaluation": {"depth": 2, "seeds": 1, "max_plies": 2,
                               "opening_plies": [0], "seed": 12}}

    def test_learning_curve_and_interrupted_comparison_resume_preserve_training(self):
        from koushougi import dqn_experiment as experiment
        with TemporaryDirectory() as directory, patch("koushougi.train_dqn.Game", QuietGame), patch(
            "koushougi.dqn_experiment.Game", QuietGame
        ), patch("sys.stdout", new_callable=StringIO):
            root = Path(directory)
            full, resumed = root / "full", root / "resumed"
            full_config, resumed_config = self.setup_run(full), self.setup_run(resumed)
            experiment.run(full, full_config, "cpu", 1)
            original = experiment.evaluate
            calls = 0

            def interrupted(*args, **kwargs):
                nonlocal calls
                result = original(*args, **kwargs)
                calls += 1
                if calls == 1:
                    raise KeyboardInterrupt()
                return result

            with patch.object(experiment, "evaluate", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    experiment.run(resumed, resumed_config, "cpu", 1)
            experiment.run(resumed, resumed_config, "cpu", 1)
            self.assertEqual((full / "training/candidate.json").read_bytes(),
                             (resumed / "training/candidate.json").read_bytes())
            for games in (1, 2):
                folder = f"snapshots/game-{games:06d}"
                self.assertEqual((full / folder / "model.json").read_bytes(),
                                 (resumed / folder / "model.json").read_bytes())
                report = experiment.read(full / folder / "evaluation.json")
                self.assertEqual(report["results"], {"win": 0, "loss": 0, "ply_limit": 2, "no_legal_move": 0})
                self.assertIsNone(report["win_rate_completed"])
                self.assertEqual(report["depths"], {"2": 4})
                self.assertTrue(report["all_trajectories_replayed"])
                metadata = experiment.read(full / folder / "training.json")
                self.assertEqual(metadata["games_played"], games)
            summary = experiment.read(resumed / "summary.json")
            self.assertEqual([row["games"] for row in summary["milestones"]], [1, 2])
            self.assertFalse(summary["automatic_model_adoption"])
            self.assertEqual(experiment.read(resumed / "progress.json")["stage"], "complete")
            self.assertTrue((resumed / "summary.csv").exists())

    def test_match_resume_replays_exactly_and_detects_tampered_frames(self):
        from koushougi import dqn_experiment as experiment
        with TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.json"
            ValueNetwork(width=4).save(model)
            job = {"folder": str(root / "full"), "models": {"black": str(model), "white": str(model)},
                   "model_hashes": {str(model): experiment.digest(model)}, "opening": 0, "seed_index": 0,
                   "candidate_side": "black", "seed": 3, "start": experiment.state(QuietGame()),
                   "max_plies": 3, "depth": 2}
            full = experiment.run_match(job)
            resume_job = {**job, "folder": str(root / "resumed")}
            original = experiment.analyze_search
            calls = 0

            def interrupted(*args, **kwargs):
                nonlocal calls
                self.assertEqual(kwargs["time_limit"], float("inf"))
                self.assertIsNone(kwargs["candidate_limit"])
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt()
                return original(*args, **kwargs)

            with patch.object(experiment, "analyze_search", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    experiment.run_match(resume_job)
            resumed = experiment.run_match(resume_job)
            experiment.verify_match(resume_job, resumed)
            for first, second in zip(sorted((root / "full").glob("ply-*.json")),
                                     sorted((root / "resumed").glob("ply-*.json"))):
                self.assertEqual(experiment.read(first), experiment.read(second))
            broken = root / "resumed/ply-000002.json"
            data = experiment.read(broken)
            data["root_enumeration_complete"] = False
            experiment.save_json(broken, data)
            with self.assertRaisesRegex(ValueError, "列挙"):
                experiment.verify_match(resume_job, resumed)
            with self.assertRaisesRegex(ValueError, "識別情報"):
                experiment.verify_match(resume_job, {**resumed, "candidate_side": "white"})

    def test_openings_are_fixed_and_mutation_is_rejected(self):
        from koushougi import dqn_experiment as experiment
        with TemporaryDirectory() as directory, patch("koushougi.dqn_experiment.Game", QuietGame):
            root = Path(directory)
            config = {"seed": 4, "opening_plies": [0, 2]}
            rows = experiment.make_openings(root, config)
            self.assertEqual(experiment.make_openings(root, config), rows)
            for row in rows:
                game = QuietGame()
                for move in row["moves"]:
                    game.play(*experiment.unpack(move))
                self.assertEqual(experiment.state(game), row["state"])
            saved = experiment.read(root / "openings.json")
            saved["openings"][0]["state"]["turn"] = "white"
            experiment.save_json(root / "openings.json", saved)
            with self.assertRaisesRegex(ValueError, "開始局面"):
                experiment.make_openings(root, config)

    def test_statistics_use_opening_clusters_and_leave_unfinished_unscored(self):
        from koushougi.dqn_experiment import aggregate
        rows = [{"opening": opening, "winner": "black", "candidate_side": "black", "reason": "win"}
                for opening in range(2) for _ in range(4)]
        rows.append({"opening": 0, "winner": None, "candidate_side": "black", "reason": "ply_limit"})
        report = aggregate(rows, 2)
        self.assertEqual(report["decided"], 8)
        self.assertEqual(report["results"]["ply_limit"], 1)
        self.assertEqual(report["win_rate_completed"], 1)
        self.assertEqual(report["opening_cluster_label_swap_test"]["two_sided_p"], 0.5)


if __name__ == "__main__":
    unittest.main()

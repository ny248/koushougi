import importlib.util
from io import StringIO
import json
from math import atanh, tanh
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from koushougi import Action, Piece, square
from koushougi.game import Game, outcome
from koushougi.value_network import SCALE, ValueNetwork, encode_board


class QuietGame(Game):
    def __init__(self):
        super().__init__()
        self.board.clear()
        self.board.update({square("A19"): Piece("black", "将"),
                           square("T1"): Piece("white", "将"),
                           square("E12"): Piece("black", "歩兵"),
                           square("N8"): Piece("white", "歩兵")})


class FinishingGame(Game):
    def __init__(self):
        super().__init__()
        self.board.clear()
        self.board.update({square("A1"): Piece("black", "将"),
                           square("B1"): Piece("white", "将")})

    def actions(self, origin):
        capture = Action(square("A1"), (square("B1"),))
        return tuple(action for action in super().actions(origin) if action == capture)


@unittest.skipUnless(importlib.util.find_spec("torch"), "学習用のPyTorchが必要")
class DQNTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(1)

    def test_afterstate_q_preserves_initial_evaluation_and_both_perspectives(self):
        import torch
        from koushougi.train_dqn import DoubleDQN, encode_afterstate, restore_afterstate

        model = ValueNetwork(width=8)
        learner = DoubleDQN(model)
        game, rng = QuietGame(), Random(9)
        for _ in range(6):
            actor = game.turn
            _, child = rng.choice(list(game.successors()))
            encoded = encode_afterstate(child)
            restored = restore_afterstate(encoded)
            self.assertEqual(encode_afterstate(restored), encoded)
            self.assertEqual(outcome(restored.board), outcome(child.board))
            actual = learner.q_values(learner.online, [encoded]).item()
            self.assertAlmostEqual(actual, tanh(model.score(child, actor) / SCALE), places=6)
            # 回転・先後交換後も、次のすべての合法手の結果が一致する。
            original = {encode_afterstate(next_game) for _, next_game in child.successors()}
            normalized = {encode_afterstate(next_game) for _, next_game in restored.successors()}
            self.assertEqual(original, normalized)
            game = child
        with torch.no_grad():
            learner.online.weights["output"].fill_(0.1)
        native = learner.online.export()
        actual = learner.q_values(learner.online, [encode_afterstate(game)]).item()
        self.assertAlmostEqual(actual, tanh(native.score(game, actor) / SCALE), delta=0.0001)

    def test_double_dqn_selects_online_action_and_evaluates_same_action_with_target(self):
        import torch
        from types import SimpleNamespace
        from koushougi.train_dqn import DoubleDQN, Transition

        class FixedQ(torch.nn.Module):
            def __init__(self, values):
                super().__init__()
                self.register_buffer("scores", torch.tensor([-atanh(v) * SCALE for v in values]))

            def forward(self, boards):
                return self.scores[boards[:, 0]]

        learner = DoubleDQN(ValueNetwork(width=8), gamma=0.9, inference_batch_size=1)
        learner.online = FixedQ([0.0, 0.8, 0.2])
        learner.target = FixedQ([0.0, -0.3, 0.9])
        encoded = [bytes([token] + [0] * 360) for token in (1, 2)]
        children = [SimpleNamespace(board={}, encoded=row) for row in encoded]
        game = SimpleNamespace(turn="black", successors=lambda: iter([(None, child) for child in children]))
        with patch("koushougi.train_dqn.outcome", return_value=None), patch(
            "koushougi.train_dqn.encode_afterstate", side_effect=lambda child: child.encoded
        ), patch("koushougi.train_dqn.restore_afterstate", return_value=game):
            value = learner.best_reply_value(game)
            self.assertAlmostEqual(value, -0.3, places=6)
            # 相手の最善手の価値を反転する。targetの最大値0.9は選ばない。
            targets = learner.targets([Transition(encoded[0], 0.0, False),
                                       Transition(encoded[0], 1.0, True),
                                       Transition(encoded[1], -1.0, True)])
            self.assertAlmostEqual(targets[0], 0.27, places=6)
            self.assertEqual(targets[1:], [1.0, -1.0])
        self.assertFalse(learner.target.scores.requires_grad)

    def test_winning_reply_has_exact_reward_and_no_legal_move_is_not_a_draw(self):
        from types import SimpleNamespace
        from koushougi.train_dqn import DoubleDQN, Transition, encode_afterstate

        learner = DoubleDQN(ValueNetwork(width=8), gamma=0.9)
        self.assertEqual(learner.best_reply_value(FinishingGame()), 1.0)
        with patch("koushougi.train_dqn.restore_afterstate",
                   return_value=SimpleNamespace(successors=lambda: iter(()), turn="black")):
            row = Transition(encode_afterstate(QuietGame()), 0.0, False)
            self.assertEqual(learner.targets([row]), [None])
            result = learner.train_batch([row])
        self.assertEqual(result, {"loss": None, "samples": 0, "skipped_no_legal_move": 1})
        self.assertEqual(learner.updates, 0)

    def test_training_updates_online_then_synchronizes_frozen_target(self):
        import torch
        from koushougi.train_dqn import DoubleDQN, Transition, encode_afterstate

        learner = DoubleDQN(ValueNetwork(width=8), target_interval=3, learning_rate=0.01)
        _, child = next(FinishingGame().successors())
        row = Transition(encode_afterstate(child), 1.0, True)
        before = {key: value.clone() for key, value in learner.target.state_dict().items()}
        first = learner.train_batch([row])["loss"]
        self.assertTrue(any(not torch.equal(before[key], value)
                            for key, value in learner.online.state_dict().items()))
        for key, value in learner.target.state_dict().items():
            self.assertTrue(torch.equal(before[key], value))
        learner.train_batch([row])
        last = learner.train_batch([row])["loss"]
        self.assertLess(last, first)
        self.assertEqual((learner.updates, learner.target_updates), (3, 1))
        for key, value in learner.target.state_dict().items():
            self.assertTrue(torch.equal(learner.online.state_dict()[key], value))
        self.assertTrue(all(parameter.grad is None for parameter in learner.target.parameters()))

    def test_replay_capacity_and_restore(self):
        from koushougi.train_dqn import ReplayBuffer, Transition, encode_afterstate

        encoded = encode_afterstate(QuietGame())
        buffer = ReplayBuffer(2)
        for reward in (-1.0, 0.0, 1.0):
            buffer.push(Transition(encoded, reward, True))
        self.assertEqual(len(buffer), 2)
        self.assertEqual({row.reward for row in buffer.rows}, {0.0, 1.0})
        restored = ReplayBuffer.from_state_dict(buffer.state_dict())
        self.assertEqual(buffer.state_dict(), restored.state_dict())
        self.assertEqual(buffer.sample(2, Random(3)), restored.sample(2, Random(3)))

    def test_truncated_games_keep_bootstrapping_and_resume_matches_uninterrupted_run(self):
        import torch
        from koushougi import train_dqn

        config = train_dqn.Config(games=3, max_plies=2, batch_size=2, warmup=2,
                                 train_every=1, epsilon_start=1.0, epsilon_end=1.0,
                                 target_interval=2, checkpoint_every=1)
        with TemporaryDirectory() as directory, patch("koushougi.train_dqn.Game", QuietGame), patch(
            "sys.stdout", new_callable=StringIO
        ):
            full, resumed = (Path(directory) / name for name in ("full", "resumed"))
            full.mkdir()
            resumed.mkdir()
            train_dqn.train(full, config)
            real_choose = train_dqn.choose_move
            calls = 0

            def interrupt(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise KeyboardInterrupt
                return real_choose(*args, **kwargs)

            with patch("koushougi.train_dqn.choose_move", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    train_dqn.train(resumed, config)
            train_dqn.train(resumed, config, resume=True)
            self.assertEqual(json.loads((full / "candidate.json").read_text()),
                             json.loads((resumed / "candidate.json").read_text()))
            expected = torch.load(full / "checkpoint.pt", weights_only=True)
            actual = torch.load(resumed / "checkpoint.pt", weights_only=True)
            for name in ("rng", "replay", "steps", "results", "last_loss"):
                self.assertEqual(expected[name], actual[name], name)
            for name in ("online", "target"):
                for key, value in expected["learner"][name].items():
                    self.assertTrue(torch.equal(value, actual["learner"][name][key]))
            self.assertGreater(actual["learner"]["updates"], 0)
            self.assertTrue(all(not row["terminated"] and row["reward"] == 0
                                for row in actual["replay"]["rows"]))
            report = json.loads((resumed / "report.json").read_text())
            self.assertEqual(report["outcomes"], {"ply_limit": 3})
            self.assertEqual(report["games_decided"], 0)
            self.assertEqual(report["status"], "complete")

    def test_cli_exports_runtime_model_and_rejects_overwrite_and_changed_resume_config(self):
        import fcntl
        import sys
        from koushougi import train_dqn, evaluate_value
        from koushougi.value_network import load_network

        with TemporaryDirectory() as directory, patch("koushougi.train_dqn.Game", FinishingGame), patch(
            "sys.stdout", new_callable=StringIO
        ):
            output = Path(directory) / "run"
            command = ["train_dqn", "--output", str(output), "--device", "cpu", "--games", "2",
                       "--depth", "1", "--batch-size", "1", "--warmup", "1", "--train-every", "1",
                       "--epsilon-start", "0", "--epsilon-end", "0", "--target-interval", "2"]
            with patch.object(sys, "argv", command):
                train_dqn.main()
            model = load_network(output / "candidate.json")
            report = json.loads((output / "report.json").read_text())
            self.assertEqual((report["updates"], report["target_updates"]), (2, 1))
            self.assertEqual(report["outcomes"], {"black": 2})
            with patch("koushougi.evaluate_value.Game", FinishingGame):
                self.assertEqual(evaluate_value.match(model, ValueNetwork(), 2, 1, "black", depth=1), "win")
            with patch.object(sys, "argv", command), patch("sys.stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit):
                    train_dqn.main()
            with patch.object(sys, "argv", ["train_dqn", "--output", str(output), "--resume",
                                            "--games", "3"]), patch("sys.stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit):
                    train_dqn.main()
            with patch.object(sys, "argv", ["train_dqn", "--output", str(output), "--resume", "--device", "cpu"]):
                train_dqn.main()
                with (output / "run.lock").open("a") as lock, patch("sys.stderr", new_callable=StringIO):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(SystemExit):
                        train_dqn.main()
            with patch("koushougi.train_dqn.source_digest", return_value="changed"):
                with self.assertRaisesRegex(ValueError, "実行コード"):
                    train_dqn.train(output, train_dqn.Config(**report["config"]), resume=True)


if __name__ == "__main__":
    unittest.main()

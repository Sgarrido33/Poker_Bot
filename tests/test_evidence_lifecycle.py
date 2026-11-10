"""Replay worker ownership and the meaning of recorded sampling quotas."""
from dataclasses import asdict
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pokerfight.arena import make_policy
from pokerfight.evaluation import evaluate
from pokerfight.replay import replay_worst
from pokerfight.strategy import BotConfig


def replay_report(players=2):
    ids = ("hero",) + tuple(f"opponent_{i}" for i in range(1, players))
    payoffs = dict.fromkeys(ids, 0)
    record = {"seats": ids, "hand": 1, "hero_policy": "v2",
              "policy_seeds": {pid: i + 1 for i, pid in enumerate(ids)},
              "block": 0, "rotation": 0, "table_id": "replay-test",
              "history": [], "payoffs": payoffs, "board": []}
    return {"worst_candidate_hands": [record], "config": asdict(BotConfig(samples=128)),
            "rival_config": asdict(BotConfig(samples=512)),
            "hands_per_block_per_seat": 2, "opponents": {pid: "noregrets" for pid in ids[1:]},
            "assumptions": {"starting_stack": 800, "small_blind": 50, "big_blind": 100, "ante": 0},
            "seed": 1, "environment": {"source_sha256": "test-source"}}


def hand_result(report):
    return SimpleNamespace(history=[], trace=[],
                           payoffs=report["worst_candidate_hands"][0]["payoffs"],
                           board=[], decisions=[])


class ReplayLifecycleTests(unittest.TestCase):
    def test_success_closes_workers_after_all_prior_hands(self):
        report = replay_report()
        policies = [SimpleNamespace(close=Mock()), SimpleNamespace(close=Mock())]
        with patch("pokerfight.replay.Path.read_text", return_value=json.dumps(report)), \
             patch("pokerfight.evaluation.make_policy", side_effect=policies) as factory, \
             patch("pokerfight.replay.play_hand", return_value=hand_result(report)) as play, \
             patch("pokerfight.replay.environment", return_value=report["environment"]):
            result = replay_worst("memory.json")
        self.assertTrue(result["matched"])
        self.assertTrue(result["same_source"])
        self.assertEqual(play.call_count, 2)
        self.assertEqual([call.args[1].samples for call in factory.call_args_list], [128, 512])
        for policy in policies:
            policy.close.assert_called_once_with()

    def test_hand_failure_closes_workers_and_propagates_original_error(self):
        report = replay_report()
        policies = [SimpleNamespace(close=Mock()), SimpleNamespace(close=Mock())]
        failure = RuntimeError("failed hand")
        with patch("pokerfight.replay.Path.read_text", return_value=json.dumps(report)), \
             patch("pokerfight.evaluation.make_policy", side_effect=policies), \
             patch("pokerfight.replay.play_hand", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                replay_worst("memory.json")
        self.assertIs(caught.exception, failure)
        for policy in policies:
            policy.close.assert_called_once_with()

    def test_partial_factory_failure_closes_previously_created_workers(self):
        report = replay_report(3)
        policies = [SimpleNamespace(close=Mock()), SimpleNamespace(close=Mock())]
        failure = RuntimeError("failed worker creation")
        with patch("pokerfight.replay.Path.read_text", return_value=json.dumps(report)), \
             patch("pokerfight.evaluation.make_policy", side_effect=[*policies, failure]), \
             patch("pokerfight.replay.play_hand") as play:
            with self.assertRaises(RuntimeError) as caught:
                replay_worst("memory.json")
        self.assertIs(caught.exception, failure)
        play.assert_not_called()
        for policy in policies:
            policy.close.assert_called_once_with()


class EvidenceQuotaTests(unittest.TestCase):
    def test_report_uses_the_explicit_rival_base_config(self):
        report = evaluate(2, 1, 1, 72831, BotConfig(samples=128), opponents=("calling",),
                          candidate="calling", baseline="calling", rival_config=BotConfig(samples=512))
        self.assertEqual(report["rival_samples"], 512)
        self.assertEqual(report["rival_config"]["samples"], 512)

    def test_report_uses_hero_config_when_no_rival_config_was_passed(self):
        report = evaluate(2, 1, 1, 72832, BotConfig(samples=128), opponents=("calling",),
                          candidate="calling", baseline="calling")
        self.assertEqual(report["rival_samples"], 128)
        self.assertEqual(report["rival_config"]["samples"], 128)

    def test_base_quota_does_not_override_the_fixed_v2_4000_profile(self):
        # rival_samples records the base configuration passed to factories.
        # Named profiles and external/rule opponents retain their own quotas.
        policy = make_policy("v2_4000", BotConfig(samples=128), 72833)
        self.assertEqual(policy.config.samples, 4000)
        self.assertEqual(policy.config.budget_ms, 1600)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerfight.arena import POLICY_KINDS, make_policy
from pokerfight.evaluation import evaluate, simulate
from pokerfight.arena import HandResult
from pokerfight.strategy import BotConfig
from pokerfight.noregrets_opponent import NoRegretsTableOpponent

ROOT = Path(__file__).resolve().parents[1]


class _ClosablePolicy:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class NoRegretsFactoryTests(unittest.TestCase):
    def test_policy_choice_uses_env_profile_index_and_4250ms_timeout(self):
        index = ROOT / "research/noregrets_training_20261028/profiles_index.json"
        with patch.dict(os.environ, {"POKERFIGHT_NOREGRETS_PROFILES": str(index)}):
            self.assertIn("noregrets", POLICY_KINDS)
            policy = make_policy("noregrets", BotConfig(), 17)
        try:
            self.assertIsInstance(policy, NoRegretsTableOpponent)
            self.assertEqual(policy.profiles_manifest, index.resolve())
            self.assertEqual(policy.timeout_s, 4.25)
        finally:
            policy.close()

    def _patch_policies(self, instances):
        def factory(*_args, **_kwargs):
            value = _ClosablePolicy()
            instances.append(value)
            return value
        return patch("pokerfight.evaluation.make_policy", side_effect=factory)

    @staticmethod
    def _result():
        return HandResult({"hero": 10000, "opponent_1": 10000},
                          {"hero": 0, "opponent_1": 0}, (), (), ())

    def test_simulate_closes_workers_on_success_and_hand_error(self):
        for failure in (False, True):
            instances = []
            hand_patch = patch("pokerfight.evaluation.play_hand", side_effect=RuntimeError("table failed")) if failure else patch("pokerfight.evaluation.play_hand", return_value=self._result())
            with self.subTest(failure=failure), self._patch_policies(instances), hand_patch:
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "table failed"):
                        simulate(2, 1, 1, BotConfig(), opponents=("calling",), hero_kind="noregrets")
                else:
                    result = simulate(2, 1, 1, BotConfig(), opponents=("calling",), hero_kind="noregrets")
                    self.assertEqual(result["played_hands"], 1)
                self.assertEqual(len(instances), 2)
                self.assertTrue(all(p.closed == 1 for p in instances))

    def test_evaluate_closes_workers_per_rotation_label_even_on_error(self):
        for failure in (False, True):
            instances = []
            hand_patch = patch("pokerfight.evaluation.play_hand", side_effect=RuntimeError("table failed")) if failure else patch("pokerfight.evaluation.play_hand", return_value=self._result())
            with self.subTest(failure=failure), self._patch_policies(instances), hand_patch:
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "table failed"):
                        evaluate(2, 1, 1, 1, BotConfig(), opponents=("calling",), candidate="noregrets")
                else:
                    result = evaluate(2, 1, 1, 1, BotConfig(), opponents=("calling",), candidate="noregrets")
                    self.assertEqual(result["candidate_noregrets_native_fallback_reasons"], {})
                self.assertTrue(instances)
                self.assertTrue(all(p.closed == 1 for p in instances))


if __name__ == "__main__":
    unittest.main()

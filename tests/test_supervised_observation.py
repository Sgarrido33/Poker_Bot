"""Public-history updates cross the same persistent boundary as decisions."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy
from pokerfight.domain import Observation, PublicAction
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy


class SupervisedObservationTests(unittest.TestCase):
    def test_full_history_updates_match_direct_model_and_ack_does_not_leak(self):
        config = BotConfig(samples=128, seed=71)
        root = Path(__file__).resolve().parents[1]
        original = Observation.from_dict(json.loads((root / "examples/observation.json").read_text()))
        obs = replace(original, history=(PublicAction("0", "p4", "preflop", "raise_to", 300, True),),
                      players=tuple(replace(p, street_bet=300, contribution=300, stack=9700)
                                    if p.player_id == "p4" else p for p in original.players),
                      legal=replace(original.legal, call_amount=300, min_raise_to=500))
        for kind in ("v2",):
            with self.subTest(kind=kind), SupervisedPolicy(config, policy=kind) as worker:
                direct = make_policy(kind, config, config.seed)
                for hand in range(20):
                    history = (PublicAction("0", "p4", "preflop", "raise_to", 300, True),
                               PublicAction("1", "hero", "preflop", "fold", 0, True),
                               PublicAction("2", "p4", "flop", "raise_to", 500))
                    self.assertTrue(worker.observe(obs.table_id, f"old-{hand}", history))
                    # Duplicate broadcasts must have no extra effect.
                    self.assertTrue(worker.observe(obs.table_id, f"old-{hand}", history))
                    direct.model.observe(obs.table_id, f"old-{hand}", history)
                expected, actual = direct.decide(obs), worker.decide(obs)
                self.assertFalse(actual.fallback, actual.reason)
                self.assertEqual(actual.equity, expected.equity)
                self.assertEqual(actual.action, expected.action)

    def test_failed_observation_closes_worker_before_next_turn(self):
        with SupervisedPolicy(BotConfig(samples=16), policy="v2") as worker:
            with patch.object(worker, "_request", return_value={"observed": False}):
                self.assertFalse(worker.observe("table", "hand", ()))
            self.assertIsNone(worker.process)


if __name__ == "__main__":
    unittest.main()

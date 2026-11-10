from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts import competition_stage3 as stage3


class Stage3RegistrationTests(unittest.TestCase):
    def test_pilot_protocol_is_fixed_to_three_arms_and_two_groups(self):
        plan = stage3.protocol(stage3.PILOT_ID, "pilot", 2)
        self.assertEqual(plan["arms"], ["v2", "v4rb", "v6"])
        self.assertEqual(plan["players"], [5, 6])
        self.assertEqual(plan["session"]["hand_limit"], 128)
        self.assertEqual(len(stage3.jobs(plan)), 4)
        self.assertEqual(sum(n * len(plan["arms"]) * 2 for n in plan["players"]), 66)
        self.assertEqual(plan["configs"]["v2"], {"samples": 4000, "budget_ms": 1600})
        self.assertEqual(plan["configs"]["v6"], {"samples": 4096, "budget_ms": 3500})

    def test_comparison_jobs_cover_primary_and_controls(self):
        plan = stage3.protocol("crossplay-stage3-unit-comparison-20261028-01", "comparison", 40)
        self.assertEqual(len(stage3.jobs(plan)), 2 * 40 + 4 * 2 * 8)
        self.assertEqual(plan["inference"]["bootstrap_repetitions"], 20000)
        self.assertEqual(plan["inference"]["confirmatory_comparisons"], 2)
        self.assertEqual(plan["control_groups_per_format"], 8)
        self.assertEqual(plan["execution"]["workers"], 6)
        with tempfile.TemporaryDirectory(dir=stage3.BASE / ".tmp") as temp:
            seed_check = stage3.seed_check(Path(temp) / "fresh", plan)
        self.assertFalse(seed_check["reserved_reuse_authorized"])
        self.assertEqual(seed_check["historical_overlap"], 0)
        self.assertEqual(seed_check["reserved_overlap"], 0)

    def test_seed_guard_rejects_a_collision_in_a_history_fixture(self):
        identifier = "stage3-seed-collision-fixture"
        plan = stage3.protocol(identifier, "pilot", 1)
        group_seed = stage3.seed_for(identifier, "crossplay-session-01", "external_diverse", 5, 0)
        deck_seed = stage3.seed_for(group_seed, "deck", 0)
        with tempfile.TemporaryDirectory(dir=stage3.BASE / ".tmp") as temp:
            fixture = Path(temp) / "history.jsonl"
            fixture.write_text('{"deck_seed": %d}\n' % deck_seed, encoding="utf-8")
            with patch.object(Path, "rglob", return_value=[fixture]):
                with self.assertRaisesRegex(ValueError, "overlap historical data"):
                    stage3.seed_check(Path(temp) / "fresh", plan)

    def test_horizon_censoring_does_not_use_a_later_bust(self):
        row = {"eliminated_at": {"hero": 79}, "hero_observed_win": False,
               "played_hands": 128, "table_finished": False, "censored_survivor": False}
        at_24 = stage3._events(row, 24)
        self.assertEqual(at_24["bust"], 0)
        self.assertEqual(at_24["unresolved"], 1)
        self.assertEqual(at_24["censored_survivor"], 0)
        at_128 = stage3._events(row, 128)
        self.assertEqual(at_128["bust"], 1)
        self.assertEqual(at_128["unresolved"], 0)

    def test_snapshot_source_list_ignores_new_unused_noregrets_module(self):
        self.assertFalse(any(name.endswith("noregrets_opponent.py") for name in stage3.source_paths()))

    def test_registration_freezes_sources_and_protocol(self):
        with tempfile.TemporaryDirectory(dir=stage3.BASE / ".tmp") as temp:
            root = Path(temp) / "pilot"
            plan = stage3.register(root, "stage3-registration-test", "pilot", 1)
            loaded, digest = stage3.load(root)
            self.assertEqual(loaded["sources"], plan["sources"])
            self.assertEqual(len(digest), 64)
            self.assertEqual(stage3.seed_check(root, plan)["overlap"], 0)


if __name__ == "__main__":
    unittest.main()

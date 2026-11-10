import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy
from pokerfight.strategy import BotConfig
from scripts import competition_stage2 as exp
from scripts import competition_experiment as old


class Stage2Tests(unittest.TestCase):
    def test_explicit_rival_4000_profile_cannot_inherit_hero_quota(self):
        for config in (BotConfig(128, 100), BotConfig(4096, 3500)):
            p = make_policy("v2_4000", config, 812)
            self.assertEqual((p.control.config.samples, p.control.config.budget_ms), (4000, 1600))
            self.assertEqual(p.control.config.seed, 812)

    def test_pilot_has_no_candidate_and_main_requires_completed_pilot(self):
        plan = exp.protocol("technical-only-pilot-test", "pilot")
        self.assertEqual(plan["arms"], ["v2"])
        self.assertTrue(all(j[0] == "session" for j in old.jobs(plan)))
        self.assertEqual(len(old.jobs(plan)), 6)
        with self.assertRaisesRegex(ValueError, "completed technical pilot"):
            exp.protocol("must-not-run", "comparison")
        main = exp.protocol("fresh-comparison", "comparison", {"phase": "pilot", "complete": True, "selected_hand_limit": 128})
        self.assertEqual(len(old.jobs(main)), 68)
        self.assertEqual(main["session"]["groups"], 4)
        self.assertEqual(set(old.SCENARIOS) - set(main["scenarios"]), set())

    def test_elimination_horizon_uses_one_based_completed_hands_and_competing_win(self):
        row = {"eliminated_at": {"hero": 24}, "hero_observed_win": False,
               "played_hands": 64, "table_finished": False}
        self.assertEqual(exp.events(row, 24), {"bust": 0, "win": 0, "unresolved": 1, "table_finished": 0})
        self.assertEqual(exp.events(row, 25)["bust"], 1)
        row.update(eliminated_at={}, hero_observed_win=True, played_hands=10, table_finished=True)
        self.assertEqual(exp.events(row, 24), {"bust": 0, "win": 1, "unresolved": 0, "table_finished": 1})

    def test_pilot_length_selection_is_based_on_completion_only(self):
        plan = exp.protocol("technical-duration-selection", "pilot")
        sessions = [{"played_hands": 80, "hero_observed_win": False, "table_finished": True, "eliminated_at": {"hero": 0},
                     "counts": {"fallbacks": 0}, "last_stacks": {"hero": 0}}]
        jobs = [{"job": ["session", "external_mix", n, 0], "executions": 80, "sessions": sessions} for n in (5, 6)]
        with tempfile.TemporaryDirectory(dir=old.BASE / ".tmp") as tmp, patch.object(old, "load_plan", return_value=(plan, "digest")), patch.object(old, "verify"), patch.object(exp, "reports", return_value=jobs):
            out = exp.summarize_pilot(Path(tmp))
        self.assertEqual(out["selected_hand_limit"], 128)
        self.assertTrue(out["target_met"])
        self.assertFalse(out["policy_comparisons_observed"])


if __name__ == "__main__":
    unittest.main()

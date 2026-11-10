from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerfight.campaign import save
from scripts import competition_experiment as executor
from scripts import v8_validation as experiment


class V8ValidationTests(unittest.TestCase):
    def small_plan(self):
        p = experiment.protocol("v8d-validation-unit-only")
        p["players"] = [2]
        p["scenarios"] = {"copies_v2": ["v2_4000"]}
        p["phases"] = {"development": {"arms": ["v2", "v8d"], "groups": {"copies_v2": 2}},
                       "validation": {"arms": ["v2", "v4rb", "v8d"], "groups": {"copies_v2": 2}}}
        p["session"]["hand_limit"] = 3
        p["inference"]["bootstrap_reps"] = 100
        for config in p["configs"].values():
            config.update(samples=32, budget_ms=1600)
        return p

    def test_fixed_matrix_components_and_disjoint_phase_decks(self):
        p = experiment.protocol("fixed-before-results")
        self.assertEqual(len(experiment.jobs(p, "development")), 32)
        self.assertEqual(len(experiment.jobs(p, "validation")), 520)
        decks = experiment.planned_decks(p)
        self.assertEqual(len(decks), (32 + 520) * 128)
        self.assertEqual(p["configs"]["v2"]["samples"], 4000)
        self.assertEqual(p["configs"]["v4rb"]["samples"], 1024)
        self.assertIn("pokerfight/data/pushfold_charts.json", p["sources"])
        self.assertEqual(p["criteria"]["max_early_elimination_increase"], .05)

    def test_source_and_protocol_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=experiment.BASE / ".tmp") as temp:
            root = Path(temp)
            (root / "source").mkdir()
            code = root / "source" / "one.py"
            code.write_text("pass\n")
            p = self.small_plan()
            p["sources"] = {"one.py": experiment.sha(code)}
            save(root / "protocol.json", p)
            (root / "protocol.sha256").write_text(experiment.sha(root / "protocol.json"))
            experiment.load(root)
            code.write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                experiment.load(root)
            (root / "protocol.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "protocol changed"):
                experiment.load(root)

    def test_real_paired_sessions_replay_and_complete_matrix(self):
        p = self.small_plan()
        with tempfile.TemporaryDirectory(dir=experiment.BASE / ".tmp") as temp:
            root = Path(temp)
            folder = root / "development"
            folder.mkdir()
            cfg = experiment.settings(p, "development")
            with patch.object(experiment, "load", return_value=(p, "digest")):
                with self.assertRaisesRegex(ValueError, "Incomplete phase"):
                    experiment.summarize(root, "development")
                for job in experiment.jobs(p, "development"):
                    row = executor.execute_sessions(folder, cfg, "digest", job)
                    save(folder / (executor.job_name(job) + ".json"), row)
                result = experiment.summarize(root, "development")
                self.assertTrue(result["technical_passed"])
                self.assertEqual(result["table_executions"], 8)
                self.assertFalse(result["local_statistical_gates_passed"])
                replay = experiment.replay_worker((str(folder), cfg, experiment.jobs(p, "development")[0]))
                self.assertGreater(replay["hands"], 0)
                path = folder / (executor.job_name(experiment.jobs(p, "development")[0]) + ".jsonl")
                with path.open("a") as f:
                    f.write("{}\n")
                with self.assertRaisesRegex(ValueError, "Trace changed"):
                    experiment.summarize(root, "development")

    def test_bootstrap_uses_groups_and_keeps_player_formats_equal(self):
        def table(arm, rotation, chips):
            return {"variant": arm, "rotation": rotation, "last_stacks": {"hero": chips},
                    "eliminated_at": {}, "hero_observed_win": False, "censored_survivor": True}
        rows = []
        for n in (5, 6):
            for group in range(3):
                tables = [table(arm, rotation, 800 + (100 if arm == "v8d" else 0))
                          for rotation in range(n) for arm in ("v2", "v8d")]
                rows.append({"job": ["session", "test", n, group], "sessions": tables})
        result = experiment.paired_report(rows, "v8d", "v2", 1, 100)
        self.assertEqual(result["final_chips"]["diff"], 100)
        self.assertEqual(result["final_chips"]["ci97_5_primary"], [100, 100])
        self.assertEqual(result["elim_24"]["upper97_5_one_sided"], 0)


if __name__ == "__main__":
    unittest.main()

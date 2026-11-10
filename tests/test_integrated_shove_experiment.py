from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import integrated_shove_experiment as experiment
from scripts import competition_experiment as executor


class IntegratedShoveExperimentTests(unittest.TestCase):
    def small_plan(self):
        plan = experiment.protocol("integrated-unit-test-20261029")
        plan.update(players=[2], depths_bb=[4], scenarios={"pressure": ["pressure"]},
                    phases={"pilot": {"blocks": 1, "session_groups": 0},
                            "comparison": {"blocks": 2, "session_groups": 1}})
        plan["session"].update(scenarios=["pressure"], hand_limit=3)
        for config in plan["configs"].values():
            config.update(samples=32, budget_ms=1600)
        return plan

    def test_phases_share_frozen_parameters_and_have_disjoint_decks(self):
        plan = self.small_plan()
        pilot, comparison = (experiment.phase_plan(plan, phase) for phase in plan["phases"])
        self.assertNotEqual(pilot["experiment_id"], comparison["experiment_id"])
        self.assertEqual(pilot["configs"], comparison["configs"])
        self.assertEqual(pilot["arms"], comparison["arms"])
        self.assertEqual(len(experiment.planned_decks(plan)), 6)
        self.assertFalse(plan["criteria"]["default"].startswith("Promote"))

    def test_real_tiny_reset_pairs_all_versions_and_summary_requires_complete_matrix(self):
        plan = self.small_plan()
        settings = experiment.phase_plan(plan, "pilot")
        job = ("reset", "pressure", 2, 4)
        with tempfile.TemporaryDirectory(dir=experiment.old.BASE / ".tmp") as temp:
            root = Path(temp)
            (root / "pilot").mkdir()
            folder = root / "pilot"
            row = executor.execute_reset(folder, settings, "unit-digest", job)
            executor.save(folder / (executor.job_name(job) + ".json"), row)
            with patch.object(experiment, "load", return_value=(plan, "unit-digest")):
                result = experiment.summarize(root, "pilot")
                self.assertEqual(result["reset_hand_executions"], 12)
                self.assertEqual(len(result["contrasts"]), 15)
                self.assertTrue(result["technical_passed"])
                from scripts import audit_integrated_shove as auditor
                import importlib
                api = {name: importlib.import_module("pokerfight." + name)
                       for name in ("arena", "domain", "strategy")}
                with patch.object(auditor, "snapshot_api", return_value=api):
                    self.assertTrue(auditor.audit(root, "pilot", replay=False)["passed"])
                    changed = deepcopy(result)
                    changed["descriptive"]["v2"]["reset_bb_per_hand"] += 1
                    executor.save(folder / "summary.json", changed)
                    with self.assertRaisesRegex(ValueError, "Summary reset mean differs"):
                        auditor.audit(root, "pilot", replay=False)
                    executor.save(folder / "summary.json", result)
                trace = folder / (executor.job_name(job) + ".jsonl")
                records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
                for rotation in range(2):
                    selected = [item for item in records if item["rotation"] == rotation]
                    self.assertEqual({item["variant"] for item in selected}, set(experiment.ARMS))
                    self.assertEqual(len({item["deck_seed"] for item in selected}), 1)
                    self.assertEqual(len({json.dumps(item["policy_seeds"], sort_keys=True) for item in selected}), 1)
                trace.write_text(trace.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Trace changed"):
                    experiment.summarize(root, "pilot")

    def test_snapshot_and_protocol_tampering_fail_closed(self):
        plan = self.small_plan()
        plan["sources"] = {"pokerfight/test.py": "not-a-hash"}
        with tempfile.TemporaryDirectory(dir=experiment.old.BASE / ".tmp") as temp:
            root = Path(temp)
            (root / "source" / "pokerfight").mkdir(parents=True)
            (root / "source" / "pokerfight" / "test.py").write_text("pass\n", encoding="utf-8")
            executor.save(root / "protocol.json", plan)
            import hashlib
            digest = hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
            (root / "protocol.sha256").write_text(digest, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                experiment.load(root)
            (root / "protocol.sha256").write_text("wrong", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "protocol changed"):
                experiment.load(root)


if __name__ == "__main__":
    unittest.main()

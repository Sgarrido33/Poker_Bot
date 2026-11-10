"""Small integration checks for paired quality experiment construction."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.quality_experiment as experiment


class QualityExperimentTests(unittest.TestCase):
    def test_tiny_cell_pairs_decks_seeds_seats_and_fixes_rival_quota(self):
        plan = experiment.protocol("quality-test")
        plan["phases"]["pilot"]["namespace"] = "quality-test:pilot"
        plan["phases"]["pilot"]["blocks"] = 1
        plan["samples"] = 128
        plan["rival_samples"] = 16
        calls = []
        real_make_policy = experiment.make_policy

        def capture_make_policy(kind, config, seed):
            calls.append({"kind": kind, "samples": config.samples,
                          "budget_ms": config.budget_ms, "seed": seed})
            return real_make_policy(kind, config, seed)

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".tmp") as temp, patch.object(
                experiment, "make_policy", side_effect=capture_make_policy):
            root = Path(temp)
            experiment.cell(root, plan, "pilot", "copies_v2", 2, 4)
            rows = [json.loads(line) for line in
                    (root / "pilot" / "cell_copies_v2_2p_4bb.jsonl").read_text(encoding="utf-8").splitlines()]
            report = json.loads((root / "pilot" / "cell_copies_v2_2p_4bb.json").read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 1 * 2 * len(experiment.VARIANTS))
        grouped = {}
        for row in rows:
            grouped.setdefault((row["block"], row["rotation"]), []).append(row)
        self.assertEqual(len(grouped), 2)
        for paired in grouped.values():
            self.assertEqual({row["variant"] for row in paired}, set(experiment.VARIANTS))
            self.assertEqual(len({row["deck_seed"] for row in paired}), 1)
            self.assertEqual(len({tuple(row["seats"]) for row in paired}), 1)
            self.assertEqual(len({json.dumps(row["policy_seeds"], sort_keys=True) for row in paired}), 1)

        # One opponent policy is reconstructed for each arm and rotation; its
        # requested sample quota and time budget stay fixed across candidates.
        rival_calls = [call for call in calls if call["samples"] == plan["rival_samples"]]
        self.assertEqual(len(rival_calls), len(experiment.VARIANTS) * 2)
        self.assertTrue(all(call["budget_ms"] == 1600 for call in rival_calls))
        self.assertEqual(report["rival_config"]["samples"], plan["rival_samples"])

    def test_protocol_uses_disjoint_phase_namespaces_and_rejects_source_changes(self):
        plan = experiment.protocol("quality-test")
        self.assertNotEqual(plan["phases"]["pilot"]["namespace"],
                            plan["phases"]["validation"]["namespace"])
        with patch.object(experiment, "environment", return_value={"source_sha256": "changed"}):
            with self.assertRaisesRegex(ValueError, "Código cambió"):
                experiment.verify(plan)


if __name__ == "__main__":
    unittest.main()

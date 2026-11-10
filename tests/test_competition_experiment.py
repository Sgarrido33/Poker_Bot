import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.competition_experiment as experiment

TEMP = Path(__file__).resolve().parents[1] / ".tmp"


@unittest.skipUnless(importlib.util.find_spec("numpy"), "install requirements-evaluation.txt")
class CompetitionExperimentTests(unittest.TestCase):
    def small_plan(self):
        plan = experiment.protocol("technical-test-only")
        plan.update(arms=["v2", "v4", "v4rb", "v5"], blocks=1, players=[5], depths_bb=[8], scenarios={"external_mix": ["fullhouse", "v2", "pressure"]})
        for config in plan["configs"].values():
            config["samples"] = 128
        plan["rival_config"]["samples"] = 32
        plan["session"].update(groups=1, hand_limit=3, scenarios=["external_mix"])
        return plan

    def test_fixed_rival_quota_decks_and_all_seats(self):
        plan = self.small_plan()
        calls = []
        original = experiment.make_policy

        def capture(kind, config, seed):
            calls.append((kind, config.samples, config.budget_ms, seed))
            return original(kind, config, seed)

        with tempfile.TemporaryDirectory(dir=TEMP) as temp, patch.object(experiment, "make_policy", side_effect=capture):
            root = Path(temp)
            row = experiment.execute_reset(root, plan, "digest", ("reset", "external_mix", 5, 8))
            records = [json.loads(s) for s in (root / "reset_external_mix_5p_8.jsonl").read_text().splitlines()]
            experiment.check_artifact(root, plan, "digest", ("reset", "external_mix", 5, 8), row)
        self.assertEqual(len(records), 20)
        for rotation in range(5):
            paired = [r for r in records if r["rotation"] == rotation]
            self.assertEqual({r["variant"] for r in paired}, set(plan["arms"]))
            for field in ("deck_seed", "policy_seeds", "seats"):
                self.assertEqual(len({json.dumps(r[field], sort_keys=True) for r in paired}), 1)
        rivals = [c for c in calls if c[1] == 32]
        self.assertEqual(len(rivals), 80)
        self.assertEqual({c[2] for c in rivals}, {1600})
        self.assertEqual({r["rotation"] for r in records}, set(range(5)))

    def test_sessions_censor_and_pair_without_inventing_wins(self):
        plan = self.small_plan()
        plan["session"]["hand_limit"] = 1
        plan["session"]["starting_stack"] = 10000
        with tempfile.TemporaryDirectory(dir=TEMP) as temp:
            row = experiment.execute_sessions(Path(temp), plan, "digest", ("session", "external_mix", 5, 0))
            experiment.check_artifact(Path(temp), plan, "digest", ("session", "external_mix", 5, 0), row)
        for r in row["sessions"]:
            self.assertEqual(sum(r["last_stacks"].values()), 50000)
            if r["censored_survivor"]:
                self.assertIsNone(r["hero_rank"])
                self.assertFalse(r["hero_observed_win"])
        self.assertTrue(any(r["censored_survivor"] for r in row["sessions"]))
        self.assertEqual(experiment.paired_sessions([row], "v4", lambda r: 1), [[0.0]])

    def test_protocol_and_source_mutations_and_incomplete_batches_rejected(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as temp:
            root = Path(temp)
            experiment.register(root, "protocol-integrity-test")
            plan, digest = experiment.load_plan(root)
            experiment.verify(plan)
            with patch.object(experiment, "sources", return_value={}):
                with self.assertRaisesRegex(ValueError, "changed since registration"):
                    experiment.verify(plan)
            with self.assertRaisesRegex(ValueError, "Incomplete campaign"):
                experiment.summarize(root, plan, digest)
            (root / "protocol.json").write_bytes((root / "protocol.json").read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "protocol changed"):
                experiment.load_plan(root)

    def test_intervals_cluster_rotations_not_hands_and_namespaces_are_distinct(self):
        plan = self.small_plan()
        plan["inference"]["bootstrap_repetitions"] = 200
        self.assertEqual(experiment.interval([[1, 1], [3, 3]], 8, plan), [2, 2])
        self.assertIsNone(experiment.interval([[1]], 8, plan))
        a, b = experiment.protocol("fresh-A"), experiment.protocol("fresh-B")
        self.assertNotEqual(a["experiment_id"], b["experiment_id"])
        self.assertFalse(a["criteria"]["default"].find("retain v2") == -1)


if __name__ == "__main__":
    unittest.main()

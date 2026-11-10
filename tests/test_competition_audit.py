"""Independent audit falsification checks, added without changing game code."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from research.competition_audit_20261028.audit_sessions import canonical_trace, reconstruct
from scripts.competition_experiment import execute_sessions, protocol


@unittest.skipUnless(importlib.util.find_spec("numpy"), "install requirements-evaluation.txt")
class SessionAuditTests(unittest.TestCase):
    def test_trace_json_normalization_preserves_decisions_and_numbers(self):
        trace = ({"observation": {"hole_cards": ("As", "Ah")},
                  "decision": {"action": {"kind": "call"}, "elapsed_ms": 20.0,
                               "equity": {"equity": 0.625}}},)
        decoded = json.loads(json.dumps(trace))
        self.assertEqual(canonical_trace(trace), canonical_trace(decoded))
        decoded[0]["decision"]["equity"]["equity"] = 0.624
        self.assertNotEqual(canonical_trace(trace), canonical_trace(decoded))

    def test_reconstruct_and_reject_broken_stack_transition_and_missing_hand(self):
        plan = protocol("independent-audit-technical-check")
        for cfg in plan["configs"].values():
            cfg["samples"] = 128
        plan["rival_config"]["samples"] = 32
        plan["session"]["hand_limit"] = 2
        job = ("session", "external_mix", 5, 0)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".tmp") as tmp:
            report = execute_sessions(Path(tmp), plan, "technical", job)
            lines = (Path(tmp) / "session_external_mix_5p_0.jsonl").read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        expected = reconstruct(plan, job, records)
        self.assertEqual(expected, {(r["variant"], r["rotation"]): r for r in report["sessions"]})
        broken = json.loads(json.dumps(records))
        pid = next(iter(broken[0]["stacks"]))
        broken[0]["stacks"][pid] += 1
        with self.assertRaisesRegex(ValueError, "stack transition"):
            reconstruct(plan, job, broken)
        pair = (records[0]["variant"], records[0]["rotation"])
        missing = [r for r in records if (r["variant"], r["rotation"]) != pair or r["hand"] != 0]
        with self.assertRaisesRegex(ValueError, "session hand"):
            reconstruct(plan, job, missing)


if __name__ == "__main__":
    unittest.main()

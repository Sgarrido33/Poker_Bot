"""Adversarial checks for the stage-two independent audit helpers."""
from collections import Counter
import unittest

from pokerfight.arena import seed_for
from scripts.audit_competition_stage2 import expected_reset, fixed_horizon_elimination


def reset_fixture():
    plan = {"experiment_id": "stage2-audit-test", "scenarios": {"x": ["calling"]},
            "arms": ["v2", "v2_4000"], "blocks": 2}
    job = ("reset", "x", 2, 8)
    ids = ("hero", "opponent_1")
    base = seed_for(plan["experiment_id"], "crossplay-reset-01", "x", 2, 8)
    records = []
    for block in range(plan["blocks"]):
        for rotation in range(2):
            for arm in plan["arms"]:
                initial = 800
                hero_delta = 100 if arm == "v2_4000" else -100
                payoffs = {"hero": hero_delta, "opponent_1": -hero_delta}
                stacks = {pid: initial + payoffs[pid] for pid in ids}
                records.append({"block": block, "rotation": rotation, "variant": arm,
                                "seats": list(ids[rotation:] + ids[:rotation]),
                                "policy_seeds": {pid: seed_for(base, "policy", block, rotation, pid) for pid in ids},
                                "deck_seed": seed_for(base, "deck", block), "payoffs": payoffs,
                                "stacks": stacks, "counts": {"decisions": 1},
                                "reasons": {"hero:call": 1}, "hero_actions": {"call": 1}})
    gains = {arm: [(-1.0 if arm == "v2" else 1.0)] * plan["blocks"] for arm in plan["arms"]}
    report = {"block_bb_per_hand": gains, "bust_hands": {arm: 0 for arm in plan["arms"]},
              "counts": {arm: {"decisions": 4} for arm in plan["arms"]},
              "reasons": {arm: {"hero:call": 4} for arm in plan["arms"]},
              "hero_actions": {arm: {"call": 4} for arm in plan["arms"]}, "executions": 8}
    return plan, job, records, report


class Stage2AuditTests(unittest.TestCase):
    def test_exact_reset_cartesian_coverage_accepts_complete_fixture(self):
        plan, job, records, report = reset_fixture()
        result = expected_reset(plan, job, records, report)
        self.assertEqual(result["groups"], 4)
        self.assertEqual(result["records"], 8)

    def test_reset_rejects_missing_and_duplicated_pairs(self):
        plan, job, records, report = reset_fixture()
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            expected_reset(plan, job, records[:-1], {**report, "executions": 7})
        duplicated = records + [dict(records[0])]
        with self.assertRaisesRegex(ValueError, "Duplicate reset"):
            expected_reset(plan, job, duplicated, {**report, "executions": 9})

    def test_reset_rejects_seed_mismatch_even_if_pairing_is_preserved(self):
        plan, job, records, report = reset_fixture()
        changed = [dict(r) for r in records]
        changed[0]["deck_seed"] += 1
        with self.assertRaisesRegex(ValueError, "deck seed mismatch"):
            expected_reset(plan, job, changed, report)
        changed = [dict(r) for r in records]
        changed[0]["deck_seed"] = str(changed[0]["deck_seed"])
        with self.assertRaisesRegex(ValueError, "deck seed mismatch"):
            expected_reset(plan, job, changed, report)

    def test_fixed_horizon_keeps_win_competing_and_survivor_alive(self):
        plan = {"arms": ["v2", "v2_4000"], "scenarios": {"x": ["calling"]},
                "session": {"hand_limit": 64, "starting_stack": 800}}
        completed = [{"variant": "v2", "rotation": 0, "hand": h,
                      "stacks": {"hero": 800, "opponent_1": 0, "opponent_2": 0}} for h in range(6)]
        alive = [{"variant": "v2_4000", "rotation": 0, "hand": h,
                  "stacks": {"hero": 500, "opponent_1": 200, "opponent_2": 100}} for h in range(24)]
        eliminated = [{"variant": "v2_4000", "rotation": 1, "hand": h,
                       "stacks": {"hero": 0 if h >= 10 else 800,
                                  "opponent_1": 400,
                                  "opponent_2": 400}}
                      for h in range(24)]
        metrics = fixed_horizon_elimination(
            plan, [{"job": ("session", "x", 3, 0), "records": completed + alive + eliminated}])
        self.assertEqual(metrics["v2"]["24"]["table_finished_hero_alive"], 1)
        self.assertEqual(metrics["v2_4000"]["24"]["alive_through_horizon"], 1)
        self.assertEqual(metrics["v2_4000"]["24"]["eliminated"], 1)
        self.assertEqual(metrics["v2_4000"]["24"]["tables"], 2)

    def test_eliminated_hero_is_carried_forward_when_later_rows_omit_hero(self):
        plan = {"arms": ["v2"], "scenarios": {"x": ["calling"]},
                "session": {"hand_limit": 64, "starting_stack": 800}}
        rows = []
        for hand in range(24):
            stacks = {"hero": 800 if hand == 0 else 0,
                      "opponent_1": 600, "opponent_2": 600, "opponent_3": 600}
            if hand >= 2:
                stacks.pop("hero")
            rows.append({"variant": "v2", "rotation": 0, "hand": hand, "stacks": stacks})
        metrics = fixed_horizon_elimination(
            plan, [{"job": ("session", "x", 4, 0), "records": rows}])
        self.assertEqual(metrics["v2"]["24"]["eliminated"], 1)
        self.assertEqual(metrics["v2"]["24"].get("alive_through_horizon", 0), 0)


if __name__ == "__main__":
    unittest.main()

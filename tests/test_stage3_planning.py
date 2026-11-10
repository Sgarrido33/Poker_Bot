import unittest
import json
from pathlib import Path
import shutil
import tempfile

from scripts.plan_competition_stage3 import (
    build_plan,
    detectable_effect,
    load_primary_groups,
    required_groups,
    _event,
    EXPERIMENT_ID,
    seed_for,
)


class Stage3PlanningTests(unittest.TestCase):
    TEST_EXPERIMENT_ID = "crossplay-stage3-unit-test-seedguard-20261028-01"

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory(prefix="stage3-planning-test-", dir=Path(".tmp"))
        root = Path(cls._temp.name)
        cls.source = root / "stage2"
        cls.source.mkdir()
        original = Path("results/competition_stage2_2026-10-28")
        for n in (5, 6):
            for group in range(4):
                name = f"session_external_diverse_{n}p_{group}.json"
                shutil.copy2(original / name, cls.source / name)

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def build_test_plan(self, **kwargs):
        return build_plan(source=self.source, experiment_id=self.TEST_EXPERIMENT_ID, **kwargs)

    def test_uses_complete_group_as_independent_unit_and_balances_formats(self):
        observed, hashes = load_primary_groups(Path("results/competition_stage2_2026-10-28"))
        self.assertEqual(8, len(hashes))
        self.assertEqual([4, 4], [len(observed["contrasts"]["v4"]["chips"][n]) for n in (5, 6)])

    def test_controls_are_retained_but_nonconfirmatory(self):
        plan = self.build_test_plan()
        cfg = plan["proposed_configurable_protocol"]
        self.assertEqual(["external_diverse"], [cfg["primary"]["scenario"]])
        self.assertEqual(["pressure", "copies_v2", "copies_v2_4000", "external_mix"], cfg["controls"]["scenarios"])
        self.assertEqual(40, cfg["primary"]["groups_per_format"])
        self.assertEqual(8, cfg["controls"]["groups_per_format_each"])
        self.assertIn("exploratory", cfg["controls"]["purpose"])

    def test_v6_is_the_only_two_endpoint_confirmatory_contrast(self):
        plan = self.build_test_plan()
        self.assertEqual(2, plan["multiplicity_and_decision"]["primary_tests"])
        self.assertIn("v6 versus v2 only", plan["inference_target"])
        self.assertIn("v4/v4rb/v5 contrasts exploratory", plan["proposed_configurable_protocol"]["primary"]["purpose"])
        self.assertIn("v4rb", plan["v6_experimental_configuration"]["parent_policy"])
        self.assertIn("pre-search local baseline action", plan["v6_experimental_configuration"]["isolated_change"])
        self.assertIn("not the final output of a full v4rb run", plan["v6_experimental_configuration"]["baseline_semantics"])
        self.assertEqual({"samples": 4096, "budget_ms": 3500, "matches": "v4rb"}, plan["v6_experimental_configuration"]["hero_profile"])

    def test_campaign_is_planning_only_and_sized_by_scenario_groups(self):
        plan = self.build_test_plan()
        cfg = plan["proposed_configurable_protocol"]
        self.assertEqual("planning_only_not_registered_not_executed", plan["status"])
        self.assertEqual(144, cfg["groups_total_across_scenarios_and_formats"])
        self.assertEqual(2200, cfg["primary_tables_maximum"])
        self.assertEqual(1760, cfg["control_tables_maximum"])
        self.assertEqual(3960, cfg["tables_maximum"])
        self.assertEqual(506880, cfg["hand_executions_maximum"])

    def test_seed_allocation_is_new_and_collision_free(self):
        plan = self.build_test_plan()
        seed_info = plan["fixed_seed_policy"]
        self.assertEqual(self.TEST_EXPERIMENT_ID, seed_info["experiment_id"])
        self.assertEqual(18432, seed_info["planned_unique_deck_seed_count"])
        self.assertEqual(0, seed_info["overlap_count"])
        self.assertIn("external_mix", seed_info["group_seeds_by_scenario_and_format"])
        self.assertEqual(seed_for(self.TEST_EXPERIMENT_ID, "inference-bootstrap"),
                         plan["planned_interval_method"]["bootstrap_seed"])

    def test_two_strata_standard_error_has_sqrt_two_gain(self):
        from math import ceil, sqrt
        from statistics import NormalDist

        sd5 = sd6 = .2
        proxy = sqrt((sd5**2 + sd6**2) / 2)
        z = NormalDist().inv_cdf(1 - .05 / (2 * 2)) + NormalDist().inv_cdf(.80)
        expected = ceil((z * proxy / (sqrt(2) * .1)) ** 2)
        self.assertEqual(expected, required_groups(proxy, .1, family_alpha=.05, comparisons=2, power=.80))

    def test_early_bust_is_counted_by_hero_elimination_time_not_table_end(self):
        row = {"hero_eliminated": True, "played_hands": 128, "eliminated_at": {"hero": 2},
               "hero_observed_win": False, "table_finished": False}
        result = _event(row, 24)
        self.assertEqual(1, result["bust"])
        self.assertEqual(0, result["unresolved"])
        self.assertEqual(0, result["table_finished"])

    def test_chips_sizing_rejects_unavailable_earlier_horizon(self):
        with self.assertRaisesRegex(ValueError, "last_stacks at 128"):
            self.build_test_plan(horizon=64)

    def test_seed_guard_rejects_fixture_collision_but_fresh_test_id_passes(self):
        with tempfile.TemporaryDirectory(prefix="stage3-seed-fixture-", dir=Path(".tmp")) as temp:
            root = Path(temp)
            source = root / "stage2"
            source.mkdir()
            original = Path("results/competition_stage2_2026-10-28")
            for n in (5, 6):
                for group in range(4):
                    name = f"session_external_diverse_{n}p_{group}.json"
                    shutil.copy2(original / name, source / name)
            base = seed_for(EXPERIMENT_ID, "crossplay-session-01", "external_diverse", 5, 0)
            colliding_deck = seed_for(base, "deck", 0)
            (root / "history.jsonl").write_text(json.dumps({"deck_seed": colliding_deck}) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "overlap"):
                build_plan(source=source)
            fresh = build_plan(source=source, experiment_id=self.TEST_EXPERIMENT_ID)
            self.assertEqual(0, fresh["fixed_seed_policy"]["overlap_count"])

    def test_sizing_scales_with_effect_size_and_group_count(self):
        self.assertGreater(required_groups(.8, .05), required_groups(.8, .10))
        self.assertLess(detectable_effect(.8, 80), detectable_effect(.8, 20))

    def test_missing_group_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            load_primary_groups(Path("results/.missing_stage3_plan_input"))


if __name__ == "__main__":
    unittest.main()

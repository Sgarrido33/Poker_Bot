from dataclasses import asdict
import unittest
from unittest.mock import patch

from pokerfight import cli
from pokerfight.evaluation import evaluate
from pokerfight.strategy import BotConfig


class ComparisonConfigTests(unittest.TestCase):
    def test_real_comparison_keeps_candidate_control_and_rival_compute_separate(self):
        from pokerfight import evaluation
        calls = []
        real = evaluation.make_policy

        def record(kind, config, seed):
            calls.append((kind, config.samples, config.budget_ms, seed))
            return real(kind, config, seed)

        candidate, control, rival = BotConfig(32, 3500), BotConfig(64, 1600), BotConfig(16, 1600)
        with patch.object(evaluation, "make_policy", side_effect=record):
            result = evaluate(2, 1, 1, 29, candidate, ("v2",), "v2", "v7",
                              starting_stack=800, experiment_id="comparison-config-unit",
                              rival_config=rival, baseline_config=control)
        self.assertEqual(sum(kind == "v7" and samples == 32 and budget == 3500
                             for kind, samples, budget, seed in calls), 2)
        self.assertEqual(sum(kind == "v2" and samples == 64 for kind, samples, budget, seed in calls), 2)
        self.assertEqual(sum(kind == "v2" and samples == 16 for kind, samples, budget, seed in calls), 4)
        self.assertEqual(result["baseline_config"], asdict(control))
        self.assertEqual(result["rival_samples"], 16)
        self.assertEqual(result["fallbacks_all_policies"], 0)

    def test_cli_extended_candidate_defaults_to_valid_frozen_control_and_rivals(self):
        with patch.object(cli, "evaluate", return_value={}) as compare, \
             patch.object(cli, "environment", return_value={}), patch.object(cli, "output"):
            cli.main(["evaluate", "--players", "2", "--blocks", "1", "--hands-per-block", "1",
                      "--hero", "v7", "--baseline", "v2", "--opponents", "v2"])
        candidate = compare.call_args.args[4]
        self.assertEqual((candidate.samples, candidate.budget_ms), (1024, 3500))
        for key in ("baseline_config", "rival_config"):
            config = compare.call_args.kwargs[key]
            self.assertEqual((config.samples, config.budget_ms), (4000, 1600))

    def test_explicit_control_and_rival_profiles_are_respected(self):
        with patch.object(cli, "evaluate", return_value={}) as compare, \
             patch.object(cli, "environment", return_value={}), patch.object(cli, "output"):
            cli.main(["evaluate", "--players", "2", "--hero", "v7", "--baseline", "v2",
                      "--samples", "64", "--baseline-samples", "128", "--baseline-budget-ms", "1700",
                      "--rival-samples", "16", "--rival-budget-ms", "1500"])
        self.assertEqual(compare.call_args.args[4].samples, 64)
        control, rival = (compare.call_args.kwargs[key] for key in ("baseline_config", "rival_config"))
        self.assertEqual((control.samples, control.budget_ms), (128, 1700))
        self.assertEqual((rival.samples, rival.budget_ms), (16, 1500))


if __name__ == "__main__":
    unittest.main()

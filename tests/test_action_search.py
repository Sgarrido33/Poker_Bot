from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import random
import sys
import tempfile
from time import perf_counter
import unittest
from unittest.mock import patch

from pokerfight.action_model import PRIORS, PreparedAction, call_probability, candidate_actions, showdown_return
from pokerfight.action_search import ActionSearchBot, Moments, search
from pokerfight.arena import make_policy, play_hand
from pokerfight.cards import CARD_INDEX
from pokerfight.domain import Action, LegalActions, Observation, Player
from pokerfight.domain import PublicAction
from pokerfight.equity import WeightedRange, build_ranges
from pokerfight.opponents import OpponentModel
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases, opening

ROOT = Path(__file__).resolve().parents[1]


class ActionValueTests(unittest.TestCase):
    def test_side_pots_dead_money_ties_and_unmatched_returns(self):
        self.assertEqual(showdown_return([150, 100, 300, 100], [False, False, False, True], [2, 1, 0, 9], 0), 500)
        self.assertEqual(showdown_return([100, 100, 300], [False] * 3, [2, 2, 0], 0), 150)
        self.assertEqual(showdown_return([800, 100], [False, True], [1, 9], 0), 900)
        self.assertEqual(showdown_return([150, 100, 300], [False] * 3, [1, 2, 0], 0), 100)

    def test_fold_zero_and_winning_without_callers_collects_existing_pot(self):
        obs = opening(2, 8, "BTN", ("As", "Ah"))
        push = PreparedAction(obs, Action("raise_to", 800), {})
        self.assertEqual(push.value([1, 9], [.9, .9], [1, 1], PRIORS[0]), obs.pot)
        self.assertEqual(PreparedAction(obs, Action("fold"), {}).value([1, 9], [.9, .9], [0, 0], PRIORS[0]), 0)

    def test_public_all_in_players_cannot_be_folded_by_response_model(self):
        obs = Observation("t", "h", "hero", 1,
            (Player("hero", 100, 100, 100), Player("v", 0, 200, 200)),
            ("As", "Ah"), (), 100, LegalActions(False, True, 100))
        arm = PreparedAction(obs, Action("call"), {})
        self.assertEqual(arm.value([0, 1], [.9, .1], [1, 1], PRIORS[0]), -100)

    def test_response_prior_monotonicity_and_positive_support(self):
        for prior in PRIORS:
            self.assertLess(call_probability(.3, .3, prior), call_probability(.9, .3, prior))
            self.assertGreater(call_probability(.7, .1, prior), call_probability(.7, .45, prior))
            self.assertTrue(0 < call_probability(0, 1, prior) < 1)
        self.assertLess(call_probability(.65, .25, PRIORS[0]), call_probability(.65, .25, PRIORS[2]))

    def test_legal_unique_candidates_do_not_open_limp(self):
        obs = opening()
        arms = candidate_actions(obs, Action("fold"))
        self.assertNotIn(Action("call"), arms)
        self.assertTrue(all(a.is_legal(obs) for a in arms))
        self.assertEqual(len(arms), len(set(arms)))
        obs = replace(obs, legal=LegalActions(False, True, 100))
        self.assertFalse(any(a.kind == "raise_to" for a in candidate_actions(obs, Action("fold"))))

    def test_paired_difference_with_identical_worlds_has_zero_variance(self):
        moments = Moments()
        for _ in range(100):
            moments.add(7)
        self.assertEqual(moments.mean, 7)
        self.assertEqual(moments.se, 0)

    def test_search_reproducible_and_respects_hard_work_cap(self):
        obs = opening(3, 4, "BTN", ("As", "Ah"))
        model = OpponentModel()
        ranges = build_ranges(obs, model, math.inf)
        a = search(obs, ranges, model, Action("fold"), random.Random(19), 512, math.inf)
        b = search(obs, ranges, model, Action("fold"), random.Random(19), 512, math.inf)
        self.assertEqual(a, b)
        self.assertEqual(a[1]["worlds"], 512)
        self.assertNotEqual(a[0].kind, "fold")
        self.assertEqual(a[1]["priors"], [p.name for p in PRIORS])
        self.assertNotIn("hole_cards", json.dumps(a[1]))

    def test_expired_search_keeps_legal_base_without_using_partial_worlds(self):
        obs = opening()
        model = OpponentModel()
        ranges = build_ranges(obs, model, math.inf)
        action, info = search(obs, ranges, model, Action("fold"), random.Random(1), 512, 0)
        self.assertEqual(action, Action("fold"))
        self.assertEqual(info["stop"], "deadline_keep_v2")
        self.assertEqual(info["worlds"], 0)
        json.dumps(info, allow_nan=False)

    def test_exhausted_collision_attempts_keep_baseline_with_partial_worlds(self):
        obs = opening(3, 8, "BTN", ("As", "Ah"))

        class RareCompatibleRange:
            def __init__(self):
                self.attempts = 0

            def draw(self, rng):
                self.attempts += 1
                return (2, 3) if self.attempts in (1, 5001) else (0, 2)

        ranges = {"1": WeightedRange.create([((0, 1), 1)]), "2": RareCompatibleRange()}
        # Two winning worlds have a zero observed SE, but do not complete the
        # requested quota. Exhausting the collision guard is not sample_cap.
        with patch("pokerfight.action_search.eval7.evaluate", side_effect=[2, 1, 1] * 2), \
             patch("pokerfight.action_model.call_probability", return_value=1.0):
            action, info = search(obs, ranges, OpponentModel(), Action("fold"),
                                  random.Random(19), 64, math.inf)
        self.assertEqual(info["worlds"], 2)
        self.assertEqual(info["attempts"], 10000)
        self.assertEqual(info["stop"], "incompatible_ranges_keep_v2")
        self.assertEqual(action, Action("fold"))
        self.assertFalse(info["changed"])


class SearchPolicyTests(unittest.TestCase):
    def test_old_control_is_unchanged_and_mc_control_only_extends_envelope(self):
        verify_control()
        obs = opening(hole=("As", "Ah"))
        a = make_policy("v2", BotConfig(samples=128), 17).decide(obs)
        b = make_policy("v2mc", BotConfig(samples=128, budget_ms=3500), 17).decide(obs)
        self.assertEqual(a.action, b.action)
        self.assertEqual(a.equity, b.equity)

    def test_all_in_price_regression_bypasses_search(self):
        obs = cases()["cheap_all_in_regression"]
        bot = ActionSearchBot(BotConfig(samples=128, budget_ms=3500))
        with patch("pokerfight.action_search.search", side_effect=AssertionError("must bypass")):
            result = bot.decide(obs)
        self.assertEqual(result.action, Action("call"))
        self.assertFalse(result.fallback)

    def test_postflop_and_deep_preflop_match_mc_control_exactly(self):
        for obs in (opening(depth=20, hole=("As", "Ah")),
                    replace(opening(hole=("As", "Ah")), board=("2c", "3d", "4h"))):
            config = BotConfig(samples=128, budget_ms=3500)
            a = make_policy("v4", config, 19).decide(obs)
            b = make_policy("v2mc", config, 19).decide(obs)
            self.assertEqual(a.action, b.action)
            self.assertEqual(a.equity, b.equity)
            self.assertIsNone(a.search)

    def test_search_exception_returns_computed_baseline_and_reports_fallback(self):
        obs = opening(hole=("As", "Ah"))
        with patch("pokerfight.action_search.search", side_effect=RuntimeError("search error")):
            result = make_policy("v4", BotConfig(samples=128), 19).decide(obs)
        self.assertTrue(result.fallback)
        self.assertEqual(result.action, make_policy("v2", BotConfig(samples=128), 19).decide(obs).action)

    def test_complete_multiplayer_hands_conserve_chips_with_v4(self):
        for n in (2, 3, 4, 5, 6):
            ids = ("hero",) + tuple(str(i) for i in range(1, n))
            policies = {pid: make_policy("v4" if pid == "hero" else "v2mc", BotConfig(samples=128), i + 7)
                        for i, pid in enumerate(ids)}
            result = play_hand(policies, ids, dict.fromkeys(ids, 800), 43)
            self.assertEqual(sum(result.payoffs.values()), 0)
            self.assertFalse(any(d.fallback for _, d in result.decisions))


class SupervisorTests(unittest.TestCase):
    def test_stalled_worker_is_killed_and_returns_legal_action(self):
        command = [sys.executable, "-u", "-c",
            "import time; print('{\"ready\":true}',flush=True); time.sleep(10)"]
        with SupervisedPolicy(BotConfig(samples=128), timeout_ms=50, command=command) as bot:
            started = perf_counter()
            result = bot.decide(opening())
            self.assertLess(perf_counter() - started, .6)
            self.assertTrue(result.fallback)
            self.assertTrue(result.action.is_legal(opening()))
            self.assertIsNone(bot.process)

    def test_illegal_worker_action_is_not_sent_to_engine(self):
        code = "import sys,json; print('{\"ready\":true}',flush=True); r=json.loads(input()); print(json.dumps({'request_id':r['request_id'],'decision':{'action':{'kind':'raise_to','amount':1}}}),flush=True)"
        with SupervisedPolicy(BotConfig(samples=128), 500, [sys.executable, "-u", "-c", code]) as bot:
            result = bot.decide(opening())
            self.assertTrue(result.fallback)
            self.assertEqual(result.action.kind, "fold")

    def test_persistent_real_worker_matches_direct_policy(self):
        config = BotConfig(samples=128, budget_ms=3500)
        direct = make_policy("v4", config, config.seed)
        with SupervisedPolicy(config) as bot:
            process_id = bot.process.pid
            for obs in (cases()["cheap_all_in_regression"], opening(hole=("As", "Ah"))):
                a, b = bot.decide(obs), direct.decide(obs)
                self.assertEqual(a.action, b.action)
                self.assertEqual(a.equity, b.equity)
                self.assertEqual(a.search, b.search)
                self.assertFalse(a.fallback)
                self.assertEqual(bot.process.pid, process_id)

    def test_watchdog_also_covers_a_blocked_large_pipe_write(self):
        command = [sys.executable, "-u", "-c", "import time; print('{\"ready\":true}',flush=True); time.sleep(10)"]
        obs = opening()
        obs = replace(obs, history=tuple(PublicAction(str(i), "0", "preflop", "check") for i in range(4000)))
        with SupervisedPolicy(BotConfig(samples=128), 50, command) as bot:
            started = perf_counter()
            result = bot.decide(obs)
            self.assertLess(perf_counter() - started, .7)
            self.assertTrue(result.fallback)


class ThreeArmExperimentTests(unittest.TestCase):
    def test_original_third_arm_has_same_decks_and_replays_with_fixed_rival_quota(self):
        from pokerfight.action_experiment import original_arm
        from pokerfight.evaluation import environment, evaluate
        from pokerfight.replay import replay_worst
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            root = Path(directory)
            report = evaluate(2, 2, 1, 47, BotConfig(samples=4000), ("v2",), "v2mc", "v4",
                starting_stack=400, experiment_id="unit-third-arm", rival_config=BotConfig(samples=128))
            report.update(environment=environment(), scenario="copies_v2", depth_bb=4)
            original = original_arm(report, root / "original.jsonl")
            self.assertEqual(original["candidate_block_bb_per_hand"], report["baseline_block_bb_per_hand"])
            path = root / "original.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            self.assertTrue(replay_worst(str(path))["matched"])

    def test_new_protocol_separates_phases_and_refuses_environment_changes(self):
        from pokerfight.action_experiment import protocol, run
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            root = Path(directory)
            plan = protocol("unit-new-v4-id")
            self.assertNotEqual(plan["phases"]["pilot"]["namespace"], plan["phases"]["validation"]["namespace"])
            (root / "protocol.json").write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "piloto"):
                run(root, "validation")
            with patch("pokerfight.action_experiment.environment", return_value={}):
                with self.assertRaisesRegex(ValueError, "Código"):
                    run(root, "pilot")


if __name__ == "__main__":
    unittest.main()

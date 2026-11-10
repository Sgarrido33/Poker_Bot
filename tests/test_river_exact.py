from dataclasses import replace
import math
import random
import unittest
from unittest.mock import patch

from pokerfight.cards import CARD_INDEX
from pokerfight.controls import ControlBot
from pokerfight.domain import Action, LegalActions, Observation, Player, PublicAction
from pokerfight.equity import WeightedRange, estimate
from pokerfight.evaluation import latency
from pokerfight.river_exact import ExactRiverPolicy, estimate_river
from pokerfight.strategy import BotConfig, Decision, PokerBot


def river(hole=("As", "Ah"), board=("2c", "3d", "7h", "8s", "9c")):
    return Observation("table", "hand", "hero", 1,
        (Player("hero", 900, 0, 100), Player("villain", 900, 0, 100)),
        hole, board, 10, LegalActions(True, False, 0, 10, 900))


def weighted(*entries):
    return WeightedRange.create([((CARD_INDEX[a], CARD_INDEX[b]), w) for a, b, w in entries])


class ExactRiverEstimatorTests(unittest.TestCase):
    def test_weights_known_result_and_tiny_support(self):
        obs = river()
        ranges = {"villain": weighted(("Ks", "Kh", 1), ("6h", "Th", 3))}
        result = estimate_river(obs, ranges)
        self.assertEqual(result.equity, .25)
        self.assertEqual(result.expected_return, 50)
        self.assertEqual(result.eligible_pot, 200)
        self.assertEqual((result.samples, result.attempts), (2, 2))
        self.assertEqual(result.standard_error, 0)
        self.assertFalse(result.timed_out)
        mc = estimate(obs, ranges, random.Random(17), 12000)
        self.assertAlmostEqual(mc.equity, result.equity, delta=.015)

    def test_tie_and_probability_normalization(self):
        obs = river(("2d", "3d"), ("As", "Ks", "Qs", "Js", "Ts"))
        result = estimate_river(obs, {"villain": weighted(("4c", "5h", 1), ("4s", "6s", 3))})
        self.assertEqual(result.equity, .5)
        self.assertEqual(result.expected_return, 100)

    def test_dead_money_and_hero_only_refund_layer(self):
        obs = Observation("t", "h", "hero", 2,
            (Player("hero", 1, 0, 100), Player("villain", 0, 0, 50),
             Player("dead", 1, 0, 100, True)),
            ("Ks", "Kh"), river().board, 10, LegalActions(True, False, 0))
        result = estimate_river(obs, {"villain": weighted(("As", "Ah", 1))})
        self.assertEqual(result.equity, .4)
        self.assertEqual(result.expected_return, 100)
        self.assertEqual(result.eligible_pot, 250)

    def test_call_amount_caps_eligible_pots(self):
        obs = Observation("t", "h", "hero", 2,
            (Player("hero", 50, 0, 0), Player("villain", 0, 100, 100),
             Player("dead", 0, 100, 100, True)),
            ("As", "Ah"), river().board, 10, LegalActions(False, True, 50))
        result = estimate_river(obs, {"villain": weighted(("Ks", "Kh", 1))})
        self.assertEqual(result.equity, 1)
        self.assertEqual(result.eligible_pot, 150)
        self.assertEqual(result.expected_return, 150)

    def test_blockers_range_ids_and_scope_are_validated(self):
        obs = river()
        for ranges in ({}, {"other": weighted(("Ks", "Kh", 1))},
                       {"villain": weighted(("As", "Kh", 1))},
                       {"villain": weighted(("2c", "Kh", 1))}):
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                estimate_river(obs, ranges)
        ranges = {"villain": weighted(("Ks", "Kh", 1))}
        with self.assertRaises(ValueError):
            estimate_river(replace(obs, board=obs.board[:4]), ranges)
        multiway = replace(obs, players=obs.players + (Player("third", 900, 0, 100),))
        with self.assertRaises(ValueError):
            estimate_river(multiway, ranges)

    def test_invalid_cumulative_and_zero_effective_weight(self):
        pair = (CARD_INDEX["Ks"], CARD_INDEX["Kh"])
        for r in (WeightedRange((), ()), WeightedRange((pair,), ()),
                  WeightedRange((pair,), (math.inf,)),
                  WeightedRange((pair, pair), (2., 1.))):
            with self.subTest(r=r), self.assertRaises(ValueError):
                estimate_river(river(), {"villain": r})
        # Floating point cumulative sums may contain a zero-size increment.
        result = estimate_river(river(), {"villain": WeightedRange((pair, pair), (1., 1.))})
        self.assertEqual(result.equity, 1)

    def test_deadline_never_returns_partial_enumeration(self):
        ranges = {"villain": weighted(("Ks", "Kh", 1), ("6h", "Th", 3))}
        with self.assertRaises(TimeoutError):
            estimate_river(river(), ranges, 0)
        with patch("pokerfight.river_exact.perf_counter", side_effect=[0, 0, 2]), \
                self.assertRaises(TimeoutError):
            estimate_river(river(), ranges, 1)
        with self.assertRaises(ValueError):
            estimate_river(river(), ranges, math.nan)


class ExactRiverPolicyTests(unittest.TestCase):
    def test_select_receives_exact_small_support_and_observes_history(self):
        base = PokerBot(BotConfig(samples=4000))
        wrapper = ExactRiverPolicy(base)
        event = PublicAction("one", "villain", "river", "check")
        obs = replace(river(), history=(event,))
        with patch("pokerfight.river_exact.build_ranges", return_value={"villain": weighted(("Ks", "Kh", 1))}), \
                patch.object(base, "select", return_value=(Action("check"), "chosen")) as select:
            result = wrapper.decide(obs)
        self.assertFalse(result.fallback)
        self.assertEqual(result.equity.samples, 1)
        self.assertEqual(result.equity.standard_error, 0)
        self.assertEqual(result.reason, "exact_river:chosen")
        self.assertEqual(result.search["model"], "exact_heads_up_river")
        self.assertEqual(result.search["combos"], 1)
        self.assertFalse(result.search["changed"])
        self.assertEqual(result.search["stop"], "exact_enumeration")
        self.assertEqual(result.search["worlds"], 1)
        self.assertIs(select.call_args.args[1], result.equity)
        self.assertIs(wrapper.config, base.config)
        self.assertIs(wrapper.model, base.model)
        self.assertEqual(base.model.counts[("villain", "river", False)].n, 1)

    def test_arena_type_and_latency_metadata_remain_compatible(self):
        from types import SimpleNamespace
        wrapper = ExactRiverPolicy(PokerBot(BotConfig(samples=128)))
        # play_hand uses this type to observe final actions after hero's turn.
        self.assertIsInstance(wrapper, PokerBot)
        result = wrapper.decide(river())
        self.assertFalse(result.fallback)
        report = latency([SimpleNamespace(decisions=(("hero", result),))])
        self.assertEqual(report["search_stops"], {"exact_enumeration": 1})
        self.assertEqual(report["search_changes"], 0)
        self.assertEqual(report["search_worlds"], 990)

    def test_out_of_scope_delegates_exact_result_object(self):
        base = PokerBot(BotConfig(samples=128))
        wrapper = ExactRiverPolicy(base)
        sentinel = Decision(Action("check"), "sentinel", 0, False)
        cases = (replace(river(), board=river().board[:4]),
                 replace(river(), players=river().players + (Player("third", 900, 0, 100),)))
        for obs in cases:
            with self.subTest(obs=obs), patch.object(base, "decide", return_value=sentinel) as decide:
                self.assertIs(wrapper.decide(obs), sentinel)
                decide.assert_called_once_with(obs)

    def test_errors_and_illegal_selection_use_safe_action(self):
        base = PokerBot(BotConfig(samples=128))
        wrapper = ExactRiverPolicy(base)
        with patch("pokerfight.river_exact.estimate_river", side_effect=TimeoutError("deadline")):
            result = wrapper.decide(river())
        self.assertTrue(result.fallback)
        self.assertEqual(result.action, Action("check"))
        self.assertIn("TimeoutError", result.reason)
        with patch.object(base, "select", return_value=(Action("raise_to", 1), "bad")):
            result = wrapper.decide(river())
        self.assertTrue(result.fallback)
        self.assertEqual(result.action, Action("check"))

    def test_close_is_forwarded_and_frozen_controls_rejected(self):
        base = PokerBot()
        with patch.object(base, "close", create=True) as close:
            ExactRiverPolicy(base).close()
            close.assert_called_once_with()
        ExactRiverPolicy(base).close()
        with self.assertRaises(ValueError):
            ExactRiverPolicy(ControlBot(BotConfig()))
        with self.assertRaises(ValueError):
            ExactRiverPolicy(object())


if __name__ == "__main__":
    unittest.main()

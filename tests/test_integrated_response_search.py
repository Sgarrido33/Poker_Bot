"""Independent expectation checks by branching the existing scalar v5 rollout."""
from dataclasses import replace
import math
import random
import statistics
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy, play_hand
from pokerfight.domain import Action
from pokerfight.equity import build_ranges
from pokerfight.integrated_response_search import (IntegratedResponse, ReachMoments,
    learned_recourse, search_integrated_responses)
from pokerfight.opponents import OpponentModel
from pokerfight.response_search import ResponseRollout, SHOVE_PRIORS, response_probabilities
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases, opening
from tests.test_action_integration import fixture


class NeedBranch(Exception):
    def __init__(self, probabilities):
        self.probabilities = probabilities


def scalar_expectation(rollout, ranks, scores, prior, continuation, training=False, tape=()):
    """Restart scalar execution for every nonzero probabilistic response path.

    No compiled nodes, masks, prices or accounting enter this oracle. The scalar
    rollout, also checked against PokerKit, computes its own public states.
    """
    offset = 0

    def forced_response(*args, **kwargs):
        nonlocal offset
        probabilities = response_probabilities(*args, **kwargs)
        if offset == len(tape):
            raise NeedBranch(probabilities)
        chosen = tape[offset]
        offset += 1
        return tuple(float(i == chosen) for i in range(3))

    try:
        with patch("pokerfight.response_search.response_probabilities", side_effect=forced_response):
            value, node = rollout.value(ranks, scores, [[.5] * len(ranks)] * 2,
                                        prior, continuation, training)
        return value, {node[0]: (1., node[1])} if node is not None else {}
    except NeedBranch as branch:
        value, nodes = 0., {}
        for chosen, probability in enumerate(branch.probabilities):
            if not probability:
                continue
            child_value, child_nodes = scalar_expectation(rollout, ranks, scores, prior,
                continuation, training, tape + (chosen,))
            value += probability * child_value
            for key, (weight, gain) in child_nodes.items():
                previous_weight, previous_gain = nodes.get(key, (0., 0.))
                nodes[key] = (previous_weight + probability * weight,
                              previous_gain + probability * gain)
        return value, nodes


class ReachMomentsTests(unittest.TestCase):
    def test_weighted_posterior_and_ratio_standard_error_match_direct_sums(self):
        gains, weights = [10., -40., 70., 20.], [.001, .5, .1, .3]
        item = ReachMoments()
        for gain, weight in zip(gains, weights):
            item.add(gain, weight)
        mean = sum(g * w for g, w in zip(gains, weights)) / sum(weights)
        se = math.sqrt(len(weights) / (len(weights) - 1)
                       * sum(w * w * (g - mean) ** 2 for g, w in zip(gains, weights))) / sum(weights)
        self.assertAlmostEqual(item.mean, mean)
        self.assertAlmostEqual(item.se, se)
        self.assertAlmostEqual(item.effective_n, sum(weights) ** 2 / sum(w * w for w in weights))

    def test_equal_weights_match_ordinary_mean_error_and_sparse_nodes_fold(self):
        item = ReachMoments()
        gains = [10., 20., 30., 40.] * 4
        for gain in gains:
            item.add(gain, .00001)  # Rare public node, but all worlds contribute.
        self.assertAlmostEqual(item.se, statistics.stdev(gains) / math.sqrt(len(gains)))
        self.assertTrue(learned_recourse({"p": item}, 100)["p"])
        concentrated = ReachMoments()
        for i in range(20):
            concentrated.add(100., 1. if i == 0 else 1e-8)
        self.assertFalse(learned_recourse({"p": concentrated}, 100)["p"])


class IntegratedResponseTests(unittest.TestCase):
    def test_complete_six_player_tree_with_hero_away_from_index_zero(self):
        state = opening(6, 8, "UTG", ("As", "Ah"))
        self.assertNotEqual(state.hero_id, state.players[0].player_id)
        ranks, scores = [2, 3, 1, 2, 2, 3], [.85, .9, .75, .98, .65, .8]
        for action in (Action("raise_to", 200), Action("raise_to", 800)):
            exact, scalar = IntegratedResponse(state, action, {}), ResponseRollout(state, action, {})
            for prior in SHOVE_PRIORS:
                expected, expected_nodes = scalar_expectation(scalar, ranks, scores, prior, {}, True)
                actual, nodes = exact.value(ranks, scores, prior, {}, True)
                self.assertAlmostEqual(actual, expected, places=9)
                self.assertEqual({key for key, _, _ in nodes}, set(expected_nodes))
                for key, reach, gain in nodes:
                    self.assertAlmostEqual(reach, expected_nodes[key][0], places=12)
                    self.assertAlmostEqual(reach * gain, expected_nodes[key][1], places=9)
                policy = {key: i % 2 == 0 for i, key in enumerate(expected_nodes)}
                expected, _ = scalar_expectation(scalar, ranks, scores, prior, policy)
                self.assertAlmostEqual(exact.value(ranks, scores, prior, policy)[0], expected, places=9)

    def test_expectation_and_every_public_training_node_match_scalar_enumeration(self):
        rng = random.Random(290106)
        obs, _ = fixture()
        states = [opening(2, 8, "BTN", ("As", "Ah")),
                  opening(3, 8, "BTN", ("As", "Ah")), obs]
        comparisons = 0
        for state in states:
            for action in (Action("call"), Action("raise_to", state.legal.min_raise_to),
                           Action("raise_to", state.legal.max_raise_to)):
                integrated = IntegratedResponse(state, action, {p.player_id: .01 for p in state.opponents})
                scalar = ResponseRollout(state, action, {p.player_id: .01 for p in state.opponents})
                for prior in SHOVE_PRIORS:
                    ranks = [rng.randrange(1, 4) for _ in state.players]
                    scores = [rng.random() for _ in state.players]
                    expected, expected_nodes = scalar_expectation(scalar, ranks, scores, prior, {}, True)
                    actual, actual_nodes = integrated.value(ranks, scores, prior, {}, True)
                    self.assertAlmostEqual(actual, expected, places=9)
                    actual_nodes = {key: (weight, weight * gain) for key, weight, gain in actual_nodes}
                    self.assertEqual(set(actual_nodes), set(expected_nodes))
                    for key, (weight, gain) in actual_nodes.items():
                        self.assertAlmostEqual(weight, expected_nodes[key][0], places=12)
                        self.assertAlmostEqual(gain, expected_nodes[key][1], places=9)
                    # Alternate frozen public choices; neither implementation
                    # chooses a continuation against the evaluation ranks.
                    policy = {key: i % 2 == 0 for i, key in enumerate(expected_nodes)}
                    expected, _ = scalar_expectation(scalar, ranks, scores, prior, policy)
                    actual, _ = integrated.value(ranks, scores, prior, policy)
                    self.assertAlmostEqual(actual, expected, places=9)
                    comparisons += 1
        self.assertEqual(comparisons, 27)

    def test_continuation_uses_public_policy_even_on_a_winning_hidden_runout(self):
        state = opening(2, 8, "BTN", ("As", "Ah"))
        arm = IntegratedResponse(state, Action("raise_to", 200), {})

        def forced_jam(score, price, prior, adjustment=0., callers=0, can_shove=True):
            return (0., 0., 1.) if can_shove else (0., 1., 0.)

        with patch("pokerfight.integrated_response_search.response_probabilities", side_effect=forced_jam):
            for ranks in ([2, 1], [1, 2]):
                self.assertEqual(arm.value(ranks, [.8, .99], SHOVE_PRIORS[0], {})[0], -150)
            _, nodes = arm.value([2, 1], [.8, .99], SHOVE_PRIORS[0], {}, True)
            policy = {key: True for key, reach, gain in nodes}
            self.assertEqual(arm.value([1, 2], [.8, .99], SHOVE_PRIORS[0], policy)[0], -750)

    def test_all_in_fold_and_already_acted_matched_players(self):
        state = cases()["bb_cheap_defense_8bb"]
        arm = IntegratedResponse(state, Action("call"), {})
        with patch("pokerfight.integrated_response_search.response_probabilities", side_effect=AssertionError("no turn")):
            self.assertEqual(arm.value([1, 0, 2], [.5] * 3, SHOVE_PRIORS[0], {})[0], 350)
        self.assertEqual(IntegratedResponse(state, Action("fold"), {}).value(
            [1, 0, 2], [.5] * 3, SHOVE_PRIORS[0], {})[0], 0)

    def test_search_is_reproducible_bounded_and_expired_search_retains_baseline(self):
        state, model = opening(3, 4, "BTN", ("As", "Ah")), OpponentModel()
        ranges = build_ranges(state, model, math.inf)
        args = (state, ranges, model, Action("fold"))
        a = search_integrated_responses(*args, random.Random(19), 128, math.inf)
        b = search_integrated_responses(*args, random.Random(19), 128, math.inf)
        self.assertEqual(a, b)
        self.assertEqual(a[1]["total_worlds"], 128)
        self.assertEqual(a[1]["training_worlds"], 64)
        self.assertTrue(a[0].is_legal(state))
        expired = search_integrated_responses(*args, random.Random(19), 128, 0)
        self.assertEqual(expired[0], Action("fold"))
        self.assertEqual(expired[1]["stop"], "deadline_keep_v2")
        self.assertEqual(expired[1]["total_worlds"], 0)

    def test_incomplete_training_or_evaluation_does_not_select_partial_gain(self):
        state, model = opening(2, 4, "BTN"), OpponentModel()
        ranges = build_ranges(state, model, math.inf)
        world = ([2, 1], [.6, .6], [[.5] * 2] * 2)
        for batches in ([iter([world]), iter([world] * 32)],
                        [iter([world] * 32), iter([world])]):
            with patch("pokerfight.integrated_response_search.worlds", side_effect=batches):
                action, info = search_integrated_responses(state, ranges, model, Action("fold"),
                    random.Random(1), 64, math.inf)
            self.assertEqual(action, Action("fold"))
            self.assertEqual(info["stop"], "incompatible_ranges_keep_v2")


class IntegratedResponsePolicyTests(unittest.TestCase):
    def test_all_in_price_and_out_of_scope_match_control(self):
        config = BotConfig(samples=128, budget_ms=3500)
        price = make_policy("v7", config, 19).decide(cases()["cheap_all_in_regression"])
        self.assertEqual(price.action, Action("call"))
        self.assertIsNone(price.search)
        for state in (opening(depth=20), replace(opening(), board=("2c", "3d", "4h"))):
            actual = make_policy("v7", config, 19).decide(state)
            expected = make_policy("v2mc", config, 19).decide(state)
            self.assertEqual(actual.action, expected.action)
            self.assertEqual(actual.equity, expected.equity)

    def test_supervised_and_direct_match(self):
        config = BotConfig(samples=128, budget_ms=3500)
        state = opening(3, 4, "BTN", ("As", "Ah"))
        with SupervisedPolicy(config, policy="v7") as bot:
            actual = bot.decide(state)
        expected = make_policy("v7", config, config.seed).decide(state)
        self.assertFalse(actual.fallback, actual.reason)
        self.assertEqual(actual.action, expected.action)
        self.assertEqual(actual.search, expected.search)

    def test_full_legal_hands_and_chip_conservation_two_to_six_players(self):
        for players in range(2, 7):
            ids = ("hero",) + tuple(str(i) for i in range(1, players))
            policies = {pid: make_policy("v7" if pid == "hero" else "pressure",
                BotConfig(samples=128), 7 + i) for i, pid in enumerate(ids)}
            result = play_hand(policies, ids, dict.fromkeys(ids, 800), 290107)
            self.assertEqual(sum(result.payoffs.values()), 0)
            self.assertFalse(any(decision.fallback for _, decision in result.decisions))


if __name__ == "__main__":
    unittest.main()

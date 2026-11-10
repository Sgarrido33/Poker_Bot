from dataclasses import replace
import math
import random
import unittest
from unittest.mock import patch

from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.action_search import Moments
from pokerfight.arena import make_policy, observation, play_hand
from pokerfight.domain import Action, PublicAction
from pokerfight.equity import build_ranges
from pokerfight.opponents import OpponentModel
from pokerfight.response_search import (ResponseRollout, SHOVE_PRIORS, acted_since_full_raise,
    learned_continuation, response_probabilities, search_responses)
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases, opening


def call_or_shove(score, price, prior, adjustment=0., callers=0, can_shove=True):
    return (0., 0., 1.) if can_shove and score > .9 else (0., 1., 0.)


class ResponseTests(unittest.TestCase):
    def test_probabilities_sum_to_one_and_no_cost_never_folds(self):
        for prior in SHOVE_PRIORS:
            for score in (0., .5, 1.):
                for price in (0., .2, .8):
                    probs = response_probabilities(score, price, prior)
                    self.assertTrue(all(0 <= p <= 1 for p in probs))
                    self.assertAlmostEqual(sum(probs), 1)
                    if price == 0:
                        self.assertEqual(probs[0], 0)
                    self.assertEqual(response_probabilities(score, price, prior, can_shove=False)[2], 0)

    def test_earlier_caller_revisited_after_shove_matches_pokerkit(self):
        # PokerKit seats: SB, BB, BTN. Hero opens; SB calls; BB shoves;
        # hero calls; SB must pay again. Compare actual terminal stack changes.
        auto = tuple(a for a in Automation if a not in (
            Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
        state = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, (800,) * 3, 3)
        for i, cards in enumerate(("KsKh", "QsQh", "AsAh")):
            state.deal_hole(cards, i)
        obs = observation(state, ("sb", "bb", "hero"), "oracle", "1", (), 100)
        arm = ResponseRollout(obs, Action("raise_to", 200), {})
        ranks, scores, uniforms = [2, 1, 3], [.7, .99, .5], [[.5] * 3] * 2
        with patch("pokerfight.response_search.response_probabilities", side_effect=call_or_shove):
            value, node = arm.value(ranks, scores, uniforms, SHOVE_PRIORS[0], {}, training=True)
            self.assertIsNotNone(node)
            self.assertEqual(arm.value(ranks, scores, uniforms, SHOVE_PRIORS[0], {node[0]: True})[0], value)
            self.assertEqual(arm.value(ranks, scores, uniforms, SHOVE_PRIORS[0], {})[0], -200)
        state.complete_bet_or_raise_to(200)
        state.check_or_call()
        state.complete_bet_or_raise_to(800)
        state.check_or_call()
        state.check_or_call()
        for burn, board in (("2c", "3c4d7s"), ("5h", "8h"), ("6d", "9c")):
            state.burn_card(burn)
            state.deal_board(board)
        self.assertFalse(state.status)
        self.assertEqual(value, state.stacks[2] - 800)
        self.assertEqual(node[1], value + 200)

    def test_continuation_does_not_peek_at_evaluation_world_ranks(self):
        obs = opening(2, 8, "BTN", ("As", "Ah"))
        arm = ResponseRollout(obs, Action("raise_to", 200), {})
        with patch("pokerfight.response_search.response_probabilities", side_effect=call_or_shove):
            _, node = arm.value([2, 1], [.8, .99], [[.5] * 2] * 2, SHOVE_PRIORS[0], {}, True)
            # Freeze the choice to fold. Winning and losing hidden runouts
            # produce exactly the same investment loss.
            for ranks in ([2, 1], [1, 2]):
                value, _ = arm.value(ranks, [.8, .99], [[.5] * 2] * 2, SHOVE_PRIORS[0], {node[0]: False})
                self.assertEqual(value, -150)
            # A frozen call can lose; evaluation never optimizes against ranks.
            value, _ = arm.value([1, 2], [.8, .99], [[.5] * 2] * 2, SHOVE_PRIORS[0], {node[0]: True})
            self.assertEqual(value, -750)

    def test_sparse_or_negative_training_nodes_fold(self):
        positive, sparse, negative = Moments(), Moments(), Moments()
        for _ in range(16):
            positive.add(100)
            negative.add(-1)
        sparse.add(1000)
        self.assertEqual(learned_continuation({"p": positive, "s": sparse, "n": negative}, 100),
                         {"p": True, "s": False, "n": False})

    def test_short_all_in_does_not_reopen_raise_rights(self):
        obs = replace(opening(3, 8, "BTN"), history=(
            PublicAction("0", "1", "preflop", "raise_to", 300),
            PublicAction("1", "2", "preflop", "raise_to", 400)))
        acted, increment = acted_since_full_raise(obs)
        self.assertEqual(acted, {"1", "2"})
        self.assertEqual(increment, 200)

    def test_cumulative_short_all_ins_reopen_earlier_actor(self):
        obs = replace(opening(4, 8, "BTN"), history=(
            PublicAction("0", "1", "preflop", "raise_to", 300),
            PublicAction("1", "2", "preflop", "raise_to", 400),
            PublicAction("2", "3", "preflop", "raise_to", 500)))
        acted, increment = acted_since_full_raise(obs)
        self.assertNotIn("1", acted)
        self.assertEqual(acted, {"2", "3"})
        self.assertEqual(increment, 200)

    def test_cumulative_reopening_agrees_with_pokerkit(self):
        auto = tuple(a for a in Automation if a not in (
            Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
        state = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, (400, 500, 1000, 1000), 4)
        for i, cards in enumerate(("2c2d", "3c3d", "AsAh", "KsKh")):
            state.deal_hole(cards, i)
        history = []
        for kind, amount in (("raise_to", 300), ("call", 300), ("raise_to", 400), ("raise_to", 500)):
            actor = state.actor_index
            history.append(PublicAction(str(len(history)), str(actor), "preflop", kind, amount))
            if kind == "call":
                state.check_or_call()
            else:
                state.complete_bet_or_raise_to(amount)
        obs = observation(state, tuple(str(i) for i in range(4)), "reopen", "1", tuple(history), 100)
        self.assertTrue(state.can_complete_bet_or_raise_to())
        self.assertNotIn(obs.hero_id, acted_since_full_raise(obs)[0])
        self.assertEqual(obs.legal.min_raise_to, 700)

    def test_already_acted_matched_opponent_does_not_raise_again(self):
        obs = cases()["bb_cheap_defense_8bb"]
        arm = ResponseRollout(obs, Action("call"), {})
        with patch("pokerfight.response_search.response_probabilities", side_effect=AssertionError("no turn")):
            value, node = arm.value([1, 0, 2], [.99] * 3, [[.5] * 3] * 2, SHOVE_PRIORS[0], {})
        self.assertEqual(value, 350)
        self.assertIsNone(node)

    def test_all_in_players_never_fold_and_unmatched_return_is_kept(self):
        obs = opening(2, 4, "BTN", ("As", "Ah"))
        # Both commit; no second decision or possible villain shove remains.
        arm = ResponseRollout(obs, Action("raise_to", 400), {})
        with patch("pokerfight.response_search.response_probabilities", return_value=(0., 1., 0.)):
            self.assertEqual(arm.value([2, 1], [.9] * 2, [[0.] * 2] * 2, SHOVE_PRIORS[0], {})[0], 450)

    def test_search_reproducible_and_world_cap_includes_training(self):
        obs, model = opening(3, 4, "BTN", ("As", "Ah")), OpponentModel()
        ranges = build_ranges(obs, model, math.inf)
        args = (obs, ranges, model, Action("fold"))
        a = search_responses(*args, random.Random(19), 512, math.inf)
        b = search_responses(*args, random.Random(19), 512, math.inf)
        self.assertEqual(a, b)
        self.assertEqual(a[1]["total_worlds"], 512)
        self.assertEqual(a[1]["training_worlds"], 256)
        self.assertEqual(a[1]["worlds"], 256)
        self.assertTrue(a[0].is_legal(obs))

    def test_expired_search_keeps_baseline(self):
        obs, model = opening(), OpponentModel()
        result = search_responses(obs, build_ranges(obs, model, math.inf), model, Action("fold"), random.Random(1), 512, 0)
        self.assertEqual(result[0], Action("fold"))
        self.assertEqual(result[1]["stop"], "deadline_keep_v2")
        self.assertEqual(result[1]["total_worlds"], 0)


class NewPolicyTests(unittest.TestCase):
    def test_both_candidates_preserve_all_in_price_and_out_of_scope_behavior(self):
        config = BotConfig(samples=128, budget_ms=3500)
        for kind in ("v4rb", "v5"):
            result = make_policy(kind, config, 19).decide(cases()["cheap_all_in_regression"])
            self.assertEqual(result.action, Action("call"))
            self.assertIsNone(result.search)
            for obs in (opening(depth=20), replace(opening(), board=("2c", "3d", "4h"))):
                a, b = make_policy(kind, config, 19).decide(obs), make_policy("v2mc", config, 19).decide(obs)
                self.assertEqual(a.action, b.action)
                self.assertEqual(a.equity, b.equity)

    def test_new_supervised_workers_match_direct(self):
        config = BotConfig(samples=128, budget_ms=3500)
        for kind in ("v4rb", "v5"):
            obs = opening(3, 4, "BTN", ("As", "Ah"))
            with SupervisedPolicy(config, policy=kind) as bot:
                supervised = bot.decide(obs)
                direct = make_policy(kind, config, config.seed).decide(obs)
                self.assertFalse(supervised.fallback, supervised.reason)
                self.assertEqual(supervised.action, direct.action)
                self.assertEqual(supervised.search, direct.search)

    def test_complete_hands_with_new_policies_are_legal(self):
        for kind in ("v4rb", "v5"):
            for n in (2, 3, 4, 5, 6):
                ids = ("hero",) + tuple(str(i) for i in range(1, n))
                policies = {pid: make_policy(kind if pid == "hero" else "pressure", BotConfig(samples=128), 7 + i)
                            for i, pid in enumerate(ids)}
                hand = play_hand(policies, ids, dict.fromkeys(ids, 800), 8901)
                self.assertEqual(sum(hand.payoffs.values()), 0)
                self.assertFalse(any(d.fallback for _, d in hand.decisions))


if __name__ == "__main__":
    unittest.main()

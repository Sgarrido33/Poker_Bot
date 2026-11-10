"""Independent checks for exact integration of sampled-world responses."""
from dataclasses import replace
from itertools import product
import random
import statistics
import unittest

from pokerfight.action_integration import IntegratedAction
from pokerfight.action_model import PRIORS, PreparedAction, ResponsePrior, call_probability
from pokerfight.domain import Action, LegalActions, Observation, Player


def fixture():
    # Several distinct contribution levels create side pots.  One folded
    # player's chips remain dead money, and three live players can respond.
    players = (
        Player("hero", 500, 100, 150),
        Player("short", 250, 100, 140),
        Player("dead", 0, 100, 100, True),
        Player("caller", 800, 200, 300),
        Player("deep", 1000, 0, 40),
    )
    obs = Observation("integrate", "1", "hero", 0, players, ("As", "Kh"), (), 100,
                      LegalActions(False, True, 100, 300, 600))
    return obs, Action("raise_to", 400)


def direct_showdown(contributions, folded, ranks, hero):
    """Simple layer-by-layer terminal payoff, independent of compiled masks."""
    returned = 0.0
    previous = 0
    for level in sorted(set(contributions) - {0}):
        amount = (level - previous) * sum(value >= level for value in contributions)
        eligible = [i for i, value in enumerate(contributions)
                    if value >= level and not folded[i]]
        if hero in eligible:
            best = max(ranks[i] for i in eligible)
            if ranks[hero] == best:
                returned += amount / sum(ranks[i] == best for i in eligible)
        previous = level
    return returned


def enumerate_responses(obs, action, ranks, scores, prior, adjustments):
    """Enumerate fold/call paths directly from the observation, not tree data."""
    hero = next(i for i, player in enumerate(obs.players) if player.player_id == obs.hero_id)
    if action.kind == "fold":
        return 0.0
    investment = (action.amount - obs.hero.street_bet if action.kind == "raise_to"
                  else obs.legal.call_amount if action.kind == "call" else 0)
    initial = [player.contribution for player in obs.players]
    initial[hero] += investment
    target = obs.hero.street_bet + investment
    initial_folded = [player.folded for player in obs.players]
    order = [(hero + distance) % len(obs.players) for distance in range(1, len(obs.players))]

    def visit(offset, contributions, folded, callers):
        if offset == len(order):
            return direct_showdown(contributions, folded, ranks, hero) - investment
        i = order[offset]
        player = obs.players[i]
        cost = min(player.stack, max(0, target - player.street_bet))
        if player.folded or cost == 0:
            return visit(offset + 1, contributions, folded, callers)
        own_total = contributions[i] + cost
        pot_after_call = own_total + sum(min(value, own_total)
                                         for j, value in enumerate(contributions) if j != i)
        price = cost / pot_after_call
        probability = call_probability(scores[i], price, prior,
                                       adjustments.get(player.player_id, 0), callers)

        declined = folded.copy()
        declined[i] = True
        fold_value = visit(offset + 1, contributions, declined, callers)
        paid = contributions.copy()
        paid[i] += cost
        call_value = visit(offset + 1, paid, folded, callers + 1)
        return (1 - probability) * fold_value + probability * call_value

    return visit(0, initial, initial_folded, 0)


class IntegratedActionTests(unittest.TestCase):
    def test_all_six_seat_rank_patterns_match_independent_enumeration(self):
        obs, _ = fixture()
        obs = replace(obs, players=obs.players + (Player("extra", 440, 120, 180),))
        adjustments = {"short": -.02, "caller": .01, "extra": -.015}
        rng = random.Random(20261029)
        for action in (Action("call"), Action("raise_to", 400), Action("raise_to", 600)):
            exact = IntegratedAction(obs, action, adjustments)
            # Every possible better/tied/worse relation, varied priors/scores,
            # and repeated rank patterns exercise reuse without caching EVs.
            for others in product((1, 2, 3), repeat=5):
                ranks = [2, *others]
                for prior in PRIORS:
                    scores = [rng.random() for _ in obs.players]
                    expected = enumerate_responses(obs, action, ranks, scores, prior, adjustments)
                    self.assertEqual(exact.value(ranks, scores, [], prior), expected,
                                     (action, ranks, prior.name))

    def test_check_and_separate_observations_do_not_share_terminal_values(self):
        obs, action = fixture()
        check = replace(obs, players=tuple(replace(p, street_bet=0) for p in obs.players),
                        legal=LegalActions(True, False, 0, 100, obs.hero.stack))
        other = replace(obs, players=tuple(replace(p, contribution=p.contribution + 50)
                                          for p in obs.players))
        ranks, scores = [2, 1, 3, 2, 3], [.5] * 5
        for state, act in ((obs, action), (check, Action("check")), (other, action)):
            integrated = IntegratedAction(state, act, {})
            for prior in PRIORS:
                self.assertEqual(integrated.value(ranks, scores, [], prior),
                                 enumerate_responses(state, act, ranks, scores, prior, {}))

    def test_matches_independent_enumeration_with_caller_dependent_prices(self):
        obs, action = fixture()
        adjustments = {"short": -.02, "caller": .01, "deep": .025}
        ranks = [3, 3, 9, 1, 3]  # Hero ties the short and deep hands in main-pot layers.
        scores = [.4, .66, .2, .59, .73]
        integrated = IntegratedAction(obs, action, adjustments)
        self.assertEqual(len(integrated.levels), 3)

        # The deep player's response price/probability differs according to
        # whether earlier players called, proving caller-dependent paths matter.
        prices = integrated.levels[2][2]
        self.assertNotEqual(prices[0], prices[3])
        for prior in (*PRIORS, ResponsePrior("custom", .61, .8)):
            expected = enumerate_responses(obs, action, ranks, scores, prior, adjustments)
            self.assertAlmostEqual(integrated.value(ranks, scores, [0.0] * 5, prior), expected, places=10)
            self.assertAlmostEqual(integrated.value(ranks, scores, [1.0] * 5, prior), expected, places=10)

    def test_integrates_ties_dead_money_and_side_pots(self):
        obs, action = fixture()
        integrated = IntegratedAction(obs, action, {})
        # Hero loses the main pot, but can tie a side pot against a short stack;
        # the folded seat's contribution is still included in pot layers.
        ranks = [1, 2, 9, 1, 3]
        scores = [.5, .5, .1, .5, .5]
        prior = PRIORS[1]
        expected = enumerate_responses(obs, action, ranks, scores, prior, {})
        self.assertAlmostEqual(integrated.value(ranks, scores, [], prior), expected, places=10)

    def test_fold_and_forced_response_edges(self):
        obs, action = fixture()
        fold = IntegratedAction(obs, Action("fold"), {})
        self.assertEqual(fold.value([1, 2, 3, 4, 5], [.5] * 5, [], PRIORS[0]), 0)

        # All opponents are already matched or all-in, so there is one leaf and
        # integration is exactly the compiled terminal value.
        players = (Player("hero", 300, 100, 100), Player("villain", 0, 200, 200))
        matched = Observation("integrate", "2", "hero", 0, players, ("As", "Kh"), (), 100,
                              LegalActions(False, True, 100, 300, 400))
        call = Action("call")
        exact = IntegratedAction(matched, call, {})
        sampled = PreparedAction(matched, call, {})
        ranks, scores = [2, 1], [.5, .5]
        for prior in PRIORS:
            self.assertEqual(exact.value(ranks, scores, [], prior),
                             sampled.value(ranks, scores, [0, 1], prior))

    def test_expected_value_matches_old_random_response_average(self):
        obs, action = fixture()
        ranks = [2, 1, 9, 2, 0]
        scores = [.3, .68, .1, .61, .75]
        prior = PRIORS[1]
        adjustments = {"short": -.01, "caller": .015, "deep": -.02}
        exact = IntegratedAction(obs, action, adjustments).value(ranks, scores, [], prior)
        sampled = PreparedAction(obs, action, adjustments)
        rng = random.Random(92517)
        n = 100000
        values = [sampled.value(ranks, scores, [rng.random() for _ in obs.players], prior)
                  for _ in range(n)]
        average = sum(values) / n
        standard_error = statistics.stdev(values) / (n ** .5)
        self.assertLessEqual(abs(average - exact), 5 * standard_error)


if __name__ == "__main__":
    unittest.main()

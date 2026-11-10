"""Compare compiled paths to direct accounting, including every response mask."""
from dataclasses import replace
import math
import random
import unittest
from unittest.mock import patch

from pokerfight.action_model import (PRIORS, PreparedAction, ResponsePrior, call_probability,
                                    candidate_actions, relative_rank_masks, showdown_return)
from pokerfight.action_search import search
from pokerfight.domain import Action, LegalActions, Observation, Player, safe_action
from pokerfight.equity import build_ranges
from pokerfight.opponents import OpponentModel
from scripts.diagnose_shortstack import opening


class ScalarAction:
    """Direct, uncompiled reference; recompute contributions on each world."""
    def __init__(self, obs, action, adjustments):
        self.obs, self.action, self.adjustments = obs, action, adjustments
        self.hero = next(i for i, p in enumerate(obs.players) if p.player_id == obs.hero_id)

    def value(self, ranks, scores, uniforms, prior, rank_masks=None):
        obs, action = self.obs, self.action
        if action.kind == "fold":
            return 0.0
        investment = (action.amount - obs.hero.street_bet if action.kind == "raise_to"
                      else obs.legal.call_amount if action.kind == "call" else 0)
        contributions = [p.contribution for p in obs.players]
        folded = [p.folded for p in obs.players]
        contributions[self.hero] += investment
        target = obs.hero.street_bet + investment
        callers = 0
        for distance in range(1, len(obs.players)):
            i = (self.hero + distance) % len(obs.players)
            player = obs.players[i]
            cost = min(player.stack, max(0, target - player.street_bet))
            if player.folded or cost == 0:
                continue
            own_total = contributions[i] + cost
            price = cost / (own_total + sum(min(c, own_total) for j, c in enumerate(contributions) if j != i))
            if uniforms[i] < call_probability(scores[i], price, prior, self.adjustments.get(player.player_id, 0), callers):
                contributions[i] += cost
                callers += 1
            else:
                folded[i] = True
        return showdown_return(contributions, folded, ranks, self.hero) - investment


class CompiledActionTests(unittest.TestCase):
    def test_all_response_masks_match_scalar_with_side_pots_ties_and_antes(self):
        rng = random.Random(73310)
        comparisons = 0
        for n in range(2, 7):
            for case in range(16):
                hero = case % n
                bets = [rng.choice((0, 50, 100, 200, 300)) for _ in range(n)]
                bets[hero] = min(bets[hero], 100)
                states = tuple(Player(str(i), rng.randint(1, 12) * 100 if i == hero else rng.choice((0, 100, 400, 1200)),
                                      bets[i], bets[i] + rng.choice((0, 10, 25)),
                                      i != hero and i != (hero + 1) % n and rng.random() < .3)
                               for i in range(n))
                cost = min(states[hero].stack, max(bets) - bets[hero])
                minimum, maximum = max(bets) + 100, states[hero].stack + bets[hero]
                legal = LegalActions(cost == 0, cost > 0, cost,
                                     minimum if maximum >= minimum else None, maximum if maximum >= minimum else None)
                obs = Observation("compile", str(case), str(hero), case % n, states, ("As", "Kh"), (), 100, legal)
                actions = list(candidate_actions(obs, safe_action(obs)))
                if cost and Action("call") not in actions:
                    actions.append(Action("call"))
                adjustments = {str(i): rng.uniform(-.03, .03) for i in range(n)}
                for action in actions:
                    compiled, scalar = PreparedAction(obs, action, adjustments), ScalarAction(obs, action, adjustments)
                    self.assertLessEqual(len(compiled.outcomes), 32)
                    for mask in range(1 << n):
                        ranks = [rng.randrange(3) for _ in range(n)]  # Frequent ties and lost side pots.
                        scores = [rng.random() for _ in range(n)]
                        uniforms = [float(bool(mask & (1 << i))) for i in range(n)]
                        for prior in PRIORS:
                            expected = scalar.value(ranks, scores, uniforms, prior)
                            self.assertEqual(compiled.value(ranks, scores, uniforms, prior), expected)
                            self.assertEqual(compiled.value(ranks, scores, uniforms, prior, relative_rank_masks(ranks, hero)), expected)
                            comparisons += 1
                    for _ in range(4):
                        ranks, scores = [rng.randrange(3) for _ in range(n)], [rng.random() for _ in range(n)]
                        uniforms = [rng.random() for _ in range(n)]
                        for prior in (*PRIORS, ResponsePrior("custom", .61, .8)):
                            self.assertEqual(compiled.value(ranks, scores, uniforms, prior), scalar.value(ranks, scores, uniforms, prior))
        self.assertGreater(comparisons, 10000)

    def test_whole_search_matches_scalar_including_stopping_and_uncertainty(self):
        for n in range(2, 7):
            for hole in (("As", "Ah"), ("Ts", "9s")):
                obs = opening(n, 8, "BTN" if n == 2 else {3: "BTN", 4: "CO", 5: "HJ", 6: "UTG"}[n], hole)
                model = OpponentModel()
                ranges = build_ranges(obs, model, math.inf)
                args = (obs, ranges, model, Action("fold"))
                actual = search(*args, random.Random(809), 1024, math.inf)
                with patch("pokerfight.action_search.PreparedAction", ScalarAction):
                    expected = search(*args, random.Random(809), 1024, math.inf)
                self.assertEqual(actual, expected)

    def test_compiled_tree_never_folds_matched_or_all_in_players(self):
        obs = Observation("t", "h", "hero", 0,
            (Player("hero", 700, 100, 110), Player("allin", 0, 200, 210),
             Player("matched", 600, 200, 210), Player("unmatched", 100, 50, 60)),
            ("As", "Ah"), (), 100, LegalActions(False, True, 100, 300, 800))
        compiled = PreparedAction(obs, Action("call"), {})
        self.assertEqual([i for i, _, _ in compiled.levels], [3])
        self.assertEqual(len(compiled.outcomes), 2)
        ranks, scores, uniforms = [0, 2, 1, 0], [.5] * 4, [1.] * 4
        self.assertEqual(compiled.value(ranks, scores, uniforms, PRIORS[0]), -100)
        # A free check must preserve every current opponent as well.
        obs = replace(obs, players=(Player("hero", 600, 200, 210), *obs.players[1:3],
                                   Player("unmatched", 0, 50, 60)), legal=LegalActions(True, False, 0))
        self.assertEqual(len(PreparedAction(obs, Action("check"), {}).outcomes), 1)


if __name__ == "__main__":
    unittest.main()

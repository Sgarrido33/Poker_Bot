from dataclasses import replace
import unittest

from pokerfight.arena import make_policy, play_hand
from pokerfight.domain import Action
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy
from pokerfight.terminal_search import terminal_alternatives
from scripts.diagnose_shortstack import cases, opening


class TerminalAlternativeTests(unittest.TestCase):
    def test_does_not_introduce_small_raise_but_retains_baseline(self):
        obs = opening(5, 8, 'BTN', ('7s', '2h'))
        actions = terminal_alternatives(obs, Action('fold'))
        self.assertEqual(actions, (Action('fold'), Action('raise_to', 800)))
        baseline = Action('raise_to', 200)
        self.assertEqual(terminal_alternatives(obs, baseline)[0], baseline)
        self.assertTrue(all(a.is_legal(obs) for a in terminal_alternatives(obs, baseline)))

    def test_big_blind_check_does_not_introduce_nonterminal_call(self):
        obs = cases()['bb_cheap_defense_8bb']
        self.assertNotIn(Action('call'), terminal_alternatives(obs, Action('fold')))
        self.assertIn(Action('call'), terminal_alternatives(obs, Action('call')))

    def test_covers_every_live_opponent_not_only_smallest(self):
        obs = opening(5, 8, 'BTN', ('As', 'Ah'), rival_depth=2)
        # A min-raise puts every live rival all-in and is therefore allowed.
        self.assertIn(Action('raise_to', 200), terminal_alternatives(obs, Action('fold')))
        live = next(i for i, p in enumerate(obs.players) if p.player_id != obs.hero_id and not p.folded)
        players = tuple(replace(p, stack=800 - p.street_bet) if i == live else p
                        for i, p in enumerate(obs.players))
        mixed = replace(obs, players=players)
        self.assertNotIn(Action('raise_to', 200), terminal_alternatives(mixed, Action('fold')))

    def test_price_regression_and_out_of_scope_match_control(self):
        config = BotConfig(samples=128, budget_ms=3500)
        result = make_policy('v6', config, 19).decide(cases()['cheap_all_in_regression'])
        self.assertEqual(result.action, Action('call'))
        self.assertIsNone(result.search)
        for obs in (opening(depth=20), replace(opening(), board=('2c', '3d', '4h'))):
            candidate = make_policy('v6', config, 19).decide(obs)
            control = make_policy('v2mc', config, 19).decide(obs)
            self.assertEqual(candidate.action, control.action)
            self.assertEqual(candidate.equity, control.equity)

    def test_supervisor_and_direct_decision_match(self):
        config = BotConfig(samples=128, budget_ms=3500)
        obs = opening(3, 4, 'BTN', ('As', 'Ah'))
        with SupervisedPolicy(config, policy='v6') as bot:
            supervised = bot.decide(obs)
        direct = make_policy('v6', config, config.seed).decide(obs)
        self.assertFalse(supervised.fallback, supervised.reason)
        self.assertEqual(supervised.action, direct.action)
        self.assertEqual(supervised.search, direct.search)

    def test_legal_hands_and_chip_conservation(self):
        for n in (2, 5, 6):
            ids = ('hero',) + tuple(str(i) for i in range(1, n))
            policies = {pid: make_policy('v6' if pid == 'hero' else 'pressure',
                BotConfig(samples=128), 7 + i) for i, pid in enumerate(ids)}
            hand = play_hand(policies, ids, dict.fromkeys(ids, 800), 92341)
            self.assertEqual(sum(hand.payoffs.values()), 0)
            self.assertFalse(any(d.fallback for _, d in hand.decisions))


if __name__ == '__main__':
    unittest.main()

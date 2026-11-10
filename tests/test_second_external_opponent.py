import random
import unittest
from unittest.mock import patch

from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.arena import observation, play_hand
from pokerfight.domain import Action, LegalActions, Observation, Player
from pokerfight.external_opponents import (
    HonestOpponent,
    honest_win_rate,
    verify_honest,
)


class HonestOpponentTests(unittest.TestCase):
    def test_pinned_source_and_license_hashes(self):
        source = verify_honest()
        self.assertEqual(source["commit"], "a52a048a15da276005eca4acae96fb6eeb4dc034")
        self.assertEqual(source["license"].split()[0], "MIT")
        self.assertEqual(set(source["sha256"]), {"honest_player.py", "LICENSE.md"})

    def test_upstream_tie_rule_and_threshold_equality(self):
        # HonestPlayer counts ties as wins (score >= max opponent score), and
        # chooses CALL when win_rate is exactly 1 / player_num.
        obs = Observation("t", "h", "hero", 0,
            (Player("hero", 900, 0, 0), Player("v1", 1000, 0, 0),
             Player("v2", 1000, 0, 0), Player("v3", 1000, 0, 0),
             Player("v4", 1000, 0, 0)),
            ("As", "Ah"), (), 100, LegalActions(True, False, 0))
        with patch("pokerfight.external_opponents.honest_win_rate", return_value=0.2):
            decision = HonestOpponent(1, samples=1).decide(obs)
        self.assertEqual(decision.action, Action("check"))
        self.assertFalse(decision.fallback)

    def test_table_start_size_survives_later_eliminations(self):
        obs = Observation("table-7", "h2", "hero", 0,
            (Player("hero", 900, 0, 0), Player("v1", 1000, 0, 0),
             Player("v2", 1000, 0, 0)),
            ("As", "Ah"), (), 100, LegalActions(True, False, 0))
        policy = HonestOpponent(3, samples=1)
        policy.start_table("table-7", 5)
        policy.start_table("table-7", 3)
        # At equality this is a call/check only if both the original player
        # count (1/5) and the simulated number of opponents are preserved.
        with patch("pokerfight.external_opponents.honest_win_rate", return_value=0.2) as estimate:
            decision = policy.decide(obs)
        estimate.assert_called_once_with(obs, policy.rng, 1, 5)
        self.assertEqual(decision.action, Action("check"))
        self.assertIn("threshold=0.200", decision.reason)

    def test_simulator_is_deterministic_private_and_does_not_touch_global_rng(self):
        obs = Observation("t", "h", "hero", 0,
            (Player("hero", 900, 0, 0), Player("v1", 1000, 0, 0),
             Player("v2", 1000, 0, 0), Player("v3", 1000, 0, 0),
             Player("v4", 1000, 0, 0)),
            ("As", "Ah"), ("2c", "3d", "4h"), 100, LegalActions(True, False, 0))
        before = random.getstate()
        a, b = random.Random(812), random.Random(812)
        self.assertEqual(honest_win_rate(obs, a, 64), honest_win_rate(obs, b, 64))
        self.assertEqual(before, random.getstate())
        # The adapter has no access to the PokerKit state, deck, or opponents' cards.
        decision_a = HonestOpponent(77, samples=64).decide(obs)
        decision_b = HonestOpponent(77, samples=64).decide(obs)
        self.assertEqual(decision_a.action, decision_b.action)
        self.assertIn("external:honest:", decision_a.reason)

    def test_different_hidden_opponent_holes_produce_the_same_input_and_decision(self):
        def observed(other_holes):
            auto = tuple(a for a in Automation if a not in (
                Automation.HOLE_DEALING, Automation.BOARD_DEALING,
                Automation.CARD_BURNING))
            state = NoLimitTexasHoldem.create_state(auto, True, 0,
                (50, 100), 100, (10000,) * 5, 5)
            for hole in other_holes + ("AsAh", "2c3d", "4h5s"):
                state.deal_hole(hole)
            ids = ("a", "b", "hero", "c", "d")
            return observation(state, ids, "t", "h", (), 100)

        a = observed(("KsKh", "QsQh"))
        b = observed(("6c7c", "8s9s"))
        self.assertEqual(a, b)
        self.assertEqual(HonestOpponent(99, samples=64).decide(a).action,
                         HonestOpponent(99, samples=64).decide(b).action)

    def test_eval7_equal_scores_count_as_wins_like_upstream(self):
        obs = Observation("t", "h", "hero", 0,
            (Player("hero", 900, 0, 0), Player("v1", 1000, 0, 0),
             Player("v2", 1000, 0, 0)),
            ("As", "Ah"), (), 100, LegalActions(True, False, 0))
        # An equal rank is the exact tie case in the upstream `my_score >= max`.
        with patch("pokerfight.external_opponents.eval7.evaluate", return_value=123):
            self.assertEqual(honest_win_rate(obs, random.Random(1), samples=5), 1.0)

    def test_complete_hands_remain_legal_2_5_6_max(self):
        for n in (2, 5, 6):
            with self.subTest(players=n):
                ids = tuple(f"p{i}" for i in range(n))
                policies = {pid: HonestOpponent(i + 7, samples=16) for i, pid in enumerate(ids)}
                result = play_hand(policies, ids, dict.fromkeys(ids, 1000), deck_seed=100 + n)
                self.assertEqual(sum(result.payoffs.values()), 0)
                self.assertGreater(len(result.decisions), 0)
                self.assertTrue(all(d.action.kind in ("fold", "check", "call")
                                    for _, d in result.decisions))


if __name__ == "__main__":
    unittest.main()

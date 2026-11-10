import unittest

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.domain import LegalActions, Observation, Player, PublicAction
from pokerfight.pushfold import _nearest, call_freq, range_percent, shove_freq
from pokerfight.pushfold_bot import chart_action, position6
from pokerfight.strategy import BotConfig


def heads_up(hole, stack=800, facing_shove=False):
    """Button/SB first in (or BB facing the button shove), 100 blinds."""
    if not facing_shove:
        players = (Player("btn", stack - 50, 50, 50), Player("bb", stack - 100, 100, 100))
        legal = LegalActions(False, True, 50, 200, stack)
        return Observation("t", "h", "btn", 0, players, hole, (), 100, legal)
    players = (Player("btn", 0, stack, stack), Player("bb", stack - 100, 100, 100))
    history = (PublicAction("0", "btn", "preflop", "raise_to", stack, True),)
    legal = LegalActions(False, True, stack - 100)
    return Observation("t", "h", "bb", 0, players, hole, (), 100, legal, history)


class ChartTests(unittest.TestCase):
    def test_heads_up_ten_bb_matches_published_equilibrium_size(self):
        sol = _nearest(10)
        # Published chip-EV Nash at 10 bb: SB shoves ~58 %, BB calls ~37 %.
        self.assertAlmostEqual(range_percent(sol["shove"]["4"]), 0.58, delta=0.03)
        self.assertAlmostEqual(range_percent(sol["call"]["4,5"]), 0.37, delta=0.03)

    def test_ranges_tighten_with_position_and_depth(self):
        for stack in (4, 8, 15):
            sizes = [range_percent(_nearest(stack)["shove"][str(p)]) for p in range(5)]
            self.assertEqual(sizes, sorted(sizes))
        self.assertGreater(range_percent(_nearest(4)["shove"]["0"]), range_percent(_nearest(15)["shove"]["0"]))
        self.assertGreater(shove_freq("AA", 0, 15), 0.99)
        self.assertLess(shove_freq("72o", 0, 8), 0.01)
        self.assertGreater(call_freq("AA", 0, 5, 15), 0.99)

    def test_positions_follow_preflop_action_order(self):
        for n, expected in {2: [4, 5], 3: [3, 4, 5], 6: [3, 4, 5, 0, 1, 2]}.items():
            players = tuple(Player(str(i), 800, 0, 0) for i in range(n))
            obs = Observation("t", "h", "0", 0, players, ("As", "Ks"), (), 100,
                              LegalActions(True, False, 0, 200, 800))
            self.assertEqual([position6(obs, str(i)) for i in range(n)], expected)


class DecisionTests(unittest.TestCase):
    def test_first_in_shove_or_fold(self):
        action, reason = chart_action(heads_up(("Ks", "2d")))
        self.assertEqual((action.kind, action.amount), ("raise_to", 800))
        self.assertTrue(reason.startswith("v8:first_in_shove"))
        action, _ = chart_action(heads_up(("7s", "2d")))
        self.assertEqual(action.kind, "fold")

    def test_call_or_fold_facing_shove(self):
        self.assertEqual(chart_action(heads_up(("As", "9d"), facing_shove=True))[0].kind, "call")
        self.assertEqual(chart_action(heads_up(("7s", "2d"), facing_shove=True))[0].kind, "fold")

    def test_isolation_shove_over_limper_only_in_v8b(self):
        players = (Player("btn", 700, 100, 100), Player("sb", 750, 50, 50), Player("bb", 700, 100, 100))
        history = (PublicAction("0", "btn", "preflop", "call", 100, True),
                   PublicAction("1", "sb", "preflop", "fold", 0, True))
        obs = Observation("t", "h", "bb", 0, players, ("As", "Kd"), (), 100,
                          LegalActions(True, False, 0, 200, 800), history)
        self.assertIsNone(chart_action(obs))
        action, reason = chart_action(obs, isolate=True)
        self.assertEqual((action.kind, action.amount, reason.split(":")[1]), ("raise_to", 800, "isolation_shove"))
        weak = Observation("t", "h", "bb", 0, players, ("7s", "2d"), (), 100,
                           LegalActions(True, False, 0, 200, 800), history)
        self.assertIsNone(chart_action(weak, isolate=True))

    def test_v8c_calls_only_when_v2_equity_confirms(self):
        bot = make_policy("v8c", BotConfig(samples=512), 1)
        self.assertEqual(bot.decide(heads_up(("As", "Ad"), facing_shove=True)).reason, "v8:call_shove_confirmed")
        decision = bot.decide(heads_up(("7s", "2d"), facing_shove=True))
        self.assertEqual(decision.action.kind, "fold")
        self.assertTrue(decision.reason.startswith("v8:facing_raise_fold"))

    def test_deep_stacks_and_postflop_are_left_to_v2(self):
        self.assertIsNone(chart_action(heads_up(("As", "Ad"), stack=4000)))
        decision = make_policy("v8", BotConfig(samples=128), 1).decide(heads_up(("As", "Ad"), stack=4000))
        self.assertFalse(decision.reason.startswith("v8:"))

    def test_full_hands_are_legal_for_every_table_size(self):
        for n in (2, 3, 4, 5, 6):
            ids = tuple(f"p{i}" for i in range(n))
            policies = {pid: make_policy("v8", BotConfig(samples=128), seed_for("v8", n, pid)) for pid in ids}
            stacks = dict.fromkeys(ids, 800)
            for hand in range(6):
                active = tuple(p for p in ids if stacks[p] > 0)
                if len(active) < 2:
                    break
                result = play_hand(policies, active, stacks, seed_for("v8-deck", n, hand), str(hand), f"v8-{n}")
                stacks.update(result.stacks)
            self.assertEqual(sum(stacks.values()), 800 * n)


if __name__ == "__main__":
    unittest.main()

from dataclasses import replace
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.controls import ControlBot
from pokerfight.domain import LegalActions, Observation, Player, PublicAction
from pokerfight.strategy import BotConfig
from tests.test_pushfold import heads_up


def raised(other=10000, folded=False):
    return Observation("guard", "raise", "hero", 0,
        (Player("btn", 550, 250, 250), Player("hero", 9950, 50, 50),
         Player("bb", other - 100, 100, 100, folded)),
        ("As", "Ad"), (), 100, LegalActions(False, True, 200, 400, 10000),
        (PublicAction("0", "btn", "preflop", "raise_to", 250, True),))


class GuardedPushFoldTests(unittest.TestCase):
    def bot(self, kind="v8d"):
        return make_policy(kind, BotConfig(samples=128), 7)

    def test_deep_response_delegates_and_legacy_is_unchanged(self):
        obs = raised()
        self.assertEqual(self.bot("v8").decide(obs).action.amount, 10000)
        decision = self.bot().decide(obs)
        self.assertTrue(decision.reason.startswith("v8d:scope_guard:"))
        self.assertEqual(decision.action, self.bot("v2").decide(obs).action)
        self.assertTrue(decision.action.is_legal(obs))

    def test_guard_also_covers_unequal_short_stacks_and_folds(self):
        obs = raised(1200)
        obs = replace(obs, players=(obs.players[0], Player("hero", 1150, 50, 50), obs.players[2]),
                      hole_cards=("7s", "2d"), legal=LegalActions(False, True, 200, 400, 1200))
        self.assertTrue(self.bot().decide(obs).reason.startswith("v8d:scope_guard:"))

    def test_folded_deep_seat_does_not_disable_a_covered_shove(self):
        obs = raised(folded=True)
        decision = self.bot().decide(obs)
        self.assertEqual(decision.reason, "v8d:reshove:8.0bb")
        self.assertEqual(decision.action.amount, 800)

    def test_observation_is_ingested_on_chart_requests_and_deduplicated(self):
        obs = Observation("guard", "observe", "hero", 0,
            (Player("btn", 800, 0, 0, True), Player("hero", 750, 50, 50), Player("bb", 700, 100, 100)),
            ("As", "Ad"), (), 100, LegalActions(False, True, 50, 200, 800),
            (PublicAction("0", "btn", "preflop", "fold", 0, False),))
        bot = self.bot()
        self.assertEqual(bot.decide(obs).reason, "v8d:first_in_shove:8.0bb")
        self.assertEqual(bot.model.counts[("btn", "preflop", False)].folds, 1)
        bot.decide(obs)
        self.assertEqual(bot.model.counts[("btn", "preflop", False)].folds, 1)

    def test_chart_failure_is_visible_even_when_control_succeeds(self):
        with patch("pokerfight.guarded_pushfold.chart_action", side_effect=KeyError("missing")):
            decision = self.bot().decide(heads_up(("As", "Ad")))
        self.assertTrue(decision.fallback)
        self.assertTrue(decision.reason.startswith("v8d:chart_error:KeyError:"))
        self.assertTrue(decision.action.is_legal(heads_up(("As", "Ad"))))

    def test_component_variants_change_only_the_enabled_context(self):
        contexts = {"open": heads_up(("As", "Ad")),
                    "call": heads_up(("As", "Ad"), facing_shove=True),
                    "reshove": raised(other=800)}
        for enabled in contexts:
            for name, obs in contexts.items():
                bot = self.bot("v8d_" + enabled)
                decision = bot.decide(obs)
                if enabled == name:
                    self.assertTrue(decision.reason.startswith("v8d:"), (enabled, name))
                else:
                    self.assertEqual(decision.action, self.bot("v2").decide(obs).action)
                    self.assertFalse(decision.reason.startswith("v8d:"))

    def test_arena_supplies_final_history_to_legacy_and_new_models(self):
        for kind in ("v8", "v8d"):
            bot = self.bot(kind)
            pp = {"hero": bot, "other": self.bot("v2")}
            result = play_hand(pp, ("hero", "other"), {"hero": 800, "other": 800}, 12)
            count = sum(c.n for c in bot.model.counts.values())
            self.assertEqual(count, len(result.history))

    def test_hands_with_eliminations_and_unequal_stacks_are_legal(self):
        for n in (2, 3, 5, 6):
            ids = tuple(str(i) for i in range(n))
            pp = {pid: self.bot() for pid in ids}
            stacks = {pid: 400 + i * 500 for i, pid in enumerate(ids)}
            expected = sum(stacks.values())
            for hand in range(8):
                active = tuple(pid for pid in ids if stacks[pid])
                if len(active) < 2:
                    break
                result = play_hand(pp, active, stacks, seed_for("v8d-test", n, hand), str(hand))
                stacks.update(result.stacks)
                self.assertEqual(sum(stacks.values()), expected)
                self.assertFalse(any(d.fallback for pid, d in result.decisions))


if __name__ == "__main__":
    unittest.main()

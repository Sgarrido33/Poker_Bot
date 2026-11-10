from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.domain import Action, LegalActions, Observation, Player, PublicAction
from pokerfight.equity import EquityResult
from pokerfight.evaluation import evaluate, simulate
from pokerfight.replay import replay_worst
from pokerfight.shortstack import ShortStackBot, context
from pokerfight.shortstack_experiment import protocol, run, stratified_interval, verify_control
from pokerfight.strategy import BotConfig, PokerBot
from scripts.diagnose_shortstack import cases, opening

ROOT = Path(__file__).resolve().parents[1]


class ControlTests(unittest.TestCase):
    def test_snapshot_checksums(self):
        verify_control()

    def test_v2_matches_golden_multiplayer_hands_before_changes(self):
        expected = json.loads((ROOT / "tests/v2_golden.json").read_text(encoding="utf-8"))
        actual = []
        for n in (2, 3, 4, 5, 6):
            ids = ("hero",) + tuple(str(i) for i in range(1, n))
            policies = {pid: make_policy("v2", BotConfig(samples=128), seed_for("golden-v2", n, pid)) for pid in ids}
            for hand in range(2):
                result = play_hand(policies, ids, dict.fromkeys(ids, 800), seed_for("golden-v2", n, hand), str(hand), f"golden-{n}")
                actual.append({"players": n, "hand": hand, "payoffs": result.payoffs,
                               "history": [asdict(e) for e in result.history]})
        self.assertEqual(actual, expected)

    def test_control_ignores_mutations_of_live_charts_sampler_and_model(self):
        obs = opening(hole=("As", "Ah"))
        before = make_policy("v2", BotConfig(samples=128), 17).decide(obs)
        with patch("pokerfight.strategy.estimate", side_effect=RuntimeError("live sampler changed")), \
             patch("pokerfight.opponents.OpponentModel.observe", side_effect=RuntimeError("live model changed")), \
             patch.dict("pokerfight.preflop.OPEN_RANGES", {"UTG": "72o"}), \
             patch("pokerfight.cards.preflop_score", return_value=0):
            after = make_policy("v2", BotConfig(samples=128), 17).decide(obs)
        self.assertFalse(after.fallback)
        self.assertEqual(before.action, after.action)
        self.assertEqual(before.equity, after.equity)


class ShortStackTests(unittest.TestCase):
    def setUp(self):
        self.bot = ShortStackBot(BotConfig(samples=128))
        self.equity = EquityResult(.50, .01, 100, 200, 128, 128, False)

    def test_speculative_early_open_declines_instead_of_committing_62_percent(self):
        obs = cases()["utg_speculative_4bb"]
        self.assertEqual(PokerBot().select(obs, self.equity)[0], Action("raise_to", 250))
        self.assertEqual(self.bot.select(obs, self.equity)[0], Action("fold"))

    def test_position_and_remaining_opponents_change_short_ace_open(self):
        early = opening(hole=("As", "7h"))
        late = opening(position="BTN", hole=("As", "7h"))
        self.assertEqual(context(early).opponents, 5)
        self.assertEqual(context(late).opponents, 2)
        self.assertEqual(self.bot.select(early, self.equity)[0], Action("fold"))
        self.assertEqual(self.bot.select(late, self.equity)[0], Action("raise_to", 400))

    def test_all_player_counts_and_blind_positions(self):
        for n, pos in ((2, "BTN"), (3, "BTN"), (4, "CO"), (5, "HJ"), (6, "UTG")):
            obs = opening(n, 8, pos, ("As", "Ah"))
            action, reason = self.bot.select(obs, self.equity)
            self.assertEqual(action, Action("raise_to", 800))
            self.assertTrue(action.is_legal(obs))
            self.assertEqual(reason, "v3:short_first_in_push")

    def test_effective_stack_caps_push_with_deep_hero(self):
        obs = cases()["effective_4bb_hero_100bb"]
        self.assertEqual(context(obs).effective_bb, 4)
        self.assertEqual(self.bot.select(obs, self.equity)[0], Action("raise_to", 400))
        # A short third player cannot make a confrontation with a deep rival short.
        obs = opening(3, 100, "BTN", ("As", "Ah"), rival_depth=4)
        obs = replace(obs, players=(obs.players[0], replace(obs.players[1], stack=9950), obs.players[2]))
        self.assertEqual(context(obs).effective_bb, 100)
        self.assertEqual(self.bot.select(obs, self.equity), PokerBot().select(obs, self.equity))

    def test_depth_boundary_uses_total_street_stack_including_posted_blind(self):
        obs = opening(2, 8, "BTN", ("As", "5h"))
        self.assertEqual(context(obs).effective_bb, 8)
        self.assertEqual(self.bot.select(obs, self.equity)[0], Action("raise_to", 800))
        obs = opening(2, 8.01, "BTN", ("As", "5h"))
        self.assertEqual(self.bot.select(obs, self.equity), PokerBot().select(obs, self.equity))

    def test_limped_pots_and_defense_use_v2(self):
        for name in ("bb_cheap_defense_8bb", "bb_expensive_defense_8bb"):
            obs = cases()[name]
            self.assertEqual(self.bot.select(obs, self.equity), PokerBot().select(obs, self.equity))
        obs = opening(3, 8, "SB", ("As", "Ah"))
        # BTN called instead of folding: this must not enter first-in branch.
        obs = replace(obs, players=(Player("0", 700, 100, 100), obs.players[1], obs.players[2]),
                      history=(PublicAction("0", "0", "preflop", "call", 100, True),))
        self.assertEqual(context(obs).situation, "limped")
        self.assertEqual(self.bot.select(obs, self.equity), PokerBot().select(obs, self.equity))

    def test_cheap_all_in_and_bad_price_regressions_in_v3(self):
        obs = cases()["cheap_all_in_regression"]
        result = self.bot.decide(obs)
        self.assertEqual(result.action.kind, "call")
        self.assertFalse(result.fallback)
        obs = Observation("t", "h", "hero", 1,
            (Player("hero", 790, 10, 10), Player("v", 0, 800, 800)),
            ("7s", "2h"), (), 100, LegalActions(False, True, 790))
        eq = replace(self.equity, equity=.1, eligible_pot=1600)
        self.assertEqual(self.bot.select(obs, eq)[0], Action("fold"))

    def test_free_check_no_reopen_and_postflop_unchanged(self):
        obs = cases()["bb_cheap_defense_8bb"]
        obs = replace(obs, hole_cards=("7s", "2h"),
            players=(Player("BTN", 700, 100, 100), obs.players[1], obs.players[2]),
            legal=LegalActions(True, False, 0, 200, 800),
            history=(PublicAction("0", "BTN", "preflop", "call", 100, True),
                     PublicAction("1", "SB", "preflop", "fold", 0, True)))
        self.assertEqual(self.bot.select(obs, self.equity)[0], Action("check"))
        obs = opening(hole=("As", "Ah"))
        obs = replace(obs, legal=LegalActions(False, True, 100))
        self.assertNotEqual(self.bot.select(obs, self.equity)[0].kind, "raise_to")
        obs = replace(obs, board=("2c", "3d", "4h"))
        self.assertEqual(self.bot.select(obs, self.equity), PokerBot().select(obs, self.equity))


class ExperimentTests(unittest.TestCase):
    def test_namespace_changes_decks_and_same_namespace_replays_at_4bb(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            args = dict(players=3, blocks=2, hands_per_block=2, seed=29, config=BotConfig(samples=128),
                        opponents=("v2",), candidate="v3", baseline="v2", starting_stack=400, experiment_id="fresh-A")
            first = evaluate(**args)
            again = evaluate(**args)
            other = evaluate(**{**args, "experiment_id": "fresh-B"})
            self.assertEqual(first["block_differences_bb_per_hand"], again["block_differences_bb_per_hand"])
            self.assertNotEqual(first["worst_candidate_hands"][0]["deck_seed"], other["worst_candidate_hands"][0]["deck_seed"])
            first["environment"] = __import__("pokerfight.evaluation", fromlist=["environment"]).environment()
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(first), encoding="utf-8")
            self.assertTrue(replay_worst(str(path))["matched"])
            self.assertEqual(first["assumptions"]["starting_stack_bb"], 4)

    def test_context_outcomes_count_each_hero_hand_once(self):
        report = evaluate(3, 2, 2, 9, BotConfig(samples=128), ("v2",), "v2", "v3", starting_stack=800)
        for key in ("candidate_contexts", "baseline_contexts"):
            self.assertEqual(sum(r["hands"] for r in report[key]["first_decision_outcomes"]), report["hands_per_variant"])
            expected = report["candidate_chips"] if key == "candidate_contexts" else report["baseline_chips"]
            self.assertAlmostEqual(sum(r["payoff_bb"] for r in report[key]["first_decision_outcomes"]), expected / 100)

    def test_equal_policies_zero_difference_at_all_depths(self):
        for depth in (4, 8, 12, 20):
            report = evaluate(2, 2, 1, 43, BotConfig(samples=128), ("v2",), "v2", "v2", starting_stack=depth * 100,
                              experiment_id="identity-check")
            self.assertEqual(report["block_differences_bb_per_hand"], [0, 0])
            self.assertEqual(report["fallbacks_all_policies"], 0)

    def test_stratified_bootstrap_preserves_constant_cells_and_requires_blocks(self):
        self.assertEqual(stratified_interval([[1, 1], [3, 3]], 1), [2, 2])
        self.assertIsNone(stratified_interval([[1]], 1))
        self.assertEqual(stratified_interval([[1, -2, 3], [4, 7]], 3), stratified_interval([[1, -2, 3], [4, 7]], 3))

    def test_preregistered_plan_refuses_changed_code_and_requires_pilot(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            root = Path(directory)
            plan = protocol("unit-only-fresh")
            (root / "protocol.json").write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "piloto"):
                run(root, "validation")
            with patch("pokerfight.shortstack_experiment.environment", return_value={}):
                with self.assertRaisesRegex(ValueError, "Código"):
                    run(root, "pilot")


if __name__ == "__main__":
    unittest.main()

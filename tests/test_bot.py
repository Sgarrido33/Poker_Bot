from __future__ import annotations

from dataclasses import asdict, replace
from io import StringIO
from itertools import product
import json
import math
from pathlib import Path
import random
from time import perf_counter
import unittest
from unittest.mock import patch

import eval7
from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.arena import Baseline, make_policy, observation, play_hand
from pokerfight.cards import CARD_INDEX, EVAL_CARDS, hand_class
from pokerfight.cli import serve
from pokerfight.domain import Action, LegalActions, Observation, Player, PublicAction, safe_action
from pokerfight.equity import WeightedRange, build_ranges, estimate
from pokerfight.evaluation import evaluate, simulate
from pokerfight.opponents import OpponentModel
from pokerfight.strategy import BotConfig, PokerBot

ROOT = Path(__file__).resolve().parents[1]


def example() -> Observation:
    return Observation.from_dict(json.loads((ROOT / "examples/observation.json").read_text(encoding="utf-8")))


def river(hole=("As", "Ah"), board=("2c", "3d", "7h", "8s", "9c")) -> Observation:
    return Observation("table", "hand", "hero", 1,
        (Player("hero", 900, 0, 100), Player("villain", 900, 0, 100)),
        hole, board, 10, LegalActions(True, False, 0, 10, 900))


def weighted(*entries: tuple[str, str, float]) -> WeightedRange:
    return WeightedRange.create([((CARD_INDEX[a], CARD_INDEX[b]), weight) for a, b, weight in entries])


class DomainTests(unittest.TestCase):
    def test_example_round_trip_and_positions(self):
        obs = example()
        self.assertEqual(obs.position, "HJ")
        self.assertEqual(Observation.from_dict(asdict(obs)), obs)
        for n in (2, 3, 4, 5, 6):
            players = tuple(Player(str(i), 100, 0, 10) for i in range(n))
            positions = [Observation("t", "h", str(i), n - 1, players,
                ("As", "Kh"), (), 10, LegalActions(True, False, 0)).position for i in range(n)]
            self.assertEqual(positions[-1], "BTN")
            self.assertEqual(positions[0], "BB" if n == 2 else "SB")
            self.assertEqual(len(set(positions)), n)

    def test_malformed_or_hidden_data_is_rejected(self):
        original = asdict(example())
        cases = []
        for key, value in (("hole_cards", ("As", "As")), ("board", ("2c",)),
                           ("button_index", -1), ("big_blind", True), ("schema_version", 2)):
            cases.append({**original, key: value})
        hidden = json.loads(json.dumps(original))
        hidden["players"][0]["hole_cards"] = ["Ks", "Kh"]
        cases.append(hidden)
        invalid_call = json.loads(json.dumps(original))
        invalid_call["legal"]["call_amount"] = 200
        cases.append(invalid_call)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                Observation.from_dict(data)

    def test_no_reopen_is_respected_even_with_large_stack(self):
        obs = replace(example(), legal=LegalActions(False, True, 100))
        self.assertFalse(Action("raise_to", 200).is_legal(obs))
        self.assertFalse(Action("check").is_legal(obs))
        self.assertTrue(Action("call").is_legal(obs))
        self.assertTrue(Action("fold").is_legal(obs))
        self.assertFalse(Action("raise_to", True).is_legal(example()))

    def test_safe_action_checks_before_folding(self):
        self.assertEqual(safe_action(river()).kind, "check")
        self.assertEqual(safe_action(example()).kind, "fold")
        no_fold = replace(example(), legal=LegalActions(False, False, 100))
        self.assertEqual(safe_action(no_fold).kind, "call")

    def test_side_pots_exclude_unwinnable_layers_and_include_dead_money(self):
        obs = Observation("t", "h", "hero", 2,
            (Player("hero", 50, 0, 0), Player("v1", 900, 100, 100),
             Player("v2", 900, 100, 100), Player("dead", 900, 100, 100, True)),
            ("As", "Ah"), ("2c", "3d", "7h", "8s", "9c"), 10,
            LegalActions(False, True, 50))
        pots = obs.call_pots()
        self.assertEqual(sum(p.amount for p in pots), 200)
        self.assertEqual(pots[0].eligible, ("hero", "v1", "v2"))
        self.assertEqual(sum(p.amount for p in replace(obs, hero_id="v1",
            legal=LegalActions(True, False, 0)).call_pots()), 300)


class EquityTests(unittest.TestCase):
    def test_nuts_and_tie_shares(self):
        obs = river()
        result = estimate(obs, {"villain": weighted(("Ks", "Kh", 1))}, random.Random(1), 16)
        self.assertEqual(result.equity, 1)
        self.assertEqual(result.expected_return, 200)
        obs = river(hole=("2d", "3d"), board=("As", "Ks", "Qs", "Js", "Ts"))
        result = estimate(obs, {"villain": weighted(("4c", "5h", 1))}, random.Random(1), 16)
        self.assertEqual(result.equity, 0.5)

    def test_weighted_equity_matches_exact_river_enumeration(self):
        obs = river()
        ranges = {"villain": weighted(("Ks", "Kh", 1), ("6h", "Th", 3))}
        # Hero beats KK but loses to the ten-high straight: 1 / (1 + 3).
        result = estimate(obs, ranges, random.Random(17), 12000)
        self.assertAlmostEqual(result.equity, 0.25, delta=0.015)
        self.assertGreater(result.standard_error, 0)

    def test_joint_conditioning_and_blockers_match_enumeration(self):
        obs = Observation("t", "h", "hero", 2,
            (Player("hero", 100, 0, 100), Player("v1", 100, 0, 100), Player("v2", 100, 0, 100)),
            ("As", "Ah"), ("2c", "3d", "7h", "8s", "9c"), 10, LegalActions(True, False, 0))
        a = [(("Ks", "Kh"), 5), (("6h", "Th"), 1), (("5c", "5d"), 2)]
        b = [(("Ks", "Kd"), 3), (("6h", "Ts"), 2), (("Qc", "Qd"), 1)]
        total = expected = 0.0
        board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board]
        hero_rank = eval7.evaluate([EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards] + board)
        for (pa, wa), (pb, wb) in product(a, b):
            if set(pa).intersection(pb):
                continue
            ranks = [hero_rank] + [eval7.evaluate([EVAL_CARDS[CARD_INDEX[c]] for c in pair] + board) for pair in (pa, pb)]
            share = (1 / ranks.count(max(ranks))) if hero_rank == max(ranks) else 0
            total += wa * wb
            expected += wa * wb * share
        ranges = {"v1": weighted(*(p + (w,) for p, w in a)), "v2": weighted(*(p + (w,) for p, w in b))}
        result = estimate(obs, ranges, random.Random(41), 16000)
        self.assertAlmostEqual(result.equity, expected / total, delta=0.015)
        self.assertGreater(result.attempts, result.samples)

    def test_loses_main_pot_but_wins_side_pot(self):
        # Short-stack AA wins the main pot; hero KK beats deep-stack QQ.
        obs = Observation("t", "h", "hero", 2,
            (Player("hero", 1, 0, 100), Player("v1", 0, 0, 50), Player("v2", 1, 0, 100)),
            ("Ks", "Kh"), ("2c", "3d", "7h", "8s", "9c"), 10, LegalActions(True, False, 0))
        ranges = {"v1": weighted(("As", "Ah", 1)), "v2": weighted(("Qs", "Qh", 1))}
        result = estimate(obs, ranges, random.Random(1), 8)
        # AA short stack wins 150; hero wins the 100-chip side pot.
        self.assertAlmostEqual(result.equity, 0.4)
        self.assertAlmostEqual(result.expected_return, 100)

    def test_known_cards_and_incompatible_ranges_are_rejected(self):
        obs = river()
        with self.assertRaises(ValueError):
            estimate(obs, {"villain": weighted(("As", "Kh", 1))}, random.Random(1), 5)
        with self.assertRaises(TimeoutError):
            estimate(obs, {"villain": weighted(("Ks", "Kh", 1))}, random.Random(1), 5, 0)
        with self.assertRaises(ValueError):
            WeightedRange.create([((1, 2), math.nan)])

    def test_replay_and_full_support_ranges(self):
        obs = example()
        model = OpponentModel()
        ranges = build_ranges(obs, model, math.inf)
        known = {CARD_INDEX[c] for c in obs.hole_cards}
        for weighted_range in ranges.values():
            self.assertTrue(all(not known.intersection(pair) for pair in weighted_range.combos))
        a = estimate(obs, ranges, random.Random(51), 128)
        b = estimate(obs, ranges, random.Random(51), 128)
        self.assertEqual(a, b)


class ModelAndStrategyTests(unittest.TestCase):
    def test_model_deduplicates_and_resets_at_table_boundary(self):
        model = OpponentModel()
        event = PublicAction("0", "v", "flop", "raise_to", 100, False)
        model.observe("t", "h", (event,))
        model.observe("t", "h", (event,))
        self.assertEqual(model.counts[("v", "flop", False)].n, 1)
        _, confidence = model.tendency("v", "flop", False)
        self.assertGreater(confidence, 0)
        self.assertLess(confidence, 0.35)
        self.assertEqual(model.tendency("v", "river", True)[1], 0)
        model.observe("new-table", "h", ())
        self.assertEqual(model.tendency("v", "flop", False)[1], 0)

    def test_premium_open_and_weak_hand_fold(self):
        bot = PokerBot(BotConfig(samples=256))
        obs = example()
        premium = bot.decide(obs)
        self.assertEqual(premium.action, Action("raise_to", 250))
        self.assertFalse(premium.fallback)
        weak = bot.decide(replace(obs, hole_cards=("7s", "2h")))
        self.assertEqual(weak.action.kind, "fold")
        self.assertFalse(weak.fallback)

    def test_no_reopen_and_all_in_call(self):
        bot = PokerBot(BotConfig(samples=128))
        obs = replace(example(), legal=LegalActions(False, True, 100))
        decision = bot.decide(obs)
        self.assertTrue(decision.action.is_legal(obs))
        self.assertNotEqual(decision.action.kind, "raise_to")
        obs = Observation("t", "h", "hero", 1,
            (Player("hero", 50, 0, 0), Player("v", 0, 100, 100)),
            ("As", "Ah"), ("Ac", "Ad", "2c", "3d", "4h"), 10, LegalActions(False, True, 50))
        decision = bot.decide(obs)
        self.assertEqual(decision.action.kind, "call")
        self.assertFalse(decision.fallback)

    def test_exception_and_deadline_fallback(self):
        bot = PokerBot(BotConfig(samples=128))
        with patch("pokerfight.strategy.estimate", side_effect=RuntimeError("test failure")):
            decision = bot.decide(example())
        self.assertEqual(decision.action.kind, "fold")
        self.assertTrue(decision.fallback)
        self.assertIn("RuntimeError", decision.reason)
        with patch.object(bot, "select", return_value=(Action("raise_to", 1), "illegal")):
            self.assertTrue(bot.decide(example()).fallback)
        with patch("pokerfight.strategy.build_ranges", side_effect=TimeoutError("budget")):
            self.assertEqual(bot.decide(river()).action.kind, "check")
        # A finite work cap is meaningful even on fast machines.
        decision = PokerBot(BotConfig(samples=1000000, budget_ms=1)).decide(example())
        self.assertTrue(decision.action.is_legal(example()))
        self.assertLess(decision.elapsed_ms, 250)

    def test_jsonl_recovers_after_invalid_input_and_continues(self):
        bot = PokerBot(BotConfig(samples=128))
        request = json.dumps(asdict(example()))
        stdin, stdout = StringIO("oops\n" + request + "\n"), StringIO()
        with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
            serve(bot)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0]["error"], "invalid_observation")
        self.assertEqual(lines[1]["action"]["kind"], "raise_to")


class ArenaTests(unittest.TestCase):
    def test_hidden_cards_never_enter_policy_observation(self):
        seen = []

        class Spy:
            def decide(self, obs):
                seen.append(obs)
                return Baseline("calling", 1).decide(obs)

        ids = ("p0", "p1", "p2", "p3", "p4", "p5")
        result = play_hand({pid: Spy() for pid in ids}, ids, dict.fromkeys(ids, 10000), 7)
        self.assertEqual(sum(result.payoffs.values()), 0)
        self.assertEqual(len(result.board), 5)
        for obs in seen:
            serialized = asdict(obs)
            self.assertEqual(len(serialized["hole_cards"]), 2)
            self.assertTrue(all("hole_cards" not in p for p in serialized["players"]))
            self.assertFalse(hasattr(obs, "deck"))

    def test_pokerkit_side_pots_and_short_all_in_no_reopen(self):
        auto = tuple(a for a in Automation if a not in (Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
        state = NoLimitTexasHoldem.create_state(auto, True, 0, (5, 10), 10, (1000, 150, 1000), 3)
        for cards in ("AsAh", "KsKh", "QsQh"):
            state.deal_hole(cards)
        state.complete_bet_or_raise_to(100)
        state.check_or_call()
        state.complete_bet_or_raise_to(150)
        obs = observation(state, ("p0", "p1", "p2"), "t", "h", (), 10)
        self.assertIsNone(obs.legal.min_raise_to)
        self.assertEqual(obs.legal.call_amount, 50)
        state = NoLimitTexasHoldem.create_state(auto, True, 0, (5, 10), 10, (50, 100, 200), 3)
        for cards in ("AsAh", "KsKh", "QsQh"):
            state.deal_hole(cards)
        state.complete_bet_or_raise_to(200)
        state.check_or_call()
        state.check_or_call()
        for burn, board in zip(("4c", "5c", "6c"), ("2c3d7h", "8s", "9c")):
            state.burn_card(burn)
            state.deal_board(board)
        self.assertEqual(state.stacks, [150, 100, 100])

    def test_complete_hands_replay_and_chip_conservation_2_5_6_players(self):
        for n in (2, 5, 6):
            ids = tuple(f"p{i}" for i in range(n))
            def run():
                policies = {pid: make_policy("v1" if i == 0 else ("random", "calling", "tight")[i % 3],
                            BotConfig(samples=128), 99 + i) for i, pid in enumerate(ids)}
                return play_hand(policies, ids, {pid: (i + 1) * 130 for i, pid in enumerate(ids)}, 19)
            a, b = run(), run()
            self.assertEqual(a.payoffs, b.payoffs)
            self.assertEqual(a.history, b.history)
            self.assertEqual(a.board, b.board)
            self.assertEqual(sum(a.payoffs.values()), 0)
            self.assertFalse(any(d.fallback for _, d in a.decisions))

    def test_runout_does_not_depend_on_policy_randomness(self):
        ids = ("a", "b", "c", "d", "e")
        a = play_hand({pid: Baseline("calling", 2) for pid in ids}, ids, dict.fromkeys(ids, 10000), 77)
        b = play_hand({pid: Baseline("random", 4) for pid in ids}, ids, dict.fromkeys(ids, 10000), 77)
        if len(b.board) == 5:
            self.assertEqual(a.board, b.board)
        else:
            self.assertEqual(a.board[:len(b.board)], b.board)

    def test_single_table_eliminations_and_paired_evaluation(self):
        result = simulate(5, 8, 5, BotConfig(samples=128), carry_stacks=True, starting_stack=300)
        self.assertTrue(result["chips_conserved"])
        self.assertEqual(sum(result["last_stacks"].values()), 1500)
        report = evaluate(2, 2, 1, 11, BotConfig(samples=128))
        self.assertEqual(report["hands_per_variant"], 4)
        self.assertEqual(len(report["block_differences_bb_per_hand"]), 2)
        self.assertEqual(report["hero_latency"]["fallbacks"], 0)


if __name__ == "__main__":
    unittest.main()

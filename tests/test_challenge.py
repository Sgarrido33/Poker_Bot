from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerfight.arena import make_policy, play_hand
from pokerfight.arena import observation
from pokerkit import Automation, NoLimitTexasHoldem
from pokerfight.campaign import run_campaign
from pokerfight.evaluation import bootstrap_interval, environment, evaluate, simulate
from pokerfight.replay import replay_worst
from pokerfight.strategy import BotConfig
from pokerfight.domain import LegalActions, Observation, Player

ROOT = Path(__file__).resolve().parents[1]


class ChallengeTests(unittest.TestCase):
    def test_cheap_all_in_is_priced_before_starting_hand_chart(self):
        auto = tuple(a for a in Automation if a not in (Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
        state = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, (100, 51), 2)
        state.deal_hole("AsAh", 0)
        state.deal_hole("7s2h", 1)
        obs = observation(state, ("villain", "hero"), "test", "1", (), 100)
        old = make_policy("v1", BotConfig(samples=1000), 27).decide(obs)
        new = make_policy("v2", BotConfig(samples=1000), 27).decide(obs)
        self.assertEqual(old.action.kind, "fold")
        self.assertEqual(new.action.kind, "call")
        self.assertEqual(new.equity.eligible_pot, 102)
        self.assertEqual(old.equity, new.equity)
        self.assertTrue(new.action.is_legal(obs))
        state.check_or_call()
        self.assertTrue(state.status)

    def test_badly_priced_all_in_still_folds(self):
        obs = Observation("t", "h", "hero", 1,
            (Player("hero", 9900, 100, 100), Player("villain", 0, 10000, 10000)),
            ("7s", "2h"), (), 100, LegalActions(False, True, 9900))
        result = make_policy("v2", BotConfig(samples=1000), 27).decide(obs)
        self.assertEqual(result.action.kind, "fold")
        self.assertEqual(result.reason, "preflop:all_in_price_fold")

    def test_rule_rivals_play_legal_complete_hands(self):
        ids = ("hero", "a", "b", "c", "d", "e")
        for kind in ("tag", "lag", "pressure"):
            policies = {pid: make_policy(kind if pid != "hero" else "v1", BotConfig(samples=128), i + 2)
                        for i, pid in enumerate(ids)}
            result = play_hand(policies, ids, dict.fromkeys(ids, 800), 8, trace_player_id="hero")
            self.assertEqual(sum(result.payoffs.values()), 0)
            self.assertFalse(any(d.fallback for _, d in result.decisions))
            for entry in result.trace:
                self.assertEqual(entry["observation"]["hero_id"], "hero")
                self.assertTrue(all("hole_cards" not in p for p in entry["observation"]["players"]))

    def test_identical_policies_produce_zero_paired_difference(self):
        report = evaluate(3, 3, 2, 93, BotConfig(samples=128), ("tag", "lag"), baseline="v1")
        self.assertEqual(report["block_differences_bb_per_hand"], [0, 0, 0])
        self.assertEqual(report["paired_block_bootstrap_95_interval"], [0, 0])

    def test_bootstrap_resamples_blocks_deterministically(self):
        self.assertIsNone(bootstrap_interval([1], 2))
        self.assertEqual(bootstrap_interval([2, 2, 2], 9), [2, 2])
        self.assertEqual(bootstrap_interval([1, -3, 4, 7], 11), bootstrap_interval([1, -3, 4, 7], 11))

    def test_button_advances_to_next_survivor(self):
        result = simulate(6, 30, 82, BotConfig(samples=128), ("calling",), True, 300,
                          blind_interval=2, initial_rotation=2)
        ids = ("hero",) + tuple(f"opponent_{i}" for i in range(1, 6))
        buttons = result["button_history"]
        self.assertEqual(buttons[0], ids[1])
        self.assertGreater(len(result["eliminated"]), 0)
        for hand in range(1, len(buttons)):
            active = {pid for pid in ids if result["eliminated_at_hand"].get(pid, 10**9) >= hand}
            previous = ids.index(buttons[hand - 1])
            expected = next(ids[(previous + d) % 6] for d in range(1, 7) if ids[(previous + d) % 6] in active)
            self.assertEqual(buttons[hand], expected)
        self.assertTrue(result["chips_conserved"])

    def test_trace_and_replay_include_prior_hand_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(ROOT))
            report = evaluate(3, 2, 3, 27, BotConfig(samples=128), ("tag", "pressure"), "tag",
                              trace_path=str(Path(directory) / "trace.jsonl"))
            report["environment"] = environment()
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = replay_worst(str(path))
            self.assertTrue(result["matched"])
            self.assertTrue(result["same_source"])
            lines = [json.loads(line) for line in (Path(directory) / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), 36)
            self.assertTrue(all(e["observation"]["hero_id"] == "hero" for line in lines for e in line["trace"]))

    def test_campaign_saves_plan_before_measuring_and_refuses_changed_plan(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(ROOT))
            with patch("pokerfight.campaign.evaluate", side_effect=RuntimeError("stop before measuring")):
                with self.assertRaises(RuntimeError):
                    run_campaign(directory, blocks=1, hands_per_block=1)
            plan = json.loads((Path(directory) / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["seed_namespace"], "challenge-v1-development")
            with self.assertRaises(ValueError):
                run_campaign(directory, phase="holdout", blocks=1, hands_per_block=1)


if __name__ == "__main__":
    unittest.main()

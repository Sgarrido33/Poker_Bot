import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest
from dataclasses import asdict

from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.arena import Baseline, make_policy, observation, play_hand
from pokerfight.domain import Action, LegalActions, Observation, Player
from pokerfight.external_opponents import FullhouseOpponent, fullhouse_action, fullhouse_state, verify_fullhouse
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig

BASE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("numpy"), "install requirements-evaluation.txt")
class ExternalOpponentTests(unittest.TestCase):
    def test_artifacts_and_control_are_intact(self):
        verify_control()
        source = verify_fullhouse()
        self.assertEqual(source["commit"], "e504793d480b1b975f25258d25939b45c6dbd5a4")
        self.assertEqual(source["original_files"]["data/deep_cfr_model.npz"], source["runtime_files"]["data/deep_cfr_model.npz"])

    def test_no_global_rng_mutation_or_shared_stream(self):
        import numpy as np
        global_before = random.getstate()
        a, b, control = (FullhouseOpponent(123) for _ in range(3))
        probabilities = np.array([.3, .7, 0, 0, 0])
        for _ in range(20):
            b.sample(probabilities)
            b.sample(probabilities)
            self.assertEqual(a.sample(probabilities), control.sample(probabilities))
        self.assertEqual(global_before, random.getstate())

    def test_private_cards_do_not_change_observation_or_external_decision(self):
        def state(others):
            auto = tuple(a for a in Automation if a not in (Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
            s = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, (10000,) * 5, 5)
            for hole in others + ("AsAh", "2c3d", "4h5s"):
                s.deal_hole(hole)
            return s
        ids = ("a", "b", "hero", "c", "d")
        a = observation(state(("KsKh", "QsQh")), ids, "t", "h", (), 100)
        b = observation(state(("6c7c", "8s9s")), ids, "t", "h", (), 100)
        self.assertEqual(a.hero_id, "hero")
        self.assertEqual(asdict(a), asdict(b))
        translated = fullhouse_state(a)
        self.assertEqual(translated, fullhouse_state(b))
        self.assertEqual(set(translated) & {"deck", "burns", "runout", "hole_cards"}, set())
        self.assertTrue(all("your_cards" not in p and "hole_cards" not in p for p in translated["players"]))
        self.assertEqual(FullhouseOpponent(9).decide(a).action, FullhouseOpponent(9).decide(b).action)

    def test_allin_call_and_raise_translation_use_authoritative_rights(self):
        obs = Observation("t", "h", "hero", 1,
            (Player("hero", 100, 100, 100), Player("v", 0, 150, 150)),
            ("As", "Ah"), (), 100, LegalActions(False, True, 50))
        action, adjustment = fullhouse_action({"action": "all_in"}, obs)
        self.assertEqual(action, Action("call"))
        self.assertIsNotNone(adjustment)
        with self.assertRaisesRegex(ValueError, "Illegal"):
            fullhouse_action({"action": "raise", "amount": 200}, obs)
        short = Observation("t", "h", "hero", 1,
            (Player("hero", 75, 0, 0), Player("v", 0, 100, 100)),
            ("As", "Ah"), (), 100, LegalActions(False, True, 75))
        self.assertEqual(fullhouse_action({"action": "all_in"}, short)[0], Action("call"))

    def test_complete_hands_public_history_and_upstream_parity(self):
        """Reference runs ORIGINAL pinned files in a separate Python process.

        Real PokerKit trajectories exercise dealer, full/short calls, all streets,
        and 2/5/6 seats. These are rule/adapter checks, not campaign observations.
        """
        upstream = BASE / "research/external_sources/fullhouse"
        if not (upstream / "bot/bot.py").exists():
            self.skipTest("original source checkout is needed for reference parity")
        seen = []

        class Spy:
            def __init__(self, seed):
                self.policy = FullhouseOpponent(seed)

            def decide(self, obs):
                seen.append(obs)
                return self.policy.decide(obs)

        for n in (2, 5, 6):
            for depth in (800, 10000):
                for deck in range(12):
                    ids = tuple(f"p{i}" for i in range(n))
                    policies = {p: Spy(i + 1) if i % 2 else Baseline("calling", i) for i, p in enumerate(ids)}
                    result = play_hand(policies, ids, dict.fromkeys(ids, depth), 500 + deck)
                    self.assertEqual(sum(result.payoffs.values()), 0)
        self.assertEqual({o.street for o in seen}, {"preflop", "flop", "turn", "river"})
        # Bound subprocess input without excluding any street or table format.
        chosen = []
        buckets = {}
        for obs in seen:
            key = (len(obs.players), obs.street, obs.hero.stack > 1200)
            buckets.setdefault(key, []).append(obs)
        for values in buckets.values():
            chosen.extend(values[:4])
        payload = [{"state": fullhouse_state(o), "seed": 317 + i} for i, o in enumerate(chosen)]
        script = '''import json,sys
sys.path.insert(0,sys.argv[1])
from bot import bot
for row in json.load(sys.stdin):
    bot._RNG.seed(row['seed'])
    state=row['state']
    proposal=bot._push_fold(state) if state['street']=='preflop' else None
    if proposal is None:
        p=bot._apply_legal_mask(bot._DEEP_CFR.get_strategy(state),state)
        proposal=bot._to_engine_action(bot._sample(p),state)
    print(json.dumps(proposal))
'''
        response = subprocess.run([sys.executable, "-c", script, str(upstream)], input=json.dumps(payload),
                                  text=True, capture_output=True, check=True)
        reference = [json.loads(s) for s in response.stdout.splitlines()]
        self.assertGreater(len(reference), 30)
        for i, (obs, expected) in enumerate(zip(chosen, reference, strict=True)):
            actual = FullhouseOpponent(317 + i).decide(obs)
            self.assertEqual(actual.action, fullhouse_action(expected, obs)[0])
            self.assertFalse(actual.fallback)

    def test_unsupported_blinds_ante_or_incomplete_history_fail(self):
        observed = []

        class Capture:
            def decide(self, obs):
                observed.append(obs)
                return Baseline("calling", 0).decide(obs)

        ids = ("a", "b", "c", "d", "e")
        play_hand(dict.fromkeys(ids, Capture()), ids, dict.fromkeys(ids, 1000), 11, ante=10)
        with self.assertRaisesRegex(ValueError, "no ante"):
            fullhouse_state(observed[0])
        play_hand(dict.fromkeys(ids, Capture()), ids, dict.fromkeys(ids, 1000), 11, big_blind=200)
        with self.assertRaisesRegex(ValueError, "fixed 50/100"):
            fullhouse_state(observed[-1])


if __name__ == "__main__":
    unittest.main()

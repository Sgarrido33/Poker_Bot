from __future__ import annotations

import importlib.util
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import patch

from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.arena import Baseline, observation, play_hand
from pokerfight.domain import Action
from pokerfight.noregrets_opponent import NoRegretsOpponent, NoRegretsTableOpponent
from pokerfight.strategy import Decision
from pokerfight.strategy import Decision

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "research/noregrets_integration_20261028"
ADAPTER = INTEGRATION / "artifacts/noregrets-pokerfight-adapter.exe"


def make_state(n: int, stacks: tuple[int, ...], holes: tuple[str, ...]):
    auto = tuple(a for a in Automation if a not in (
        Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
    state = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, stacks, n)
    for seat, cards in enumerate(holes):
        state.deal_hole(cards, seat)
    return state


@unittest.skipUnless(ADAPTER.exists(), "build research/noregrets_integration_20261028 first")
class NoRegretsAdapterTests(unittest.TestCase):
    def _opponent(self, n: int):
        # Smoke blueprints are isolated local training artifacts; no upstream model.
        name = {2: "noregrets_2max_1k.json", 5: "noregrets_5max_1k.json",
                6: "noregrets_6max_1k.json"}[n]
        return NoRegretsOpponent(123, INTEGRATION / "profiles" / name, timeout_s=20)

    def test_public_observation_replay_2_5_6_and_runtime_close(self):
        for n in (2, 5, 6):
            with self.subTest(players=n):
                ids = tuple(f"p{i}" for i in range(n))
                holes = tuple(("AsAh" if i == 0 else f"{rank}{suit}{rank2}{suit2}")
                              for i, (rank, suit, rank2, suit2) in enumerate(
                                  [("K", "s", "K", "h"), ("Q", "s", "Q", "h"),
                                   ("J", "s", "J", "h"), ("T", "s", "T", "h"),
                                   ("9", "s", "9", "h"), ("8", "s", "8", "h")][:n]))
                stacks = tuple(10000 for _ in range(n))
                state = make_state(n, stacks, holes)
                obs = observation(state, ids, "adapter", "hand-1", (), 100)
                opponent = self._opponent(n)
                try:
                    result = opponent.decide(obs)
                    self.assertTrue(result.action.is_legal(obs))
                    self.assertIn(result.external["lookup_stats_delta"][0][0], (0, 1))
                    self.assertEqual(opponent.telemetry["decisions"], 1)
                finally:
                    opponent.close()

    def test_unequal_stacks_and_eliminated_table_cardinality(self):
        ids = tuple(f"p{i}" for i in range(5))
        holes = ("AsAh", "KsKh", "QsQh", "JsJh", "TsTh")
        state = make_state(5, (800, 1200, 1800, 400, 1500), holes)
        obs = observation(state, ids, "adapter", "unequal", (), 100)
        opponent = self._opponent(5)
        try:
            result = opponent.decide(obs)
            self.assertTrue(result.action.is_legal(obs))
            self.assertTrue(result.external["profile_transfer"])
            self.assertEqual(result.external["observed_start_stacks"], [800, 1200, 1800, 400, 1500])
        finally:
            opponent.close()
        # A new hand after eliminations is a smaller game and selects its own
        # matching blueprint rather than retaining dead seats from the old hand.
        heads_up = make_state(2, (500, 700), ("AsAh", "KsKh"))
        obs2 = observation(heads_up, ("winner", "rival"), "adapter", "after-elimination", (), 100)
        hu = self._opponent(2)
        try:
            self.assertTrue(hu.decide(obs2).action.is_legal(obs2))
        finally:
            hu.close()

    def test_table_wrapper_switches_and_closes_profile_on_bustout(self):
        wrapper = NoRegretsTableOpponent(88, ROOT / "research/noregrets_training_20261028/profiles_index.json", timeout_s=20)
        try:
            five = observation(make_state(5, (10000,) * 5,
                ("AsAh", "KsKh", "QsQh", "JsJh", "TsTh")), tuple(f"p{i}" for i in range(5)), "t", "5", (), 100)
            two = observation(make_state(2, (10000,) * 2, ("AsAh", "KsKh")), ("winner", "rival"), "t", "2", (), 100)
            self.assertTrue(wrapper.decide(five).action.is_legal(five))
            self.assertEqual(wrapper._active_players, 5)
            self.assertTrue(wrapper.decide(two).action.is_legal(two))
            self.assertEqual(wrapper._active_players, 2)
            self.assertEqual(wrapper.telemetry["profile_switches"], 2)
        finally:
            wrapper.close()

    def test_write_watchdog_and_reader_queue_are_bound_to_process(self):
        obs = observation(make_state(5, (10000,) * 5,
            ("AsAh", "KsKh", "QsQh", "JsJh", "TsTh")), tuple(f"p{i}" for i in range(5)), "t", "watchdog", (), 100)
        policy = self._opponent(5)
        stopped = threading.Event()

        class PipeIn:
            def write(self, _text):
                stopped.wait(5)
            def flush(self):
                stopped.wait(5)
            def close(self):
                stopped.set()

        class PipeOut:
            def __iter__(self): return self
            def __next__(self):
                stopped.wait(5)
                raise StopIteration
            def close(self): stopped.set()

        class FakeProcess:
            def __init__(self):
                self.stdin, self.stdout = PipeIn(), PipeOut()
            def poll(self): return None if not stopped.is_set() else 0
            def kill(self): stopped.set()
            def wait(self, timeout=None):
                stopped.set()
                return 0

        try:
            with patch("pokerfight.noregrets_opponent.subprocess.Popen", return_value=FakeProcess()):
                policy.timeout_s = 0.15
                with self.assertRaises(TimeoutError):
                    policy.decide(obs)
            self.assertEqual(policy.telemetry["timeouts"], 1)
            self.assertIsNone(policy._process)

            old_queue, new_queue = queue.Queue(), queue.Queue()
            policy._lines = new_queue
            local_stop = threading.Event()
            class OldOut:
                def __iter__(self): return self
                def __next__(self):
                    local_stop.wait(1)
                    raise StopIteration
                def close(self): local_stop.set()
            class OldProcess:
                stdout = OldOut()
            reader = threading.Thread(target=policy._read_stdout, args=(OldProcess(), old_queue), daemon=True)
            reader.start()
            local_stop.set()
            reader.join(1)
            self.assertIsNone(old_queue.get_nowait())
            self.assertTrue(new_queue.empty())
        finally:
            policy.close()

    def test_hidden_opponent_cards_do_not_change_request_or_decision(self):
        ids = tuple(f"p{i}" for i in range(5))
        a = observation(make_state(5, (10000,) * 5,
                                  ("AsAh", "KsKh", "QsQh", "JsJh", "TsTh")), ids, "t", "h", (), 100)
        b = observation(make_state(5, (10000,) * 5,
                                  ("2c3d", "4c5d", "QsQh", "6c7d", "8c9d")), ids, "t", "h", (), 100)
        self.assertEqual(a, b)
        policy = self._opponent(5)
        try:
            self.assertEqual(policy.decide(a).action, policy.decide(b).action)
        finally:
            policy.close()

    def test_sidepot_call_layers_and_illegal_observation_fail_loudly(self):
        from pokerfight.domain import LegalActions, Observation, Player
        obs = Observation("t", "sidepot", "hero", 2,
            (Player("hero", 20, 80, 280), Player("short", 0, 60, 260),
             Player("deep", 100, 100, 300)), ("As", "Ah"), (), 100,
            LegalActions(False, True, 20))
        layers = obs.call_pots()
        self.assertTrue(all("hero" in pot.eligible for pot in layers))
        self.assertGreater(sum(pot.amount for pot in layers), 0)
        policy = self._opponent(5)
        try:
            with self.assertRaisesRegex(ValueError, "player count"):
                policy.decide(obs)
        finally:
            policy.close()

    def test_short_stack_call_is_capped_by_remaining_stack(self):
        captured = []
        class ShortCaller:
            def decide(self, obs):
                captured.append(obs)
                return Decision(Action("fold"), "capture", 0, False)
        class Raiser:
            def decide(self, obs):
                action = Action("raise_to", 500)
                self_action = action if action.is_legal(obs) else Action("call" if obs.legal.call_amount else "check")
                return Decision(self_action, "raise", 0, False)

        play_hand({"short": ShortCaller(), "deep": Raiser()}, ("short", "deep"),
                  {"short": 150, "deep": 1000}, 419, hand_id="short-call")
        obs = captured[0]
        self.assertEqual(obs.hero_id, "short")
        self.assertEqual(obs.legal.call_amount, 50)
        self.assertEqual(obs.hero.stack, 50)
        self.assertGreater(max(p.street_bet for p in obs.players) - obs.hero.street_bet,
                           obs.legal.call_amount)
        policy = self._opponent(2)
        try:
            result = policy.decide(obs)
            self.assertTrue(result.action.is_legal(obs))
        finally:
            policy.close()

    def test_raise_bounds_close_when_other_player_is_all_in(self):
        from pokerfight.domain import PublicAction
        state = make_state(2, (800, 300), ("AsAh", "KsKh"))
        self.assertEqual(state.actor_index, 1)  # button/SB is first heads-up
        state.complete_bet_or_raise_to(300)  # short SB all-in raise
        history = (PublicAction("0", "short", "preflop", "raise_to", 300, True),)
        obs = observation(state, ("hero", "short"), "test", "no-other-can-bet", history, 100)
        self.assertEqual(obs.hero.stack, 700)
        self.assertEqual(obs.legal.call_amount, 200)
        self.assertIsNone(obs.legal.min_raise_to)
        self.assertIsNone(obs.legal.max_raise_to)
        policy = self._opponent(2)
        try:
            result = policy.decide(obs)
            self.assertTrue(result.action.is_legal(obs))
            self.assertNotEqual(result.action.kind, "raise_to")
        finally:
            policy.close()

    def test_full_public_history_replay_through_postflop(self):
        captured = []
        class Capture:
            def decide(self, obs):
                captured.append(obs)
                return Baseline("calling", 4).decide(obs)

        ids = tuple(f"p{i}" for i in range(5))
        play_hand(dict.fromkeys(ids, Capture()), ids, dict.fromkeys(ids, 800), 271828,
                  hand_id="postflop-replay")
        observed = next((o for o in captured if o.street in ("flop", "turn", "river") and len(o.history) >= 5), None)
        self.assertIsNotNone(observed, "checkdown should expose a multi-action postflop observation")
        policy = self._opponent(5)
        try:
            result = policy.decide(observed)
            self.assertTrue(result.action.is_legal(observed))
            self.assertIn(result.external["fallback_reason"], ("none", "unseen_infoset", "zero_mass", "menu_mismatch"))
        finally:
            policy.close()


if __name__ == "__main__":
    unittest.main()

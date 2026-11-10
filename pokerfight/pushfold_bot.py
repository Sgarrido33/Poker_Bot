"""v8 candidate: solved push/fold charts preflop at <=15 effective bb, v2 elsewhere.

Covered spots: unopened pot (shove or fold) and a single raise with no callers
(call a shove / reshove over an open, or fold). Limped and multi-raise pots,
deeper stacks and every postflop decision use the frozen v2 control.
"""
from __future__ import annotations

from time import perf_counter

from .controls import ControlBot
from .domain import Action, Observation, safe_action
from .cards import hand_class
from .pushfold import call_freq, shove_freq
from .strategy import Decision, raise_to

MAX_BB = 15.0
SIX_MAX = {"UTG": 0, "HJ": 1, "CO": 2, "BTN": 3, "SB": 4, "BB": 5}


def position6(obs: Observation, player_id: str) -> int:
    n = len(obs.players)
    index = next(i for i, p in enumerate(obs.players) if p.player_id == player_id)
    offset = (index - obs.button_index) % n
    if n == 2:
        return (4, 5)[offset]
    middle = {3: (), 4: ("CO",), 5: ("HJ", "CO"), 6: ("UTG", "HJ", "CO")}[n]
    return SIX_MAX[(("BTN", "SB", "BB") + middle)[offset]]


def total(player) -> int:
    return player.stack + player.street_bet


def chart_action(obs: Observation, isolate: bool = False) -> tuple[Action, str] | None:
    if obs.street != "preflop":
        return None
    hero = obs.hero
    hand = hand_class(obs.hole_cards)
    voluntary = [e for e in obs.history if e.street == "preflop" and e.kind in ("call", "raise_to")]
    shove = raise_to(obs, hero.stack + hero.street_bet)
    if not voluntary:
        effective = min(total(hero), max(total(p) for p in obs.opponents)) / obs.big_blind
        if effective > MAX_BB or shove is None:
            return None
        if shove_freq(hand, position6(obs, obs.hero_id), effective) >= 0.5:
            return shove, f"v8:first_in_shove:{effective:.1f}bb"
        return safe_action(obs), f"v8:first_in_fold:{effective:.1f}bb"
    if isolate and all(e.kind == "call" for e in voluntary):
        # v8b: limpers. Shove over them with hands that would call a shove from
        # the first limper's seat; otherwise leave the spot to v2.
        limper = next(p for p in obs.players if p.player_id == voluntary[0].player_id)
        effective = min(total(hero), max(total(p) for p in obs.opponents)) / obs.big_blind
        p, q = position6(obs, limper.player_id), position6(obs, obs.hero_id)
        if effective > MAX_BB or shove is None or p >= q or call_freq(hand, p, q, effective) < 0.5:
            return None
        return shove, f"v8:isolation_shove:{effective:.1f}bb"
    if len(voluntary) != 1 or voluntary[0].kind != "raise_to" or obs.legal.call_amount == 0:
        return None
    raiser = next(p for p in obs.players if p.player_id == voluntary[0].player_id)
    effective = min(total(hero), total(raiser)) / obs.big_blind
    if effective > MAX_BB:
        return None
    p, q = position6(obs, raiser.player_id), position6(obs, obs.hero_id)
    if p >= q:
        return None
    if call_freq(hand, p, q, effective) < 0.5:
        return safe_action(obs), f"v8:facing_raise_fold:{effective:.1f}bb"
    # A shove (or a raise leaving the raiser nothing behind) is simply called.
    if raiser.stack == 0 or shove is None or obs.legal.call_amount >= hero.stack:
        return Action("call"), f"v8:call_shove:{effective:.1f}bb"
    return shove, f"v8:reshove:{effective:.1f}bb"


class PushFoldBot(ControlBot):
    isolate = False
    confirm_calls = False

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        try:
            chosen = chart_action(obs, self.isolate)
            if chosen is not None and chosen[0].is_legal(obs):
                if self.confirm_calls and chosen[1].startswith("v8:call_shove"):
                    # v8c: a solved call must also beat the price against the
                    # opponent's modelled range (v2 equity), else v2 decides.
                    control = super().decide(obs)
                    if control.action.kind == "call":
                        return Decision(control.action, "v8:call_shove_confirmed", control.elapsed_ms,
                                        control.fallback, control.equity)
                    return control
                return Decision(chosen[0], chosen[1], (perf_counter() - started) * 1000, False)
        except Exception:
            pass  # any chart problem falls back to the full v2 decision
        return super().decide(obs)


class IsolationPushFoldBot(PushFoldBot):
    isolate = True


class ConfirmedPushFoldBot(PushFoldBot):
    confirm_calls = True

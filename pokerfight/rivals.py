"""Independent rule opponents for local development, not tournament benchmarks.

TAG/LAG use uniform unknown hands rather than the candidate's opponent model.
Pressure deliberately tests excessive folding. All use the public contract.
"""
from __future__ import annotations

from functools import lru_cache
import random
from time import perf_counter

from .cards import CARD_INDEX
from .domain import Action, Observation, safe_action
from .equity import COMBOS, WeightedRange, estimate
from .preflop import BLIND_DEFEND, DEFEND, OPEN_RANGES, PREMIUM, in_range, warm_charts
from .strategy import Decision, raise_to


@lru_cache(maxsize=64)
def uniform_range(known: tuple[int, ...]) -> WeightedRange:
    blocked = set(known)
    return WeightedRange.create([(pair, 1.0) for pair in COMBOS if not blocked.intersection(pair)])


class RuleOpponent:
    def __init__(self, kind: str, seed: int, samples: int = 256):
        if kind not in ("tag", "lag", "pressure"):
            raise ValueError(f"Rival desconocido: {kind}")
        self.kind = kind
        self.rng = random.Random(seed)
        self.samples = samples
        warm_charts()

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        cost = obs.legal.call_amount
        highest = max(p.street_bet for p in obs.players)
        action = safe_action(obs)
        equity = None
        if obs.street == "preflop":
            unopened = highest <= obs.big_blind
            premium = in_range(obs.hole_cards, PREMIUM)
            opening = OPEN_RANGES[obs.position if self.kind == "tag" else "BTN"]
            if premium or (unopened and in_range(obs.hole_cards, opening)):
                action = raise_to(obs, max(2.5 * obs.big_blind, 3 * highest)) or Action("call" if cost else "check")
            elif self.kind == "pressure" and unopened and self.rng.random() < 0.50:
                action = raise_to(obs, 3 * obs.big_blind) or action
            elif cost == 0:
                action = Action("check")
            else:
                defending = DEFEND if self.kind == "tag" else BLIND_DEFEND
                limit = (4 if self.kind == "tag" else 6) * obs.big_blind
                if in_range(obs.hole_cards, defending) and cost <= limit:
                    action = Action("call")
        else:
            uniform = uniform_range(tuple(sorted(CARD_INDEX[c] for c in obs.hole_cards + obs.board)))
            equity = estimate(obs, {p.player_id: uniform for p in obs.opponents}, self.rng,
                              self.samples, started + 0.5)
            strength = max(0.0, equity.equity - equity.standard_error)
            odds = cost / equity.eligible_pot
            value_threshold = (0.64 if self.kind == "tag" else 0.56) if len(obs.opponents) == 1 else (0.52 if self.kind == "tag" else 0.45)
            bluff = (cost == 0 and self.rng.random() < {"tag": 0.04, "lag": 0.16, "pressure": 0.45}[self.kind])
            if strength >= max(value_threshold, odds + 0.12) or bluff:
                fraction = 0.60 if self.kind == "tag" else 0.85
                action = raise_to(obs, highest + fraction * (obs.pot + cost)) or Action("call" if cost else "check")
            elif not cost:
                action = Action("check")
            elif strength >= odds + (0.045 if self.kind == "tag" else 0.015):
                action = Action("call")
        if not action.is_legal(obs):
            raise RuntimeError(f"Acción ilegal del rival {self.kind}")
        return Decision(action, "rival:" + self.kind, (perf_counter() - started) * 1000, False, equity)

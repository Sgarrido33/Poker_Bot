"""First heuristic policy. Equity is a check-down estimate, not bet EV."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import random
from time import perf_counter

from .domain import Action, Observation, safe_action
from .equity import EquityResult, build_ranges, estimate
from .opponents import OpponentModel
from .preflop import BLIND_DEFEND, DEFEND, OPEN_RANGES, PREMIUM, SHORT_VALUE, in_range, warm_charts


@dataclass(frozen=True)
class BotConfig:
    samples: int = 4000
    budget_ms: int = 1600
    seed: int = 20261027
    confidence_cap: float = 0.35
    prior_observations: int = 40

    def __post_init__(self):
        if type(self.samples) is not int or self.samples < 1:
            raise ValueError("samples debe ser positivo")
        if type(self.budget_ms) is not int or not 1 <= self.budget_ms <= 3500:
            raise ValueError("budget_ms debe estar entre 1 y 3500")
        if not 0 <= self.confidence_cap <= 0.5 or self.prior_observations < 1:
            raise ValueError("Parámetros de confianza inválidos")


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    elapsed_ms: float
    fallback: bool
    equity: EquityResult | None = None
    search: dict | None = None

    def to_dict(self) -> dict:
        return {"action": self.action.to_dict(), "reason": self.reason,
                "elapsed_ms": round(self.elapsed_ms, 3), "fallback": self.fallback,
                "equity": asdict(self.equity) if self.equity else None,
                **({"search": self.search} if self.search is not None else {})}


def raise_to(obs: Observation, target: float) -> Action | None:
    if obs.legal.min_raise_to is None:
        return None
    # No need to wager more than any opponent can match, unless the legal
    # minimum itself is larger. The engine handles uncalled chip returns.
    effective_cap = max(p.stack + p.street_bet for p in obs.opponents)
    target = min(round(target), effective_cap)
    amount = max(obs.legal.min_raise_to, min(obs.legal.max_raise_to, target))
    return Action("raise_to", amount)


class PokerBot:
    def __init__(self, config: BotConfig | None = None):
        self.config = config or BotConfig()
        warm_charts()
        self.model = OpponentModel(self.config.confidence_cap, self.config.prior_observations)

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        deadline = started + self.config.budget_ms / 1000
        equity = None
        try:
            self.model.observe(obs.table_id, obs.hand_id, obs.history)
            key = f"{self.config.seed}|{obs.table_id}|{obs.hand_id}|{obs.hero_id}|{len(obs.history)}|{obs.street}"
            rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))
            ranges = build_ranges(obs, self.model, deadline)
            equity = estimate(obs, ranges, rng, self.config.samples, deadline)
            # Extremely small timed-out samples are not a strategy signal.
            if equity.samples < min(128, self.config.samples):
                raise TimeoutError("Muestra insuficiente dentro del presupuesto")
            action, reason = self.select(obs, equity)
            if not action.is_legal(obs):
                raise ValueError("La estrategia propuso una acción ilegal")
            return Decision(action, reason, (perf_counter() - started) * 1000, False, equity)
        except Exception as error:
            # Keep legal state errors outside this boundary: parse/validate first.
            return Decision(safe_action(obs), f"fallback:{type(error).__name__}:{error}",
                            (perf_counter() - started) * 1000, True, equity)

    def select(self, obs: Observation, equity: EquityResult) -> tuple[Action, str]:
        cost = obs.legal.call_amount
        if obs.street == "preflop" and cost > 0 and (
                cost == obs.hero.stack or all(p.stack == 0 for p in obs.opponents)):
            # Once hero is all-in, or all opponents are, starting-hand charts
            # must not veto a call with a favorable showdown price.
            conservative = max(0.0, equity.equity - equity.standard_error)
            if conservative >= cost / equity.eligible_pot:
                return Action("call"), "preflop:all_in_price_call"
            return safe_action(obs), "preflop:all_in_price_fold"
        return self.select_legacy(obs, equity)

    def select_legacy(self, obs: Observation, equity: EquityResult) -> tuple[Action, str]:
        cost = obs.legal.call_amount
        odds = cost / equity.eligible_pot
        conservative = max(0.0, equity.equity - equity.standard_error)
        highest = max(p.street_bet for p in obs.players)
        if obs.street == "preflop":
            raised = highest > obs.big_blind or any(e.kind == "raise_to" and e.street == "preflop" for e in obs.history)
            premium = in_range(obs.hole_cards, PREMIUM)
            if not raised and in_range(obs.hole_cards, OPEN_RANGES[obs.position]):
                limpers = sum(e.kind == "call" and e.street == "preflop" for e in obs.history)
                target = (2.5 + limpers) * obs.big_blind
                if obs.hero.stack / obs.big_blind <= 12 and in_range(obs.hole_cards, SHORT_VALUE):
                    target = obs.hero.stack + obs.hero.street_bet
                action = raise_to(obs, target)
                if action:
                    return action, "preflop:open_position_chart"
            if raised and premium and conservative >= odds + 0.12:
                action = raise_to(obs, max(3 * highest, highest + obs.pot * 0.75))
                if action:
                    return action, "preflop:premium_value_raise"
            if cost == 0:
                return Action("check"), "preflop:free_check"
            defend = BLIND_DEFEND if obs.position in ("BB", "BTN") else DEFEND
            if not premium and (not in_range(obs.hole_cards, defend) or cost > obs.big_blind * 8):
                return safe_action(obs), "preflop:outside_defend_chart"
            margin = 0.025 if premium else 0.055
        else:
            threshold = 0.64 if len(obs.opponents) == 1 else 0.55
            if conservative >= max(threshold, odds + 0.15):
                fraction = 0.75 if conservative >= 0.80 else 0.50
                action = raise_to(obs, highest + fraction * (obs.pot + cost))
                if action:
                    return action, "postflop:value_raise"
            if cost == 0:
                return Action("check"), "postflop:check"
            # Equity realization is uncertain before the river. This cushion is
            # a heuristic, not a model of future bets or opponent responses.
            margin = {"flop": 0.045, "turn": 0.025, "river": 0.0}[obs.street]
            margin += self.model.call_margin_adjustment(obs)
        if cost == obs.hero.stack or all(p.stack == 0 for p in obs.opponents):
            margin = 0.0
        if conservative >= odds + max(0.0, margin):
            return Action("call"), "call:equity_covers_price_and_margin"
        return safe_action(obs), "fold:price_exceeds_conservative_equity"


class LegacyPokerBot(PokerBot):
    """Frozen v1 selection rules for paired comparisons with the correction."""

    def select(self, obs: Observation, equity: EquityResult) -> tuple[Action, str]:
        return self.select_legacy(obs, equity)

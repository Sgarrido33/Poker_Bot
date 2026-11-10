"""v8d: bounded chart application and observation on every public request.

The historical v8/v8b/v8c implementations and tables remain unchanged.
Component variants are development ablations, not production defaults.
"""
from __future__ import annotations

from time import perf_counter

from .controls import ControlBot
from .pushfold_bot import chart_action, total
from .strategy import Decision, raise_to


def component(obs):
    if obs.street != "preflop":
        return None
    voluntary = [e for e in obs.history if e.street == "preflop" and e.kind in ("call", "raise_to")]
    if not voluntary:
        return "open"
    if len(voluntary) != 1 or voluntary[0].kind != "raise_to" or not obs.legal.call_amount:
        return None
    raiser = next(p for p in obs.players if p.player_id == voluntary[0].player_id)
    if raiser.stack == 0 or obs.legal.call_amount >= obs.hero.stack or raise_to(obs, total(obs.hero)) is None:
        return "call"
    return "reshove"


def response_scope_exceeded(obs):
    """Reject a nonterminal response whose wager can face a deeper opponent.

    Checking the whole response branch also avoids using its shallow-chart fold
    range in a state in which the corresponding shove is outside that model.
    Folded opponents cannot cover a wager and therefore do not impose a limit.
    """
    raises = [e for e in obs.history if e.street == "preflop" and e.kind == "raise_to"]
    raiser = next(p for p in obs.players if p.player_id == raises[0].player_id)
    modeled = min(total(obs.hero), total(raiser))
    exposed = min(total(obs.hero), max(total(p) for p in obs.opponents))
    return exposed > modeled


class GuardedPushFoldBot(ControlBot):
    components = frozenset(("open", "reshove", "call"))

    def decide(self, obs):
        started = perf_counter()
        # Deduplication in the frozen model makes delegation's second observe
        # harmless. This also works in serve, without arena end-of-hand hooks.
        self.model.observe(obs.table_id, obs.hand_id, obs.history)
        try:
            kind = component(obs)
            if kind not in self.components:
                return super().decide(obs)
            if kind == "reshove" and response_scope_exceeded(obs):
                decision = super().decide(obs)
                return Decision(decision.action, "v8d:scope_guard:" + decision.reason,
                                (perf_counter() - started) * 1000, decision.fallback, decision.equity)
            chosen = chart_action(obs)
            if chosen is None:
                return super().decide(obs)
            action, reason = chosen
            if not action.is_legal(obs):
                raise ValueError("Illegal chart action")
            return Decision(action, reason.replace("v8:", "v8d:", 1),
                            (perf_counter() - started) * 1000, False)
        except Exception as error:
            decision = super().decide(obs)
            # A table failure is visible even if delegation succeeds.
            return Decision(decision.action, f"v8d:chart_error:{type(error).__name__}:{decision.reason}",
                            (perf_counter() - started) * 1000, True, decision.equity)


class OpeningChartBot(GuardedPushFoldBot):
    components = frozenset(("open",))


class ReshoveChartBot(GuardedPushFoldBot):
    components = frozenset(("reshove",))


class CallingChartBot(GuardedPushFoldBot):
    components = frozenset(("call",))

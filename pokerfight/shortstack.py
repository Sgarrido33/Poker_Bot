"""v3 candidate: first-in commitment at <=8 effective bb, preflop only.

Hand-written chip-EV hypotheses, not Nash/GTO charts. No fold-equity estimate
is inferred from the check-down equity sampler. Defense remains v2.
"""
from dataclasses import dataclass
from types import MappingProxyType

from .domain import Observation, safe_action
from .preflop import in_range
from .strategy import PokerBot, raise_to

# Keys are active opponents still to act (all earlier actions must be folds).
# 4 also covers 5 opponents. Deeper pushes use a narrower range.
PUSH_5 = MappingProxyType({
    4: "44+,A8s+,ATo+,KJs+,KQo,QJs",
    3: "33+,A5s+,A9o+,KTs+,KQo,QJs,JTs",
    2: "22+,A2s+,A7o+,K9s+,KTo+,QTs+,QJo,JTs",
    1: "22+,A2s+,A2o+,K2s+,K8o+,Q8s+,QTo+,J8s+,JTo,T8s+,98s,87s",
})
PUSH_8 = MappingProxyType({
    4: "55+,ATs+,AJo+,KQs",
    3: "44+,A8s+,ATo+,KJs+,KQo,QJs",
    2: "22+,A2s+,A8o+,KTs+,KJo+,QTs+,JTs",
    1: "22+,A2s+,A5o+,K7s+,KTo+,Q9s+,QJo,J9s+,T9s",
})


@dataclass(frozen=True)
class PreflopContext:
    players: int
    position: str
    opponents: int
    effective_bb: float
    call_bb: float
    price: float
    situation: str


def context(obs: Observation) -> PreflopContext:
    highest = max(p.street_bet for p in obs.players)
    events = [e for e in obs.history if e.street == "preflop"]
    raised = highest > obs.big_blind or any(e.kind == "raise_to" for e in events)
    called = any(e.kind == "call" for e in events)
    # Max rival coverage is the maximum amount hero can contest. A tiny third
    # player must not turn a deep confrontation with another player into a push.
    effective = min(obs.hero.stack + obs.hero.street_bet,
                    max(p.stack + p.street_bet for p in obs.opponents))
    return PreflopContext(len(obs.players), obs.position, len(obs.opponents),
        effective / obs.big_blind, obs.legal.call_amount / obs.big_blind,
        obs.legal.call_amount / sum(p.amount for p in obs.call_pots()),
        "raised" if raised else "limped" if called else "first_in")


class ShortStackBot(PokerBot):
    def select(self, obs, equity):
        # Keep v2's price regression ahead of every chart, including v3 charts.
        cost = obs.legal.call_amount
        if obs.street != "preflop" or (cost > 0 and (
                cost == obs.hero.stack or all(p.stack == 0 for p in obs.opponents))):
            return super().select(obs, equity)
        ctx = context(obs)
        if ctx.situation == "first_in" and ctx.effective_bb <= 8 and obs.legal.min_raise_to is not None:
            charts = PUSH_5 if ctx.effective_bb <= 5 else PUSH_8
            if in_range(obs.hole_cards, charts[min(4, ctx.opponents)]):
                return raise_to(obs, obs.hero.stack + obs.hero.street_bet), "v3:short_first_in_push"
            return safe_action(obs), "v3:short_first_in_decline"
        return super().select(obs, equity)

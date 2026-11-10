"""Hypothetical preflop fold/call responses and one-step showdown payoffs.

These priors are deliberately distinct from observed public information.
Nonterminal action values omit reraises and later bets; they are proxies.
"""
from dataclasses import dataclass
import math

from .domain import Action, Observation, safe_action
from .strategy import raise_to


@dataclass(frozen=True)
class ResponsePrior:
    name: str
    threshold: float
    price_slope: float = .65


PRIORS = (ResponsePrior("selective", .72), ResponsePrior("balanced", .64),
          ResponsePrior("loose", .56))


def call_probability(score: float, price: float, prior: ResponsePrior,
                     adjustment: float = 0.0, previous_callers: int = 0) -> float:
    threshold = prior.threshold + prior.price_slope * (price - .20)
    threshold += .015 * previous_callers - adjustment
    # Positive support: a response never reveals a sampled hand as a fact.
    z = max(-40.0, min(40.0, 18 * (score - threshold)))
    return .02 + .96 / (1 + math.exp(-z))


def candidate_actions(obs: Observation, baseline: Action) -> tuple[Action, ...]:
    actions = [baseline, safe_action(obs)]
    highest = max(p.street_bet for p in obs.players)
    raised = highest > obs.big_blind or any(e.street == "preflop" and e.kind == "raise_to" for e in obs.history)
    if obs.legal.call_amount and (raised or baseline.kind == "call"):
        actions.append(Action("call"))
    small = raise_to(obs, 2 * obs.big_blind if not raised else 2 * highest)
    push = raise_to(obs, obs.hero.stack + obs.hero.street_bet)
    actions.extend(a for a in (small, push) if a is not None)
    return tuple(dict.fromkeys(a for a in actions if a.is_legal(obs)))


def showdown_return(contributions: list[int], folded: list[bool], ranks: list[int], hero_index: int) -> float:
    """All layers, dead money, ties and unmatched returns; no inaccessible pots."""
    result = 0.0
    previous = 0
    for level in sorted(set(contributions) - {0}):
        amount = (level - previous) * sum(c >= level for c in contributions)
        eligible = [i for i, c in enumerate(contributions) if c >= level and not folded[i]]
        if hero_index in eligible:
            best = max(ranks[i] for i in eligible)
            if ranks[hero_index] == best:
                result += amount / sum(ranks[i] == best for i in eligible)
        previous = level
    return result


class PreparedAction:
    """Compile the small response tree once, including every terminal pot layer.

    At most five opponents can owe chips, so there are at most 32 leaves.
    Card draws only choose a path and resolve its already prepared pots.
    """

    def __init__(self, obs: Observation, action: Action, adjustments: dict[str, float]):
        self.action = action
        self.hero = next(i for i, p in enumerate(obs.players) if p.player_id == obs.hero_id)
        self.fold = action.kind == "fold"
        self.contributions = [p.contribution for p in obs.players]
        self.folded = [p.folded for p in obs.players]
        self.investment = (action.amount - obs.hero.street_bet if action.kind == "raise_to"
                           else obs.legal.call_amount if action.kind == "call" else 0)
        self.contributions[self.hero] += self.investment
        target = obs.hero.street_bet + self.investment
        self.responses = []
        for distance in range(1, len(obs.players)):
            i = (self.hero + distance) % len(obs.players)
            p = obs.players[i]
            if p.folded:
                continue
            cost = min(p.stack, max(0, target - p.street_bet))
            self.responses.append((i, cost, adjustments.get(p.player_id, 0)))

        self.levels = []
        self.outcomes = []
        if self.fold:
            return
        states = [(self.contributions, self.folded, 0)]
        for i, cost, adjustment in self.responses:
            if cost == 0:
                continue  # Matched and all-in players never get a fold branch.
            prices, next_states = [], []
            for contributions, folded, callers in states:
                own_total = contributions[i] + cost
                eligible = sum(min(c, own_total) for j, c in enumerate(contributions) if j != i) + own_total
                prices.append((cost / eligible, callers))
                declined = folded.copy()
                declined[i] = True
                paid = contributions.copy()
                paid[i] += cost
                next_states.extend(((contributions, declined, callers), (paid, folded, callers + 1)))
            self.levels.append((i, adjustment, tuple(prices)))
            states = next_states
        for contributions, folded, _ in states:
            layers = []
            previous = 0
            for level in sorted(set(contributions) - {0}):
                amount = (level - previous) * sum(c >= level for c in contributions)
                if contributions[self.hero] >= level:
                    opponents = sum(1 << i for i, c in enumerate(contributions)
                                    if i != self.hero and c >= level and not folded[i])
                    layers.append((amount, opponents))
                previous = level
            self.outcomes.append(tuple(layers))

    def value(self, ranks: list[int], scores: list[float], uniforms: list[float], prior: ResponsePrior,
              rank_masks: tuple[int, int] | None = None) -> float:
        if self.fold:
            return 0.0
        leaf = 0
        for i, adjustment, prices in self.levels:
            price, callers = prices[leaf]
            called = uniforms[i] < call_probability(scores[i], price, prior, adjustment, callers)
            leaf = 2 * leaf + called
        better, tied = rank_masks if rank_masks is not None else relative_rank_masks(ranks, self.hero)
        returned = 0.0
        for amount, opponents in self.outcomes[leaf]:
            if not opponents & better:
                returned += amount / (1 + (opponents & tied).bit_count())
        return returned - self.investment


def relative_rank_masks(ranks: list[int], hero: int) -> tuple[int, int]:
    """Opponents beating/tying hero, shared across actions and response priors."""
    better = tied = 0
    for i, rank in enumerate(ranks):
        if i != hero:
            if rank > ranks[hero]:
                better |= 1 << i
            elif rank == ranks[hero]:
                tied |= 1 << i
    return better, tied

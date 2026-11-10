"""v5: sampled preflop responses with one opposing shove and learned recourse.

Hero's continuation uses a frozen public-information lookup learned on separate
worlds. It never compares the hidden ranks in the evaluation world to decide
whether to call. This is an approximate Bayesian rollout, not a poker solver.
"""
from dataclasses import dataclass
import math
import random
from time import perf_counter

import eval7

from .action_model import PRIORS, ResponsePrior, call_probability, candidate_actions, showdown_return
from .action_search import ActionSearchBot, Moments, search as fold_call_search
from .cards import CARD_INDEX, EVAL_CARDS
from .equity import COMBO_SCORES


@dataclass(frozen=True)
class ShovePrior:
    response: ResponsePrior
    threshold: float
    frequency: float

    @property
    def name(self):
        return self.response.name


# Deliberately broad sensitivity scenarios, fixed before playing new decks.
SHOVE_PRIORS = tuple(ShovePrior(p, t, f) for p, t, f in
                    zip(PRIORS, (.86, .80, .74), (.45, .60, .75)))


def response_probabilities(score, price, prior, adjustment=0., callers=0, can_shove=True):
    """Mutually exclusive fold, call, shove; no hidden showdown information."""
    continuing = call_probability(score, price, prior.response, adjustment, callers) if price else 1.
    shove = 0.
    if can_shove:
        z = max(-40., min(40., 20 * (score - prior.threshold + adjustment)))
        shove = continuing * prior.frequency * (.01 + .99 / (1 + math.exp(-z)))
    return 1 - continuing, continuing - shove, shove


def betting_state(obs):
    """Track the target last faced by each actor, including cumulative shorts."""
    target, increment, last_targets = obs.big_blind, obs.big_blind, {}
    for event in obs.history:
        if event.street != "preflop":
            continue
        if event.kind == "raise_to":
            if event.amount - target >= increment:
                increment = event.amount - target
            target = max(target, event.amount)
        last_targets[event.player_id] = target
    return target, increment, last_targets


def acted_since_full_raise(obs):
    """Players whose action has not reopened, possibly across short all-ins."""
    target, increment, last_targets = betting_state(obs)
    return {pid for pid, last in last_targets.items() if target - last < increment}, increment


class ResponseRollout:
    """One opposing all-in raise, with earlier callers revisited in turn order.

    No further raises or postflop bets are allowed in the abstraction. Side pots
    and uncalled returns are nevertheless settled with their full contributions.
    """
    def __init__(self, obs, action, adjustments):
        self.obs, self.action, self.adjustments = obs, action, adjustments
        self.hero = next(i for i, p in enumerate(obs.players) if p.player_id == obs.hero_id)
        self.initial = action.amount - obs.hero.street_bet if action.kind == "raise_to" else (
            obs.legal.call_amount if action.kind == "call" else 0)
        self.acted, self.increment = acted_since_full_raise(obs)
        _, _, self.last_targets = betting_state(obs)

    def value(self, ranks, scores, uniforms, prior, continuation, training=False):
        if self.action.kind == "fold":
            return 0., None
        obs, hero = self.obs, self.hero
        contributions = [p.contribution for p in obs.players]
        bets = [p.street_bet for p in obs.players]
        stacks = [p.stack for p in obs.players]
        folded = [p.folded for p in obs.players]
        contributions[hero] += self.initial
        bets[hero] += self.initial
        stacks[hero] -= self.initial
        highest = max(bets)
        previous_highest = max(p.street_bet for p in obs.players)
        full_raise = self.action.kind == "raise_to" and highest - previous_highest >= self.increment
        increment = highest - previous_highest if full_raise else self.increment
        # Matched players who have already acted cannot take another free turn.
        pending = [i for d in range(1, len(bets)) if
                   not folded[i := (hero + d) % len(bets)] and stacks[i] and
                   (bets[i] < highest or (obs.players[i].player_id not in self.acted))]
        if self.action.kind == "raise_to":
            pending = [i for d in range(1, len(bets)) if
                       not folded[i := (hero + d) % len(bets)] and stacks[i]]
        shoved, raiser, callers = False, -1, 0
        hero_node, investment = None, self.initial
        events = []
        while pending:
            i = pending.pop(0)
            if folded[i] or not stacks[i]:
                continue
            cost = min(stacks[i], max(0, highest - bets[i]))
            if i == hero:
                if not cost:
                    continue
                # Only public hypothetical actions and amounts define the node.
                key = (raiser, tuple(events), tuple(contributions), tuple(folded), cost)
                if training:
                    hero_node = key
                    call = True  # Estimate a counterfactual call on training worlds.
                else:
                    call = continuation.get(key, False)
                if not call:
                    return -investment, None
                contributions[i] += cost
                bets[i] += cost
                stacks[i] -= cost
                investment += cost
                callers += 1
                events.append((i, "call", cost))
                continue
            own_total = contributions[i] + cost
            eligible = own_total + sum(min(c, own_total) for j, c in enumerate(contributions) if j != i)
            price = cost / eligible if eligible else 0.
            last_target = self.last_targets.get(obs.players[i].player_id)
            has_raise_right = last_target is None or highest - last_target >= increment
            can_shove = (not shoved and stacks[i] > cost and has_raise_right
                         and bets[i] + stacks[i] > highest)
            fold, call, jam = response_probabilities(scores[i], price, prior,
                self.adjustments.get(obs.players[i].player_id, 0.), callers, can_shove)
            u = uniforms[1 if shoved else 0][i]
            if u < fold:
                folded[i] = True
                events.append((i, "fold", 0))
            elif u < fold + call:
                contributions[i] += cost
                bets[i] += cost
                stacks[i] -= cost
                callers += bool(cost)
                events.append((i, "call" if cost else "check", cost))
            else:
                # A short all-in is legal with existing raise rights; it does
                # not reopen betting. No later raise exists in this abstraction.
                amount = stacks[i]
                contributions[i] += amount
                bets[i] += amount
                stacks[i] = 0
                highest = bets[i]
                shoved, raiser, callers = True, i, 0
                events.append((i, "raise_to", highest))
                pending = [j for d in range(1, len(bets)) if
                           not folded[j := (i + d) % len(bets)] and stacks[j] and bets[j] < highest]
        value = showdown_return(contributions, folded, ranks, hero) - investment
        # Incremental call value versus folding at the later hero information set.
        return value, (hero_node, value + self.initial) if hero_node is not None else None


def worlds(obs, ranges, rng, count, deadline):
    known = {CARD_INDEX[c] for c in obs.hole_cards}
    hero = next(i for i, p in enumerate(obs.players) if p.player_id == obs.hero_id)
    ids = [(i, p.player_id) for i, p in enumerate(obs.players) if p.player_id in ranges]
    hero_cards = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards]
    completed = attempts = 0
    while completed < count and attempts < max(10000, 100 * count):
        if attempts % 16 == 0 and perf_counter() >= deadline:
            return
        attempts += 1
        used, hands = set(known), {}
        for i, pid in ids:
            pair = ranges[pid].draw(rng)
            if used.intersection(pair):
                break
            used.update(pair)
            hands[i] = pair
        if len(hands) != len(ids):
            continue
        board = [EVAL_CARDS[c] for c in rng.sample([c for c in range(52) if c not in used], 5)]
        ranks, scores = [0] * len(obs.players), [0.] * len(obs.players)
        ranks[hero] = eval7.evaluate(hero_cards + board)
        for i, pair in hands.items():
            ranks[i] = eval7.evaluate([EVAL_CARDS[c] for c in pair] + board)
            scores[i] = COMBO_SCORES[tuple(sorted(pair))]
        uniforms = [[rng.random() for _ in obs.players] for _ in range(2)]
        completed += 1
        yield ranks, scores, uniforms


def learned_continuation(statistics, big_blind, minimum=16):
    # Sparse nodes default to folding; do not optimize on the evaluation ranks.
    return {key: m.n >= minimum and m.mean - m.se > .02 * big_blind
            for key, m in statistics.items()}


def search_responses(obs, ranges, model, baseline, rng, max_samples, deadline):
    if obs.street != "preflop" or max_samples < 1:
        raise ValueError("v5 requiere preflop y muestras positivas")
    actions = candidate_actions(obs, baseline)
    adjustments = {}
    for p in obs.opponents:
        aggression, confidence = model.tendency(p.player_id, "preflop", True)
        adjustments[p.player_id] = confidence * (aggression - .25) * .15
    arms = [ResponseRollout(obs, a, adjustments) for a in actions]
    training = [[{} for _ in SHOVE_PRIORS] for _ in arms]
    train_count, eval_cap = max_samples // 2, max_samples - max_samples // 2
    train_rng, eval_rng = random.Random(rng.getrandbits(128)), random.Random(rng.getrandbits(128))
    trained = 0
    for ranks, scores, uniforms in worlds(obs, ranges, train_rng, train_count, deadline):
        for a, arm in enumerate(arms):
            for j, prior in enumerate(SHOVE_PRIORS):
                _, node = arm.value(ranks, scores, uniforms, prior, {}, training=True)
                if node is not None:
                    key, gain = node
                    training[a][j].setdefault(key, Moments()).add(gain)
        trained += 1
    policies = [[learned_continuation(t, obs.big_blind) for t in arm] for arm in training]
    values = [[Moments() for _ in SHOVE_PRIORS] for _ in arms]
    gains = [[Moments() for _ in SHOVE_PRIORS] for _ in arms]
    completed, chosen, stop = 0, 0, "sample_cap"
    if trained == train_count:
        for ranks, scores, uniforms in worlds(obs, ranges, eval_rng, eval_cap, deadline):
            for j, prior in enumerate(SHOVE_PRIORS):
                base, _ = arms[0].value(ranks, scores, uniforms, prior, policies[0][j])
                for a, arm in enumerate(arms):
                    value = base if a == 0 else arm.value(ranks, scores, uniforms, prior, policies[a][j])[0]
                    values[a][j].add(value)
                    gains[a][j].add(value - base)
            completed += 1
    if completed != eval_cap:
        stop = "deadline_keep_v2" if perf_counter() >= deadline else "incompatible_ranges_keep_v2"
    elif completed > 1:
        lower = [min(m.mean - 2 * m.se for m in row) for row in gains]
        best = max(range(len(arms)), key=lambda a: lower[a])
        if best and lower[best] > .05 * obs.big_blind:
            chosen, stop = best, "robust_gain"
        else:
            stop = "no_robust_gain"
    summary = {"model": "one_opposing_shove_learned_public_recourse", "worlds": completed,
        "training_worlds": trained, "total_worlds": trained + completed, "sample_cap": max_samples,
        "stop": stop, "changed": chosen != 0, "margin_bb": .05,
        "priors": [p.name for p in SHOVE_PRIORS], "chosen": actions[chosen].to_dict(),
        "baseline": baseline.to_dict(), "continuation_nodes": sum(len(t) for arm in training for t in arm),
        "continuation_calls": sum(sum(p.values()) for arm in policies for p in arm),
        "arms": [{"action": action.to_dict(),
            "values_chips": {p.name: values[a][j].mean for j, p in enumerate(SHOVE_PRIORS)},
            "paired_gain_chips": {p.name: gains[a][j].mean for j, p in enumerate(SHOVE_PRIORS)},
            "paired_se_chips": {p.name: gains[a][j].se if completed > 1 else None for j, p in enumerate(SHOVE_PRIORS)}}
            for a, action in enumerate(actions)],
        "limitations": "One opposing shove only; no later bets. Separate training/evaluation worlds prevent hidden-hand recourse. Sparse continuation nodes fold. Manual priors; two-SE selection is heuristic."}
    return actions[chosen], summary


class ResponseSearchBot(ActionSearchBot):
    policy_name = "v5"

    def run_search(self, *args):
        return search_responses(*args)


class IntegratedSearchBot(ActionSearchBot):
    policy_name = "v4rb"

    def run_search(self, *args):
        from .action_integration import IntegratedAction
        action, info = fold_call_search(*args, prepared_factory=IntegratedAction)
        info["model"] = "exact_fold_call_checkdown"
        info["response_integration"] = "Rao-Blackwell; all response branches averaged per card world"
        return action, info

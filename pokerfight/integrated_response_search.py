"""v7: exact one-shove response integration with public weighted recourse.

The response model and action menu are those of v5. Card worlds still come
from Monte Carlo. Every response branch is integrated within each world;
continuation is learned only from a separate set of training worlds.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from time import perf_counter

from .action_model import candidate_actions, relative_rank_masks
from .action_search import ActionSearchBot, Moments
from .response_search import (SHOVE_PRIORS, acted_since_full_raise, betting_state,
                              response_probabilities, worlds)


@dataclass
class ReachMoments:
    """Posterior mean and delta-method SE for sum(reach * gain)/sum(reach)."""
    n: int = 0
    weight: float = 0.
    weight2: float = 0.
    mean: float = 0.
    square_weight_mean: float = 0.
    square_weight_m2: float = 0.

    def add(self, gain, reach):
        if reach <= 0:
            return
        self.n += 1
        self.weight += reach
        self.mean += reach / self.weight * (gain - self.mean)
        weight2 = reach * reach
        self.weight2 += weight2
        delta = gain - self.square_weight_mean
        self.square_weight_mean += weight2 / self.weight2 * delta
        self.square_weight_m2 += weight2 * delta * (gain - self.square_weight_mean)

    @property
    def effective_n(self):
        return self.weight * self.weight / self.weight2 if self.weight2 else 0.

    @property
    def se(self):
        if self.n < 2 or not self.weight:
            return math.inf
        centered = (self.square_weight_m2 + self.weight2
                    * (self.square_weight_mean - self.mean) ** 2)
        return math.sqrt(max(0., centered) * self.n / (self.n - 1)) / self.weight


def learned_recourse(statistics, big_blind, minimum=16):
    # Equal weights can round an integer effective count just below the bound.
    return {key: item.n >= minimum and item.effective_n >= minimum * (1 - 1e-12)
            and item.mean - item.se > .02 * big_blind
            for key, item in statistics.items()}


class IntegratedResponse:
    """Compile all public paths with at most one opposing all-in raise.

    Nodes are in postorder. Each public hero node has a fold payoff and a call
    subtree; its policy is fixed before evaluation. Terminal pot layers and
    equivalent response probabilities are shared, not public information sets.
    """

    def __init__(self, obs, action, adjustments):
        self.obs, self.action = obs, action
        self.hero = next(i for i, player in enumerate(obs.players) if player.player_id == obs.hero_id)
        self.initial = (action.amount - obs.hero.street_bet if action.kind == "raise_to"
                        else obs.legal.call_amount if action.kind == "call" else 0)
        self.nodes, self.terminals, self.responses, self.hero_nodes = [], [], [], []
        self._terminal_indices, self._response_indices = {}, {}
        self._terminal_nodes = {}
        self._terminal_values = {}
        acted, increment = acted_since_full_raise(obs)
        _, _, last_targets = betting_state(obs)

        def terminal(contributions, folded, investment):
            layers, previous = [], 0
            for level in sorted(set(contributions) - {0}):
                amount = (level - previous) * sum(c >= level for c in contributions)
                if contributions[self.hero] >= level:
                    opponents = sum(1 << i for i, c in enumerate(contributions)
                                    if i != self.hero and c >= level and not folded[i])
                    layers.append((amount, opponents))
                previous = level
            key = (tuple(layers), investment)
            existing = self._terminal_nodes.get(key)
            if existing is not None:
                return existing
            self._terminal_indices[key] = len(self.terminals)
            self.terminals.append(key)
            self.nodes.append((0, self._terminal_indices[key]))
            self._terminal_nodes[key] = len(self.nodes) - 1
            return self._terminal_nodes[key]

        if action.kind == "fold":
            self.nodes.append((0, 0))
            self.terminals.append(((), 0))
            self.root = 0
            return

        contributions = [p.contribution for p in obs.players]
        bets = [p.street_bet for p in obs.players]
        stacks = [p.stack for p in obs.players]
        folded = [p.folded for p in obs.players]
        contributions[self.hero] += self.initial
        bets[self.hero] += self.initial
        stacks[self.hero] -= self.initial
        highest = max(bets)
        previous = max(p.street_bet for p in obs.players)
        if action.kind == "raise_to" and highest - previous >= increment:
            increment = highest - previous
        pending = [i for distance in range(1, len(bets))
                   if not folded[i := (self.hero + distance) % len(bets)] and stacks[i]
                   and (action.kind == "raise_to" or bets[i] < highest
                        or obs.players[i].player_id not in acted)]

        def build(contributions, bets, stacks, folded, pending, shoved, raiser,
                  callers, events, investment):
            while pending and (folded[pending[0]] or not stacks[pending[0]]):
                pending = pending[1:]
            if not pending:
                return terminal(contributions, folded, investment)
            i, rest = pending[0], pending[1:]
            highest = max(bets)
            cost = min(stacks[i], max(0, highest - bets[i]))
            if i == self.hero and not cost:
                return build(contributions, bets, stacks, folded, rest, shoved,
                             raiser, callers, events, investment)
            paid, new_bets, new_stacks = contributions.copy(), bets.copy(), stacks.copy()
            paid[i] += cost
            new_bets[i] += cost
            new_stacks[i] -= cost
            event = (i, "call" if cost else "check", cost)
            call = build(paid, new_bets, new_stacks, folded, rest, shoved, raiser,
                         callers + bool(cost), events + (event,),
                         investment + cost if i == self.hero else investment)
            if i == self.hero:
                key = (raiser, events, tuple(contributions), tuple(folded), cost)
                node = len(self.nodes)
                self.hero_nodes.append((node, key, call))
                self.nodes.append((2, key, call))
                return node

            last = last_targets.get(obs.players[i].player_id)
            right = last is None or highest - last >= increment
            can_shove = (not shoved and stacks[i] > cost and right
                         and bets[i] + stacks[i] > highest)
            if not cost and not can_shove:
                return call  # Forced check; its public event is already in child paths.
            declined = folded.copy()
            declined[i] = True
            fold = (build(contributions, bets, stacks, declined, rest, shoved, raiser,
                          callers, events + ((i, "fold", 0),), investment) if cost else -1)
            jam = -1
            if can_shove:
                jammed, jam_bets, jam_stacks = contributions.copy(), bets.copy(), stacks.copy()
                jammed[i] += stacks[i]
                jam_bets[i] += stacks[i]
                jam_stacks[i] = 0
                target = jam_bets[i]
                revisited = [j for distance in range(1, len(bets))
                             if not folded[j := (i + distance) % len(bets)]
                             and jam_stacks[j] and jam_bets[j] < target]
                jam = build(jammed, jam_bets, jam_stacks, folded, revisited, True, i, 0,
                            events + ((i, "raise_to", target),), investment)
            own_total = contributions[i] + cost
            eligible = own_total + sum(min(c, own_total) for j, c in enumerate(contributions) if j != i)
            price = cost / eligible if eligible else 0.
            group = (i, price, callers, can_shove, adjustments.get(obs.players[i].player_id, 0.))
            if group not in self._response_indices:
                self._response_indices[group] = len(self.responses)
                self.responses.append(group)
            self.nodes.append((1, self._response_indices[group], fold, call, jam))
            return len(self.nodes) - 1

        self.root = build(contributions, bets, stacks, folded, pending, False, -1, 0, (), self.initial)

    def value(self, ranks, scores, prior, continuation, training=False, statistics=None):
        masks = relative_rank_masks(ranks, self.hero)
        terminals = self._terminal_values.get(masks)
        if terminals is None:
            better, tied = masks
            terminals = []
            for layers, investment in self.terminals:
                returned = 0.
                for amount, opponents in layers:
                    if not opponents & better:
                        returned += amount / (1 + (opponents & tied).bit_count())
                terminals.append(returned - investment)
            self._terminal_values[masks] = terminals
        probabilities = [response_probabilities(scores[i], price, prior, adjustment, callers, can_shove)
                         for i, price, callers, can_shove, adjustment in self.responses]
        values = []
        for node in self.nodes:
            kind = node[0]
            if kind == 0:
                values.append(terminals[node[1]])
            elif kind == 1:
                _, group, fold, call, jam = node
                pf, pc, pj = probabilities[group]
                values.append((pf * values[fold] if fold >= 0 else 0.) + pc * values[call]
                              + (pj * values[jam] if jam >= 0 else 0.))
            else:
                _, key, call = node
                values.append(values[call] if training or continuation.get(key, False) else -self.initial)
        if not training or not self.hero_nodes:
            return values[self.root], ()
        reach = [0.] * len(self.nodes)
        reach[self.root] = 1.
        for index in range(self.root, -1, -1):
            node, weight = self.nodes[index], reach[index]
            if node[0] == 1:
                for child, probability in zip(node[2:], probabilities[node[1]]):
                    if child >= 0:
                        reach[child] += weight * probability
            elif node[0] == 2:
                reach[node[2]] += weight  # Counterfactual call during training only.
        if statistics is not None:
            for item, (node, _, call) in zip(statistics, self.hero_nodes):
                item.add(values[call] + self.initial, reach[node])
            return values[self.root], ()
        return values[self.root], tuple((key, reach[node], values[call] + self.initial)
                                       for node, key, call in self.hero_nodes)


def search_integrated_responses(obs, ranges, model, baseline, rng, max_samples, deadline):
    if obs.street != "preflop" or type(max_samples) is not int or max_samples < 1:
        raise ValueError("v7 requiere preflop y muestras enteras positivas")
    actions = candidate_actions(obs, baseline)
    adjustments = {}
    for player in obs.opponents:
        aggression, confidence = model.tendency(player.player_id, "preflop", True)
        adjustments[player.player_id] = confidence * (aggression - .25) * .15
    arms = [IntegratedResponse(obs, action, adjustments) for action in actions]
    training = [[[ReachMoments() for _ in arm.hero_nodes] for _ in SHOVE_PRIORS] for arm in arms]
    train_count, eval_cap = max_samples // 2, max_samples - max_samples // 2
    train_rng, eval_rng = random.Random(rng.getrandbits(128)), random.Random(rng.getrandbits(128))
    trained = 0
    for ranks, scores, _ in worlds(obs, ranges, train_rng, train_count, deadline):
        for a, arm in enumerate(arms):
            for j, prior in enumerate(SHOVE_PRIORS):
                arm.value(ranks, scores, prior, {}, training=True, statistics=training[a][j])
        trained += 1
    policies = [[learned_recourse(dict(zip((key for _, key, _ in arms[a].hero_nodes), statistics)),
                                 obs.big_blind) for statistics in arm] for a, arm in enumerate(training)]
    values = [[Moments() for _ in SHOVE_PRIORS] for _ in arms]
    gains = [[Moments() for _ in SHOVE_PRIORS] for _ in arms]
    completed, chosen, stop = 0, 0, "sample_cap"
    if trained == train_count:
        for ranks, scores, _ in worlds(obs, ranges, eval_rng, eval_cap, deadline):
            for j, prior in enumerate(SHOVE_PRIORS):
                base = arms[0].value(ranks, scores, prior, policies[0][j])[0]
                for a, arm in enumerate(arms):
                    value = base if a == 0 else arm.value(ranks, scores, prior, policies[a][j])[0]
                    values[a][j].add(value)
                    gains[a][j].add(value - base)
            completed += 1
    if completed != eval_cap:
        stop = "deadline_keep_v2" if perf_counter() >= deadline else "incompatible_ranges_keep_v2"
    elif completed > 1:
        lower = [min(item.mean - 2 * item.se for item in row) for row in gains]
        best = max(range(len(arms)), key=lambda a: lower[a])
        if best and lower[best] > .05 * obs.big_blind:
            chosen, stop = best, "robust_gain"
        else:
            stop = "no_robust_gain"
    summary = {
        "model": "exact_one_opposing_shove_public_weighted_recourse", "worlds": completed,
        "training_worlds": trained, "total_worlds": trained + completed, "sample_cap": max_samples,
        "stop": stop, "changed": chosen != 0, "margin_bb": .05,
        "priors": [prior.name for prior in SHOVE_PRIORS], "chosen": actions[chosen].to_dict(),
        "baseline": baseline.to_dict(), "compiled_nodes": sum(len(arm.nodes) for arm in arms),
        "continuation_nodes": sum(len(statistics) for arm in training for statistics in arm) if trained else 0,
        "continuation_calls": sum(sum(policy.values()) for arm in policies for policy in arm),
        "arms": [{"action": action.to_dict(),
                  "values_chips": {prior.name: values[a][j].mean for j, prior in enumerate(SHOVE_PRIORS)},
                  "paired_gain_chips": {prior.name: gains[a][j].mean for j, prior in enumerate(SHOVE_PRIORS)},
                  "paired_se_chips": {prior.name: gains[a][j].se if completed > 1 else None
                                      for j, prior in enumerate(SHOVE_PRIORS)}}
                 for a, action in enumerate(actions)],
        "limitations": "One opposing shove; no later bets. Manual priors. Separate training/evaluation worlds. "
                       "Reach-weighted posterior and ratio-estimator SE; two-SE selection remains heuristic."}
    return actions[chosen], summary


class IntegratedResponseBot(ActionSearchBot):
    policy_name = "v7"

    def run_search(self, *args):
        return search_integrated_responses(*args)

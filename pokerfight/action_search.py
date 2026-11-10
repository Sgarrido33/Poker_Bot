"""v4: paired Monte Carlo action comparison under three response priors."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
from time import perf_counter
import eval7

from .action_model import PRIORS, PreparedAction, candidate_actions, relative_rank_masks
from .cards import CARD_INDEX, EVAL_CARDS
from .domain import safe_action
from .equity import COMBO_SCORES, build_ranges, estimate
from .shortstack import context
from .strategy import Decision, PokerBot


@dataclass
class Moments:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value):
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)

    @property
    def se(self):
        return math.sqrt(self.m2 / (self.n - 1) / self.n) if self.n > 1 else math.inf


def search(obs, ranges, model, baseline, rng, max_samples, deadline, min_samples=512, batch=256,
           prepared_factory=PreparedAction, action_factory=candidate_actions):
    if obs.street != "preflop":
        raise ValueError("La búsqueda v4 solo admite preflop")
    if max_samples < 1 or min_samples < 1 or batch < 1:
        raise ValueError("Límites de búsqueda deben ser positivos")
    actions = action_factory(obs, baseline)
    adjustments = {}
    for p in obs.opponents:
        aggression, confidence = model.tendency(p.player_id, "preflop", True)
        adjustments[p.player_id] = confidence * (aggression - .25) * .15
    prepared = [prepared_factory(obs, action, adjustments) for action in actions]
    values = [[Moments() for _ in PRIORS] for _ in actions]
    differences = [[Moments() for _ in PRIORS] for _ in actions]
    known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
    hero_cards = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards]
    hero = prepared[0].hero
    ids = [(i, p.player_id) for i, p in enumerate(obs.players) if p.player_id in ranges]
    margin = .05 * obs.big_blind
    completed = attempts = 0
    stop = "sample_cap"
    chosen = 0
    while completed < max_samples and attempts < max(10000, max_samples * 100):
        if attempts % 16 == 0 and perf_counter() >= deadline:
            stop = "deadline_keep_v2"
            break
        attempts += 1
        used = set(known)
        hands = {}
        for i, pid in ids:
            pair = ranges[pid].draw(rng)
            if used.intersection(pair):
                break
            used.update(pair)
            hands[i] = pair
        if len(hands) != len(ids):
            continue  # Reject the entire joint draw, preserving product conditioning.
        board = [EVAL_CARDS[i] for i in rng.sample([i for i in range(52) if i not in used], 5)]
        ranks = [0] * len(obs.players)
        scores = [0.0] * len(obs.players)
        ranks[hero] = eval7.evaluate(hero_cards + board)
        uniforms = [rng.random() for _ in obs.players]
        for i, pair in hands.items():
            ranks[i] = eval7.evaluate([EVAL_CARDS[c] for c in pair] + board)
            scores[i] = COMBO_SCORES[tuple(sorted(pair))]
        rank_masks = relative_rank_masks(ranks, hero)
        for j, prior in enumerate(PRIORS):
            base = prepared[0].value(ranks, scores, uniforms, prior, rank_masks)
            for a, arm in enumerate(prepared):
                value = base if a == 0 else arm.value(ranks, scores, uniforms, prior, rank_masks)
                values[a][j].add(value)
                differences[a][j].add(value - base)
        completed += 1
        if completed >= min(min_samples, max_samples) and completed % batch == 0:
            lower = [min(m.mean - 2 * m.se for m in d) for d in differences]
            possible = [min(m.mean + 2 * m.se for m in d) for d in differences]
            best = max(range(len(actions)), key=lambda a: lower[a])
            if best and lower[best] > margin:
                # Further refinement only when a competing robust gain might
                # overtake the leader by a material amount.
                if all(a == best or possible[a] < lower[best] + margin for a in range(1, len(actions))):
                    chosen, stop = best, "robust_gain"
                    break
            if all(upper <= margin for upper in possible[1:]):
                stop = "no_robust_gain"
                break
    if completed < max_samples and stop == "sample_cap":
        stop = "incompatible_ranges_keep_v2"
    if completed and stop not in ("deadline_keep_v2", "incompatible_ranges_keep_v2"):
        lower = [min(m.mean - 2 * m.se for m in d) for d in differences]
        best = max(range(len(actions)), key=lambda a: lower[a])
        if best and lower[best] > margin:
            chosen = best
    summary = {"model": "one_step_fold_call_checkdown", "worlds": completed, "attempts": attempts,
        "sample_cap": max_samples, "stop": stop, "changed": chosen != 0, "margin_bb": .05,
        "priors": [p.name for p in PRIORS], "chosen": actions[chosen].to_dict(),
        "baseline": baseline.to_dict(), "arms": [
            {"action": action.to_dict(), "values_chips": {p.name: values[a][j].mean for j, p in enumerate(PRIORS)},
             "paired_gain_chips": {p.name: differences[a][j].mean for j, p in enumerate(PRIORS)},
             "paired_se_chips": {p.name: (differences[a][j].se if completed > 1 else None) for j, p in enumerate(PRIORS)}}
            for a, action in enumerate(actions)],
        "limitations": "No reraises or later bets. Nonterminal values are checkdown proxies. Two-SE stopping is heuristic, not a confidence guarantee."}
    return actions[chosen], summary


class ActionSearchBot(PokerBot):
    policy_name = "v4"

    def run_search(self, *args):
        return search(*args)

    def decide(self, obs):
        started = perf_counter()
        deadline = started + self.config.budget_ms / 1000
        equity = None
        baseline = None
        try:
            self.model.observe(obs.table_id, obs.hand_id, obs.history)
            key = f"{self.config.seed}|{obs.table_id}|{obs.hand_id}|{obs.hero_id}|{len(obs.history)}|{obs.street}"
            rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))
            cost = obs.legal.call_amount
            applicable = (obs.street == "preflop" and context(obs).effective_bb <= 12
                and not (cost > 0 and (cost == obs.hero.stack or all(p.stack == 0 for p in obs.opponents))))
            ranges = build_ranges(obs, self.model, deadline)
            # Preserve v2's ordinary quota for the base decision; allocate the
            # extra work to responses/actions instead of repeating this estimate.
            quota = min(4000, self.config.samples) if applicable else self.config.samples
            equity = estimate(obs, ranges, rng, quota, deadline)
            if equity.samples < min(128, quota):
                raise TimeoutError("Muestra base insuficiente")
            baseline, reason = self.select(obs, equity)
            info = None
            action = baseline
            if applicable:
                action, info = self.run_search(obs, ranges, self.model, baseline, rng, self.config.samples,
                                              deadline - .015)
                reason = self.policy_name + ":" + ("action_gain" if info["changed"] else "keep_v2") + ":" + info["stop"]
            if not action.is_legal(obs):
                raise ValueError("La búsqueda propuso una acción ilegal")
            return Decision(action, reason, (perf_counter() - started) * 1000, False, equity, info)
        except Exception as error:
            return Decision(baseline if baseline is not None and baseline.is_legal(obs) else safe_action(obs),
                f"fallback:{self.policy_name}:{type(error).__name__}:{error}", (perf_counter() - started) * 1000, True, equity)

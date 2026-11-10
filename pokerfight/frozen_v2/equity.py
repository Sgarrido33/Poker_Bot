"""Weighted, collision-free Monte Carlo with side-pot-aware showdown shares.

Each opponent is first sampled independently. If ANY cards collide, the
entire joint draw is rejected. Sequentially resampling just the colliding
player would bias the desired product of ranges conditioned on disjointness.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from itertools import combinations
import math
import random
from time import perf_counter
import eval7

from .cards import CARD_INDEX, DECK, EVAL_CARDS, preflop_score
from .domain import Observation
from .opponents import OpponentModel

COMBOS = tuple(combinations(range(52), 2))
COMBO_SCORES = {pair: preflop_score((DECK[pair[0]], DECK[pair[1]])) for pair in COMBOS}


@dataclass(frozen=True)
class WeightedRange:
    combos: tuple[tuple[int, int], ...]
    cumulative: tuple[float, ...]

    @classmethod
    def create(cls, entries: list[tuple[tuple[int, int], float]]) -> WeightedRange:
        if not entries:
            raise ValueError("Rango vacío")
        cumulative = []
        total = 0.0
        for pair, weight in entries:
            if (len(pair) != 2 or pair[0] == pair[1]
                    or any(type(i) is not int or not 0 <= i < 52 for i in pair)
                    or not math.isfinite(weight) or weight <= 0):
                raise ValueError("Combo o peso inválido")
            total += weight
            cumulative.append(total)
        if not math.isfinite(total):
            raise ValueError("Peso total inválido")
        return cls(tuple(pair for pair, _ in entries), tuple(cumulative))

    def draw(self, rng: random.Random) -> tuple[int, int]:
        return self.combos[bisect_right(self.cumulative, rng.random() * self.cumulative[-1])]


def build_ranges(obs: Observation, model: OpponentModel, deadline: float) -> dict[str, WeightedRange]:
    known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
    board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board]
    available = [pair for pair in COMBOS if not known.intersection(pair)]
    result = {}
    for opponent in obs.opponents:
        if perf_counter() >= deadline:
            raise TimeoutError("Presupuesto agotado preparando rangos")
        preflop = [e for e in obs.history if e.player_id == opponent.player_id and e.street == "preflop"]
        raises = sum(e.kind == "raise_to" for e in preflop)
        called = any(e.kind == "call" for e in preflop)
        latest = next((e for e in reversed(obs.history) if e.player_id == opponent.player_id and e.street == obs.street), None)
        aggression, confidence = model.tendency(opponent.player_id, "preflop", True)
        # More observed aggression loosens the assumed range, bounded by confidence.
        threshold = (0.70 if raises else 0.48 if called else 0.0)
        threshold += min(raises - 1, 2) * 0.065 if raises else 0
        threshold -= confidence * (aggression - 0.25) * 0.3
        entries = []
        for j, pair in enumerate(available):
            if j % 128 == 0 and perf_counter() >= deadline:
                raise TimeoutError("Presupuesto agotado preparando rangos")
            score = COMBO_SCORES[pair]
            # A full-support prior: actions never turn unknown cards into facts.
            weight = 1.0 if threshold == 0 else 0.06 + 0.94 / (1 + math.exp(-15 * (score - threshold)))
            if board and latest is not None:
                rank = eval7.evaluate(board + [EVAL_CARDS[pair[0]], EVAL_CARDS[pair[1]]])
                category = rank >> 24
                quality = min(1.0, category / 3)
                # The likelihood uses only cards already public at this street.
                if latest.kind == "raise_to":
                    weight *= 0.12 + 0.80 * quality
                elif latest.kind == "call":
                    weight *= 0.35 + 0.50 * quality
                elif latest.kind == "check":
                    weight *= 0.90 - 0.30 * quality
            entries.append((pair, weight))
        result[opponent.player_id] = WeightedRange.create(entries)
    return result


@dataclass(frozen=True)
class EquityResult:
    equity: float
    standard_error: float
    expected_return: float
    eligible_pot: int
    samples: int
    attempts: int
    timed_out: bool


def estimate(obs: Observation, ranges: dict[str, WeightedRange], rng: random.Random,
             samples: int = 4000, deadline: float = math.inf) -> EquityResult:
    if type(samples) is not int or samples < 1:
        raise ValueError("samples debe ser positivo")
    known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
    ids = [p.player_id for p in obs.opponents]
    if set(ranges) != set(ids):
        raise ValueError("Se necesita exactamente un rango por rival activo")
    for weighted in ranges.values():
        if any(known.intersection(pair) for pair in weighted.combos):
            raise ValueError("El rango incluye cartas conocidas")
    pots = obs.call_pots()
    total_pot = sum(p.amount for p in pots)
    if total_pot <= 0:
        raise ValueError("No hay un pozo elegible")
    hero_cards = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards]
    current_board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board]
    completed = attempts = 0
    mean = m2 = 0.0
    # Also bounds pathological incompatible ranges even without a deadline.
    max_attempts = max(10000, samples * 100)
    while completed < samples and attempts < max_attempts:
        if attempts % 32 == 0 and perf_counter() >= deadline:
            break
        attempts += 1
        used = set(known)
        hands = {}
        for player_id in ids:
            pair = ranges[player_id].draw(rng)
            if used.intersection(pair):
                break
            used.update(pair)
            hands[player_id] = pair
        if len(hands) != len(ids):
            continue
        runout = rng.sample([i for i in range(52) if i not in used], 5 - len(current_board))
        board = current_board + [EVAL_CARDS[i] for i in runout]
        ranks = {obs.hero_id: eval7.evaluate(hero_cards + board)}
        ranks.update({pid: eval7.evaluate([EVAL_CARDS[a], EVAL_CARDS[b]] + board)
                      for pid, (a, b) in hands.items()})
        returned = 0.0
        for pot in pots:
            best = max(ranks[pid] for pid in pot.eligible)
            if ranks[obs.hero_id] == best:
                returned += pot.amount / sum(ranks[pid] == best for pid in pot.eligible)
        share = returned / total_pot
        completed += 1
        delta = share - mean
        mean += delta / completed
        m2 += delta * (share - mean)
    if completed == 0:
        raise TimeoutError("No se pudo completar ninguna simulación compatible")
    standard_error = math.sqrt(m2 / (completed - 1) / completed) if completed > 1 else 0.5
    return EquityResult(mean, standard_error, mean * total_pot, total_pot,
                        completed, attempts, completed < samples)

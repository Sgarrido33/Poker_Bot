"""Exact showdown equity for heads-up rivers, as an opt-in policy wrapper.

Zero standard error denotes the absence of Monte Carlo sampling error. It
does not express confidence in the opponent range or in the betting policy.
"""
from __future__ import annotations

import math
from time import perf_counter

import eval7

from .cards import CARD_INDEX, EVAL_CARDS
from .domain import Observation, safe_action
from .equity import EquityResult, WeightedRange, build_ranges
from .strategy import Decision, PokerBot


def estimate_river(obs: Observation, ranges: dict[str, WeightedRange],
                   deadline: float = math.inf) -> EquityResult:
    """Enumerate one rival's river range, including all hero-eligible pots.

    Range weights are the increments of its cumulative distribution, matching
    WeightedRange.draw. An expired deadline raises instead of returning a
    partially enumerated distribution.
    """
    if len(obs.board) != 5 or len(obs.opponents) != 1:
        raise ValueError("La enumeración requiere river y un rival activo")
    opponent = obs.opponents[0].player_id
    if set(ranges) != {opponent}:
        raise ValueError("Se necesita exactamente el rango del rival activo")
    if math.isnan(deadline):
        raise ValueError("Deadline inválido")
    if perf_counter() >= deadline:
        raise TimeoutError("Presupuesto agotado antes de enumerar el river")
    weighted = ranges[opponent]
    if not weighted.combos or len(weighted.combos) != len(weighted.cumulative):
        raise ValueError("Rango vacío o distribución inconsistente")
    total_weight = weighted.cumulative[-1]
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise ValueError("Peso total inválido")
    known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
    board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board]
    hero_rank = eval7.evaluate(board + [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards])
    pots = obs.call_pots()
    total_pot = sum(p.amount for p in pots)
    if total_pot <= 0:
        raise ValueError("No hay un pozo elegible")
    terms = []
    previous = 0.0
    for index, (pair, cumulative) in enumerate(zip(weighted.combos, weighted.cumulative)):
        if index % 32 == 0 and perf_counter() >= deadline:
            raise TimeoutError("Presupuesto agotado enumerando el river")
        if (len(pair) != 2 or pair[0] == pair[1]
                or any(type(i) is not int or not 0 <= i < 52 for i in pair)
                or known.intersection(pair)):
            raise ValueError("Combo inválido o con cartas conocidas")
        if not math.isfinite(cumulative) or cumulative < previous:
            raise ValueError("Distribución acumulada inválida")
        probability = (cumulative - previous) / total_weight
        previous = cumulative
        if probability == 0:
            continue
        opponent_rank = eval7.evaluate(board + [EVAL_CARDS[pair[0]], EVAL_CARDS[pair[1]]])
        ranks = {obs.hero_id: hero_rank, opponent: opponent_rank}
        returns = []
        for pot in pots:
            best = max(ranks[pid] for pid in pot.eligible)
            if hero_rank == best:
                returns.append(pot.amount / sum(ranks[pid] == best for pid in pot.eligible))
        terms.append(probability * (math.fsum(returns) / total_pot))
    if perf_counter() >= deadline:
        raise TimeoutError("Presupuesto agotado al completar el river")
    equity = math.fsum(terms)
    count = len(weighted.combos)
    return EquityResult(equity, 0.0, equity * total_pot, total_pot, count, count, False)


class ExactRiverPolicy(PokerBot):
    """Use exact heads-up river equity with an existing live policy's rules.

    Every observation outside this scope is passed directly to the base.
    Frozen control policies are deliberately excluded.
    """

    def __init__(self, base: PokerBot):
        if not isinstance(base, PokerBot) or hasattr(base, "control"):
            raise ValueError("Se requiere una política viva, no un control congelado")
        self.base = base

    @property
    def config(self):
        return self.base.config

    @property
    def model(self):
        return self.base.model

    def decide(self, obs: Observation) -> Decision:
        if obs.street != "river" or len(obs.opponents) != 1:
            return self.base.decide(obs)
        started = perf_counter()
        deadline = started + self.config.budget_ms / 1000
        equity = None
        try:
            self.model.observe(obs.table_id, obs.hand_id, obs.history)
            ranges = build_ranges(obs, self.model, deadline)
            equity = estimate_river(obs, ranges, deadline)
            action, reason = self.base.select(obs, equity)
            if not action.is_legal(obs):
                raise ValueError("La política propuso una acción ilegal")
            if perf_counter() >= deadline:
                raise TimeoutError("Presupuesto agotado seleccionando la acción")
            return Decision(action, "exact_river:" + reason,
                            (perf_counter() - started) * 1000, False, equity,
                            {"model": "exact_heads_up_river", "combos": equity.samples,
                             "changed": False, "stop": "exact_enumeration", "worlds": equity.samples,
                             "limitations": "Zero Monte Carlo error under the supplied range; "
                                            "range/model uncertainty remains."})
        except Exception as error:
            return Decision(safe_action(obs),
                            f"fallback:exact_river:{type(error).__name__}:{error}",
                            (perf_counter() - started) * 1000, True, equity)

    def close(self) -> None:
        close = getattr(self.base, "close", None)
        if close is not None:
            close()

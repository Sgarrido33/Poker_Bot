"""Exact fold/call response integration for compiled preflop action trees.

The card world remains sampled.  Conditional on one world, this class sums
every binary opponent response branch using the existing response prior.
"""
from __future__ import annotations

from .action_model import PreparedAction, ResponsePrior, call_probability, relative_rank_masks


class IntegratedAction(PreparedAction):
    """A ``PreparedAction`` whose fold/call responses are Rao-Blackwellized.

    ``uniforms`` is accepted for drop-in compatibility with ``PreparedAction``
    but intentionally ignored.  Caller-dependent prices still follow the
    branch-specific values compiled in ``levels``.
    """

    def __init__(self, obs, action, adjustments):
        super().__init__(obs, action, adjustments)
        # Different response paths often face the same price and caller count.
        # Resolve those duplicates once, without merging their pot outcomes.
        self._integration_levels = []
        for i, adjustment, prices in reversed(self.levels):
            unique = tuple(dict.fromkeys(prices))
            indices = {price: j for j, price in enumerate(unique)}
            self._integration_levels.append((i, adjustment, unique,
                                             tuple(indices[price] for price in prices)))
        # Terminal payoffs depend on who beats/ties hero, not on exact ranks or
        # response priors. At six seats there are at most 3**5 such patterns.
        # This cache belongs to this action/observation only, never another hand.
        self._terminal_values = {}

    def value(self, ranks: list[int], scores: list[float], uniforms: list[float],
              prior: ResponsePrior, rank_masks: tuple[int, int] | None = None) -> float:
        if self.fold:
            return 0.0

        masks = rank_masks if rank_masks is not None else relative_rank_masks(ranks, self.hero)
        values = self._terminal_values.get(masks)
        if values is None:
            better, tied = masks
            terminal = []
            for layers in self.outcomes:
                returned = 0.0
                for amount, opponents in layers:
                    if not opponents & better:
                        returned += amount / (1 + (opponents & tied).bit_count())
                terminal.append(returned - self.investment)
            values = tuple(terminal)
            self._terminal_values[masks] = values

        # Same child order and arithmetic as recursive integration: fixed card
        # worlds retain bit-for-bit EVs, including ties and unmatched returns.
        for i, adjustment, prices, indices in self._integration_levels:
            probabilities = [call_probability(scores[i], price, prior, adjustment, callers)
                             for price, callers in prices]
            values = [(1.0 - probabilities[index]) * values[2 * leaf]
                      + probabilities[index] * values[2 * leaf + 1]
                      for leaf, index in enumerate(indices)]
        return values[0]

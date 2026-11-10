"""Card representation shared by the protocol, charts and equity engine."""
from __future__ import annotations

from functools import lru_cache
import eval7

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(rank + suit for rank in RANKS for suit in SUITS)
EVAL_CARDS = tuple(eval7.Card(card) for card in DECK)
CARD_INDEX = {card: i for i, card in enumerate(DECK)}


def validate_cards(cards: tuple[str, ...]) -> None:
    if any(not isinstance(c, str) or c not in CARD_INDEX for c in cards):
        raise ValueError("Use cartas como As, Td, 2c; T representa el diez")
    if len(set(cards)) != len(cards):
        raise ValueError("Hay cartas conocidas duplicadas")


def hand_class(cards: tuple[str, str]) -> str:
    a, b = sorted(cards, key=lambda c: RANKS.index(c[0]), reverse=True)
    return a[0] + b[0] + ("" if a[0] == b[0] else "s" if a[1] == b[1] else "o")


@lru_cache(maxsize=128)
def expand_range(notation: str) -> frozenset[str]:
    """Expand notation once; chart membership is by the 169 hand classes."""
    return frozenset(hand_class(tuple(map(str, pair))) for pair, _ in eval7.HandRange(notation).hands)


def preflop_score(cards: tuple[str, str]) -> float:
    """A transparent ordering heuristic, not equity or a solved strategy."""
    a, b = sorted((RANKS.index(c[0]) + 2 for c in cards), reverse=True)
    if a == b:
        return 0.48 + 0.50 * (a - 2) / 12
    suited = cards[0][1] == cards[1][1]
    gap = a - b - 1
    score = 0.13 + 0.40 * (a - 2) / 12 + 0.24 * (b - 2) / 12
    return min(0.95, score + 0.07 * suited + 0.035 * (gap == 0) - 0.02 * min(gap, 5))

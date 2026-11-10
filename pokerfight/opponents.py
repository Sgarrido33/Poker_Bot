"""Bounded, table-local adaptation from public actions only."""
from __future__ import annotations

from dataclasses import dataclass
from .domain import Observation, PublicAction


@dataclass
class Counts:
    folds: int = 0
    passive: int = 0
    raises: int = 0

    @property
    def n(self) -> int:
        return self.folds + self.passive + self.raises

    def aggression(self) -> float:
        return (self.raises + 2) / (self.n + 8)


class OpponentModel:
    def __init__(self, confidence_cap: float = 0.35, prior_observations: int = 40):
        self.cap = confidence_cap
        self.prior = prior_observations
        self.table_id: str | None = None
        self.counts: dict[tuple[str, str, bool], Counts] = {}
        self._seen: set[tuple[str, str]] = set()
        self._hands: list[str] = []

    def observe(self, table_id: str, hand_id: str, history: tuple[PublicAction, ...]) -> None:
        if table_id != self.table_id:
            self.table_id = table_id
            self.counts.clear()
            self._seen.clear()
            self._hands.clear()
        if hand_id not in self._hands:
            self._hands.append(hand_id)
            # Bounded deduplication. The adapter must send current-hand history.
            if len(self._hands) > 64:
                old = self._hands.pop(0)
                self._seen = {key for key in self._seen if key[0] != old}
        for event in history:
            key = (hand_id, event.event_id)
            if key in self._seen:
                continue
            self._seen.add(key)
            counts = self.counts.setdefault((event.player_id, event.street, event.facing_bet), Counts())
            if event.kind == "fold":
                counts.folds += 1
            elif event.kind == "raise_to":
                counts.raises += 1
            else:
                counts.passive += 1

    def tendency(self, player_id: str, street: str, facing_bet: bool) -> tuple[float, float]:
        counts = self.counts.get((player_id, street, facing_bet), Counts())
        confidence = self.cap * counts.n / (self.prior + counts.n)
        return counts.aggression(), confidence

    def call_margin_adjustment(self, obs: Observation) -> float:
        """At most a few percentage points, with zero change without evidence."""
        adjustments = []
        for p in obs.opponents:
            latest = next((e for e in reversed(obs.history)
                           if e.player_id == p.player_id and e.street == obs.street), None)
            aggression, confidence = self.tendency(p.player_id, obs.street, latest.facing_bet if latest else False)
            adjustments.append(confidence * (0.25 - aggression) * 0.12)
        return sum(adjustments) / len(adjustments) if adjustments else 0.0

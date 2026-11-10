"""Local protocol v1. It deliberately contains no opponent hole cards."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from .cards import validate_cards

Kind = Literal["fold", "check", "call", "raise_to"]
STREETS = ("preflop", "flop", "turn", "river")


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} debe ser un entero >= {minimum}")
    return value


def fields(data: dict, allowed: set[str], required: set[str]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Se esperaba un objeto JSON")
    if set(data) - allowed:
        raise ValueError(f"Campos desconocidos: {sorted(set(data) - allowed)}")
    if required - set(data):
        raise ValueError(f"Faltan campos: {sorted(required - set(data))}")


@dataclass(frozen=True)
class Player:
    player_id: str
    stack: int
    street_bet: int
    contribution: int
    folded: bool = False

    def __post_init__(self):
        if not isinstance(self.player_id, str) or not self.player_id:
            raise ValueError("player_id debe ser un texto no vacío")
        for name in ("stack", "street_bet", "contribution"):
            integer(getattr(self, name), name)
        if self.street_bet > self.contribution or type(self.folded) is not bool:
            raise ValueError("Apuesta/contribución o estado de jugador inválido")


@dataclass(frozen=True)
class PublicAction:
    event_id: str
    player_id: str
    street: str
    kind: Kind
    amount: int = 0
    facing_bet: bool = False

    def __post_init__(self):
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError("event_id debe ser un texto no vacío")
        if self.street not in STREETS or self.kind not in ("fold", "check", "call", "raise_to"):
            raise ValueError("Acción pública inválida")
        integer(self.amount, "amount")
        if type(self.facing_bet) is not bool:
            raise ValueError("facing_bet debe ser booleano")


@dataclass(frozen=True)
class LegalActions:
    can_check: bool
    can_fold: bool
    call_amount: int
    min_raise_to: int | None = None
    max_raise_to: int | None = None

    def __post_init__(self):
        if type(self.can_check) is not bool or type(self.can_fold) is not bool:
            raise ValueError("Las acciones permitidas deben ser booleanas")
        integer(self.call_amount, "call_amount")
        if self.can_check != (self.call_amount == 0):
            raise ValueError("can_check no coincide con call_amount")
        if (self.min_raise_to is None) != (self.max_raise_to is None):
            raise ValueError("Se necesitan ambos límites de raise_to o ninguno")
        if self.min_raise_to is not None:
            integer(self.min_raise_to, "min_raise_to", 1)
            integer(self.max_raise_to, "max_raise_to", self.min_raise_to)


@dataclass(frozen=True)
class Action:
    kind: Kind
    amount: int = 0

    def is_legal(self, obs: Observation) -> bool:
        legal = obs.legal
        if type(self.amount) is not int:
            return False
        if self.kind == "check":
            return legal.can_check and self.amount == 0
        if self.kind == "fold":
            return legal.can_fold and self.amount == 0
        if self.kind == "call":
            return legal.call_amount > 0 and self.amount == 0
        return (self.kind == "raise_to" and legal.min_raise_to is not None
                and legal.min_raise_to <= self.amount <= legal.max_raise_to)

    def to_dict(self) -> dict:
        return {"kind": self.kind, **({"amount": self.amount} if self.kind == "raise_to" else {})}


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    table_id: str
    hand_id: str
    hero_id: str
    button_index: int
    players: tuple[Player, ...]
    hole_cards: tuple[str, str]
    board: tuple[str, ...]
    big_blind: int
    legal: LegalActions
    history: tuple[PublicAction, ...] = ()

    def __post_init__(self):
        if any(not isinstance(x, str) or not x for x in (self.table_id, self.hand_id, self.hero_id)):
            raise ValueError("table_id, hand_id y hero_id deben ser textos no vacíos")
        if not 2 <= len(self.players) <= 6:
            raise ValueError("Esta versión admite de 2 a 6 jugadores")
        ids = [p.player_id for p in self.players]
        if len(set(ids)) != len(ids) or self.hero_id not in ids:
            raise ValueError("Identificadores de jugadores inválidos")
        integer(self.button_index, "button_index")
        integer(self.big_blind, "big_blind", 1)
        if self.button_index >= len(ids) or self.hero.folded or self.hero.stack == 0:
            raise ValueError("Botón o actor inválido")
        if len(self.hole_cards) != 2 or len(self.board) not in (0, 3, 4, 5):
            raise ValueError("Cantidad de cartas inválida para Hold'em")
        validate_cards(self.hole_cards + self.board)
        if any(e.player_id not in ids for e in self.history):
            raise ValueError("El historial menciona un jugador ajeno a la mesa")
        if len({e.event_id for e in self.history}) != len(self.history):
            raise ValueError("event_id repetido dentro de la mano")
        street_indices = [STREETS.index(e.street) for e in self.history]
        if street_indices != sorted(street_indices) or any(i > STREETS.index(self.street) for i in street_indices):
            raise ValueError("Historial fuera de orden o con acciones futuras")
        cost = min(self.hero.stack, max(p.street_bet for p in self.players) - self.hero.street_bet)
        if cost != self.legal.call_amount:
            raise ValueError("call_amount no coincide con apuestas y stack")
        if self.legal.max_raise_to is not None:
            if not (self.legal.min_raise_to > max(p.street_bet for p in self.players)
                    and self.legal.max_raise_to <= self.hero.stack + self.hero.street_bet):
                raise ValueError("Límites de raise_to incompatibles con el estado")
        if len(self.opponents) == 0:
            raise ValueError("La mano necesita al menos un rival activo")

    @property
    def hero(self) -> Player:
        return next(p for p in self.players if p.player_id == self.hero_id)

    @property
    def opponents(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if p.player_id != self.hero_id and not p.folded)

    @property
    def street(self) -> str:
        return STREETS[{0: 0, 3: 1, 4: 2, 5: 3}[len(self.board)]]

    @property
    def pot(self) -> int:
        return sum(p.contribution for p in self.players)

    @property
    def position(self) -> str:
        n = len(self.players)
        index = next(i for i, p in enumerate(self.players) if p.player_id == self.hero_id)
        offset = (index - self.button_index) % n
        if n == 2:
            return ("BTN", "BB")[offset]
        middle = {3: (), 4: ("CO",), 5: ("HJ", "CO"), 6: ("UTG", "HJ", "CO")}[n]
        return (("BTN", "SB", "BB") + middle)[offset]

    def call_pots(self) -> tuple[Pot, ...]:
        """Contributions after ONLY hero calls, including dead money and refunds.

        No future calls are assumed. Layers hero cannot win are excluded.
        A single-eligible-player layer includes any return of unmatched chips.
        """
        contributions = {p.player_id: p.contribution + (self.legal.call_amount if p == self.hero else 0)
                         for p in self.players}
        pots = []
        previous = 0
        for level in sorted(set(contributions.values()) - {0}):
            amount = (level - previous) * sum(c >= level for c in contributions.values())
            eligible = tuple(p.player_id for p in self.players if not p.folded and contributions[p.player_id] >= level)
            if self.hero_id in eligible:
                pots.append(Pot(amount, eligible))
            previous = level
        return tuple(pots)

    @classmethod
    def from_dict(cls, data: dict) -> Observation:
        required = {"table_id", "hand_id", "hero_id", "button_index", "players", "hole_cards", "board", "big_blind", "legal"}
        fields(data, required | {"schema_version", "history"}, required)
        if type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) != 1:
            raise ValueError("schema_version incompatible")
        for p in data["players"]:
            fields(p, {"player_id", "stack", "street_bet", "contribution", "folded"}, {"player_id", "stack", "street_bet", "contribution"})
        fields(data["legal"], {"can_check", "can_fold", "call_amount", "min_raise_to", "max_raise_to"}, {"can_check", "can_fold", "call_amount"})
        for e in data.get("history", []):
            fields(e, {"event_id", "player_id", "street", "kind", "amount", "facing_bet"}, {"event_id", "player_id", "street", "kind"})
        return cls(**{k: data[k] for k in required - {"players", "hole_cards", "board", "legal"}},
                   players=tuple(Player(**p) for p in data["players"]),
                   hole_cards=tuple(data["hole_cards"]), board=tuple(data["board"]),
                   legal=LegalActions(**data["legal"]),
                   history=tuple(PublicAction(**e) for e in data.get("history", [])))


def safe_action(obs: Observation) -> Action:
    return Action("check" if obs.legal.can_check else "fold" if obs.legal.can_fold else "call")

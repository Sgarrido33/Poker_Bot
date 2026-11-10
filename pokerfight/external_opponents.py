"""Observation-only boundary for the independently authored Fullhouse agent.

The bundled 6-max model is not Pluribus. Its original encoder, weights and
short-stack overlay are preserved. Only 50/100, no-ante tables are supported;
unsupported public states fail loudly instead of silently playing a fallback.
The same weights run at 2-5 players, without claiming training in those formats.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from time import perf_counter
from types import FunctionType

import eval7

from .cards import DECK, EVAL_CARDS, CARD_INDEX
from .domain import Action, Observation, STREETS
from .strategy import Decision


def verify_fullhouse() -> dict:
    root = Path(__file__).parent / "external" / "fullhouse"
    source = json.loads((root / "SOURCE.json").read_text(encoding="utf-8"))
    for name, digest in source["runtime_files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Fullhouse artifact changed: {name}")
    return source


def fullhouse_state(obs: Observation) -> dict:
    """Translate public history, including posted blinds and street boundaries.

    Reconstruct wagers independently and check against the observation. This
    detects missing history, nonstandard blinds and antes rather than fabricating
    training features. No deck, other holes, future board or simulator is passed.
    """
    if obs.big_blind != 100:
        raise ValueError("Fullhouse adapter requires fixed 50/100 blinds")
    ids = [p.player_id for p in obs.players]
    n = len(ids)
    sb = obs.button_index if n == 2 else (obs.button_index + 1) % n
    bb = (sb + 1) % n
    bets = [0] * n
    invested = [0] * n
    log = []
    for seat, amount, kind in ((sb, 50, "small_blind"), (bb, 100, "big_blind")):
        amount = min(amount, obs.players[seat].stack + obs.players[seat].contribution)
        bets[seat] = invested[seat] = amount
        log.append({"seat": seat, "action": kind, "amount": amount})
    street = 0
    for event in obs.history:
        target = STREETS.index(event.street)
        while street < target:
            log.append({"action": "deal"})
            bets = [0] * n
            street += 1
        seat = ids.index(event.player_id)
        if event.kind == "raise_to":
            increment = event.amount - bets[seat]
            if increment <= 0:
                raise ValueError("Non-increasing public raise")
            bets[seat] = event.amount
            invested[seat] += increment
        elif event.kind == "call":
            bets[seat] += event.amount
            invested[seat] += event.amount
        log.append({"seat": seat, "action": "raise" if event.kind == "raise_to" else event.kind,
                    "amount": event.amount})
    while street < STREETS.index(obs.street):
        log.append({"action": "deal"})
        bets = [0] * n
        street += 1
    if any((bets[i], invested[i]) != (p.street_bet, p.contribution) for i, p in enumerate(obs.players)):
        raise ValueError("Fullhouse requires complete history, 50/100 blinds and no ante")
    hero = ids.index(obs.hero_id)
    # Upstream uses the UNCAPPED amount owed in its encoder, even for a short call.
    owed = max(bets) - bets[hero]
    return {"type": "action_request", "hand_id": obs.hand_id, "street": obs.street,
            "seat_to_act": hero, "dealer": obs.button_index, "pot": obs.pot,
            "community_cards": list(obs.board), "your_cards": list(obs.hole_cards),
            "current_bet": max(bets), "min_raise_to": obs.legal.min_raise_to or 0,
            "amount_owed": owed, "can_check": obs.legal.can_check,
            "your_stack": obs.hero.stack, "your_bet_this_street": obs.hero.street_bet,
            "players": [{"seat": i, "stack": p.stack, "bet_this_street": p.street_bet,
                         "is_folded": p.folded, "is_all_in": not p.folded and p.stack == 0}
                        for i, p in enumerate(obs.players)], "action_log": log}


def fullhouse_action(proposal: dict, obs: Observation) -> tuple[Action, str | None]:
    """Translate engine verbs, with PokerKit's raise rights authoritative.

    A request to move all chips is a call when raising is closed (not a new
    raise). Upstream's preflop overlay bypasses its own legal mask, so this case
    is explicit and counted. Unknown/invalid proposals are never hidden.
    """
    kind = proposal["action"]
    adjustment = None
    if kind == "all_in":
        if obs.legal.min_raise_to is None:
            action = Action("call" if obs.legal.call_amount else "check")
            adjustment = "all_in_as_call_or_check"
        else:
            action = Action("raise_to", obs.legal.max_raise_to)
    elif kind == "raise":
        action = Action("raise_to", proposal["amount"])
    elif kind in ("fold", "call", "check"):
        action = Action("check" if kind in ("fold", "call") and obs.legal.can_check else kind)
    else:
        raise ValueError(f"Unknown Fullhouse action: {proposal}")
    if not action.is_legal(obs):
        raise ValueError(f"Illegal Fullhouse proposal: {proposal}")
    return action, adjustment


class FullhouseOpponent:
    def __init__(self, seed: int):
        verify_fullhouse()
        from .external.fullhouse import bot
        self.runtime = bot
        # Exact upstream sampler code, a private globals dict and instance RNG.
        # No changing module/global random state or cross-seat coupling.
        self.sample = FunctionType(bot._sample.__code__, {**bot._sample.__globals__, "_RNG": random.Random(seed)})
        self.counts = Counter()

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        state = fullhouse_state(obs)
        proposal = self.runtime._push_fold(state) if obs.street == "preflop" else None
        branch = "overlay" if proposal is not None else "network"
        if proposal is None:
            probabilities = self.runtime._DEEP_CFR.get_strategy(state)
            probabilities = self.runtime._apply_legal_mask(probabilities, state)
            proposal = self.runtime._to_engine_action(self.sample(probabilities), state)
        action, adjustment = fullhouse_action(proposal, obs)
        self.counts[branch] += 1
        if adjustment:
            self.counts[adjustment] += 1
        reason = "external:fullhouse:" + branch + (":" + adjustment if adjustment else "")
        return Decision(action, reason, (perf_counter() - started) * 1000, False)


def verify_honest() -> dict:
    """Verify the pinned PyPokerEngine example and its MIT notice."""
    root = Path(__file__).parent / "external" / "honest"
    source = json.loads((root / "SOURCE.json").read_text(encoding="utf-8"))
    for name, digest in source["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest().casefold() != digest.casefold():
            raise ValueError(f"PyPokerEngine source artifact changed: {name}")
    return source


def honest_win_rate(obs: Observation, rng: random.Random, samples: int = 1000,
                    nb_players: int | None = None) -> float:
    """PyPokerEngine HonestPlayer's Monte Carlo win-rate, adapted to Eval7.

    As upstream, every seat is treated as a random opponent for the sampled
    showdown, and a tied best hand counts as a win. The table size therefore
    stays len(players), including seats that folded; their actual cards remain
    hidden and are only random samples here. This is intentionally a crude
    fold/call baseline, not an equity-vs-range model.
    """
    if type(samples) is not int or samples < 1:
        raise ValueError("samples debe ser un entero positivo")
    nb_players = len(obs.players) if nb_players is None else nb_players
    if type(nb_players) is not int or not 2 <= nb_players <= 6:
        raise ValueError("nb_players debe estar entre 2 y 6")
    known = set(obs.hole_cards + obs.board)
    available = [card for card in DECK if card not in known]
    missing_board = 5 - len(obs.board)
    opponent_cards = 2 * (nb_players - 1)
    draw_count = missing_board + opponent_cards
    if draw_count > len(available):
        raise ValueError("No hay cartas suficientes para la simulación HonestPlayer")
    hero_hole = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards]
    current_board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board]
    wins = 0
    for _ in range(samples):
        draw = rng.sample(available, draw_count)
        board = current_board + [EVAL_CARDS[CARD_INDEX[c]] for c in draw[:missing_board]]
        opponents = draw[missing_board:]
        best_opponent = max(
            eval7.evaluate([EVAL_CARDS[CARD_INDEX[opponents[i]]],
                            EVAL_CARDS[CARD_INDEX[opponents[i + 1]]]] + board)
            for i in range(0, len(opponents), 2)
        )
        # PyPokerEngine's source uses my_score >= max(opponents_score): ties
        # count as wins instead of fractional pot equity.
        wins += eval7.evaluate(hero_hole + board) >= best_opponent
    return wins / samples


class HonestOpponent:
    """Independent adapter of PyPokerEngine's educational HonestPlayer."""

    def __init__(self, seed: int, samples: int = 1000):
        verify_honest()
        if type(seed) is not int:
            raise ValueError("seed debe ser entero")
        if type(samples) is not int or samples < 1:
            raise ValueError("samples debe ser un entero positivo")
        self.rng = random.Random(seed)
        self.samples = samples
        self.table_sizes: dict[str, int] = {}

    def start_table(self, table_id: str, player_count: int) -> None:
        """Record the original seat count, matching HonestPlayer's game-start callback."""
        if not isinstance(table_id, str) or not table_id:
            raise ValueError("table_id debe ser un texto no vacío")
        if type(player_count) is not int or not 2 <= player_count <= 6:
            raise ValueError("player_count debe estar entre 2 y 6")
        self.table_sizes.setdefault(table_id, player_count)

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        # PokerFight calls start_table once before play; this fallback keeps
        # direct uses compatible with the current observation size.
        player_count = self.table_sizes.get(obs.table_id, len(obs.players))
        win_rate = honest_win_rate(obs, self.rng, self.samples, player_count)
        # Upstream tests against 1 / player_num and takes CALL at equality.
        qualifies = win_rate >= 1.0 / player_count
        if qualifies:
            action = Action("call" if obs.legal.call_amount else "check")
        elif obs.legal.can_fold:
            action = Action("fold")
        else:
            action = Action("call" if obs.legal.call_amount else "check")
        if not action.is_legal(obs):
            raise ValueError(f"Acción HonestPlayer ilegal: {action}")
        reason = f"external:honest:win_rate={win_rate:.3f}:threshold={1 / player_count:.3f}"
        return Decision(action, reason, (perf_counter() - started) * 1000, False)

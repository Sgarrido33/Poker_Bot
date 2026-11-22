"""Local PokerKit adapter. Policies receive only an Observation.

Deck, holes, burns and runout are fixed before actions. Folding does not
change which board is dealt. No module-global random seed is used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import random
from time import perf_counter
from typing import Protocol

from pokerkit import Automation, NoLimitTexasHoldem

from .cards import DECK
from .domain import Action, LegalActions, Observation, Player, PublicAction, safe_action
from .preflop import OPEN_RANGES, PREMIUM, in_range
from .strategy import BotConfig, Decision, LegacyPokerBot, PokerBot, raise_to

POLICY_KINDS = ("v1", "v2", "v3", "v4", "v4rb", "v5", "v6", "v7", "v8", "v8b", "v8c", "v8d", "v8d_open", "v8d_reshove", "v8d_call", "v9", "v2mc", "v2_4000", "calling", "tight", "random", "tag", "lag", "pressure", "fullhouse", "honest", "noregrets")


def seed_for(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big")


class Policy(Protocol):
    def decide(self, obs: Observation) -> Decision: ...


class Baseline:
    """Deliberately simple opponents for plumbing and initial comparisons."""
    def __init__(self, kind: str, seed: int):
        if kind not in ("calling", "random", "tight"):
            raise ValueError(f"Política desconocida: {kind}")
        self.kind = kind
        self.rng = random.Random(seed)

    def decide(self, obs: Observation) -> Decision:
        started = perf_counter()
        cost = obs.legal.call_amount
        action = safe_action(obs)
        if self.kind == "calling":
            action = Action("call" if cost else "check")
        elif self.kind == "random":
            if self.rng.random() < 0.10:
                action = raise_to(obs, max(p.street_bet for p in obs.players) + 0.5 * (obs.pot + cost)) or action
            elif not cost or self.rng.random() < 0.65:
                action = Action("call" if cost else "check")
        elif obs.street == "preflop":
            premium = in_range(obs.hole_cards, PREMIUM)
            unopened = max(p.street_bet for p in obs.players) <= obs.big_blind
            if premium or (unopened and in_range(obs.hole_cards, OPEN_RANGES[obs.position])):
                action = raise_to(obs, max(2.5 * obs.big_blind, 3 * max(p.street_bet for p in obs.players))) or Action("call" if cost else "check")
            elif in_range(obs.hole_cards, OPEN_RANGES[obs.position]) and cost <= 3 * obs.big_blind:
                action = Action("call" if cost else "check")
        else:
            # Check/call small prices; no hidden information or evaluation.
            if not cost or cost <= max(obs.big_blind, obs.pot // 5):
                action = Action("call" if cost else "check")
        return Decision(action, "baseline:" + self.kind, (perf_counter() - started) * 1000, False)


def make_policy(kind: str, config: BotConfig, seed: int) -> Policy:
    if kind == "honest":
        from .external_opponents import HonestOpponent
        return HonestOpponent(seed)
    if kind == "noregrets":
        import os
        from pathlib import Path
        from .noregrets_opponent import NoRegretsTableOpponent
        profiles = Path(os.environ.get("POKERFIGHT_NOREGRETS_PROFILES",
                         Path(__file__).resolve().parents[1] / "research/noregrets_training_20261028/profiles_index_validated.json"))
        return NoRegretsTableOpponent(seed, profiles, timeout_s=4.25)
    if kind == "v2_4000":
        # Explicit rival profile. Never inherit the hero's sample/budget quota.
        from .controls import ControlBot
        return ControlBot(BotConfig(4000, 1600, seed, config.confidence_cap, config.prior_observations))
    if kind == "fullhouse":
        from .external_opponents import FullhouseOpponent
        return FullhouseOpponent(seed)
    if kind in ("tag", "lag", "pressure"):
        from .rivals import RuleOpponent
        return RuleOpponent(kind, seed)
    if kind in ("v1", "v2", "v3", "v4", "v4rb", "v5", "v6", "v7", "v8", "v8b", "v8c", "v8d", "v8d_open", "v8d_reshove", "v8d_call", "v9", "v2mc"):
        settings = BotConfig(config.samples, config.budget_ms, seed,
                             config.confidence_cap, config.prior_observations)
        if kind == "v9":
            from .postflop_ranges import PostflopRangeBot
            return PostflopRangeBot(settings)
        if kind == "v3":
            from .shortstack import ShortStackBot
            return ShortStackBot(settings)
        if kind.startswith("v8d"):
            from .guarded_pushfold import GuardedPushFoldBot, OpeningChartBot, ReshoveChartBot, CallingChartBot
            return {"v8d": GuardedPushFoldBot, "v8d_open": OpeningChartBot,
                    "v8d_reshove": ReshoveChartBot, "v8d_call": CallingChartBot}[kind](settings)
        if kind == "v4":
            from .action_search import ActionSearchBot
            return ActionSearchBot(settings)
        if kind == "v6":
            from .terminal_search import TerminalSearchBot
            return TerminalSearchBot(settings)
        if kind in ("v8", "v8b", "v8c"):
            from .pushfold_bot import ConfirmedPushFoldBot, IsolationPushFoldBot, PushFoldBot
            return {"v8": PushFoldBot, "v8b": IsolationPushFoldBot, "v8c": ConfirmedPushFoldBot}[kind](settings)
        if kind == "v7":
            from .integrated_response_search import IntegratedResponseBot
            return IntegratedResponseBot(settings)
        if kind in ("v4rb", "v5"):
            from .response_search import IntegratedSearchBot, ResponseSearchBot
            return (IntegratedSearchBot if kind == "v4rb" else ResponseSearchBot)(settings)
        from .controls import ControlBot
        return ControlBot(settings, legacy=kind == "v1", extended_budget=kind == "v2mc")
    return Baseline(kind, seed)


def close_policies(policies: dict[str, Policy]) -> None:
    """Close policy-owned workers once a table/batch ends, even on exceptions."""
    seen: set[int] = set()
    first_error = None
    for policy in policies.values():
        if id(policy) in seen:
            continue
        seen.add(id(policy))
        close = getattr(policy, "close", None)
        if close is None:
            continue
        try:
            close()
        except Exception as error:  # close all remaining workers before surfacing it
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


def observation(state, ids: tuple[str, ...], table_id: str, hand_id: str,
                history: tuple[PublicAction, ...], big_blind: int) -> Observation:
    actor = state.actor_index
    if actor is None:
        raise ValueError("El motor no espera una decisión")
    can_raise = state.can_complete_bet_or_raise_to()
    legal = LegalActions(
        can_check=state.checking_or_calling_amount == 0,
        can_fold=state.can_fold(),
        call_amount=state.checking_or_calling_amount,
        min_raise_to=state.min_completion_betting_or_raising_to_amount if can_raise else None,
        max_raise_to=state.max_completion_betting_or_raising_to_amount if can_raise else None,
    )
    return Observation(
        table_id, hand_id, ids[actor], len(ids) - 1,
        tuple(Player(pid, state.stacks[i], state.bets[i], -state.payoffs[i], not state.statuses[i]) for i, pid in enumerate(ids)),
        tuple(f"{c.rank}{c.suit}" for c in state.hole_cards[actor]),
        tuple(f"{c.rank}{c.suit}" for c in state.get_board_cards(0)), big_blind, legal, history,
    )


@dataclass(frozen=True)
class HandResult:
    stacks: dict[str, int]
    payoffs: dict[str, int]
    history: tuple[PublicAction, ...]
    decisions: tuple[tuple[str, Decision], ...]
    board: tuple[str, ...]
    trace: tuple[dict, ...] = ()
    big_blind: int = 100


def play_hand(policies: dict[str, Policy], seat_ids: tuple[str, ...], stacks: dict[str, int],
              deck_seed: int, hand_id: str = "1", table_id: str = "local",
              small_blind: int = 50, big_blind: int = 100, ante: int = 0,
              trace_player_id: str | None = None) -> HandResult:
    if not 2 <= len(seat_ids) <= 6 or len(set(seat_ids)) != len(seat_ids):
        raise ValueError("Se requieren 2 a 6 asientos con identificadores únicos")
    if (type(big_blind) is not int or type(small_blind) is not int or type(ante) is not int
            or not 0 < small_blind <= big_blind or ante < 0):
        raise ValueError("Ciegas o ante inválidos")
    if any(type(stacks[pid]) is not int or stacks[pid] <= 0 for pid in seat_ids):
        raise ValueError("Cada jugador debe empezar con fichas enteras positivas")
    # PyPokerEngine fixes HonestPlayer's player count at game start, including
    # seats eliminated later. Supply only public table identity and seat count.
    from .external_opponents import HonestOpponent
    for pid in seat_ids:
        if isinstance(policies[pid], HonestOpponent):
            policies[pid].start_table(table_id, len(seat_ids))
    automations = tuple(a for a in Automation if a not in (
        Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
    state = NoLimitTexasHoldem.create_state(automations, True, ante,
        (small_blind, big_blind), big_blind, [stacks[pid] for pid in seat_ids], len(seat_ids))
    deck = list(DECK)
    random.Random(deck_seed).shuffle(deck)
    # Preset every chance outcome; no engine randomness reaches a decision.
    for i in range(len(seat_ids)):
        state.deal_hole("".join(deck[2 * i:2 * i + 2]), i)
    offset = 2 * len(seat_ids)
    burns = {0: deck[offset], 3: deck[offset + 4], 4: deck[offset + 6]}
    boards = {0: "".join(deck[offset + 1:offset + 4]), 3: deck[offset + 5], 4: deck[offset + 7]}
    history: list[PublicAction] = []
    decisions: list[tuple[str, Decision]] = []
    trace = []
    while state.status:
        if len(history) > 1000:
            raise RuntimeError("Demasiadas acciones en una mano")
        if state.actor_index is None:
            count = len(tuple(state.get_board_cards(0)))
            if state.can_burn_card():
                state.burn_card(burns[count])
            elif state.can_deal_board():
                state.deal_board(boards[count])
            else:
                raise RuntimeError("Estado del simulador sin decisión ni reparto pendiente")
            continue
        obs = observation(state, seat_ids, table_id, hand_id, tuple(history), big_blind)
        decision = policies[obs.hero_id].decide(obs)
        action = decision.action
        if not action.is_legal(obs):
            raise RuntimeError(f"Política {obs.hero_id} produjo acción ilegal: {action}")
        if obs.hero_id == trace_player_id:
            trace.append({"observation": asdict(obs), "decision": decision.to_dict()})
        event = PublicAction(str(len(history)), obs.hero_id, obs.street, action.kind,
                             action.amount if action.kind == "raise_to" else obs.legal.call_amount if action.kind == "call" else 0,
                             obs.legal.call_amount > 0)
        # PokerKit is a second independent authority on action legality.
        if action.kind == "fold":
            state.fold()
        elif action.kind in ("check", "call"):
            state.check_or_call()
        else:
            state.complete_bet_or_raise_to(action.amount)
        history.append(event)
        decisions.append((obs.hero_id, decision))
    final = {pid: state.stacks[i] for i, pid in enumerate(seat_ids)}
    if sum(final.values()) != sum(stacks[pid] for pid in seat_ids) or min(final.values()) < 0:
        raise RuntimeError("El simulador no conservó las fichas")
    for policy in policies.values():
        if isinstance(policy, PokerBot):
            policy.model.observe(table_id, hand_id, tuple(history))
    return HandResult(final, {pid: final[pid] - stacks[pid] for pid in seat_ids},
                      tuple(history), tuple(decisions), tuple(f"{c.rank}{c.suit}" for c in state.get_board_cards(0)), tuple(trace), big_blind)

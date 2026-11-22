"""TCP client for the PokerFight Mesa protocol v1.0.0."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from random import uniform
from select import select
import socket
import sys
from time import perf_counter, sleep

from .domain import Action, LegalActions, Observation, Player, PublicAction
from .strategy import BotConfig
from .supervision import SupervisedPolicy


VERSION = "1.0.0"
MAX_LINE = 1024 * 1024
SATURATED = "demasiadas conexiones esperando el saludo"
# Versión entregada: v2 (4 000 muestras, 1 600 ms de cálculo, corte local a 3 000 ms).
PROFILES = {"v2": (BotConfig(), 3000)}


def card(value: dict) -> str:
    return "23456789TJQKA"[value["rango"] - 2] + "cdhs"[value["palo"]]


def players_in_hand(state: dict) -> list[dict]:
    return sorted((p for p in state["jugadores"] if p["en_mano"]),
                  key=lambda p: p["posicion_silla"])


class Hand:
    def __init__(self, message: dict):
        state = message["estado"]
        self.id = state["id_mano"]
        self.cards = tuple(card(value) for value in message["cartas"])
        initial = players_in_hand(state)
        self.blinds = {p["id"]: p["apuesta_ronda"] for p in initial}
        self.starting_stacks = {p["id"]: p["saldo"] + p["apuesta_ronda"] for p in initial}

    def history(self, state: dict) -> tuple[PublicAction, ...]:
        # Call and all-in have no wire amount. Replay them from the posted blinds
        # and the starting stacks to recover how much each player actually paid.
        bets = self.blinds.copy()
        remaining = {pid: stack - bets[pid] for pid, stack in self.starting_stacks.items()}
        street = "preflop"
        highest = state["ciega_grande"]
        actions = []
        for index, event in enumerate(state.get("historial_acciones") or ()):
            if event["etapa"] != street:
                street = event["etapa"]
                bets = dict.fromkeys(bets, 0)
                highest = 0
            pid = event["id_jugador"]
            action = event["accion"]
            kind = action["tipo"]
            pending = highest - bets[pid]
            amount = 0
            if kind in ("call", "allin", "bet", "raise"):
                if kind == "call":
                    paid = min(pending, remaining[pid])
                elif kind == "allin":
                    paid = remaining[pid]
                else:
                    paid = action["monto"] - bets[pid]
                remaining[pid] -= paid
                bets[pid] += paid
                if bets[pid] > highest:
                    highest = bets[pid]
                    kind, amount = "raise_to", highest
                else:
                    kind, amount = "call", paid
            actions.append(PublicAction(str(index), pid, street, kind, amount, pending > 0))
        return tuple(actions)

    def observation(self, message: dict, hero_id: str) -> Observation:
        state = message["estado"]
        if state["id_mano"] != self.id:
            raise ValueError("Falta el inicio de la mano solicitada")
        seated = players_in_hand(state)
        players = tuple(Player(p["id"], p["saldo"], p["apuesta_ronda"],
                               self.starting_stacks[p["id"]] - p["saldo"], not p["activo"])
                        for p in seated)
        if sum(p.contribution for p in players) != state["pozo"]:
            raise ValueError("Los aportes no coinciden con el pozo de la Mesa")
        hero = next(p for p in players if p.player_id == hero_id)
        button = [p["posicion_silla"] for p in seated].index(state["posicion_boton"])
        valid = message["acciones_validas"]
        current_bet = state["apuesta_actual"]
        call = min(hero.stack, current_bet - hero.street_bet)
        if call != min(hero.stack, max(p.street_bet for p in players) - hero.street_bet):
            # The official nominal blind can exceed all actual bets when the BB
            # is short. v2 derives the call from the real bets in its observation.
            raise ValueError("La ciega nominal supera las apuestas que puede representar v2")
        minimum = current_bet + state["subida_minima"]
        ceiling = hero.stack + hero.street_bet
        can_raise = (ceiling > current_bet and (
            (ceiling >= minimum and ("bet" in valid or "raise" in valid)) or "allin" in valid))
        legal = LegalActions("check" in valid, "fold" in valid, call,
                             min(minimum, ceiling) if can_raise else None,
                             ceiling if can_raise else None)
        return Observation(self.id.rpartition("-mano-")[0] or self.id, self.id, hero_id,
                           button, players, self.cards,
                           tuple(card(value) for value in state.get("comunitarias") or ()),
                           state["ciega_grande"], legal, self.history(state))


def wire_action(action: Action, message: dict) -> dict:
    valid = message["acciones_validas"]
    if action.kind == "raise_to":
        state = message["estado"]
        if action.amount < state["apuesta_actual"] + state["subida_minima"]:
            result = {"tipo": "allin"}
        else:
            result = {"tipo": "bet" if "bet" in valid else "raise", "monto": action.amount}
    else:
        result = {"tipo": action.kind}
    if result["tipo"] not in valid:
        raise ValueError("La acción traducida no está autorizada por la Mesa")
    return result


def send(connection: socket.socket, kind: str, **payload: object) -> None:
    message = {"tipo": kind, "version": VERSION, **payload}
    connection.sendall((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))


def read_line(connection, buffer, deadline):
    while True:
        end = buffer.find(b"\n")
        if end >= MAX_LINE or end < 0 and len(buffer) >= MAX_LINE:
            raise ValueError("La Mesa envió una línea demasiado larga")
        if end >= 0:
            line = bytes(buffer[:end + 1])
            del buffer[:end + 1]
            return line
        remaining = deadline - perf_counter()
        if remaining <= 0:
            raise TimeoutError("Venció el plazo de lectura")
        # Poll only to allow Ctrl+C or the requested stop time. Silence is normal.
        if not select([connection], [], [], min(1, remaining))[0]:
            continue
        data = connection.recv(64 * 1024)
        if not data:
            if buffer:
                raise ConnectionError("EOF a mitad de un mensaje")
            return None
        buffer.extend(data)


class Session:
    def __init__(self, bot, log):
        self.bot, self.log = bot, log
        self.stats = dict.fromkeys((
            "hands", "actions", "adapter_fallbacks", "policy_fallbacks", "late_responses",
            "skipped_responses", "max_response_ms", "connections", "disconnects",
            "connection_failures", "server_errors", "matched", "substituted", "unconfirmed",
        ), 0)
        self.hand = self.hero_id = self.pending = self.table = None
        self.logged_hand = None
        self.logged_actions = 0

    def observe(self, state=None):
        history = (state.get("historial_acciones") or []) if state else []
        if self.pending:
            hand_id, index, sent = self.pending
            same_hand = state and state["id_mano"] == hand_id
            if same_hand and len(history) <= index:
                return
            actual = history[index] if same_hand else None
            outcome = "unconfirmed"
            if actual and actual["id_jugador"] == self.hero_id:
                action = actual["accion"]
                outcome = "matched" if (action["tipo"], action.get("monto", 0)) == (
                    sent["tipo"], sent.get("monto", 0)) else "substituted"
            self.stats[outcome] += 1
            self.log("action_outcome", hand=hand_id, index=index, outcome=outcome, actual=actual)
            self.pending = None
        if state:
            hand_id = state["id_mano"]
            if self.logged_hand != hand_id:
                self.logged_hand, self.logged_actions = hand_id, 0
            new_history = len(history) > self.logged_actions
            for index in range(self.logged_actions, len(history)):
                self.log("public_action", hand=hand_id, index=index, action=history[index])
            self.logged_actions = max(self.logged_actions, len(history))
            # Keep learning after hero folds. The local arena supplies the
            # complete public history; official state broadcasts carry it too.
            observer = getattr(self.bot, "observe", None)
            if new_history and self.hand and self.hand.id == hand_id and callable(observer):
                try:
                    table_id = hand_id.rpartition("-mano-")[0] or hand_id
                    if not observer(table_id, hand_id, self.hand.history(state)):
                        self.log("model_observation_error", hand=hand_id, reason="worker_rejected_history")
                except Exception as error:
                    self.log("model_observation_error", hand=hand_id,
                             reason=f"{type(error).__name__}:{error}")

    def respond(self, connection, message, started):
        state = message["estado"]
        hand_id = state["id_mano"]
        timeout_ms = message["timeout_ms"]
        # Reserve network time, even when the mesa advertises less than 5 s.
        expires = started + timeout_ms / 1000
        deadline = expires - min(1000, timeout_ms / 4) / 1000
        try:
            if self.hand is None:
                raise ValueError("Falta el inicio de la mano")
            obs = self.hand.observation(message, self.hero_id)
            decision = self.bot.decide(obs, deadline=deadline)
            action = wire_action(decision.action, message)
            self.stats["policy_fallbacks"] += int(decision.fallback)
            source = "policy_fallback" if decision.fallback else "policy"
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as error:
            valid = message["acciones_validas"]
            action = {"tipo": "check" if "check" in valid else "fold"}
            if action["tipo"] not in valid:
                raise ValueError("La Mesa no anunció una acción de respaldo") from error
            self.stats["adapter_fallbacks"] += 1
            self.log("adapter_fallback", hand=hand_id, reason=str(error))
            source = "adapter_fallback"
        # A stale response can be consumed by a later turn of the same hand.
        remaining = expires - min(250, timeout_ms / 8) / 1000 - perf_counter()
        if remaining <= 0:
            self.stats["skipped_responses"] += 1
            self.log("action_skipped", hand=hand_id, timeout_ms=timeout_ms)
            return
        connection.settimeout(remaining)
        try:
            send(connection, "accion", id_mano=hand_id, accion=action)
        finally:
            connection.settimeout(None)
        elapsed = round((perf_counter() - started) * 1000, 3)
        self.stats["actions"] += 1
        self.stats["late_responses"] += int(elapsed >= timeout_ms)
        self.stats["max_response_ms"] = max(self.stats["max_response_ms"], elapsed)
        index = len(state.get("historial_acciones") or [])
        self.pending = hand_id, index, action
        self.log("action_sent", hand=hand_id, index=index, action=action, source=source,
                 response_ms=elapsed, timeout_ms=timeout_ms)

    def read(self, connection, token, stop_at):
        welcomed = False
        handshake_deadline = min(stop_at, perf_counter() + 5)
        send(connection, "saludo", token=token)
        buffer = bytearray()
        while perf_counter() < stop_at:
            line = read_line(connection, buffer, stop_at if welcomed else handshake_deadline)
            if line is None:
                break
            started = perf_counter()
            message = json.loads(line)
            kind = message["tipo"]
            if kind == "error":
                reason = message.get("mensaje", "Error de la Mesa")
                self.stats["server_errors"] += 1
                self.log("server_error", reason=reason, handshake=not welcomed)
                if reason == SATURATED:
                    raise ConnectionError(reason)
                raise ValueError(reason)
            if not welcomed:
                if kind != "bienvenida":
                    raise ValueError("La Mesa no envió la bienvenida")
                welcomed = True
                connection.settimeout(None)
                hero_id = message["id_jugador"]
                if hero_id != self.hero_id:
                    self.observe()
                    self.hand = self.table = self.logged_hand = None
                self.hero_id = hero_id
                self.stats["connections"] += 1
                self.log("welcome", alias=hero_id, seat=message.get("silla", 0))
            elif kind == "mano_inicio":
                self.observe()
                self.hand = Hand(message)
                table = self.hand.id.rpartition("-mano-")[0] or self.hand.id
                if table != self.table:
                    self.table = table
                    self.log("table", table=table, players=len(self.hand.starting_stacks),
                             stack=self.hand.starting_stacks.get(self.hero_id))
            elif kind == "mano_fin":
                self.observe()
                result = message["resultado"]
                self.stats["hands"] += 1
                if self.hand and self.hand.id == result["id_mano"]:
                    self.hand = None
                self.log("hand_end", hand=result["id_mano"], shown=result.get("mostradas"),
                         payouts=result.get("repartos"))
            elif kind == "estado":
                self.observe(message["estado"])
            elif kind == "solicitar_accion":
                self.observe(message["estado"])
                self.respond(connection, message, started)
        if not welcomed:
            raise ConnectionError("EOF antes de la bienvenida")


def keepalive(connection):
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    for name, value in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 3), ("TCP_KEEPCNT", 3)):
        option = getattr(socket, name, None)
        if option is not None:
            connection.setsockopt(socket.IPPROTO_TCP, option, value)


def redact(value, token):
    if isinstance(value, str):
        return value.replace(token, "[oculto]")
    if isinstance(value, dict):
        return {redact(key, token): redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    return value


def play(address: tuple[str, int], token: str, *, policy="v2", reconnect=True,
         duration=None, journal=None) -> dict:
    def log(event, **fields):
        if journal is not None:
            record = {"utc": datetime.now(timezone.utc).isoformat(), "event": event,
                      **{key: redact(value, token) for key, value in fields.items()}}
            print(json.dumps(record, ensure_ascii=False), file=journal, flush=True)
        elif event == "adapter_fallback":
            reason = redact(fields["reason"], token)
            print(f"PokerFight: respaldo del adaptador ({reason})", file=sys.stderr, flush=True)

    config, timeout = PROFILES[policy]
    with SupervisedPolicy(config, timeout, policy=policy) as bot:
        stop_at = perf_counter() + duration if duration is not None else float("inf")
        session = Session(bot, log)
        log("start", policy=policy, address=f"{address[0]}:{address[1]}")
        failures = 0
        try:
            while (remaining := stop_at - perf_counter()) > 0:
                previous = session.stats["connections"]
                reason = "EOF"
                try:
                    with socket.create_connection(address, timeout=min(5, remaining)) as connection:
                        keepalive(connection)
                        session.read(connection, token, stop_at)
                except OSError as error:
                    if perf_counter() >= stop_at:
                        break
                    if not reconnect:
                        raise
                    reason = str(error)
                if perf_counter() >= stop_at or not reconnect:
                    break
                connected = session.stats["connections"] > previous
                counter = "disconnects" if connected else "connection_failures"
                session.stats[counter] += 1
                failures = 0 if connected else min(failures + 1, 5)
                delay = min(8, 0.25 * 2 ** failures) * uniform(1, 1.5)
                log("disconnect" if connected else "connect_failed", reason=reason, retry_s=round(delay, 3))
                if journal is None:
                    print(f"PokerFight: {reason}. Reintento en {delay:.2f} s".replace(token, "[oculto]"),
                          file=sys.stderr, flush=True)
                sleep(max(0, min(delay, stop_at - perf_counter())))
        except KeyboardInterrupt:
            log("interrupted")
        finally:
            session.observe()
            log("summary", **session.stats)
    return session.stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Conecta una política a una mesa PokerFight")
    parser.add_argument("-addr", default="127.0.0.1:9000", help="Dirección host:puerto")
    parser.add_argument("-token", default=os.environ.get("POKERFIGHT_TOKEN"),
                        help="Credencial de la mesa, o variable POKERFIGHT_TOKEN")
    parser.add_argument("--policy", choices=PROFILES, default="v2")
    parser.add_argument("--once", action="store_true", help="Termina al cerrar la mesa local")
    parser.add_argument("--duration", type=int, help="Termina tras este número de segundos")
    parser.add_argument("--journal", type=Path, help="Añade eventos de diagnóstico a un archivo JSONL")
    args = parser.parse_args()
    if not args.token:
        parser.error("Indica -token o POKERFIGHT_TOKEN")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration debe ser positiva")
    try:
        host, port = args.addr.rsplit(":", 1)
        if not host or not 1 <= int(port) <= 65535:
            raise ValueError("Usa una dirección host:puerto válida")
        with args.journal.open("a", encoding="utf-8") if args.journal else nullcontext() as journal:
            stats = play((host.strip("[]"), int(port)), args.token, policy=args.policy,
                         reconnect=not args.once, duration=args.duration, journal=journal)
    except (KeyError, TypeError, ValueError, OSError) as error:
        parser.exit(1, f"PokerFight: {error}\n".replace(args.token, "[oculto]"))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()

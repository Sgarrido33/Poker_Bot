"""Exercise the official client against a controlled TCP session."""
import argparse
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
from time import perf_counter

from pokerfight.official import send


TOKEN = "fixture-local-credential"
ALIAS = "j-fixture"


def read(stream):
    return json.loads(stream.readline())


def join(listener):
    peer, _ = listener.accept()
    peer.settimeout(10)
    return peer


def greet(peer, stream):
    assert read(stream) == {"tipo": "saludo", "version": "1.0.0", "token": TOKEN}
    send(peer, "bienvenida", id_jugador=ALIAS, silla=2)


def hand(table, count, hero_stack):
    seats = [{"id": ALIAS if i == 2 else f"j-rival-{i}", "posicion_silla": i,
              "saldo": (hero_stack if i == 2 else 10_000) - bet, "apuesta_ronda": bet,
              "en_mano": True, "activo": True}
             for i, bet in enumerate([50, 100] + [0] * (count - 2))]
    return {"id_mano": f"{table}-mano-1", "posicion_boton": count - 1, "ciega_grande": 100,
            "apuesta_actual": 100, "subida_minima": 100, "pozo": 150,
            "jugadores": seats, "historial_acciones": [], "etapa": "preflop"}


def start_hand(peer, state):
    send(peer, "mano_inicio", estado=state, cartas=[{"rango": 14, "palo": 3}, {"rango": 14, "palo": 1}])


def turn(peer, stream, state):
    valid = ["fold", "call", "raise", "allin"]
    start = perf_counter()
    send(peer, "solicitar_accion", estado=state, acciones_validas=valid, timeout_ms=5000)
    reply = read(stream)
    elapsed = round((perf_counter() - start) * 1000, 3)
    assert elapsed < 4000, elapsed
    assert reply["tipo"] == "accion" and reply["id_mano"] == state["id_mano"], reply
    action = reply["accion"]
    assert action["tipo"] in valid, reply
    if action["tipo"] == "raise":
        assert 200 <= action["monto"] <= state["jugadores"][2]["saldo"], reply
    event = {"id_jugador": ALIAS, "etapa": "preflop", "accion": action}
    send(peer, "estado", estado={**state, "historial_acciones": [event]})
    send(peer, "mano_fin", resultado={"id_mano": state["id_mano"],
                                     "repartos": [{"id_jugador": ALIAS, "monto": action.get("monto", 100) + 150}]})
    return elapsed


def verify(policy, idle_seconds, journal):
    assert not journal.exists(), f"Elige una bitácora nueva: {journal}"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(20)
        address = f"127.0.0.1:{listener.getsockname()[1]}"
        command = [sys.executable, "-m", "pokerfight.official", "-addr", address, "-token", TOKEN,
                   "--policy", policy, "--journal", str(journal), "--duration", str(idle_seconds + 10)]
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as bot:
            try:
                first = hand("r1-t0", 5, 10_000)
                with join(listener) as peer, peer.makefile("rb") as stream:
                    greet(peer, stream)
                    start_hand(peer, first)
                    peer.sendall(b'{"tipo":"solicitar_')
                    cut = perf_counter()
                with join(listener) as peer, peer.makefile("rb") as stream:
                    greet(peer, stream)
                    recovered = round((perf_counter() - cut) * 1000, 3)
                    first_ms = turn(peer, stream, first)
                    # 150 won from the blinds, carried into a different six-player table.
                    before = perf_counter()
                    ready, _, _ = select.select([peer, listener], [], [], idle_seconds)
                    silence = round(perf_counter() - before, 3)
                    assert not ready, "El cliente cerró el socket, reconectó o envió datos durante el silencio"
                    second = hand("r2-t1", 6, 10_150)
                    start_hand(peer, second)
                    second_ms = turn(peer, stream, second)
                    output, errors = bot.communicate(timeout=15)
                    assert bot.returncode == 0, errors
                    assert json.loads(output)["hands"] == 2
            finally:
                if bot.poll() is None:
                    bot.kill()
                    bot.communicate(timeout=5)
    rows = events(journal)
    assert sum(r["event"] == "welcome" for r in rows) == 2
    assert sum(r["event"] == "disconnect" for r in rows) == 1
    assert [r["source"] for r in rows if r["event"] == "action_sent"] == ["policy", "policy"]
    assert [r["outcome"] for r in rows if r["event"] == "action_outcome"] == ["matched", "matched"]
    assert [(r["players"], r["stack"]) for r in rows if r["event"] == "table"] == [(5, 10_000), (6, 10_150)]
    return {"policy": policy, "reconnect_ms": recovered, "idle_s": silence,
            "mesa_5_response_ms": first_ms, "mesa_6_response_ms": second_ms}


def events(journal):
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("v2", "v4rb"), default="v2")
    parser.add_argument("--idle-seconds", type=int, default=180)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.policy, args.idle_seconds, args.journal)))


if __name__ == "__main__":
    main()

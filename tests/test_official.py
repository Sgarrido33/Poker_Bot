import unittest
from time import perf_counter
from unittest.mock import Mock

from pokerfight.domain import Action
from pokerfight.official import Hand, Session, wire_action


def player(pid, seat, stack, bet, *, in_hand=True):
    return {"id": pid, "posicion_silla": seat, "saldo": stack, "apuesta_ronda": bet,
            "activo": in_hand, "en_mano": in_hand}


def event(pid, street, kind, amount=None):
    action = {"tipo": kind}
    if amount is not None:
        action["monto"] = amount
    return {"id_jugador": pid, "etapa": street, "accion": action}


class OfficialProtocolTests(unittest.TestCase):
    def test_does_not_send_a_response_after_its_deadline(self):
        session = Session(bot=None, log=Mock())
        connection = Mock()
        session.respond(connection, {"estado": {"id_mano": "mesa-1-mano-1"},
                                     "acciones_validas": ["check"], "timeout_ms": 5000},
                        perf_counter() - 5)
        connection.sendall.assert_not_called()
        self.assertEqual(session.stats["skipped_responses"], 1)

    def test_detects_a_substituted_action_in_public_history(self):
        session = Session(bot=None, log=Mock())
        session.hero_id = "hero"
        session.pending = "mesa-1-mano-1", 1, {"tipo": "raise", "monto": 250}
        session.observe({"id_mano": "mesa-1-mano-1", "historial_acciones": [
            event("rival", "preflop", "call"), event("hero", "preflop", "fold"),
        ]})
        self.assertEqual(session.stats["substituted"], 1)
        self.assertIsNone(session.pending)

    def test_reconstructs_blinds_calls_and_short_all_in_across_streets(self):
        state = {"id_mano": "mesa-2-mano-7", "ciega_grande": 100, "posicion_boton": 5,
                 "jugadores": [player("btn", 5, 2000, 0), player("hero", 3, 1900, 100),
                               player("sb", 1, 250, 50), player("waiting", 0, 10000, 0, in_hand=False)]}
        hand = Hand({"estado": state, "cartas": [{"rango": 14, "palo": 3}, {"rango": 10, "palo": 2}]})
        turn = {"acciones_validas": ["fold", "call", "raise", "allin"], "estado": {
            **state, "apuesta_actual": 400, "subida_minima": 400, "pozo": 1300,
            "comunitarias": [{"rango": 2, "palo": 0}, {"rango": 3, "palo": 1}, {"rango": 4, "palo": 2}],
            "jugadores": [player("btn", 5, 1300, 400), player("hero", 3, 1700, 0), player("sb", 1, 0, 0)],
            "historial_acciones": [event("btn", "preflop", "raise", 250), event("sb", "preflop", "allin"),
                                  event("hero", "preflop", "call"), event("btn", "preflop", "call"),
                                  event("hero", "flop", "check"), event("btn", "flop", "bet", 400)]}}
        obs = hand.observation(turn, "hero")
        self.assertEqual((obs.table_id, obs.position, obs.hole_cards), ("mesa-2", "BB", ("As", "Th")))
        self.assertEqual([p.contribution for p in obs.players], [300, 300, 700])
        self.assertEqual([(e.kind, e.amount, e.facing_bet) for e in obs.history],
                         [("raise_to", 250, True), ("raise_to", 300, True), ("call", 200, True),
                          ("call", 50, True), ("check", 0, False), ("raise_to", 400, False)])
        self.assertEqual((obs.legal.call_amount, obs.legal.min_raise_to, obs.legal.max_raise_to), (400, 800, 1700))
        self.assertEqual(wire_action(Action("raise_to", 900), turn), {"tipo": "raise", "monto": 900})

    def test_short_all_in_and_raise_not_reopened(self):
        state = {"id_mano": "mesa-2-mano-1", "ciega_grande": 100, "posicion_boton": 0,
                 "jugadores": [player("hero", 0, 125, 50), player("bb", 2, 900, 100)],
                 "apuesta_actual": 100, "subida_minima": 100, "pozo": 150}
        hand = Hand({"estado": state, "cartas": [{"rango": 5, "palo": 1}, {"rango": 2, "palo": 2}]})
        turn = {"estado": state, "acciones_validas": ["fold", "call", "raise", "allin"]}
        obs = hand.observation(turn, "hero")
        self.assertEqual((obs.legal.min_raise_to, obs.legal.max_raise_to), (175, 175))
        self.assertEqual(wire_action(Action("raise_to", 175), turn), {"tipo": "allin"})
        turn["acciones_validas"] = ["fold", "call"]
        self.assertIsNone(hand.observation(turn, "hero").legal.min_raise_to)

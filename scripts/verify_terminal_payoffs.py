"""Independent PokerKit oracle for terminal action-model chip accounting."""
import json
from pathlib import Path
import random
import eval7

from pokerfight.action_model import PRIORS, PreparedAction
from pokerfight.arena import play_hand, seed_for
from pokerfight.cards import DECK
from pokerfight.domain import Action
from pokerfight.strategy import Decision


def verify():
    rows = []
    for n in (2, 3, 4, 5, 6):
        for index in range(8):
            seed = seed_for("terminal-oracle-v4", n, index)
            rng = random.Random(seed)
            hero_index = 1 if n == 2 else 2  # PokerKit's first preflop actor.
            ids = tuple("hero" if i == hero_index else f"p{i}" for i in range(n))
            stacks = {pid: 100 * rng.randint(2, 15) for pid in ids}
            folds = {pid: rng.random() < .4 for pid in ids if pid != "hero"}
            captured = []

            class Script:
                def __init__(self, pid):
                    self.pid = pid

                def decide(self, obs):
                    if self.pid == "hero" and not captured:
                        action = Action("raise_to", obs.legal.max_raise_to)
                        captured.append((obs, action))
                    elif obs.legal.call_amount:
                        action = Action("fold" if self.pid != "hero" and folds[self.pid] else "call")
                    else:
                        action = Action("check")
                    return Decision(action, "oracle_script", 0, False)

            result = play_hand({pid: Script(pid) for pid in ids}, ids, stacks, seed)
            obs, action = captured[0]
            deck = list(DECK)
            random.Random(seed).shuffle(deck)
            offset = 2 * n
            board = [eval7.Card(deck[i]) for i in (offset + 1, offset + 2, offset + 3, offset + 5, offset + 7)]
            ranks = [eval7.evaluate([eval7.Card(c) for c in deck[2*i:2*i+2]] + board) for i in range(n)]
            uniforms = [1.0 if folds.get(pid, False) else 0.0 for pid in ids]
            predicted = PreparedAction(obs, action, {}).value(ranks, [.5] * n, uniforms, PRIORS[0])
            engine_incremental = result.payoffs["hero"] + obs.hero.contribution
            # Monte Carlo splits ties fractionally; PokerKit awards integer odd
            # chips. At most one chip per eligible layer may differ here.
            difference = predicted - engine_incremental
            assert abs(difference) <= n, (n, index, predicted, engine_incremental)
            rows.append({"players": n, "case": index, "starting_stacks": stacks,
                         "model_value": predicted, "engine_incremental_value": engine_incremental,
                         "difference": difference, "chips_conserved": sum(result.payoffs.values()) == 0})
    return {"cases": rows, "passed": True, "max_absolute_difference": max(abs(r["difference"]) for r in rows),
            "scope": "Accounting only under predetermined fold/call/checkdown responses, not validation of response probabilities."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    a = parser.parse_args()
    result = verify()
    Path(a.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))

"""Public, replayable decision fixtures; run before changing candidate parameters."""
from dataclasses import asdict, replace
import json
from pathlib import Path

from pokerfight.arena import make_policy
from pokerfight.domain import LegalActions, Observation, Player, PublicAction
from pokerfight.strategy import BotConfig


def opening(players=6, depth=4, position="UTG", hole=("Ts", "9s"), rival_depth=None):
    button = 0
    amounts = [0] * players
    amounts[0 if players == 2 else 1] = 50
    amounts[1 if players == 2 else 2] = 100
    order = [0, 1] if players == 2 else list(range(3, players)) + [0, 1, 2]
    ids = tuple(str(i) for i in range(players))
    probe = tuple(Player(pid, 10000 - amounts[i], amounts[i], amounts[i]) for i, pid in enumerate(ids))
    index = next(i for i in range(players) if Observation("diagnosis", "opening", str(i), button,
        probe, hole, (), 100, LegalActions(amounts[i] == 100, amounts[i] != 100, 100 - amounts[i])).position == position)
    folded = set(order[:order.index(index)])
    states = tuple(Player(pid, round((depth if i == index or rival_depth is None else rival_depth) * 100) - amounts[i],
                          amounts[i], amounts[i], i in folded) for i, pid in enumerate(ids))
    history = tuple(PublicAction(str(j), str(i), "preflop", "fold", 0, True) for j, i in enumerate(order[:order.index(index)]))
    cost = min(states[index].stack, 100 - amounts[index])
    maximum = states[index].stack + amounts[index]
    return Observation("diagnosis", "opening", str(index), button, states, hole, (), 100,
                       LegalActions(cost == 0, cost > 0, cost, 200 if maximum >= 200 else None,
                                    maximum if maximum >= 200 else None), history)


def cases():
    defend = Observation("diagnosis", "defense", "BB", 0,
        (Player("BTN", 600, 200, 200), Player("SB", 750, 50, 50, True), Player("BB", 700, 100, 100)),
        ("Qs", "7h"), (), 100, LegalActions(False, True, 100, 300, 800),
        (PublicAction("0", "BTN", "preflop", "raise_to", 200, True),
         PublicAction("1", "SB", "preflop", "fold", 0, True)))
    cheap = json.loads(Path("examples/all_in_price.json").read_text(encoding="utf-8"))
    return {
        "utg_speculative_4bb": opening(),
        "heads_up_8bb": opening(2, 8, "BTN", ("Ks", "8h")),
        "utg_weak_ace_4bb": opening(hole=("As", "2h")),
        "button_weak_ace_4bb": opening(position="BTN", hole=("As", "2h")),
        "effective_4bb_hero_100bb": opening(depth=100, position="SB", hole=("As", "Ah"), rival_depth=4),
        "bb_cheap_defense_8bb": defend,
        "bb_expensive_defense_8bb": replace(defend, players=(Player("BTN", 100, 700, 700),
             defend.players[1], defend.players[2]), legal=LegalActions(False, True, 600)),
        "cheap_all_in_regression": Observation.from_dict(cheap),
    }


def run(path, variants=("v2",)):
    report = {}
    for name, obs in cases().items():
        report[name] = {"observation": asdict(obs), "decisions": {
            kind: make_policy(kind, BotConfig(samples=4000), 283901).decide(obs).to_dict() for kind in variants}}
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, result in report.items():
        print(name, {kind: (d["action"], d["reason"]) for kind, d in result["decisions"].items()})


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--variants", nargs="+", default=["v2"])
    a = p.parse_args()
    run(a.output, tuple(a.variants))

"""Paired ten-round qualifier using the local PokerKit engine."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from math import comb
from pathlib import Path
from time import perf_counter

from pokerfight.arena import close_policies, make_policy, play_hand, seed_for
from pokerfight.official import PROFILES
from pokerfight.strategy import BotConfig


FIELDS = {
    "diverso": ("fullhouse", "honest", "pressure", "tight", "calling",
                "fullhouse", "honest", "lag", "tight", "random"),
    "selectivo": ("fullhouse", "honest", "tag", "tight", "tight",
                  "fullhouse", "honest", "tag", "pressure", "tight"),
}


def draw(players, seed, round_no):
    order = sorted(players, key=lambda pid: seed_for(seed, "draw", round_no, pid))
    if len(order) < 2:
        return []
    # Prefer five and six; balance smaller tables if that partition is impossible.
    count = (len(order) + 5) // 6
    size, larger = divmod(len(order), count)
    tables = []
    for index in range(count):
        take = size + (index < larger)
        tables.append(tuple(order[:take]))
        del order[:take]
    return tables


def tournament(seed, field, hero, *, hero_config=None, opponents=None, rival_config=None):
    opponents = FIELDS[field] if opponents is None else opponents
    hero_config = PROFILES[hero][0] if hero_config is None else hero_config
    rival_config = BotConfig() if rival_config is None else rival_config
    kinds = {"hero": hero, **{f"r{i:02d}": kind for i, kind in enumerate(opponents, 1)}}
    stacks = dict.fromkeys(kinds, 10_000)
    policies = {}
    rounds, eliminated = [], {}
    diagnostics = Counter()
    max_ms = 0.0
    try:
        for pid, kind in kinds.items():
            config = hero_config if pid == "hero" else rival_config
            policies[pid] = make_policy(kind, config, seed_for(seed, "policy", pid))
        for round_no in range(1, 11):
            tables = draw([pid for pid in stacks if stacks[pid]], seed, round_no)
            summary = {"round": round_no, "tables": [], "eliminations": []}
            for table_index, seats in enumerate(tables):
                table_id = f"r{round_no}-t{table_index}"
                table_policies = {pid: policies[pid] for pid in seats}
                table = {"seats": seats, "start": {pid: stacks[pid] for pid in seats}}
                button = len(seats) - 1
                elapsed, hands = 0.0, 0
                for hand_no in range(1, 51):
                    if elapsed >= 360 or sum(stacks[pid] > 0 for pid in seats) < 2:
                        break
                    ring = seats[button + 1:] + seats[:button + 1]
                    active = tuple(pid for pid in ring if stacks[pid])
                    start = perf_counter()
                    result = play_hand(table_policies, active, stacks,
                                       seed_for(seed, "deck", round_no, table_index, hand_no),
                                       str(hand_no), table_id)
                    elapsed += perf_counter() - start
                    hands += 1
                    stacks.update(result.stacks)
                    for pid, decision in result.decisions:
                        if pid != "hero":
                            diagnostics["rival_fallbacks"] += int(decision.fallback)
                            continue
                        diagnostics["decisions"] += 1
                        diagnostics["fallbacks"] += int(decision.fallback)
                        diagnostics["over_4s"] += int(decision.elapsed_ms >= 4000)
                        diagnostics["partial_equity"] += int(bool(decision.equity and decision.equity.timed_out))
                        max_ms = max(max_ms, decision.elapsed_ms)
                        if decision.search is not None:
                            diagnostics["searches"] += 1
                            diagnostics["search_changes"] += int(decision.search["changed"])
                            diagnostics["search_clock_stops"] += int("deadline" in decision.search["stop"])
                    for pid in active:
                        if stacks[pid] == 0:
                            eliminated[pid] = round_no, hand_no
                            summary["eliminations"].append({"player": pid, "table": table_index,
                                                            "hand": hand_no})
                    button = seats.index(next(pid for pid in ring if stacks[pid]))
                table.update(hands=hands, elapsed_s=round(elapsed, 3),
                             end={pid: stacks[pid] for pid in seats})
                diagnostics["table_clock_hits"] += int(elapsed >= 360)
                summary["tables"].append(table)
            if sum(stacks.values()) != 10_000 * len(kinds):
                raise RuntimeError("Las fichas no se conservaron entre mesas")
            summary["stacks"] = stacks.copy()
            rounds.append(summary)
    finally:
        close_policies(policies)
    ranking = sorted(kinds, key=lambda pid: (
        -stacks[pid], *(-value for value in eliminated.get(pid, (0, 0))),
        seed_for(seed, "tie", pid),
    ))
    return {"policy": hero, "rounds": rounds, "ranking": ranking, "hero_rank": ranking.index("hero") + 1,
            "hero_eliminated": eliminated.get("hero"), "hero_chips": stacks["hero"],
            "diagnostics": {**diagnostics, "max_decision_ms": round(max_ms, 3)}}


def run_pair(job):
    seed, field = job
    arms = ("v2", "v4rb") if seed % 2 else ("v4rb", "v2")
    return {"seed": seed, "field": field, **{arm: tournament(seed, field, arm) for arm in arms}}


def paired_top6(control_ranks, candidate_ranks):
    scores = [(a <= 6, b <= 6) for a, b in zip(control_ranks, candidate_ranks, strict=True)]
    control = sum(a and not b for a, b in scores)
    candidate = sum(b and not a for a, b in scores)
    discordant = control + candidate
    return {"pairs": len(scores), "control_top6": sum(a for a, _ in scores),
            "candidate_top6": sum(b for _, b in scores), "control_only": control, "candidate_only": candidate,
            "p_one_sided": sum(comb(discordant, n) for n in range(candidate, discordant + 1))
                           / 2 ** discordant}


def contrast(pairs):
    result = paired_top6((pair["v2"]["hero_rank"] for pair in pairs),
                         (pair["v4rb"]["hero_rank"] for pair in pairs))
    return {"pairs": result["pairs"], "v2_top6": result["control_top6"], "v4rb_top6": result["candidate_top6"],
            "v2_only": result["control_only"], "v4rb_only": result["candidate_only"],
            "p_one_sided": result["p_one_sided"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 2 or args.workers < 1:
        parser.error("Se requieren al menos dos pares y un proceso")
    fields = tuple(FIELDS)
    jobs = [(args.seed + i, fields[i % len(fields)]) for i in range(args.pairs)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pairs = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for pair in pool.map(run_pair, jobs):
            pairs.append(pair)
            print(pair["seed"], pair["field"], *(pair[arm]["hero_rank"] for arm in ("v2", "v4rb")), flush=True)
    report = {"fields": FIELDS, "seed": args.seed, "pairs": pairs, "summary": contrast(pairs),
              "by_field": {field: contrast([pair for pair in pairs if pair["field"] == field])
                           for field in fields}}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

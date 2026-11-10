"""Paired elimination sessions v8 vs v2 (same decks, seeds, seats and rivals).

Local rules as in stage 3: 800 chips, blinds 50/100, no ante, up to 128 hands.
Each job is one (scenario, players, group); every rotation plays both arms.
Usage: python -m scripts.v8_sessions --root results/v8_sessions_2026-10-29 --groups 8 --workers 11
       python -m scripts.v8_sessions --root ... --summary
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import random
import statistics
import time

from pokerfight.arena import close_policies, make_policy, play_hand, seed_for
from pokerfight.evaluation import lineup
from pokerfight.strategy import BotConfig

EXPERIMENT_ID = "v8-pushfold-sessions-20261029-01"
SCENARIOS = {"external_diverse": ["fullhouse", "honest", "v2_4000", "pressure", "fullhouse"],
             "pressure": ["pressure", "lag", "tag"], "copies_v2": ["v2"]}
ARMS = ("v2", "v8")
STACK, SB, BB, LIMIT = 800, 50, 100, 128


def session(scenario: str, n: int, group: int, arms=ARMS, experiment_id=EXPERIMENT_ID) -> list[dict]:
    ids, kinds = lineup(n, tuple(SCENARIOS[scenario]))
    base = seed_for(experiment_id, scenario, n, group)
    rows = []
    for rotation in range(n):
        seeds = {pid: seed_for(base, "policy", rotation, pid) for pid in ids}
        for variant in arms:
            pp = {pid: make_policy(variant if pid == "hero" else kind, BotConfig(4000, 1600, seeds[pid]), seeds[pid])
                  for pid, kind in {"hero": variant, **kinds}.items()}
            stacks = dict.fromkeys(ids, STACK)
            button = ids[(rotation - 1) % n]
            reasons, eliminated_at, played = Counter(), None, 0
            try:
                for hand in range(LIMIT):
                    active = tuple(pid for pid in ids if stacks[pid] > 0)
                    if len(active) < 2:
                        break
                    if hand:
                        old = ids.index(button)
                        button = next(ids[(old + k) % n] for k in range(1, n + 1) if ids[(old + k) % n] in active)
                    btn = active.index(button)
                    seats = active[btn + 1:] + active[:btn + 1]
                    result = play_hand(pp, seats, stacks, seed_for(base, "deck", hand), str(hand),
                                       f"t-{seed_for(base, rotation):x}", SB, BB, 0)
                    stacks.update(result.stacks)
                    played += 1
                    reasons.update(d.reason.split(":")[0] + ":" + d.reason.split(":")[1]
                                   for pid, d in result.decisions if pid == "hero" and ":" in d.reason)
                    reasons.update(f"fallback" for pid, d in result.decisions if pid == "hero" and d.fallback)
                    if stacks["hero"] == 0 and eliminated_at is None:
                        eliminated_at = hand
            finally:
                close_policies(pp)
            if sum(stacks.values()) != STACK * n:
                raise RuntimeError("chips not conserved")
            alive = sum(s > 0 for s in stacks.values())
            rows.append({"scenario": scenario, "players": n, "group": group, "rotation": rotation,
                         "variant": variant, "final": stacks["hero"], "eliminated_at": eliminated_at,
                         "won": alive == 1 and stacks["hero"] > 0, "played": played, "reasons": dict(reasons)})
    return rows


def run(root: Path, groups: int, workers: int, scenarios: list[str], arms=ARMS, experiment_id=EXPERIMENT_ID) -> None:
    root.mkdir(parents=True, exist_ok=True)
    out = root / "sessions.jsonl"
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["scenario"], r["players"], r["group"]))
    jobs = [(s, n, g) for g in range(groups) for s in scenarios for n in (5, 6) if (s, n, g) not in done]
    with ProcessPoolExecutor(workers) as pool:
        futures = {pool.submit(session, *job, tuple(arms), experiment_id): job for job in jobs}
        for future in as_completed(futures):
            started = time.time()
            rows = future.result()
            with out.open("a", encoding="utf-8", newline="") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            print("done", futures[future], round(time.time() - started, 1), flush=True)


def bootstrap(values: list[float], reps: int = 10000, seed: int = 1) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(reps))
    return means[int(0.025 * reps)], means[int(0.975 * reps)]


def summary(root: Path, candidate: str = "v8", control: str = "v2") -> dict:
    rows = [json.loads(l) for l in (root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()]
    report = {}
    for scenario in sorted({r["scenario"] for r in rows}):
        sub = [r for r in rows if r["scenario"] == scenario]
        by = {}
        for r in sub:
            by.setdefault((r["players"], r["group"]), {}).setdefault(r["variant"], []).append(r)
        metrics = {
            "final_chips": lambda rs: statistics.fmean(r["final"] for r in rs),
            "elim_24": lambda rs: statistics.fmean(r["eliminated_at"] is not None and r["eliminated_at"] < 24 for r in rs),
            "elim_128": lambda rs: statistics.fmean(r["eliminated_at"] is not None for r in rs),
            "wins": lambda rs: statistics.fmean(r["won"] for r in rs),
        }
        entry = {"groups": len(by), "tables_per_arm": sum(len(v.get(control, [])) for v in by.values())}
        for name, fn in metrics.items():
            pairs = [(fn(v[candidate]), fn(v[control])) for v in by.values() if candidate in v and control in v]
            diffs = [a - b for a, b in pairs]
            entry[name] = {candidate: round(statistics.fmean(a for a, _ in pairs), 4),
                           control: round(statistics.fmean(b for _, b in pairs), 4),
                           "diff": round(statistics.fmean(diffs), 4),
                           "ci95": [round(x, 4) for x in bootstrap(diffs)] if len(diffs) > 1 else None}
        reasons = Counter()
        for r in sub:
            if r["variant"] == candidate:
                reasons.update(r["reasons"])
        entry[candidate + "_reasons"] = dict(reasons.most_common(12))
        report[scenario] = entry
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="results/v8_sessions_2026-10-29")
    parser.add_argument("--groups", type=int, default=8)
    parser.add_argument("--workers", type=int, default=11)
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--arms", nargs="+", default=list(ARMS))
    parser.add_argument("--experiment-id", default=EXPERIMENT_ID)
    parser.add_argument("--candidate", default="v8")
    parser.add_argument("--control", default="v2")
    args = parser.parse_args()
    root = Path(args.root)
    if args.summary:
        result = summary(root, args.candidate, args.control)
        with open(root / "summary.json", "w", encoding="utf-8", newline="") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
    else:
        run(root, args.groups, args.workers, args.scenarios, args.arms, args.experiment_id)


if __name__ == "__main__":
    main()

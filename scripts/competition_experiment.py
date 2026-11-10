"""Fixed cross-play screening with a frozen external model, NOT official arena.

register must precede run; immutable protocol and source snapshot are checked on
resume. Every reset block and session group contains all cyclic seat rotations.
Summary rejects incomplete/mismatched batches. All observed data are development.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import random
import statistics

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.campaign import save
from pokerfight.evaluation import environment, lineup
from pokerfight.external_opponents import verify_fullhouse
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig

BASE = Path(__file__).resolve().parents[1]
ARMS = ("v2", "v4", "v4rb", "v5")
SCENARIOS = {"selective": ["tag", "tag", "lag"],
             "pressure": ["pressure", "lag", "tag"], "copies_v2": ["v2"],
             "external_mix": ["fullhouse", "v2", "fullhouse", "pressure", "lag"],
             "external_only": ["fullhouse"]}


def sources() -> dict:
    paths = list((BASE / "pokerfight").rglob("*.py")) + list((BASE / "scripts").glob("*.py"))
    paths += list((BASE / "pokerfight/external").rglob("*.npz"))
    paths += list((BASE / "pokerfight/external").rglob("SOURCE.json"))
    paths += list((BASE / "pokerfight/external").rglob("LICENSE*"))
    paths += list((BASE / "tests").glob("*.py"))
    paths += list((BASE / "research/competition_audit_20261028").glob("*.py"))
    paths += [BASE / p for p in ("pokerfight/external/fullhouse/SOURCE.json", "requirements.txt",
                                "pokerfight/external/fullhouse/LICENSE", "pokerfight/frozen_v2/manifest.json",
                                "requirements-evaluation.txt", "pyproject.toml")]
    return {p.relative_to(BASE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def protocol(identifier: str) -> dict:
    if not identifier.strip():
        raise ValueError("Empty experiment id")
    return {"experiment_id": identifier, "registered_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {**environment(), "numpy": version("numpy")}, "sources": sources(),
            "external": verify_fullhouse(), "arms": list(ARMS), "scenarios": SCENARIOS,
            "players": [5, 6], "depths_bb": [8, 100], "blocks": 8,
            "configs": {"v2": asdict(BotConfig()), **{v: asdict(BotConfig(4096, 3500)) for v in ARMS[1:]}},
            "rival_config": asdict(BotConfig(512, 1600)),
            "rival_quotas": {"tag_lag_pressure": "256 equity worlds per postflop decision; no changes",
                             "v2": "512 equity worlds per decision; 1600ms cap",
                             "fullhouse": "fixed model, 51 features, 5 actions; no online training"},
            "session": {"scenarios": ["pressure", "copies_v2", "external_mix"],
                        "groups": 3, "hand_limit": 24, "starting_stack": 800,
                        "small_blind": 50, "big_blind": 100, "ante": 0, "blind_interval": 0},
            "primary": "Equal-weight bb/hand paired delta versus v2 in external_mix, across both formats/depths.",
            "inference": {"bootstrap_repetitions": 10000, "family_alpha": .05,
                          "comparisons": 3, "unit": "whole reset deck block or whole session seed group, stratified by cell",
                          "interval": "Bonferroni percentile intervals: 98.333% for each of 3 primary candidates; approximate small-sample screening"},
            "criteria": {"technical": "Complete matrix, no fallback, illegal action or chip error; no wall-clock truncation for exact replay.",
                         "followup": "Primary lower bound >0, nonnegative delta in each format, and external_mix session final chips/800 lower bound >=0.",
                         "default": "Always retain v2 in this screening; no tournament claim or automatic promotion.",
                         "stopping": "Run all registered jobs; no tuning, no favorable-result stopping; technical faults invalidate batch."},
            "old_data": "All previous results and all data observed here are development data.",
            "limitations": ["One independent external author/model family, not a representative tournament field.",
                            "Fullhouse trained 6-max; execution at 5 players and after eliminations is transfer, not retraining.",
                            "Local 50/100 no-ante assumptions, no official tournament rules inferred.",
                            "Sessions may be censored at 24 hands; leaders are not assigned wins or final ranks.",
                            "Session seeds shared by hand index; different eliminations change card recipients.",
                            "Cyclic rotations balance seats, not all opponent-order permutations; not AIVAT.",
                            "Hero compute envelopes differ; opponent envelopes and model remain constant.",
                            "Only 8 blocks per reset cell and 3 session groups per stratum; intervals are fragile."]}


def register(root: Path, identifier: str) -> None:
    if (root / "protocol.json").exists():
        raise ValueError("Protocol already exists; use a new output directory and id")
    verify_control()
    plan = protocol(identifier)
    root.mkdir(parents=True, exist_ok=True)
    for name in plan["sources"]:
        dst = root / "source" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((BASE / name).read_bytes())
    save(root / "protocol.json", plan)
    (root / "protocol.sha256").write_text(hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest(), encoding="ascii")


def load_plan(root: Path) -> tuple[dict, str]:
    raw = (root / "protocol.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (root / "protocol.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Registered protocol changed")
    return json.loads(raw), digest


def verify(plan: dict) -> None:
    verify_control()
    verify_fullhouse()
    if sources() != plan["sources"]:
        raise ValueError("Evaluated code changed since registration; register a new experiment")
    current = {**environment(), "numpy": version("numpy")}
    for key in ("python", "eval7", "pokerkit", "numpy"):
        if current[key] != plan["environment"][key]:
            raise ValueError(f"Runtime changed: {key}")


def jobs(plan: dict) -> list[tuple]:
    return ([("reset", s, n, d) for s in plan["scenarios"] for n in plan["players"] for d in plan["depths_bb"]]
            + [("session", s, n, g) for s in plan["session"]["scenarios"] for n in plan["players"]
               for g in range(plan["session"]["groups"])])


def job_name(job: tuple) -> str:
    mode, scenario, n, number = job
    return f"{mode}_{scenario}_{n}p_{number}"


def table_key(base, rotation, mode):
    # Expose an opaque public identity, never the seed used to derive decks.
    return f"cp-{seed_for('public-table-token', base, rotation, mode):016x}"


def policies(plan, variant, kinds, seeds):
    return {pid: make_policy(variant if pid == "hero" else kind,
                BotConfig(**(plan["configs"][variant] if pid == "hero" else plan["rival_config"])), seeds[pid])
            for pid, kind in {"hero": variant, **kinds}.items()}


def metrics(result) -> dict:
    counts = Counter()
    reasons = Counter()
    hero_actions = Counter()
    for pid, d in result.decisions:
        reasons[("hero:" if pid == "hero" else "rival:") + d.reason] += 1
        counts["decisions"] += 1
        counts["fallbacks"] += d.fallback
        if d.reason.startswith("external:honest:"):
            counts["external_honest_simulated_deals"] += 1000
        if pid == "hero":
            hero_actions[d.action.kind] += 1
        if d.equity:
            counts["equity_worlds_completed"] += d.equity.samples
            counts["equity_deadlines"] += d.equity.timed_out
        if d.search:
            counts["search_evaluation_worlds"] += d.search["worlds"]
            counts["search_training_worlds"] += d.search.get("training_worlds", 0)
            counts["search_deadlines"] += "deadline" in d.search["stop"]
    return {"counts": dict(counts), "reasons": dict(reasons), "hero_actions": dict(hero_actions)}


def record(result, **fields) -> dict:
    return {**fields, "payoffs": result.payoffs, "stacks": result.stacks, "board": result.board,
            "history": [asdict(e) for e in result.history], "trace": result.trace, **metrics(result)}


def write_record(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def execute_reset(root, plan, digest, job):
    _, scenario, n, depth = job
    ids, kinds = lineup(n, tuple(plan["scenarios"][scenario]))
    base = seed_for(plan["experiment_id"], "crossplay-reset-01", scenario, n, depth)
    means = {v: [] for v in plan["arms"]}
    counts, reasons, actions = {v: Counter() for v in means}, {v: Counter() for v in means}, {v: Counter() for v in means}
    gains = {v: [] for v in means}
    name = job_name(job)
    trace = root / (name + ".jsonl")
    with trace.open("w", encoding="utf-8") as stream:
        for block in range(plan["blocks"]):
            profit = {v: [] for v in means}
            for rotation in range(n):
                seats = ids[rotation:] + ids[:rotation]
                seeds = {pid: seed_for(base, "policy", block, rotation, pid) for pid in ids}
                deck = seed_for(base, "deck", block)
                arms = list(plan["arms"])
                shift = (block + rotation) % len(arms)
                for variant in arms[shift:] + arms[:shift]:
                    pp = policies(plan, variant, kinds, seeds)
                    result = play_hand(pp, seats, dict.fromkeys(ids, depth * 100), deck,
                                       str(block), table_key(base, rotation, "reset"), trace_player_id="hero")
                    row = record(result, mode="reset", block=block, rotation=rotation, variant=variant,
                                 seats=seats, deck_seed=deck, policy_seeds=seeds)
                    write_record(stream, row)
                    profit[variant].append(result.payoffs["hero"] / 100)
                    gains[variant].append(result.stacks["hero"] == 0)
                    counts[variant].update(row["counts"])
                    reasons[variant].update(row["reasons"])
                    actions[variant].update(row["hero_actions"])
            for v in means:
                means[v].append(statistics.mean(profit[v]))
    return {"job": list(job), "protocol_sha256": digest, "opponents": kinds,
            "block_bb_per_hand": means, "counts": counts, "reasons": reasons, "hero_actions": actions,
            "bust_hands": {v: sum(gains[v]) for v in means},
            "executions": plan["blocks"] * n * len(means),
            "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}


def execute_sessions(root, plan, digest, job):
    _, scenario, n, group = job
    cfg = plan["session"]
    ids, kinds = lineup(n, tuple(plan["scenarios"][scenario]))
    base = seed_for(plan["experiment_id"], "crossplay-session-01", scenario, n, group)
    rows = []
    trace = root / (job_name(job) + ".jsonl")
    with trace.open("w", encoding="utf-8") as stream:
        for rotation in range(n):
            seeds = {pid: seed_for(base, "policy", rotation, pid) for pid in ids}
            arms = list(plan["arms"])
            shift = (rotation + group) % len(arms)
            for variant in arms[shift:] + arms[:shift]:
                pp = policies(plan, variant, kinds, seeds)
                stacks = dict.fromkeys(ids, cfg["starting_stack"])
                button = ids[(rotation - 1) % n]
                counts, reasons, actions = Counter(), Counter(), Counter()
                hero_rank, eliminated_at = None, {}
                played, hero_hands = 0, 0
                for hand in range(cfg["hand_limit"]):
                    active = tuple(pid for pid in ids if stacks[pid] > 0)
                    if len(active) < 2:
                        break
                    if hand:
                        old = ids.index(button)
                        button = next(ids[(old + k) % n] for k in range(1, n + 1) if ids[(old + k) % n] in active)
                    btn = active.index(button)
                    seats = active[btn + 1:] + active[:btn + 1]
                    deck = seed_for(base, "deck", hand)
                    result = play_hand(pp, seats, stacks, deck, str(hand), table_key(base, rotation, "session"),
                                       cfg["small_blind"], cfg["big_blind"], cfg["ante"], trace_player_id="hero")
                    row = record(result, mode="session", group=group, rotation=rotation, hand=hand,
                                 variant=variant, seats=seats, deck_seed=deck, policy_seeds=seeds)
                    write_record(stream, row)
                    stacks.update(result.stacks)
                    played += 1
                    hero_hands += "hero" in active
                    eliminated = [pid for pid in active if stacks[pid] == 0]
                    for pid in eliminated:
                        eliminated_at[pid] = hand
                    if "hero" in eliminated:
                        # Share ranks for simultaneous busts; no arbitrary tie-break.
                        hero_rank = len(active) - len(eliminated) + (len(eliminated) + 1) / 2
                    counts.update(row["counts"])
                    reasons.update(row["reasons"])
                    actions.update(row["hero_actions"])
                finished = sum(s > 0 for s in stacks.values()) == 1
                if finished and stacks["hero"] > 0:
                    hero_rank = 1
                if sum(stacks.values()) != cfg["starting_stack"] * n:
                    raise RuntimeError("Session chips not conserved")
                rows.append({"variant": variant, "rotation": rotation, "last_stacks": stacks,
                             "played_hands": played, "hero_hands": hero_hands, "eliminated_at": eliminated_at,
                             "hero_eliminated": stacks["hero"] == 0, "table_finished": finished,
                             "hero_observed_win": finished and stacks["hero"] > 0,
                             "hero_rank": hero_rank, "censored_survivor": not finished and stacks["hero"] > 0,
                             "counts": counts, "reasons": reasons, "hero_actions": actions})
    return {"job": list(job), "protocol_sha256": digest, "opponents": kinds, "sessions": rows,
            "executions": sum(r["played_hands"] for r in rows),
            "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}


def run(root: Path, plan: dict, digest: str, shard=0, shards=1):
    if not 0 <= shard < shards:
        raise ValueError("Invalid shard")
    verify(plan)
    for index, job in enumerate(jobs(plan)):
        if index % shards != shard:
            continue
        output = root / (job_name(job) + ".json")
        if output.exists():
            row = json.loads(output.read_text(encoding="utf-8"))
            check_artifact(root, plan, digest, job, row)
            continue
        row = (execute_reset if job[0] == "reset" else execute_sessions)(root, plan, digest, job)
        verify(plan)
        save(output, row)
        print(f"done {job_name(job)} executions={row['executions']}", flush=True)


def check_artifact(root, plan, digest, job, row):
    if row["protocol_sha256"] != digest or row["job"] != list(job):
        raise ValueError("Mismatched experiment artifact")
    trace = root / (job_name(job) + ".jsonl")
    if row["trace_sha256"] != hashlib.sha256(trace.read_bytes()).hexdigest():
        raise ValueError("Trace changed")
    arms = plan["arms"]
    if job[0] == "reset":
        if set(row["block_bb_per_hand"]) != set(arms) or any(len(x) != plan["blocks"] for x in row["block_bb_per_hand"].values()):
            raise ValueError("Incomplete reset block")
    else:
        expected = {(v, r) for v in arms for r in range(job[2])}
        if {(r["variant"], r["rotation"]) for r in row["sessions"]} != expected or len(row["sessions"]) != len(expected):
            raise ValueError("Incomplete session rotations")


def interval(strata, seed, plan):
    if not strata or any(len(s) < 2 for s in strata):
        return None
    rng = random.Random(seed)
    reps = plan["inference"]["bootstrap_repetitions"]
    tail = plan["inference"]["family_alpha"] / plan["inference"]["comparisons"] / 2
    means = sorted(statistics.mean(statistics.mean(rng.choices(s, k=len(s))) for s in strata) for _ in range(reps))
    return [means[int(reps * tail)], means[min(reps - 1, int(reps * (1 - tail)))]]


def paired_reset(cells, candidate):
    return [[a - b for a, b in zip(c["block_bb_per_hand"][candidate], c["block_bb_per_hand"]["v2"], strict=True)] for c in cells]


def paired_sessions(session_jobs, candidate, metric):
    strata = {}
    for job in session_jobs:
        _, scenario, n, _ = job["job"]
        indexed = {(r["variant"], r["rotation"]): r for r in job["sessions"]}
        delta = [metric(indexed[(candidate, rot)]) - metric(indexed[("v2", rot)]) for rot in range(n)]
        strata.setdefault((scenario, n), []).append(statistics.mean(delta))
    return list(strata.values())


def describe(strata, name, plan):
    return {"mean": statistics.mean(map(statistics.mean, strata)) if strata else None,
            "interval_family_adjusted": interval(strata, seed_for(plan["experiment_id"], "bootstrap", name), plan),
            "strata": len(strata), "independent_groups": sum(map(len, strata))}


def summarize(root: Path, plan: dict, digest: str) -> dict:
    verify(plan)
    all_rows = []
    for job in jobs(plan):
        path = root / (job_name(job) + ".json")
        if not path.exists():
            raise ValueError(f"Incomplete campaign: {path.name}")
        row = json.loads(path.read_text(encoding="utf-8"))
        check_artifact(root, plan, digest, job, row)
        all_rows.append(row)
    cells = [r for r in all_rows if r["job"][0] == "reset"]
    sessions = [r for r in all_rows if r["job"][0] == "session"]
    counts = Counter()
    for job in all_rows:
        for c in (job["counts"].values() if job["job"][0] == "reset" else (r["counts"] for r in job["sessions"])):
            counts.update(c)
    safety = counts["fallbacks"] == 0
    replayable = counts["equity_deadlines"] == counts["search_deadlines"] == 0
    contrasts = {}
    for v in plan["arms"][1:]:
        primary = [c for c in cells if c["job"][1] == "external_mix"]
        ext_sessions = [s for s in sessions if s["job"][1] == "external_mix"]
        main = describe(paired_reset(primary, v), (v, "primary"), plan)
        sess = describe(paired_sessions(ext_sessions, v, lambda r: r["last_stacks"]["hero"] / 800), (v, "session"), plan)
        formats = {str(n): statistics.mean(map(statistics.mean, paired_reset([c for c in primary if c["job"][2] == n], v))) for n in plan["players"]}
        contrasts[v] = {"primary_external_mix_bb_per_hand": main, "primary_by_players": formats,
                        "external_mix_session_final_stack_fraction": sess,
                        "by_scenario": {s: describe(paired_reset([c for c in cells if c["job"][1] == s], v), (v, s), plan) for s in plan["scenarios"]},
                        "all_sessions_final_stack_fraction": describe(paired_sessions(sessions, v, lambda r: r["last_stacks"]["hero"] / 800), (v, "all_session"), plan),
                        "session_elimination_probability_delta": describe(paired_sessions(sessions, v, lambda r: float(r["hero_eliminated"])), (v, "elimination"), plan),
                        "passes_followup_screen": bool(safety and replayable and main["interval_family_adjusted"] and sess["interval_family_adjusted"] and main["interval_family_adjusted"][0] > 0 and all(d >= 0 for d in formats.values()) and sess["interval_family_adjusted"][0] >= 0)}
    raw_sessions = [r for s in sessions for r in s["sessions"]]
    session_descriptive = {}
    for v in plan["arms"]:
        rows = [r for r in raw_sessions if r["variant"] == v]
        session_descriptive[v] = {"tables": len(rows), "played_hands": sum(r["played_hands"] for r in rows),
                                  "mean_final_stack": statistics.mean(r["last_stacks"]["hero"] for r in rows),
                                  "eliminations": sum(r["hero_eliminated"] for r in rows),
                                  "observed_wins": sum(r["hero_observed_win"] for r in rows),
                                  "finished_tables": sum(r["table_finished"] for r in rows),
                                  "censored_survivors": sum(r["censored_survivor"] for r in rows)}
    output = {"complete": True, "protocol_sha256": digest, "reset_cells": len(cells),
              "reset_hand_executions": sum(r["executions"] for r in cells),
              "session_hand_executions": sum(r["executions"] for r in sessions),
              "reset_independent_blocks": len(cells) * plan["blocks"],
              "session_independent_seed_groups": len(sessions),
              "all_policy_counts": counts, "safety_passed": safety, "no_clock_truncation": replayable,
              "contrasts": contrasts, "session_descriptive": session_descriptive,
              "default": "v2", "promotion_allowed": False, "limitations": plan["limitations"]}
    save(root / "summary.json", output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "run", "summarize"))
    parser.add_argument("--root", type=Path, default=Path("results/competition_2026-10-28"))
    parser.add_argument("--id", default="crossplay-fullhouse-20261028-01")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if args.command == "register":
        register(args.root, args.id)
    else:
        plan, digest = load_plan(args.root)
        if args.command == "run":
            run(args.root, plan, digest, args.shard, args.shards)
        else:
            print(json.dumps(summarize(args.root, plan, digest), indent=2), flush=True)


if __name__ == "__main__":
    main()

"""Sealed six-version experiment for exact one-shove response integration.

Pilot and comparison quantities are fixed together. Workers import a preserved
source tree. All contrasts are exploratory and never promote the default.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

import numpy as np

from pokerfight.arena import seed_for
from pokerfight.campaign import save
from pokerfight.external_opponents import verify_honest
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig
from scripts import competition_experiment as old

ARMS = ("v2", "v2mc", "v4rb", "v5", "v6", "v7")
SCENARIOS = {"pressure": ["pressure", "lag", "tag"],
             "copies_v2": ["v2_4000"],
             "external_diverse": ["fullhouse", "honest", "v2_4000", "pressure", "fullhouse"]}


def protocol(identifier):
    plan = old.protocol(identifier)
    plan.update(arms=list(ARMS), scenarios=SCENARIOS, external_honest=verify_honest(),
                players=[5, 6], depths_bb=[4, 8, 12], blocks=8,
                phases={"pilot": {"blocks": 2, "session_groups": 0},
                        "comparison": {"blocks": 8, "session_groups": 4}},
                configs={"v2": asdict(BotConfig()),
                         **{kind: asdict(BotConfig(1024, 3500)) for kind in ARMS[1:]}},
                rival_config=asdict(BotConfig(256, 1600)),
                execution={"workers": 2, "imports": "registered source snapshot",
                           "technical_failures": "Retain all outcomes; clock cuts invalidate exact-replay and strength screening, never silently rerun favorable data."})
    plan["session"].update(scenarios=list(SCENARIOS), groups=4, hand_limit=128,
                           starting_stack=800, small_blind=50, big_blind=100, ante=0)
    plan["primary"] = "Exploratory v7-v5 algorithm contrast; v7-v4rb and v7-v2 as controls. Report all 15 version pairs and all unfavorable outcomes."
    plan["inference"] = {"bootstrap_repetitions": 5000, "confidence": .95,
                         "unit": "Whole deck block (all rotations) or session seed group (all rotations). Equal cell/scenario/format weights.",
                         "multiplicity": "Unadjusted exploratory intervals; no confirmatory declaration and no promotion."}
    plan["criteria"] = {"default": "Always retain v2; no promotion in this exploratory experiment.",
                        "technical": "Complete registered jobs; no fallbacks, illegal actions, chip errors or clock truncation; exact replays and audits agree.",
                        "stopping": "Run both fixed phases without changing policy parameters or quantities after pilot outcomes. Pilot only checks operation."}
    plan["rival_quotas"] = {"v2_4000": "Fixed 4000 samples, 1600ms; never inherits hero settings.",
                            "rules": "Existing public observation policies, unchanged internal quotas.",
                            "fullhouse": "Pinned model and adapter, no training.",
                            "honest": "1000 uniform simulated deals, isolated RNG; educational fold/call rival."}
    plan["limitations"] = [
        "Development screening with only eight blocks per reset cell and four session groups per scenario/format.",
        "Unadjusted intervals across many comparisons; no winner declaration from a positive sample mean.",
        "v2 uses 4000 worlds; other arms cap at 1024, with half training for v5/v7. Equal caps are not equal CPU.",
        "v5/v7 permit one opposing shove, no later bets, with manual priors. Integration does not correct model misspecification.",
        "Fullhouse transfers a six-seat model; Honest is educational. NoRegrets is not in this matrix.",
        "Fixed local 50/100, no ante/rebuy; no official tournament conditions inferred.",
        "Session seeds share hand indices, but eliminations change card recipients. Censored leaders get no invented wins."]
    return plan


def phase_plan(plan, phase):
    result = deepcopy(plan)
    result["experiment_id"] += ":" + phase
    result["phase"] = phase
    result["blocks"] = plan["phases"][phase]["blocks"]
    result["session"]["groups"] = plan["phases"][phase]["session_groups"]
    return result


def planned_decks(plan):
    result = set()
    for phase in plan["phases"]:
        settings = phase_plan(plan, phase)
        for mode, scenario, n, number in old.jobs(settings):
            base = seed_for(settings["experiment_id"], "crossplay-reset-01" if mode == "reset"
                            else "crossplay-session-01", scenario, n, number)
            count = settings["blocks"] if mode == "reset" else settings["session"]["hand_limit"]
            result.update(seed_for(base, "deck", index) for index in range(count))
    return result


def register(root, identifier):
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty experiment directory")
    plan = protocol(identifier)
    verify_control()
    root.mkdir(parents=True, exist_ok=True)
    for name, expected in plan["sources"].items():
        source = old.BASE / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        target = root / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    save(root / "protocol.json", plan)
    digest = hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
    (root / "protocol.sha256").write_text(digest, encoding="ascii")
    # Ripgrep scans existing traces without decoding every historical hand.
    scan = subprocess.run(["rg", "--no-config", "--no-filename", "--only-matching",
                           r'"deck_seed"\s*:\s*[0-9]+', str(old.BASE / "results"),
                           "-g", "*.jsonl"], capture_output=True, text=True, check=False)
    if scan.returncode not in (0, 1):
        raise RuntimeError(scan.stderr)
    historical = {int(match) for match in re.findall(r":\s*([0-9]+)", scan.stdout)}
    decks = planned_decks(plan)
    if decks & historical:
        raise ValueError("Planned seeds overlap historical traces")
    save(root / "seed_check.json", {"planned_unique_decks": len(decks),
        "historical_unique_decks_scanned_from_jsonl": len(historical), "overlap": 0})
    return plan


def load(root):
    raw = (root / "protocol.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (root / "protocol.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Registered protocol changed")
    plan = json.loads(raw)
    for name, expected in plan["sources"].items():
        if hashlib.sha256((root / "source" / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Registered snapshot changed: {name}")
    return plan, digest


def _init_snapshot(snapshot):
    sys.path.insert(0, snapshot)
    for name in list(sys.modules):
        if name == "pokerfight" or name.startswith("pokerfight.") or name == "scripts" or name.startswith("scripts."):
            del sys.modules[name]


def _execute(args):
    folder, plan, digest, job = args
    from scripts import competition_experiment as frozen
    from pokerfight.campaign import save as frozen_save
    started = time.perf_counter()
    row = (frozen.execute_reset if job[0] == "reset" else frozen.execute_sessions)(Path(folder), plan, digest, job)
    row["elapsed_seconds"] = time.perf_counter() - started
    frozen_save(Path(folder) / (frozen.job_name(job) + ".json"), row)
    return {"job": job, "executions": row["executions"], "elapsed_seconds": row["elapsed_seconds"]}


def run(root, phase):
    plan, digest = load(root)
    if phase == "comparison":
        summary = root / "pilot" / "summary.json"
        if not summary.exists() or not json.loads(summary.read_text(encoding="utf-8"))["complete"]:
            raise ValueError("Complete and summarize the fixed pilot first")
    settings = phase_plan(plan, phase)
    folder = root / phase
    folder.mkdir(exist_ok=True)
    pending = []
    for job in old.jobs(settings):
        output = folder / (old.job_name(job) + ".json")
        if output.exists():
            old.check_artifact(folder, settings, digest, job, json.loads(output.read_text(encoding="utf-8")))
            continue
        if output.with_suffix(".jsonl").exists():
            raise ValueError(f"Incomplete trace exists: {output.with_suffix('.jsonl')}")
        pending.append((str(folder), settings, digest, job))
    with ProcessPoolExecutor(max_workers=plan["execution"]["workers"], initializer=_init_snapshot,
                             initargs=(str((root / "source").resolve()),)) as pool:
        for future in as_completed([pool.submit(_execute, args) for args in pending]):
            row = future.result()
            with (folder / "progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
            print(f"done {old.job_name(row['job'])}: {row['executions']} hands, {row['elapsed_seconds']:.1f}s", flush=True)
    load(root)


def interval(strata, seed, reps=5000):
    if not strata or any(len(group) < 2 for group in strata):
        return None
    rng = np.random.default_rng(seed)
    samples = np.zeros(reps)
    for group in strata:
        array = np.asarray(group, dtype=float)
        samples += array[rng.integers(0, len(array), (reps, len(array)))].mean(axis=1) / len(strata)
    return np.quantile(samples, [.025, .975]).tolist()


def describe(strata, seed):
    return {"mean": statistics.mean(map(statistics.mean, strata)) if strata else None,
            "interval_95_exploratory": interval(strata, seed),
            "strata": len(strata), "independent_groups": sum(map(len, strata))}


def bust(row, horizon):
    hand = row["eliminated_at"].get("hero")
    return float(hand is not None and hand + 1 <= horizon)


def summarize(root, phase):
    plan, digest = load(root)
    settings, folder = phase_plan(plan, phase), root / phase
    cells, sessions, counts = [], [], {arm: Counter() for arm in plan["arms"]}
    for job in old.jobs(settings):
        path = folder / (old.job_name(job) + ".json")
        if not path.exists():
            raise ValueError(f"Incomplete phase: {path.name}")
        row = json.loads(path.read_text(encoding="utf-8"))
        old.check_artifact(folder, settings, digest, job, row)
        if job[0] == "reset":
            cells.append(row)
            for arm in counts:
                counts[arm].update(row["counts"][arm])
        else:
            sessions.append(row)
            for table in row["sessions"]:
                counts[table["variant"]].update(table["counts"])
    metrics = {"final_stack_fraction": lambda row: row["last_stacks"]["hero"] / 800,
               "bust_24": lambda row: bust(row, 24),
               "bust_128": lambda row: bust(row, 128)}
    contrasts = {}
    for i, candidate in enumerate(plan["arms"]):
        for control in plan["arms"][:i]:
            key = candidate + "-" + control
            reset = {}
            for scenario in ["all", *plan["scenarios"]]:
                selected = [row for row in cells if scenario == "all" or row["job"][1] == scenario]
                strata = [[a - b for a, b in zip(row["block_bb_per_hand"][candidate], row["block_bb_per_hand"][control], strict=True)]
                          for row in selected]
                reset[scenario] = describe(strata, seed_for(settings["experiment_id"], key, scenario, "reset"))
            session = {}
            for scenario in ["all", *plan["scenarios"]]:
                selected = [row for row in sessions if scenario == "all" or row["job"][1] == scenario]
                session[scenario] = {}
                for name, metric in metrics.items():
                    strata = defaultdict(list)
                    for row in selected:
                        index = {(table["variant"], table["rotation"]): table for table in row["sessions"]}
                        n = row["job"][2]
                        value = statistics.mean(metric(index[(candidate, rotation)]) - metric(index[(control, rotation)])
                                                for rotation in range(n))
                        strata[tuple(row["job"][1:3])].append(value)
                    session[scenario][name] = describe(list(strata.values()), seed_for(settings["experiment_id"], key, scenario, name))
            contrasts[key] = {"reset_bb_per_hand": reset, "sessions": session}
    descriptive = {}
    for arm in plan["arms"]:
        reset_means = [statistics.mean(row["block_bb_per_hand"][arm]) for row in cells]
        tables = [table for row in sessions for table in row["sessions"] if table["variant"] == arm]
        strata = defaultdict(list)
        for row in sessions:
            selected = [table for table in row["sessions"] if table["variant"] == arm]
            strata[tuple(row["job"][1:3])].append({
                "mean_final_stack": statistics.mean(table["last_stacks"]["hero"] for table in selected),
                "bust_24": statistics.mean(bust(table, 24) for table in selected),
                "bust_128": statistics.mean(bust(table, 128) for table in selected)})
        descriptive[arm] = {"reset_bb_per_hand": statistics.mean(reset_means), "session_tables": len(tables),
            **({metric: statistics.mean(statistics.mean(row[metric] for row in rows) for rows in strata.values())
                for metric in ("mean_final_stack", "bust_24", "bust_128")} if strata else {}),
            "observed_wins": sum(table["hero_observed_win"] for table in tables),
            "unfinished_tables": sum(not table["table_finished"] for table in tables),
            "censored_survivors": sum(table["censored_survivor"] for table in tables)}
    technical = all(counts[arm][name] == 0 for arm in counts
                    for name in ("fallbacks", "equity_deadlines", "search_deadlines"))
    result = {"complete": True, "phase": phase, "protocol_sha256": digest,
        "reset_hand_executions": sum(row["executions"] for row in cells),
        "session_hand_executions": sum(row["executions"] for row in sessions),
        "reset_independent_blocks": len(cells) * settings["blocks"],
        "session_independent_seed_groups": len(sessions), "counts_by_arm": counts,
        "technical_passed": technical, "descriptive": descriptive, "contrasts": contrasts,
        "default": "v2", "promotion_allowed": False, "limitations": plan["limitations"]}
    save(folder / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "run", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--id", default="integrated-one-shove-six-versions-20261029-01")
    parser.add_argument("--phase", choices=("pilot", "comparison"), default="pilot")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "register":
        plan = register(root, args.id)
        print(json.dumps({"registered": str(root), "arms": plan["arms"]}))
    elif args.command == "run":
        run(root, args.phase)
    else:
        result = summarize(root, args.phase)
        print(json.dumps({key: result[key] for key in ("phase", "reset_hand_executions", "session_hand_executions", "technical_passed", "descriptive")}, indent=2))


if __name__ == "__main__":
    main()

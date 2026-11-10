"""Frozen, resumable v8d component study and preregistered local validation.

register -> run development -> run validation -> summarize/audit.
No policy selection or sample-size change is allowed between phases.
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
from pokerfight.evaluation import environment
from pokerfight.external_opponents import verify_fullhouse, verify_honest
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig
from scripts import competition_experiment as executor

BASE = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "external_diverse": ["fullhouse", "honest", "v2_4000", "pressure", "fullhouse"],
    "copies_v2": ["v2_4000"],
    "selective": ["tag", "tight", "v2_4000", "tag", "tight"],
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def protocol(identifier):
    if not identifier.strip():
        raise ValueError("Empty experiment id")
    sources = executor.sources()
    for p in (BASE / "pokerfight/data").glob("*.json"):
        sources[p.relative_to(BASE).as_posix()] = sha(p)
    arms = ["v2", "v8", "v8d", "v8d_open", "v8d_reshove", "v8d_call", "v4rb"]
    configs = {a: asdict(BotConfig(4000, 1600)) for a in arms}
    configs["v4rb"] = asdict(BotConfig(1024, 3500))
    return {
        "experiment_id": identifier, "registered_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {**environment(), "numpy": np.__version__}, "sources": sources,
        "external": {"fullhouse": verify_fullhouse(), "honest": verify_honest()},
        "configs": configs, "rival_config": asdict(BotConfig(4000, 1600)),
        "scenarios": SCENARIOS, "players": [5, 6],
        "session": {"hand_limit": 128, "starting_stack": 800, "small_blind": 50,
                    "big_blind": 100, "ante": 0},
        "phases": {
            "development": {"arms": arms[:-1], "groups": {"copies_v2": 8, "selective": 8}},
            "validation": {"arms": ["v2", "v4rb", "v8d"],
                           "groups": {"external_diverse": 212, "copies_v2": 24, "selective": 24}},
        },
        "execution": {"workers": 6, "source": "frozen snapshot",
                      "failures": "abort on technical error; preserve partial trace; never silently replace outcomes"},
        "inference": {"unit": "scenario/player-count/seed group with all seat rotations and arms",
                      "weights": "equal 5p/6p weights within each scenario; never pool scenarios for primary",
                      "bootstrap_reps": 20000, "primary": "v8d-control final chips in external_diverse",
                      "controls": ["v2", "v4rb"], "primary_interval": "97.5% two-sided percentile, Bonferroni for two controls",
                      "guardrail_interval": "97.5% one-sided upper percentile; every guard must pass",
                      "secondary": ["wins", "elim_24", "elim_128", "alive_unfinished"],
                      "development": "95% descriptive intervals, no confirmatory claim"},
        "criteria": {"minimum_mean_chip_gain": 80, "primary_lower_bound": 0,
                     "max_early_elimination_increase": .05,
                     "early_guard_scenarios": list(SCENARIOS),
                     "per_format_chips": "nonnegative vs both controls in external_diverse",
                     "technical": "complete matrix, conserved chips, no fallback or equity/search deadline, replay agreement",
                     "local_advance": "all primary, mean, per-format, early-elimination and technical gates must pass",
                     "default": "retain v2; local advance only qualifies v8d for a future official-format evaluation",
                     "stopping": "fixed complete phases; no outcome-based stopping/tuning; a technical fault invalidates strength screening"},
        "planning": {"validation_groups_per_format_main": 212,
                     "basis": "historical v8-v2 SD ~1064 chips/group; ~80% normal-approximate power for +160 vs zero with two Bonferroni contrasts",
                     "limits": "not guaranteed power for v4rb, corrected v8d, the +80 mean gate, or 5pp noninferiority; inconclusive means no advance"},
        "replay": {"groups": [0], "rotations": [0], "hands": 8,
                   "rule": "first up to eight hands, all arms, group zero in every scenario/format/phase"},
        "limitations": ["local fixed blinds/no ante, unknown official scoring; not tournament validation",
                        "single-caller/equal-stack chart approximation and deterministic frequency threshold retained",
                        "component ablations alter whole trajectories; cannot attribute each lost pot to one decision",
                        "compute profiles differ; v4rb profile fixed to previous six-arm campaign, not equal CPU",
                        "all historical and development observations stay development data; candidate fixed before new outcomes",
                        "arena observes final public history for all PokerBot instances, including historical v8"],
    }


def settings(plan, phase):
    p = deepcopy(plan)
    p["experiment_id"] += ":" + phase
    p["arms"] = p["phases"][phase]["arms"]
    return p


def jobs(plan, phase):
    return [("session", s, n, g) for s, count in plan["phases"][phase]["groups"].items()
            for n in plan["players"] for g in range(count)]


def planned_decks(plan):
    result = set()
    for phase in plan["phases"]:
        p = settings(plan, phase)
        for _, s, n, g in jobs(plan, phase):
            base = seed_for(p["experiment_id"], "crossplay-session-01", s, n, g)
            for h in range(p["session"]["hand_limit"]):
                result.add(seed_for(base, "deck", h))
    return result


def register(root, identifier):
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty directory")
    verify_control()
    p = protocol(identifier)
    # Both phases and policies are sealed together before any new outcomes.
    scan = subprocess.run(["rg", "--no-config", "--no-filename", "--only-matching",
                           r'"deck_seed"\s*:\s*[0-9]+', str(BASE / "results"), "-g", "*.jsonl"],
                          capture_output=True, text=True, check=False)
    if scan.returncode not in (0, 1):
        raise RuntimeError(scan.stderr)
    historical = {int(x) for x in re.findall(r":\s*([0-9]+)", scan.stdout)}
    # The compact historical v8 logs omitted deck seeds: reconstruct those too.
    for folder, identifier_old in (("v8_sessions_2026-10-29", "v8-pushfold-sessions-20261029-01"),
                                   ("v8_replication_2026-10-29", "v8-replication-20261029-02"),
                                   ("v8c_2026-10-29", "v8c-20261029-03")):
        path = BASE / "results" / folder / "sessions.jsonl"
        if path.exists():
            keys = {(r["scenario"], r["players"], r["group"])
                    for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
            for s, n, g in keys:
                base = seed_for(identifier_old, s, n, g)
                historical.update(seed_for(base, "deck", h) for h in range(128))
    decks = planned_decks(p)
    expected = sum(len(jobs(p, phase)) for phase in p["phases"]) * p["session"]["hand_limit"]
    if len(decks) != expected or decks & historical:
        raise ValueError("Repeated planned decks or overlap with historical data")
    root.mkdir(parents=True, exist_ok=True)
    for name, expected_hash in p["sources"].items():
        src, dst = BASE / name, root / "source" / name
        if sha(src) != expected_hash:
            raise ValueError(f"Source changed during registration: {name}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    save(root / "protocol.json", p)
    (root / "protocol.sha256").write_text(sha(root / "protocol.json"), encoding="ascii")
    save(root / "seed_check.json", {"planned_unique_decks": len(decks),
                                   "historical_unique_decks": len(historical), "overlap": 0})
    print(json.dumps({"registered": str(root), "jobs": {phase: len(jobs(p, phase)) for phase in p["phases"]},
                      "protocol_sha256": sha(root / "protocol.json")}), flush=True)


def load(root):
    if sha(root / "protocol.json") != (root / "protocol.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Registered protocol changed")
    p = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    for name, expected in p["sources"].items():
        if sha(root / "source" / name) != expected:
            raise ValueError(f"Registered snapshot changed: {name}")
    current = {**environment(), "numpy": np.__version__}
    for key in ("python", "eval7", "pokerkit", "numpy"):
        if current[key] != p["environment"][key]:
            raise ValueError(f"Runtime changed: {key}")
    return p, sha(root / "protocol.json")


def init_snapshot(snapshot):
    sys.path.insert(0, snapshot)
    for name in list(sys.modules):
        if name == "pokerfight" or name.startswith("pokerfight.") or name == "scripts" or name.startswith("scripts."):
            del sys.modules[name]


def worker(args):
    from scripts import competition_experiment as frozen
    from pokerfight.campaign import save as frozen_save
    folder, p, digest, job = args
    started = time.perf_counter()
    result = frozen.execute_sessions(Path(folder), p, digest, job)
    frozen.check_artifact(Path(folder), p, digest, job, result)
    result["elapsed_seconds"] = time.perf_counter() - started
    frozen_save(Path(folder) / (frozen.job_name(job) + ".json"), result)
    return {"job": job, "executions": result["executions"], "seconds": result["elapsed_seconds"]}


def run(root, phase):
    p, digest = load(root)
    if phase == "validation":
        path = root / "development" / "summary.json"
        if not path.exists() or not json.loads(path.read_text(encoding="utf-8"))["technical_passed"]:
            raise ValueError("Complete the development phase without technical faults first")
    folder = root / phase
    folder.mkdir(exist_ok=True)
    pending = []
    for job in jobs(p, phase):
        out = folder / (executor.job_name(job) + ".json")
        if out.exists():
            executor.check_artifact(folder, settings(p, phase), digest, job, json.loads(out.read_text(encoding="utf-8")))
        elif out.with_suffix(".jsonl").exists():
            raise ValueError(f"Incomplete trace retained: {out.name}")
        else:
            pending.append((str(folder), settings(p, phase), digest, job))
    with ProcessPoolExecutor(max_workers=p["execution"]["workers"], initializer=init_snapshot,
                             initargs=(str((root / "source").resolve()),)) as pool:
        for future in as_completed([pool.submit(worker, arg) for arg in pending]):
            row = future.result()
            with (folder / "progress.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
    load(root)
    summarize(root, phase)


def table_metrics(table):
    eliminated = table["eliminated_at"].get("hero")
    return np.array([table["last_stacks"]["hero"], table["hero_observed_win"],
                     eliminated is not None and eliminated < 24, eliminated is not None,
                     table["censored_survivor"]], dtype=float)


METRICS = ("final_chips", "wins", "elim_24", "elim_128", "alive_unfinished")


def paired_report(rows, candidate, control, seed, reps):
    strata = defaultdict(list)
    for row in rows:
        index = {(t["variant"], t["rotation"]): t for t in row["sessions"]}
        n = row["job"][2]
        strata[n].append(np.mean([table_metrics(index[(candidate, r)]) - table_metrics(index[(control, r)])
                                 for r in range(n)], axis=0))
    rng = np.random.default_rng(seed)
    boot = np.zeros((reps, len(METRICS)))
    for array in map(np.array, strata.values()):
        boot += array[rng.integers(0, len(array), (reps, len(array)))].mean(axis=1) / len(strata)
    mean = np.mean([np.mean(a, axis=0) for a in strata.values()], axis=0)
    report = {}
    for i, name in enumerate(METRICS):
        report[name] = {"diff": float(mean[i]), "ci95_descriptive": np.quantile(boot[:, i], [.025, .975]).tolist(),
                        "ci97_5_primary": np.quantile(boot[:, i], [.0125, .9875]).tolist(),
                        "upper97_5_one_sided": float(np.quantile(boot[:, i], .975)),
                        "by_players": {str(n): float(np.mean(a, axis=0)[i]) for n, a in strata.items()}}
    return report


def summarize(root, phase):
    p, digest = load(root)
    cfg = settings(p, phase)
    folder = root / phase
    rows, counts = [], Counter()
    for job in jobs(p, phase):
        path = folder / (executor.job_name(job) + ".json")
        if not path.exists():
            raise ValueError(f"Incomplete phase: {path.name}")
        row = json.loads(path.read_text(encoding="utf-8"))
        executor.check_artifact(folder, cfg, digest, job, row)
        rows.append(row)
        for t in row["sessions"]:
            counts.update(t["counts"])
            if sum(t["last_stacks"].values()) != p["session"]["starting_stack"] * job[2]:
                raise ValueError("Chips not conserved")
    contrasts, descriptive = {}, {}
    for scenario in p["phases"][phase]["groups"]:
        sub = [r for r in rows if r["job"][1] == scenario]
        contrasts[scenario] = {}
        for i, candidate in enumerate(cfg["arms"]):
            for control in cfg["arms"][:i]:
                key = candidate + "-" + control
                contrasts[scenario][key] = paired_report(sub, candidate, control,
                    seed_for(cfg["experiment_id"], scenario, key, "bootstrap"), p["inference"]["bootstrap_reps"])
        descriptive[scenario] = {}
        for arm in cfg["arms"]:
            means = [np.mean([table_metrics(t) for t in r["sessions"] if t["variant"] == arm], axis=0) for r in sub]
            descriptive[scenario][arm] = dict(zip(METRICS, map(float, np.mean(means, axis=0))))
    technical = all(counts[k] == 0 for k in ("fallbacks", "equity_deadlines", "search_deadlines"))
    gates = {}
    if phase == "validation":
        for control in p["inference"]["controls"]:
            entry = contrasts["external_diverse"]["v8d-" + control]["final_chips"]
            gates["chips_vs_" + control] = entry["ci97_5_primary"][0] > 0 and entry["diff"] >= p["criteria"]["minimum_mean_chip_gain"]
            gates["formats_vs_" + control] = min(entry["by_players"].values()) >= 0
            for scenario in p["criteria"]["early_guard_scenarios"]:
                gates["early_" + scenario + "_vs_" + control] = (
                    contrasts[scenario]["v8d-" + control]["elim_24"]["upper97_5_one_sided"] <= p["criteria"]["max_early_elimination_increase"])
    result = {"complete": True, "phase": phase, "protocol_sha256": digest, "jobs": len(rows),
              "table_executions": sum(len(r["sessions"]) for r in rows),
              "hand_executions": sum(r["executions"] for r in rows), "counts": dict(counts),
              "technical_passed": technical, "descriptive": descriptive, "contrasts": contrasts,
              "gates": gates, "local_statistical_gates_passed": bool(gates) and all(gates.values()),
              "local_advance": "pending replay audit" if gates and all(gates.values()) and technical else False,
              "default": "v2"}
    save(folder / "summary.json", result)
    print(json.dumps({k: result[k] for k in ("phase", "jobs", "table_executions", "hand_executions", "technical_passed", "gates")}), flush=True)
    return result


def replay_worker(args):
    from pokerfight.arena import play_hand, close_policies
    from scripts import competition_experiment as frozen
    folder, p, job = args
    pp, checked = {}, 0
    path = Path(folder) / (frozen.job_name(job) + ".jsonl")
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row["rotation"] != 0 or row["hand"] >= 8:
                    continue
                arm = row["variant"]
                if arm not in pp:
                    _, kinds = frozen.lineup(job[2], tuple(p["scenarios"][job[1]]))
                    pp[arm] = frozen.policies(p, arm, kinds, row["policy_seeds"])
                stacks = {pid: row["stacks"][pid] - row["payoffs"][pid] for pid in row["seats"]}
                result = play_hand(pp[arm], tuple(row["seats"]), stacks, row["deck_seed"],
                    str(row["hand"]), frozen.table_key(seed_for(p["experiment_id"], "crossplay-session-01", job[1], job[2], job[3]), 0, "session"),
                    p["session"]["small_blind"], p["session"]["big_blind"], p["session"]["ante"], trace_player_id="hero")
                if result.stacks != row["stacks"] or result.payoffs != row["payoffs"]:
                    raise ValueError("Replay outcome differs")
                if [asdict(e) for e in result.history] != row["history"]:
                    raise ValueError("Replay public history differs")
                expected = row["trace"]
                actual = json.loads(json.dumps(result.trace))
                for trace in (expected, actual):
                    for item in trace:
                        item["decision"].pop("elapsed_ms", None)
                if actual != expected:
                    raise ValueError("Replay observation or decision differs")
                checked += 1
    finally:
        for policies in pp.values():
            close_policies(policies)
    return {"job": job, "hands": checked}


def audit(root, phase):
    p, digest = load(root)
    summary = json.loads((root / phase / "summary.json").read_text(encoding="utf-8"))
    selected = [job for job in jobs(p, phase) if job[3] == 0]
    with ProcessPoolExecutor(max_workers=2, initializer=init_snapshot,
                             initargs=(str((root / "source").resolve()),)) as pool:
        replays = list(pool.map(replay_worker, [(str(root / phase), settings(p, phase), job) for job in selected]))
    result = {"passed": True, "protocol_sha256": digest, "replayed_hands": sum(r["hands"] for r in replays), "replays": replays}
    save(root / phase / "audit.json", result)
    if phase == "validation":
        summary["local_advance"] = summary["technical_passed"] and summary["local_statistical_gates_passed"]
        save(root / phase / "summary.json", summary)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("register", "run", "summarize", "audit"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--experiment-id", default="v8d-guarded-validation-20261030-01")
    parser.add_argument("--phase", choices=("development", "validation"), default="development")
    args = parser.parse_args()
    if args.command == "register":
        register(args.root.resolve(), args.experiment_id)
    else:
        {"run": run, "summarize": summarize, "audit": audit}[args.command](args.root.resolve(), args.phase)


if __name__ == "__main__":
    main()

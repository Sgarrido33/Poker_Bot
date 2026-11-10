"""Registered runner for the v6 technical pilot and stage-3 screening.

The pilot is development-only. It records a source snapshot and immutable
protocol before executing complete paired groups of cyclic seat rotations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import platform
from pathlib import Path
import statistics
import sys
import time

from pokerfight.arena import seed_for
from pokerfight.campaign import save
from pokerfight.domain import Action, Observation
from scripts import competition_experiment as old

BASE = Path(__file__).resolve().parents[1]
PILOT_ID = "crossplay-v6pilot-20261028-01"
EXPERIMENT_ID = "crossplay-stage3-20261028-03"
PILOT_ARMS = ["v2", "v4rb", "v6"]
SCENARIOS = {"external_diverse": ["fullhouse", "honest", "v2_4000", "pressure", "fullhouse"],
             "pressure": ["pressure", "lag", "tag"], "copies_v2": ["v2"],
             "copies_v2_4000": ["v2_4000"],
             "external_mix": ["fullhouse", "v2", "fullhouse", "pressure", "lag"]}


def source_paths() -> list[str]:
    # Include all executor/runtime files that can affect a decision, plus the
    # Fullhouse model and license. Unused NoRegrets modules are intentionally
    # excluded so adding a separate opponent cannot invalidate this campaign.
    paths = ["scripts/__init__.py", "scripts/competition_experiment.py", "scripts/competition_stage2.py",
             "scripts/competition_stage3.py", "requirements.txt", "requirements-evaluation.txt", "pyproject.toml"]
    # Freeze the complete Python runtime except separately-added NoRegrets
    # experiments, which this pilot never imports or invokes.
    for p in (BASE / "pokerfight").rglob("*.py"):
        rel = p.relative_to(BASE).as_posix()
        stem = p.stem.casefold().replace("_", "")
        if stem.startswith("noregrets") or stem in {"noregret", "noregrettraining", "trainingnoregret"}:
            continue
        if "__pycache__" not in p.parts:
            paths.append(rel)
    for p in (BASE / "pokerfight/frozen_v2").rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            paths.append(p.relative_to(BASE).as_posix())
    for package in ("fullhouse", "honest"):
        ext = BASE / "pokerfight/external" / package
        for p in ext.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and (p.suffix in (".py", ".npz") or p.name in ("SOURCE.json", "LICENSE", "LICENSE.md")):
                paths.append(p.relative_to(BASE).as_posix())
    return sorted(set(paths))


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest() for name in source_paths()}


def protocol(identifier: str, phase: str = "pilot", groups: int = 2) -> dict:
    if not identifier.strip() or groups < 1:
        raise ValueError("Experiment id and positive group count are required")
    return {
        "experiment_id": identifier, "registered_utc": datetime.now(timezone.utc).isoformat(),
        "stage": 3, "phase": phase, "development_only": True,
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "eval7": version("eval7"), "pokerkit": version("pokerkit"), "numpy": version("numpy")},
        "sources": source_hashes(), "arms": PILOT_ARMS if phase == "pilot" else ["v2", "v4", "v4rb", "v5", "v6"],
        "scenarios": SCENARIOS if phase == "comparison" else {"external_diverse": SCENARIOS["external_diverse"]},
        "players": [5, 6], "groups_per_format": groups,
        "control_groups_per_format": 8 if phase == "comparison" else 0,
        "configs": {"v2": {"samples": 4000, "budget_ms": 1600},
                    "v4": {"samples": 4096, "budget_ms": 3500},
                    "v4rb": {"samples": 4096, "budget_ms": 3500},
                    "v5": {"samples": 4096, "budget_ms": 3500},
                    "v6": {"samples": 4096, "budget_ms": 3500}},
        "rival_config": {"samples": 512, "budget_ms": 1600},
        "rival_quotas": {"fullhouse": "frozen external model", "honest": "1000 uniform deals, fold/call only",
                         "v2_4000": "4000 equity worlds, 1600ms", "pressure": "fixed local pressure policy"},
        "session": {"scenarios": ["external_diverse"], "groups": groups, "hand_limit": 128,
                    "starting_stack": 800, "small_blind": 50, "big_blind": 100, "ante": 0, "blind_interval": 0},
        "execution": {"workers": 2 if phase == "pilot" else 6, "max_groups": groups,
                      "telemetry": "per-group wall time and complete decision counts",
                      "snapshot_isolated_workers": True},
        "inference": {"bootstrap_repetitions": 20000, "family_alpha": 0.05,
                      "confirmatory_comparisons": 2, "endpoints": ["final_stack_fraction", "bust_at_128"],
                      "control_interpretation": "exploratory only"},
        "seeds": {"derivation": "seed_for(id, 'crossplay-session-01', scenario, players, group); deck=seed_for(group_seed, 'deck', hand)",
                  "group_indices": list(range(groups)), "rotations": "all cyclic seat rotations", "hands_shared_by_index": True},
        "interpretation": ("Candidate-blind technical/development pilot only; no inferential claims and no result-based tuning."
                           if phase == "pilot" else "Fixed development screen: v6 versus v2 has two co-primary outcomes; all other arms and controls are descriptive. No tuning or stopping by outcome."),
    }


def seed_check(root: Path, plan: dict) -> dict:
    planned = set()
    for scenario in plan["scenarios"]:
      for n in plan["players"]:
        count = plan["groups_per_format"] if scenario == "external_diverse" else plan["control_groups_per_format"]
        for g in range(count):
            base = seed_for(plan["experiment_id"], "crossplay-session-01", scenario, n, g)
            planned.update(seed_for(base, "deck", h) for h in range(plan["session"]["hand_limit"]))
    historical = set()
    for p in (BASE / "results").rglob("*.jsonl"):
        if root.resolve() in p.resolve().parents:
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if "deck_seed" in row:
                        historical.add(row["deck_seed"])
                except (json.JSONDecodeError, TypeError):
                    continue
    reserved = set()
    reserved_path = BASE / "results/competition_stage3_plan_2026-10-28/plan.json"
    if reserved_path.is_file():
        frozen = json.loads(reserved_path.read_text(encoding="utf-8"))["fixed_seed_policy"]["group_seeds_by_scenario_and_format"]
        for scenario, formats in frozen.items():
            for group_seeds in formats.values():
                for base in group_seeds:
                    reserved.update(seed_for(base, "deck", h) for h in range(plan["session"]["hand_limit"]))
    historical_overlap = len(planned & historical)
    reserved_overlap = len(planned & reserved)
    if historical_overlap:
        raise ValueError("Planned session decks overlap historical data")
    reserved_reuse_authorized = False
    if reserved_overlap:
        frozen = json.loads(reserved_path.read_text(encoding="utf-8"))
        if not (plan["phase"] == "comparison"
                and plan["experiment_id"] == frozen["fixed_seed_policy"]["experiment_id"]
                and planned == reserved):
            raise ValueError("Planned session decks overlap the reserved stage-3 allocation")
        reserved_reuse_authorized = True
    return {"planned_unique_decks": len(planned), "historical_unique_decks": len(historical),
            "reserved_stage3_decks": len(reserved), "historical_overlap": historical_overlap,
            "reserved_overlap": reserved_overlap, "reserved_reuse_authorized": reserved_reuse_authorized,
            "overlap": historical_overlap,
            "planned_seed_sha256": hashlib.sha256(json.dumps(sorted(planned)).encode()).hexdigest(),
            "reserved_plan_sha256": hashlib.sha256(reserved_path.read_bytes()).hexdigest() if reserved_path.is_file() else None}


def register(root: Path, identifier: str = PILOT_ID, phase: str = "pilot", groups: int = 2) -> dict:
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty output directory")
    plan = protocol(identifier, phase, groups)
    root.mkdir(parents=True, exist_ok=True)
    for name, digest in plan["sources"].items():
        dst = root / "source" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = (BASE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Source changed while registering: {name}")
        dst.write_bytes(raw)
    save(root / "protocol.json", plan)
    digest = hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
    (root / "protocol.sha256").write_text(digest, encoding="ascii")
    seeds = seed_check(root, plan)
    save(root / "seed_check.json", seeds)
    return plan


def load(root: Path) -> tuple[dict, str]:
    raw = (root / "protocol.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (root / "protocol.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Registered protocol changed")
    plan = json.loads(raw)
    for name, expected in plan["sources"].items():
        if hashlib.sha256((root / "source" / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source snapshot mismatch: {name}")
    current_env = {"python": sys.version, "platform": platform.platform(),
                   "eval7": version("eval7"), "pokerkit": version("pokerkit"), "numpy": version("numpy")}
    if current_env != plan["environment"]:
        raise ValueError("Runtime environment changed since registration")
    return plan, digest


def jobs(plan: dict) -> list[tuple]:
    result = []
    for scenario in plan["scenarios"]:
        count = plan["groups_per_format"] if scenario == "external_diverse" else plan["control_groups_per_format"]
        for n in plan["players"]:
            result.extend(("session", scenario, n, g) for g in range(count))
    return result


def _init_snapshot(snapshot_root: str) -> None:
    # Windows workers import the entry module before the initializer. Clear
    # live package modules and load the frozen project copy for execution.
    sys.path.insert(0, snapshot_root)
    for name in list(sys.modules):
        if (name == "pokerfight" or name.startswith("pokerfight.")
                or name == "scripts" or name.startswith("scripts.")):
            del sys.modules[name]


def _execute(args):
    root_s, plan, digest, job = args
    root = Path(root_s)
    from scripts import competition_experiment as frozen_old
    from pokerfight.campaign import save as frozen_save
    start = time.perf_counter()
    row = frozen_old.execute_sessions(root, plan, digest, job)
    row["elapsed_seconds"] = time.perf_counter() - start
    frozen_save(root / (frozen_old.job_name(job) + ".json"), row)
    return {"job": job, "executions": row["executions"], "elapsed_seconds": row["elapsed_seconds"]}


def run(root: Path, workers: int = 2) -> list[dict]:
    plan, digest = load(root)
    if workers != plan["execution"]["workers"]:
        raise ValueError("Worker count must match registered protocol")
    pending = []
    live_sources = source_hashes()
    drift = {name: {"registered": expected, "workspace": live_sources.get(name)}
             for name, expected in plan["sources"].items() if live_sources.get(name) != expected}
    save(root / "execution_start.json", {"started_utc": datetime.now(timezone.utc).isoformat(),
        "registered_protocol_sha256": digest, "workers": workers,
        "source_snapshot": str((root / "source").resolve()),
        "workspace_source_drift_names": sorted(drift),
        "workspace_source_drift": drift,
        "execution_uses": "registered source snapshot, not mutable workspace"})
    for job in jobs(plan):
        out = root / (old.job_name(job) + ".json")
        if out.exists():
            existing = json.loads(out.read_text(encoding="utf-8"))
            old.check_artifact(root, plan, digest, job, existing)
            continue
        trace = root / (old.job_name(job) + ".jsonl")
        if trace.exists():
            raise ValueError(f"Partial trace exists without a completed job artifact: {trace.name}")
        pending.append((str(root), plan, digest, job))
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_snapshot,
                             initargs=(str((root / "source").resolve()),)) as pool:
        for r in pool.map(_execute, pending):
            results.append(r)
            with (root / "telemetry.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
                f.flush()
    # Verify no source drift after a long batch.
    load(root)
    return results


def _events(row: dict, h: int) -> dict:
    bust = row.get("eliminated_at", {}).get("hero")
    bust = bust is not None and bust + 1 <= h
    win = bool(row["hero_observed_win"] and row["played_hands"] <= h)
    finished = bool(row["table_finished"] and row["played_hands"] <= h)
    unresolved = not (bust or win)
    # Censor only at the administrative horizon; later observed busts are not
    # censored at earlier descriptive horizons.
    censored = unresolved and not finished and h == 128 and row["played_hands"] >= h
    return {"bust": int(bust), "win": int(win), "unresolved": int(unresolved),
            "table_finished": int(finished), "censored_survivor": int(censored)}


def _bootstrap(strata: list[list[float]], seed: int, reps: int, alpha: float) -> list[float] | None:
    import random
    if not strata or any(not s for s in strata):
        return None
    rng = random.Random(seed)
    values = sorted(statistics.mean(statistics.mean(rng.choices(s, k=len(s))) for s in strata) for _ in range(reps))
    lo = max(0, int(reps * alpha / 2))
    hi = min(reps - 1, int(reps * (1 - alpha / 2)))
    return [values[lo], values[hi]]


def summarize(root: Path) -> dict:
    plan, digest = load(root)
    rows = []
    trace_audit = {"rows": 0, "hero_decisions": 0, "illegal_hero_actions": 0,
                   "stack_or_payoff_conservation_errors": 0, "incomplete_history_rows": 0}
    for job in jobs(plan):
        p = root / (old.job_name(job) + ".json")
        if not p.exists():
            raise ValueError(f"Missing job artifact: {p.name}")
        row = json.loads(p.read_text(encoding="utf-8"))
        old.check_artifact(root, plan, digest, job, row)
        trace_path = root / (old.job_name(job) + ".jsonl")
        trace_rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        if len(trace_rows) != row["executions"]:
            raise ValueError(f"Trace row count does not match execution count: {trace_path.name}")
        trace_audit["rows"] += len(trace_rows)
        for trace_row in trace_rows:
            n = job[2]
            trace_audit["stack_or_payoff_conservation_errors"] += int(
                sum(trace_row["stacks"].values()) != 800 * n or sum(trace_row["payoffs"].values()) != 0)
            trace_audit["incomplete_history_rows"] += int(not isinstance(trace_row.get("history"), list))
            for entry in trace_row.get("trace", []):
                obs = Observation.from_dict(entry["observation"])
                raw_action = entry["decision"]["action"]
                action = Action(raw_action["kind"], raw_action.get("amount", 0))
                trace_audit["hero_decisions"] += 1
                trace_audit["illegal_hero_actions"] += int(not action.is_legal(obs))
        rows.append(row)
    all_sessions = [s for j in rows for s in j["sessions"]]
    counts = Counter()
    for s in all_sessions:
        counts.update(s["counts"])
    arms = {}
    audit = {"tables": len(all_sessions), "expected_tables": sum(n * len(plan["arms"]) * (plan["groups_per_format"] if scenario == "external_diverse" else plan["control_groups_per_format"])
                                                               for scenario in plan["scenarios"] for n in plan["players"]),
             "stack_conservation_failures": 0, "final_zero_stack_counts": 0,
             "histories_complete": True, "jsonl_hashes": {}}
    for j in rows:
        audit["jsonl_hashes"][Path(old.job_name(tuple(j["job"])) + ".jsonl").name] = j["trace_sha256"]
    for arm in plan["arms"]:
        ss = [s for s in all_sessions if s["variant"] == arm]
        reason_totals = Counter()
        for session in ss:
            for reason, count in session["reasons"].items():
                reason_totals[reason.split("=", 1)[0]] += count
        arms[arm] = {"tables": len(ss), "hands": sum(s["played_hands"] for s in ss),
                     "mean_final_stack": statistics.mean(s["last_stacks"]["hero"] for s in ss),
                     "busts": sum(s["hero_eliminated"] for s in ss), "observed_wins": sum(s["hero_observed_win"] for s in ss),
                     "unresolved_at_128": sum(_events(s, 128)["unresolved"] for s in ss),
                     "censored_survivors": sum(s["censored_survivor"] for s in ss),
                     "horizons": {str(h): {k: sum(_events(s, h)[k] for s in ss) for k in ("bust", "win", "unresolved", "table_finished", "censored_survivor")} for h in (24, 64, 128)},
                     "action_counts": dict(sum((Counter(s["hero_actions"]) for s in ss), Counter())),
                     "decision_counts": dict(sum((Counter(s["counts"]) for s in ss), Counter())),
                     "reasons": dict(reason_totals)}
        for s in ss:
            audit["stack_conservation_failures"] += int(sum(s["last_stacks"].values()) != 800 * len(s["last_stacks"]))
            audit["final_zero_stack_counts"] += int(s["last_stacks"]["hero"] == 0)
    contrasts = {}
    if plan["phase"] == "comparison":
        main = [j for j in rows if j["job"][1] == "external_diverse"]
        for candidate in ("v6",):
            by_metric = {}
            for name, metric in (("final_stack_fraction", lambda s: s["last_stacks"]["hero"] / 800),
                                 ("bust_at_128", lambda s: _events(s, 128)["bust"])):
                strata = {n: [] for n in plan["players"]}
                for job in main:
                    n = job["job"][2]
                    idx = {(s["variant"], s["rotation"]): s for s in job["sessions"]}
                    strata[n].append(statistics.mean(metric(idx[(candidate, r)]) - metric(idx[("v2", r)]) for r in range(n)))
                ss = [strata[n] for n in plan["players"]]
                by_metric[name] = {"mean": statistics.mean(map(statistics.mean, ss)),
                                   "interval_97_5": _bootstrap(ss, seed_for(plan["experiment_id"], "stage3-bootstrap", name),
                                                               plan["inference"]["bootstrap_repetitions"],
                                                               plan["inference"]["family_alpha"] / 2),
                                   "groups_by_format": {str(n): len(strata[n]) for n in strata}}
            contrasts[candidate] = by_metric
    trace_audit["passed"] = not any(trace_audit[k] for k in ("illegal_hero_actions", "stack_or_payoff_conservation_errors", "incomplete_history_rows"))
    complete = len(all_sessions) == audit["expected_tables"]
    result = {"complete": complete, "phase": plan["phase"],
              "protocol_sha256": digest, "tables": audit["tables"], "hand_executions": sum(j["executions"] for j in rows),
              "elapsed_seconds": sum(j.get("elapsed_seconds", 0) for j in rows), "technical_counts": dict(counts),
              "technical_pass": complete and not audit["stack_conservation_failures"] and trace_audit["passed"]
                                and all(counts[k] == 0 for k in ("fallbacks", "equity_deadlines", "search_deadlines")),
              "audit": audit, "trace_audit": trace_audit, "arms": arms, "contrasts": contrasts,
              "no_inference": plan["phase"] != "comparison", "default": "v2"}
    save(root / "summary.json", result)
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("register", "run", "summarize"))
    p.add_argument("--root", type=Path, default=Path("results/v6_session_pilot_2026-10-28"))
    p.add_argument("--id", default=PILOT_ID)
    p.add_argument("--phase", choices=("pilot", "comparison"), default="pilot")
    p.add_argument("--groups", type=int, default=2)
    p.add_argument("--workers", type=int, default=2)
    a = p.parse_args()
    if a.command == "register":
        register(a.root, a.id, a.phase, a.groups)
    elif a.command == "run":
        print(json.dumps(run(a.root, a.workers), indent=2))
    else:
        print(json.dumps(summarize(a.root), indent=2))


if __name__ == "__main__":
    main()

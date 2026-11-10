"""Reconstruct six-version results and replay predetermined snapshot hands."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

from pokerfight.campaign import save
from research.competition_audit_20261028.audit_sessions import canonical_trace, reconstruct
from scripts.audit_competition_stage2 import expected_reset
from scripts import integrated_shove_experiment as experiment
from scripts import competition_experiment as executor


def snapshot_api(root):
    alias = "_integrated_shove_replay_snapshot"
    package_path = root / "source" / "pokerfight"
    spec = importlib.util.spec_from_file_location(alias, package_path / "__init__.py",
                                                submodule_search_locations=[str(package_path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return {name: importlib.import_module(alias + "." + name)
            for name in ("arena", "domain", "strategy")}


def audit(root, phase, replay=True):
    plan, digest = experiment.load(root)
    settings, folder = experiment.phase_plan(plan, phase), root / phase
    api = snapshot_api(root)
    totals = Counter()
    times, strategies = {arm: [] for arm in plan["arms"]}, {arm: Counter() for arm in plan["arms"]}
    hashes, replays = {}, []
    reset_means, session_groups = {arm: [] for arm in plan["arms"]}, defaultdict(lambda: defaultdict(list))
    for job in executor.jobs(settings):
        name = executor.job_name(job)
        report_path, trace_path = folder / (name + ".json"), folder / (name + ".jsonl")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        executor.check_artifact(folder, settings, digest, job, report)
        records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        if job[0] == "reset":
            rebuilt = expected_reset(settings, job, records, report)
            totals["reset_hands"] += rebuilt["records"]
            for arm in plan["arms"]:
                reset_means[arm].append(statistics.mean(rebuilt["block_bb_per_hand"][arm]))
        else:
            expected = reconstruct(settings, job, records)
            actual = {(row["variant"], row["rotation"]): row for row in report["sessions"]}
            if expected != actual or len(records) != report["executions"]:
                raise ValueError("Reconstructed session differs: " + name)
            totals["session_hands"] += len(records)
            totals["session_tables"] += len(expected)
            for arm in plan["arms"]:
                selected = [row for (variant, _), row in expected.items() if variant == arm]
                session_groups[arm][tuple(job[1:3])].append({
                    "mean_final_stack": statistics.mean(row["last_stacks"]["hero"] for row in selected),
                    "bust_24": statistics.mean(experiment.bust(row, 24) for row in selected),
                    "bust_128": statistics.mean(experiment.bust(row, 128) for row in selected)})
        for record in records:
            for entry in record["trace"]:
                observation = api["domain"].Observation.from_dict(entry["observation"])
                decision = entry["decision"]
                action = api["domain"].Action(**decision["action"])
                if not action.is_legal(observation):
                    raise ValueError("Trace action violates public legal envelope")
                history = entry["observation"]["history"]
                if record["history"][:len(history)] != history:
                    raise ValueError("Public history prefix differs")
                event = record["history"][len(history)]
                if event["kind"] != action.kind or event["player_id"] != observation.hero_id:
                    raise ValueError("Hero action differs from public event")
                if action.kind == "raise_to" and event["amount"] != action.amount:
                    raise ValueError("Raise amount differs from public event")
                arm = record["variant"]
                times[arm].append(decision["elapsed_ms"])
                strategies[arm][observation.street + ":" + action.kind] += 1
                totals["hero_decisions"] += 1
                totals["hero_fallbacks"] += decision["fallback"]
                info = decision.get("search")
                if info:
                    strategies[arm]["searches"] += 1
                    strategies[arm]["search_changes"] += info["changed"]
                    strategies[arm]["continuation_nodes"] += info.get("continuation_nodes", 0)
                    strategies[arm]["continuation_calls"] += info.get("continuation_calls", 0)
        for path in (report_path, trace_path):
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        selected = (job[1] == "external_diverse" and job[3] == 0) if job[0] == "session" else (
                    job[1] == "external_diverse")
        if replay and selected:
            n = job[2]
            ids, kinds = executor.lineup(n, tuple(settings["scenarios"][job[1]]))
            mode = job[0]
            base = api["arena"].seed_for(settings["experiment_id"],
                "crossplay-session-01" if mode == "session" else "crossplay-reset-01", job[1], n, job[3])
            for arm in settings["arms"]:
                original = [row for row in records if row["variant"] == arm and row["rotation"] == 0
                            and (mode == "session" or row["block"] == 0)]
                original.sort(key=lambda row: row.get("hand", row.get("block")))
                policies = {pid: api["arena"].make_policy(arm if pid == "hero" else kind,
                    api["strategy"].BotConfig(**(settings["configs"][arm] if pid == "hero" else settings["rival_config"])),
                    original[0]["policy_seeds"][pid]) for pid, kind in {"hero": arm, **kinds}.items()}
                stacks = dict.fromkeys(ids, 800 if mode == "session" else job[3] * 100)
                try:
                    for row in original:
                        hand_id = str(row.get("hand", row.get("block")))
                        result = api["arena"].play_hand(policies, tuple(row["seats"]), stacks,
                            row["deck_seed"], hand_id, executor.table_key(base, 0, mode), trace_player_id="hero")
                        if (result.payoffs != row["payoffs"] or result.stacks != row["stacks"]
                            or list(result.board) != row["board"]
                            or [asdict(event) for event in result.history] != row["history"]
                            or canonical_trace(result.trace) != canonical_trace(row["trace"])):
                            raise ValueError(f"Snapshot replay differs: {name}/{arm}/{hand_id}")
                        stacks.update(result.stacks)
                        totals["replay_hands_excluded_from_new_evidence"] += 1
                finally:
                    api["arena"].close_policies(policies)
                replays.append({"job": job, "arm": arm, "rotation": 0, "matched_hands": len(original)})
        save(folder / "audit_progress.json", {"last_job": name, **totals})
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    if summary["reset_hand_executions"] != totals["reset_hands"] or summary["session_hand_executions"] != totals["session_hands"]:
        raise ValueError("Summary execution totals differ")
    for arm in plan["arms"]:
        if summary["descriptive"][arm]["reset_bb_per_hand"] != statistics.mean(reset_means[arm]):
            raise ValueError("Summary reset mean differs")
        for metric in ("mean_final_stack", "bust_24", "bust_128"):
            strata = session_groups[arm]
            if strata:
                value = statistics.mean(statistics.mean(row[metric] for row in rows) for rows in strata.values())
                if summary["descriptive"][arm][metric] != value:
                    raise ValueError("Summary session metric differs")
    result = {"passed": True, "phase": phase, "protocol_sha256": digest, **totals,
              "snapshot_replays": replays, "artifact_sha256": hashes,
              "hero_latency": {arm: {"decisions": len(values),
                  "p50_ms": statistics.median(values) if values else 0,
                  "p95_ms": sorted(values)[max(0, __import__('math').ceil(.95 * len(values)) - 1)] if values else 0,
                  "max_ms": max(values, default=0)} for arm, values in times.items()},
              "strategies": strategies,
              "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(folder / "audit.json", result)
    print(json.dumps({key: result[key] for key in ("passed", "phase", "reset_hands", "session_hands", "hero_decisions", "replay_hands_excluded_from_new_evidence") if key in result}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", choices=("pilot", "comparison"), default="comparison")
    parser.add_argument("--no-replay", action="store_true")
    args = parser.parse_args()
    audit(args.root.resolve(), args.phase, not args.no_replay)

"""Preregister, execute and summarize the bounded v3 experiment.

Each cell has independent blocks; paired variants and seat rotations share decks.
Bootstrap within cells, then average cells equally. Sessions cluster rotations
within independent groups. This is neither AIVAT nor a tournament simulation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

from .arena import seed_for
from .campaign import save
from .evaluation import bootstrap_interval, environment, evaluate, simulate
from .strategy import BotConfig

SCENARIOS = {"selective": ["tag", "tag", "lag"],
             "pressure": ["pressure", "lag", "tag"], "copies_v2": ["v2"]}


def protocol(experiment_id: str) -> dict:
    if not experiment_id.strip():
        raise ValueError("experiment_id vacío")
    return {"experiment_id": experiment_id, "created_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment(), "candidate": "v3", "control": "v2", "scenarios": SCENARIOS,
        "depths_bb": [4, 8, 12, 20], "players": [2, 3, 4, 5, 6], "primary_players": [5, 6],
        "primary_depths_bb": [4, 8], "big_blind": 100, "small_blind": 50, "ante": 0,
        "budget_ms": 1600, "rival_samples": 256,
        "phases": {
            "pilot": {"namespace": experiment_id + ":pilot:01", "samples": 256,
                      "main_blocks": 2, "secondary_blocks": 2, "hands_per_block": 1,
                      "session_groups": 1, "session_hands": 24, "session_scenarios": ["pressure", "copies_v2"]},
            "validation": {"namespace": experiment_id + ":validation:01", "samples": 512,
                           "main_blocks": 12, "secondary_blocks": 4, "hands_per_block": 2,
                           "session_groups": 3, "session_hands": 30, "session_scenarios": list(SCENARIOS)},
            "production": {"namespace": experiment_id + ":production:01", "samples": 4000,
                           "blocks": 2, "hands_per_block": 1, "players": [5, 6],
                           "depths_bb": [4, 8], "scenarios": ["pressure"]}},
        "session_starting_bb": 8, "session_blind_interval": 10,
        "acceptance": {
            "primary": "Equal-weight paired v3-v2 bb/hand over 5/6 players, 4/8 bb, all 3 scenarios; stratified block bootstrap 95% lower > 0.",
            "formats": "Mean paired delta for each primary player count must be >= 0.",
            "harm": "No primary cell with 95% interval upper < -0.25 bb/hand.",
            "sessions": "Equal-weight final-chip delta / initial stack over independent rotation groups: 95% lower >= 0.",
            "safety": "All phases complete, zero invalid actions, recovered illegal proposals, fallbacks or hero decisions >=2000ms.",
            "default": "Keep v2 if any criterion fails or evidence is uncertain. No tuning after pilot; validation is examined once at completion."},
        "inference": "Rotations are dependent. Cell blocks and session groups have disjoint seeds. Intervals are descriptive, no multiple-comparison correction.",
        "old_data": "All previously viewed batches, even those named holdout, are development only."}


def verify_control() -> None:
    root = Path(__file__).parent / "frozen_v2"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Control v2 modificado: {name}")


def stratified_interval(groups: list[list[float]], seed: int, repetitions=5000):
    """Equal-weight cells; resample entire independent blocks inside each cell."""
    if not groups or any(len(g) < 2 for g in groups):
        return None
    rng = random.Random(seed)
    means = sorted(statistics.mean(statistics.mean(rng.choices(g, k=len(g))) for g in groups)
                   for _ in range(repetitions))
    return [means[int(repetitions * .025)], means[int(repetitions * .975)]]


def pooled(rows: list[dict], key: str, seed: int) -> dict:
    groups = [r[key] for r in rows]
    return {"cells": len(groups), "independent_blocks": sum(map(len, groups)),
            "mean": statistics.mean(statistics.mean(g) for g in groups) if groups else None,
            "interval_95": stratified_interval(groups, seed)}


def summarize(root: Path, plan: dict, phase: str) -> dict:
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / phase).glob("paired_*.json"))]
    sessions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / phase).glob("session_*.json"))]
    primary = [r for r in reports if r["players"] in plan["primary_players"] and r["depth_bb"] in plan["primary_depths_bb"]]
    key = "block_differences_bb_per_hand"
    result = {"phase": phase, "paired_cells": len(reports), "paired_hand_executions": sum(r["hands_per_variant"] * 2 for r in reports),
              "base_decks": sum(r["base_decks"] for r in reports),
              "primary": pooled(primary, key, seed_for(plan["experiment_id"], phase, "primary")),
              "by_players": {str(n): pooled([r for r in primary if r["players"] == n], key, seed_for(phase, n)) for n in (5, 6)},
              "paired": [{k: r[k] for k in ("scenario", "players", "depth_bb", "candidate_bb_per_hand", "baseline_bb_per_hand",
                   "paired_difference_bb_per_hand", "paired_block_bootstrap_95_interval", "candidate_chips", "baseline_chips",
                   "candidate_bust_hands", "baseline_bust_hands", "hero_latency", "baseline_latency")} for r in reports],
              "session_hand_executions": sum(r["variants"][v]["played_hands"] for r in sessions for v in ("v2", "v3")),
              "session_tables_per_variant": len(sessions), "sessions": []}
    grouped = {}
    for row in sessions:
        a, b = row["variants"]["v3"], row["variants"]["v2"]
        group = (row["scenario"], row["players"], row["group"])
        grouped.setdefault(group, []).append((a["last_stacks"]["hero"] - b["last_stacks"]["hero"]) / 800)
    group_deltas = [statistics.mean(v) for v in grouped.values()]
    result["session_pooled"] = {"groups": len(grouped), "mean_delta_initial_stacks": statistics.mean(group_deltas) if group_deltas else None,
        "interval_95": bootstrap_interval(group_deltas, seed_for(phase, "sessions")), "group_deltas": group_deltas}
    for scenario in SCENARIOS:
        for n in (5, 6):
            rows = [r for r in sessions if r["scenario"] == scenario and r["players"] == n]
            if not rows:
                continue
            deltas = [statistics.mean(v) for (s, p, _), v in grouped.items() if s == scenario and p == n]
            detail = {"scenario": scenario, "players": n, "tables_per_variant": len(rows),
                      "group_delta_initial_stacks": deltas,
                      "interval_95": bootstrap_interval(deltas, seed_for(phase, scenario, n, "session"))}
            for v in ("v2", "v3"):
                variants = [r["variants"][v] for r in rows]
                detail[v] = {"mean_final_chips": statistics.mean(r["last_stacks"]["hero"] for r in variants),
                    "eliminated": sum(not r["hero_survived"] for r in variants),
                    "survived": sum(r["hero_survived"] for r in variants),
                    "tables_won": sum(r["hero_survived"] and r["table_finished"] for r in variants),
                    "tables_finished": sum(r["table_finished"] for r in variants)}
            result["sessions"].append(detail)
    all_reports = reports + [r["variants"][v] for r in sessions for v in ("v2", "v3")]
    result["checks"] = {"fallbacks": sum(r["fallbacks_all_policies"] for r in all_reports),
        "invalid_actions": sum(r["invalid_actions_all_policies"] for r in all_reports),
        "recovered_illegal_proposals": sum(r["invalid_proposals_recovered"] for r in all_reports),
        "hero_over_2000_ms": sum(r["hero_latency"]["over_2000_ms"] + r.get("baseline_latency", {}).get("over_2000_ms", 0) for r in all_reports),
        "chips_conserved": all(r["chips_conserved"] for r in all_reports)}
    primary_ci = result["primary"]["interval_95"]
    session_ci = result["session_pooled"]["interval_95"]
    result["criteria"] = {"primary_positive": bool(primary_ci and primary_ci[0] > 0),
        "both_formats_nonnegative": all(r["mean"] is not None and r["mean"] >= 0 for r in result["by_players"].values()),
        "no_clear_primary_harm": all(r["paired_block_bootstrap_95_interval"] is not None and r["paired_block_bootstrap_95_interval"][1] >= -.25 for r in primary),
        "sessions_nonnegative": bool(session_ci and session_ci[0] >= 0),
        "safety": result["checks"]["chips_conserved"] and not any(result["checks"][k] for k in ("fallbacks", "invalid_actions", "recovered_illegal_proposals", "hero_over_2000_ms"))}
    result["recommendation"] = "v3_eligible_pending_all_phases" if all(result["criteria"].values()) else "keep_v2"
    save(root / phase / "summary.json", result)
    return result


def run(root: Path, phase: str) -> dict:
    plan = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    verify_control()
    if environment() != plan["environment"]:
        raise ValueError("Código o entorno distinto del protocolo; registre un experimento nuevo")
    if phase == "validation" and not (root / "pilot" / "summary.json").exists():
        raise ValueError("Complete el piloto antes de validar")
    settings = plan["phases"][phase]
    target = root / phase
    target.mkdir(exist_ok=True)
    config = BotConfig(settings["samples"], plan["budget_ms"])
    for scenario in settings.get("scenarios", list(SCENARIOS)):
        for n in settings.get("players", plan["players"]):
            for depth in settings.get("depths_bb", plan["depths_bb"]):
                path = target / f"paired_{scenario}_{n}p_{depth}bb.json"
                if path.exists():
                    continue
                print(f"{phase}: {scenario} {n}p {depth}bb", flush=True)
                report = evaluate(n, settings.get("blocks", settings.get("main_blocks") if n in (5, 6) else settings.get("secondary_blocks")),
                    settings["hands_per_block"], seed_for(scenario, n, depth), config, tuple(SCENARIOS[scenario]),
                    "v2", "v3", str(target / (path.stem + ".jsonl")), starting_stack=depth * 100,
                    experiment_id=settings["namespace"])
                save(path, {"environment": plan["environment"], "scenario": scenario, "depth_bb": depth, **report})
    for scenario in settings.get("session_scenarios", []):
        for n in (5, 6):
            for group in range(settings["session_groups"]):
                for rotation in range(n):
                    path = target / f"session_{scenario}_{n}p_g{group}_r{rotation}.json"
                    if path.exists():
                        continue
                    print(f"{phase}: session {scenario} {n}p g{group} r{rotation}", flush=True)
                    variants = {}
                    for v in ("v2", "v3"):
                        variants[v] = simulate(n, settings["session_hands"], seed_for("session", scenario, n, group),
                            config, tuple(SCENARIOS[scenario]), True, plan["session_starting_bb"] * 100,
                            hero_kind=v, blind_interval=plan["session_blind_interval"], initial_rotation=rotation,
                            experiment_id=settings["namespace"])
                    save(path, {"scenario": scenario, "players": n, "group": group, "rotation": rotation, "variants": variants})
    return summarize(root, plan, phase)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--init", metavar="EXPERIMENT_ID")
    parser.add_argument("--phase", choices=("pilot", "validation", "production"))
    args = parser.parse_args()
    root = Path(args.root)
    if args.init:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "protocol.json"
        if path.exists():
            raise ValueError("El protocolo ya existe; no se sobrescribe")
        verify_control()
        save(path, protocol(args.init))
        print(path)
    if args.phase:
        result = run(root, args.phase)
        print(json.dumps({k: result[k] for k in ("phase", "paired_hand_executions", "session_hand_executions", "primary", "criteria", "recommendation")}, indent=2))


if __name__ == "__main__":
    main()

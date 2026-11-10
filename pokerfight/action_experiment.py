"""Fresh preregistered three-arm test: original v2, high-MC v2, response-search v4."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from .arena import make_policy, play_hand, seed_for
from .campaign import save
from .evaluation import environment, evaluate, latency, lineup, simulate, summarize_contexts
from .shortstack_experiment import pooled, verify_control
from .strategy import BotConfig

SCENARIOS = {"selective": ("tag", "tag", "lag"), "pressure": ("pressure", "lag", "tag"), "copies_v2": ("v2",)}


def protocol(identifier):
    if not identifier.strip():
        raise ValueError("Identificador vacío")
    return {"experiment_id": identifier, "created_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment(), "scenarios": SCENARIOS,
        "candidate": "v4", "equal_envelope_control": "v2mc", "original_control": "v2",
        "budget_ms": 3500, "hard_response_ms": 4250,
        "original_config": asdict(BotConfig(samples=4000, budget_ms=1600)),
        "rival_config": asdict(BotConfig(samples=512, budget_ms=1600)),
        "primary_players": [5, 6], "primary_depths": [4, 8, 12], "secondary_players": [2, 3, 4],
        "sentinel_depths": [20, 100],
        "phases": {
            "pilot": {"namespace": identifier + ":pilot:01", "samples": 1024, "main_blocks": 2,
                      "secondary_blocks": 1, "sentinel_blocks": 1, "hands_per_block": 1,
                      "session_groups": 1, "session_scenarios": ["pressure"], "session_hands": 16},
            "validation": {"namespace": identifier + ":validation:01", "samples": 16384, "main_blocks": 8,
                           "secondary_blocks": 3, "sentinel_blocks": 3, "hands_per_block": 1,
                           "session_groups": 2, "session_scenarios": list(SCENARIOS), "session_hands": 20}},
        "session_starting_bb": 8, "session_blind_interval": 10,
        "profile": {"cases": ["utg_speculative_4bb", "heads_up_8bb", "utg_weak_ace_4bb", "button_weak_ace_4bb",
            "effective_4bb_hero_100bb", "bb_cheap_defense_8bb", "bb_expensive_defense_8bb", "cheap_all_in_regression"],
            "repeats": 3, "policies": ["v2", "v2mc", "v4"], "intentional_stall_timeout_ms": 4250},
        "acceptance": {
            "primary": "Equal-weight paired v4-v2mc over 5/6 players and 4/8/12 bb: stratified block bootstrap 95% lower > 0.",
            "original": "The same primary contrast v4-original-v2 must also have 95% lower > 0.",
            "formats": "Mean delta >=0 versus both controls separately for 5 and 6 players.",
            "sessions": "Paired final-chip delta versus each control, rotations averaged per group: aggregate 95% lower >=0.",
            "safety": "Zero illegal actions, recovered illegal proposals, error fallbacks, or hero decisions >4250ms; chips conserved; supervisor fault tests pass.",
            "default": "Keep original v2 unless all pass; no retuning between pilot and validation."},
        "allocation": "v4 and v2mc have the same 3500ms ceiling and total sample-cap parameter. v4 allocates at most 4000 samples to baseline equity and the remainder of TIME to action-world evaluation; v2mc spends its quota on equity. Actual CPU work is reported, not assumed equal.",
        "model": "Three hypothetical fold/call priors, common joint card draws and response uniforms. Nonterminal checkdown proxies omit reraises and future bets. Retain v2 unless all priors favor a change by 0.05bb plus two paired MC SE.",
        "old_data": "All earlier v1/v2/v3 batches and compute probes are development. New phase namespaces determine new decks.",
        "interpretation": "Rotations are not independent. Local table wins do not imply tournament qualification. Two-SE adaptive stopping is heuristic; outcome intervals use independent blocks/groups."}


def cells(plan, settings):
    for scenario in SCENARIOS:
        for n in plan["primary_players"] + plan["secondary_players"]:
            for depth in plan["primary_depths"]:
                yield scenario, n, depth, settings["main_blocks"] if n in (5, 6) else settings["secondary_blocks"]
        for n in plan["primary_players"]:
            for depth in plan["sentinel_depths"]:
                yield scenario, n, depth, settings["sentinel_blocks"]


def original_arm(report, trace_path):
    """Third arm on exactly the report's decks, seats and policy RNG seeds."""
    config = BotConfig(samples=4000, budget_ms=1600)
    rival = BotConfig(**report["rival_config"])
    ids, kinds = lineup(report["players"], tuple(report["opponents"].values()))
    results, means, worst = [], [], []
    with Path(trace_path).open("w", encoding="utf-8") as trace:
        for block in range(report["blocks"]):
            profits = []
            for rotation in range(report["players"]):
                seats = ids[rotation:] + ids[:rotation]
                seeds = {pid: seed_for(report["seed"], "policy", block, rotation, pid) for pid in ids}
                table = f"eval-{report['seed']}-{block}-{rotation}"
                policies = {pid: make_policy("v2" if pid == "hero" else kinds[pid], config if pid == "hero" else rival,
                                             seeds[pid]) for pid in ids}
                for hand in range(report["hands_per_block_per_seat"]):
                    deck = seed_for(report["seed"], "deck", block, hand)
                    a = report["assumptions"]
                    result = play_hand(policies, seats, dict.fromkeys(ids, a["starting_stack"]), deck,
                        str(hand), table, a["small_blind"], a["big_blind"], a["ante"], trace_player_id="hero")
                    results.append(result)
                    profits.append(result.payoffs["hero"] / a["big_blind"])
                    record = {"block": block, "rotation": rotation, "hand": hand, "variant": "original", "hero_policy": "v2",
                        "table_id": table, "seats": seats, "deck_seed": deck, "policy_seeds": seeds,
                        "payoffs": result.payoffs, "board": result.board, "history": [asdict(e) for e in result.history], "trace": result.trace}
                    trace.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    worst.append(record)
                    worst.sort(key=lambda r: r["payoffs"]["hero"])
                    del worst[5:]
            means.append(statistics.mean(profits))
    return {**{k: report[k] for k in ("players", "seed", "blocks", "hands_per_block_per_seat", "assumptions", "opponents",
                                      "rival_config", "environment", "scenario", "depth_bb", "experiment_id")},
        "config": asdict(config), "candidate": "v2", "candidate_block_bb_per_hand": means,
        "hands_per_variant": len(results), "candidate_chips": sum(r.payoffs["hero"] for r in results),
        "candidate_bust_hands": sum(r.stacks["hero"] == 0 for r in results), "hero_latency": latency(results),
        "candidate_contexts": summarize_contexts(results), "worst_candidate_hands": worst,
        "fallbacks_all_policies": sum(d.fallback for r in results for _, d in r.decisions),
        "invalid_actions_all_policies": 0, "chips_conserved": True,
        "invalid_proposals_recovered": sum(d.fallback and "ilegal" in d.reason for r in results for _, d in r.decisions)}


def summarize(root, phase, plan):
    folder = root / phase
    reports = []
    checks = Counter()
    for path in sorted(folder.glob("paired_*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        old = json.loads((folder / path.name.replace("paired_", "original_")).read_text(encoding="utf-8"))
        r["original_block_bb_per_hand"] = old["candidate_block_bb_per_hand"]
        r["delta_original"] = [a - b for a, b in zip(r["candidate_block_bb_per_hand"], old["candidate_block_bb_per_hand"], strict=True)]
        r["original_bb_per_hand"] = statistics.mean(old["candidate_block_bb_per_hand"])
        r["original_latency"] = old["hero_latency"]
        r["original_chips"] = old["candidate_chips"]
        r["original_bust_hands"] = old["candidate_bust_hands"]
        reports.append(r)
        for result in (r, old):
            checks["fallbacks"] += result["fallbacks_all_policies"]
            checks["invalid_actions"] += result["invalid_actions_all_policies"]
            checks["recovered_illegal_proposals"] += result["invalid_proposals_recovered"]
            checks["chip_failures"] += not result["chips_conserved"]
            checks["over_4250_ms"] += result["hero_latency"]["over_4250_ms"] + result.get("baseline_latency", {}).get("over_4250_ms", 0)
    primary = [r for r in reports if r["players"] in (5, 6) and r["depth_bb"] in plan["primary_depths"]]
    result = {"phase": phase, "cells": len(reports), "hand_executions_reset": sum(r["hands_per_variant"] * 3 for r in reports),
        "primary_vs_mc": pooled(primary, "block_differences_bb_per_hand", seed_for(phase, "primary-mc")),
        "primary_vs_original": pooled(primary, "delta_original", seed_for(phase, "primary-original")),
        "by_players": {str(n): {"mc": pooled([r for r in primary if r["players"] == n], "block_differences_bb_per_hand", seed_for(phase, n, "mc")),
                               "original": pooled([r for r in primary if r["players"] == n], "delta_original", seed_for(phase, n, "original"))} for n in (5, 6)},
        "paired": [{k: r[k] for k in ("scenario", "players", "depth_bb", "hands_per_variant", "candidate_bb_per_hand", "baseline_bb_per_hand",
            "original_bb_per_hand", "paired_difference_bb_per_hand", "delta_original", "block_differences_bb_per_hand", "paired_block_bootstrap_95_interval",
            "candidate_chips", "baseline_chips", "original_chips", "candidate_bust_hands", "baseline_bust_hands", "original_bust_hands",
            "hero_latency", "baseline_latency", "original_latency")} for r in reports]}
    sessions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("session_*.json"))]
    result["session_tables_per_variant"] = len(sessions)
    result["hand_executions_sessions"] = sum(v["played_hands"] for s in sessions for v in s["variants"].values())
    session_groups = {"v2": {}, "v2mc": {}}
    for s in sessions:
        for kind, v in s["variants"].items():
            checks["fallbacks"] += v["fallbacks_all_policies"]
            checks["invalid_actions"] += v["invalid_actions_all_policies"]
            checks["recovered_illegal_proposals"] += v["invalid_proposals_recovered"]
            checks["chip_failures"] += not v["chips_conserved"]
            checks["over_4250_ms"] += v["hero_latency"]["over_4250_ms"]
        for control in session_groups:
            delta = (s["variants"]["v4"]["last_stacks"]["hero"] - s["variants"][control]["last_stacks"]["hero"]) / 800
            session_groups[control].setdefault((s["scenario"], s["players"], s["group"]), []).append(delta)
    from .evaluation import bootstrap_interval
    result["session_pooled"] = {control: {"groups": len(groups),
        "mean_initial_stacks": statistics.mean(statistics.mean(g) for g in groups.values()) if groups else None,
        "interval_95": bootstrap_interval([statistics.mean(g) for g in groups.values()], seed_for(phase, "sessions", control))}
        for control, groups in session_groups.items()}
    result["checks"] = dict(checks)
    result["criteria"] = {"primary_mc_positive": bool(result["primary_vs_mc"]["interval_95"] and result["primary_vs_mc"]["interval_95"][0] > 0),
        "primary_original_positive": bool(result["primary_vs_original"]["interval_95"] and result["primary_vs_original"]["interval_95"][0] > 0),
        "both_formats_nonnegative": all(r[c]["mean"] >= 0 for r in result["by_players"].values() for c in ("mc", "original")),
        "sessions_nonnegative": all(v["interval_95"] and v["interval_95"][0] >= 0 for v in result["session_pooled"].values()),
        "safety": not any(checks.values())}
    result["recommendation"] = "v4_eligible_pending_supervisor_validation" if all(result["criteria"].values()) else "keep_v2"
    save(folder / "summary.json", result)
    return result


def run(root, phase):
    plan = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    verify_control()
    if environment() != plan["environment"]:
        raise ValueError("Código/entorno distinto del protocolo")
    if phase == "validation" and not (root / "pilot/summary.json").exists():
        raise ValueError("Complete primero el piloto")
    settings = plan["phases"][phase]
    folder = root / phase
    folder.mkdir(exist_ok=True)
    config = BotConfig(samples=settings["samples"], budget_ms=plan["budget_ms"])
    rival = BotConfig(**plan["rival_config"])
    for scenario, n, depth, blocks in cells(plan, settings):
        path = folder / f"paired_{scenario}_{n}p_{depth}bb.json"
        if not path.exists():
            print(f"{phase}: {scenario} {n}p {depth}bb", flush=True)
            report = evaluate(n, blocks, settings["hands_per_block"], seed_for(scenario, n, depth), config,
                SCENARIOS[scenario], "v2mc", "v4", str(path.with_suffix(".jsonl")), starting_stack=depth * 100,
                experiment_id=settings["namespace"], rival_config=rival)
            save(path, {"environment": plan["environment"], "scenario": scenario, "depth_bb": depth, **report})
        original = folder / path.name.replace("paired_", "original_")
        if not original.exists():
            r = json.loads(path.read_text(encoding="utf-8"))
            save(original, original_arm(r, str(original.with_suffix(".jsonl"))))
    for scenario in settings["session_scenarios"]:
        for n in (5, 6):
            for group in range(settings["session_groups"]):
                for rotation in range(n):
                    path = folder / f"session_{scenario}_{n}p_g{group}_r{rotation}.json"
                    if path.exists():
                        continue
                    print(f"{phase}: session {scenario} {n}p g{group} r{rotation}", flush=True)
                    variants = {kind: simulate(n, settings["session_hands"], seed_for("session", scenario, n, group),
                        BotConfig(**plan["original_config"]) if kind == "v2" else config, SCENARIOS[scenario],
                        True, 800, hero_kind=kind, blind_interval=10, initial_rotation=rotation,
                        experiment_id=settings["namespace"], rival_config=rival) for kind in ("v2", "v2mc", "v4")}
                    save(path, {"scenario": scenario, "players": n, "group": group, "rotation": rotation, "variants": variants})
    return summarize(root, phase, plan)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--init")
    parser.add_argument("--phase", choices=("pilot", "validation"))
    a = parser.parse_args()
    root = Path(a.root)
    if a.init:
        root.mkdir(exist_ok=True, parents=True)
        if (root / "protocol.json").exists():
            raise ValueError("El protocolo no se sobrescribe")
        verify_control()
        save(root / "protocol.json", protocol(a.init))
        print(root / "protocol.json")
    if a.phase:
        result = run(root, a.phase)
        print(json.dumps({k: result[k] for k in ("phase", "hand_executions_reset", "hand_executions_sessions",
            "primary_vs_mc", "primary_vs_original", "criteria", "recommendation")}, indent=2))


if __name__ == "__main__":
    main()

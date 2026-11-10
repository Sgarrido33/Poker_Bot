"""Preregistered five-arm quality comparison; identical deals and rival quotas.

Pilot/validation use disjoint namespaces. Every seat rotation stays in its deck
block for inference. No selection rule may be tuned after observing the pilot.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.campaign import save
from pokerfight.evaluation import environment, latency, lineup, simulate
from pokerfight.shortstack_experiment import stratified_interval, verify_control
from pokerfight.strategy import BotConfig


VARIANTS = ("v2", "v2mc", "v4", "v4rb", "v5")
SCENARIOS = {"selective": ("tag", "tag", "lag"), "pressure": ("pressure", "lag", "tag"), "copies_v2": ("v2",)}


def protocol(identifier):
    return {"experiment_id": identifier, "created_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment(), "variants": VARIANTS, "scenarios": SCENARIOS,
        "players": [5, 6], "depths_bb": [4, 8, 12], "rival_samples": 512,
        "samples": 4096, "budget_ms": 3500,
        "phases": {"pilot": {"namespace": identifier + ":pilot:01", "blocks": 2, "session_groups": 0},
                   "validation": {"namespace": identifier + ":validation:01", "blocks": 6, "session_groups": 2}},
        "session": {"starting_stack": 800, "hand_limit": 20, "blind_interval": 10,
                    "scenarios": ["pressure", "copies_v2"]},
        "acceptance": {"primary": "Equal-weight paired bb/hand delta over 18 cells versus both v4 and original v2: 95% stratified block bootstrap lower > 0.",
            "formats": "Mean paired delta >=0 for each player count against both controls.",
            "sessions": "Final chips/800 paired delta, grouped by independent seeds and rotations: 95% lower >=0 versus both controls.",
            "safety": "Zero fallbacks, illegal proposals or chip conservation errors.",
            "promotion": "Retain v2 default if any criterion fails; no tuning after pilot. Intervals are exploratory, unadjusted for two candidates."},
        "limitations": ["Local rule opponents; no tournament strength claim.",
            "v5 contains one opposing shove, no later betting; manual response priors.",
            "Equal world caps are not equal CPU; v5 spends half its worlds learning continuation.",
            "v4/v4rb can stop adaptively; two-SE boundaries are heuristic."]}


def verify(plan):
    verify_control()
    if plan["environment"]["source_sha256"] != environment()["source_sha256"]:
        raise ValueError("Código cambió desde el registro; registra un experimento nuevo")


def cell(root, plan, phase, scenario, players, depth):
    verify(plan)
    settings = plan["phases"][phase]
    path = root / phase / f"cell_{scenario}_{players}p_{depth}bb.json"
    if path.exists():
        print(f"existing {path.name}", flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ids, kinds = lineup(players, tuple(plan["scenarios"][scenario]))
    base_seed = seed_for(settings["namespace"], scenario, players, depth)
    config = BotConfig(samples=plan["samples"], budget_ms=plan["budget_ms"])
    original = BotConfig(samples=4000, budget_ms=1600)
    rival = BotConfig(samples=plan["rival_samples"], budget_ms=1600)
    results = {v: [] for v in VARIANTS}
    block_means = {v: [] for v in VARIANTS}
    with path.with_suffix(".jsonl").open("w", encoding="utf-8") as trace:
        for block in range(settings["blocks"]):
            profits = {v: [] for v in VARIANTS}
            for rotation in range(players):
                seats = ids[rotation:] + ids[:rotation]
                policy_seeds = {pid: seed_for(base_seed, "policy", block, rotation, pid) for pid in ids}
                deck = seed_for(base_seed, "deck", block)
                # Alternate order to spread machine-load effects across arms.
                ordered = VARIANTS if (block + rotation) % 2 == 0 else tuple(reversed(VARIANTS))
                for variant in ordered:
                    policies = {pid: make_policy(variant if pid == "hero" else kinds[pid],
                        (original if variant == "v2" else config) if pid == "hero" else rival,
                        policy_seeds[pid]) for pid in ids}
                    result = play_hand(policies, seats, dict.fromkeys(ids, depth * 100), deck,
                        str(block), f"quality-{base_seed}-{rotation}", trace_player_id="hero")
                    results[variant].append(result)
                    profits[variant].append(result.payoffs["hero"] / 100)
                    trace.write(json.dumps({"block": block, "rotation": rotation, "variant": variant,
                        "deck_seed": deck, "policy_seeds": policy_seeds, "seats": seats,
                        "payoffs": result.payoffs, "stacks": result.stacks,
                        "history": [asdict(e) for e in result.history], "trace": result.trace}, ensure_ascii=False) + "\n")
            for v in VARIANTS:
                block_means[v].append(statistics.mean(profits[v]))
    row = {"phase": phase, "scenario": scenario, "players": players, "depth_bb": depth,
        "base_seed": base_seed, "source_sha256": plan["environment"]["source_sha256"],
        "blocks": settings["blocks"], "hands_per_variant": settings["blocks"] * players,
        "config": asdict(config), "original_config": asdict(original), "rival_config": asdict(rival),
        "block_bb_per_hand": block_means, "arms": {v: {
            "bb_per_hand": statistics.mean(block_means[v]), "hero_latency": latency(results[v]),
            "fallbacks_all_policies": sum(d.fallback for r in results[v] for _, d in r.decisions),
            "bust_hands": sum(r.stacks["hero"] == 0 for r in results[v]),
            "hero_actions": dict(Counter(f"{e.street}:{d.action.kind}" for r in results[v]
                for e, (pid, d) in zip(r.history, r.decisions, strict=True) if pid == "hero")),
            "chips_conserved": all(sum(r.payoffs.values()) == 0 for r in results[v])} for v in VARIANTS}}
    verify(plan)
    save(path, row)
    print(f"done {path.name}: " + str({v: round(row['arms'][v]['bb_per_hand'], 3) for v in VARIANTS}), flush=True)


def sessions(root, plan, phase, scenario, players, group):
    verify(plan)
    settings = plan["phases"][phase]
    config, rival = BotConfig(plan["samples"], plan["budget_ms"]), BotConfig(plan["rival_samples"])
    for rotation in range(players):
        path = root / phase / f"session_{scenario}_{players}p_g{group}_r{rotation}.json"
        if path.exists():
            continue
        rows = {}
        for variant in VARIANTS:
            cfg = BotConfig() if variant == "v2" else config
            rows[variant] = simulate(players, plan["session"]["hand_limit"],
                seed_for(settings["namespace"], "sessions", scenario, players, group), cfg,
                tuple(plan["scenarios"][scenario]), True, plan["session"]["starting_stack"],
                50, 100, 0, variant, plan["session"]["blind_interval"], rotation, rival_config=rival)
        verify(plan)
        save(path, {"scenario": scenario, "players": players, "group": group, "rotation": rotation, "variants": rows})
        print(f"done {path.name}", flush=True)


def summarize(root, plan, phase):
    cells = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / phase).glob("cell_*.json"))]
    sessions_data = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / phase).glob("session_*.json"))]
    contrasts = {}
    for candidate in ("v4rb", "v5", "v4", "v2mc"):
        contrasts[candidate] = {}
        for control in ("v2", "v4"):
            if candidate == control:
                continue
            groups = [[a - b for a, b in zip(r["block_bb_per_hand"][candidate], r["block_bb_per_hand"][control])]
                      for r in cells]
            session_groups = {}
            for r in sessions_data:
                key = (r["scenario"], r["players"], r["group"])
                a, b = (r["variants"][v]["last_stacks"]["hero"] for v in (candidate, control))
                session_groups.setdefault(key, []).append((a - b) / 800)
            # Stratify sessions by scenario/player count, resample whole seed groups.
            strata = {}
            for (scenario, players, group), deltas in session_groups.items():
                strata.setdefault((scenario, players), []).append(statistics.mean(deltas))
            session_arrays = list(strata.values())
            contrasts[candidate][control] = {"mean_bb_per_hand": statistics.mean(map(statistics.mean, groups)) if groups else None,
                "interval_95": stratified_interval(groups, seed_for(phase, candidate, control)),
                "by_players": {str(n): statistics.mean(statistics.mean([a-b for a,b in zip(
                    r['block_bb_per_hand'][candidate], r['block_bb_per_hand'][control])]) for r in cells if r['players'] == n)
                    for n in (5, 6) if any(r['players'] == n for r in cells)},
                "session_mean_stack_fraction": statistics.mean(map(statistics.mean, session_arrays)) if session_arrays else None,
                "session_interval_95": stratified_interval(session_arrays, seed_for(phase, candidate, control, "sessions")),
                "session_independent_groups": len(session_groups)}
    expected_sessions = sum(plan['players']) * len(plan['session']['scenarios']) * plan['phases'][phase]['session_groups']
    complete = len(cells) == len(plan["players"]) * len(plan["depths_bb"]) * len(plan["scenarios"]) and len(sessions_data) == expected_sessions
    safety = all(r['arms'][v]['fallbacks_all_policies'] == 0 and r['arms'][v]['chips_conserved'] for r in cells for v in VARIANTS)
    safety = safety and all(r['variants'][v]['fallbacks_all_policies'] == 0 and r['variants'][v]['chips_conserved']
                            for r in sessions_data for v in VARIANTS)
    eligible = {}
    for candidate in ("v4rb", "v5"):
        eligible[candidate] = complete and safety and phase == 'validation' and all(
            c['interval_95'] is not None and c['interval_95'][0] > 0 and
            all(d >= 0 for d in c['by_players'].values()) and
            c['session_interval_95'] is not None and c['session_interval_95'][0] >= 0
            for c in contrasts[candidate].values())
    result = {"phase": phase, "complete": complete, "cells": len(cells), "session_tables_per_variant": len(sessions_data),
        "paired_hand_executions": sum(r['hands_per_variant'] * len(VARIANTS) for r in cells),
        "session_hand_executions": sum(r['variants'][v]['played_hands'] for r in sessions_data for v in VARIANTS),
        "safety_passed": safety, "contrasts": contrasts, "eligible_for_promotion": eligible,
        "default": "v2", "limitations": plan['limitations']}
    save(root / phase / 'summary.json', result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('register', 'run', 'summarize'))
    parser.add_argument('--root', default='results/quality_2026-10-28')
    parser.add_argument('--id', default='quality-rb-shove-20261028-01')
    parser.add_argument('--phase', choices=('pilot', 'validation'), default='pilot')
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    args = parser.parse_args()
    root = Path(args.root)
    if args.command == 'register':
        if (root / 'protocol.json').exists():
            raise ValueError('Protocolo ya existe')
        root.mkdir(parents=True, exist_ok=True)
        save(root / 'protocol.json', protocol(args.id))
        return
    plan = json.loads((root / 'protocol.json').read_text(encoding='utf-8'))
    verify(plan)
    if args.command == 'summarize':
        summarize(root, plan, args.phase)
        return
    if args.phase == 'validation':
        pilot = root / 'pilot' / 'summary.json'
        if not pilot.exists() or not json.loads(pilot.read_text())['complete']:
            raise ValueError('Completa el piloto antes de validar')
    jobs = [('cell', scenario, n, d) for scenario in plan['scenarios'] for n in plan['players'] for d in plan['depths_bb']]
    jobs += [('session', scenario, n, g) for scenario in plan['session']['scenarios'] for n in plan['players']
             for g in range(plan['phases'][args.phase]['session_groups'])]
    for index, (kind, scenario, players, number) in enumerate(jobs):
        if index % args.shards != args.shard:
            continue
        (cell if kind == 'cell' else sessions)(root, plan, args.phase, scenario, players, number)


if __name__ == '__main__':
    main()

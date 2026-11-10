"""Audit duplicate deals and replay a preselected set of real campaign hands.

Replays are technical checks and never counted as new evaluation observations.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from pokerfight.arena import play_hand
from pokerfight.campaign import save
from scripts.competition_experiment import (BASE, check_artifact, jobs, job_name,
                                           load_plan, policies, table_key, verify)


def without_times(trace):
    return [{"observation": r["observation"], "decision": {k: v for k, v in r["decision"].items() if k != "elapsed_ms"}} for r in trace]


def audit(root: Path, replay: bool = False) -> dict:
    plan, digest = load_plan(root)
    verify(plan)
    count, reset_groups, session_groups, replays = 0, 0, 0, 0
    deck_seeds = set()
    cell_rows = []
    for job in jobs(plan):
        report = json.loads((root / (job_name(job) + ".json")).read_text(encoding="utf-8"))
        check_artifact(root, plan, digest, job, report)
        records = [json.loads(s) for s in (root / (job_name(job) + ".jsonl")).read_text(encoding="utf-8").splitlines()]
        if len(records) != report["executions"]:
            raise ValueError("Execution count mismatch")
        count += len(records)
        for r in records:
            if sum(r["payoffs"].values()) != 0 or min(r["stacks"].values()) < 0:
                raise ValueError("Chips not conserved")
            deck_seeds.add(r["deck_seed"])
        if job[0] == "reset":
            groups = defaultdict(list)
            for r in records:
                groups[(r["block"], r["rotation"])].append(r)
            for paired in groups.values():
                if len(paired) != len(plan["arms"]) or {r["variant"] for r in paired} != set(plan["arms"]):
                    raise ValueError("Incomplete paired arms")
                for field in ("deck_seed", "policy_seeds", "seats"):
                    if len({json.dumps(r[field], sort_keys=True) for r in paired}) != 1:
                        raise ValueError(f"Pairing error: {field}")
            reset_groups += len(groups)
            for v in plan["arms"]:
                selected = [r for r in records if r["variant"] == v]
                reconstructed = [statistics.mean(r["payoffs"]["hero"] / 100 for r in selected if r["block"] == b) for b in range(plan["blocks"])]
                if reconstructed != report["block_bb_per_hand"][v]:
                    raise ValueError("Payoff aggregation mismatch")
                row = {"scenario": job[1], "players": job[2], "depth_bb": job[3], "variant": v,
                       "bb_per_hand": statistics.mean(reconstructed),
                       "delta_v2": statistics.mean(a - b for a, b in zip(reconstructed, report["block_bb_per_hand"]["v2"], strict=True)),
                       "bust_hands": report["bust_hands"][v], "executions": len(selected)}
                cell_rows.append(row)
                if replay:
                    # Chosen before results: block zero, rotation zero, every arm,
                    # every external cell. No picking only winners or outliers.
                    original = next(r for r in selected if r["block"] == r["rotation"] == 0)
                    if job[1].startswith("external"):
                        pp = policies(plan, v, report["opponents"], original["policy_seeds"])
                        result = play_hand(pp, tuple(original["seats"]), dict.fromkeys(original["seats"], job[3] * 100),
                                           original["deck_seed"], "0", table_key(_base_seed(plan, job), 0, "reset"), trace_player_id="hero")
                        if result.payoffs != original["payoffs"] or without_times(result.trace) != without_times(original["trace"]):
                            raise ValueError("Exact replay differs (possibly a timed-out decision)")
                        replays += 1
        else:
            by_hand = defaultdict(list)
            for r in records:
                by_hand[r["hand"]].append(r)
            if any(len({r["deck_seed"] for r in rows}) != 1 for rows in by_hand.values()):
                raise ValueError("Session chance not shared by hand index and rotation")
            first = [r for r in records if r["hand"] == 0]
            if len(first) != job[2] * len(plan["arms"]):
                raise ValueError("Missing initial session rotations")
            session_groups += 1
    # Previously observed decks must not re-enter this campaign. Ignore source
    # snapshots (no result traces) and this campaign's own files.
    historical_decks = set()
    for path in (BASE / "results").rglob("*.jsonl"):
        if root.resolve() in path.resolve().parents:
            continue
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if "deck_seed" in r:
                historical_decks.add(r["deck_seed"])
    if deck_seeds & historical_decks:
        raise ValueError("Deck seeds overlap an earlier campaign")
    result = {"protocol_sha256": digest, "real_hand_executions_checked": count,
              "reset_paired_seat_groups": reset_groups, "session_seed_groups": session_groups,
              "unique_hand_index_seeds": len(deck_seeds), "historical_seed_overlap": 0,
              "technical_replays_not_new_observations": replays, "cells": cell_rows}
    save(root / "audit.json", result)
    return result


def _base_seed(plan, job):
    from pokerfight.arena import seed_for
    return seed_for(plan["experiment_id"], "crossplay-reset-01", job[1], job[2], job[3])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/competition_2026-10-28"))
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    result = audit(args.root, args.replay)
    print(json.dumps({k: v for k, v in result.items() if k != "cells"}, indent=2))


if __name__ == "__main__":
    main()

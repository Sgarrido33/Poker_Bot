"""Independent audit addendum for a registered stage-two cross-play batch.

This supplements the registered and session auditors. It checks exact reset
coverage and reconstruction, reports fixed-horizon session outcomes with table
completion treated as a competing event, and replays preselected stage-two rows.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics

from pokerfight.arena import play_hand, seed_for
from pokerfight.campaign import save
from pokerfight.evaluation import lineup
from research.competition_audit_20261028.audit_sessions import canonical_trace
from research.competition_audit_20261028 import audit_sessions
from scripts import audit_competition as registered_audit
from scripts.competition_experiment import (check_artifact, job_name, load_plan,
                                           jobs as campaign_jobs, policies, table_key, verify)


def expected_reset(plan: dict, job: tuple, records: list[dict], report: dict) -> dict:
    """Validate and reconstruct one reset artifact from its hand rows."""
    _, scenario, players, depth = job
    ids, kinds = lineup(players, tuple(plan["scenarios"][scenario]))
    base = seed_for(plan["experiment_id"], "crossplay-reset-01", scenario, players, depth)
    arms = tuple(plan["arms"])
    expected_keys = {(b, r, v) for b in range(plan["blocks"])
                     for r in range(players) for v in arms}
    indexed = {}
    for row in records:
        key = (row["block"], row["rotation"], row["variant"])
        if key in indexed:
            raise ValueError("Duplicate reset block/rotation/arm pair")
        indexed[key] = row
    if set(indexed) != expected_keys:
        raise ValueError("Reset block/rotation/arm coverage mismatch")
    profits = {v: defaultdict(list) for v in arms}
    busts = Counter()
    counts = {v: Counter() for v in arms}
    reasons = {v: Counter() for v in arms}
    actions = {v: Counter() for v in arms}
    for (block, rotation, variant), row in indexed.items():
        seats = list(ids[rotation:] + ids[:rotation])
        policy_seeds = {pid: seed_for(base, "policy", block, rotation, pid) for pid in ids}
        deck_seed = seed_for(base, "deck", block)
        if row["seats"] != seats or row["policy_seeds"] != policy_seeds:
            raise ValueError("Reset seat or policy seed mismatch")
        # Compare decoded JSON scalars exactly, including the seed's numeric type.
        if type(row["deck_seed"]) is not int or row["deck_seed"] != deck_seed:
            raise ValueError("Reset deck seed mismatch")
        if set(row["payoffs"]) != set(ids) or set(row["stacks"]) != set(ids):
            raise ValueError("Reset active seat set mismatch")
        initial = depth * 100
        if any(row["payoffs"][pid] != row["stacks"][pid] - initial for pid in ids):
            raise ValueError("Reset stack transition mismatch")
        if sum(row["payoffs"].values()) != 0 or min(row["stacks"].values()) < 0:
            raise ValueError("Reset chip conservation failure")
        profits[variant][block].append(row["payoffs"]["hero"] / 100)
        busts[variant] += row["stacks"]["hero"] == 0
        counts[variant].update(row["counts"])
        reasons[variant].update(row["reasons"])
        actions[variant].update(row["hero_actions"])
    reconstructed = {v: [statistics.mean(profits[v][b]) for b in range(plan["blocks"])] for v in arms}
    if reconstructed != report["block_bb_per_hand"]:
        raise ValueError("Reset block gains differ from report")
    if dict(busts) != report["bust_hands"]:
        raise ValueError("Reset bust counts differ from report")
    for key, values in (("counts", counts), ("reasons", reasons), ("hero_actions", actions)):
        normalized = {v: dict(values[v]) for v in arms}
        if normalized != report[key]:
            raise ValueError(f"Reset {key} differ from report")
    if len(records) != report["executions"]:
        raise ValueError("Reset execution count mismatch")
    return {"groups": len(expected_keys) // len(arms), "records": len(records),
            "block_bb_per_hand": reconstructed, "bust_hands": dict(busts),
            "counts": {v: dict(counts[v]) for v in arms}}


def fixed_horizon_elimination(plan: dict, session_jobs: list[dict]) -> dict:
    """Count elimination, observed win, alive-at-horizon, and early censoring.

    A completed table with hero alive is an observed competing win, never a
    censored survivor. Horizons are capped by the registered session limit.
    """
    configured = (24, 64, 128, 256)
    limit = plan["session"]["hand_limit"]
    horizons = tuple(h for h in configured if h <= limit)
    if limit not in horizons:
        horizons = tuple(sorted((*horizons, limit)))
    by_variant = {v: {h: Counter() for h in horizons} for v in plan["arms"]}
    total = {v: 0 for v in plan["arms"]}
    for artifact in session_jobs:
        _mode, scenario, players, _group = artifact["job"]
        ids, _ = lineup(players, tuple(plan["scenarios"][scenario]))
        grouped = defaultdict(list)
        for row in artifact["records"]:
            grouped[(row["variant"], row["rotation"])].append(row)
        for (variant, _rotation), rows in grouped.items():
            rows.sort(key=lambda r: r["hand"])
            total[variant] += 1
            eliminated_at = None
            finished_at = None
            stacks = dict.fromkeys(ids, plan["session"]["starting_stack"])
            for row in rows:
                # Later hands omit eliminated seats. Carry their zero stacks
                # forward so table completion and hero elimination remain
                # reconstructible from each partial hand result.
                stacks.update(row["stacks"])
                if stacks["hero"] == 0 and eliminated_at is None:
                    eliminated_at = row["hand"]
                if sum(s > 0 for s in stacks.values()) == 1:
                    finished_at = row["hand"]
                    break
            for requested in horizons:
                horizon = min(requested, limit)
                out = by_variant[variant][requested]
                if eliminated_at is not None and eliminated_at < horizon:
                    out["eliminated"] += 1
                elif finished_at is not None and finished_at < horizon:
                    out["table_finished_hero_alive"] += 1
                elif len(rows) >= horizon and (eliminated_at is None or eliminated_at >= horizon):
                    out["alive_through_horizon"] += 1
                else:
                    out["censored_before_horizon"] += 1
    return {v: {str(requested): {**dict(by_variant[v][requested]), "tables": total[v],
                                 "effective_horizon": requested,
                                 "elimination_fraction_of_tables": by_variant[v][requested]["eliminated"] / total[v]
                                 if total[v] else None}
                for requested in horizons} for v in by_variant}


def _compare_replay(result, row):
    return (result.payoffs == row["payoffs"] and result.stacks == row["stacks"]
            and list(result.board) == row["board"]
            and [__import__("dataclasses").asdict(e) for e in result.history] == row["history"]
            and canonical_trace(result.trace) == canonical_trace(row["trace"]))


def replay_stage2(root: Path, plan: dict, jobs: list[tuple]) -> dict:
    """Replay external_diverse group/reset strata selected before outcomes."""
    # The registered auditor's `startswith("external")` selector already
    # replays all external_diverse reset cells at block 0 / rotation 0.
    # Replay those hands only once; this addendum supplies the diverse sessions.
    reset_hands = session_hands = 0
    for job in jobs:
        name = job_name(job)
        if job[0] == "session" and job[1] == "external_diverse" and job[3] == 0:
            report = json.loads((root / (name + ".json")).read_text(encoding="utf-8"))
            records = [json.loads(line) for line in (root / (name + ".jsonl")).read_text(encoding="utf-8").splitlines()]
            _, kinds = lineup(job[2], tuple(plan["scenarios"][job[1]]))
            base = seed_for(plan["experiment_id"], "crossplay-session-01", job[1], job[2], 0)
            for variant in plan["arms"]:
                selected = sorted((r for r in records if r["variant"] == variant and r["rotation"] == 0),
                                  key=lambda r: r["hand"])
                if not selected:
                    raise ValueError("Missing stage-two session replay rows")
                pp = policies(plan, variant, kinds, selected[0]["policy_seeds"])
                stacks = dict.fromkeys(selected[0]["seats"], plan["session"]["starting_stack"])
                for row in selected:
                    result = play_hand(pp, tuple(row["seats"]), stacks, row["deck_seed"], str(row["hand"]),
                                       table_key(base, 0, "session"), plan["session"]["small_blind"],
                                       plan["session"]["big_blind"], plan["session"]["ante"],
                                       trace_player_id="hero")
                    if not _compare_replay(result, row):
                        raise ValueError("Stage-two session exact replay differs")
                    stacks.update(result.stacks)
                    session_hands += 1
    return {"reset_replay_hands": reset_hands, "session_replay_hands": session_hands,
            "total_replay_hands": reset_hands + session_hands,
            "reset_replay_selection": "Covered once by registered auditor: external_diverse block 0 / rotation 0, each arm, format, and depth.",
            "session_replay_selection": "external_diverse group 0 / rotation 0, each arm and format."}


def audit(root: Path, replay: bool = False) -> dict:
    # Run the two established corrected auditors first; they keep their own
    # result files and their replay selection remains unchanged.
    plan, digest = load_plan(root)
    verify(plan)
    snapshot = root / "source"
    for name, expected_hash in plan["sources"].items():
        source_copy = snapshot / name
        if not source_copy.is_file() or hashlib.sha256(source_copy.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"Registered source snapshot mismatch: {name}")
    registered_audit.without_times = canonical_trace
    registered = registered_audit.audit(root, replay)
    sessions = audit_sessions.audit(root, replay)
    all_jobs = campaign_jobs(plan)
    reset_checked, all_records, session_artifacts = 0, [], []
    deck_seeds = set()
    for job in all_jobs:
        name = job_name(job)
        report = json.loads((root / (name + ".json")).read_text(encoding="utf-8"))
        check_artifact(root, plan, digest, job, report)
        records = [json.loads(line) for line in (root / (name + ".jsonl")).read_text(encoding="utf-8").splitlines()]
        deck_seeds.update(row["deck_seed"] for row in records)
        if job[0] == "reset":
            expected_reset(plan, job, records, report)
            reset_checked += 1
        else:
            session_artifacts.append({"job": job, "records": records})
        all_records.extend(records)
    historical = set()
    base_results = Path(__file__).resolve().parents[1] / "results"
    for path in base_results.rglob("*.jsonl"):
        if root.resolve() in path.resolve().parents:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "deck_seed" in value:
                historical.add(value["deck_seed"])
    overlap = deck_seeds & historical
    if overlap:
        raise ValueError("Stage-two deck seeds overlap historical results")
    new_replays = replay_stage2(root, plan, all_jobs) if replay else {
        "reset_replay_hands": 0, "session_replay_hands": 0, "total_replay_hands": 0}
    old_replays = registered.get("technical_replays_not_new_observations", 0) + sessions.get("technical_replay_hands_not_new_observations", 0)
    result = {"protocol_sha256": digest,
              "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "auditors_run_first": {"registered": True, "sessions": True},
              "registered_audit_replays": registered.get("technical_replays_not_new_observations", 0),
              "session_audit_replay_hands": sessions.get("technical_replay_hands_not_new_observations", 0),
              "reset_artifacts_fully_reconstructed": reset_checked,
              "session_artifacts_reconstructed": sessions["session_tables_reconstructed"],
              "unique_deck_seeds": len(deck_seeds), "historical_deck_seed_overlap": len(overlap),
              "stage2_preselected_replays": new_replays,
              "all_technical_replay_hands_not_new_observations": old_replays + new_replays["total_replay_hands"],
              "fixed_horizon_elimination_competing_outcomes": fixed_horizon_elimination(plan, session_artifacts)}
    save(root / "stage2_audit.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/competition_stage2"))
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.root, args.replay), indent=2))


if __name__ == "__main__":
    main()

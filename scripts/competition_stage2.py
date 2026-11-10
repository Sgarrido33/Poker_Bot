"""Second local cross-play: technical pilot first, sealed comparison afterwards.

Reuses the audited deal/session executor. All quantities are selected before
candidate outcomes exist. No policy tuning or automatic promotion is allowed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics

from pokerfight.arena import seed_for
from pokerfight.campaign import save
from pokerfight.external_opponents import verify_honest
from scripts import competition_experiment as old

SCENARIOS = {**old.SCENARIOS, "copies_v2_4000": ["v2_4000"],
             "external_diverse": ["fullhouse", "honest", "v2_4000", "pressure", "fullhouse"]}
SESSION_SCENARIOS = ["pressure", "copies_v2", "external_mix", "copies_v2_4000", "external_diverse"]


def protocol(identifier, phase, pilot=None):
    plan = old.protocol(identifier)
    plan.update(stage=2, phase=phase, external_honest=verify_honest(),
                scenarios=SCENARIOS, blocks=8)
    plan["rival_quotas"].update(v2_4000="4000 equity worlds, 1600ms; explicit fixed rival kind",
                               honest="1000 uniform Monte Carlo deals per decision; no clock cutoff; fold/call only")
    plan["execution"] = {"workers": 4, "technical_failure": "Any fallback or clock truncation invalidates inference; no outcome-dependent reruns."}
    plan["limitations"] = [
        "Two independently authored external policies, but HonestPlayer is an educational fold/call baseline, not a trained competitive bot.",
        "NoRegrets source inspected; no published blueprint, Rust toolchain absent, no trained NoRegrets opponent integrated.",
        "HonestPlayer adapted with Eval7 and isolated RNG; not the unmodified PyPokerEngine runtime.",
        "Fullhouse trained for six seats; five and eliminated tables are transfer.",
        "Fixed local 50/100 blinds, no ante/rebuys; official tournament conditions unknown.",
        "Cyclic rotations are clustered by complete seed group, not independent tables or all rival permutations.",
        "Shared decks by hand index do not preserve player-to-card identity after different eliminations.",
        "Four session groups per scenario/format and eight reset blocks per cell give fragile approximate intervals.",
        "Hero v2 uses 4000 samples; candidates 4096 and more wall time. Rival quotas fixed between arms.",
        "Censored leaders receive neither victory nor final rank. No tournament win probability inferred."]
    if phase == "pilot":
        plan.update(arms=["v2"], depths_bb=[], blocks=0,
                    scenarios={s: SCENARIOS[s] for s in ("external_mix", "copies_v2_4000", "external_diverse")})
        plan["session"].update(scenarios=list(plan["scenarios"]), groups=1, hand_limit=128)
        plan["pilot_selection"] = {
            "horizons": [64, 128], "target_table_censoring": .25,
            "rule": "Choose smallest horizon with <=25% unfinished tables overall and <=35% in each player format; otherwise 128 and report unmet target.",
            "scope": "Technical v2-only pilot. Never compare candidates or use chip gains to choose length.",
            "main_quantities": "8 reset blocks/cell, 4 session groups/stratum, all cyclic rotations, four arms; fixed before pilot."}
    elif phase == "comparison":
        if not pilot or pilot.get("phase") != "pilot" or not pilot.get("complete"):
            raise ValueError("A completed technical pilot is required")
        plan["session"].update(scenarios=SESSION_SCENARIOS, groups=4, hand_limit=pilot["selected_hand_limit"])
        plan["pilot_evidence"] = pilot
    else:
        raise ValueError("Invalid phase")
    plan["inference"].update(comparisons=6,
        interval="99.1667% percentile intervals for six co-primary comparisons (three candidates x chips/elimination); approximate, small clusters.")
    plan["primary"] = "Equal-weight external_diverse session contrasts vs v2: final chips/800 (higher) AND bust incidence by selected horizon (lower)."
    plan["criteria"] = {
        "technical": "All registered jobs complete; zero fallbacks, illegal actions, chip errors and equity/search deadlines; audits pass.",
        "followup": "Both co-primary intervals strictly favorable: chips lower >0 AND bust probability upper <0, with nonnegative chip deltas in both formats. Screening only.",
        "default": "Always retain v2. No automatic promotion or claim about the official tournament.",
        "stopping": "Run entire registered matrix. Do not modify policies, quantities or criteria after outcomes. Technical faults invalidate inference."}
    plan["metrics"] = {
        "elimination": "Cumulative observed hero bust incidence by h, h=24,64,H where <=H; tournament win is a competing absorbing outcome, not a bust or censor.",
        "unresolved": "Neither bust nor observed sole-survivor victory by h; includes administrative censoring at H.",
        "chips": "Final observed hero stack /800 even for administratively censored tables; not prize equity or final rank.",
        "independence": "Mean paired rotation differences within seed group, then equal-weight scenario/format strata; bootstrap whole groups.",
        "secondary": "Reset bb/hand, legacy fields and all scenario/horizon contrasts are diagnostics, not separately confirmatory."}
    return plan


def register(root, identifier, phase, pilot_root=None):
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty output directory")
    pilot = None
    if phase == "comparison":
        if pilot_root is None:
            raise ValueError("--pilot-root is required")
        pilot = summarize_pilot(pilot_root)
        pilot["summary_sha256"] = hashlib.sha256((pilot_root / "pilot_summary.json").read_bytes()).hexdigest()
        pilot["root"] = str(pilot_root.resolve())
    plan = protocol(identifier, phase, pilot)
    root.mkdir(parents=True, exist_ok=True)
    for name in plan["sources"]:
        dst = root / "source" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((old.BASE / name).read_bytes())
    save(root / "protocol.json", plan)
    (root / "protocol.sha256").write_text(hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest(), encoding="ascii")
    seed_check(root, plan)


def seed_check(root, plan):
    planned = set()
    for mode, s, n, k in old.jobs(plan):
        if mode == "reset":
            base = seed_for(plan["experiment_id"], "crossplay-reset-01", s, n, k)
            planned.update(seed_for(base, "deck", b) for b in range(plan["blocks"]))
        else:
            base = seed_for(plan["experiment_id"], "crossplay-session-01", s, n, k)
            planned.update(seed_for(base, "deck", h) for h in range(plan["session"]["hand_limit"]))
    historical = set()
    for p in (old.BASE / "results").rglob("*.jsonl"):
        if root.resolve() in p.resolve().parents:
            continue
        with p.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if "deck_seed" in row:
                    historical.add(row["deck_seed"])
    if planned & historical:
        raise ValueError("Planned decks overlap previous data")
    save(root / "seed_check.json", {"planned_unique_decks": len(planned), "historical_unique_decks": len(historical), "overlap": 0})


def run(root, workers):
    plan, digest = old.load_plan(root)
    if workers != plan["execution"]["workers"]:
        raise ValueError("Worker count differs from registration")
    old.verify(plan)
    # Shards execute disjoint complete jobs and never share mutable bot state.
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(old.run, root, plan, digest, i, workers) for i in range(workers)]
        for f in futures:
            f.result()


def reports(root, plan, digest):
    rows = []
    for job in old.jobs(plan):
        path = root / (old.job_name(job) + ".json")
        if not path.exists():
            raise ValueError(f"Incomplete campaign: {path.name}")
        row = json.loads(path.read_text(encoding="utf-8"))
        old.check_artifact(root, plan, digest, job, row)
        rows.append(row)
    return rows


def events(row, horizon):
    bust = "hero" in row["eliminated_at"] and row["eliminated_at"]["hero"] + 1 <= horizon
    win = row["hero_observed_win"] and row["played_hands"] <= horizon
    return {"bust": int(bust), "win": int(win), "unresolved": int(not (bust or win)),
            "table_finished": int(row["table_finished"] and row["played_hands"] <= horizon)}


def all_counts(rows):
    counts = Counter()
    for job in rows:
        cc = job["counts"].values() if job["job"][0] == "reset" else (r["counts"] for r in job["sessions"])
        for c in cc:
            counts.update(c)
    return counts


def summarize_pilot(root):
    plan, digest = old.load_plan(root)
    old.verify(plan)
    if plan["phase"] != "pilot":
        raise ValueError("Expected pilot")
    rows = reports(root, plan, digest)
    sessions = [(j["job"][2], r) for j in rows for r in j["sessions"]]
    counts = all_counts(rows)
    if any(counts[k] for k in ("fallbacks", "equity_deadlines", "search_deadlines")):
        raise ValueError("Technical pilot failed")
    horizons = {}
    selected = None
    for h in plan["pilot_selection"]["horizons"]:
        rates = {str(n): statistics.mean(1 - events(r, h)["table_finished"] for nn, r in sessions if nn == n) for n in plan["players"]}
        rate = statistics.mean(1 - events(r, h)["table_finished"] for _, r in sessions)
        passed = rate <= .25 and all(v <= .35 for v in rates.values())
        horizons[str(h)] = {"unfinished_fraction": rate, "by_players": rates, "target_met": passed}
        if passed and selected is None:
            selected = h
    result = {"phase": "pilot", "complete": True, "protocol_sha256": digest,
              "technical_hand_executions_not_evaluation": sum(j["executions"] for j in rows),
              "tables": len(sessions), "counts": counts, "horizons": horizons,
              "selected_hand_limit": selected or 128, "target_met": selected is not None,
              "policy_comparisons_observed": False}
    save(root / "pilot_summary.json", result)
    return result


def summarize(root):
    plan, digest = old.load_plan(root)
    old.verify(plan)
    if plan["phase"] == "pilot":
        return summarize_pilot(root)
    rows = reports(root, plan, digest)
    cells = [j for j in rows if j["job"][0] == "reset"]
    sj = [j for j in rows if j["job"][0] == "session"]
    counts = all_counts(rows)
    safety = not any(counts[k] for k in ("fallbacks", "equity_deadlines", "search_deadlines"))
    horizon = plan["session"]["hand_limit"]
    contrasts = {}
    for v in plan["arms"][1:]:
        by_scenario = {}
        for s in plan["scenarios"]:
            reset = old.describe(old.paired_reset([c for c in cells if c["job"][1] == s], v), (v, s, "reset"), plan)
            ss = [j for j in sj if j["job"][1] == s]
            entry = {"reset_delta_bb_per_hand": reset}
            if ss:
                entry["final_stack_fraction_delta"] = old.describe(old.paired_sessions(ss, v, lambda r: r["last_stacks"]["hero"] / 800), (v, s, "chips"), plan)
                entry["by_horizon"] = {str(h): {m: old.describe(old.paired_sessions(ss, v, lambda r: events(r, h)[m]), (v, s, h, m), plan)
                                               for m in ("bust", "win", "unresolved", "table_finished")}
                                       for h in sorted({24, 64, horizon}) if h <= horizon}
            by_scenario[s] = entry
        primary = by_scenario["external_diverse"]
        chips = primary["final_stack_fraction_delta"]["interval_family_adjusted"]
        bust = primary["by_horizon"][str(horizon)]["bust"]["interval_family_adjusted"]
        formats = {str(n): old.describe(old.paired_sessions([j for j in sj if j["job"][1] == "external_diverse" and j["job"][2] == n], v,
                             lambda r: r["last_stacks"]["hero"] / 800), (v, n, "chips"), plan)["mean"] for n in plan["players"]}
        contrasts[v] = {"by_scenario": by_scenario, "primary_chip_delta_by_players": formats,
                        "passes_followup_screen": bool(safety and chips and bust and chips[0] > 0 and bust[1] < 0 and all(d >= 0 for d in formats.values()))}
    descriptive = {}
    for s in plan["session"]["scenarios"]:
        descriptive[s] = {}
        for v in plan["arms"]:
            rr = [r for j in sj if j["job"][1] == s for r in j["sessions"] if r["variant"] == v]
            descriptive[s][v] = {"tables": len(rr), "mean_final_stack": statistics.mean(r["last_stacks"]["hero"] for r in rr),
                "played_hands": sum(r["played_hands"] for r in rr),
                "by_horizon": {str(h): dict(Counter({m: sum(events(r, h)[m] for r in rr) for m in events(rr[0], h)}))
                               for h in sorted({24, 64, horizon}) if h <= horizon}}
    output = {"complete": True, "phase": "comparison", "protocol_sha256": digest,
        "reset_hand_executions": sum(j["executions"] for j in cells), "session_hand_executions": sum(j["executions"] for j in sj),
        "reset_independent_blocks": len(cells) * plan["blocks"], "session_independent_seed_groups": len(sj),
        "all_policy_counts": counts, "technical_counts_passed": safety, "contrasts": contrasts,
        "session_descriptive": descriptive, "default": "v2", "promotion_allowed": False,
        "limitations": plan["limitations"], "interval_warning": "Six co-primary contrasts adjusted; other intervals descriptive. Four seed groups per stratum is a small sample."}
    save(root / "summary.json", output)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("register", "run", "summarize"))
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--id", default="crossplay-stage2-20261028-02")
    p.add_argument("--phase", choices=("pilot", "comparison"), default="comparison")
    p.add_argument("--pilot-root", type=Path)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    if a.command == "register":
        register(a.root, a.id, a.phase, a.pilot_root)
    elif a.command == "run":
        run(a.root, a.workers)
    else:
        out = summarize(a.root)
        print(json.dumps({k: v for k, v in out.items() if k not in ("contrasts", "session_descriptive")}, indent=2))


if __name__ == "__main__":
    main()

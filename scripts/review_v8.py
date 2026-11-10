"""Read-only audit of historical v8 sessions; generates no new poker evidence.

Run from the repository root: python -m scripts.review_v8 --output PATH.json
The output is created exclusively so an earlier audit cannot be overwritten.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np

from pokerfight.domain import LegalActions, Observation, Player, PublicAction
from pokerfight.pushfold import _nearest, range_percent
from pokerfight.pushfold_bot import chart_action


ROOT = Path(__file__).resolve().parents[1]
METRICS = ("final_chips", "wins", "elim_24", "elim_128")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(rows):
    return np.array([[r["final"], r["won"],
                      r["eliminated_at"] is not None and r["eliminated_at"] < 24,
                      r["eliminated_at"] is not None] for r in rows], dtype=float).mean(axis=0)


def load_batch(name, arms):
    path = ROOT / "results" / name / "sessions.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    grouped = defaultdict(lambda: defaultdict(list))
    keys = set()
    for r in rows:
        n = r["players"]
        key = (r["scenario"], n, r["group"], r["rotation"], r["variant"])
        assert key not in keys, ("duplicate", key)
        keys.add(key)
        assert n in (5, 6) and 0 <= r["rotation"] < n
        assert r["variant"] in arms and 0 <= r["final"] <= 800 * n
        assert 1 <= r["played"] <= 128
        assert (r["final"] == 0) == (r["eliminated_at"] is not None)
        assert not r["won"] or r["final"] == 800 * n
        assert r["final"] != 800 * n or r["won"]
        assert r["eliminated_at"] is None or 0 <= r["eliminated_at"] < r["played"]
        grouped[(r["scenario"], n, r["group"])][r["variant"]].append(r)
    for (s, n, g), variants in grouped.items():
        assert set(variants) == set(arms), ("incomplete arms", s, n, g)
        for rs in variants.values():
            assert len(rs) == n and {r["rotation"] for r in rs} == set(range(n))
    return rows, grouped, {"path": str(path.relative_to(ROOT)), "sha256": digest(path),
                           "rows": len(rows), "groups": len(grouped),
                           "reported_hero_fallbacks": sum(r["reasons"].get("fallback", 0) for r in rows)}


def contrast(grouped, scenario, candidate, control):
    strata = {}
    for n in (5, 6):
        pairs = [(values(v[candidate]), values(v[control]))
                 for (s, players, g), v in sorted(grouped.items()) if s == scenario and players == n]
        assert pairs
        a, b = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        strata[n] = (a, b, a - b)
    rng = np.random.default_rng(20261030)
    replicates = []
    for a, b, d in strata.values():
        replicates.append(d[rng.integers(0, len(d), (20000, len(d)))].mean(axis=1))
    ci = np.quantile(np.mean(replicates, axis=0), [.025, .975], axis=0)
    report = {}
    for i, metric in enumerate(METRICS):
        report[metric] = {
            candidate: float(np.mean([a[:, i].mean() for a, b, d in strata.values()])),
            control: float(np.mean([b[:, i].mean() for a, b, d in strata.values()])),
            "diff": float(np.mean([d[:, i].mean() for a, b, d in strata.values()])),
            "ci95_stratified_descriptive": ci[:, i].tolist(),
            "by_players": {str(n): {"groups": len(d), "diff": float(d[:, i].mean()),
                                    "sd_group_diff": float(d[:, i].std(ddof=1))}
                           for n, (a, b, d) in strata.items()},
        }
    return report


def deep_reshove_probe():
    obs = Observation("review", "probe", "hero", 0,
        (Player("btn", 550, 250, 250), Player("hero", 9950, 50, 50), Player("bb", 9900, 100, 100)),
        ("As", "Ad"), (), 100, LegalActions(False, True, 200, 400, 10000),
        (PublicAction("0", "btn", "preflop", "raise_to", 250, True),))
    action, reason = chart_action(obs)
    assert action.is_legal(obs) and action.amount == 10000 and reason == "v8:reshove:8.0bb"
    return {"hero_total_bb": 100, "raiser_total_bb": 8, "other_opponent_total_bb": 100,
            "action": action.to_dict(), "reason": reason,
            "interpretation": "8 bb chart selects a 100 bb commitment against the remaining deep opponent"}


def skipped_observation_probe():
    from pokerfight.arena import make_policy
    from pokerfight.strategy import BotConfig
    bot = make_policy("v8", BotConfig(samples=128), 1)
    obs = Observation("review", "observe", "hero", 0,
        (Player("btn", 800, 0, 0, True), Player("hero", 750, 50, 50), Player("bb", 700, 100, 100)),
        ("As", "Ad"), (), 100, LegalActions(False, True, 50, 200, 800),
        (PublicAction("0", "btn", "preflop", "fold", 0, False),))
    decision = bot.decide(obs)
    assert decision.reason.startswith("v8:first_in_shove")
    assert not bot.model.counts
    return {"reason": decision.reason, "observed_model_entries": len(bot.model.counts),
            "interpretation": "chart decisions bypass the inherited v2 model.observe; history is only ingested on delegation"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    batches = {}
    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "historical reanalysis and deterministic probes, zero new poker sessions",
              "inputs": {}, "contrasts": {}}
    specs = {"v8_sessions_2026-10-29": ("v2", "v8"),
             "v8_replication_2026-10-29": ("v2", "v8", "v8b"),
             "v8c_2026-10-29": ("v8", "v8c")}
    for name, arms in specs.items():
        rows, groups, audit = load_batch(name, arms)
        batches[name] = (rows, groups)
        report["inputs"][name] = audit
        candidate, control = ("v8c", "v8") if name.startswith("v8c") else ("v8", "v2")
        original_path = ROOT / "results" / name / ("summary_v8_vs_v2.json" if "replication" in name else "summary.json")
        original = json.loads(original_path.read_text(encoding="utf-8"))
        entries = {}
        for scenario in sorted({r["scenario"] for r in rows}):
            entry = contrast(groups, scenario, candidate, control)
            for metric in METRICS:
                for key in (candidate, control, "diff"):
                    assert abs(entry[metric][key] - original[scenario][metric][key]) < .000051
            entry["alive_without_completed_win"] = {
                variant: float(np.mean([np.mean([r["final"] > 0 and not r["won"] for r in rows
                                                   if r["scenario"] == scenario and r["players"] == n and r["variant"] == variant])
                                        for n in (5, 6)]))
                for variant in (candidate, control)}
            entries[scenario] = entry
        report["contrasts"][name] = entries
    # Pool old data descriptively, retaining batch and table-size strata.
    pooled = {}
    for batch_id, name in enumerate(list(specs)[:2]):
        for (s, n, g), v in batches[name][1].items():
            if s == "external_diverse":
                pooled[(s, n, (batch_id, g))] = v
    pooled_report = contrast(pooled, "external_diverse", "v8", "v2")
    report["pooled_external_descriptive"] = pooled_report
    # Approximate planning only: two two-sided comparisons, Bonferroni FWER .05, power .8.
    zsum = NormalDist().inv_cdf(1 - .05 / (2 * 2)) + NormalDist().inv_cdf(.8)
    sizes = {}
    for metric, effects in {"final_chips": (80, 160, 240), "wins": (.05, .10), "elim_24": (.05, .10)}.items():
        s2sum = sum(pooled_report[metric]["by_players"][str(n)]["sd_group_diff"] ** 2 for n in (5, 6))
        sizes[metric] = {str(effect): int(np.ceil(zsum ** 2 * s2sum / (4 * effect ** 2))) for effect in effects}
    report["planning_groups_per_format"] = {"assumptions": "normal approximation; historical v8-v2 variance; superiority vs zero; NOT power for v8-v4rb or noninferiority", "sizes": sizes}
    report["probes"] = {"deep_reshove": deep_reshove_probe(), "skipped_model_observation": skipped_observation_probe()}
    report["chart_rounding"] = {
        str(s): {str(p): {"frequency_weighted_range": range_percent(_nearest(s)["shove"][str(p)]),
                          "actual_threshold_range": range_percent([float(f >= .5) for f in _nearest(s)["shove"][str(p)]]),
                          "classes_with_intermediate_frequency": sum(.05 < f < .95 for f in _nearest(s)["shove"][str(p)])}
                 for p in (0, 3, 4)} for s in (5, 8, 10, 15)}
    tight = batches["v8c_2026-10-29"][1]
    mismatches = {key: [] for key in ("final", "eliminated_at", "won", "played")}
    for (s, n, g), v in sorted(tight.items()):
        if s != "copies_v2":
            continue
        for a, b in zip(sorted(v["v8"], key=lambda r: r["rotation"]), sorted(v["v8c"], key=lambda r: r["rotation"])):
            for key in mismatches:
                if a[key] != b[key]:
                    mismatches[key].append({"players": n, "group": g, "rotation": a["rotation"],
                                            "v8": a[key], "v8c": b[key]})
    report["v8c_tight_paired_mismatches"] = mismatches
    # Present-day hashes identify this audit, not the code used on October 29.
    paths = [*sorted((ROOT / "pokerfight").rglob("*.py")),
             ROOT / "pokerfight/data/pushfold_charts.json", ROOT / "pokerfight/data/preflop_equity.json",
             ROOT / "scripts/v8_sessions.py", Path(__file__).resolve()]
    report["current_source_sha256"] = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({"output": str(out), "integrity": report["inputs"],
                      "pooled_external": {k: v["diff"] for k, v in pooled_report.items()},
                      "planning": sizes, "probes": report["probes"]}, indent=2))


if __name__ == "__main__":
    main()

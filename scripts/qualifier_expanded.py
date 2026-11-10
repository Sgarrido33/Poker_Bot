"""Run a matched multi-policy qualifier and checkpoint every tournament."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
from statistics import mean, median

from pokerfight.strategy import BotConfig
from scripts.qualifier_pilot import FIELDS as PILOT_FIELDS
from scripts.qualifier_pilot import paired_top6, tournament


FIELDS = {
    **PILOT_FIELDS,
    "presion": ("v2", "v2", "pressure", "pressure", "lag",
                "lag", "tag", "fullhouse", "honest", "random"),
}
CONFIGS = {
    policy: (1024, 3500) if policy in ("v2mc", "v4", "v4rb", "v5", "v6", "v7") else (4000, 1600)
    for policy in ("v1", "v2", "v2mc", "v3", "v4", "v4rb", "v5", "v6", "v7", "v8", "v8b", "v8c", "v8d")
}
RIVAL_CONFIG = (512, 1600)


def run_tournament(job):
    seed, field, policy = job
    data = tournament(seed, field, policy, hero_config=BotConfig(*CONFIGS[policy]),
                      opponents=FIELDS[field], rival_config=BotConfig(*RIVAL_CONFIG))
    return {"seed": seed, "field": field, **data}


def comparison(rows, candidates):
    matched = {(row["seed"], row["field"], row["policy"]): row for row in rows}
    scenarios = sorted({(row["seed"], row["field"]) for row in rows})
    control_ranks = [matched[seed, field, "v2"]["hero_rank"] for seed, field in scenarios]
    results = {}
    for policy in candidates:
        own = [matched[seed, field, policy] for seed, field in scenarios]
        stats = paired_top6(control_ranks, (row["hero_rank"] for row in own))
        diagnostics = Counter()
        for row in own:
            diagnostics.update({key: value for key, value in row["diagnostics"].items()
                                if key != "max_decision_ms"})
        results[policy] = {
            "tournaments": len(own),
            "top6": stats["candidate_top6"],
            "only_v2": stats["control_only"],
            "only_candidate": stats["candidate_only"],
            "p_one_sided": stats["p_one_sided"],
            "wins": sum(row["hero_rank"] == 1 for row in own),
            "median_rank": median(row["hero_rank"] for row in own),
            "mean_chips": round(mean(row["hero_chips"] for row in own), 2),
            "median_chips": median(row["hero_chips"] for row in own),
            "eliminations": sum(row["hero_eliminated"] is not None for row in own),
            "qualified_after_elimination": sum(row["hero_rank"] <= 6 and row["hero_eliminated"] is not None
                                               for row in own),
            "hands": sum(table["hands"] for row in own for rnd in row["rounds"] for table in rnd["tables"]),
            "by_field": {field: {"tournaments": len(group),
                                 "top6": sum(row["hero_rank"] <= 6 for row in group),
                                 "eliminations": sum(row["hero_eliminated"] is not None for row in group)}
                         for field in FIELDS if (group := [row for row in own if row["field"] == field])},
            "rounds": [{"round": i + 1, "mean_chips": round(mean(row["rounds"][i]["stacks"]["hero"]
                                                                for row in own), 2),
                        "eliminations": sum(row["hero_eliminated"] is not None
                                            and row["hero_eliminated"][0] == i + 1 for row in own)}
                       for i in range(10)],
            "diagnostics": {**diagnostics, "max_decision_ms": max(row["diagnostics"]["max_decision_ms"]
                                                                for row in own)},
        }
    # Holm adjustment for the family of one-sided comparisons against v2.
    ordered = sorted((result["p_one_sided"], policy) for policy, result in results.items() if policy != "v2")
    adjusted = 0.0
    for i, (p, policy) in enumerate(ordered):
        adjusted = max(adjusted, min(1.0, p * (len(ordered) - i)))
        results[policy]["p_holm"] = adjusted
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=36)
    parser.add_argument("--seed", type=int, default=20261201)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--policies", nargs="+", choices=CONFIGS, default=tuple(CONFIGS))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < len(FIELDS) or args.seeds % len(FIELDS) or args.workers < 1:
        parser.error("La cantidad de semillas debe ser un múltiplo positivo del número de campos")
    if "v2" not in args.policies or len(set(args.policies)) != len(args.policies):
        parser.error("Incluye v2 y elige cada política una sola vez")

    fields = tuple(FIELDS)
    jobs = [(args.seed + i, fields[i % len(fields)], args.policies[(i + j) % len(args.policies)])
            for i in range(args.seeds) for j in range(len(args.policies))]
    plan = {"fields": FIELDS, "configs": {p: CONFIGS[p] for p in args.policies},
            "rival_config": RIVAL_CONFIG, "seed": args.seed, "seeds": args.seeds,
            "policies": args.policies}
    rendered_plan = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_dir / "plan.json"
    ledger = args.output_dir / "tournaments.jsonl"
    if plan_path.exists():
        if plan_path.read_text(encoding="utf-8") != rendered_plan:
            parser.error("El plan existente difiere. Elige otra carpeta.")
    else:
        plan_path.write_text(rendered_plan, encoding="utf-8")

    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
    done = {(row["seed"], row["field"], row["policy"]) for row in rows}
    if len(done) != len(rows) or not done.issubset(jobs):
        parser.error("La bitácora no coincide con el plan")
    pending = [job for job in jobs if job not in done]
    print(f"{len(rows)}/{len(jobs)} torneos ya registrados", flush=True)
    if pending:
        with ledger.open("a", encoding="utf-8") as log, ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_tournament, job) for job in pending]
            for future in as_completed(futures):
                row = future.result()
                print(json.dumps(row, separators=(",", ":")), file=log, flush=True)
                rows.append(row)
                if len(rows) % len(args.policies) == 0:
                    print(f"{len(rows)}/{len(jobs)} torneos", flush=True)

    report = {"plan": plan, "results": comparison(rows, args.policies)}
    (args.output_dir / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

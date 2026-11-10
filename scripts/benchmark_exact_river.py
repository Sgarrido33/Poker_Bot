"""Opt-in exact river experiment, frozen before measurements.

register saves sources and the fixed protocol; run must use that snapshot.
decide provides a standalone entry point without changing the main factory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import statistics
from time import perf_counter

from pokerfight.arena import close_policies, make_policy, play_hand, seed_for
from pokerfight.domain import LegalActions, Observation, Player, PublicAction
from pokerfight.equity import COMBOS, WeightedRange, build_ranges, estimate
from pokerfight.cards import CARD_INDEX
from pokerfight.opponents import OpponentModel
from pokerfight.river_exact import ExactRiverPolicy, estimate_river
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig, PokerBot


ROOT = Path(__file__).resolve().parents[1]
SEED = 2026102908
QUOTAS = (128, 1024, 4000)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixtures():
    obs = Observation("exact-river", "dry", "hero", 1,
        (Player("hero", 4900, 0, 100), Player("villain", 4900, 0, 100)),
        ("As", "Ah"), ("2c", "3d", "7h", "8s", "9c"), 100,
        LegalActions(True, False, 0, 100, 4900))
    cases = {
        "dry_overpair_uniform": (obs, "uniform", None),
        "dry_overpair_prior": (obs, "prior", None),
        "paired_board": (replace(obs, hand_id="paired", hole_cards=("Qd", "Jh"),
            board=("Qc", "8h", "8s", "3c", "2d")), "prior", None),
        "four_flush": (replace(obs, hand_id="flush", hole_cards=("Ah", "Tc"),
            board=("Kh", "Qh", "7h", "2h", "3s")), "prior", None),
        "royal_board": (replace(obs, hand_id="royal", hole_cards=("2d", "3d"),
            board=("As", "Ks", "Qs", "Js", "Ts")), "uniform", .5),
        "weighted_two_combos": (obs, "weighted", .25),
        "facing_river_raise": (replace(obs, hand_id="facing",
            players=(Player("hero", 4900, 0, 100), Player("villain", 4800, 100, 200)),
            hole_cards=("Qd", "Jh"), board=("Qc", "8h", "8s", "3c", "2d"),
            legal=LegalActions(False, True, 100, 200, 4900),
            history=(PublicAction("0", "villain", "river", "raise_to", 100, False),)), "prior", None),
        "weighted_price_boundary": (replace(obs, hand_id="boundary",
            players=(Player("hero", 4900, 0, 100), Player("villain", 4800, 100, 200)),
            legal=LegalActions(False, True, 100)), "weighted", .25),
        "folded_money_and_refund": (Observation("exact-river", "refund", "hero", 2,
            (Player("hero", 1, 0, 100), Player("villain", 0, 0, 50),
             Player("dead", 1, 0, 100, True)), ("Ks", "Kh"), obs.board, 100,
            LegalActions(True, False, 0)), "short_aces", .4),
    }
    return cases


def ranges_for(obs, mode, model):
    if mode == "prior":
        return build_ranges(obs, model, math.inf)
    if mode in ("weighted", "short_aces"):
        entries = [(('Ks', 'Kh'), 1), (('6h', 'Th'), 3)] if mode == "weighted" else [(('As', 'Ah'), 1)]
        weighted = WeightedRange.create([((CARD_INDEX[a], CARD_INDEX[b]), w) for (a, b), w in entries])
    else:
        known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
        weighted = WeightedRange.create([(pair, 1) for pair in COMBOS if not known.intersection(pair)])
    return {"villain": weighted}


def register(output, replicates, hand_replicates):
    if replicates < 2 or hand_replicates < 1:
        raise ValueError("Cuotas de repetición inválidas")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    shutil.copytree(ROOT / "pokerfight", source / "pokerfight", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (source / "scripts").mkdir()
    for name in ("__init__.py", "benchmark_exact_river.py"):
        shutil.copy2(ROOT / "scripts" / name, source / "scripts" / name)
    hashes = {p.relative_to(source).as_posix(): sha256(p) for p in source.rglob("*") if p.is_file()}
    protocol = {
        "date_lima": "2026-10-29", "seed": SEED, "replicates": replicates,
        "quotas": QUOTAS, "hand_replicates": hand_replicates,
        "scope": "River, exactly one active opponent; supplied range and existing selection unchanged.",
        "fixtures": {name: {"observation": asdict(obs), "range_mode": mode, "known_equity": expected}
            for name, (obs, mode, expected) in fixtures().items()},
        "technical_hands": {"players": [2, 3, 4, 5, 6], "all_rotations": True,
            "base": "v4rb", "rivals": "calling", "stack": 5000, "samples": 512,
            "purpose": "Legality, chip conservation, delegation and exercising exact river; no strength inference."},
        "benchmarks": "Alternating estimator order; estimation-only timings plus complete policy timing.",
        "source_sha256": hashes,
        "limitations": ["Exactness is conditional on the supplied opponent range and showdown model.",
            "Zero SE only removes Monte Carlo noise; existing heuristic selection can change.",
            "No promotion or conclusion about tournament strength from this experiment."],
    }
    write_json(output / "protocol.json", protocol)
    (output / "protocol.sha256").write_text(sha256(output / "protocol.json") + "\n", encoding="ascii")
    print(json.dumps({"registered": str(output), "files_frozen": len(hashes)}))


def run(output):
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    if ROOT != output / "source":
        raise ValueError("Ejecuta run desde la instantánea source, usando su directorio como cwd")
    if (output / "benchmark.json").exists():
        raise FileExistsError("No se sobrescriben resultados")
    for path, expected in protocol["source_sha256"].items():
        if sha256(ROOT / path) != expected:
            raise ValueError(f"Fuente congelada modificada: {path}")
    verify_control()
    records = []
    policy_rows = []
    for name, item in protocol["fixtures"].items():
        obs = Observation.from_dict(item["observation"])
        model = OpponentModel()
        model.observe(obs.table_id, obs.hand_id, obs.history)
        ranges = ranges_for(obs, item["range_mode"], model)
        exact = estimate_river(obs, ranges)
        if item["known_equity"] is not None:
            assert math.isclose(exact.equity, item["known_equity"], abs_tol=1e-14)
        selector = PokerBot(BotConfig())
        selector.model = model
        exact_action = selector.select(obs, exact)[0].to_dict()
        exact_times = []
        quotas = []
        for quota in protocol["quotas"]:
            rows = []
            for replica in range(protocol["replicates"]):
                computed = {}
                for method in (("mc", "exact") if replica % 2 == 0 else ("exact", "mc")):
                    started = perf_counter()
                    value = (estimate_river(obs, ranges) if method == "exact" else
                        estimate(obs, ranges, random.Random(seed_for(SEED, name, quota, replica)), quota))
                    elapsed = (perf_counter() - started) * 1000
                    computed[method] = value
                    if method == "exact":
                        assert value == exact
                        exact_times.append(elapsed)
                    else:
                        rows.append({"replica": replica, "elapsed_ms": elapsed,
                            "equity": value.equity, "standard_error": value.standard_error,
                            "error": value.equity - exact.equity,
                            "action": selector.select(obs, value)[0].to_dict()})
            quotas.append({"samples": quota, "median_ms": statistics.median(r["elapsed_ms"] for r in rows),
                "rmse": math.sqrt(statistics.mean(r["error"] ** 2 for r in rows)),
                "mean_error": statistics.mean(r["error"] for r in rows),
                "action_disagreements": sum(r["action"] != exact_action for r in rows), "replicas": rows})
        records.append({"case": name, "exact": asdict(exact), "exact_action": exact_action,
            "exact_median_ms": statistics.median(exact_times), "mc": quotas})
        # The policy wrapper always builds the ordinary public-information prior.
        # Synthetic weighted fixtures above test the estimator independently.
        base = make_policy("v4rb", BotConfig(4000, 3500, SEED), SEED)
        wrapped = ExactRiverPolicy(make_policy("v4rb", BotConfig(4000, 3500, SEED), SEED))
        try:
            policy_rows.append({"case": name, "base": base.decide(obs).to_dict(),
                "exact_wrapper": wrapped.decide(obs).to_dict()})
        finally:
            close_policies({"base": base, "exact": wrapped})
        print(f"measured {name}", flush=True)

    hands = []
    for n in protocol["technical_hands"]["players"]:
        ids = ("hero",) + tuple(f"v{i}" for i in range(1, n))
        for replica in range(protocol["hand_replicates"]):
            for rotation in range(n):
                seats = ids[rotation:] + ids[:rotation]
                paired = {}
                for mode in ("base", "exact"):
                    config = BotConfig(512, 3500, SEED)
                    policies = {pid: make_policy("v4rb" if pid == "hero" else "calling", config,
                        seed_for(SEED, "policy", n, replica, pid)) for pid in ids}
                    if mode == "exact":
                        policies["hero"] = ExactRiverPolicy(policies["hero"])
                    try:
                        result = play_hand(policies, seats, dict.fromkeys(ids, 5000),
                            seed_for(SEED, "deck", n, replica), str(replica), f"exact-tech-{n}-{rotation}",
                            50, 100, trace_player_id="hero")
                        assert sum(result.payoffs.values()) == 0
                        assert sum(result.stacks.values()) == 5000 * n
                        assert not any(d.fallback for _, d in result.decisions)
                        for trace in result.trace:
                            from pokerfight.domain import Action
                            assert Action(**trace["decision"]["action"]).is_legal(Observation.from_dict(trace["observation"]))
                        paired[mode] = {"payoffs": result.payoffs, "trace": list(result.trace),
                            "decisions": len(result.decisions)}
                    finally:
                        close_policies(policies)
                # Earlier streets are delegated without changing their decisions.
                def early(trace):
                    return [(t["observation"], {k: v for k, v in t["decision"].items() if k != "elapsed_ms"})
                        for t in trace if len(t["observation"]["board"]) < 5]
                assert early(paired["base"]["trace"]) == early(paired["exact"]["trace"])
                hands.append({"players": n, "replica": replica, "rotation": rotation, **paired})
        print(f"technical hands {n}p complete", flush=True)

    exact_sum = sum(row["exact_median_ms"] for row in records)
    at4000 = [next(q for q in row["mc"] if q["samples"] == 4000) for row in records]
    mc_sum = sum(row["median_ms"] for row in at4000)
    targets = [entry for hand in hands for entry in hand["exact"]["trace"]
        if entry["decision"].get("search", {}).get("model") == "exact_heads_up_river"]
    summary = {
        "fixture_count": len(records), "replicates_per_quota": protocol["replicates"],
        "sum_medians_speedup_vs_mc4000": mc_sum / exact_sum,
        "estimator_time_reduction_percent": 100 * (1 - exact_sum / mc_sum),
        "mc4000_pooled_rmse": math.sqrt(statistics.mean(r["rmse"] ** 2 for r in at4000)),
        "complete_hand_pairs": len(hands), "exact_river_decisions_in_hands": len(targets),
        "technical_fallbacks": 0, "illegal_actions": 0, "chip_failures": 0,
        "pre_river_traces_identical": True,
        "max_wrapper_ms": max(row["exact_wrapper"]["elapsed_ms"] for row in policy_rows),
        "policy_fallbacks": sum(row["exact_wrapper"]["fallback"] for row in policy_rows),
        "frozen_v2_intact": True,
    }
    result = {"protocol_sha256": sha256(output / "protocol.json"), "summary": summary,
        "estimators": records, "policy_decisions": policy_rows, "technical_hands": hands}
    write_json(output / "benchmark.json", result)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    register_parser = sub.add_parser("register")
    register_parser.add_argument("--output", type=Path, required=True)
    register_parser.add_argument("--replicates", type=int, default=24)
    register_parser.add_argument("--hand-replicates", type=int, default=2)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--output", type=Path, required=True)
    decide_parser = sub.add_parser("decide")
    decide_parser.add_argument("observation", type=Path)
    decide_parser.add_argument("--base", choices=("v3", "v4", "v4rb", "v5", "v6", "v7"), default="v4rb")
    decide_parser.add_argument("--samples", type=int, default=4000)
    decide_parser.add_argument("--budget-ms", type=int, default=3500)
    decide_parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.command == "register":
        register(args.output.resolve(), args.replicates, args.hand_replicates)
    elif args.command == "run":
        run(args.output.resolve())
    else:
        obs = Observation.from_dict(json.loads(args.observation.read_text(encoding="utf-8")))
        policy = ExactRiverPolicy(make_policy(args.base, BotConfig(args.samples, args.budget_ms, args.seed), args.seed))
        try:
            print(json.dumps(policy.decide(obs).to_dict(), ensure_ascii=False, allow_nan=False))
        finally:
            policy.close()


if __name__ == "__main__":
    main()

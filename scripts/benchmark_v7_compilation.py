"""Check exact v7 results against the registered pre-optimization package."""
import argparse
from dataclasses import asdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import statistics
from time import perf_counter

from scripts.audit_integrated_shove import snapshot_api
from scripts.integrated_shove_experiment import load
from scripts.diagnose_shortstack import cases


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()
                if key not in ("elapsed_ms", "compiled_nodes")}
    if isinstance(value, (tuple, list)):
        return [normalized(item) for item in value]
    return value


def fixed(api, obs_data, baseline_data, seed):
    obs = api["domain"].Observation.from_dict(obs_data)
    model = api["opponents"].OpponentModel()
    model.observe(obs.table_id, obs.hand_id, obs.history)
    ranges = api["equity"].build_ranges(obs, model, math.inf)
    baseline = api["domain"].Action(**baseline_data)
    started = perf_counter()
    action, info = api["integrated_response_search"].search_integrated_responses(
        obs, ranges, model, baseline, random.Random(seed), 1024, math.inf)
    return {"action": action.to_dict(), "search": info}, (perf_counter() - started) * 1000


def hand(api, n, rotation, seed):
    ids = ("hero",) + tuple(str(i) for i in range(1, n))
    seats = ids[rotation:] + ids[:rotation]
    kinds = ("tag", "pressure", "v2", "fullhouse", "honest")
    config = api["strategy"].BotConfig(samples=512, budget_ms=3500)
    rival = api["strategy"].BotConfig(samples=256, budget_ms=1600)
    policies = {pid: api["arena"].make_policy("v7" if pid == "hero" else kinds[i - 1],
        config if pid == "hero" else rival, api["arena"].seed_for(seed, "policy", pid))
        for i, pid in enumerate(ids)}
    try:
        result = api["arena"].play_hand(policies, seats, dict.fromkeys(ids, 800), seed,
            table_id=f"v7-opt-{seed}", trace_player_id="hero")
        assert sum(result.payoffs.values()) == 0
        assert not any(decision.fallback for _, decision in result.decisions)
        return normalized(asdict(result))
    finally:
        api["arena"].close_policies(policies)


def run(root, output):
    if output.exists():
        raise ValueError("Use a new benchmark output")
    _, digest = load(root)
    old = snapshot_api(root)
    names = ("arena", "domain", "strategy", "integrated_response_search", "equity", "opponents", "evaluation")
    old = {name: importlib.import_module(old["arena"].__package__ + "." + name) for name in names}
    current = {name: importlib.import_module("pokerfight." + name) for name in names}
    rows, hands = [], []
    for name, obs in cases().items():
        if name == "cheap_all_in_regression":
            continue
        baseline = current["arena"].make_policy("v2", current["strategy"].BotConfig(), 2026102903).decide(obs)
        timings = {"before": [], "after": []}
        for repeat in range(3):
            pair = {}
            for label in (("before", "after") if repeat % 2 == 0 else ("after", "before")):
                pair[label], elapsed = fixed(old if label == "before" else current, asdict(obs),
                                            baseline.action.to_dict(), 2026102907 + repeat)
                timings[label].append(elapsed)
            assert normalized(pair["before"]) == normalized(pair["after"]), (name, repeat)
        before, after = (statistics.median(timings[label]) for label in ("before", "after"))
        rows.append({"case": name, "samples": 1024, "timings_ms": timings,
                     "before_median_ms": before, "after_median_ms": after, "speedup": before / after,
                     "compiled_nodes_before": pair["before"]["search"]["compiled_nodes"],
                     "compiled_nodes_after": pair["after"]["search"]["compiled_nodes"], "identical": True})
        print(f"{name}: {before:.1f}->{after:.1f}ms ({before / after:.2f}x), exact outputs", flush=True)
    for n in range(2, 7):
        for rotation in range(n):
            seed = current["arena"].seed_for("v7-optimization-technical-hands-20261029", n, rotation)
            before, after = hand(old, n, rotation, seed), hand(current, n, rotation, seed)
            assert before == after, (n, rotation)
            hands.append({"players": n, "rotation": rotation, "seed": seed, "identical": True,
                          "payoffs": after["payoffs"],
                          "result_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest()})
    result = {"reference_protocol_sha256": digest, "fixed_search_pairs": rows,
        "total_median_speedup": sum(row["before_median_ms"] for row in rows) / sum(row["after_median_ms"] for row in rows),
        "complete_hand_pairs": hands, "excluded_fields": ["elapsed_ms", "compiled_nodes"],
        "source_sha256_after": current["evaluation"].environment()["source_sha256"],
        "module_sha256_before": hashlib.sha256(Path(old["integrated_response_search"].__file__).read_bytes()).hexdigest(),
        "module_sha256_after": hashlib.sha256(Path(current["integrated_response_search"].__file__).read_bytes()).hexdigest(),
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": "Technical fixed-work fixtures and paired replays only. The registered strategic campaign used its original unoptimized snapshot throughout."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"speedup": result["total_median_speedup"], "fixed_pairs": len(rows) * 3,
                     "hand_pairs": len(hands)}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output.resolve())

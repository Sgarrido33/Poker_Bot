"""Compare fixed-work searches and complete hands against the saved pre-change code."""
import argparse
from dataclasses import asdict
import importlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter

from pokerfight import action_search, arena, domain, equity, evaluation, opponents, strategy
from pokerfight.campaign import save
from pokerfight.shortstack_experiment import verify_control
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases

ROOT = Path(__file__).resolve().parents[1]


def reference_package(path):
    name = "_pokerfight_pre_compilation"
    spec = importlib.util.spec_from_file_location(name, path / "pokerfight/__init__.py",
                                                submodule_search_locations=[str(path / "pokerfight")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    modules = {key: importlib.import_module(f"{name}.{key}") for key in
               ("action_search", "arena", "domain", "equity", "evaluation", "opponents", "strategy")}
    recorded = json.loads((path / "environment.json").read_text(encoding="utf-8"))
    if modules["evaluation"].environment() != recorded:
        raise ValueError("La instantánea anterior no coincide con su huella")
    return modules, recorded


def fixed_search(api, obs_data, baseline_data, samples, seed):
    obs = api["domain"].Observation.from_dict(obs_data)
    model = api["opponents"].OpponentModel()
    model.observe(obs.table_id, obs.hand_id, obs.history)
    ranges = api["equity"].build_ranges(obs, model, math.inf)
    baseline = api["domain"].Action(**baseline_data)
    started = perf_counter()
    action, info = api["action_search"].search(obs, ranges, model, baseline, random.Random(seed),
        samples, math.inf, min_samples=samples, batch=samples)
    elapsed = (perf_counter() - started) * 1000
    assert info["worlds"] == samples
    return {"action": action.to_dict(), "search": info}, elapsed


def without_timing(value):
    if isinstance(value, dict):
        return {k: without_timing(v) for k, v in value.items() if k != "elapsed_ms"}
    if isinstance(value, (list, tuple)):
        return [without_timing(v) for v in value]
    return value


def full_hand(api, players, rotation, seed):
    ids = ("hero",) + tuple(f"v{i}" for i in range(1, players))
    seats = ids[rotation:] + ids[:rotation]
    config = api["strategy"].BotConfig(samples=512, budget_ms=3500)
    rival_config = api["strategy"].BotConfig(samples=512, budget_ms=1600)
    kinds = ("tag", "pressure", "v2")
    policies = {pid: api["arena"].make_policy("v4" if pid == "hero" else kinds[(i - 1) % len(kinds)],
                  config if pid == "hero" else rival_config,
                  arena.seed_for(seed, "policy", pid)) for i, pid in enumerate(ids)}
    result = api["arena"].play_hand(policies, seats, dict.fromkeys(ids, 800), seed,
                                  table_id=f"compile-{seed}", trace_player_id="hero")
    assert sum(result.payoffs.values()) == 0
    assert not any(d.fallback for _, d in result.decisions)
    return without_timing(asdict(result))


def run(reference, output, samples=8192, repeats=3):
    if samples < 2 or repeats < 1:
        raise ValueError("Se requieren al menos dos mundos y una repetición")
    output.parent.mkdir(parents=True, exist_ok=True)
    old, old_environment = reference_package(reference)
    current = {key: globals()[key] for key in old}
    verify_control()
    fixtures = cases()
    rows = []
    for name, obs in fixtures.items():
        if "all_in" in name:
            continue
        baseline = arena.make_policy("v2mc", strategy.BotConfig(samples=4000, budget_ms=3500), 90210).decide(obs)
        assert not baseline.fallback
        timings = {"before": [], "after": []}
        result = None
        for repeat in range(repeats):
            pair = {}
            for label in (("before", "after") if repeat % 2 == 0 else ("after", "before")):
                pair[label], ms = fixed_search(old if label == "before" else current, asdict(obs),
                                              baseline.action.to_dict(), samples, 27017 + repeat)
                timings[label].append(ms)
            assert pair["before"] == pair["after"], (name, repeat)
            result = pair["after"]
        before, after = (statistics.median(timings[label]) for label in ("before", "after"))
        rows.append({"case": name, "observation": asdict(obs), "identical": True,
                     "samples": samples, "repeats": repeats, "timings_ms": timings,
                     "before_median_ms": before, "after_median_ms": after,
                     "speedup": before / after, "last_result": result})
        print(f"{name}: {before:.1f} -> {after:.1f} ms ({before / after:.2f}x), identical", flush=True)

    # Earlier validation traces are development data. Check the full adaptive
    # policy on one recorded preflop state per cell, including rare price states.
    replay_rows = []
    folder = ROOT / "results/action_search_2026-10-28/validation"
    for path in sorted(folder.glob("paired_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        recorded = next((entry for hand in report["worst_candidate_hands"] for entry in hand["trace"]
                         if not entry["observation"]["board"]), None)
        if recorded is None:
            continue
        decisions = {}
        for label, api in (("before", old), ("after", current)):
            config = api["strategy"].BotConfig(samples=1024, budget_ms=3500, seed=27017)
            obs = api["domain"].Observation.from_dict(recorded["observation"])
            bot = api["action_search"].ActionSearchBot(config)
            decisions[label] = without_timing(bot.decide(obs).to_dict())
            assert not decisions[label]["fallback"]
        assert decisions["before"] == decisions["after"], path.name
        replay_rows.append({"cell": path.stem, "identical": True,
                            "action": decisions["after"]["action"], "reason": decisions["after"]["reason"]})

    hands = []
    for players in range(2, 7):
        for rotation in range(players):
            seed = arena.seed_for("action-compilation-hands-20261028", players, rotation)
            before, after = full_hand(old, players, rotation, seed), full_hand(current, players, rotation, seed)
            assert before == after, (players, rotation)
            hands.append({"players": players, "rotation": rotation, "seed": seed,
                          "identical": True, "payoffs": after["payoffs"]})

    production = []
    config = strategy.BotConfig(samples=16384, budget_ms=3500)
    with SupervisedPolicy(config) as bot:
        for name, obs in fixtures.items():
            decision = bot.decide(obs)
            assert not decision.fallback and decision.action.is_legal(obs)
            assert decision.elapsed_ms <= 4250
            production.append({"case": name, "decision": decision.to_dict()})
    result = {"environment_before": old_environment, "environment_after": evaluation.environment(),
              "reference": str(reference.relative_to(ROOT)), "fixed_work": rows,
              "total_median_speedup": sum(r["before_median_ms"] for r in rows) / sum(r["after_median_ms"] for r in rows),
              "recorded_state_replays": replay_rows, "complete_hands": hands, "supervised": production,
              "checks": {"fixed_search_identical": True, "recorded_decisions_identical": True,
                         "hands_identical": True, "chip_failures": 0, "fallbacks": 0,
                         "supervisor_over_4250_ms": 0},
              "limitations": "Fixed-work development fixtures, not a strength experiment or production latency percentile. "
                             "Equal worlds give identical results; a wall-clock cutoff can now complete more worlds and change an action. "
                             "Hand replays use 512 samples; recorded decisions use 1024; supervised fixtures use 16384."}
    save(output, result)
    print(json.dumps({"speedup": result["total_median_speedup"], "recorded_states": len(replay_rows),
                      "complete_hands_per_variant": len(hands), "supervised": len(production), "checks": result["checks"]}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=ROOT / "research/policy_snapshots/pre_fast_v4_20261028")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=8192)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run(args.reference.resolve(), args.output, args.samples, args.repeats)

"""Fixed-work equivalence, speed and hand replays for exact response integration.

This is a technical benchmark against a preserved package, not a strength test.
Run from the project root with --reference and --output pointing at a new run.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter

from pokerfight.shortstack_experiment import verify_control
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases, opening

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("action_model", "action_search", "action_integration", "response_search",
           "terminal_search", "arena", "domain", "equity", "evaluation", "opponents", "strategy")
SEED = 2026102901


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key != "elapsed_ms"}
    if isinstance(value, (tuple, list)):
        return [normalized(item) for item in value]
    return value


def reference_package(path):
    protocol = json.loads((path.parent / "protocol.json").read_text(encoding="utf-8"))
    for name, expected in protocol["source_sha256_before"].items():
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reference source changed: {name}")
    name = "_pokerfight_pre_integrated_optimization"
    spec = importlib.util.spec_from_file_location(name, path / "pokerfight/__init__.py",
                                                submodule_search_locations=[str(path / "pokerfight")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    api = {key: importlib.import_module(f"{name}.{key}") for key in MODULES}
    recorded = json.loads((path / "environment.json").read_text(encoding="utf-8"))
    if api["evaluation"].environment() != recorded:
        raise ValueError("Reference environment changed")
    return api, protocol, recorded


def fixed_search(api, obs_data, baseline_data, samples, seed):
    obs = api["domain"].Observation.from_dict(obs_data)
    model = api["opponents"].OpponentModel()
    model.observe(obs.table_id, obs.hand_id, obs.history)
    ranges = api["equity"].build_ranges(obs, model, math.inf)
    baseline = api["domain"].Action(**baseline_data)
    started = perf_counter()
    result = api["action_search"].search(obs, ranges, model, baseline, random.Random(seed),
        samples, math.inf, min_samples=samples, batch=samples,
        prepared_factory=api["action_integration"].IntegratedAction)
    elapsed_ms = (perf_counter() - started) * 1000
    assert result[1]["worlds"] == samples
    return (result[0].to_dict(), result[1]), elapsed_ms


def full_hand(api, kind, players, rotation, seed):
    ids = ("hero",) + tuple(f"v{i}" for i in range(1, players))
    seats = ids[rotation:] + ids[:rotation]
    config = api["strategy"].BotConfig(samples=512, budget_ms=3500)
    rival_config = api["strategy"].BotConfig(samples=512, budget_ms=1600)
    rivals = ("tag", "pressure", "v2", "calling", "tight")
    policies = {pid: api["arena"].make_policy(kind if pid == "hero" else rivals[i - 1],
                 config if pid == "hero" else rival_config,
                 api["arena"].seed_for(seed, "policy", pid)) for i, pid in enumerate(ids)}
    try:
        result = api["arena"].play_hand(policies, seats, dict.fromkeys(ids, 800), seed,
            table_id=f"integrated-{seed}", trace_player_id="hero")
    finally:
        api["arena"].close_policies(policies)
    assert sum(result.payoffs.values()) == 0
    assert not any(decision.fallback for _, decision in result.decisions)
    return normalized(asdict(result))


def collision_guard_probe(api):
    obs = api["domain"].Observation.from_dict(asdict(opening(3, 8, "BTN", ("As", "Ah"))))

    class RareCompatibleRange:
        attempts = 0

        def draw(self, rng):
            self.attempts += 1
            return (2, 3) if self.attempts in (1, 5001) else (0, 2)

    class WinningAction(api["action_model"].PreparedAction):
        def value(self, ranks, scores, uniforms, prior, rank_masks=None):
            # Deterministic terminal wins and calls isolate the stopping guard
            # from card strength and response noise in this synthetic fixture.
            return super().value([2 if i == self.hero else 1 for i in range(3)],
                                 scores, [0.] * 3, prior)

    ranges = {"1": api["equity"].WeightedRange.create([((0, 1), 1)]), "2": RareCompatibleRange()}
    action, info = api["action_search"].search(obs, ranges, api["opponents"].OpponentModel(),
        api["domain"].Action("fold"), random.Random(19), 64, math.inf,
        prepared_factory=WinningAction)
    assert info["worlds"] == 2 and info["attempts"] == 10000
    return {"action": action.to_dict(), "worlds": info["worlds"], "attempts": info["attempts"],
            "stop": info["stop"], "changed": info["changed"]}


def run(reference, output, samples=2048, repeats=5):
    if output.exists():
        raise ValueError(f"Refusing to replace benchmark: {output}")
    if samples < 2 or repeats < 1:
        raise ValueError("samples >= 2 and repeats >= 1 are required")
    old, protocol, old_environment = reference_package(reference)
    current = {key: importlib.import_module(f"pokerfight.{key}") for key in MODULES}
    verify_control()
    fixtures = cases()
    selected = {name: obs for name, obs in fixtures.items() if name != "cheap_all_in_regression"}
    rows, adaptive, hands, supervised = [], [], [], []
    for name, obs in selected.items():
        baseline = current["arena"].make_policy("v2", current["strategy"].BotConfig(samples=4000), SEED).decide(obs)
        assert not baseline.fallback
        timings = {"before": [], "after": []}
        for repeat in range(repeats):
            pair = {}
            for label in (("before", "after") if repeat % 2 == 0 else ("after", "before")):
                pair[label], elapsed = fixed_search(old if label == "before" else current,
                    asdict(obs), baseline.action.to_dict(), samples, SEED + repeat)
                timings[label].append(elapsed)
            assert pair["before"] == pair["after"], (name, repeat)
        before, after = (statistics.median(timings[label]) for label in ("before", "after"))
        rows.append({"case": name, "identical": True, "samples": samples,
                     "timings_ms": timings, "before_median_ms": before,
                     "after_median_ms": after, "speedup": before / after,
                     "last_result": pair["after"]})
        print(f"{name}: {before:.1f} -> {after:.1f} ms ({before / after:.2f}x), identical", flush=True)

    for name, obs in selected.items():
        for kind in ("v4rb", "v6"):
            for seed in range(SEED, SEED + 3):
                pair = {}
                for label, api in (("before", old), ("after", current)):
                    state = api["domain"].Observation.from_dict(asdict(obs))
                    config = api["strategy"].BotConfig(samples=1024, budget_ms=3500)
                    decision = api["arena"].make_policy(kind, config, seed).decide(state)
                    assert not decision.fallback
                    pair[label] = normalized(decision.to_dict())
                assert pair["before"] == pair["after"], (name, kind, seed)
                adaptive.append({"case": name, "policy": kind, "seed": seed,
                                 "identical": True, "decision": pair["after"]})
    print(f"Adaptive policy equivalence: {len(adaptive)} paired decisions", flush=True)

    for kind in ("v4rb", "v6"):
        for players in range(2, 7):
            for rotation in range(players):
                seed = current["arena"].seed_for("integrated-optimization-replays-20261029",
                                                players, rotation)
                before = full_hand(old, kind, players, rotation, seed)
                after = full_hand(current, kind, players, rotation, seed)
                assert before == after, (kind, players, rotation)
                digest = hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest()
                hands.append({"policy": kind, "players": players, "rotation": rotation,
                              "seed": seed, "identical": True, "result_sha256": digest,
                              "payoffs": after["payoffs"], "hero_trace": after["trace"]})
        print(f"Complete-hand equivalence through {kind}: {len(hands)} pairs", flush=True)

    config = current["strategy"].BotConfig(samples=4096, budget_ms=3500, seed=SEED)
    for kind in ("v4rb", "v6"):
        direct = current["arena"].make_policy(kind, config, config.seed)
        with SupervisedPolicy(config, policy=kind) as bot:
            for name, obs in fixtures.items():
                decision = bot.decide(obs)
                expected = direct.decide(obs)
                assert not decision.fallback and decision.action.is_legal(obs)
                assert decision.elapsed_ms <= 4250
                assert normalized(decision.to_dict()) == normalized(expected.to_dict()), (kind, name)
                supervised.append({"policy": kind, "case": name, "decision": decision.to_dict()})
    print(f"Supervised/direct equivalence: {len(supervised)} paired decisions", flush=True)

    guards = {"before": collision_guard_probe(old), "after": collision_guard_probe(current)}
    assert guards["before"]["changed"] and guards["before"]["stop"] == "sample_cap"
    assert not guards["after"]["changed"] and guards["after"]["stop"] == "incompatible_ranges_keep_v2"
    verify_control()
    result = {"date_lima": "2026-10-29", "reference": str(reference.relative_to(ROOT)),
              "environment_before": old_environment, "environment_after": current["evaluation"].environment(),
              "protocol_sha256": hashlib.sha256((reference.parent / "protocol.json").read_bytes()).hexdigest(),
              "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "config": {"samples": samples, "repeats": repeats, "seed": SEED},
              "fixed_work": rows,
              "total_median_speedup": sum(row["before_median_ms"] for row in rows) / sum(row["after_median_ms"] for row in rows),
              "adaptive_decisions": adaptive, "complete_hand_pairs": hands, "supervised_decisions": supervised,
              "collision_guard_reproduction": guards,
              "checks": {"fixed_search_identical": True, "adaptive_decisions_identical": True,
                         "complete_hands_identical": True, "supervised_matches_direct": True,
                         "chip_failures": 0, "fallbacks": 0, "illegal_actions": 0,
                         "supervisor_over_4250_ms": 0, "frozen_v2_intact": True},
              "limitations": protocol["limitations"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"speedup": result["total_median_speedup"], "fixed_pairs": len(rows) * repeats,
                     "adaptive_pairs": len(adaptive), "hand_pairs": len(hands),
                     "supervised_pairs": len(supervised), "checks": result["checks"]}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    run(args.reference.resolve(), args.output.resolve(), args.samples, args.repeats)

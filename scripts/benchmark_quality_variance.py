"""Paired variance benchmark for sampled and integrated fold/call response EVs.

For each fixed preflop fixture, every replica uses the same card worlds and
response uniforms for both estimators. IntegratedAction averages the response
branches conditional on each sampled card world; it does not average away
card/range uncertainty.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
from time import perf_counter

import eval7

from pokerfight.action_integration import IntegratedAction
from pokerfight.action_model import PRIORS, PreparedAction, candidate_actions
from pokerfight.cards import CARD_INDEX, EVAL_CARDS
from pokerfight.equity import COMBO_SCORES, build_ranges
from pokerfight.opponents import OpponentModel
from pokerfight.strategy import BotConfig
from scripts.diagnose_shortstack import cases
from pokerfight.arena import make_policy
from pokerfight.evaluation import environment


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "quality_2026-10-28" / "variance.json"
SEED = 2026102807
REPLICATES = 24
WORLDS_PER_REPLICATE = 128
EXCLUDED_CASES = {"cheap_all_in_regression"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_for(*parts: object) -> int:
    payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def sample_world(obs, ranges, rng):
    known = {CARD_INDEX[c] for c in obs.hole_cards + obs.board}
    hero = next(i for i, player in enumerate(obs.players) if player.player_id == obs.hero_id)
    ids = [(i, player.player_id) for i, player in enumerate(obs.players)
           if player.player_id in ranges]
    used = set(known)
    hands = {}
    for i, player_id in ids:
        pair = ranges[player_id].draw(rng)
        if used.intersection(pair):
            return None
        used.update(pair)
        hands[i] = pair
    runout = rng.sample([card for card in range(52) if card not in used], 5 - len(obs.board))
    board = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.board] + [EVAL_CARDS[c] for c in runout]
    hero_cards = [EVAL_CARDS[CARD_INDEX[c]] for c in obs.hole_cards]
    ranks = [0] * len(obs.players)
    scores = [0.0] * len(obs.players)
    ranks[hero] = eval7.evaluate(hero_cards + board)
    for i, pair in hands.items():
        ranks[i] = eval7.evaluate([EVAL_CARDS[c] for c in pair] + board)
        scores[i] = COMBO_SCORES[tuple(sorted(pair))]
    uniforms = [rng.random() for _ in obs.players]
    return ranks, scores, uniforms


def action_adjustments(obs, model):
    result = {}
    for player in obs.opponents:
        aggression, confidence = model.tendency(player.player_id, "preflop", True)
        result[player.player_id] = confidence * (aggression - .25) * .15
    return result


def sample_variance_or_zero(values):
    return statistics.variance(values) if len(values) > 1 else 0.0


def ratio(numerator, denominator):
    return numerator / denominator if denominator > 0 else None


def run(output: Path = OUTPUT) -> dict:
    started = perf_counter()
    all_cases = cases()
    selected = {name: obs for name, obs in all_cases.items() if name not in EXCLUDED_CASES}
    base_config = BotConfig(samples=4000, budget_ms=1600, seed=SEED)
    fixture_results = {}
    cell_variances = {
        "per_world": {"sampled": [], "integrated": []},
        "between_replica": {"sampled": [], "integrated": []},
    }

    for fixture_name, obs in selected.items():
        # Use the real frozen v2 decision as the first/reference action in the
        # candidate list, matching the production search convention.
        baseline = make_policy("v2", base_config, SEED).decide(obs).action
        model = OpponentModel(base_config.confidence_cap, base_config.prior_observations)
        model.observe(obs.table_id, obs.hand_id, obs.history)
        ranges = build_ranges(obs, model, float("inf"))
        actions = candidate_actions(obs, baseline)
        adjustments = action_adjustments(obs, model)
        sampled_arms = [PreparedAction(obs, action, adjustments) for action in actions]
        integrated_arms = [IntegratedAction(obs, action, adjustments) for action in actions]

        per_cell = {}
        for prior in PRIORS:
            sampled_replica_means = defaultdict(list)
            integrated_replica_means = defaultdict(list)
            sampled_all_worlds = defaultdict(list)
            integrated_all_worlds = defaultdict(list)

            for replica in range(REPLICATES):
                rng = random.Random(seed_for(SEED, fixture_name, prior.name, replica))
                sampled_gain_sum = [0.0] * len(actions)
                integrated_gain_sum = [0.0] * len(actions)
                completed = 0
                attempts = 0
                max_attempts = max(10000, 100 * WORLDS_PER_REPLICATE)
                while completed < WORLDS_PER_REPLICATE and attempts < max_attempts:
                    attempts += 1
                    world = sample_world(obs, ranges, rng)
                    if world is None:
                        continue
                    ranks, scores, uniforms = world
                    sampled_values = [arm.value(ranks, scores, uniforms, prior)
                                      for arm in sampled_arms]
                    integrated_values = [arm.value(ranks, scores, uniforms, prior)
                                         for arm in integrated_arms]
                    sampled_base = sampled_values[0]
                    integrated_base = integrated_values[0]
                    for a in range(len(actions)):
                        sampled_gain = sampled_values[a] - sampled_base
                        integrated_gain = integrated_values[a] - integrated_base
                        sampled_gain_sum[a] += sampled_gain
                        integrated_gain_sum[a] += integrated_gain
                        sampled_all_worlds[a].append(sampled_gain)
                        integrated_all_worlds[a].append(integrated_gain)
                    completed += 1
                if completed != WORLDS_PER_REPLICATE:
                    raise RuntimeError(f"{fixture_name}/{prior.name}: solo {completed} mundos válidos")
                for a, action in enumerate(actions):
                    sampled_replica_means[a].append(sampled_gain_sum[a] / completed)
                    integrated_replica_means[a].append(integrated_gain_sum[a] / completed)

            prior_cells = {}
            for a, action in enumerate(actions):
                old_world_var = sample_variance_or_zero(sampled_all_worlds[a])
                new_world_var = sample_variance_or_zero(integrated_all_worlds[a])
                old_replica_var = sample_variance_or_zero(sampled_replica_means[a])
                new_replica_var = sample_variance_or_zero(integrated_replica_means[a])
                prior_cells[str(a)] = {
                    "action": action.to_dict(),
                    "mean_gain_chips": {
                        "sampled": statistics.fmean(sampled_replica_means[a]),
                        "integrated": statistics.fmean(integrated_replica_means[a]),
                    },
                    "between_replica_sample_variance_chips2": {
                        "sampled": old_replica_var,
                        "integrated": new_replica_var,
                        "integrated_over_sampled": ratio(new_replica_var, old_replica_var),
                    },
                    "per_world_sample_variance_chips2": {
                        "sampled": old_world_var,
                        "integrated": new_world_var,
                        "integrated_over_sampled": ratio(new_world_var, old_world_var),
                    },
                    "replicates": REPLICATES,
                    "worlds_per_replicate": WORLDS_PER_REPLICATE,
                }
                if a > 0:
                    cell_variances["per_world"]["sampled"].append(old_world_var)
                    cell_variances["per_world"]["integrated"].append(new_world_var)
                    cell_variances["between_replica"]["sampled"].append(old_replica_var)
                    cell_variances["between_replica"]["integrated"].append(new_replica_var)
            per_cell[prior.name] = prior_cells

        fixture_results[fixture_name] = {
            "baseline": baseline.to_dict(),
            "actions": [a.to_dict() for a in actions],
            "priors": per_cell,
        }

    target_sources = [
        ROOT / "pokerfight" / "action_model.py",
        ROOT / "pokerfight" / "action_integration.py",
        ROOT / "pokerfight" / "equity.py",
        ROOT / "scripts" / "diagnose_shortstack.py",
        Path(__file__).resolve(),
    ]
    env = environment()
    aggregate = {}
    for level, variance_key in (("per_world", "per_world_sample_variance_chips2"),
                                ("between_replica", "between_replica_sample_variance_chips2")):
        old = statistics.fmean(cell_variances[level]["sampled"])
        new = statistics.fmean(cell_variances[level]["integrated"])
        aggregate[variance_key] = {
            "aggregation": "arithmetic mean of within-cell sample variances across nonbaseline fixture/prior/action cells",
            "cells": len(cell_variances[level]["sampled"]),
            "sampled": old,
            "integrated": new,
            "integrated_over_sampled": ratio(new, old),
        }
    elapsed = perf_counter() - started
    report = {
        "title": "Paired per-action EV estimator variance: Bernoulli fold/call vs exact integration",
        "date": "2026-10-28",
        "config": {
            "seed": SEED,
            "replicates_per_fixture_prior": REPLICATES,
            "worlds_per_replicate": WORLDS_PER_REPLICATE,
            "fixtures": list(selected),
            "excluded_fixtures": sorted(EXCLUDED_CASES),
            "priors": [prior.name for prior in PRIORS],
            "baseline": "frozen v2 decision with 4000 samples; first candidate arm",
            "world_pairing": "same opponent hands, board, and response uniforms for both estimators",
            "gain": "candidate EV minus the baseline-arm EV within the same world",
            "replica_rng": "SHA-256 derived seed from global seed, fixture, prior, and replica index",
        },
        "environment": env,
        "environment_source_sha256": env["source_sha256"],
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in target_sources},
        "fixtures": fixture_results,
        "mean_nonbaseline_cell_variance": aggregate,
        "elapsed_seconds": elapsed,
        "interpretation": (
            "IntegratedAction computes the conditional mean over fold/call responses for each sampled card world. "
            "The per-world variance ratio should be at most one in aggregate by conditional-expectation variance "
            "reduction, though finite samples and individual fixture/action cells can deviate. It does not reduce "
            "variance caused by opponent-card ranges or board runouts."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "output": str(OUTPUT),
        "fixtures": len(result["fixtures"]),
        "per_world_variance_ratio": result["mean_nonbaseline_cell_variance"]["per_world_sample_variance_chips2"]["integrated_over_sampled"],
        "between_replica_variance_ratio": result["mean_nonbaseline_cell_variance"]["between_replica_sample_variance_chips2"]["integrated_over_sampled"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, indent=2))

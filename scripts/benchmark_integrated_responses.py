"""Compare v5/v7 estimators on the same cards and frozen public recourse.

Continuation always calls here to isolate response integration from learning.
This measures estimator variance and CPU, never playing strength.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
from time import perf_counter

from pokerfight.action_model import candidate_actions
from pokerfight.arena import make_policy, seed_for
from pokerfight.equity import build_ranges
from pokerfight.evaluation import environment
from pokerfight.integrated_response_search import IntegratedResponse
from pokerfight.opponents import OpponentModel
from pokerfight.response_search import ResponseRollout, SHOVE_PRIORS, worlds
from pokerfight.strategy import BotConfig
from scripts.diagnose_shortstack import cases

ROOT = Path(__file__).resolve().parents[1]
REPLICATES, WORLDS = 24, 128


def run(output):
    if output.exists():
        raise ValueError("Use a new output path")
    results, aggregate = [], {"sampled": [], "integrated": []}
    elapsed = {"sampled": 0., "integrated": 0.}
    for name, obs in cases().items():
        if name == "cheap_all_in_regression":
            continue
        model = OpponentModel()
        model.observe(obs.table_id, obs.hand_id, obs.history)
        ranges = build_ranges(obs, model, math.inf)
        baseline = make_policy("v2", BotConfig(), 2026102903).decide(obs).action
        actions = candidate_actions(obs, baseline)
        scalar = [ResponseRollout(obs, action, {}) for action in actions]
        exact = [IntegratedResponse(obs, action, {}) for action in actions]
        policies = [{key: True for _, key, _ in arm.hero_nodes} for arm in exact]
        cells = []
        for prior in SHOVE_PRIORS:
            means = {label: [[] for _ in actions] for label in elapsed}
            for replica in range(REPLICATES):
                rng = random.Random(seed_for("one-shove-variance-20261029", name, prior.name, replica))
                drawn = list(worlds(obs, ranges, rng, WORLDS, math.inf))
                assert len(drawn) == WORLDS
                for label in (("sampled", "integrated") if replica % 2 == 0 else ("integrated", "sampled")):
                    sums = [0.] * len(actions)
                    start = perf_counter()
                    for ranks, scores, uniforms in drawn:
                        values = [(scalar[a].value(ranks, scores, uniforms, prior, policies[a])[0]
                                   if label == "sampled" else exact[a].value(ranks, scores, prior, policies[a])[0])
                                  for a in range(len(actions))]
                        for a, value in enumerate(values):
                            sums[a] += value - values[0]
                    elapsed[label] += perf_counter() - start
                    for a, total in enumerate(sums):
                        means[label][a].append(total / WORLDS)
            for a, action in enumerate(actions):
                variances = {label: statistics.variance(means[label][a]) for label in elapsed}
                cells.append({"prior": prior.name, "action": action.to_dict(), "baseline": a == 0,
                              "replica_mean_gain": {label: statistics.mean(means[label][a]) for label in elapsed},
                              "between_replica_variance": variances,
                              "ratio": variances["integrated"] / variances["sampled"] if variances["sampled"] else None})
                if a:
                    for label in elapsed:
                        aggregate[label].append(variances[label])
        results.append({"case": name, "observation": asdict(obs), "cells": cells})
        print(f"variance complete: {name}", flush=True)
    means = {label: statistics.mean(values) for label, values in aggregate.items()}
    result = {"replicates": REPLICATES, "worlds_per_replicate": WORLDS,
              "environment": environment(), "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "public_continuation": "Always call, identical public keys for both estimators; no learning or evaluation-rank optimization.",
              "fixtures": results, "nonbaseline_cells": len(aggregate["sampled"]),
              "mean_between_replica_variance": means,
              "variance_ratio_integrated_over_sampled": means["integrated"] / means["sampled"],
              "estimator_seconds_excluding_card_worlds_and_compilation": elapsed,
              "limitations": ["Development fixtures, finite replicas; individual variance ratios can exceed one.",
                              "Always-call continuation isolates response integration, not the effect of learned recourse.",
                              "Equal worlds do not mean equal compute; variance and cost are both reported.",
                              "No strength or tournament claim."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"variance_ratio": result["variance_ratio_integrated_over_sampled"],
                     "estimator_seconds": elapsed}, indent=2))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())

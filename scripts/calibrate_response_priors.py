"""Diagnose fixed response priors against next public actions in reset hands.

Select nonterminal preflop raises without looking at payoffs or hidden cards.
This is an out-of-model diagnostic, not fitting or selecting a replacement prior.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

from pokerfight.arena import seed_for
from pokerfight.campaign import save
from pokerfight.domain import Action, Observation
from pokerfight.equity import build_ranges
from pokerfight.integrated_response_search import IntegratedResponse
from pokerfight.opponents import OpponentModel
from pokerfight.response_search import SHOVE_PRIORS, response_probabilities, worlds
from scripts import competition_experiment as executor
from scripts.integrated_shove_experiment import load, phase_plan

CATEGORIES = ("fold", "call", "terminal_raise", "nonterminal_raise")
MAX_PER_CELL_FAMILY, WORLDS = 12, 512


def run(root, output):
    if output.exists():
        raise ValueError("Refusing to replace calibration output")
    plan, digest = load(root)
    settings, folder = phase_plan(plan, "comparison"), root / "comparison"
    selected, skipped, counts, seen = [], Counter(), Counter(), set()
    for job in executor.jobs(settings):
        if job[0] != "reset":
            continue
        path = folder / (executor.job_name(job) + ".json")
        report = json.loads(path.read_text(encoding="utf-8"))
        executor.check_artifact(folder, settings, digest, job, report)
        trace = path.with_suffix(".jsonl")
        with trace.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                for entry in record["trace"]:
                    obs = Observation.from_dict(entry["observation"])
                    action = Action(**entry["decision"]["action"])
                    if obs.street != "preflop" or action.kind != "raise_to":
                        continue
                    coverage = max(p.street_bet + p.stack for p in obs.opponents)
                    if action.amount >= min(obs.hero.street_bet + obs.hero.stack, coverage):
                        continue  # Terminal pushes have redundant uncalled-raise abstractions.
                    offset = len(obs.history) + 1
                    if offset >= len(record["history"]):
                        skipped["no_next_action"] += 1
                        continue
                    event = record["history"][offset]
                    if event["street"] != "preflop" or event["player_id"] == obs.hero_id:
                        skipped["no_next_preflop_opponent"] += 1
                        continue
                    family = report["opponents"][event["player_id"]]
                    cell = (*job[1:], family)
                    if counts[cell] >= MAX_PER_CELL_FAMILY:
                        continue
                    physical = json.dumps([entry["observation"], action.to_dict()], sort_keys=True)
                    key = hashlib.sha256(physical.encode()).hexdigest()
                    if key in seen:
                        continue
                    seen.add(key)
                    model = OpponentModel()
                    model.observe(obs.table_id, obs.hand_id, obs.history)
                    adjustments = {}
                    for player in obs.opponents:
                        aggression, confidence = model.tendency(player.player_id, "preflop", True)
                        adjustments[player.player_id] = confidence * (aggression - .25) * .15
                    tree = IntegratedResponse(obs, action, adjustments)
                    node = tree.nodes[tree.root]
                    if node[0] != 1:
                        skipped["no_probabilistic_root_response"] += 1
                        continue
                    i, price, callers, can_shove, adjustment = tree.responses[node[1]]
                    if obs.players[i].player_id != event["player_id"]:
                        skipped["model_actor_mismatch"] += 1
                        continue
                    probabilities = {prior.name: [0., 0., 0., 0.] for prior in SHOVE_PRIORS}
                    ranges = build_ranges(obs, model, math.inf)
                    rng = random.Random(seed_for("response-calibration-20261029", key))
                    completed = 0
                    for _, scores, _ in worlds(obs, ranges, rng, WORLDS, math.inf):
                        for prior in SHOVE_PRIORS:
                            response = response_probabilities(scores[i], price, prior, adjustment, callers, can_shove)
                            for j, value in enumerate(response):
                                probabilities[prior.name][j] += value / WORLDS
                        completed += 1
                    assert completed == WORLDS
                    if event["kind"] == "raise_to":
                        player = obs.players[i]
                        cap = min(player.street_bet + player.stack,
                                  max(p.street_bet + p.stack for p in obs.players
                                      if p.player_id != player.player_id and not p.folded))
                        category = "terminal_raise" if event["amount"] >= cap else "nonterminal_raise"
                    else:
                        category = "call" if event["kind"] == "check" else event["kind"]
                    assert category in CATEGORIES
                    truth = [float(category == value) for value in CATEGORIES]
                    briers = {name: sum((p - y) ** 2 for p, y in zip(values, truth))
                              for name, values in probabilities.items()}
                    assert all(abs(sum(values) - 1) < 1e-10 for values in probabilities.values())
                    selected.append({"cell": job[1:], "family": family, "state_sha256": key,
                        "observed": category, "next_event": event, "predicted": probabilities,
                        "brier": briers, "observation": entry["observation"], "action": action.to_dict()})
                    counts[cell] += 1
        print(f"calibration complete: {executor.job_name(job)}", flush=True)
    aggregate = {}
    for family in ["all", *sorted({row["family"] for row in selected})]:
        rows = [row for row in selected if family == "all" or row["family"] == family]
        observed = Counter(row["observed"] for row in rows)
        aggregate[family] = {"states": len(rows), "observed_counts": dict(observed),
            "observed_rates": {category: observed[category] / len(rows) for category in CATEGORIES},
            "priors": {prior.name: {
                "mean_predicted_rates": dict(zip(CATEGORIES,
                    [statistics.mean(row["predicted"][prior.name][j] for row in rows) for j in range(4)])),
                "mean_brier": statistics.mean(row["brier"][prior.name] for row in rows)} for prior in SHOVE_PRIORS}}
    result = {"protocol_sha256": digest, "max_per_cell_family": MAX_PER_CELL_FAMILY,
        "worlds_per_state": WORLDS, "selection": "First distinct nonterminal preflop hero raises by registered job and trace order, up to 12 per cell/opponent family. No payoff or hidden opponent cards.",
        "categories": CATEGORIES, "states": selected, "aggregate": aggregate, "skipped": dict(skipped),
        "diagnostic_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": ["Selected development decisions, not representative frequencies for an entire tournament.",
            "Different states and responses remain correlated within deck/rotation/arm; these are descriptive scores, not independent-sample tests.",
            "Nonterminal rival raises have zero mass in this abstraction and are reported explicitly, not relabeled as all-ins.",
            "Brier score uses four categories; no prior is fitted or promoted using these outcomes.",
            "Monte Carlo range uncertainty and manual prior misspecification remain."]}
    save(output, result)
    print(json.dumps(aggregate, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output.resolve())

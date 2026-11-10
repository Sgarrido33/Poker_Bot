"""Measure sampling/latency only; this is not a playing-strength evaluation."""
from dataclasses import asdict
import json
from pathlib import Path
import statistics

from pokerfight.arena import make_policy
from pokerfight.campaign import save
from pokerfight.domain import Observation
from pokerfight.evaluation import environment
from pokerfight.strategy import BotConfig
from scripts.diagnose_shortstack import cases


def observations():
    fixed = cases()
    result = {"preflop_2p": fixed["heads_up_8bb"],
              "preflop_6p": fixed["utg_speculative_4bb"],
              "defense_3p": fixed["bb_cheap_defense_8bb"]}
    trace = Path("results/shortstack_2026-10-28/validation/paired_pressure_6p_20bb.jsonl")
    best = None
    for line in trace.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["variant"] != "baseline":
            continue
        for entry in record["trace"]:
            obs = Observation.from_dict(entry["observation"])
            if obs.street == "flop" and (best is None or len(obs.opponents) > len(best.opponents)):
                best = obs
    if best is not None:
        result["postflop_6p"] = best
    return result


def benchmark(samples, budget_ms, repeats):
    rows = []
    for name, obs in observations().items():
        # Exclude one warmup. Each measured call gets a fresh model and the
        # same seed; this measures deterministic sample prefixes, not strength.
        make_policy("v2", BotConfig(samples=4000, budget_ms=budget_ms), 283901).decide(obs)
        for count in samples:
            decisions = [make_policy("v2", BotConfig(samples=count, budget_ms=budget_ms), 283901).decide(obs)
                         for _ in range(repeats)]
            row = {"case": name, "requested_samples": count, "budget_ms": budget_ms,
                   "observation": asdict(obs), "repeats": [d.to_dict() for d in decisions],
                   "median_ms": statistics.median(d.elapsed_ms for d in decisions),
                   "median_completed_samples": statistics.median(d.equity.samples for d in decisions if d.equity),
                   "median_standard_error": statistics.median(d.equity.standard_error for d in decisions if d.equity),
                   "fallbacks": sum(d.fallback for d in decisions)}
            rows.append(row)
            print(f"{name}: {count} requested, {row['median_completed_samples']:g} completed, "
                  f"{row['median_ms']:.1f} ms, SE={row['median_standard_error'] * 100:.3f} pp", flush=True)
    return {"environment": environment(), "policy": "frozen_v2", "budget_ms": budget_ms,
            "repetitions": repeats, "rows": rows,
            "limitations": ["Timing and Monte Carlo noise only, not action EV or playing strength.",
                "Four selected public states, not a representative latency percentile.",
                "Default cooperative deadline retained. Partial samples depend on wall clock.",
                "Uncertainty in opponent ranges is not included in Monte Carlo standard error."]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", nargs="+", type=int, default=[4000, 16000, 64000])
    parser.add_argument("--budget-ms", type=int, default=1600)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats debe ser positivo")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    save(target, benchmark(args.samples, args.budget_ms, args.repeats))

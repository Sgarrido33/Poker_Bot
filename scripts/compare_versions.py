"""Complete the registered v1/v2 comparison after the untouched v1 holdout."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

from pokerkit import Automation, NoLimitTexasHoldem

from pokerfight.arena import make_policy, observation, seed_for
from pokerfight.equity import WeightedRange, estimate
from pokerfight.cards import CARD_INDEX
from pokerfight.evaluation import bootstrap_interval, environment, evaluate, simulate
from pokerfight.replay import replay_worst
from pokerfight.strategy import BotConfig

ROOT = Path("results/challenge_2026-10-27")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    if not (ROOT / "holdout/summary.json").exists():
        raise ValueError("Complete la validación v1 antes de comparar la corrección")
    plan = json.loads((ROOT / "correction_protocol.json").read_text(encoding="utf-8"))
    env = environment()
    env["comparison_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    target = ROOT / "comparison"
    target.mkdir(exist_ok=True)
    sessions = []
    settings = plan["paired_sessions"]
    for players in settings["players"]:
        for index in range(settings["independent_seed_groups_per_format"] * players):
            rows = {}
            for policy in ("v1", "v2"):
                original = ROOT / f"holdout/session_{players}p_{index}.json"
                reuse = policy == "v1" and index < players * 2
                path = original if reuse else target / f"session_{policy}_{players}p_{index}.json"
                if path.exists():
                    result = json.loads(path.read_text(encoding="utf-8"))
                else:
                    result = simulate(players, settings["hand_limit"],
                        seed_for(settings["seed_namespace"], "session", players, index // players),
                        BotConfig(samples=settings["samples"]), tuple(settings["opponents"]), True,
                        settings["starting_stack"], settings["small_blind"], settings["big_blind"], 0,
                        hero_kind=policy, blind_interval=settings["blind_interval"], initial_rotation=index % players)
                    result["environment"] = env
                    save(path, result)
                assert result["lineup"]["hero"] == policy
                assert result["config"]["samples"] == settings["samples"]
                rows[policy] = {"hero_chips": result["last_stacks"]["hero"], "survived": result["hero_survived"],
                    "won": result["table_finished"] and result["hero_survived"],
                    "finished": result["table_finished"], "hands": result["played_hands"], "original_holdout": reuse,
                    "fallbacks": result["fallbacks_all_policies"], "latency": result["hero_latency"],
                    "all_in_price_calls": result.get("hero_reasons", {}).get("preflop:all_in_price_call", 0),
                    "chips_conserved": result["chips_conserved"], "path": str(path)}
            sessions.append({"players": players, "index": index, "group": index // players, **rows,
                             "chip_difference": rows["v2"]["hero_chips"] - rows["v1"]["hero_chips"]})
            print(f"comparación {players}p {index + 1}/{settings['independent_seed_groups_per_format'] * players}: "
                  f"v1={rows['v1']['hero_chips']}, v2={rows['v2']['hero_chips']}", flush=True)
    summary = {}
    for players in settings["players"]:
        subset = [row for row in sessions if row["players"] == players]
        groups = [statistics.mean(row["chip_difference"] for row in subset if row["group"] == group)
                  for group in range(settings["independent_seed_groups_per_format"])]
        summary[str(players)] = {"tables_per_variant": len(subset), "independent_groups": len(groups),
            "v1_wins": sum(row["v1"]["won"] for row in subset), "v2_wins": sum(row["v2"]["won"] for row in subset),
            "v1_survived": sum(row["v1"]["survived"] for row in subset), "v2_survived": sum(row["v2"]["survived"] for row in subset),
            "mean_paired_chip_difference": statistics.mean(groups), "group_mean_differences": groups,
            "group_bootstrap_95_interval": bootstrap_interval(groups, seed_for("comparison-bootstrap", players)),
            "v2_all_in_price_calls": sum(row["v2"]["all_in_price_calls"] for row in subset)}
    productions = []
    for policy, baseline, blocks, namespace, label in (
        ("v1", "tag", 8, "challenge-v1-production-check", "production_v1"),
        ("v2", "v1", 4, "challenge-v2-production-comparison", "production_v2_vs_v1")):
        for players in (5, 6):
            path = target / f"{label}_{players}p.json"
            if path.exists():
                report = json.loads(path.read_text(encoding="utf-8"))
            else:
                print(f"configuración 4000 muestras {label}, {players}p", flush=True)
                report = {"environment": env, **evaluate(players, blocks, 3, seed_for(namespace, players),
                    BotConfig(samples=4000), ("pressure", "lag", "tag"), baseline, policy,
                    trace_path=str(target / f"{label}_{players}p.jsonl"))}
                save(path, report)
            productions.append({"label": label, "players": players, "hands_per_variant": report["hands_per_variant"],
                "candidate_bb_per_hand": report["candidate_bb_per_hand"], "delta": report["paired_difference_bb_per_hand"],
                "bootstrap_95_interval": report["paired_block_bootstrap_95_interval"],
                "fallbacks": report["fallbacks_all_policies"], "latency": report["hero_latency"], "path": str(path)})
    # Regression proof: the true fixed rival hand is used only by the test
    # estimator below. It is absent from both policies' observations.
    auto = tuple(a for a in Automation if a not in (Automation.HOLE_DEALING, Automation.BOARD_DEALING, Automation.CARD_BURNING))
    state = NoLimitTexasHoldem.create_state(auto, True, 0, (50, 100), 100, (100, 51), 2)
    state.deal_hole("AsAh", 0)
    state.deal_hole("7s2h", 1)
    obs = observation(state, ("villain", "hero"), "proof", "1", (), 100)
    decisions = {policy: make_policy(policy, BotConfig(samples=4000), 27).decide(obs).to_dict() for policy in ("v1", "v2")}
    known_test_range = WeightedRange.create([((CARD_INDEX["As"], CARD_INDEX["Ah"]), 1.0)])
    exact_hypothesis = estimate(obs, {"villain": known_test_range}, random.Random(843901), 100000)
    proof = {"observation": asdict(obs), "decisions": decisions, "test_only_fixed_rival": ["As", "Ah"],
             "samples": exact_hypothesis.samples, "equity_against_fixed_rival": exact_hypothesis.equity,
             "expected_return_against_fixed_rival": exact_hypothesis.expected_return,
             "incremental_call_ev_against_fixed_rival": exact_hypothesis.expected_return - obs.legal.call_amount}
    assert decisions["v1"]["action"]["kind"] == "fold"
    assert decisions["v2"]["action"]["kind"] == "call"
    assert proof["incremental_call_ev_against_fixed_rival"] > 0
    save(target / "pricing_regression.json", proof)
    replays = []
    for phase in ("development", "holdout"):
        for name in ("basic", "selective", "pressure", "selfplay"):
            for players in (5, 6):
                path = ROOT / phase / f"{name}_{players}p.json"
                result = replay_worst(str(path))
                assert result["matched"], path
                replays.append({"report": str(path), "matched": result["matched"], "same_source": result["same_source"]})
    result = {"environment": env, "session_summary": summary, "paired_sessions": sessions,
        "additional_session_hands": sum(r[p]["hands"] for r in sessions for p in ("v1", "v2") if not r[p]["original_holdout"]),
        "production_reports": productions, "production_hands": sum(r["hands_per_variant"] * 2 for r in productions),
        "fallbacks": sum(r[p]["fallbacks"] for r in sessions for p in ("v1", "v2")) + sum(r["fallbacks"] for r in productions),
        "pricing_regression": str(target / "pricing_regression.json"), "replays": replays,
        "limitations": ["Four independent seed groups per format; rotations are dependent. Win counts are descriptive.",
                        "Single-table finish is not multi-round qualification. No tuning on holdout results."]}
    assert env["source_sha256"] == environment()["source_sha256"], "El código cambió durante la medición"
    save(target / "summary.json", result)
    print(json.dumps({"session_summary": summary, "production_hands": result["production_hands"],
                      "additional_session_hands": result["additional_session_hands"], "fallbacks": result["fallbacks"]}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

from __future__ import annotations

"""Plan, size, and report a non-executed stage-3 poker evaluation."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from statistics import NormalDist

DEFAULT_SOURCE = Path("results/competition_stage2_2026-10-28")
DEFAULT_OUTPUT = Path("results/competition_stage3_plan_2026-10-28/plan.json")
EXPERIMENT_ID = "crossplay-stage3-20261028-03"
HISTORICAL_CANDIDATES = ("v4", "v4rb", "v5")
ARMS = ("v2", "v4", "v4rb", "v5", "v6")
FORMATS = (5, 6)
PRIMARY_SCENARIO = "external_diverse"
CONTROL_SCENARIOS = ("pressure", "copies_v2", "copies_v2_4000", "external_mix")
HORIZON = 128


def seed_for(*parts: object) -> int:
    """Match pokerfight.arena.seed_for without importing runtime dependencies."""
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big")


def _event(row: dict, horizon: int) -> dict[str, int]:
    eliminated_at = row.get("eliminated_at", {}).get("hero")
    bust = eliminated_at is not None and eliminated_at + 1 <= horizon
    win = bool(row["hero_observed_win"] and row["played_hands"] <= horizon)
    return {
        "bust": int(bust),
        "win": int(win),
        "unresolved": int(not (bust or win)),
        "table_finished": int(row["table_finished"] and row["played_hands"] <= horizon),
    }


def load_primary_groups(source: Path, horizon: int = HORIZON) -> tuple[dict, dict]:
    """Recover complete paired group contrasts and outcome counts from stage 2."""
    contrasts = {c: {"chips": {}, "bust": {}} for c in HISTORICAL_CANDIDATES}
    outcome_counts: dict[str, dict[str, int]] = {}
    input_hashes: dict[str, str] = {}
    for n in FORMATS:
        for g in range(4):
            name = f"session_external_diverse_{n}p_{g}.json"
            path = source / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing registered stage-2 group: {path}")
            raw = path.read_bytes()
            input_hashes[name] = hashlib.sha256(raw).hexdigest()
            job = json.loads(raw)
            if job.get("job") != ["session", PRIMARY_SCENARIO, n, g]:
                raise ValueError(f"Unexpected group identity in {name}")
            indexed = {(r["variant"], r["rotation"]): r for r in job["sessions"]}
            expected = {(arm, rot) for arm in ("v2", *HISTORICAL_CANDIDATES) for rot in range(n)}
            if set(indexed) != expected:
                raise ValueError(f"Incomplete paired arms/rotations in {name}")
            for c in HISTORICAL_CANDIDATES:
                chips_delta, bust_delta = [], []
                for rot in range(n):
                    ref, cand = indexed[("v2", rot)], indexed[(c, rot)]
                    chips_delta.append((cand["last_stacks"]["hero"] - ref["last_stacks"]["hero"]) / 800)
                    bust_delta.append(_event(cand, horizon)["bust"] - _event(ref, horizon)["bust"])
                contrasts[c]["chips"].setdefault(n, []).append(statistics.mean(chips_delta))
                contrasts[c]["bust"].setdefault(n, []).append(statistics.mean(bust_delta))
            for arm in ("v2", *HISTORICAL_CANDIDATES):
                rows = [indexed[(arm, rot)] for rot in range(n)]
                counts = outcome_counts.setdefault(arm, {k: 0 for k in ("tables", "bust", "win", "unresolved", "table_finished", "censored")})
                counts["tables"] += len(rows)
                counts["bust"] += sum(_event(r, horizon)["bust"] for r in rows)
                counts["win"] += sum(_event(r, horizon)["win"] for r in rows)
                counts["unresolved"] += sum(_event(r, horizon)["unresolved"] for r in rows)
                counts["table_finished"] += sum(_event(r, horizon)["table_finished"] for r in rows)
                counts["censored"] += sum(_event(r, horizon)["unresolved"] and not _event(r, horizon)["table_finished"] for r in rows)
    return {"contrasts": contrasts, "outcome_counts": outcome_counts}, input_hashes


def _pooled_stratum_sd(values_by_format: dict[int, list[float]]) -> dict:
    by_format = {}
    for n in FORMATS:
        values = values_by_format[n]
        by_format[str(n)] = {"groups": len(values), "mean": statistics.mean(values), "sd": statistics.stdev(values) if len(values) > 1 else None}
    if any(by_format[str(n)]["sd"] is None for n in FORMATS):
        raise ValueError("At least two independent groups per format are required")
    sd5, sd6 = (by_format[str(n)]["sd"] for n in FORMATS)
    return {"by_format": by_format, "stratum_rms_sd": math.sqrt((sd5**2 + sd6**2) / 2)}


def required_groups(sd: float, effect: float, family_alpha: float = .05,
                    comparisons: int = 2, power: float = .80) -> int:
    """Normal-approximation balanced n per format, Bonferroni two-sided alpha."""
    if sd < 0 or effect <= 0 or comparisons < 1 or not 0 < family_alpha < 1 or not 0 < power < 1:
        raise ValueError("Invalid sizing inputs")
    z_alpha = NormalDist().inv_cdf(1 - family_alpha / (2 * comparisons))
    z_power = NormalDist().inv_cdf(power)
    # Equal-weight mean of two independent stratum means, n groups in each:
    # Var(delta_bar) = (sd5^2 + sd6^2)/(4n) = sd_proxy^2/(2n).
    return max(2, math.ceil(((z_alpha + z_power) * sd / (math.sqrt(2) * effect)) ** 2))


def detectable_effect(sd: float, groups_per_format: int, family_alpha: float = .05,
                      comparisons: int = 2, power: float = .80) -> float:
    z_alpha = NormalDist().inv_cdf(1 - family_alpha / (2 * comparisons))
    z_power = NormalDist().inv_cdf(power)
    return (z_alpha + z_power) * sd / math.sqrt(2 * groups_per_format)


def materialize_seed_manifest(source: Path, primary_groups: int,
                              control_groups: int, horizon: int,
                              experiment_id: str = EXPERIMENT_ID) -> dict:
    planned: set[int] = set()
    group_seeds: dict[str, dict[str, list[int]]] = {}
    for scenario, groups in ((PRIMARY_SCENARIO, primary_groups), *((s, control_groups) for s in CONTROL_SCENARIOS)):
        group_seeds[scenario] = {}
        for n in FORMATS:
            group_seeds[scenario][str(n)] = []
            for group in range(groups):
                base = seed_for(experiment_id, "crossplay-session-01", scenario, n, group)
                group_seeds[scenario][str(n)].append(base)
                planned.update(seed_for(base, "deck", hand) for hand in range(horizon))
    historical: set[int] = set()
    files = 0
    for path in source.parent.rglob("*.jsonl"):
        files += 1
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if "deck_seed" in row:
                    historical.add(row["deck_seed"])
    overlap = planned & historical
    if overlap:
        raise ValueError(f"Planned stage-3 seeds overlap {len(overlap)} historical deck seeds")
    encoded = "\n".join(str(seed) for seed in sorted(planned)).encode("ascii")
    return {
        "group_seeds_by_scenario_and_format": group_seeds,
        "planned_unique_deck_seed_count": len(planned),
        "planned_deck_seed_set_sha256": hashlib.sha256(encoded).hexdigest(),
        "historical_jsonl_files_scanned": files,
        "historical_unique_deck_seeds": len(historical),
        "overlap_count": 0,
        "seed_collision_check": "passed against all JSONL files below results/ at planning time",
    }


def build_plan(source: Path = DEFAULT_SOURCE, primary_groups_per_format: int = 40,
               control_groups_per_format: int = 8, horizon: int = HORIZON,
               experiment_id: str = EXPERIMENT_ID) -> dict:
    if primary_groups_per_format < 4 or control_groups_per_format < 4:
        raise ValueError("Both proposed allocations must exceed the four stage-2 groups")
    if horizon != HORIZON:
        raise ValueError("Only H=128 is supported for stack sizing; stage-2 files store last_stacks at 128, not earlier horizons")
    observed, hashes = load_primary_groups(source, horizon)
    seed_manifest = materialize_seed_manifest(source, primary_groups_per_format, control_groups_per_format,
                                              horizon, experiment_id)
    alpha, power, tests = .05, .80, 2
    mde = {"chips_fraction_of_starting_stack": [.05, .10, .20], "bust_probability_absolute": [.025, .05, .10]}
    effects = {
        "chips": {"relevant_effect": .10, "unit": "fraction of 800-chip starting stack", "direction": "v6 minus v2 > 0"},
        "bust": {"relevant_effect": .05, "unit": "absolute probability at H", "direction": "v6 minus v2 < 0"},
    }
    variance_proxy = {}
    sizing = {}
    for metric, spec in effects.items():
        by_candidate = {c: _pooled_stratum_sd(observed["contrasts"][c][metric]) for c in HISTORICAL_CANDIDATES}
        conservative = max(v["stratum_rms_sd"] for v in by_candidate.values())
        sensitivity = [{"effect": effect, "groups_per_format_for_80pct_power": required_groups(conservative, effect, alpha, tests, power)}
                       for effect in (mde["chips_fraction_of_starting_stack"] if metric == "chips" else mde["bust_probability_absolute"])]
        variance_proxy[metric] = {
            "historical_candidate_sd_by_format": by_candidate,
            "planning_sd_proxy_max_historical_candidate": conservative,
            "note": "v6 has no observed variance; max historical v4/v4rb/v5 SD is only a provisional planning proxy, not a validated v6 variance.",
        }
        sizing[metric] = {
            "proxy_sd": conservative,
            "relevant_effect": spec["relevant_effect"],
            "required_groups_per_format": required_groups(conservative, spec["relevant_effect"], alpha, tests, power),
            "sensitivity": sensitivity,
            "mde_at_primary_groups": detectable_effect(conservative, primary_groups_per_format, alpha, tests, power),
        }
    required = max(v["required_groups_per_format"] for v in sizing.values())
    primary_tables = primary_groups_per_format * len(ARMS) * sum(FORMATS)
    control_tables = control_groups_per_format * len(CONTROL_SCENARIOS) * len(ARMS) * sum(FORMATS)
    total_tables = primary_tables + control_tables
    total_groups = primary_groups_per_format * len(FORMATS) + control_groups_per_format * len(CONTROL_SCENARIOS) * len(FORMATS)
    plan = {
        "plan_id": experiment_id,
        "created_local_date": "2026-10-28",
        "status": "planning_only_not_registered_not_executed",
        "source": {"path": str(source), "stage": 2, "primary_scenario": PRIMARY_SCENARIO, "groups_per_format_observed": 4, "group_file_sha256": hashes},
        "inference_target": "v6 versus v2 only, with two co-primary outcomes; other candidate and control contrasts are exploratory.",
        "estimand": "Equal-weight mean paired difference across 5-player and 6-player strata; average seat-rotation differences within each complete independent seed group first.",
        "observed_stage2_variance_data": observed["contrasts"],
        "stage2_outcomes_by_arm": observed["outcome_counts"],
        "v6_experimental_configuration": {
            "status": "existing implementation: pokerfight/terminal_search.py; freeze this file and dependency/source hashes in the immutable registration protocol",
            "parent_policy": "v4rb",
            "hero_profile": {"samples": 4096, "budget_ms": 3500, "matches": "v4rb"},
            "isolated_change": "Restrict the search alternatives to fold/check and effective terminal commits as implemented in terminal_search.py; preserve the pre-search local baseline action as arm zero.",
            "baseline_semantics": "The retained arm-zero action is the inherited pre-search v2/equity decision, not the final output of a full v4rb run. v6 uses the integrated search with a restricted action set; it does not execute v4rb and filter its final decision.",
            "limitations": "This restriction does not guarantee fewer all-ins, lower risk, or better outcomes; the value model omits later bets/resubidas and an all-in does not prevent opponent side-pot betting.",
            "all_other_policy_parameters": "Use the v4rb profile and parameters (4096 samples, 3500 ms); freeze exact dependency/source hashes at registration.",
            "v6_is_a_new_experimental_arm": True,
        },
        "sample_size_method": {
            "independent_unit": "One complete session seed group within scenario and player-count stratum. Rotations, arms, and hands within a group are not independent units.",
            "paired_metric": "Within each group average candidate-minus-v2 over all n seat rotations; equal-weight the 5p and 6p stratum means.",
            "stratum_sd_proxy": "sqrt((s_5^2+s_6^2)/2). With n independent groups in each format, SE of the equal-weight contrast is sqrt((s_5^2+s_6^2)/(4n)) = proxy/sqrt(2n).",
            "confirmatory_family": "Two co-primary tests for v6 versus v2 (chips and bust); Bonferroni two-sided family alpha 0.05/2.",
            "power": power,
            "approximation": "Normal approximation using the exact two-stratum equal-weight SE above. v6 has no historical variance; use the largest stage-2 proxy among v4/v4rb/v5 provisionally. Only four stage-2 groups per format inform these SDs, so N is unstable and not validated power.",
        },
        "assumed_minimum_relevant_effects": effects,
        "sensitivity_effects": mde,
        "variance_proxy": variance_proxy,
        "v6_primary_sizing": sizing,
        "required_groups_per_format_for_both_v6_outcomes": required,
        "proposed_configurable_protocol": {
            "primary": {"scenario": PRIMARY_SCENARIO, "arms": list(ARMS), "groups_per_format": primary_groups_per_format,
                        "groups_total": primary_groups_per_format * len(FORMATS), "purpose": "v6 versus v2 two-endpoint screening; v4/v4rb/v5 contrasts exploratory"},
            "controls": {"scenarios": list(CONTROL_SCENARIOS), "arms": list(ARMS), "groups_per_format_each": control_groups_per_format,
                         "groups_total": control_groups_per_format * len(CONTROL_SCENARIOS) * len(FORMATS), "purpose": "diagnostic/exploratory only; no confirmatory claims or multiplicity-adjusted follow-up"},
            "players": list(FORMATS),
            "rotations_per_group": {"5": 5, "6": 6},
            "session_hand_limit": horizon,
            "starting_stack": 800,
            "blinds": {"small": 50, "big": 100, "ante": 0, "blind_interval": 0},
            "primary_tables_maximum": primary_tables,
            "control_tables_maximum": control_tables,
            "tables_maximum": total_tables,
            "groups_total_across_scenarios_and_formats": total_groups,
            "hand_executions_maximum": total_tables * horizon,
            "purpose": "Development screening only. Do not infer official-tournament performance or promote v6; any future validation must use a newly frozen protocol and new seeds.",
        },
        "exploratory_arms_and_controls": {
            "non_v6_candidate_contrasts": "v4/v4rb/v5 versus v2 in external_diverse are descriptive only; not part of the two-test confirmatory family.",
            "controls": "pressure, copies_v2, copies_v2_4000, external_mix retained at 8 independent groups per format each; descriptive, not confirmatory.",
            "future_validation": "If v6 is selected for further work, run a separate future validation with fresh ID/seeds, frozen v6 hash, and official rules/decision metric when available.",
        },
        "multiplicity_and_decision": {
            "primary_tests": tests,
            "correction": "Bonferroni, two-sided family alpha 0.05 across the two v6-versus-v2 outcomes.",
            "selection": "Report both adjusted intervals and by-format chip deltas. This stage is an experimental screen; it cannot establish official tournament fitness or automatic promotion.",
            "control_inference": "All control contrasts and other candidates are exploratory; do not attach confirmatory language or significance claims.",
            "default": "v2 remains default. v6 requires a distinct future validation before any tournament recommendation.",
        },
        "planned_interval_method": {
            "estimator": "Average paired seat-rotation deltas within each group; give 5p and 6p stratum means equal weight.",
            "method": "Stratified percentile bootstrap of complete paired groups, independently within each player-count stratum; never resample hands or rotations as independent units.",
            "bootstrap_replicates": 20000,
            "bootstrap_seed": seed_for(experiment_id, "inference-bootstrap"),
            "primary_interval_level_each": .975,
            "family_coverage_nominal": .95,
            "coverage_limitation": "Approximate bootstrap coverage; normal sizing and historical proxy variance do not guarantee power or coverage.",
            "fixed_allocation": "Complete the registered allocation once; no profit-based stopping, group-count changes or seed replacement after examining candidate outcomes.",
        },
        "outcomes_censoring": {
            "chips": "Observed hero stack at H divided by 800, including administrative censoring; not prize equity or final rank.",
            "bust": "Cumulative observed hero elimination by H.",
            "competing_event": "Observed sole-survivor win is a competing event, not a bust or censor.",
            "unresolved": "Neither bust nor observed sole-survivor win by H; includes censored leaders.",
            "censoring": "Report bust, observed win, unresolved, table completion and administrative censor counts/rates by arm, scenario and format at H; never assign censored rank or victory.",
            "horizons": [24, 64, horizon],
        },
        "fixed_seed_policy": {
            "experiment_id": experiment_id,
            "derivation": "Use pokerfight.arena.seed_for(experiment_id, 'crossplay-session-01', scenario, players, group), then derive deck seed as seed_for(group_seed, 'deck', hand_index); arms and rotations share each group's hand-index deck seeds as stage 2 did.",
            "group_indices": "0-based, disjoint indices within each scenario and format as materialized below.",
            **seed_manifest,
            "seeds_materialized": True,
        },
        "pending_before_registration": [
            "Review the existing pokerfight/terminal_search.py behavior; freeze its hash and all source/dependency hashes in the immutable registration protocol.",
            "Confirm external opponent eligibility/licensing and adapted-runtime validity.",
            "Freeze all arm quotas/dependencies; run candidate-blind technical/censoring pilot, then register protocol and fresh seed ledger.",
            "Revisit the v6 variance proxy and minimum relevant effects with the decision owner; stage-2 estimates have four groups per format only.",
        ],
        "pending_for_official_tournament_inference": [
            "Official tournament rules, blind schedule, antes, rebuys, payout structure, format and decision metric are unknown; this blocks official-tournament claims, not a local evaluation under the stated proxy assumptions.",
        ],
    }
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--id", default=EXPERIMENT_ID,
                        help="Fresh experiment id; completed campaign seeds cannot be reused")
    parser.add_argument("--primary-groups-per-format", type=int, default=40)
    parser.add_argument("--control-groups-per-format", type=int, default=8)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use --output with a new path; preserve existing plans")
    plan = build_plan(args.source, args.primary_groups_per_format, args.control_groups_per_format,
                      args.horizon, experiment_id=args.id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cfg = plan["proposed_configurable_protocol"]
    print(json.dumps({"output": str(args.output), "plan_id": plan["plan_id"],
                      "primary_groups_per_format": args.primary_groups_per_format,
                      "control_groups_per_format": args.control_groups_per_format,
                      "required_groups_per_format_for_v6": plan["required_groups_per_format_for_both_v6_outcomes"],
                      "tables_maximum": cfg["tables_maximum"],
                      "hand_executions_maximum": cfg["hand_executions_maximum"]}, indent=2))


if __name__ == "__main__":
    main()

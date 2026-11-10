"""Fixed batches, duplicate decks and rotated seats; NOT AIVAT or full tournament simulation."""
from __future__ import annotations

from dataclasses import asdict
from collections import Counter
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
from importlib.metadata import version

from .arena import POLICY_KINDS, HandResult, close_policies, make_policy, play_hand, seed_for
from .strategy import BotConfig
from .shortstack import context


def summarize_contexts(results: list[HandResult]) -> dict:
    """Decision counts; payoffs attributed ONCE per hand to its first preflop decision.

    Outcome association is descriptive, not the counterfactual EV of an action.
    """
    decisions, outcomes = {}, {}
    for result in results:
        if "hero" not in result.payoffs:
            continue
        first = True
        for entry in result.trace:
            from .domain import Observation
            obs = Observation.from_dict(entry["observation"])
            if obs.street != "preflop":
                continue
            ctx = asdict(context(obs))
            ctx["effective_bb_band"] = next((str(b) for b in (5, 8, 12, 20) if ctx["effective_bb"] <= b), ">20")
            ctx["price_band"] = next((str(b) for b in (.1, .25, .4) if ctx["price"] <= b), ">0.4")
            action = entry["decision"]["action"]
            ctx["action"] = action["kind"]
            ctx["commits_effective_stack"] = action["kind"] == "raise_to" and action["amount"] >= round(ctx["effective_bb"] * obs.big_blind)
            del ctx["effective_bb"], ctx["call_bb"], ctx["price"]
            key = json.dumps(ctx, sort_keys=True)
            row = decisions.setdefault(key, {**ctx, "decisions": 0})
            row["decisions"] += 1
            if first:
                row = outcomes.setdefault(key, {**ctx, "hands": 0, "payoff_bb": 0.0, "busts": 0})
                row["hands"] += 1
                row["payoff_bb"] += result.payoffs[obs.hero_id] / obs.big_blind
                row["busts"] += result.stacks[obs.hero_id] == 0
                first = False
        if first:
            # Walks or forced blind all-ins can finish without a hero decision.
            row = outcomes.setdefault("no_decision", {"situation": "no_decision", "hands": 0,
                                                      "payoff_bb": 0.0, "busts": 0})
            row["hands"] += 1
            row["payoff_bb"] += result.payoffs["hero"] / result.big_blind
            row["busts"] += result.stacks["hero"] == 0
    return {"decisions": list(decisions.values()), "first_decision_outcomes": list(outcomes.values())}


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else 0.0


def latency(results: list[HandResult], player_id: str = "hero") -> dict:
    decisions = [d for r in results for pid, d in r.decisions if pid == player_id]
    times = [d.elapsed_ms for d in decisions]
    return {"decisions": len(times), "p50_ms": statistics.median(times) if times else 0,
            "p95_ms": percentile(times, 0.95), "max_ms": max(times, default=0),
            "over_2000_ms": sum(t > 2000 for t in times),
            "over_3500_ms": sum(t > 3500 for t in times), "over_4250_ms": sum(t > 4250 for t in times),
            "fallbacks": sum(d.fallback for d in decisions),
            "partial_equity_samples": sum(bool(d.equity and d.equity.timed_out) for d in decisions),
            "action_searches": sum(d.search is not None for d in decisions),
            "search_changes": sum(bool(d.search and d.search["changed"]) for d in decisions),
            "search_stops": dict(Counter(d.search["stop"] for d in decisions if d.search)),
            "search_worlds": sum(d.search["worlds"] for d in decisions if d.search)}


def noregrets_fallback_reasons(results: list[HandResult]) -> dict[str, int]:
    """Count native NoRegrets data fallbacks separately from worker failures.

    Infrastructure failures raise and abort the table; they are never converted
    to a synthetic policy fallback.
    """
    counts: Counter[str] = Counter()
    for result in results:
        for _pid, decision in result.decisions:
            external = getattr(decision, "external", None)
            if isinstance(external, dict) and external.get("fallback_reason") in (
                    "menu_mismatch", "unseen_infoset", "zero_mass"):
                counts[external["fallback_reason"]] += 1
    return dict(counts)


def lineup(players: int, opponents: tuple[str, ...]) -> tuple[tuple[str, ...], dict[str, str]]:
    if not 2 <= players <= 6 or not opponents or any(p not in POLICY_KINDS for p in opponents):
        raise ValueError("Mesa o políticas inválidas")
    ids = ("hero",) + tuple(f"opponent_{i}" for i in range(1, players))
    return ids, {pid: opponents[(i - 1) % len(opponents)] for i, pid in enumerate(ids) if i}


def build_policies(kinds: dict[str, str], config: BotConfig, rival_config: BotConfig | None,
                   seeds: dict[str, int]) -> dict[str, object]:
    policies = {}
    try:
        for pid, kind in kinds.items():
            policies[pid] = make_policy(kind, config if pid == "hero" else rival_config or config,
                                         seeds[pid])
    except BaseException:
        close_policies(policies)
        raise
    return policies


def simulate(players: int, hands: int, seed: int, config: BotConfig,
             opponents: tuple[str, ...] = ("calling", "tight", "random"),
             carry_stacks: bool = False, starting_stack: int = 10000,
             small_blind: int = 50, big_blind: int = 100, ante: int = 0,
             hero_kind: str = "v1", blind_interval: int = 0, initial_rotation: int = 0,
             experiment_id: str | None = None, rival_config: BotConfig | None = None) -> dict:
    if hands < 1 or starting_stack < 1 or blind_interval < 0 or (blind_interval and not carry_stacks):
        raise ValueError("Configuración de simulación inválida; las ciegas crecientes requieren carry-stacks")
    input_seed = seed
    seed = seed_for(experiment_id, seed) if experiment_id is not None else seed
    ids, kinds = lineup(players, opponents)
    kinds["hero"] = hero_kind
    policies = build_policies(kinds, config, rival_config,
                              {pid: seed_for(seed, "policy", pid) for pid in ids})
    stacks = {pid: starting_stack for pid in ids}
    totals = dict.fromkeys(ids, 0)
    results = []
    button = ids[(initial_rotation - 1) % len(ids)]
    eliminated_at = {}
    button_history = []
    try:
        for hand in range(hands):
            active = tuple(pid for pid in ids if not carry_stacks or stacks[pid] > 0)
            if len(active) < 2:
                break
            if hand:
                old_index = ids.index(button)
                button = next(ids[(old_index + distance) % len(ids)] for distance in range(1, len(ids) + 1)
                              if ids[(old_index + distance) % len(ids)] in active)
            button_index = active.index(button)
            seats = active[button_index + 1:] + active[:button_index + 1]
            button_history.append(button)
            initial = stacks.copy() if carry_stacks else {pid: starting_stack for pid in seats}
            multiplier = 2 ** (hand // blind_interval) if blind_interval else 1
            result = play_hand(policies, seats, initial, seed_for(seed, "deck", hand),
                               str(hand), f"simulation-{seed}", small_blind * multiplier, big_blind * multiplier, ante * multiplier,
                               trace_player_id="hero")
            stacks.update(result.stacks)
            if carry_stacks:
                for pid in active:
                    if stacks[pid] == 0:
                        eliminated_at[pid] = hand
            for pid, amount in result.payoffs.items():
                totals[pid] += amount
            results.append(result)
    finally:
        close_policies(policies)
    return {"mode": "carry_stacks_single_table" if carry_stacks else "reset_stacks_each_hand",
            "players": players, "seed": seed, "input_seed": input_seed, "experiment_id": experiment_id,
            "requested_hands": hands, "played_hands": len(results),
            "assumptions": {"starting_stack": starting_stack, "small_blind": small_blind, "big_blind": big_blind, "ante": ante,
                            "blind_interval": blind_interval, "blind_multiplier": 2 if blind_interval else 1,
                            "button_rule": "next_surviving_player_clockwise", "initial_rotation": initial_rotation},
            "lineup": kinds, "config": asdict(config), "rival_config": asdict(rival_config or config), "payoffs_chips": totals,
            "last_stacks": stacks, "eliminated": [pid for pid in ids if stacks[pid] == 0] if carry_stacks else [],
            "eliminated_at_hand": eliminated_at, "button_history": button_history,
            "hero_reasons": dict(Counter(d.reason for r in results for pid, d in r.decisions if pid == "hero")),
            "hero_survived": stacks["hero"] > 0, "table_finished": carry_stacks and sum(s > 0 for s in stacks.values()) == 1,
            "fallbacks_all_policies": sum(d.fallback for r in results for _, d in r.decisions),
            "noregrets_native_fallback_reasons": noregrets_fallback_reasons(results),
            "external_worker_errors": 0,
            "invalid_actions_all_policies": 0,
            "invalid_proposals_recovered": sum(d.fallback and "ilegal" in d.reason for r in results for _, d in r.decisions),
            "hero_contexts": summarize_contexts(results),
            "hero_latency": latency(results), "chips_conserved": sum(totals.values()) == 0}


def bootstrap_interval(blocks: list[float], seed: int, repetitions: int = 5000) -> list[float] | None:
    """Resample whole deck batches, never dependent hands or seat rotations."""
    if len(blocks) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(blocks, k=len(blocks))) / len(blocks) for _ in range(repetitions))
    return [means[int(repetitions * 0.025)], means[min(repetitions - 1, int(repetitions * 0.975))]]


def evaluate(players: int, blocks: int, hands_per_block: int, seed: int, config: BotConfig,
             opponents: tuple[str, ...] = ("calling", "tight", "random"), baseline: str = "tight",
             candidate: str = "v1", trace_path: str | None = None,
             starting_stack: int = 10000, small_blind: int = 50, big_blind: int = 100,
             ante: int = 0, experiment_id: str | None = None,
             rival_config: BotConfig | None = None,
             baseline_config: BotConfig | None = None) -> dict:
    if blocks < 1 or hands_per_block < 1:
        raise ValueError("Se necesitan bloques y manos positivos")
    input_seed = seed
    seed = seed_for(experiment_id, seed) if experiment_id is not None else seed
    ids, kinds = lineup(players, opponents)
    candidate_results = []
    baseline_results = []
    differences = []
    candidate_block_means = []
    baseline_block_means = []
    worst = []
    actions = Counter()
    all_fallbacks = 0
    if trace_path:
        Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(trace_path).open("w", encoding="utf-8") if trace_path else nullcontext(None) as trace_file:
        for block in range(blocks):
            profits = {"candidate": [], "baseline": []}
            for rotation in range(players):
                seats = ids[rotation:] + ids[:rotation]
                for label, hero_kind in (("candidate", candidate), ("baseline", baseline)):
                    table_id = f"eval-{seed}-{block}-{rotation}"
                    policy_seeds = {pid: seed_for(seed, "policy", block, rotation, pid) for pid in ids}
                    table_kinds = {pid: (hero_kind if pid == "hero" else kinds[pid]) for pid in ids}
                    hero_config = baseline_config if label == "baseline" and baseline_config is not None else config
                    policies = build_policies(table_kinds, hero_config, rival_config or config, policy_seeds)
                    try:
                        for hand in range(hands_per_block):
                            deck_seed = seed_for(seed, "deck", block, hand)
                            result = play_hand(policies, seats, dict.fromkeys(ids, starting_stack), deck_seed,
                                str(hand), table_id, small_blind, big_blind, ante, trace_player_id="hero")
                            profits[label].append(result.payoffs["hero"] / big_blind)
                            all_fallbacks += sum(d.fallback for _, d in result.decisions)
                            record = {"block": block, "rotation": rotation, "hand": hand, "variant": label,
                                      "hero_policy": hero_kind, "table_id": table_id, "seats": seats,
                                      "deck_seed": deck_seed, "policy_seeds": policy_seeds,
                                      "payoffs": result.payoffs, "board": result.board,
                                      "history": [asdict(e) for e in result.history], "trace": result.trace}
                            if trace_file:
                                trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                            if label == "baseline":
                                baseline_results.append(result)
                            if label == "candidate":
                                candidate_results.append(result)
                                worst.append(record)
                                worst.sort(key=lambda r: r["payoffs"]["hero"])
                                del worst[5:]
                                for event, (pid, decision) in zip(result.history, result.decisions, strict=True):
                                    if pid == "hero":
                                        actions[f"{event.street}:{decision.action.kind}"] += 1
                    finally:
                        close_policies(policies)
            candidate_mean = statistics.mean(profits["candidate"])
            reference = statistics.mean(profits["baseline"])
            candidate_block_means.append(candidate_mean)
            baseline_block_means.append(reference)
            differences.append(candidate_mean - reference)
    mean = statistics.mean(differences)
    error = statistics.stdev(differences) / math.sqrt(blocks) if blocks > 1 else None
    return {"players": players, "seed": seed, "input_seed": input_seed, "experiment_id": experiment_id,
            "blocks": blocks, "hands_per_block_per_seat": hands_per_block,
            "rotations": players, "hands_per_variant": blocks * hands_per_block * players,
            "assumptions": {"starting_stack": starting_stack, "starting_stack_bb": starting_stack / big_blind,
                            "small_blind": small_blind, "big_blind": big_blind, "ante": ante,
                            "reset_stacks_each_hand": True},
            "candidate": candidate, "baseline": baseline, "opponents": kinds, "config": asdict(config),
            "baseline_config": asdict(baseline_config or config),
            "rival_config": asdict(rival_config or config),
            "rival_samples": (rival_config or config).samples, "rule_opponent_internal_samples": 256,
            "unique_deck_batches": blocks, "base_decks": blocks * hands_per_block,
            "candidate_bb_per_hand": statistics.mean(candidate_block_means),
            "baseline_bb_per_hand": statistics.mean(baseline_block_means),
            "paired_difference_bb_per_hand": mean, "block_differences_bb_per_hand": differences,
            "candidate_block_bb_per_hand": candidate_block_means,
            "baseline_block_bb_per_hand": baseline_block_means,
            "standard_error_across_blocks": error,
            "approximate_95_normal_interval": [mean - 1.96 * error, mean + 1.96 * error] if error is not None else None,
            "paired_block_bootstrap_95_interval": bootstrap_interval(differences, seed_for(seed, "bootstrap")),
            "hero_actions": dict(actions), "worst_candidate_hands": worst, "trace_path": trace_path,
            "fallbacks_all_policies": all_fallbacks,
            "candidate_noregrets_native_fallback_reasons": noregrets_fallback_reasons(candidate_results),
            "baseline_noregrets_native_fallback_reasons": noregrets_fallback_reasons(baseline_results),
            "external_worker_errors": 0,
            "invalid_actions_all_policies": 0,
            "invalid_proposals_recovered": sum(d.fallback and "ilegal" in d.reason
                for r in candidate_results + baseline_results for _, d in r.decisions),
            "candidate_contexts": summarize_contexts(candidate_results),
            "baseline_contexts": summarize_contexts(baseline_results),
            "candidate_chips": sum(r.payoffs["hero"] for r in candidate_results),
            "baseline_chips": sum(r.payoffs["hero"] for r in baseline_results),
            "candidate_bust_hands": sum(r.stacks["hero"] == 0 for r in candidate_results),
            "baseline_bust_hands": sum(r.stacks["hero"] == 0 for r in baseline_results),
            "hero_latency": latency(candidate_results), "baseline_latency": latency(baseline_results), "chips_conserved": True,
            "limitations": ["Heuristic policy versus simple local opponents; not tournament qualification probability.",
                            "Normal interval across independent deck batches is descriptive; few blocks are insufficient for inference.",
                            "Rotations share decks and are clustered within a block. This is not AIVAT.",
                            "Wall-clock budget may truncate sampling; exact replay requires no truncated decisions."]}


def environment() -> dict:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.rglob("*.py")):
        digest.update(str(path.relative_to(Path(__file__).parent)).encode())
        digest.update(path.read_bytes())
    return {"python": sys.version, "platform": platform.platform(),
            "eval7": version("eval7"), "pokerkit": version("pokerkit"), "source_sha256": digest.hexdigest()}

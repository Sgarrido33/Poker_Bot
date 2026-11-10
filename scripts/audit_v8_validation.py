"""Independent reconstruction of every saved v8d hand and interrupted prefix.

This auditor was added after registration; it does not change frozen policies,
samples, metrics, seeds or advancement criteria.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random

from pokerfight.arena import seed_for
from pokerfight.cards import DECK
from pokerfight.domain import Action, Observation
from pokerfight.campaign import save
from scripts import competition_experiment as executor
from scripts import v8_validation as experiment


def strip_times(value):
    if isinstance(value, dict):
        return {k: strip_times(v) for k, v in value.items() if k != "elapsed_ms"}
    if isinstance(value, list):
        return [strip_times(v) for v in value]
    return value


def reconstruct(row, plan, trace_path, phase_settings=None):
    _, scenario, n, group = row["job"]
    stack = plan["session"]["starting_stack"]
    ids, kinds = executor.lineup(n, tuple(plan["scenarios"][scenario]))
    if row["opponents"] != kinds:
        raise ValueError("Opponent composition differs from protocol")
    if phase_settings is not None:
        base = seed_for(phase_settings["experiment_id"], "crossplay-session-01", scenario, n, group)
        policy_seeds = {rotation: {pid: seed_for(base, "policy", rotation, pid) for pid in ids}
                        for rotation in range(n)}
        table_ids = {rotation: executor.table_key(base, rotation, "session") for rotation in range(n)}
    chance = {}
    state = {}
    counts = Counter()
    for line in trace_path.open(encoding="utf-8"):
        r = json.loads(line)
        if r["mode"] != "session" or r["group"] != group:
            raise ValueError("Trace belongs to another job")
        key = r["variant"], r["rotation"]
        if key not in state:
            state[key] = {"stacks": dict.fromkeys(ids, stack), "played": 0,
                          "button": ids[(r["rotation"] - 1) % n],
                          "eliminated_at": {}, "hero_rank": None, "counts": Counter()}
        current = state[key]
        if r["hand"] != current["played"]:
            raise ValueError("Missing, duplicate or unordered hand")
        before = current["stacks"]
        active = {pid for pid, chips in before.items() if chips > 0}
        if set(r["seats"]) != active or set(r["stacks"]) != active or set(r["payoffs"]) != active:
            raise ValueError("Active seat set differs")
        ordered_active = tuple(pid for pid in ids if pid in active)
        if current["played"]:
            old = ids.index(current["button"])
            current["button"] = next(ids[(old + step) % n] for step in range(1, n + 1)
                                     if ids[(old + step) % n] in active)
        button = ordered_active.index(current["button"])
        expected_seats = ordered_active[button + 1:] + ordered_active[:button + 1]
        if tuple(r["seats"]) != expected_seats:
            raise ValueError("Button/seat rotation differs")
        if phase_settings is not None:
            expected_deck = seed_for(base, "deck", r["hand"])
            if r["deck_seed"] != expected_deck or r["policy_seeds"] != policy_seeds[r["rotation"]]:
                raise ValueError("Deck/policy seeds differ from registered namespace")
            if r["hand"] not in chance:
                chance[r["hand"]] = list(DECK)
                random.Random(expected_deck).shuffle(chance[r["hand"]])
            deck = chance[r["hand"]]
            offset = 2 * len(r["seats"])
            expected_board = deck[offset + 1:offset + 4] + [deck[offset + 5], deck[offset + 7]]
            if r["board"] != expected_board[:len(r["board"])]:
                raise ValueError("Saved board differs from preset chance cards")
        if any(r["stacks"][pid] - r["payoffs"][pid] != before[pid] for pid in active):
            raise ValueError("Hand does not continue previous stacks")
        if sum(r["payoffs"].values()) != 0 or any(v < 0 for v in r["stacks"].values()):
            raise ValueError("Invalid hand chip accounting")
        for item in r["trace"]:
            obs = Observation.from_dict(item["observation"])
            action = Action(**item["decision"]["action"])
            if obs.hero_id != "hero" or not action.is_legal(obs):
                raise ValueError("Invalid hero observation/action")
            if phase_settings is not None:
                hero_index = r["seats"].index("hero")
                if (obs.table_id != table_ids[r["rotation"]] or obs.hand_id != str(r["hand"])
                        or obs.button_index != len(r["seats"]) - 1
                        or [player.player_id for player in obs.players] != r["seats"]
                        or list(obs.hole_cards) != deck[2 * hero_index:2 * hero_index + 2]
                        or list(obs.board) != expected_board[:len(obs.board)]):
                    raise ValueError("Observation identity/seats/chance cards differ")
            index = len(obs.history)
            event = r["history"][index]
            if event["player_id"] != "hero" or event["kind"] != action.kind:
                raise ValueError("Hero decision differs from public action")
            if action.kind == "raise_to" and event["amount"] != action.amount:
                raise ValueError("Hero raise amount differs")
            if [dict(vars(e)) for e in obs.history] != r["history"][:index]:
                raise ValueError("Observation contains wrong public history")
            counts["hero_decisions"] += 1
        current["stacks"].update(r["stacks"])
        if sum(current["stacks"].values()) != stack * n:
            raise ValueError("Table chips not conserved")
        eliminated = [pid for pid in active if current["stacks"][pid] == 0]
        for pid in eliminated:
            current["eliminated_at"][pid] = r["hand"]
        if "hero" in eliminated:
            current["hero_rank"] = len(active) - len(eliminated) + (len(eliminated) + 1) / 2
        current["counts"].update(r["counts"])
        current["played"] += 1
        counts["hands"] += 1
    for table in row["sessions"]:
        key = table["variant"], table["rotation"]
        current = state[key]
        finished = sum(v > 0 for v in current["stacks"].values()) == 1
        if not finished and current["played"] != plan["session"]["hand_limit"]:
            raise ValueError("Session stopped before its registered horizon")
        checks = {"last_stacks": current["stacks"], "eliminated_at": current["eliminated_at"],
                  "played_hands": current["played"], "table_finished": finished,
                  "hero_eliminated": current["stacks"]["hero"] == 0,
                  "hero_observed_win": finished and current["stacks"]["hero"] > 0,
                  "censored_survivor": not finished and current["stacks"]["hero"] > 0,
                  "counts": dict(current["counts"])}
        for name, expected in checks.items():
            if table[name] != expected:
                raise ValueError(f"Session summary disagrees with trace: {name}")
        counts["tables"] += 1
    if counts["hands"] != row["executions"] or len(state) != len(row["sessions"]):
        raise ValueError("Execution or table count differs")
    return counts


def verify_prefixes(root):
    manifest = root / "interruption_001.json"
    checked = 0
    if manifest.exists():
        info = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in info["files"]:
            old_path = root / "interrupted_001" / entry["name"]
            if experiment.sha(old_path) != entry["sha256"]:
                raise ValueError("Interrupted original changed")
            with old_path.open(encoding="utf-8") as old, (root / "development" / entry["name"]).open(encoding="utf-8") as new:
                for i, line in enumerate(old):
                    if strip_times(json.loads(line)) != strip_times(json.loads(next(new))):
                        raise ValueError(f"Interrupted prefix differs: {entry['name']} row {i}")
                    checked += 1
    return checked


def audit(root, phase):
    p, digest = experiment.load(root)
    cfg = experiment.settings(p, phase)
    counts = Counter()
    for job in experiment.jobs(p, phase):
        name = executor.job_name(job)
        row = json.loads((root / phase / (name + ".json")).read_text(encoding="utf-8"))
        executor.check_artifact(root / phase, cfg, digest, job, row)
        counts.update(reconstruct(row, p, root / phase / (name + ".jsonl"), phase_settings=cfg))
    prefix_count = verify_prefixes(root) if phase == "development" else 0
    # Recompute statistics from trace-verified endpoints, rejecting discrepancies.
    old_summary = json.loads((root / phase / "summary.json").read_text(encoding="utf-8"))
    new_summary = experiment.summarize(root, phase)
    for field in ("descriptive", "contrasts", "gates", "counts", "hand_executions", "table_executions"):
        if old_summary[field] != new_summary[field]:
            raise ValueError(f"Statistical summary differs: {field}")
    # Preserve the recorded replay adjudication after re-computation.
    replay = root / phase / "audit.json"
    replay_passed = replay.exists() and json.loads(replay.read_text(encoding="utf-8"))["passed"]
    if phase == "validation":
        new_summary["local_advance"] = bool(replay_passed and new_summary["technical_passed"] and new_summary["local_statistical_gates_passed"])
        save(root / phase / "summary.json", new_summary)
    result = {"passed": True, "protocol_sha256": digest, "phase": phase,
              "auditor_sha256": experiment.sha(Path(__file__)),
              "additional_checks": ["registered deck/policy seed namespace", "button and seat rotations",
                                    "preset boards and hero hole cards", "public observation identity"],
              "reconstructed": dict(counts), "interrupted_prefix_records_matched": prefix_count,
              "replay_audit_passed": replay_passed}
    save(root / phase / "independent_audit.json", result)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", choices=("development", "validation"), required=True)
    args = parser.parse_args()
    audit(args.root.resolve(), args.phase)

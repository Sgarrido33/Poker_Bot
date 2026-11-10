"""Reconstruct a recorded loss, including previous hands' opponent profiles."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .arena import close_policies, play_hand, seed_for
from .evaluation import build_policies, environment
from .strategy import BotConfig


def replay_worst(report_path: str, index: int = 0) -> dict:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    records = report["worst_candidate_hands"]
    if not 0 <= index < len(records):
        raise ValueError("Índice de mano fuera de rango")
    record = records[index]
    config = BotConfig(**report["config"])
    ids = tuple(record["seats"])
    if not 0 <= record["hand"] < report["hands_per_block_per_seat"]:
        raise ValueError("Mano inconsistente con el reporte")
    kinds = {pid: record["hero_policy"] if pid == "hero" else report["opponents"][pid] for pid in ids}
    rival_config = BotConfig(**report.get("rival_config", report["config"]))
    policies = build_policies(kinds, config, rival_config, record["policy_seeds"])
    result = None
    try:
        for hand in range(record["hand"] + 1):
            settings = report["assumptions"]
            result = play_hand(policies, ids, dict.fromkeys(ids, settings["starting_stack"]),
                               seed_for(report["seed"], "deck", record["block"], hand),
                               str(hand), record["table_id"], settings["small_blind"], settings["big_blind"],
                               settings["ante"], trace_player_id="hero")
    finally:
        close_policies(policies)
    assert result is not None
    history_matches = [asdict(e) for e in result.history] == record["history"]
    actions = [entry["decision"]["action"] for entry in result.trace]
    expected_actions = [entry["decision"]["action"] for entry in record.get("trace", [])]
    payoffs_match = result.payoffs == record["payoffs"]
    board_matches = list(result.board) == record["board"]
    return {"matched": history_matches and payoffs_match and board_matches and (not expected_actions or actions == expected_actions),
            "same_source": environment()["source_sha256"] == report.get("environment", {}).get("source_sha256"),
            "history_matches": history_matches, "payoffs_match": payoffs_match, "board_matches": board_matches,
            "block": record["block"], "rotation": record["rotation"], "hand": record["hand"],
            "payoffs": result.payoffs, "hero_actions": actions, "trace": result.trace,
            "fallbacks": sum(d.fallback for _, d in result.decisions)}

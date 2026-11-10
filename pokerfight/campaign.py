"""A bounded, preregistered development matrix with disjoint holdout seeds."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys

from .arena import seed_for
from .evaluation import environment, evaluate, simulate
from .strategy import BotConfig

SCENARIOS = {
    "basic": {"opponents": ("calling", "tight", "random"), "baseline": "tight"},
    "selective": {"opponents": ("tag", "tag", "lag"), "baseline": "tag"},
    "pressure": {"opponents": ("pressure", "lag", "tag"), "baseline": "tag"},
    "selfplay": {"opponents": ("v1",), "baseline": "tag"},
}


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_campaign(output_dir: str, phase: str = "development", samples: int = 512,
                 blocks: int = 8, hands_per_block: int = 3, session_repeats: int = 1,
                 experiment_id: str | None = None) -> dict:
    if phase not in ("development", "holdout") or min(blocks, hands_per_block, session_repeats) < 1:
        raise ValueError("Fase o tamaño de campaña inválido")
    config = BotConfig(samples=samples)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "plan.json"
    plan = {"phase": phase, "environment": environment(), "config": asdict(config),
            "blocks": blocks, "hands_per_block": hands_per_block, "session_repeats": session_repeats,
            "scenarios": SCENARIOS, "players": [5, 6],
            "sessions": {"hands": 90, "starting_stack": 2500, "small_blind": 50,
                         "big_blind": 100, "ante": 0, "blind_interval": 15},
            "seed_namespace": f"{experiment_id or 'challenge-v1'}-{phase}",
            "interpretation": "All previous campaigns, including old holdout files, are development data. Use a new experiment id for new decks."}
    # JSON normalization makes tuples and loaded lists compare consistently.
    plan = json.loads(json.dumps(plan))
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != plan:
            raise ValueError("Esta carpeta ya contiene un plan distinto; use una carpeta nueva")
    else:
        save(manifest_path, plan)
    reports = []
    for name, scenario in SCENARIOS.items():
        for players in (5, 6):
            path = root / f"{name}_{players}p.json"
            if path.exists():
                report = json.loads(path.read_text(encoding="utf-8"))
            else:
                print(f"[{phase}] {name}, {players} jugadores: iniciando", file=sys.stderr, flush=True)
                report = {"environment": plan["environment"], **evaluate(players, blocks, hands_per_block,
                    seed_for(plan["seed_namespace"], "paired", name, players), config,
                    tuple(scenario["opponents"]), scenario["baseline"], candidate="v1",
                    trace_path=str(root / f"{name}_{players}p.jsonl"))}
                save(path, report)
            reports.append({"scenario": name, "players": players, "path": str(path),
                            "hands_per_variant": report["hands_per_variant"],
                            "candidate_bb_per_hand": report["candidate_bb_per_hand"],
                            "difference_bb_per_hand": report["paired_difference_bb_per_hand"],
                            "bootstrap_95_interval": report["paired_block_bootstrap_95_interval"],
                            "latency": report["hero_latency"], "fallbacks_all_policies": report["fallbacks_all_policies"]})
            print(f"[{phase}] {name} {players}p: delta={report['paired_difference_bb_per_hand']:.3f} bb/mano; "
                  f"fallbacks={report['fallbacks_all_policies']}", file=sys.stderr, flush=True)
    sessions = []
    for players in (5, 6):
        for index in range(session_repeats * players):
            path = root / f"session_{players}p_{index}.json"
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
            else:
                # Common seed within a rotation group; different starting hero seat.
                session_seed = seed_for(plan["seed_namespace"], "session", players, index // players)
                result = simulate(players, 90, session_seed, config, ("tag", "lag", "pressure"),
                    True, 2500, 50, 100, 0, hero_kind="v1", blind_interval=15, initial_rotation=index % players)
                save(path, result)
            sessions.append({"players": players, "index": index, "hands": result["played_hands"],
                             "hero_survived": result["hero_survived"], "hero_stack": result["last_stacks"]["hero"],
                             "table_finished": result["table_finished"],
                             "hero_won": result["table_finished"] and result["hero_survived"],
                             "chips_conserved": result["chips_conserved"], "latency": result["hero_latency"],
                             "fallbacks_all_policies": result["fallbacks_all_policies"]})
            print(f"[{phase}] mesa {players}p {index + 1}/{session_repeats * players}: "
                  f"{result['played_hands']} manos", file=sys.stderr, flush=True)
    summary = {"plan": str(manifest_path), "paired_reports": reports, "sessions": sessions,
               "paired_hands": sum(r["hands_per_variant"] * 2 for r in reports),
               "session_hands": sum(r["hands"] for r in sessions),
               "fallbacks_all_policies": sum(r["fallbacks_all_policies"] for r in reports + sessions),
               "session_summary": {str(players): {
                   "tables": sum(r["players"] == players for r in sessions),
                   "survived": sum(r["hero_survived"] for r in sessions if r["players"] == players),
                   "won": sum(r["hero_won"] for r in sessions if r["players"] == players),
                   "finished": sum(r["table_finished"] for r in sessions if r["players"] == players),
                   "mean_hero_chips": statistics.mean(r["hero_stack"] for r in sessions if r["players"] == players)
               } for players in (5, 6)},
               "limitations": ["Synthetic rule rivals; their strength is not externally certified.",
                               "Session rotations sharing a seed are dependent and are descriptive, not independent trials.",
                               "Single-table survival with assumed blind levels is not tournament qualification."]}
    save(root / "summary.json", summary)
    return summary

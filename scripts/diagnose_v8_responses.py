"""Post-hoc public-action description of responses to v8d's own shoves.

Uses only the completed development phase. These conditional hand outcomes are
not counterfactual action values and do not alter the registered validation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from pokerfight.campaign import save
from pokerfight.domain import Action, Observation
from pokerfight.pushfold_bot import chart_action, total
from scripts.v8_validation import load, sha


def diagnose(root):
    plan, digest = load(root)
    counts, responses, guards = defaultdict(Counter), defaultdict(Counter), Counter()
    worst_guard = None
    for path in sorted((root / "development").glob("session_*.json")):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        scenario = metadata["job"][1]
        with path.with_suffix(".jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["variant"] != "v8d":
                    continue
                for trace in row["trace"]:
                    reason = trace["decision"]["reason"]
                    if reason.startswith("v8d:scope_guard:"):
                        guards["branch_hits"] += 1
                        observed = Observation.from_dict(trace["observation"])
                        legacy = chart_action(observed)
                        if legacy is not None:
                            guards["legacy_would_use_chart"] += 1
                            current = Action(**trace["decision"]["action"])
                            guards["different_action"] += legacy[0] != current
                            if legacy[0].kind == "raise_to":
                                raiser_id = next(e.player_id for e in observed.history if e.kind == "raise_to")
                                raiser = next(p for p in observed.players if p.player_id == raiser_id)
                                modeled = min(total(observed.hero), total(raiser))
                                exposed = min(legacy[0].amount, max(total(p) for p in observed.opponents))
                                excess_bb = (exposed - modeled) / observed.big_blind
                                if worst_guard is None or excess_bb > worst_guard["excess_bb"]:
                                    worst_guard = {"scenario": scenario, "players": metadata["job"][2],
                                        "group": metadata["job"][3], "rotation": row["rotation"], "hand": row["hand"],
                                        "modeled_bb": modeled / observed.big_blind,
                                        "legacy_wager_risk_bb": exposed / observed.big_blind, "excess_bb": excess_bb,
                                        "legacy_action": legacy[0].to_dict(), "v8d_action": current.to_dict()}
                    kind = ("open" if reason.startswith("v8d:first_in_shove:") else
                            "reshove" if reason.startswith("v8d:reshove:") else None)
                    if kind is None:
                        continue
                    obs = trace["observation"]
                    index = len(obs["history"])
                    assert row["history"][index]["player_id"] == "hero"
                    assert row["history"][index]["kind"] == "raise_to"
                    c = counts[(scenario, kind)]
                    forced = any(p["player_id"] != "hero" and not p["folded"] and p["stack"] == 0 for p in obs["players"])
                    c["all_shoves"] += 1
                    if forced:
                        c["excluded_forced_allin"] += 1
                        continue
                    c["shoves_without_forced_allin"] += 1
                    calls = continuations = 0
                    for event in row["history"][index + 1:]:
                        if event["street"] != "preflop":
                            break
                        if event["player_id"] == "hero":
                            raise ValueError("Expected a terminal hero wager")
                        family = metadata["opponents"][event["player_id"]]
                        responses[(scenario, kind, family)][event["kind"]] += 1
                        calls += event["kind"] == "call"
                        continuations += event["kind"] in ("call", "raise_to")
                    c["called_by_at_least_one"] += calls >= 1
                    c["called_by_multiple"] += calls >= 2
                    c["continued_by_at_least_one"] += continuations >= 1
                    c["continued_by_multiple"] += continuations >= 2
                    c["hero_busts"] += row["stacks"]["hero"] == 0
                    c["hero_net_chips"] += row["payoffs"]["hero"]
                    c["hero_called_net_chips"] += row["payoffs"]["hero"] if calls else 0
    entries = {}
    for (scenario, kind), c in counts.items():
        denominator = c["shoves_without_forced_allin"]
        entries.setdefault(scenario, {})[kind] = {
            **dict(c), "any_call_fraction": c["called_by_at_least_one"] / denominator,
            "any_continuation_fraction": c["continued_by_at_least_one"] / denominator,
            "multiple_continuation_fraction": c["continued_by_multiple"] / denominator,
            "multiple_call_fraction": c["called_by_multiple"] / denominator,
            "hero_bust_fraction": c["hero_busts"] / denominator,
            "mean_hand_net_bb": c["hero_net_chips"] / denominator / plan["session"]["big_blind"],
            "responses_by_family": {family: dict(v) for (s, k, family), v in responses.items()
                                    if (s, k) == (scenario, kind)}}
    result = {"protocol_sha256": digest, "diagnostic_script_sha256": sha(Path(__file__)),
              "status": "post-hoc descriptive development diagnosis, no new poker sessions or confirmatory tests",
              "scope": "v8d arm only; shoves with forced pre-existing all-ins excluded from response fractions",
              "limitations": "conditions on reaching different hands/stacks; no inference that a shove caused its full hand payoff; no independent-hand significance tests",
              "scope_guard": {"counts": dict(guards), "largest_excess_case": worst_guard,
                              "interpretation": "same-observation action comparison; not a counterfactual full-session outcome"},
              "scenarios": entries}
    save(root / "development" / "response_diagnostics.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    diagnose(parser.parse_args().root.resolve())

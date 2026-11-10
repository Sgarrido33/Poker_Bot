"""Replay both variants of one recorded elimination table, excluding timing."""
import argparse
import json
from pathlib import Path

from pokerfight.campaign import save
from pokerfight.evaluation import environment, simulate
from pokerfight.shortstack_experiment import verify_control
from pokerfight.strategy import BotConfig


def replay(path: Path):
    record = json.loads(path.read_text(encoding="utf-8"))
    plan = json.loads((path.parent.parent / "protocol.json").read_text(encoding="utf-8"))
    verify_control()
    if environment() != plan["environment"]:
        raise ValueError("Restaure el código/entorno del protocolo antes de reproducir")
    results = {}
    for kind, old in record["variants"].items():
        a = old["assumptions"]
        new = simulate(old["players"], old["requested_hands"], old["input_seed"], BotConfig(**old["config"]),
            tuple(v for k, v in old["lineup"].items() if k != "hero"), True,
            a["starting_stack"], a["small_blind"], a["big_blind"], a["ante"], kind,
            a["blind_interval"], a["initial_rotation"], old["experiment_id"],
            BotConfig(**old.get("rival_config", old["config"])))
        fields = ("payoffs_chips", "last_stacks", "played_hands", "eliminated_at_hand", "button_history",
                  "hero_reasons", "hero_contexts", "fallbacks_all_policies", "chips_conserved")
        matched = {key: new[key] == old[key] for key in fields}
        results[kind] = {"matched": all(matched.values()), "fields": matched,
                         "last_stacks": new["last_stacks"], "played_hands": new["played_hands"]}
    return {"session": str(path), "matched": all(r["matched"] for r in results.values()), "variants": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = replay(Path(args.session))
    if args.output:
        save(Path(args.output), result)
    print(json.dumps(result, indent=2))
    if not result["matched"]:
        raise SystemExit(1)

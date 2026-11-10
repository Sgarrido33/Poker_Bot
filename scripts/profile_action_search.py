"""Public-state latency/adaptation profile, plus an intentional blocked worker."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

from pokerfight.arena import make_policy
from pokerfight.campaign import save
from pokerfight.evaluation import environment
from pokerfight.strategy import BotConfig
from pokerfight.supervision import SupervisedPolicy
from scripts.diagnose_shortstack import cases


def run(root):
    plan = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if environment() != plan["environment"]:
        raise ValueError("El código no coincide con el protocolo")
    observations = cases()
    rows = []
    for name, obs in observations.items():
        for kind in ("v2", "v2mc", "v4"):
            config = BotConfig(samples=4000, budget_ms=1600) if kind == "v2" else BotConfig(samples=16384, budget_ms=3500)
            for repeat in range(3):
                if kind == "v4":
                    with SupervisedPolicy(config) as bot:
                        decision = bot.decide(obs)
                else:
                    decision = make_policy(kind, config, config.seed).decide(obs)
                rows.append({"case": name, "kind": kind, "repeat": repeat, "observation": asdict(obs),
                             "decision": decision.to_dict()})
                print(name, kind, repeat, round(decision.elapsed_ms), decision.reason, flush=True)
    command = [sys.executable, "-u", "-c", "import time; print('{\"ready\":true}',flush=True); time.sleep(30)"]
    with SupervisedPolicy(BotConfig(samples=16384, budget_ms=3500), 4250, command) as bot:
        fault = bot.decide(observations["utg_speculative_4bb"])
    result = {"environment": environment(), "rows": rows, "intentional_stall": fault.to_dict(),
        "fault_passed": fault.fallback and fault.elapsed_ms < 4750 and fault.action.is_legal(observations["utg_speculative_4bb"]),
        "normal_fallbacks": sum(r["decision"]["fallback"] for r in rows),
        "normal_over_4250_ms": sum(r["decision"]["elapsed_ms"] > 4250 for r in rows),
        "limitations": "Selected development states, not a representative latency percentile; excludes worker warmup and network."}
    save(root / "profile.json", result)
    assert result["fault_passed"]
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    a = parser.parse_args()
    result = run(Path(a.root))
    print(json.dumps({k: result[k] for k in ("fault_passed", "normal_fallbacks", "normal_over_4250_ms")}, indent=2))

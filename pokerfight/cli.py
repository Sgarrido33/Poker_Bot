"""CLI and a local JSON-lines process boundary for a future arena connector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .domain import Observation
from .arena import POLICY_KINDS
from .evaluation import environment, evaluate, simulate
from .strategy import BotConfig, PokerBot


def output(data: dict, path: str | None = None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def serve(bot: PokerBot) -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            obs = Observation.from_dict(json.loads(line))
            result = {"schema_version": 1, "hand_id": obs.hand_id, **bot.decide(obs).to_dict()}
        except (ValueError, TypeError, KeyError) as error:
            # Without a validated legal-action envelope, inventing a fold is unsafe.
            result = {"schema_version": 1, "error": "invalid_observation", "detail": str(error)}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PokerFight v0.1: bot y arena local (sin conexión oficial)")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("decide", "serve", "simulate", "evaluate"):
        p = sub.add_parser(command)
        p.add_argument("--samples", type=int)
        p.add_argument("--budget-ms", type=int)
        p.add_argument("--seed", type=int, default=20261027)
        if command == "decide":
            p.add_argument("observation", help="Archivo JSON del protocolo local v1")
        if command in ("decide", "serve"):
            p.add_argument("--policy", choices=("v1", "v2", "v3", "v4", "v4rb", "v5", "v6", "v7", "v8", "v8b", "v8c", "v8d", "v8d_open", "v8d_reshove", "v8d_call", "v2mc", "noregrets"), default="v2")
        if command in ("simulate", "evaluate"):
            p.add_argument("--players", type=int, choices=(2, 3, 4, 5, 6), default=5)
            p.add_argument("--opponents", nargs="+", choices=POLICY_KINDS, default=["calling", "tight", "random"])
            p.add_argument("--hero", choices=POLICY_KINDS, default="v2")
            p.add_argument("--output")
            p.add_argument("--experiment-id")
            p.add_argument("--rival-samples", type=int)
            p.add_argument("--rival-budget-ms", type=int)
        if command == "simulate":
            p.add_argument("--hands", type=int, default=20)
            p.add_argument("--carry-stacks", action="store_true")
            p.add_argument("--starting-stack", type=int, default=10000)
            p.add_argument("--small-blind", type=int, default=50)
            p.add_argument("--big-blind", type=int, default=100)
            p.add_argument("--ante", type=int, default=0)
            p.add_argument("--blind-interval", type=int, default=0, help="Duplicar ciegas cada N manos; requiere carry-stacks")
        if command == "evaluate":
            p.add_argument("--starting-stack", type=int, default=10000)
            p.add_argument("--small-blind", type=int, default=50)
            p.add_argument("--big-blind", type=int, default=100)
            p.add_argument("--ante", type=int, default=0)
            p.add_argument("--blocks", type=int, default=8)
            p.add_argument("--hands-per-block", type=int, default=5)
            p.add_argument("--baseline", choices=POLICY_KINDS, default="tight")
            p.add_argument("--baseline-samples", type=int, help="Muestras propias del control")
            p.add_argument("--baseline-budget-ms", type=int, help="Presupuesto propio del control")
            p.add_argument("--trace", help="Guardar JSONL de manos y observaciones propias")
    campaign_parser = sub.add_parser("campaign", help="Matriz de rivales y mesas con eliminación, con plan guardado antes de medir")
    campaign_parser.add_argument("--phase", choices=("development", "holdout"), default="development")
    campaign_parser.add_argument("--output-dir", required=True)
    campaign_parser.add_argument("--experiment-id")
    campaign_parser.add_argument("--samples", type=int, default=512)
    campaign_parser.add_argument("--blocks", type=int, default=8)
    campaign_parser.add_argument("--hands-per-block", type=int, default=3)
    campaign_parser.add_argument("--session-repeats", type=int, default=1)
    replay_parser = sub.add_parser("replay", help="Reproducir una de las cinco mayores pérdidas de un reporte")
    replay_parser.add_argument("report")
    replay_parser.add_argument("--worst", type=int, default=0)
    replay_parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "replay":
            from .replay import replay_worst
            result = replay_worst(args.report, args.worst)
            output(result, args.output)
            if not result["matched"]:
                raise ValueError("La repetición difiere del registro original")
            return
        if args.command == "campaign":
            from .campaign import run_campaign
            output(run_campaign(args.output_dir, args.phase, args.samples, args.blocks,
                                args.hands_per_block, args.session_repeats, args.experiment_id))
            return
        kind = args.policy if args.command in ("decide", "serve") else args.hero
        extended = kind in ("v4", "v4rb", "v5", "v6", "v7", "v2mc")
        default_samples = 1024 if kind == "v7" else (16384 if extended else 4000)
        config = BotConfig(args.samples if args.samples is not None else default_samples,
                           args.budget_ms if args.budget_ms is not None else (3500 if extended else 1600), args.seed)
        rival_config = None
        if args.command in ("simulate", "evaluate") and (
                args.rival_samples is not None or args.rival_budget_ms is not None
                or extended and any(kind in ("v1", "v2") for kind in args.opponents)):
            rival_config = BotConfig(args.rival_samples if args.rival_samples is not None else 4000,
                                     args.rival_budget_ms if args.rival_budget_ms is not None else 1600, args.seed)
        if args.command in ("decide", "serve"):
            from .arena import make_policy
            if args.policy in ("v4", "v4rb", "v5", "v6", "v7"):
                from .supervision import SupervisedPolicy
                bot = SupervisedPolicy(config, policy=args.policy)
            else:
                bot = make_policy(args.policy, config, config.seed)
            try:
                if args.command == "serve":
                    serve(bot)
                else:
                    obs = Observation.from_dict(json.loads(Path(args.observation).read_text(encoding="utf-8")))
                    output({"schema_version": 1, "hand_id": obs.hand_id, **bot.decide(obs).to_dict()})
            finally:
                if hasattr(bot, "close"):
                    bot.close()
        elif args.command == "simulate":
            if args.hands < 1 or args.starting_stack < 1:
                raise ValueError("hands y starting-stack deben ser positivos")
            output({"environment": environment(), **simulate(args.players, args.hands, args.seed, config,
                   tuple(args.opponents), args.carry_stacks, args.starting_stack, args.small_blind, args.big_blind, args.ante,
                   args.hero, args.blind_interval, experiment_id=args.experiment_id, rival_config=rival_config)}, args.output)
        else:
            if args.blocks < 1 or args.hands_per_block < 1:
                raise ValueError("blocks y hands-per-block deben ser positivos")
            baseline_config = None
            if (args.baseline_samples is not None or args.baseline_budget_ms is not None
                    or extended and args.baseline in ("v1", "v2")):
                frozen = args.baseline in ("v1", "v2")
                baseline_config = BotConfig(
                    args.baseline_samples if args.baseline_samples is not None else (4000 if frozen else config.samples),
                    args.baseline_budget_ms if args.baseline_budget_ms is not None else (1600 if frozen else config.budget_ms), args.seed)
            output({"environment": environment(), **evaluate(args.players, args.blocks, args.hands_per_block,
                   args.seed, config, tuple(args.opponents), args.baseline, args.hero, args.trace,
                   args.starting_stack, args.small_blind, args.big_blind, args.ante, args.experiment_id,
                   rival_config=rival_config, baseline_config=baseline_config)}, args.output)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.error(str(error))

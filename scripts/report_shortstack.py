"""Post-experiment reporting only. Does not change policy or preregistered plan."""
from collections import Counter, defaultdict
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import statistics

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.campaign import save
from pokerfight.domain import Observation
from pokerfight.evaluation import bootstrap_interval, percentile
from pokerfight.replay import replay_worst
from pokerfight.shortstack import context
from pokerfight.shortstack_experiment import pooled
from pokerfight.strategy import BotConfig


def first(record):
    return next((e for e in record["trace"] if not e["observation"]["board"]), None)


def replay_record(report, record):
    ids = tuple(record["seats"])
    policies = {pid: make_policy(record["hero_policy"] if pid == "hero" else report["opponents"][pid],
        BotConfig(**(report["config"] if pid == "hero" else report.get("rival_config", report["config"]))),
        record["policy_seeds"][pid]) for pid in ids}
    a = report["assumptions"]
    for hand in range(record["hand"] + 1):
        result = play_hand(policies, ids, dict.fromkeys(ids, a["starting_stack"]),
            seed_for(report["seed"], "deck", record["block"], hand), str(hand), record["table_id"],
            a["small_blind"], a["big_blind"], a["ante"], trace_player_id="hero")
    return {"matched": result.payoffs == record["payoffs"] and [asdict(e) for e in result.history] == record["history"]
            and list(result.board) == record["board"], "payoffs": result.payoffs,
            "fallbacks": sum(d.fallback for _, d in result.decisions)}


def inspect_phase(root, phase, replay=False):
    folder = root / phase
    times = {"v2": [], "v3": []}
    audits = Counter()
    candidates = []
    contexts = defaultdict(lambda: defaultdict(list))
    replayed = []
    for path in sorted(folder.glob("paired_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        pairs = defaultdict(dict)
        for line in path.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            pairs[(record["block"], record["rotation"], record["hand"])][record["variant"]] = record
            for e in record["trace"]:
                d = e["decision"]
                times[record["hero_policy"]].append(d["elapsed_ms"])
                audits["hero_decisions"] += 1
                audits["partial_samples"] += bool(d["equity"] and d["equity"]["timed_out"])
                audits["requested_samples"] += report["config"]["samples"]
                audits["completed_samples"] += d["equity"]["samples"] if d["equity"] else 0
        for key, pair in pairs.items():
            a, b = pair["candidate"], pair["baseline"]
            assert a["deck_seed"] == b["deck_seed"] and a["seats"] == b["seats"]
            audits["matched_deck_pairs"] += 1
            fa, fb = first(a), first(b)
            delta = (a["payoffs"]["hero"] - b["payoffs"]["hero"]) / report["assumptions"]["big_blind"]
            if fa and fb:
                audits["same_first_public_state"] += fa["observation"] == fb["observation"]
            changed = fa and fb and fa["decision"]["action"] != fb["decision"]["action"]
            audits["changed_first_actions"] += bool(changed)
            if report["players"] in (5, 6) and report["depth_bb"] in (4, 8):
                if fb:
                    ctx = context(Observation.from_dict(fb["observation"]))
                    for dimension, value in (("position", ctx.position), ("situation", ctx.situation),
                        ("opponents", str(ctx.opponents)), ("price", next((str(p) for p in (.1, .25, .4) if ctx.price <= p), ">.4")),
                        ("effective_bb", next((str(p) for p in (5, 8, 12, 20) if ctx.effective_bb <= p), ">20"))):
                        contexts[(dimension, value)][(report["scenario"], report["players"], report["depth_bb"], key[0])].append(delta)
                if changed:
                    candidates.append({"report": str(path), "scenario": report["scenario"], "players": report["players"],
                        "depth_bb": report["depth_bb"], "block": key[0], "rotation": key[1], "hand": key[2],
                        "paired_delta_bb": delta, "same_first_public_state": fa["observation"] == fb["observation"],
                        "candidate": a, "baseline": b})
        if replay:
            result = replay_worst(str(path))
            assert result["matched"]
            replayed.append({"report": str(path), "matched": result["matched"], "same_source": result["same_source"],
                             "payoffs": result["payoffs"], "fallbacks": result["fallbacks"]})
    grouped = []
    for (dimension, value), batches in sorted(contexts.items()):
        blocks = [statistics.mean(v) for v in batches.values()]
        grouped.append({"dimension": dimension, "value": value, "hands": sum(map(len, batches.values())),
            "independent_block_contexts": len(blocks), "mean_block_delta_bb": statistics.mean(blocks),
            "interval_95": bootstrap_interval(blocks, seed_for(phase, dimension, value)),
            "note": "Baseline-defined context; conditional, descriptive and sparse. Equal weight to observed block-context means; no multiplicity correction."})
    chosen = sorted(candidates, key=lambda r: r["paired_delta_bb"])
    selected = chosen[:3] + chosen[-3:]
    if replay:
        for item in selected:
            report = json.loads(Path(item["report"]).read_text(encoding="utf-8"))
            item["candidate_replay"] = replay_record(report, item["candidate"])
            item["baseline_replay"] = replay_record(report, item["baseline"])
            assert item["candidate_replay"]["matched"] and item["baseline_replay"]["matched"]
    result = {"phase": phase, "audit": dict(audits), "latency": {
        v: {"decisions": len(t), "p50_ms": statistics.median(t), "p95_ms": percentile(t, .95), "max_ms": max(t)}
        for v, t in times.items()}, "contexts": grouped, "selected_cases": selected, "worst_replays": replayed}
    save(folder / "analysis.json", result)
    return result


def interval(values):
    return "—" if values is None else f"[{values[0]:+.3f}; {values[1]:+.3f}]"


def action_text(entry):
    action = entry["decision"]["action"]
    return f"subir a {action['amount'] / 100:g} bb" if action["kind"] == "raise_to" else {
        "fold": "retirarse", "call": "pagar", "check": "pasar"}[action["kind"]]


def write_results(root):
    plans = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    summaries = {p: json.loads((root / p / "summary.json").read_text(encoding="utf-8")) for p in ("pilot", "validation", "production")}
    for phase, settings in plans["phases"].items():
        players = settings.get("players", plans["players"])
        depths = settings.get("depths_bb", plans["depths_bb"])
        scenarios = settings.get("scenarios", list(plans["scenarios"]))
        expected_cells = len(players) * len(depths) * len(scenarios)
        expected_tables = settings.get("session_groups", 0) * len(settings.get("session_scenarios", [])) * 11
        assert summaries[phase]["paired_cells"] == expected_cells
        assert summaries[phase]["session_tables_per_variant"] == expected_tables
        for path in (root / phase).glob("paired_*.json"):
            report = json.loads(path.read_text(encoding="utf-8"))
            assert report["environment"] == plans["environment"]
            assert report["experiment_id"] == settings["namespace"]
            assert report["config"]["samples"] == settings["samples"]
    analyses = {p: inspect_phase(root, p, replay=True) for p in summaries}
    validation = summaries["validation"]
    accepted = all(validation["criteria"].values()) and all(s["criteria"]["safety"] for s in summaries.values())
    decision = {"default": "v3" if accepted else "v2", "validation_criteria": validation["criteria"],
        "other_phase_safety": {p: s["criteria"]["safety"] for p, s in summaries.items()},
        "protocol_sha256": hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest(),
        "evaluated_source_sha256": plans["environment"]["source_sha256"]}
    save(root / "decision.json", decision)
    reports = sorted([json.loads(p.read_text(encoding="utf-8")) for p in (root / "validation").glob("paired_*.json")],
                     key=lambda r: (list(plans["scenarios"]).index(r["scenario"]), r["players"], r["depth_bb"]))
    rows = [{k: r[k] for k in ("scenario", "players", "depth_bb", "hands_per_variant", "candidate_chips", "baseline_chips",
        "candidate_bb_per_hand", "baseline_bb_per_hand", "paired_difference_bb_per_hand", "paired_block_bootstrap_95_interval",
        "candidate_bust_hands", "baseline_bust_hands")} for r in reports]
    with (root / "validation_cells.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Resultados de la candidata preflop v3", "", "Fecha local: 28 de octubre de 2026.", "",
        f"**Decisión: mantener {decision['default']} como predeterminada.** " +
        ("La candidata cumplió los criterios registrados." if accepted else "v3 no cumplió todos los criterios registrados. Se conserva disponible como candidata experimental."), "",
        "El [método](PREFLOP_V3_METODO.md) y el [protocolo anterior al piloto](../results/shortstack_2026-10-28/protocol.json) fijan cantidades, semillas y aceptación. No se modificó la candidata después del piloto. Toda validación anterior, incluso los lotes llamados holdout, fue tratada como desarrollo.", "",
        "Pasaron las **45 pruebas automatizadas**, incluidas las 29 originales, la regresión del call all-in barato, límites legales, aislamiento del control, manos doradas de 2–6 jugadores, contexto sin duplicar fichas, namespaces nuevos y reproducción con stacks cortos. El [registro de suite](../results/shortstack_2026-10-28/candidate_tests.txt) conserva la ejecución.", "",
        "## Cantidades y resultado principal", "",
        "| Etapa | Manos con reposición, ambas variantes | Manos de sesiones, ambas variantes | Delta principal bb/mano | IC 95 % por bloques |",
        "|---|---:|---:|---:|---|"]
    for phase, s in summaries.items():
        lines.append(f"| {phase} | {s['paired_hand_executions']} | {s['session_hand_executions']} | {s['primary']['mean']:+.3f} | {interval(s['primary']['interval_95'])} |")
    total = sum(s["paired_hand_executions"] + s["session_hand_executions"] for s in summaries.values())
    lines += ["", f"Se ejecutaron **{total:,} manos adicionales**, sin contar pruebas unitarias, casos aislados o reproducciones. Son ejecuciones; las variantes y rotaciones no son repartos independientes. Piloto y validación cubren 60 celdas cada uno. La comprobación de 4 000 muestras cubre cuatro celdas de pressure, por lo que su agregado no es comparable al de las otras fases.", "",
        f"En validación, el contraste principal (5/6 jugadores, 4/8 bb) es **{validation['primary']['mean']:+.3f} bb/mano**, intervalo {interval(validation['primary']['interval_95'])}, con {validation['primary']['independent_blocks']} bloques repartidos entre doce celdas. Cada celda pesa igual. Estos intervalos describen este conjunto sintético; no demuestran robustez general.", "",
        "| Jugadores principales | Delta 4/8 bb | IC 95 % estratificado |", "|---|---:|---|"]
    for n, r in validation["by_players"].items():
        lines.append(f"| {n} | {r['mean']:+.3f} | {interval(r['interval_95'])} |")
    lines += ["", "## Todas las celdas principales", "",
        "Stacks reiniciados cada mano; bb/mano. Las tasas de bust aquí permiten volver a jugar y no equivalen a eliminación de una sesión. Las celdas de 12/20 bb comprueban el comportamiento fuera del alcance inicial de la candidata.", "",
        "| Rival | Jugadores | bb iniciales | v2 | v3 | v3−v2 | IC 95 % por bloques | Busts v2/v3 |",
        "|---|---:|---:|---:|---:|---:|---|---:|"]
    for r in reports:
        if r["players"] in (5, 6):
            lines.append(f"| {r['scenario']} | {r['players']} | {r['depth_bb']} | {r['baseline_bb_per_hand']:+.3f} | {r['candidate_bb_per_hand']:+.3f} | {r['paired_difference_bb_per_hand']:+.3f} | {interval(r['paired_block_bootstrap_95_interval'])} | {r['baseline_bust_hands']}/{r['candidate_bust_hands']} |")
    lines += ["", "## Dos, tres y cuatro jugadores", "",
        "Menos bloques; resultados secundarios agrupados con igual peso a las tres composiciones rivales. Las 60 celdas completas, fichas y busts están en [validation_cells.csv](../results/shortstack_2026-10-28/validation_cells.csv).", "",
        "| Jugadores | bb iniciales | Delta medio | IC 95 % estratificado |", "|---|---:|---:|---|"]
    for n in (2, 3, 4):
        for depth in (4, 8, 12, 20):
            result = pooled([r for r in reports if r["players"] == n and r["depth_bb"] == depth],
                            "block_differences_bb_per_hand", seed_for("secondary", n, depth))
            lines.append(f"| {n} | {depth} | {result['mean']:+.3f} | {interval(result['interval_95'])} |")
    lines += ["", "## Sesiones con eliminación", "",
        "Inicio 8 bb, ciegas duplicadas cada diez manos, hasta treinta manos o un superviviente. Tres grupos independientes por composición y formato, todos los asientos. Las rotaciones dentro de un grupo se promedian antes de calcular incertidumbre. Las mesas truncadas conservan sus fichas finales; no se cuentan como ganadas.", "",
        f"Delta agregado de fichas finales: **{validation['session_pooled']['mean_delta_initial_stacks']:+.3f} stacks iniciales**, intervalo {interval(validation['session_pooled']['interval_95'])}. La unidad es 800 fichas iniciales. Hay {validation['session_pooled']['groups']} grupos en total y solo tres por celda; las tasas de victoria son descriptivas.", "",
        "| Rival | Jugadores | Mesas/variante | Fichas medias v2/v3 | Eliminados v2/v3 | Mesas ganadas v2/v3 | Delta por grupo, stacks iniciales | IC por grupos |",
        "|---|---:|---:|---:|---:|---:|---|---|"]
    for r in validation["sessions"]:
        a, b = r["v2"], r["v3"]
        lines.append(f"| {r['scenario']} | {r['players']} | {r['tables_per_variant']} | {a['mean_final_chips']:.1f}/{b['mean_final_chips']:.1f} | {a['eliminated']}/{b['eliminated']} | {a['tables_won']}/{b['tables_won']} | {', '.join(f'{x:+.3f}' for x in r['group_delta_initial_stacks'])} | {interval(r['interval_95'])} |")
    lines += ["", "## Latencia y seguridad", "",
        "| Etapa | Política | Decisiones de comparación | p95 | Máximo |", "|---|---|---:|---:|"]
    for phase, analysis in analyses.items():
        for v, t in analysis["latency"].items():
            lines.append(f"| {phase} | {v} | {t['decisions']} | {t['p95_ms']:.1f} ms | {t['max_ms']:.1f} ms |")
    for phase, s in summaries.items():
        a = analyses[phase]["audit"]
        session_reports = [json.loads(p.read_text(encoding="utf-8")) for p in (root / phase).glob("session_*.json")]
        max_session = max((r["variants"][v]["hero_latency"]["max_ms"] for r in session_reports for v in ("v2", "v3")), default=0)
        c = s["checks"]
        lines += ["", f"{phase}: {c['fallbacks']} respaldos, {c['invalid_actions']} acciones inválidas, {c['recovered_illegal_proposals']} propuestas ilegales recuperadas, {c['hero_over_2000_ms']} decisiones del héroe sobre dos segundos y {a['partial_samples']} muestras parciales de comparación. Se conservaron las fichas en todos los lotes. " +
            (f"Máximo del héroe en sesiones: {max_session:.1f} ms." if session_reports else "Esta fase no incluye sesiones.")]
    lines += ["", "Las latencias de cada sesión están en sus JSON. Las cifras incluyen la conversión pública del control y excluyen parseo, arranque y red; el presupuesto sigue siendo cooperativo."]
    lines += ["", "La auditoría comparó las semillas y los asientos de cada par; las barajas coinciden. Las trazas registran el número real de muestras. Los controles de 12/20 bb y los contextos sin cambio ayudan a detectar contaminación de v2; las diferencias, si aparecen después de stacks efectivos cortos o decisiones previas distintas, deben analizarse con la traza.", "",
        "## Casos y contextos", "",
        "Los [casos previos al ajuste](../results/shortstack_2026-10-28/diagnosis_before.json) y su [comparación con la candidata](../results/shortstack_2026-10-28/diagnosis_candidate.json) conservan las observaciones públicas y decisiones. Se publican también pérdidas de la candidata:", ""]
    for item in analyses["validation"]["selected_cases"][:3]:
        fb, fa = first(item["baseline"]), first(item["candidate"])
        obs = Observation.from_dict(fb["observation"])
        lines.append(f"- {item['scenario']}, {item['players']} jugadores, {item['depth_bb']} bb, bloque {item['block']}, rotación {item['rotation']}, mano {item['hand']}: {''.join(obs.hole_cards)} {obs.position}; v2 {action_text(fb)}, v3 {action_text(fa)}; delta realizado {item['paired_delta_bb']:+.1f} bb. No es una prueba de EV de esa acción.")
    lines += ["", "[analysis.json](../results/shortstack_2026-10-28/validation/analysis.json) contiene seis casos pareados completos, su reproducción, auditoría de barajas y resúmenes por posición, precio, stack efectivo, rivales y situación. Los contextos de resultados pareados se definen con la primera observación de v2 y agrupan observaciones dentro de cada bloque. Son análisis descriptivos, escasos y sujetos a selección; no se deben interpretar como un EV causal ni como nuevos criterios de aceptación. Las acciones y resultados de cada variante se conservan además en los reportes de celda. Los walks tienen categoría sin decisión.", "",
        f"Se reprodujo la mayor pérdida de cada uno de los {sum(len(a['worst_replays']) for a in analyses.values())} reportes de comparación, además de ambas variantes de los casos seleccionados. Las acciones, boards y fichas coinciden con los registros. Estas reproducciones no se suman al tamaño de muestra.", "",
        "## Qué indican los contextos", "",
        "En la validación principal se agrupan los pares según la primera observación de v2. Se muestra la media de los promedios de cada bloque que tuvo ese contexto; no tiene la misma ponderación que el contraste principal y omite walks. El mismo bloque puede aparecer en varias filas. Estos intervalos exploratorios no corrigen selección ni comparaciones múltiples.", "",
        "| Dimensión | Contexto | Manos pareadas | Bloques con contexto | Delta descriptivo bb/mano | IC 95 % por bloques |",
        "|---|---|---:|---:|---:|---|"]
    dimensions = {"position": "Posición", "situation": "Situación", "opponents": "Rivales activos",
                  "price": "Precio hasta", "effective_bb": "Efectivo hasta bb"}
    for r in analyses["validation"]["contexts"]:
        lines.append(f"| {dimensions[r['dimension']]} | {r['value']} | {r['hands']} | {r['independent_block_contexts']} | {r['mean_block_delta_bb']:+.3f} | {interval(r['interval_95'])} |")
    lines += ["", "En este lote, la diferencia se concentró en aperturas limpias. Los contextos enfrentando subidas y la posición BB dieron delta cero; el cambio no arregló la defensa identificada en el diagnóstico. La posición BTN y los contextos con dos rivales activos merecen revisión: hacer push/fold con rangos manuales también puede perder aperturas pequeñas rentables. Esto no demuestra que todos los pushes ni todas esas retiradas sean malos.", "",
        "Las 30 celdas de 12/20 bb dieron diferencias exactamente cero. Esa igualdad y las pruebas de mutación del código compartido respaldan que el control no cambió. En sesiones, el daño más claro apareció frente a selectivos con seis jugadores: fichas medias de 1225 a 452,8 y eliminaciones de 10/18 a 14/18. Con solo tres grupos por esa celda, las cifras deben tratarse con cautela.", "",
        "El siguiente experimento debería separar el cambio de tamaños del cambio de rangos y modelar las respuestas al all-in antes de ampliar agresión. La defensa barata requiere estudiar realización de equity y apuestas futuras. No se implementaron ajustes posteriores al inspeccionar esta validación; sus semillas ya son desarrollo.", "",
        "## Criterios y límites", ""]
    labels = {"primary_positive": "Mejora principal con límite inferior positivo",
              "both_formats_nonnegative": "Media no negativa en ambos formatos principales",
              "no_clear_primary_harm": "Ninguna celda principal con todo el intervalo por debajo de −0,25 bb/mano",
              "sessions_nonnegative": "Fichas finales de sesiones con límite inferior no negativo",
              "safety": "Acciones, respaldos, fichas y latencia"}
    for name, ok in validation["criteria"].items():
        lines.append(f"- {labels[name]}: {'cumplido' if ok else 'no cumplido'}.")
    lines += ["", "La selección preflop corta necesita más trabajo. El cambio medido trata aperturas limpias; la defensa y los calls de all-in siguen usando rangos de v2. El muestreo modela showdown, no respuestas a un push, fold equity, riesgo de clasificación ni ICM. Los adversarios son sintéticos y su fuerza no está certificada. Cambiar a una política más agresiva puede mejorar fichas con reposición y empeorar supervivencia; ambos objetivos se publican por separado.", "",
        "Una mesa local ganada no equivale a clasificarse al torneo. La API oficial y el torneo completo no están integrados. Una vez examinados estos resultados, todas estas semillas pasan a ser desarrollo para la siguiente iteración.", "",
        "Para reproducir las fases, casos, suite y celdas individuales, véase el [método](PREFLOP_V3_METODO.md). La decisión legible por máquina está en [decision.json](../results/shortstack_2026-10-28/decision.json)."]
    (ROOT / "docs/PREFLOP_V3_RESULTADOS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2))


ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--inspect-phase", choices=("pilot", "validation", "production"))
    args = parser.parse_args()
    if args.inspect_phase:
        analysis = inspect_phase(Path(args.root), args.inspect_phase, replay=True)
        print(json.dumps({"phase": analysis["phase"], "audit": analysis["audit"], "latency": analysis["latency"]}, indent=2))
    else:
        write_results(Path(args.root))

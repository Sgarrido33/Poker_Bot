"""Audit and publish the preregistered v4 three-arm experiment."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics

from pokerfight.arena import seed_for
from pokerfight.campaign import save
from pokerfight.domain import Observation
from pokerfight.evaluation import bootstrap_interval, environment, percentile
from pokerfight.shortstack import context
from pokerfight.shortstack_experiment import pooled
from scripts.report_shortstack import action_text, interval, replay_record

ROOT = Path(__file__).resolve().parents[1]


def audit(root, phase):
    folder = root / phase
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    times = {k: [] for k in ("v2", "v2mc", "v4")}
    counts = Counter()
    worlds, changed_cases = [], []
    transitions = Counter()
    contexts = defaultdict(lambda: defaultdict(list))
    for path in sorted(folder.glob("paired_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        original_path = folder / path.name.replace("paired_", "original_")
        records = defaultdict(dict)
        for trace in (path.with_suffix(".jsonl"), original_path.with_suffix(".jsonl")):
            for line in trace.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                records[(r["block"], r["rotation"], r["hand"])][r["hero_policy"]] = r
                for e in r["trace"]:
                    d = e["decision"]
                    times[r["hero_policy"]].append(d["elapsed_ms"])
                    counts["partial_equity_samples"] += bool(d["equity"] and d["equity"]["timed_out"])
                    if d.get("search"):
                        s = d["search"]
                        counts["searches"] += 1
                        counts["changes"] += s["changed"]
                        counts["stop:" + s["stop"]] += 1
                        worlds.append(s["worlds"])
                        if s["changed"]:
                            transitions[json.dumps(s["baseline"], sort_keys=True) + " -> " + json.dumps(s["chosen"], sort_keys=True)] += 1
                        obs = Observation.from_dict(e["observation"])
                        effective_cap = min(obs.hero.stack + obs.hero.street_bet,
                            max(p.stack + p.street_bet for p in obs.opponents))
                        if d["action"]["kind"] == "raise_to" and d["action"]["amount"] < effective_cap:
                            counts["nonterminal_raise_windows"] += 1
                            for event in r["history"][len(obs.history) + 1:]:
                                if event["street"] != "preflop" or event["player_id"] == "hero":
                                    break
                                counts["observed_response:" + event["kind"]] += 1
                                if event["kind"] == "raise_to":
                                    counts["nonterminal_windows_with_reraise"] += 1
                                    break
        for key, variants in records.items():
            assert set(variants) == {"v2", "v2mc", "v4"}
            a, b, c = variants["v4"], variants["v2mc"], variants["v2"]
            assert a["deck_seed"] == b["deck_seed"] == c["deck_seed"]
            assert a["seats"] == b["seats"] == c["seats"]
            assert a["policy_seeds"] == b["policy_seeds"] == c["policy_seeds"]
            counts["matched_deck_triplets"] += 1
            if report["players"] not in (5, 6) or report["depth_bb"] not in (4, 8, 12):
                continue
            delta = (a["payoffs"]["hero"] - c["payoffs"]["hero"]) / 100
            first = next((e for e in c["trace"] if not e["observation"]["board"]), None)
            if first:
                ctx = context(Observation.from_dict(first["observation"]))
                for dimension, value in (("position", ctx.position), ("situation", ctx.situation),
                    ("opponents", str(ctx.opponents)), ("price", next((str(p) for p in (.1, .25, .4) if ctx.price <= p), ">.4")),
                    ("effective_bb", next((str(p) for p in (5, 8, 12) if ctx.effective_bb <= p), ">12"))):
                    contexts[(dimension, value)][(report["scenario"], report["players"], report["depth_bb"], key[0])].append(delta)
            changed = next((e for e in a["trace"] if e["decision"].get("search", {}).get("changed")), None)
            cutoff = any(e["decision"].get("search", {}).get("stop") == "deadline_keep_v2" for e in a["trace"])
            if changed and not cutoff:
                changed_cases.append({"report": str(path), "original_report": str(original_path), "scenario": report["scenario"],
                    "players": report["players"], "depth_bb": report["depth_bb"], "block": key[0], "rotation": key[1], "hand": key[2],
                    "delta_original_bb": delta, "decision": changed, "variants": variants})
    chosen = sorted(changed_cases, key=lambda r: r["delta_original_bb"])
    selected = chosen[:3] + chosen[-3:]
    for item in selected:
        report = json.loads(Path(item["report"]).read_text(encoding="utf-8"))
        old = json.loads(Path(item["original_report"]).read_text(encoding="utf-8"))
        item["replays"] = {kind: replay_record(old if kind == "v2" else report, r) for kind, r in item["variants"].items()}
    rows = []
    for (dimension, value), groups in sorted(contexts.items()):
        means = [statistics.mean(g) for g in groups.values()]
        rows.append({"dimension": dimension, "value": value, "hands": sum(map(len, groups.values())), "blocks": len(means),
            "mean_block_delta_original_bb": statistics.mean(means), "interval_95": bootstrap_interval(means, seed_for(phase, dimension, value))})
    result = {"phase": phase, "audit": dict(counts), "transitions": dict(transitions),
        "worlds": {"p50": statistics.median(worlds) if worlds else 0, "p95": percentile(worlds, .95), "max": max(worlds, default=0)},
        "latency": {k: {"decisions": len(t), "p50_ms": statistics.median(t), "p95_ms": percentile(t, .95), "max_ms": max(t)} for k, t in times.items()},
        "contexts": rows, "selected_cases": selected}
    save(folder / "analysis.json", result)
    return result


def report(root, reuse_analysis=False):
    plan = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    summaries = {p: json.loads((root / p / "summary.json").read_text(encoding="utf-8")) for p in ("pilot", "validation")}
    for phase, s in summaries.items():
        assert s["cells"] == 57
        assert s["session_tables_per_variant"] == (11 if phase == "pilot" else 66)
        for path in (root / phase).glob("paired_*.json"):
            r = json.loads(path.read_text(encoding="utf-8"))
            assert r["environment"] == plan["environment"]
            assert r["experiment_id"] == plan["phases"][phase]["namespace"]
    assert environment() == plan["environment"] == profile["environment"]
    analyses = {p: (json.loads((root / p / "analysis.json").read_text(encoding="utf-8"))
                    if reuse_analysis else audit(root, p)) for p in summaries}
    for phase, analysis in analyses.items():
        assert analysis["phase"] == phase
        assert analysis["audit"]["matched_deck_triplets"] * 3 == summaries[phase]["hand_executions_reset"]
    validation = summaries["validation"]
    good_profile = profile["fault_passed"] and not profile["normal_fallbacks"] and not profile["normal_over_4250_ms"]
    decision = {"default": "v4" if all(validation["criteria"].values()) and good_profile else "v2",
        "validation_criteria": validation["criteria"], "supervised_profile_passed": good_profile,
        "source_sha256": plan["environment"]["source_sha256"]}
    save(root / "decision.json", decision)
    rows = validation["paired"]
    with (root / "validation_cells.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["scenario", "players", "depth_bb", "hands_per_variant", "candidate_bb_per_hand", "baseline_bb_per_hand", "original_bb_per_hand",
                  "paired_difference_bb_per_hand", "candidate_chips", "baseline_chips", "original_chips",
                  "candidate_bust_hands", "baseline_bust_hands", "original_bust_hands"]
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    total = sum(s["hand_executions_reset"] + s["hand_executions_sessions"] for s in summaries.values())
    total_text = f"{total:,}".replace(",", " ")
    lines = ["# Resultados de búsqueda preflop v4", "", "Fecha local: 28 de octubre de 2026.", "",
        f"**Política predeterminada: {decision['default']}.** " + ("La candidata pasó los criterios registrados." if decision["default"] == "v4" else "La candidata no reúne evidencia suficiente para sustituir v2."), "",
        "Se implementó comparación de acciones con respuestas hipotéticas, muestreo adaptativo y un proceso supervisado. El [método](BUSQUEDA_V4_METODO.md) distingue sus límites y el [protocolo anterior al piloto](../results/action_search_2026-10-28/protocol.json) fija cantidades y aceptación. No se ajustaron parámetros después del piloto.", "",
        "Pasaron las **64 pruebas automatizadas**, incluidas las originales y las nuevas de valores por acción, cuota de rivales, repetición de tres brazos y procesos bloqueados. El [registro final](../results/action_search_2026-10-28/tests_final.txt) conserva la ejecución. La contabilidad terminal coincidió con PokerKit en [40 escenarios independientes](../results/action_search_2026-10-28/terminal_oracle.json), con diferencia máxima cero; eso valida los pozos y devoluciones bajo respuestas fijadas, no las probabilidades de respuesta.", "",
        f"Se ejecutaron **{total_text} manos adicionales**, excluyendo tests, perfiles y replays. Son ejecuciones de tres variantes con barajas compartidas; no observaciones independientes. El control original conserva 4 000 muestras/1 600 ms. v2mc y v4 comparten el techo de 3 500 ms y la cuota de 16 384 en validación, con asignación del trabajo distinta.", "",
        "## Contrastes principales", "",
        "Cinco/seis jugadores, 4/8/12 bb, igual peso a cada una de las dieciocho celdas. Bootstrap estratificado de bloques completos; las rotaciones no se remuestrean por separado.", "",
        "| Etapa | Manos con reposición | Manos de sesiones | v4−v2mc, bb/mano | IC 95 % | v4−v2 original | IC 95 % |",
        "|---|---:|---:|---:|---|---:|---|"]
    for phase, s in summaries.items():
        lines.append(f"| {phase} | {s['hand_executions_reset']} | {s['hand_executions_sessions']} | {s['primary_vs_mc']['mean']:+.3f} | {interval(s['primary_vs_mc']['interval_95'])} | {s['primary_vs_original']['mean']:+.3f} | {interval(s['primary_vs_original']['interval_95'])} |")
    lines += ["", "| Formato | v4−v2mc | IC 95 % | v4−v2 original | IC 95 % |", "|---|---:|---|---:|---|"]
    for n, r in validation["by_players"].items():
        lines.append(f"| {n} jugadores | {r['mc']['mean']:+.3f} | {interval(r['mc']['interval_95'])} | {r['original']['mean']:+.3f} | {interval(r['original']['interval_95'])} |")
    primary = [r for r in rows if r["players"] in (5, 6) and r["depth_bb"] in (4, 8, 12)]
    precision_rows = []
    for row in primary:
        name = f"{row['scenario']}_{row['players']}p_{row['depth_bb']}bb.json"
        high = json.loads((root / "validation" / ("paired_" + name)).read_text(encoding="utf-8"))
        original = json.loads((root / "validation" / ("original_" + name)).read_text(encoding="utf-8"))
        precision_rows.append({"blocks": [a-b for a, b in zip(high["baseline_block_bb_per_hand"],
            original["candidate_block_bb_per_hand"], strict=True)]})
    precision = pooled(precision_rows, "blocks", seed_for("mc-v2"))
    changed_blocks = sum(abs(v) > 1e-12 for r in precision_rows for v in r["blocks"])
    lines += ["", f"El efecto de aumentar solamente las muestras, v2mc−v2 original, fue {precision['mean']:+.3f} bb/mano, intervalo {interval(precision['interval_95'])}. Hubo diferencia en {changed_blocks} de los 144 bloques primarios; el intervalo toca cero. La política resta un error estándar a la equity; aumentar muestras reduce también ese descuento de incertidumbre. Este contraste separa esa asignación de cómputo de la búsqueda de acciones, sin garantizar fuerza fuera de estas mesas.", "",
        "## Todas las celdas principales", "",
        "Fichas reiniciadas cada mano. Los busts aquí no impiden jugar la siguiente. La cuota de rivales se mantiene fija en todos los brazos.", "",
        "| Escenario | Jugadores | bb | v2 original | v2mc | v4 | Delta v4−v2mc | IC 95 % | Busts v2/v2mc/v4 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for r in sorted(primary, key=lambda r: (r["scenario"], r["players"], r["depth_bb"])):
        lines.append(f"| {r['scenario']} | {r['players']} | {r['depth_bb']} | {r['original_bb_per_hand']:+.3f} | {r['baseline_bb_per_hand']:+.3f} | {r['candidate_bb_per_hand']:+.3f} | {r['paired_difference_bb_per_hand']:+.3f} | {interval(r['paired_block_bootstrap_95_interval'])} | {r['original_bust_hands']}/{r['baseline_bust_hands']}/{r['candidate_bust_hands']} |")
    lines += ["", "Las 57 celdas, incluidos 2/3/4 jugadores y sentinelas de 20/100 bb, están en [validation_cells.csv](../results/action_search_2026-10-28/validation_cells.csv). Los JSON de celda y el resumen contienen fichas y diferencias por bloque para ambos controles.", "",
        "## Sesiones con eliminación", "",
        "Inicio 8 bb, máximo veinte manos, ciegas duplicadas cada diez. Dos grupos independientes por composición/formato, todos los asientos; muestra pequeña. Si cambian eliminaciones pueden divergir repartos posteriores. Se promedian rotaciones antes de estimar incertidumbre.", "",
        "| Contraste de fichas finales | Grupos | Delta, stacks iniciales | IC 95 % por grupos |", "|---|---:|---:|---|"]
    for control, r in validation["session_pooled"].items():
        lines.append(f"| v4−{control} | {r['groups']} | {r['mean_initial_stacks']:+.3f} | {interval(r['interval_95'])} |")
    sessions = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "validation").glob("session_*.json")]
    lines += ["", "| Escenario | Jugadores | Variante | Mesas | Fichas medias finales | Eliminados | Mesas ganadas |", "|---|---:|---|---:|---:|---:|---:|"]
    for scenario in plan["scenarios"]:
        for n in (5, 6):
            relevant = [r for r in sessions if r["scenario"] == scenario and r["players"] == n]
            for kind in ("v2", "v2mc", "v4"):
                variants = [r["variants"][kind] for r in relevant]
                lines.append(f"| {scenario} | {n} | {kind} | {len(variants)} | {statistics.mean(v['last_stacks']['hero'] for v in variants):.1f} | {sum(not v['hero_survived'] for v in variants)} | {sum(v['hero_survived'] and v['table_finished'] for v in variants)} |")
    lines += ["", "Mesas truncadas cuentan por sus fichas finales, no como victorias. Estos conteos no miden clasificación al torneo.", "",
        "## Cómputo, adaptación y seguridad", "",
        "| Fase | Variante | Decisiones de comparación | p50 | p95 | Máximo |", "|---|---|---:|---:|---:|---:|"]
    for phase, analysis in analyses.items():
        for kind, t in analysis["latency"].items():
            lines.append(f"| {phase} | {kind} | {t['decisions']} | {t['p50_ms']:.1f} ms | {t['p95_ms']:.1f} ms | {t['max_ms']:.1f} ms |")
    for phase, analysis in analyses.items():
        a = analysis["audit"]
        lines += ["", f"{phase}: {a.get('searches',0)} búsquedas, {a.get('changes',0)} cambios frente a la acción base, mundos p50/p95/máximo {analysis['worlds']['p50']}/{analysis['worlds']['p95']}/{analysis['worlds']['max']}; {a['partial_equity_samples']} estimaciones base parciales. Paradas: {json.dumps({k.removeprefix('stop:'): v for k,v in a.items() if k.startswith('stop:')}, ensure_ascii=False)}.", ""]
    lines += [f"Comprobaciones de validación: {json.dumps(validation['checks'], ensure_ascii=False)}. La retención de v2 por plazo de búsqueda se publica separada de los respaldos por error. No se usó el supervisor para generar resultados estratégicos; se midió aparte el camino de producción.", "",
        f"El perfil supervisado ejecutó {len(profile['rows'])} decisiones normales en ocho estados públicos de desarrollo, con {profile['normal_fallbacks']} respaldos y {profile['normal_over_4250_ms']} decisiones sobre 4 250 ms. El proceso bloqueado intencionalmente respondió con respaldo legal en {profile['intentional_stall']['elapsed_ms']:.1f} ms; prueba {'aprobada' if profile['fault_passed'] else 'fallida'}. Véase [profile.json](../results/action_search_2026-10-28/profile.json). Estos estados no definen un percentil representativo de producción.", "",
        "Los tiempos incluyen preparación, muestreo y selección; el perfil v4 añade IPC y vigilancia. Excluyen arranque, parseo y red. El presupuesto cooperativo no equivale al supervisor, ni el supervisor local a una garantía del plazo oficial extremo a extremo.", "",
        "## Casos y diagnóstico", "",
        "Ejemplos de cambios sin corte de reloj, elegidos entre pérdidas y ganancias realizadas. No son pruebas individuales de EV:", ""]
    for item in analyses["validation"]["selected_cases"]:
        entry = item["decision"]
        obs = Observation.from_dict(entry["observation"])
        s = entry["decision"]["search"]
        arm = next(a for a in s["arms"] if a["action"] == s["chosen"])
        expected_gain = min(arm["paired_gain_chips"].values()) / obs.big_blind
        base_text = action_text({"decision": {"action": s["baseline"]}})
        chosen_text = action_text({"decision": {"action": s["chosen"]}})
        lines.append(f"- {item['scenario']}, {item['players']} jugadores, {item['depth_bb']} bb, bloque {item['block']}, rotación {item['rotation']}: {''.join(obs.hole_cards)} {obs.position}; base {base_text}, v4 {chosen_text}. El modelo estimaba al menos {expected_gain:+.2f} bb frente a su base; delta realizado de la mano frente a v2 original {item['delta_original_bb']:+.1f} bb. Reproducción de las tres variantes: {'coincide' if all(r['matched'] for r in item['replays'].values()) else 'difiere'}.")
    lines += ["", "[analysis.json](../results/action_search_2026-10-28/validation/analysis.json) conserva los tres registros completos de cada ejemplo, comparaciones reproducidas, auditoría de barajas, transiciones de acción y contextos por posición, rivales, precio y efectivo. Los contextos de resultados se definen con la primera observación de v2 original; son exploratorios y no equivalen al valor causal de una acción. Las simulaciones que tocaron reloj pueden tener distinto número de mundos al repetirlas; no se oculta esa limitación.", "",
        "## Criterios y límites", ""]
    actual = analyses["validation"]["audit"]
    lines += [f"En {actual.get('nonterminal_raise_windows',0)} secuencias con subida de v4 que dejaba fichas efectivas detrás, hubo {actual.get('nonterminal_windows_with_reraise',0)} resubidas rivales antes de la siguiente decisión propia o el cambio de calle. El modelo fold/call omite esa respuesta; se publica como diagnóstico de sesgo, sin recalibrar la candidata después de validar.", ""]
    labels = {"primary_mc_positive": "Mejora principal frente al control de mayor muestreo",
              "primary_original_positive": "Mejora principal frente a v2 original",
              "both_formats_nonnegative": "Media no negativa en cinco y seis jugadores frente a ambos controles",
              "sessions_nonnegative": "Sesiones: límite inferior no negativo frente a ambos controles",
              "safety": "Acciones, respaldos por error, fichas y plazo local"}
    for name, passed in validation["criteria"].items():
        lines.append(f"- {labels[name]}: {'cumplido' if passed else 'no cumplido'}.")
    lines += ["", "La búsqueda valora respuestas fold/call y checkdown; aún faltan resubidas y apuestas posteriores. Más muestras reducen el ruido del modelo supuesto, pero no corrigen ese sesgo. Las ganancias calculadas en el propio modelo no bastan para promover una estrategia. Los intervalos por escenario son descriptivos y no corrigen comparaciones múltiples.", "",
        "La API y el formato completo del torneo siguen pendientes. Todas las semillas de esta validación pasan a ser desarrollo tras examinar los resultados. El código y los criterios se fijaron antes del piloto; no se retocó la candidata al ver esta evidencia.", "",
        "Para comandos, configuraciones, supervisor y recuperación del código anterior véase [BUSQUEDA_V4_METODO.md](BUSQUEDA_V4_METODO.md). La decisión legible por máquina está en [decision.json](../results/action_search_2026-10-28/decision.json)."]
    (ROOT / "docs/BUSQUEDA_V4_RESULTADOS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2))
    return decision


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--audit-phase", choices=("pilot", "validation"))
    parser.add_argument("--reuse-analysis", action="store_true", help="Regenerar el documento sin repetir simulaciones ya auditadas")
    a = parser.parse_args()
    if a.audit_phase:
        result = audit(Path(a.root), a.audit_phase)
        print(json.dumps({k: result[k] for k in ("phase", "audit", "worlds", "latency")}, indent=2))
    else:
        report(Path(a.root), a.reuse_analysis)

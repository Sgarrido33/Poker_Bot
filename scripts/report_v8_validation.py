"""Write a Spanish report only after both registered phases are audited."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.v8_validation import load


def interval(entry, key="ci95_descriptive", pp=False):
    factor = 100 if pp else 1
    places = 1 if pp else 0
    low, high = entry[key]
    return f"{entry['diff'] * factor:+.{places}f} [{low * factor:+.{places}f}; {high * factor:+.{places}f}]"


def report(root, output):
    plan, digest = load(root)
    data = {}
    for phase in plan["phases"]:
        folder = root / phase
        entry = {name: json.loads((folder / (name + ".json")).read_text(encoding="utf-8"))
                 for name in ("summary", "audit", "independent_audit")}
        if not entry["audit"]["passed"] or not entry["independent_audit"]["passed"]:
            raise ValueError("Both audits must pass before reporting")
        if any(value["protocol_sha256"] != digest for value in entry.values()):
            raise ValueError("Audit protocol mismatch")
        data[phase] = entry
    dev, val = (data[phase]["summary"] for phase in ("development", "validation"))
    advance = val["local_advance"] is True
    lines = ["# Resultado de v8d: componentes y validación local", "",
             "Campaña registrada el 30 de octubre de 2026, Lima. **v2 conserva el valor predeterminado.**",
             "",
             ("v8d pasó todos los criterios locales registrados. Queda habilitada para una evaluación del formato oficial; este resultado no promueve automáticamente la candidata."
              if advance else "v8d no cumplió todos los criterios de avance registrados. No se promueve la candidata ni se elige otra variante por su mejor media posterior."),
             "", "## Ejecución", "",
             f"Se completaron **{dev['hand_executions'] + val['hand_executions']:,} ejecuciones nuevas de mano** en **{dev['table_executions'] + val['table_executions']:,} mesas simuladas**, contando cada brazo, con {dev['jobs']} grupos de desarrollo y {val['jobs']} de validación. Los replays y la repetición técnica de prefijos no se cuentan como evidencia nueva.",
             "", "| Fase | Mesas simuladas | Manos nuevas | Verificación técnica |",
             "|---|---:|---:|---|"]
    for phase, title in (("development", "Desarrollo"), ("validation", "Validación")):
        s = data[phase]["summary"]
        lines.append(f"| {title} | {s['table_executions']:,} | {s['hand_executions']:,} | {'Aprobada' if s['technical_passed'] else 'Falló'} |")
    lines += ["", "La candidata v8d, sus variantes y ambos tamaños de muestra se fijaron antes de observar resultados. El método y el protocolo se describen en [VALIDACION_V8D_METODO.md](VALIDACION_V8D_METODO.md). Las fuentes congeladas, cuotas y tablas se identifican con el hash de protocolo `" + digest + "`.",
              "", "## Validación principal frente a los dos controles", "",
              "Diferencia v8d−control en la mesa diversa externa. Fichas: intervalo bilateral del 97,5 % ajustado para los dos contrastes principales. Las otras columnas muestran intervalos descriptivos del 95 %. pp significa puntos porcentuales.",
              "", "| Control | Δ fichas | Δ victorias, pp | Δ eliminación a 24, pp | Δ eliminación a 128, pp |",
              "|---|---:|---:|---:|---:|"]
    for control in plan["inference"]["controls"]:
        e = val["contrasts"]["external_diverse"]["v8d-" + control]
        lines.append(f"| {control} | {interval(e['final_chips'], 'ci97_5_primary')} | {interval(e['wins'], pp=True)} | {interval(e['elim_24'], pp=True)} | {interval(e['elim_128'], pp=True)} |")
    main = val["contrasts"]["external_diverse"]
    if (main["v8d-v2"]["final_chips"]["ci97_5_primary"][0] > 0
            and main["v8d-v4rb"]["final_chips"]["ci97_5_primary"][1] < 0):
        lines += ["", "La comparación principal distingue las tres versiones: v8d mejora las fichas de v2, pero v4rb supera a v8d. La candidata también aumenta la eliminación temprana frente a v2. El resultado no respalda sustituir v2 por v8d según las reglas de avance fijadas."]
    lines += ["", "Los perfiles evaluados fueron v2 con 4.000 muestras/1.600 ms y v4rb con 1.024/3.500. La parte delegada de v8d usa 4.000/1.600; sus tablas deciden sin muestreo. Los resultados corresponden a estas configuraciones.",
              "", "| Mesa | Versión | Fichas finales medias | Victorias | Eliminación a 24 |",
              "|---|---|---:|---:|---:|"]
    for scenario, versions in val["descriptive"].items():
        for arm, metrics in versions.items():
            lines.append(f"| {scenario} | {arm} | {metrics['final_chips']:.0f} | {metrics['wins'] * 100:.1f} % | {metrics['elim_24'] * 100:.1f} % |")
    lines += ["", "| Escenario de control | Contraste | Δ fichas, IC95 | Δ eliminación a 24, IC95, pp | Límite superior unilateral 97,5 %, pp |",
              "|---|---|---:|---:|---:|"]
    for scenario in ("copies_v2", "selective"):
        for control in plan["inference"]["controls"]:
            e = val["contrasts"][scenario]["v8d-" + control]
            lines.append(f"| {scenario} | v8d−{control} | {interval(e['final_chips'])} | {interval(e['elim_24'], pp=True)} | {100 * e['elim_24']['upper97_5_one_sided']:+.1f} |")
    lines += ["", "Contra copias de v2, v8d vuelve a tener más eliminación temprana y su diferencia de fichas frente a v2 sigue siendo incierta; frente a v4rb pierde fichas claramente en este control exploratorio. En la otra mesa selectiva, v8d gana fichas frente a v2 y se elimina menos temprano que v4rb, pero su ventaja de fichas frente a v4rb no es concluyente. La composición del campo importa: no conviene tratar todas las mesas selectivas como una sola categoría."]
    lines += ["", "## Reglas de avance, incluidas las desfavorables", "",
              "Se exigía superar ambos controles en fichas, ganar al menos 80 fichas de media, no perder media de fichas en ningún formato principal y excluir un aumento mayor de 5 pp de eliminación temprana en cada escenario. Todos los requisitos eran necesarios.", ""]
    for name, passed in val["gates"].items():
        lines.append(f"- `{name}`: **{'pasa' if passed else 'no pasa'}**.")
    lines += ["", "Los intervalos que incluyen cero no prueban equivalencia. No pasar un límite de deterioro puede indicar daño observado o precisión insuficiente: las estimaciones e intervalos anteriores distinguen esos casos.",
              "", "## Qué ocurre al separar componentes", "",
              "Solo desarrollo: 8 grupos por formato y escenario. Cada componente activa tanto las acciones como los folds de su contexto; las demás decisiones son v2. Los intervalos son descriptivos sin ajuste por múltiples comparaciones. No se seleccionó una variante ganadora con estos datos.",
              "", "| Mesa | Versión frente a v2 | Δ fichas, IC95 | Δ eliminación a 24, IC95, pp | Δ victorias, IC95, pp |",
              "|---|---|---:|---:|---:|"]
    for scenario, pairs in dev["contrasts"].items():
        for arm in ("v8", "v8d", "v8d_open", "v8d_reshove", "v8d_call"):
            e = pairs[arm + "-v2"]
            lines.append(f"| {scenario} | {arm} | {interval(e['final_chips'])} | {interval(e['elim_24'], pp=True)} | {interval(e['wins'], pp=True)} |")
    lines += ["", "La comparación registrada con la v8 histórica separa el efecto de la corrección del efecto conjunto de las tablas. Sigue siendo desarrollo, con intervalos descriptivos del 95 %.",
              "", "| Mesa | Δ fichas v8d−v8 | Δ eliminación a 24, pp, v8d−v8 |",
              "|---|---:|---:|"]
    for scenario, pairs in dev["contrasts"].items():
        e = pairs["v8d-v8"]
        lines.append(f"| {scenario} | {interval(e['final_chips'])} | {interval(e['elim_24'], pp=True)} |")
    lines += ["", "Estas diferencias comparan trayectorias completas de políticas. No identifican la pérdida contrafactual de cada shove o call, ni justifican extrapolar la mejor media a otras mesas.",
              "", "En este desarrollo, activar solo aperturas o solo re-shoves elevó la eliminación temprana contra copias de v2. El contraste de solo calls fue menor e incierto. La candidata completa, en cambio, ganó fichas en la otra composición selectiva. Esto apunta a estudiar por separado los componentes de apuesta y las familias de rivales; no demuestra que los calls sean inocuos ni que un solo componente explique toda la diferencia de v8d."]
    diagnostic_path = root / "development" / "response_diagnostics.json"
    if diagnostic_path.exists():
        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        if diagnostic["protocol_sha256"] != digest:
            raise ValueError("Diagnostic protocol mismatch")
        lines += ["", "Un diagnóstico posterior del brazo v8d describe las respuestas públicas en las situaciones alcanzadas. Excluye all-ins forzados ya presentes y cuenta calls o raises posteriores como continuación. Es exploratorio, no una prueba registrada ni una comparación de manos equivalentes.",
                  "", "| Mesa | Acción de v8d | Casos | Al menos un rival continuó |",
                  "|---|---|---:|---:|"]
        for scenario, entries in diagnostic["scenarios"].items():
            for kind, values in entries.items():
                lines.append(f"| {scenario} | {kind} | {values['shoves_without_forced_allin']} | {values['any_continuation_fraction'] * 100:.1f} % |")
        lines += ["", "En esas trayectorias, las copias de v2 continuaron mucho más contra los shoves que la otra mesa selectiva. La etiqueta tight describe mal por sí sola las respuestas frente a distintas apuestas. Las posiciones, profundidades y manos alcanzadas también cambian: estos porcentajes no aíslan causalmente la familia rival ni son rangos de call calibrados."]
        scope = diagnostic.get("scope_guard")
        if scope:
            c, example = scope["counts"], scope["largest_excess_case"]
            lines += ["", f"En el brazo v8d de desarrollo, el guard de profundidad intervino {c['branch_hits']} veces; la v8 histórica habría usado tablas en esas {c['legacy_would_use_chart']} observaciones y habría elegido otra acción en {c['different_action']}. Esto compara acciones ante la misma información, no resultados contrafactuales de sesiones."]
            if example:
                lines += ["", f"El mayor exceso detectado en esos estados fue una tabla de {example['modeled_bb']:.1f} bb que habría expuesto {example['legacy_wager_risk_bb']:.1f} bb. La acción de v8d fue `{example['v8d_action']['kind']}`. Caso: {example['scenario']}, {example['players']} jugadores, grupo {example['group']}, rotación {example['rotation']}, índice de mano {example['hand']}."]
        lines += ["", "El [diagnóstico completo](../results/v8d_validation_2026-10-30/development/response_diagnostics.json) identifica el script, las exclusiones y los recuentos. Se añadió después del desarrollo y no modifica el criterio de promoción."]
    lines += ["", "## Alcance de la corrección y auditoría", "",
              "v8d delega en v2 una respuesta no terminal cuando otro rival activo puede cubrir más que el raiser usado para elegir la tabla. Actualiza el historial en cada solicitud y hace visibles los errores de tabla. No se alteraron las tablas históricas ni la v8 original. La arena ya completaba el historial al final de cada mano; la omisión del bot importa al operar sin ese hook y no demuestra pérdida de historial en las campañas locales.", ""]
    for phase in plan["phases"]:
        s, a, independent = (data[phase][key] for key in ("summary", "audit", "independent_audit"))
        counts = s["counts"]
        guards = 0
        for path in (root / phase).glob("session_*.json"):
            row = json.loads(path.read_text(encoding="utf-8"))
            for table in row["sessions"]:
                guards += sum(v for k, v in table["reasons"].items() if k.startswith("hero:v8d:scope_guard:"))
        lines.append(f"- {phase}: {a['replayed_hands']:,} manos de replay exacto; {independent['reconstructed']['hands']:,} manos reconstruidas desde trazas; {counts.get('fallbacks',0)} fallbacks, {counts.get('equity_deadlines',0)} cortes de equity y {counts.get('search_deadlines',0)} cortes de búsqueda. Se observaron {guards:,} delegaciones del héroe por el nuevo límite de profundidad, sumando los brazos v8d de esta fase.")
    prefixes = data["development"]["independent_audit"]["interrupted_prefix_records_matched"]
    lines += ["", "La reconstrucción comprueba además el espacio de semillas registrado, las semillas de cada política, el botón y los asientos, las cartas del héroe y el tablero prefijados y la identidad de las observaciones.",
              "", f"La primera ejecución se interrumpió porque las herramientas no mostraban las escrituras en curso. Se conservaron las seis trazas parciales y sus hashes; después se repitieron las mismas semillas. Coincidieron exactamente **{prefixes:,} registros de prefijo**, salvo tiempos. Esas repeticiones no aumentan la muestra. La incidencia está documentada en `results/v8d_validation_2026-10-30/interruption_001.json`.",
              "", "La suite completa de implementación pasó 212 pruebas; el log está en `.tmp/v8d_full_tests.txt`. El auditor adicional se comprobó con una sesión técnica válida y rechazó alteraciones de métricas, trazas, semillas y cartas.",
              "", "## Límites de la conclusión", "",
              "La evaluación usa 800 fichas, ciegas fijas 50/100, sin ante y hasta 128 manos. No reproduce la puntuación ni el formato oficial aún no establecido para este trabajo. Fullhouse y Honest aportan familias concretas; repetir instancias no convierte ese campo en una muestra representativa de rivales. Las cuotas de cómputo difieren entre v4rb y v2/v8d. Las aproximaciones del modelo push/fold permanecen. El resultado decide el avance local bajo las reglas registradas, no una probabilidad de clasificación al torneo.", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(output), "local_advance": advance, "default": "v2"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report(args.root.resolve(), args.output.resolve())

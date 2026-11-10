"""Build the Spanish evidence report from complete audited artifacts."""
import argparse
import json
from pathlib import Path
import re
import statistics


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def number(value, digits=2, signed=False):
    if round(value, digits) == 0:
        value = 0.
    return format(value, ("+" if signed else "") + f".{digits}f").replace(".", ",")


def count(value):
    return format(value, ",").replace(",", ".")


def estimate(row, scale=1, digits=2):
    mean = number(row["mean"] * scale, digits, True)
    bounds = row["interval_95_exploratory"]
    return mean + (" [" + "; ".join(number(value * scale, digits, True) for value in bounds) + "]" if bounds else " [sin intervalo]")


def run(root, output):
    campaign = root / "experiment"
    pilot, main = (read(campaign / phase / "summary.json") for phase in ("pilot", "comparison"))
    audit = read(campaign / "comparison" / "audit.json")
    pilot_audit = read(campaign / "pilot" / "audit.json")
    if not all((pilot["complete"], main["complete"], audit["passed"], pilot_audit["passed"])):
        raise ValueError("Complete and audit all phases first")
    variance, calibration = read(root / "variance.json"), read(root / "calibration.json")
    optimization = read(root / "optimization.json")
    quiet_path = root / "optimization_quiet.json"
    quiet = read(quiet_path) if quiet_path.exists() else None
    decision = read(root / "optimization_decision.json")
    test_log = (root / "tests_release.txt").read_text(encoding="utf-8-sig")
    tests = re.search(r"Ran (\d+) tests", test_log).group(1)
    if "\nOK" not in test_log:
        raise ValueError("Final tests did not pass")
    total = pilot["reset_hand_executions"] + main["reset_hand_executions"] + main["session_hand_executions"]
    replay_hands = sum(row.get("replay_hands_excluded_from_new_evidence", 0) for row in (audit, pilot_audit))
    ratio = variance["variance_ratio_integrated_over_sampled"]
    times = variance["estimator_seconds_excluding_card_worlds_and_compilation"]
    cost_ratio = times["integrated"] / times["sampled"]
    against_v2 = main["contrasts"]["v7-v2"]["sessions"]["all"]
    lines = ["# Comparación de seis versiones y candidata v7", "",
        "29 de octubre de 2026, hora de Lima. **v2 sigue predeterminada. No hay promoción de v7.**",
        "Esta campaña es exploratoria: intervalos sin corrección por las múltiples comparaciones, pocos grupos de sesiones y condiciones locales.", "",
        f"La mayor precisión del estimador no acreditó una mejora práctica: en las sesiones, v7 terminó con "
        f"{number(-against_v2['final_stack_fraction']['mean']*800)} fichas menos de media que v2 y "
        f"{number(against_v2['bust_24']['mean']*100)} puntos más de eliminación a 24 manos. "
        "v4rb tuvo la mayor media de fichas finales de esta batería. Estas observaciones conservan sus intervalos y límites abajo.", "",
        "## Qué se completó", "",
        f"Se completaron **{count(total)} ejecuciones nuevas de mano**: {count(pilot['reset_hand_executions'])} en piloto, "
        f"{count(main['reset_hand_executions'])} con fichas reiniciadas en la comparación y {count(main['session_hand_executions'])} en sesiones con eliminación.",
        f"La comparación tiene {main['reset_independent_blocks']} bloques independientes de barajas y {main['session_independent_seed_groups']} grupos independientes de sesiones. "
        "Las rotaciones de un grupo no son observaciones independientes.", "",
        "El [método](INTEGRACION_RESUBIDAS_V7_METODO.md) explica el algoritmo, los perfiles de cálculo y los límites. "
        "El [protocolo](../results/integrated_shove_2026-10-29/experiment/protocol.json) fijó ambas fases antes del piloto. "
        "Se ejecutó todo desde el código congelado, sin ajustar políticas por los resultados.", "",
        "## Versiones comparadas", "",
        "Medias con igual peso por escenario/formato y, en reset, por profundidad. Las sesiones empiezan con 800 fichas, ciegas 50/100 y llegan hasta 128 manos.", "",
        "| Versión | Reset, bb/mano | Fichas finales | Eliminación a 24 | Eliminación a 128 | p95 local por decisión |",
        "|---|---:|---:|---:|---:|---:|"]
    for arm, row in main["descriptive"].items():
        lines.append(f"| {arm} | {number(row['reset_bb_per_hand'],3,True)} | {number(row['mean_final_stack'])} | "
                     f"{number(row['bust_24']*100)} % | {number(row['bust_128']*100)} % | "
                     f"{number(audit['hero_latency'][arm]['p95_ms'],1)} ms |")
    lines += ["", "v2 usa 4.000 muestras; los otros brazos tienen cuota de 1.024, de las que v5/v7 reservan la mitad para entrenar. "
        "En los brazos con búsqueda se calculan además hasta 1.024 mundos para la equity de la decisión local. "
        "Las cuotas iguales no representan igual CPU. v2mc conserva las reglas congeladas con esa cuota menor. "
        "Las medias de esta tabla no bastan para declarar una versión ganadora.", "",
        "## Contrastes de v7, incluidos los desfavorables", "",
        "Diferencia candidata−control, con intervalo bootstrap exploratorio del 95 %. En eliminación, un valor negativo favorece a v7; en fichas y bb/mano, uno positivo.", "",
        "| Control | Reset: Δ bb/mano | Sesiones: Δ fichas finales | Δ eliminación a 24, pp | Δ eliminación a 128, pp |",
        "|---|---:|---:|---:|---:|"]
    for control in ("v2", "v4rb", "v5"):
        contrast = main["contrasts"]["v7-" + control]
        session = contrast["sessions"]["all"]
        lines.append(f"| {control} | {estimate(contrast['reset_bb_per_hand']['all'],digits=3)} | "
                     f"{estimate(session['final_stack_fraction'],800)} | {estimate(session['bust_24'],100)} | "
                     f"{estimate(session['bust_128'],100)} |")
    lines += ["", "La comparación v7−v5 estudia el efecto conjunto de integrar respuestas y aprender continuaciones con pesos de alcance. "
        "Los intervalos son descriptivos, no pruebas confirmatorias. El [resumen completo](../results/integrated_shove_2026-10-29/experiment/comparison/summary.json) conserva los 15 pares.", "",
        "### Escenario externo diverso", "",
        "Fullhouse, Honest educativo, v2 y pressure; solo ocho grupos independientes de sesiones entre ambos formatos.", "",
        "| Control | Reset: Δ bb/mano | Δ fichas finales | Δ eliminación a 128, pp |", "|---|---:|---:|---:|"]
    for control in ("v2", "v4rb", "v5"):
        contrast = main["contrasts"]["v7-" + control]
        session = contrast["sessions"]["external_diverse"]
        lines.append(f"| {control} | {estimate(contrast['reset_bb_per_hand']['external_diverse'],digits=3)} | "
                     f"{estimate(session['final_stack_fraction'],800)} | {estimate(session['bust_128'],100)} |")
    lines += ["", "## Precisión del estimador y costo", "",
        f"Con la misma continuación pública fija de pagar, la integración redujo un **{number((1-ratio)*100,1)} %** la varianza entre réplicas "
        f"a igual número de mundos. El cálculo del estimador consumió **{number(cost_ratio)}×** el tiempo del muestreado, "
        f"excluyendo cartas y compilación. El producto varianza×tiempo fue **{number(ratio*cost_ratio)}×**, desfavorable en esta prueba. "
        "No se ha demostrado una ventaja a igual tiempo de CPU.", "",
        "Son siete fixtures de desarrollo, tres priors, 24 réplicas y 128 mundos por réplica. "
        "La continuación fija aísla integración; no mide la calidad del aprendizaje ni la fuerza. "
        "Los datos están en [variance.json](../results/integrated_shove_2026-10-29/variance.json).", "",
        "## Dónde falla el modelo de respuestas", "",
        f"El diagnóstico seleccionó {len(calibration['states'])} estados públicos distintos de respuestas inmediatas a subidas preflop no terminales, "
        "sin consultar ganancias ni cartas rivales. Hay un máximo de 12 por celda/familia. Los estados están correlacionados y la selección no representa todo el torneo.", "",
        "| Rival | Estados | Call observado | Call predicho, equilibrado | Subida terminal observada | Subida terminal predicha |",
        "|---|---:|---:|---:|---:|---:|"]
    for family, row in calibration["aggregate"].items():
        if family == "all":
            continue
        actual, predicted = row["observed_rates"], row["priors"]["balanced"]["mean_predicted_rates"]
        lines.append(f"| {family} | {row['states']} | {number(actual['call']*100,1)} % | {number(predicted['call']*100,1)} % | "
                     f"{number(actual['terminal_raise']*100,1)} % | {number(predicted['terminal_raise']*100,1)} % |")
    lines += ["", "El modelo también asigna probabilidad cero a las resubidas no terminales: "
        f"se observaron {calibration['aggregate']['all']['observed_counts'].get('nonterminal_raise',0)} en esta selección. "
        "Este diagnóstico mira solo la respuesta inmediata, no toda la cadena de respuestas.", "",
        "Los priors se mantuvieron fijos. No se eligió el de menor Brier ni se reajustaron umbrales con estas observaciones. "
        "La discrepancia entre familias muestra por qué una expectativa más precisa bajo un modelo no garantiza mejores apuestas. "
        "Las probabilidades, scores Brier y observaciones están en [calibration.json](../results/integrated_shove_2026-10-29/calibration.json).", "",
        "## Optimización y reparaciones técnicas", "",
        "Se ensayó compartir hojas terminales idénticas y preasignar estadísticas de continuación. "
        f"La primera medición, bajo carga de la campaña, dio un factor global de {number(optimization['total_median_speedup'])}× "
        "y no confirmó una mejora de tiempo. Se conserva ese resultado adverso."]
    if quiet:
        lines.append(f"La repetición sin los workers de partidas dio **{number(quiet['total_median_speedup'])}×**, "
                     f"equivalente a {number((1-1/quiet['total_median_speedup'])*100,1)} % menos tiempo. "
                     "La decisión registrada sobre la optimización es: **" + decision["decision"] + "**.")
    lines += ["Se verificaron 21 parejas de búsquedas fijas y 20 pares de manos completas; coinciden exactamente acción, equity, "
        "EV, errores de Monte Carlo, mundos y continuaciones. Solo se excluyen tiempos y número de nodos compilados, "
        "que cambia al compartir hojas. Es equivalencia técnica, no evidencia nueva de fuerza.", "",
        "La CLI permite ahora `--baseline-samples` y `--baseline-budget-ms`, además de los perfiles de rivales. "
        "Se corrigió la herencia del presupuesto de 3.500 ms por controles/rivales v2 y el contador fijo de muestras del informe. "
        "Estos cambios no entraron en el snapshot de la campaña.", "",
        "## Auditoría y límites", "",
        f"La suite final pasa **{tests} pruebas**. La auditoría reconstruyó todas las manos y {audit.get('session_tables',0)} mesas de sesiones, "
        f"comprobó {audit['hero_decisions']} decisiones públicas y coincidieron **{replay_hands} manos de replay** "
        "seleccionadas antes de ver resultados. Los replays se excluyen de las ejecuciones nuevas.",
        "El estado técnico de la matriz, incluyendo cortes del reloj, fue **" + ("aprobado" if main["technical_passed"] else "NO aprobado") + "**. "
        "Las [auditorías](../results/integrated_shove_2026-10-29/experiment/comparison/audit.json), "
        "[tests](../results/integrated_shove_2026-10-29/tests_release.txt) y "
        "[fuentes congeladas](../results/integrated_shove_2026-10-29/experiment/source) permiten revisar el cálculo. "
        "La [integridad final](../results/integrated_shove_2026-10-29/integrity.json) identifica fuentes y artefactos.", "",
        "Las reglas y premios oficiales siguen sin estar definidos en el proyecto. Los resultados son sobre supuestos locales, "
        "no probabilidades de clasificación. Las mesas censuradas conservan sus fichas observadas y no reciben puestos o victorias inventados. "
        "La continuación aprendida valora escenarios hipotéticos; el bot recalcula cada turno real y puede responder de otra forma. "
        "Se mantienen todos los resultados y v2 como predeterminada.", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.root.resolve(), args.output.resolve()))

"""Render the completed experiment without changing any measurements."""
import json
from pathlib import Path
import re

ROOT = Path("results/challenge_2026-10-27")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def interval(values):
    return f"[{values[0]:+.2f}; {values[1]:+.2f}]"


def main():
    development = read(ROOT / "development/summary.json")
    holdout = read(ROOT / "holdout/summary.json")
    comparison = read(ROOT / "comparison/summary.json")
    proof = read(ROOT / "comparison/pricing_regression.json")
    unit_count = int(re.search(r"Ran (\d+) tests", (ROOT / "unit_tests.txt").read_text(encoding="utf-8")).group(1))
    total = (development["paired_hands"] + development["session_hands"] + holdout["paired_hands"]
             + holdout["session_hands"] + comparison["additional_session_hands"] + comparison["production_hands"])
    duplicate_fallbacks = sum(row[p]["fallbacks"] for row in comparison["paired_sessions"]
                             for p in ("v1", "v2") if row[p]["original_holdout"])
    fallbacks = development["fallbacks_all_policies"] + holdout["fallbacks_all_policies"] + comparison["fallbacks"] - duplicate_fallbacks
    lines = ["# Resultados de las pruebas ampliadas", "",
        f"Se completaron **{total:,} manos locales adicionales** en esta etapa, sin contar las 880 de la primera evaluación ni las pruebas unitarias.", "",
        f"Respuestas de respaldo de todas las políticas en estas partidas: **{fallbacks}**. Las evaluaciones se abortan ante acciones ilegales o pérdida de fichas; todas las ejecuciones terminaron.", "",
        f"La suite actual contiene **{unit_count} pruebas automatizadas aprobadas**, incluidas la regresión del call barato, la retirada ante mal precio, el avance del botón tras eliminaciones y la reproducción de manos.", "",
        "## Cantidades", "", "| Parte | Manos |", "|---|---:|",
        f"| Desarrollo, comparación pareada | {development['paired_hands']} |",
        f"| Desarrollo, mesas con eliminación | {development['session_hands']} |",
        f"| Validación reservada, comparación pareada | {holdout['paired_hands']} |",
        f"| Validación reservada, mesas con eliminación | {holdout['session_hands']} |",
        f"| Comparación v2/v1, mesas adicionales sin duplicar controles reutilizados | {comparison['additional_session_hands']} |",
        f"| Comprobaciones con 4 000 muestras | {comparison['production_hands']} |", "",
        "Las partidas repetidas por asiento o variante no se cuentan como repartos independientes. Desarrollo usa ocho bloques de tres barajas; validación, dieciséis de cuatro, por escenario y formato.", "",
        "## Política original en barajas reservadas", "",
        "El candidato es `v1`; la referencia es `tight` en el escenario básico y `tag` en los demás. Se utilizan 1 000 muestras del candidato y 256 de los rivales nuevos.", "",
        "| Escenario | Jugadores | Ganancia v1, bb/mano | Diferencia frente a referencia, bb/mano | Intervalo bootstrap por bloques, 95 % |",
        "|---|---:|---:|---:|---|" ]
    for row in holdout["paired_reports"]:
        lines.append(f"| {row['scenario']} | {row['players']} | {row['candidate_bb_per_hand']:+.3f} | {row['difference_bb_per_hand']:+.3f} | {interval(row['bootstrap_95_interval'])} |")
    lines += ["", "La ventaja frente a los rivales básicos se sostiene en este lote. Los intervalos de los escenarios con cálculo y copias del bot abarcan cero; no hay una ventaja clara frente a la referencia en esos escenarios con este tamaño de muestra. Los intervalos son aproximados y no corrigen la selección entre múltiples escenarios.", "",
        "## Corrección del call all-in", "",
        "Se conservó `v1` y se añadió `v2`, que valora el precio de calls preflop all-in antes de filtrar por rango inicial. Los demás umbrales y rangos no cambiaron.", "",
        "El caso de regresión tiene 72o y una ficha por pagar para disputar 102 fichas. `v1` se retira; `v2` paga. La prueba de control mantiene la retirada ante un all-in caro con equity insuficiente.", "",
        f"Como comprobación independiente, 100 000 simulaciones frente a AA fijo dieron equity {proof['equity_against_fixed_rival']:.4f}, devolución bruta esperada {proof['expected_return_against_fixed_rival']:.2f} y mejora incremental estimada de pagar frente a retirarse de {proof['incremental_call_ev_against_fixed_rival']:.2f} fichas. AA se usa solo en el cálculo de prueba, nunca en la observación enviada a las políticas. Es Monte Carlo, no enumeración exacta.", "",
        "## Comparación con fichas conservadas", "",
        "Mismas semillas y asientos iniciales para cada par v2/v1; cuatro grupos independientes por formato. Las rotaciones dentro de un grupo son dependientes. Si las eliminaciones divergen, los repartos posteriores pueden variar porque cambia el número de jugadores. Se comienza con 2 500 fichas, ciegas 50/100 y duplicación cada quince manos, con tope de noventa manos.", "",
        "| Jugadores | Mesas por variante | Mesas ganadas v1 | Mesas ganadas v2 | Diferencia media de fichas finales v2−v1 | Intervalo por grupos | Calls v2 que aplicaron la corrección |",
        "|---|---:|---:|---:|---:|---|---:|" ]
    for players, row in comparison["session_summary"].items():
        lines.append(f"| {players} | {row['tables_per_variant']} | {row['v1_wins']} | {row['v2_wins']} | {row['mean_paired_chip_difference']:+.1f} | {interval(row['group_bootstrap_95_interval'])} | {row['v2_all_in_price_calls']} |")
    lines += ["", "El contador de calls registra ejecuciones de la nueva regla, incluyendo casos en los que v1 también habría pagado.", "",
        "Cuatro grupos por formato son insuficientes para una estimación fiable de tasa de victoria. Estos conteos describen las mesas ejecutadas y no miden clasificación al torneo. La aceptación de la corrección se basa en resolver el fallo demostrado de precio; el agregado se publica también si empeora.", "",
        "## Configuración de 4 000 muestras", "",
        "| Comparación | Jugadores | Manos por variante | Diferencia bb/mano | Intervalo por bloques | p95 candidato | Máximo candidato | Respaldos de todas las políticas |",
        "|---|---:|---:|---:|---|---:|---:|---:|" ]
    for row in comparison["production_reports"]:
        lines.append(f"| {row['label']} | {row['players']} | {row['hands_per_variant']} | {row['delta']:+.3f} | {interval(row['bootstrap_95_interval'])} | {row['latency']['p95_ms']:.1f} ms | {row['latency']['max_ms']:.1f} ms | {row['fallbacks']} |")
    lines += ["", "Estos lotes usan otras barajas que la validación de 1 000 muestras; no permiten atribuir las diferencias de puntuación al número de muestras. En los lotes de 100 ciegas por jugador no hubo diferencia observada entre v2 y v1; la corrección actúa en situaciones de all-in concretas, frecuentes con stacks cortos."]
    lines += ["", f"Se reprodujeron exactamente las mayores pérdidas de **{len(comparison['replays'])} reportes**, incluyendo las manos anteriores necesarias para reconstruir perfiles. Los reportes de desarrollo provienen del código previo a añadir la corrección, por lo que su huella difiere; sus decisiones `v1` preservadas y resultados coinciden.", "",
        "Las latencias miden preparación, muestreo y selección dentro del bot, con el escritorio activo. Excluyen red, parseo y envío. El plazo sigue siendo cooperativo.", "",
        "## Artefactos y siguientes necesidades", "",
        "- [Método y comandos](PRUEBAS_AMPLIADAS.md)",
        "- [Plan original](../results/challenge_2026-10-27/protocol.json) y [plan de la corrección](../results/challenge_2026-10-27/correction_protocol.json)",
        "- [Resumen de desarrollo](../results/challenge_2026-10-27/development/summary.json)",
        "- [Resumen de validación reservada](../results/challenge_2026-10-27/holdout/summary.json)",
        "- [Comparación v2/v1, sesiones y repeticiones](../results/challenge_2026-10-27/comparison/summary.json)",
        "- [Caso de regresión](../results/challenge_2026-10-27/comparison/pricing_regression.json)",
        "- [Pruebas automatizadas](../results/challenge_2026-10-27/unit_tests.txt)", "",
        "La versión actual corrige un fallo concreto y dispone de pruebas más exigentes. Los resultados siguen señalando necesidad de mejorar la política con stacks cortos y calibrar rangos y respuestas frente a apuestas. Cualquier mejora posterior necesita nuevas semillas de validación, porque estos lotes ya se inspeccionaron. La API, el supervisor externo de plazos y el formato completo del torneo siguen pendientes.", ""]
    Path("docs/RESULTADOS_AMPLIADOS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"total_additional_hands": total, "fallbacks": fallbacks, "report": "docs/RESULTADOS_AMPLIADOS.md"}))


if __name__ == "__main__":
    main()

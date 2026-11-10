# Resultados de calidad: v4rb y v5

Fecha local: 28 de octubre de 2026.

**La política predeterminada permanece en v2.** Las nuevas variantes son experimentales.

Se completaron **8,155 ejecuciones nuevas de mano**: 3,960 con fichas reiniciadas y 4,195 en sesiones. Son cinco brazos con barajas compartidas; las ejecuciones no son observaciones independientes. Los mundos internos de Monte Carlo, replays y tests no se incluyen en esa cantidad.

El [método](CALIDAD_V5_METODO.md) y el [protocolo previo al piloto](../results/quality_2026-10-28/protocol.json) describen modelos, semillas, cuotas, agrupación y criterios. No se ajustaron parámetros después del piloto.

## Precisión del estimador

La integración exacta redujo **23.4 %** la varianza entre réplicas a igual número de mundos en siete estados de desarrollo: 24 réplicas de 128 mundos por estado/supuesto, 54 comparaciones no base. Se promedian las varianzas dentro de cada comparación; no se mezclan las diferencias de medias entre estados. Esta medición demuestra menor ruido bajo el mismo modelo fold/call, sin demostrar mayor fuerza de juego. Véase [variance.json](../results/quality_2026-10-28/variance.json).

## Resultados pareados

Igual peso a las 18 celdas de cinco/seis jugadores, 4/8/12 bb y tres escenarios. Bootstrap estratificado de bloques completos; cada bloque contiene todas las rotaciones de asiento. Los intervalos son exploratorios y no corrigen comparaciones múltiples.

| Etapa | Candidata | Δ frente a v4, bb/mano | IC 95 % | Δ frente a v2 | IC 95 % |
|---|---|---:|---|---:|---|
| Piloto | v4rb | -0.104 | [-0.249; +0.042] | +0.695 | [+0.066; +1.311] |
| Piloto | v5 | +0.065 | [-0.489; +0.608] | +0.864 | [+0.351; +1.366] |
| Validación | v4rb | +0.045 | [-0.037; +0.132] | +0.554 | [+0.148; +0.958] |
| Validación | v5 | +0.018 | [-0.274; +0.327] | +0.527 | [+0.203; +0.842] |

| Candidata | Jugadores | Δ frente a v4 | Δ frente a v2 |
|---|---:|---:|---:|
| v4rb | 5 | -0.043 | +0.324 |
| v4rb | 6 | +0.133 | +0.784 |
| v5 | 5 | +0.065 | +0.431 |
| v5 | 6 | -0.028 | +0.623 |

Las medias de cada celda, ganancias, manos que terminan sin fichas y diferencias están en [validation_cells.csv](../results/quality_2026-10-28/validation_cells.csv). En estas celdas se reponen las fichas: `bust_hands` cuenta manos con stack final cero y no eliminaciones de torneo. El control v2mc permite identificar el efecto de cambiar solo la cuota de muestreo.

## Sesiones con eliminación

Inicio de 8 bb, máximo veinte manos y ciegas duplicadas cada diez. Dos grupos independientes por escenario/formato en presión y copias v2; 44 mesas por brazo con todos los asientos. Se remuestrean grupos completos dentro de escenario/formato. La unidad de diferencia es una pila inicial de 800 fichas.

| Candidata | Δ fichas/800 frente a v4 | IC 95 % | Δ frente a v2 | IC 95 % |
|---|---:|---|---:|---|
| v4rb | -0.039 | [-0.106; +0.028] | +0.443 | [-0.101; +0.986] |
| v5 | -0.329 | [-0.909; +0.252] | +0.153 | [-0.548; +0.874] |

Los resúmenes completos, incluidos v4/v2mc frente a v2, están en [summary.json](../results/quality_2026-10-28/validation/summary.json).

## Comprobaciones y diagnóstico

- **87 pruebas aprobadas**, incluidas enumeración independiente de respuestas, oráculo PokerKit de resubidas, aislamiento de la continuación y cuotas pareadas. Véase [tests.txt](../results/quality_2026-10-28/tests.txt).
- Las 7 búsquedas con trabajo fijo y 20 manos completas coinciden exactamente con la v4 anterior al excluir los tiempos. El manifiesto de `frozen_v2` sigue intacto.
- 594 grupos de reparto auditados: misma semilla de baraja en los cinco brazos y conservación de fichas.
- 16 ejecuciones seleccionadas entre las mayores diferencias positivas y negativas frente a v4: todas coinciden al repetir observaciones, valores y decisiones con semillas y cuotas originales.
- Seguridad de las campañas: cumplida. Los JSON conservan los contadores de fallbacks y comprobaciones de fichas.

| Variante | Subidas con fichas efectivas detrás | Resubidas reales antes de volver a actuar | Pushes efectivos | Cambios por búsqueda |
|---|---:|---:|---:|---:|
| v4 | 357 | 28 | 134 | 424 |
| v4rb | 362 | 29 | 138 | 435 |
| v5 | 150 | 12 | 260 | 350 |

Los estados visitados cambian entre políticas: estos conteos son descriptivos, no un efecto causal de la técnica. El [análisis](../results/quality_2026-10-28/validation/analysis.json) incluye cobertura de las continuaciones, mundos, paradas y máximos de tiempo.

## Decisión y límites

- v4rb: no cumple todos los criterios registrados de promoción.
- v5: no cumple todos los criterios registrados de promoción.

La reducción de ruido de v4rb y el nuevo modelo de resubidas de v5 quedan disponibles para investigación. No se interpreta el valor calculado dentro del modelo como prueba de rentabilidad real. v5 omite más resubidas y apuestas futuras, usa supuestos manuales y una continuación de rollout que puede diferir de la decisión real posterior. Todos los lotes examinados pasan a ser datos de desarrollo. Siguen pendientes rivales externos, la arena oficial y el formato completo del torneo.

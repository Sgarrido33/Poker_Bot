# Resultados de las pruebas ampliadas

Nota del 28 de octubre: todos los lotes descritos aquí, incluidos los llamados reservados o holdout, ya fueron examinados y son datos de desarrollo. La siguiente iteración utiliza [barajas y protocolo nuevos](PREFLOP_V3_METODO.md), con sus [resultados por profundidad y jugadores](PREFLOP_V3_RESULTADOS.md). Las cantidades siguientes corresponden a la etapa histórica.

Se completaron **14,298 manos locales adicionales** en esta etapa, sin contar las 880 de la primera evaluación ni las pruebas unitarias.

Respuestas de respaldo de todas las políticas en estas partidas: **0**. Las evaluaciones se abortan ante acciones ilegales o pérdida de fichas; todas las ejecuciones terminaron.

La suite actual contiene **29 pruebas automatizadas aprobadas**, incluidas la regresión del call barato, la retirada ante mal precio, el avance del botón tras eliminaciones y la reproducción de manos.

## Cantidades

| Parte | Manos |
|---|---:|
| Desarrollo, comparación pareada | 2112 |
| Desarrollo, mesas con eliminación | 688 |
| Validación reservada, comparación pareada | 5632 |
| Validación reservada, mesas con eliminación | 1145 |
| Comparación v2/v1, mesas adicionales sin duplicar controles reutilizados | 3929 |
| Comprobaciones con 4 000 muestras | 792 |

Las partidas repetidas por asiento o variante no se cuentan como repartos independientes. Desarrollo usa ocho bloques de tres barajas; validación, dieciséis de cuatro, por escenario y formato.

## Política original en barajas reservadas

El candidato es `v1`; la referencia es `tight` en el escenario básico y `tag` en los demás. Se utilizan 1 000 muestras del candidato y 256 de los rivales nuevos.

| Escenario | Jugadores | Ganancia v1, bb/mano | Diferencia frente a referencia, bb/mano | Intervalo bootstrap por bloques, 95 % |
|---|---:|---:|---:|---|
| basic | 5 | +6.074 | +6.183 | [+3.12; +9.52] |
| basic | 6 | +4.999 | +4.923 | [+1.93; +8.22] |
| selective | 5 | +0.860 | +0.691 | [-0.13; +1.65] |
| selective | 6 | +0.544 | +0.261 | [-0.75; +1.42] |
| pressure | 5 | -0.057 | +1.338 | [-0.40; +3.04] |
| pressure | 6 | +1.042 | -0.272 | [-1.33; +0.73] |
| selfplay | 5 | +0.022 | +0.277 | [-0.64; +1.31] |
| selfplay | 6 | +0.010 | +0.311 | [-0.49; +1.09] |

La ventaja frente a los rivales básicos se sostiene en este lote. Los intervalos de los escenarios con cálculo y copias del bot abarcan cero; no hay una ventaja clara frente a la referencia en esos escenarios con este tamaño de muestra. Los intervalos son aproximados y no corrigen la selección entre múltiples escenarios.

## Corrección del call all-in

Se conservó `v1` y se añadió `v2`, que valora el precio de calls preflop all-in antes de filtrar por rango inicial. Los demás umbrales y rangos no cambiaron.

El caso de regresión tiene 72o y una ficha por pagar para disputar 102 fichas. `v1` se retira; `v2` paga. La prueba de control mantiene la retirada ante un all-in caro con equity insuficiente.

Como comprobación independiente, 100 000 simulaciones frente a AA fijo dieron equity 0.1112, devolución bruta esperada 11.34 y mejora incremental estimada de pagar frente a retirarse de 10.34 fichas. AA se usa solo en el cálculo de prueba, nunca en la observación enviada a las políticas. Es Monte Carlo, no enumeración exacta.

## Comparación con fichas conservadas

Mismas semillas y asientos iniciales para cada par v2/v1; cuatro grupos independientes por formato. Las rotaciones dentro de un grupo son dependientes. Si las eliminaciones divergen, los repartos posteriores pueden variar porque cambia el número de jugadores. Se comienza con 2 500 fichas, ciegas 50/100 y duplicación cada quince manos, con tope de noventa manos.

| Jugadores | Mesas por variante | Mesas ganadas v1 | Mesas ganadas v2 | Diferencia media de fichas finales v2−v1 | Intervalo por grupos | Calls v2 que aplicaron la corrección |
|---|---:|---:|---:|---:|---|---:|
| 5 | 20 | 0 | 2 | +1250.0 | [+0.00; +3750.00] | 24 |
| 6 | 24 | 4 | 5 | +625.0 | [+0.00; +1875.00] | 16 |

El contador de calls registra ejecuciones de la nueva regla, incluyendo casos en los que v1 también habría pagado.

Cuatro grupos por formato son insuficientes para una estimación fiable de tasa de victoria. Estos conteos describen las mesas ejecutadas y no miden clasificación al torneo. La aceptación de la corrección se basa en resolver el fallo demostrado de precio; el agregado se publica también si empeora.

## Configuración de 4 000 muestras

| Comparación | Jugadores | Manos por variante | Diferencia bb/mano | Intervalo por bloques | p95 candidato | Máximo candidato | Respaldos de todas las políticas |
|---|---:|---:|---:|---|---:|---:|---:|
| production_v1 | 5 | 120 | -3.639 | [-8.26; +0.39] | 82.3 ms | 100.8 ms | 0 |
| production_v1 | 6 | 144 | -1.329 | [-2.73; -0.26] | 106.8 ms | 166.9 ms | 0 |
| production_v2_vs_v1 | 5 | 60 | +0.000 | [+0.00; +0.00] | 87.6 ms | 92.6 ms | 0 |
| production_v2_vs_v1 | 6 | 72 | +0.000 | [+0.00; +0.00] | 105.6 ms | 120.0 ms | 0 |

Estos lotes usan otras barajas que la validación de 1 000 muestras; no permiten atribuir las diferencias de puntuación al número de muestras. En los lotes de 100 ciegas por jugador no hubo diferencia observada entre v2 y v1; la corrección actúa en situaciones de all-in concretas, frecuentes con stacks cortos.

Se reprodujeron exactamente las mayores pérdidas de **16 reportes**, incluyendo las manos anteriores necesarias para reconstruir perfiles. Los reportes de desarrollo provienen del código previo a añadir la corrección, por lo que su huella difiere; sus decisiones `v1` preservadas y resultados coinciden.

Las latencias miden preparación, muestreo y selección dentro del bot, con el escritorio activo. Excluyen red, parseo y envío. El plazo sigue siendo cooperativo.

## Artefactos y siguientes necesidades

- [Método y comandos](PRUEBAS_AMPLIADAS.md)
- [Plan original](../results/challenge_2026-10-27/protocol.json) y [plan de la corrección](../results/challenge_2026-10-27/correction_protocol.json)
- [Resumen de desarrollo](../results/challenge_2026-10-27/development/summary.json)
- [Resumen de validación reservada](../results/challenge_2026-10-27/holdout/summary.json)
- [Comparación v2/v1, sesiones y repeticiones](../results/challenge_2026-10-27/comparison/summary.json)
- [Caso de regresión](../results/challenge_2026-10-27/comparison/pricing_regression.json)
- [Pruebas automatizadas](../results/challenge_2026-10-27/unit_tests.txt)

La versión actual corrige un fallo concreto y dispone de pruebas más exigentes. Los resultados siguen señalando necesidad de mejorar la política con stacks cortos y calibrar rangos y respuestas frente a apuestas. Cualquier mejora posterior necesita nuevas semillas de validación, porque estos lotes ya se inspeccionaron. La API, el supervisor externo de plazos y el formato completo del torneo siguen pendientes.

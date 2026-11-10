# Resultados de la candidata preflop v3

Fecha local: 28 de octubre de 2026.

**Decisión: mantener v2 como predeterminada.** v3 no cumplió todos los criterios registrados. Se conserva disponible como candidata experimental.

El [método](PREFLOP_V3_METODO.md) y el [protocolo anterior al piloto](../results/shortstack_2026-10-28/protocol.json) fijan cantidades, semillas y aceptación. No se modificó la candidata después del piloto. Toda validación anterior, incluso los lotes llamados holdout, fue tratada como desarrollo.

Pasaron las **45 pruebas automatizadas**, incluidas las 29 originales, la regresión del call all-in barato, límites legales, aislamiento del control, manos doradas de 2–6 jugadores, contexto sin duplicar fichas, namespaces nuevos y reproducción con stacks cortos. El [registro de suite](../results/shortstack_2026-10-28/candidate_tests.txt) conserva la ejecución.

## Cantidades y resultado principal

| Etapa | Manos con reposición, ambas variantes | Manos de sesiones, ambas variantes | Delta principal bb/mano | IC 95 % por bloques |
|---|---:|---:|---:|---|
| pilot | 960 | 1005 | -0.007 | [-0.119; +0.105] |
| validation | 8064 | 5217 | -0.069 | [-0.123; -0.016] |
| production | 88 | 0 | -0.042 | [-0.188; +0.104] |

Se ejecutaron **15,334 manos adicionales**, sin contar pruebas unitarias, casos aislados o reproducciones. Son ejecuciones; las variantes y rotaciones no son repartos independientes. Piloto y validación cubren 60 celdas cada uno. La comprobación de 4 000 muestras cubre cuatro celdas de pressure, por lo que su agregado no es comparable al de las otras fases.

En validación, el contraste principal (5/6 jugadores, 4/8 bb) es **-0.069 bb/mano**, intervalo [-0.123; -0.016], con 144 bloques repartidos entre doce celdas. Cada celda pesa igual. Estos intervalos describen este conjunto sintético; no demuestran robustez general.

| Jugadores principales | Delta 4/8 bb | IC 95 % estratificado |
|---|---:|---|
| 5 | -0.081 | [-0.162; +0.001] |
| 6 | -0.057 | [-0.129; +0.011] |

## Todas las celdas principales

Stacks reiniciados cada mano; bb/mano. Las tasas de bust aquí permiten volver a jugar y no equivalen a eliminación de una sesión. Las celdas de 12/20 bb comprueban el comportamiento fuera del alcance inicial de la candidata.

| Rival | Jugadores | bb iniciales | v2 | v3 | v3−v2 | IC 95 % por bloques | Busts v2/v3 |
|---|---:|---:|---:|---:|---:|---|---:|
| selective | 5 | 4 | -0.115 | -0.223 | -0.108 | [-0.250; +0.029] | 8/8 |
| selective | 5 | 8 | +0.254 | -0.046 | -0.300 | [-0.638; -0.037] | 0/0 |
| selective | 5 | 12 | +0.234 | +0.234 | +0.000 | [+0.000; +0.000] | 1/1 |
| selective | 5 | 20 | +0.267 | +0.267 | +0.000 | [+0.000; +0.000] | 1/1 |
| selective | 6 | 4 | +0.003 | -0.090 | -0.094 | [-0.219; -0.010] | 5/5 |
| selective | 6 | 8 | +0.045 | -0.000 | -0.045 | [-0.337; +0.229] | 3/2 |
| selective | 6 | 12 | -0.186 | -0.186 | +0.000 | [+0.000; +0.000] | 2/2 |
| selective | 6 | 20 | +0.057 | +0.057 | +0.000 | [+0.000; +0.000] | 0/0 |
| pressure | 5 | 4 | -0.250 | -0.263 | -0.012 | [-0.037; +0.000] | 9/9 |
| pressure | 5 | 8 | +0.119 | +0.027 | -0.092 | [-0.296; +0.125] | 4/3 |
| pressure | 5 | 12 | +0.242 | +0.242 | +0.000 | [+0.000; +0.000] | 0/0 |
| pressure | 5 | 20 | +0.125 | +0.125 | +0.000 | [+0.000; +0.000] | 1/1 |
| pressure | 6 | 4 | -0.177 | -0.167 | +0.010 | [-0.021; +0.042] | 8/8 |
| pressure | 6 | 8 | +0.049 | +0.102 | +0.054 | [-0.120; +0.222] | 2/1 |
| pressure | 6 | 12 | +0.035 | +0.035 | +0.000 | [+0.000; +0.000] | 1/1 |
| pressure | 6 | 20 | +0.587 | +0.587 | +0.000 | [+0.000; +0.000] | 2/2 |
| copies_v2 | 5 | 4 | +0.012 | -0.104 | -0.117 | [-0.312; +0.067] | 5/6 |
| copies_v2 | 5 | 8 | -0.025 | +0.117 | +0.142 | [-0.071; +0.408] | 2/3 |
| copies_v2 | 5 | 12 | -0.342 | -0.342 | +0.000 | [+0.000; +0.000] | 6/6 |
| copies_v2 | 5 | 20 | -0.112 | -0.112 | +0.000 | [+0.000; +0.000] | 1/1 |
| copies_v2 | 6 | 4 | +0.000 | -0.097 | -0.097 | [-0.257; +0.056] | 5/7 |
| copies_v2 | 6 | 8 | -0.056 | -0.226 | -0.170 | [-0.323; -0.038] | 3/5 |
| copies_v2 | 6 | 12 | +0.000 | +0.000 | +0.000 | [+0.000; +0.000] | 3/3 |
| copies_v2 | 6 | 20 | +0.161 | +0.161 | +0.000 | [+0.000; +0.000] | 1/1 |

## Dos, tres y cuatro jugadores

Menos bloques; resultados secundarios agrupados con igual peso a las tres composiciones rivales. Las 60 celdas completas, fichas y busts están en [validation_cells.csv](../results/shortstack_2026-10-28/validation_cells.csv).

| Jugadores | bb iniciales | Delta medio | IC 95 % estratificado |
|---|---:|---:|---|
| 2 | 4 | -0.240 | [-0.448; -0.031] |
| 2 | 8 | +0.094 | [-0.125; +0.406] |
| 2 | 12 | +0.000 | [+0.000; +0.000] |
| 2 | 20 | +0.000 | [+0.000; +0.000] |
| 3 | 4 | -0.028 | [-0.194; +0.132] |
| 3 | 8 | -0.059 | [-0.174; +0.052] |
| 3 | 12 | +0.000 | [+0.000; +0.000] |
| 3 | 20 | +0.000 | [+0.000; +0.000] |
| 4 | 4 | -0.115 | [-0.286; +0.031] |
| 4 | 8 | +0.068 | [-0.193; +0.302] |
| 4 | 12 | +0.000 | [+0.000; +0.000] |
| 4 | 20 | +0.000 | [+0.000; +0.000] |

## Sesiones con eliminación

Inicio 8 bb, ciegas duplicadas cada diez manos, hasta treinta manos o un superviviente. Tres grupos independientes por composición y formato, todos los asientos. Las rotaciones dentro de un grupo se promedian antes de calcular incertidumbre. Las mesas truncadas conservan sus fichas finales; no se cuentan como ganadas.

Delta agregado de fichas finales: **-0.474 stacks iniciales**, intervalo [-0.842; -0.099]. La unidad es 800 fichas iniciales. Hay 18 grupos en total y solo tres por celda; las tasas de victoria son descriptivas.

| Rival | Jugadores | Mesas/variante | Fichas medias v2/v3 | Eliminados v2/v3 | Mesas ganadas v2/v3 | Delta por grupo, stacks iniciales | IC por grupos |
|---|---:|---:|---:|---:|---:|---|---|
| selective | 5 | 15 | 1056.7/780.0 | 10/11 | 2/2 | -1.000, +1.000, -1.038 | [-1.038; +1.000] |
| selective | 6 | 18 | 1225.0/452.8 | 10/14 | 1/0 | -0.427, -1.240, -1.229 | [-1.240; -0.427] |
| pressure | 5 | 15 | 970.0/813.3 | 9/10 | 1/2 | +0.263, -0.500, -0.350 | [-0.500; +0.263] |
| pressure | 6 | 18 | 1155.6/547.2 | 12/13 | 2/1 | +0.417, -0.448, -2.250 | [-2.250; +0.417] |
| copies_v2 | 5 | 15 | 533.3/253.3 | 13/12 | 2/0 | -1.000, +0.600, -0.650 | [-1.000; +0.600] |
| copies_v2 | 6 | 18 | 777.8/597.2 | 13/12 | 1/0 | -1.052, +0.625, -0.250 | [-1.052; +0.625] |

## Latencia y seguridad

| Etapa | Política | Decisiones de comparación | p95 | Máximo |
|---|---|---:|---:|
| pilot | v2 | 537 | 15.5 ms | 44.4 ms |
| pilot | v3 | 521 | 15.3 ms | 25.1 ms |
| validation | v2 | 4558 | 23.6 ms | 75.8 ms |
| validation | v3 | 4425 | 23.7 ms | 92.8 ms |
| production | v2 | 54 | 116.9 ms | 155.9 ms |
| production | v3 | 47 | 125.9 ms | 150.6 ms |

pilot: 0 respaldos, 0 acciones inválidas, 0 propuestas ilegales recuperadas, 0 decisiones del héroe sobre dos segundos y 0 muestras parciales de comparación. Se conservaron las fichas en todos los lotes. Máximo del héroe en sesiones: 41.1 ms.

validation: 0 respaldos, 0 acciones inválidas, 0 propuestas ilegales recuperadas, 0 decisiones del héroe sobre dos segundos y 0 muestras parciales de comparación. Se conservaron las fichas en todos los lotes. Máximo del héroe en sesiones: 42.1 ms.

production: 0 respaldos, 0 acciones inválidas, 0 propuestas ilegales recuperadas, 0 decisiones del héroe sobre dos segundos y 0 muestras parciales de comparación. Se conservaron las fichas en todos los lotes. Esta fase no incluye sesiones.

Las latencias de cada sesión están en sus JSON. Las cifras incluyen la conversión pública del control y excluyen parseo, arranque y red; el presupuesto sigue siendo cooperativo.

La auditoría comparó las semillas y los asientos de cada par; las barajas coinciden. Las trazas registran el número real de muestras. Los controles de 12/20 bb y los contextos sin cambio ayudan a detectar contaminación de v2; las diferencias, si aparecen después de stacks efectivos cortos o decisiones previas distintas, deben analizarse con la traza.

## Casos y contextos

Los [casos previos al ajuste](../results/shortstack_2026-10-28/diagnosis_before.json) y su [comparación con la candidata](../results/shortstack_2026-10-28/diagnosis_candidate.json) conservan las observaciones públicas y decisiones. Se publican también pérdidas de la candidata:

- selective, 5 jugadores, 8 bb, bloque 8, rotación 3, mano 1: KhJd HJ; v2 subir a 2.5 bb, v3 retirarse; delta realizado -17.0 bb. No es una prueba de EV de esa acción.
- selective, 6 jugadores, 8 bb, bloque 2, rotación 4, mano 1: AhJs UTG; v2 subir a 2.5 bb, v3 subir a 8 bb; delta realizado -16.0 bb. No es una prueba de EV de esa acción.
- copies_v2, 6 jugadores, 8 bb, bloque 1, rotación 1, mano 0: 3d3h BTN; v2 subir a 2.5 bb, v3 subir a 8 bb; delta realizado -9.5 bb. No es una prueba de EV de esa acción.

[analysis.json](../results/shortstack_2026-10-28/validation/analysis.json) contiene seis casos pareados completos, su reproducción, auditoría de barajas y resúmenes por posición, precio, stack efectivo, rivales y situación. Los contextos de resultados pareados se definen con la primera observación de v2 y agrupan observaciones dentro de cada bloque. Son análisis descriptivos, escasos y sujetos a selección; no se deben interpretar como un EV causal ni como nuevos criterios de aceptación. Las acciones y resultados de cada variante se conservan además en los reportes de celda. Los walks tienen categoría sin decisión.

Se reprodujo la mayor pérdida de cada uno de los 124 reportes de comparación, además de ambas variantes de los casos seleccionados. Las acciones, boards y fichas coinciden con los registros. Estas reproducciones no se suman al tamaño de muestra.

## Qué indican los contextos

En la validación principal se agrupan los pares según la primera observación de v2. Se muestra la media de los promedios de cada bloque que tuvo ese contexto; no tiene la misma ponderación que el contraste principal y omite walks. El mismo bloque puede aparecer en varias filas. Estos intervalos exploratorios no corrigen selección ni comparaciones múltiples.

| Dimensión | Contexto | Manos pareadas | Bloques con contexto | Delta descriptivo bb/mano | IC 95 % por bloques |
|---|---|---:|---:|---:|---|
| Efectivo hasta bb | 5 | 771 | 72 | -0.072 | [-0.128; -0.016] |
| Efectivo hasta bb | 8 | 759 | 72 | -0.076 | [-0.186; +0.028] |
| Rivales activos | 1 | 248 | 131 | +0.004 | [-0.046; +0.057] |
| Rivales activos | 2 | 355 | 141 | -0.129 | [-0.218; -0.049] |
| Rivales activos | 3 | 371 | 143 | -0.040 | [-0.128; +0.043] |
| Rivales activos | 4 | 376 | 144 | -0.041 | [-0.149; +0.063] |
| Rivales activos | 5 | 180 | 72 | -0.047 | [-0.242; +0.099] |
| Posición | BB | 234 | 137 | +0.000 | [+0.000; +0.000] |
| Posición | BTN | 288 | 144 | -0.165 | [-0.311; -0.017] |
| Posición | CO | 288 | 144 | -0.080 | [-0.236; +0.066] |
| Posición | HJ | 288 | 144 | -0.072 | [-0.264; +0.109] |
| Posición | SB | 288 | 144 | -0.016 | [-0.089; +0.047] |
| Posición | UTG | 144 | 72 | -0.083 | [-0.358; +0.122] |
| Precio hasta | 0.25 | 162 | 102 | -0.025 | [-0.130; +0.059] |
| Precio hasta | 0.4 | 1341 | 144 | -0.090 | [-0.167; -0.018] |
| Precio hasta | >.4 | 27 | 10 | +0.000 | [+0.000; +0.000] |
| Situación | first_in | 801 | 144 | -0.124 | [-0.249; +0.000] |
| Situación | raised | 729 | 141 | +0.000 | [+0.000; +0.000] |

En este lote, la diferencia se concentró en aperturas limpias. Los contextos enfrentando subidas y la posición BB dieron delta cero; el cambio no arregló la defensa identificada en el diagnóstico. La posición BTN y los contextos con dos rivales activos merecen revisión: hacer push/fold con rangos manuales también puede perder aperturas pequeñas rentables. Esto no demuestra que todos los pushes ni todas esas retiradas sean malos.

Las 30 celdas de 12/20 bb dieron diferencias exactamente cero. Esa igualdad y las pruebas de mutación del código compartido respaldan que el control no cambió. En sesiones, el daño más claro apareció frente a selectivos con seis jugadores: fichas medias de 1225 a 452,8 y eliminaciones de 10/18 a 14/18. Con solo tres grupos por esa celda, las cifras deben tratarse con cautela.

El siguiente experimento debería separar el cambio de tamaños del cambio de rangos y modelar las respuestas al all-in antes de ampliar agresión. La defensa barata requiere estudiar realización de equity y apuestas futuras. No se implementaron ajustes posteriores al inspeccionar esta validación; sus semillas ya son desarrollo.

## Criterios y límites

- Mejora principal con límite inferior positivo: no cumplido.
- Media no negativa en ambos formatos principales: no cumplido.
- Ninguna celda principal con todo el intervalo por debajo de −0,25 bb/mano: cumplido.
- Fichas finales de sesiones con límite inferior no negativo: no cumplido.
- Acciones, respaldos, fichas y latencia: cumplido.

La selección preflop corta necesita más trabajo. El cambio medido trata aperturas limpias; la defensa y los calls de all-in siguen usando rangos de v2. El muestreo modela showdown, no respuestas a un push, fold equity, riesgo de clasificación ni ICM. Los adversarios son sintéticos y su fuerza no está certificada. Cambiar a una política más agresiva puede mejorar fichas con reposición y empeorar supervivencia; ambos objetivos se publican por separado.

Una mesa local ganada no equivale a clasificarse al torneo. La API oficial y el torneo completo no están integrados. Una vez examinados estos resultados, todas estas semillas pasan a ser desarrollo para la siguiente iteración.

Para reproducir las fases, casos, suite y celdas individuales, véase el [método](PREFLOP_V3_METODO.md). La decisión legible por máquina está en [decision.json](../results/shortstack_2026-10-28/decision.json).

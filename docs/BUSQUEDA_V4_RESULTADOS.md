# Resultados de búsqueda preflop v4

Fecha local: 28 de octubre de 2026.

**Política predeterminada: v2.** La candidata no reúne evidencia suficiente para sustituir v2.

Se implementó comparación de acciones con respuestas hipotéticas, muestreo adaptativo y un proceso supervisado. El [método](BUSQUEDA_V4_METODO.md) distingue sus límites y el [protocolo anterior al piloto](../results/action_search_2026-10-28/protocol.json) fija cantidades y aceptación. No se ajustaron parámetros después del piloto.

Pasaron las **64 pruebas automatizadas**, incluidas las originales y las nuevas de valores por acción, cuota de rivales, repetición de tres brazos y procesos bloqueados. El [registro final](../results/action_search_2026-10-28/tests_final.txt) conserva la ejecución. La contabilidad terminal coincidió con PokerKit en [40 escenarios independientes](../results/action_search_2026-10-28/terminal_oracle.json), con diferencia máxima cero; eso valida los pozos y devoluciones bajo respuestas fijadas, no las probabilidades de respuesta.

Se ejecutaron **9 097 manos adicionales**, excluyendo tests, perfiles y replays. Son ejecuciones de tres variantes con barajas compartidas; no observaciones independientes. El control original conserva 4 000 muestras/1 600 ms. v2mc y v4 comparten el techo de 3 500 ms y la cuota de 16 384 en validación, con asignación del trabajo distinta.

## Contrastes principales

Cinco/seis jugadores, 4/8/12 bb, igual peso a cada una de las dieciocho celdas. Bootstrap estratificado de bloques completos; las rotaciones no se remuestrean por separado.

| Etapa | Manos con reposición | Manos de sesiones | v4−v2mc, bb/mano | IC 95 % | v4−v2 original | IC 95 % |
|---|---:|---:|---:|---|---:|---|
| pilot | 1035 | 521 | -0.001 | [-0.563; +0.524] | +0.023 | [-0.518; +0.558] |
| validation | 3699 | 3842 | +0.430 | [+0.042; +0.817] | +0.465 | [+0.083; +0.824] |

| Formato | v4−v2mc | IC 95 % | v4−v2 original | IC 95 % |
|---|---:|---|---:|---|
| 5 jugadores | +0.423 | [-0.135; +0.959] | +0.492 | [-0.044; +1.012] |
| 6 jugadores | +0.438 | [-0.100; +0.973] | +0.438 | [-0.101; +0.977] |

El efecto de aumentar solamente las muestras, v2mc−v2 original, fue +0.035 bb/mano, intervalo [+0.000; +0.104]. Hubo diferencia en 1 de los 144 bloques primarios; el intervalo toca cero. La política resta un error estándar a la equity; aumentar muestras reduce también ese descuento de incertidumbre. Este contraste separa esa asignación de cómputo de la búsqueda de acciones, sin garantizar fuerza fuera de estas mesas.

## Todas las celdas principales

Fichas reiniciadas cada mano. Los busts aquí no impiden jugar la siguiente. La cuota de rivales se mantiene fija en todos los brazos.

| Escenario | Jugadores | bb | v2 original | v2mc | v4 | Delta v4−v2mc | IC 95 % | Busts v2/v2mc/v4 |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| copies_v2 | 5 | 4 | +0.000 | +0.000 | -0.350 | -0.350 | [-0.988; +0.287] | 3/3/13 |
| copies_v2 | 5 | 8 | +0.000 | +0.000 | +0.688 | +0.688 | [-0.487; +1.713] | 4/4/7 |
| copies_v2 | 5 | 12 | +0.000 | +0.000 | +0.975 | +0.975 | [+0.350; +1.575] | 1/1/2 |
| copies_v2 | 6 | 4 | -0.073 | -0.073 | -0.292 | -0.219 | [-1.469; +0.958] | 2/2/15 |
| copies_v2 | 6 | 8 | +0.000 | +0.000 | -0.052 | -0.052 | [-1.729; +1.542] | 0/0/4 |
| copies_v2 | 6 | 12 | -0.229 | -0.229 | +1.005 | +1.234 | [+0.573; +1.875] | 2/2/2 |
| pressure | 5 | 4 | -0.525 | -0.525 | +1.062 | +1.587 | [+0.538; +2.487] | 2/2/8 |
| pressure | 5 | 8 | -0.094 | -0.094 | -0.867 | -0.773 | [-3.204; +1.525] | 0/0/15 |
| pressure | 5 | 12 | -0.020 | +0.605 | +1.600 | +0.996 | [-2.125; +4.008] | 0/0/3 |
| pressure | 6 | 4 | -0.083 | -0.083 | +1.281 | +1.365 | [+0.135; +2.719] | 4/4/7 |
| pressure | 6 | 8 | -0.208 | -0.208 | -1.000 | -0.792 | [-2.844; +1.531] | 4/4/15 |
| pressure | 6 | 12 | -0.229 | -0.229 | -0.031 | +0.198 | [-2.094; +2.167] | 1/1/5 |
| selective | 5 | 4 | +0.025 | +0.025 | +0.087 | +0.062 | [-0.888; +0.875] | 2/2/11 |
| selective | 5 | 8 | -0.050 | -0.050 | -0.237 | -0.187 | [-2.163; +1.300] | 2/2/10 |
| selective | 5 | 12 | +0.000 | +0.000 | +0.809 | +0.809 | [-0.673; +2.175] | 0/0/0 |
| selective | 6 | 4 | -0.031 | -0.031 | +0.958 | +0.990 | [+0.104; +1.917] | 4/4/15 |
| selective | 6 | 8 | +0.458 | +0.458 | +0.562 | +0.104 | [-2.479; +2.365] | 0/0/9 |
| selective | 6 | 12 | -0.458 | -0.458 | +0.656 | +1.115 | [-0.073; +2.208] | 2/2/5 |

Las 57 celdas, incluidos 2/3/4 jugadores y sentinelas de 20/100 bb, están en [validation_cells.csv](../results/action_search_2026-10-28/validation_cells.csv). Los JSON de celda y el resumen contienen fichas y diferencias por bloque para ambos controles.

## Sesiones con eliminación

Inicio 8 bb, máximo veinte manos, ciegas duplicadas cada diez. Dos grupos independientes por composición/formato, todos los asientos; muestra pequeña. Si cambian eliminaciones pueden divergir repartos posteriores. Se promedian rotaciones antes de estimar incertidumbre.

| Contraste de fichas finales | Grupos | Delta, stacks iniciales | IC 95 % por grupos |
|---|---:|---:|---|
| v4−v2 | 12 | +0.372 | [-0.218; +1.043] |
| v4−v2mc | 12 | +0.336 | [-0.273; +1.053] |

| Escenario | Jugadores | Variante | Mesas | Fichas medias finales | Eliminados | Mesas ganadas |
|---|---:|---|---:|---:|---:|---:|
| selective | 5 | v2 | 10 | 470.0 | 6 | 0 |
| selective | 5 | v2mc | 10 | 470.0 | 6 | 0 |
| selective | 5 | v4 | 10 | 1020.0 | 6 | 1 |
| selective | 6 | v2 | 12 | 958.3 | 8 | 0 |
| selective | 6 | v2mc | 12 | 958.3 | 8 | 0 |
| selective | 6 | v4 | 12 | 1191.7 | 8 | 1 |
| pressure | 5 | v2 | 10 | 655.0 | 6 | 0 |
| pressure | 5 | v2mc | 10 | 765.0 | 6 | 0 |
| pressure | 5 | v4 | 10 | 1580.0 | 6 | 3 |
| pressure | 6 | v2 | 12 | 341.7 | 10 | 0 |
| pressure | 6 | v2mc | 12 | 341.7 | 10 | 0 |
| pressure | 6 | v4 | 12 | 608.3 | 10 | 1 |
| copies_v2 | 5 | v2 | 10 | 740.0 | 7 | 1 |
| copies_v2 | 5 | v2mc | 10 | 800.0 | 7 | 1 |
| copies_v2 | 5 | v4 | 10 | 1040.0 | 7 | 1 |
| copies_v2 | 6 | v2 | 12 | 1033.3 | 6 | 0 |
| copies_v2 | 6 | v2mc | 12 | 1033.3 | 6 | 0 |
| copies_v2 | 6 | v4 | 12 | 541.7 | 9 | 1 |

Mesas truncadas cuentan por sus fichas finales, no como victorias. Estos conteos no miden clasificación al torneo.

## Cómputo, adaptación y seguridad

| Fase | Variante | Decisiones de comparación | p50 | p95 | Máximo |
|---|---|---:|---:|---:|---:|
| pilot | v2 | 389 | 62.8 ms | 109.4 ms | 143.3 ms |
| pilot | v2mc | 389 | 19.4 ms | 34.5 ms | 38.9 ms |
| pilot | v4 | 431 | 93.1 ms | 219.9 ms | 296.5 ms |
| validation | v2 | 1357 | 54.5 ms | 92.2 ms | 163.8 ms |
| validation | v2mc | 1359 | 205.7 ms | 349.9 ms | 465.9 ms |
| validation | v4 | 1759 | 196.1 ms | 2178.0 ms | 3487.4 ms |

pilot: 275 búsquedas, 195 cambios frente a la acción base, mundos p50/p95/máximo 1024/1024/1024; 0 estimaciones base parciales. Paradas: {"sample_cap": 187, "robust_gain": 64, "no_robust_gain": 24}.


validation: 962 búsquedas, 726 cambios frente a la acción base, mundos p50/p95/máximo 3328.0/16384/16384; 0 estimaciones base parciales. Paradas: {"robust_gain": 571, "no_robust_gain": 202, "sample_cap": 186, "deadline_keep_v2": 3}.

Comprobaciones de validación: {"fallbacks": 0, "invalid_actions": 0, "recovered_illegal_proposals": 0, "chip_failures": 0, "over_4250_ms": 0}. La retención de v2 por plazo de búsqueda se publica separada de los respaldos por error. No se usó el supervisor para generar resultados estratégicos; se midió aparte el camino de producción.

El perfil supervisado ejecutó 72 decisiones normales en ocho estados públicos de desarrollo, con 0 respaldos y 0 decisiones sobre 4 250 ms. El proceso bloqueado intencionalmente respondió con respaldo legal en 4254.6 ms; prueba aprobada. Véase [profile.json](../results/action_search_2026-10-28/profile.json). Estos estados no definen un percentil representativo de producción.

Los tiempos incluyen preparación, muestreo y selección; el perfil v4 añade IPC y vigilancia. Excluyen arranque, parseo y red. El presupuesto cooperativo no equivale al supervisor, ni el supervisor local a una garantía del plazo oficial extremo a extremo.

## Casos y diagnóstico

Ejemplos de cambios sin corte de reloj, elegidos entre pérdidas y ganancias realizadas. No son pruebas individuales de EV:

- copies_v2, 5 jugadores, 12 bb, bloque 4, rotación 3: Td9s HJ; base retirarse, v4 subir a 2 bb. El modelo estimaba al menos +0.55 bb frente a su base; delta realizado de la mano frente a v2 original -12.0 bb. Reproducción de las tres variantes: coincide.
- pressure, 5 jugadores, 12 bb, bloque 4, rotación 1: Ad6d BTN; base retirarse, v4 subir a 6 bb. El modelo estimaba al menos +1.33 bb frente a su base; delta realizado de la mano frente a v2 original -12.0 bb. Reproducción de las tres variantes: coincide.
- pressure, 5 jugadores, 12 bb, bloque 5, rotación 1: 4s4d BTN; base retirarse, v4 subir a 6 bb. El modelo estimaba al menos +0.95 bb frente a su base; delta realizado de la mano frente a v2 original -12.0 bb. Reproducción de las tres variantes: coincide.
- selective, 6 jugadores, 8 bb, bloque 2, rotación 5: 2c4d BB; base retirarse, v4 subir a 6 bb. El modelo estimaba al menos +0.44 bb frente a su base; delta realizado de la mano frente a v2 original +17.0 bb. Reproducción de las tres variantes: coincide.
- pressure, 5 jugadores, 8 bb, bloque 6, rotación 3: 5cAc HJ; base retirarse, v4 subir a 2 bb. El modelo estimaba al menos +0.80 bb frente a su base; delta realizado de la mano frente a v2 original +17.5 bb. Reproducción de las tres variantes: coincide.
- selective, 6 jugadores, 12 bb, bloque 4, rotación 3: As2c HJ; base retirarse, v4 subir a 6 bb. El modelo estimaba al menos +0.32 bb frente a su base; delta realizado de la mano frente a v2 original +25.0 bb. Reproducción de las tres variantes: coincide.

[analysis.json](../results/action_search_2026-10-28/validation/analysis.json) conserva los tres registros completos de cada ejemplo, comparaciones reproducidas, auditoría de barajas, transiciones de acción y contextos por posición, rivales, precio y efectivo. Los contextos de resultados se definen con la primera observación de v2 original; son exploratorios y no equivalen al valor causal de una acción. Las simulaciones que tocaron reloj pueden tener distinto número de mundos al repetirlas; no se oculta esa limitación.

## Criterios y límites

En 611 secuencias con subida de v4 que dejaba fichas efectivas detrás, hubo 48 resubidas rivales antes de la siguiente decisión propia o el cambio de calle. El modelo fold/call omite esa respuesta; se publica como diagnóstico de sesgo, sin recalibrar la candidata después de validar.

- Mejora principal frente al control de mayor muestreo: cumplido.
- Mejora principal frente a v2 original: cumplido.
- Media no negativa en cinco y seis jugadores frente a ambos controles: cumplido.
- Sesiones: límite inferior no negativo frente a ambos controles: no cumplido.
- Acciones, respaldos por error, fichas y plazo local: cumplido.

La búsqueda valora respuestas fold/call y checkdown; aún faltan resubidas y apuestas posteriores. Más muestras reducen el ruido del modelo supuesto, pero no corrigen ese sesgo. Las ganancias calculadas en el propio modelo no bastan para promover una estrategia. Los intervalos por escenario son descriptivos y no corrigen comparaciones múltiples.

La API y el formato completo del torneo siguen pendientes. Todas las semillas de esta validación pasan a ser desarrollo tras examinar los resultados. El código y los criterios se fijaron antes del piloto; no se retocó la candidata al ver esta evidencia.

Para comandos, configuraciones, supervisor y recuperación del código anterior véase [BUSQUEDA_V4_METODO.md](BUSQUEDA_V4_METODO.md). La decisión legible por máquina está en [decision.json](../results/action_search_2026-10-28/decision.json).

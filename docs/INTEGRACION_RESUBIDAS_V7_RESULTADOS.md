# Comparación de seis versiones y candidata v7

29 de octubre de 2026, hora de Lima. **v2 sigue predeterminada. No hay promoción de v7.**
Esta campaña es exploratoria: intervalos sin corrección por las múltiples comparaciones, pocos grupos de sesiones y condiciones locales.

La mayor precisión del estimador no acreditó una mejora práctica: en las sesiones, v7 terminó con 261,92 fichas menos de media que v2 y 16,94 puntos más de eliminación a 24 manos. v4rb tuvo la mayor media de fichas finales de esta batería. Estas observaciones conservan sus intervalos y límites abajo.

## Qué se completó

Se completaron **55.806 ejecuciones nuevas de mano**: 1.188 en piloto, 4.752 con fichas reiniciadas en la comparación y 49.866 en sesiones con eliminación.
La comparación tiene 144 bloques independientes de barajas y 24 grupos independientes de sesiones. Las rotaciones de un grupo no son observaciones independientes.

El [método](INTEGRACION_RESUBIDAS_V7_METODO.md) explica el algoritmo, los perfiles de cálculo y los límites. El [protocolo](../results/integrated_shove_2026-10-29/experiment/protocol.json) fijó ambas fases antes del piloto. Se ejecutó todo desde el código congelado, sin ajustar políticas por los resultados.

## Versiones comparadas

Medias con igual peso por escenario/formato y, en reset, por profundidad. Las sesiones empiezan con 800 fichas, ciegas 50/100 y llegan hasta 128 manos.

| Versión | Reset, bb/mano | Fichas finales | Eliminación a 24 | Eliminación a 128 | p95 local por decisión |
|---|---:|---:|---:|---:|---:|
| v2 | -0,062 | 1058,62 | 46,39 % | 73,61 % | 111,0 ms |
| v2mc | -0,046 | 1080,16 | 46,53 % | 73,19 % | 34,4 ms |
| v4rb | +0,421 | 1291,35 | 56,25 % | 69,31 % | 149,7 ms |
| v5 | +0,290 | 912,85 | 62,92 % | 77,92 % | 349,0 ms |
| v6 | +0,451 | 917,01 | 69,44 % | 78,47 % | 105,3 ms |
| v7 | +0,400 | 796,70 | 63,33 % | 80,69 % | 829,7 ms |

v2 usa 4.000 muestras; los otros brazos tienen cuota de 1.024, de las que v5/v7 reservan la mitad para entrenar. En los brazos con búsqueda se calculan además hasta 1.024 mundos para la equity de la decisión local. Las cuotas iguales no representan igual CPU. v2mc conserva las reglas congeladas con esa cuota menor. Las medias de esta tabla no bastan para declarar una versión ganadora.

## Contrastes de v7, incluidos los desfavorables

Diferencia candidata−control, con intervalo bootstrap exploratorio del 95 %. En eliminación, un valor negativo favorece a v7; en fichas y bb/mano, uno positivo.

| Control | Reset: Δ bb/mano | Sesiones: Δ fichas finales | Δ eliminación a 24, pp | Δ eliminación a 128, pp |
|---|---:|---:|---:|---:|
| v2 | +0,462 [+0,126; +0,806] | -261,92 [-622,04; +119,91] | +16,94 [+5,00; +29,03] | +7,08 [-2,08; +15,83] |
| v4rb | -0,020 [-0,296; +0,247] | -494,65 [-809,43; -191,49] | +7,08 [+0,28; +13,89] | +11,39 [+4,17; +18,61] |
| v5 | +0,110 [-0,038; +0,263] | -116,15 [-392,88; +154,51] | +0,42 [-5,00; +5,69] | +2,78 [-3,75; +9,03] |

La comparación v7−v5 estudia el efecto conjunto de integrar respuestas y aprender continuaciones con pesos de alcance. Los intervalos son descriptivos, no pruebas confirmatorias. El [resumen completo](../results/integrated_shove_2026-10-29/experiment/comparison/summary.json) conserva los 15 pares.

### Escenario externo diverso

Fullhouse, Honest educativo, v2 y pressure; solo ocho grupos independientes de sesiones entre ambos formatos.

| Control | Reset: Δ bb/mano | Δ fichas finales | Δ eliminación a 128, pp |
|---|---:|---:|---:|
| v2 | +0,322 [-0,134; +0,780] | -580,65 [-1071,10; -9,31] | +15,00 [+0,00; +24,58] |
| v4rb | -0,300 [-0,787; +0,153] | -646,96 [-1040,88; -300,00] | +15,42 [+6,25; +26,25] |
| v5 | +0,088 [-0,148; +0,363] | -130,21 [-390,62; +169,79] | +5,00 [-2,08; +12,08] |

## Precisión del estimador y costo

Con la misma continuación pública fija de pagar, la integración redujo un **29,7 %** la varianza entre réplicas a igual número de mundos. El cálculo del estimador consumió **1,97×** el tiempo del muestreado, excluyendo cartas y compilación. El producto varianza×tiempo fue **1,38×**, desfavorable en esta prueba. No se ha demostrado una ventaja a igual tiempo de CPU.

Son siete fixtures de desarrollo, tres priors, 24 réplicas y 128 mundos por réplica. La continuación fija aísla integración; no mide la calidad del aprendizaje ni la fuerza. Los datos están en [variance.json](../results/integrated_shove_2026-10-29/variance.json).

## Dónde falla el modelo de respuestas

El diagnóstico seleccionó 235 estados públicos distintos de respuestas inmediatas a subidas preflop no terminales, sin consultar ganancias ni cartas rivales. Hay un máximo de 12 por celda/familia. Los estados están correlacionados y la selección no representa todo el torneo.

| Rival | Estados | Call observado | Call predicho, equilibrado | Subida terminal observada | Subida terminal predicha |
|---|---:|---:|---:|---:|---:|
| fullhouse | 67 | 7,5 % | 8,1 % | 14,9 % | 1,8 % |
| honest | 10 | 90,0 % | 14,5 % | 0,0 % | 3,8 % |
| lag | 4 | 25,0 % | 36,9 % | 25,0 % | 11,0 % |
| pressure | 76 | 15,8 % | 12,9 % | 1,3 % | 3,4 % |
| tag | 1 | 100,0 % | 34,8 % | 0,0 % | 11,1 % |
| v2_4000 | 77 | 13,0 % | 11,2 % | 1,3 % | 2,8 % |

El modelo también asigna probabilidad cero a las resubidas no terminales: se observaron 2 en esta selección. Este diagnóstico mira solo la respuesta inmediata, no toda la cadena de respuestas.

Los priors se mantuvieron fijos. No se eligió el de menor Brier ni se reajustaron umbrales con estas observaciones. La discrepancia entre familias muestra por qué una expectativa más precisa bajo un modelo no garantiza mejores apuestas. Las probabilidades, scores Brier y observaciones están en [calibration.json](../results/integrated_shove_2026-10-29/calibration.json).

## Optimización y reparaciones técnicas

Se ensayó compartir hojas terminales idénticas y preasignar estadísticas de continuación. La primera medición, bajo carga de la campaña, dio un factor global de 0,96× y no confirmó una mejora de tiempo. Se conserva ese resultado adverso.
La repetición sin los workers de partidas dio **1,10×**, equivalente a 9,4 % menos tiempo. La decisión registrada sobre la optimización es: **conservada**.
Se verificaron 21 parejas de búsquedas fijas y 20 pares de manos completas; coinciden exactamente acción, equity, EV, errores de Monte Carlo, mundos y continuaciones. Solo se excluyen tiempos y número de nodos compilados, que cambia al compartir hojas. Es equivalencia técnica, no evidencia nueva de fuerza.

La CLI permite ahora `--baseline-samples` y `--baseline-budget-ms`, además de los perfiles de rivales. Se corrigió la herencia del presupuesto de 3.500 ms por controles/rivales v2 y el contador fijo de muestras del informe. Estos cambios no entraron en el snapshot de la campaña.

## Auditoría y límites

La suite final pasa **191 pruebas**. La auditoría reconstruyó todas las manos y 792 mesas de sesiones, comprobó 31082 decisiones públicas y coincidieron **496 manos de replay** seleccionadas antes de ver resultados. Los replays se excluyen de las ejecuciones nuevas.
El estado técnico de la matriz, incluyendo cortes del reloj, fue **aprobado**. Las [auditorías](../results/integrated_shove_2026-10-29/experiment/comparison/audit.json), [tests](../results/integrated_shove_2026-10-29/tests_release.txt) y [fuentes congeladas](../results/integrated_shove_2026-10-29/experiment/source) permiten revisar el cálculo. La [integridad final](../results/integrated_shove_2026-10-29/integrity.json) identifica fuentes y artefactos.

Las reglas y premios oficiales siguen sin estar definidos en el proyecto. Los resultados son sobre supuestos locales, no probabilidades de clasificación. Las mesas censuradas conservan sus fichas observadas y no reciben puestos o victorias inventados. La continuación aprendida valora escenarios hipotéticos; el bot recalcula cada turno real y puede responder de otra forma. Se mantienen todos los resultados y v2 como predeterminada.

# Comparación ampliada de la clasificatoria

**10 de noviembre de 2026.** Se mantiene `v2` para la entrega. La ampliación completó **468 torneos y 276 203 ejecuciones de mano**. Se compararon 13 perfiles en 36 sorteos nuevos por perfil, frente a los 12 del piloto. La métrica principal fue la cantidad de clasificaciones al top 6.

## Resultados por versión

Cada campo aporta 12 sorteos. Las columnas «Solo versión» y «Solo v2» cuentan los sorteos en los que clasificó únicamente una de las dos versiones. Las fichas finales son medias de los 36 torneos, incluyendo cero cuando el bot quedó eliminado.

| Versión | Top 6 / 36 | Diverso | Selectivo | Presión | Solo versión | Solo v2 | Eliminaciones | Fichas finales |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | 28 | 11 | 9 | 8 | 1 | 0 | 24 | 18 016 |
| **v2** | **27** | **10** | **9** | **8** | — | — | **23** | **17 893** |
| v2mc | 27 | 11 | 8 | 8 | 2 | 2 | 25 | 18 728 |
| v3 | 27 | 10 | 9 | 8 | 0 | 0 | 23 | 17 893 |
| v8 | 26 | 10 | 8 | 8 | 0 | 1 | 25 | 17 114 |
| v8b | 26 | 10 | 8 | 8 | 0 | 1 | 25 | 17 114 |
| v8c | 26 | 10 | 8 | 8 | 0 | 1 | 26 | 17 141 |
| v8d | 26 | 10 | 8 | 8 | 0 | 1 | 24 | 16 702 |
| v4 | 25 | 11 | 7 | 7 | 2 | 4 | 26 | 17 745 |
| v4rb | 25 | 11 | 7 | 7 | 2 | 4 | 26 | 16 265 |
| v5 | 24 | 10 | 7 | 7 | 2 | 5 | 23 | 19 904 |
| v6 | 24 | 10 | 7 | 7 | 2 | 5 | 23 | 22 184 |
| v7 | 24 | 10 | 7 | 7 | 2 | 5 | 24 | 18 222 |

- **v1** ganó un solo sorteo pareado. En la semilla 20261225, ambas versiones terminaron con cero fichas. `v1` quedó sexta al caer en la ronda 5 y `v2` séptima al caer en la ronda 4. `v2` terminó con fichas en 13 clasificaciones y `v1` en 12. La diferencia observada depende de cómo se completan los seis puestos con los últimos eliminados.
- **v4rb** pasó 11 de 12 veces en el campo diverso, una más que `v2`. En los campos selectivo y de presión quedó dos clasificaciones por debajo en cada uno.
- **v6** tuvo la mayor media de fichas y ganó ocho torneos frente a seis de `v2`. Su top 6 fue menor, con 24 clasificaciones frente a 27.

Ningún perfil mostró una mejora consistente del top 6. En las 12 pruebas pareadas exactas de una cola contra `v2`, el menor valor p antes del ajuste fue 0,50 y todos fueron 1,00 tras el ajuste de Holm. El análisis usa un resultado por sorteo y versión. Las manos del mismo torneo comparten jugadores, fichas e historial.

## Fichas y eliminaciones por ronda

Cada celda indica fichas medias al cierre y eliminaciones nuevas entre paréntesis. El resumen JSON incluye las diez rondas de los 13 perfiles.

| Ronda | v1 | v2 | v4rb | v6 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13 278 (5) | 13 272 (5) | 12 971 (7) | 12 971 (7) |
| 2 | 14 560 (2) | 14 536 (2) | 14 675 (2) | 14 675 (2) |
| 3 | 14 465 (4) | 14 445 (4) | 14 910 (4) | 14 868 (5) |
| 4 | 17 498 (1) | 16 707 (2) | 17 898 (1) | 17 664 (1) |
| 5 | 17 175 (3) | 17 170 (2) | 16 924 (1) | 16 890 (1) |
| 6 | 17 755 (4) | 17 768 (4) | 18 074 (3) | 20 994 (1) |
| 7 | 17 556 (3) | 17 651 (3) | 18 976 (3) | 22 877 (3) |
| 8 | 17 665 (2) | 17 592 (1) | 17 484 (3) | 21 055 (2) |
| 9 | 18 607 (0) | 18 500 (0) | 18 746 (0) | 22 333 (0) |
| 10 | 18 016 (0) | 17 893 (0) | 16 265 (2) | 22 184 (1) |

## Método

Cada torneo empezó con 11 bots a 100 ciegas grandes y ciegas fijas de 50/100. Se jugaron diez rondas, con hasta 50 manos o seis minutos por mesa y fichas acumuladas. Las mesas empezaron con cinco y seis jugadores. Cuando la cantidad de supervivientes ya no permitió esa distribución, se formaron mesas más pequeñas. Se conservaron las reglas del piloto para completar el top 6 por ronda y mano de eliminación y resolver empates con la semilla del sorteo.

Los perfiles recibieron las mismas semillas para ordenar jugadores, elegir barajas e inicializar sus rivales. Al producirse eliminaciones distintas, el mismo orden se aplicó a los supervivientes de cada torneo. Los campos diverso y selectivo conservaron los perfiles del piloto. El campo de presión añadió dos copias de `v2` con 512 muestras y combinó presión, juego agresivo, Fullhouse y Honest. Se simularon las políticas completas. Las variantes que aíslan componentes de `v8d` quedaron fuera de la matriz.

Las versiones `v1`, `v2`, `v3` y la familia `v8` usaron 4 000 muestras y 1 600 ms. El control `v2mc` y los perfiles `v4` a `v7` usaron una cuota de 1 024 y un presupuesto de 3 500 ms, siguiendo el perfil de `v4rb` del piloto y las comparaciones anteriores a esa cuota. En las políticas de búsqueda, la cuota también se aplica a los mundos de búsqueda. Los resultados corresponden a estos perfiles de cálculo.

Se verificaron las 36 semillas de cada perfil, el sorteo inicial compartido, la conservación de fichas, la ausencia de reingresos y los puestos finales. El simulador registró **179 675 decisiones** de los perfiles evaluados, sin respaldos ni recortes de muestras por tiempo. La decisión más lenta fue de **432 ms**. Este tiempo mide cálculo local y excluye latencia de red y transporte del kit. Ninguna mesa alcanzó el límite de seis minutos.

[Resumen por versión y ronda](../results/qualifier_expanded_2026-11-10/summary.json) · [Bitácora completa de torneos](../results/qualifier_expanded_2026-11-10/tournaments.jsonl) · [Plan y perfiles](../results/qualifier_expanded_2026-11-10/plan.json)

## Reproducción

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m scripts.qualifier_expanded --seeds 36 --workers 8 --seed 20261201 --output-dir results/qualifier_expanded_2026-11-10
```

El comando retoma los torneos faltantes en la misma carpeta. Con la bitácora completa, reconstruye el resumen sin volver a simular partidas.

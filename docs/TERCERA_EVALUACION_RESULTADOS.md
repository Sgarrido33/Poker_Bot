# Tercera evaluación: resultados y decisión

28 de octubre de 2026, hora de Lima. **v2 sigue predeterminada. La v6 actual no
se recomienda como sustituta. NoRegrets ya está integrado como rival aprendido
experimental, con una limitación de cobertura importante.**

## Comparación registrada

Se completó la matriz entera: **251.175 ejecuciones de mano, 3.960 mesas y
144 grupos independientes**. El contraste principal tiene 40 grupos por formato
(80 en total), cinco brazos y todas las rotaciones. Los otros cuatro escenarios
mantienen ocho grupos por formato cada uno. No se cambió la cantidad por las
ganancias observadas. Se conservaron stack 800, ciegas 50/100, sin ante ni
recompras; estas siguen siendo reglas locales.

Las semillas se comprobaron contra el historial y contra el piloto. El protocolo
se registró antes de jugar y los workers importaron su propia instantánea de
código, independiente de las modificaciones posteriores para NoRegrets.
El [protocolo](../results/competition_stage3_2026-10-28/protocol.json), el
[resumen completo](../results/competition_stage3_2026-10-28/summary.json) y la
[auditoría independiente](../results/competition_stage3_2026-10-28/independent_audit.json)
conservan las cantidades y huellas.

Los dos contrastes principales predefinidos son v6−v2 en `external_diverse`.
Se promedian primero las rotaciones de cada grupo, luego los dos formatos con
igual peso. Intervalos percentiles de 20.000 réplicas de grupos completos,
97,5 % por resultado, con Bonferroni para las dos métricas:

| Métrica principal | Diferencia v6−v2 | Intervalo ajustado |
|---|---:|---:|
| Fichas finales / stack inicial de 800 | +0,316 | [−0,008; +0,633] |
| Eliminación acumulada a 128 manos | −3,25 pp | [−9,33; +3,08] pp |

La diferencia media de fichas equivale a +252,91 fichas, pero ambos intervalos
incluyen cero. **v6 no pasa el filtro registrado**. La cobertura bootstrap es
aproximada; 80 grupos no garantizan potencia para mejoras pequeñas.

## Riesgo temprano y comparación con la política madre

Medias del escenario principal, dando igual peso a cinco y seis jugadores.
Cada brazo contiene 440 mesas; las mesas de un grupo no son independientes:

| Política | Fichas finales medias | Eliminación a 24 | Eliminación a 128 |
|---|---:|---:|---:|
| v2 | 903,97 | 46,83 % | 75,63 % |
| v4rb | 1.420,88 | 55,50 % | 65,13 % |
| v6 | 1.156,88 | 63,63 % | 72,38 % |

Respecto de v4rb, v6 perdió **264 fichas de media**, aumentó la eliminación
temprana en **8,13 puntos** y la eliminación a 128 en **7,25 puntos**. Estos
contrastes con v4rb son exploratorios; no forman parte de la familia principal
de dos pruebas. Las medias de fichas de v6 fueron menores que las de v4rb en
ambos formatos. No se declara ganadora a v4rb ni se la promueve por esta tabla.

La restricción de nuevas inversiones no terminales desplazó decisiones hacia
pushes: hasta 24 manos, sumando todos los escenarios, v6 hizo 3.109 pushes
efectivos y v4rb 1.511. Hubo 496/792 eliminaciones tempranas con v6 y 422/792
con v4rb. Son conteos descriptivos sobre trayectorias distintas, no pruebas del
EV de cada acción. El [diagnóstico nuevo](../results/competition_stage3_2026-10-28/early_diagnosis/diagnosis.json)
conserva posición, profundidad, precio, rivales y decisiones.

La hipótesis de eliminar esas alternativas **no produjo una mejora práctica
convincente**. El siguiente trabajo estratégico debería estudiar la valoración
de respuestas y resubidas conservando opciones pequeñas, antes de volver a
restringirlas o endurecer rangos con estos mismos datos.

## Verificación y contabilidad

- Cero fallbacks, cortes de equity/búsqueda, errores de fichas o acciones del
  héroe fuera del sobre legal en las 251.175 manos principales.
- Se reconstruyeron las 3.960 sesiones desde sus logs, incluyendo cambios de
  asientos, stacks, seeds, eliminaciones, victorias y censura.
- Coincidieron diez sesiones completas repetidas desde el código congelado:
  **551 manos de replay**, excluidas de la evidencia nueva. Solo se excluyeron
  tiempos y se normalizaron tuplas/listas; las demás decisiones coinciden.
- Se comprobaron 134.531 decisiones propias contra el historial público. La
  auditoría detecta una alteración artificial del resumen.
- El piloto previo tuvo 66 mesas y 3.539 manos, separado del contraste. Su
  comprobación final del conjunto dinámico de archivos detectó el módulo nuevo
  de NoRegrets; los archivos realmente registrados y sus instantáneas siguieron
  iguales. El [auditor posterior](../results/v6_session_pilot_2026-10-28/pilot_audit.json)
  reconstruyó la evidencia sin repetir ni escoger ganancias.
- El generador de resumen necesitó dos reparaciones de presentación: nombre
  de un contador y suma de razones normalizadas. No alteraron ejecución,
  cantidades, semillas, políticas ni las dos métricas principales. El diff
  queda junto al resultado.
- La suite final pasó **153 pruebas**. No se suman como resultados estratégicos.

## Segunda familia aprendida

NoRegrets ya acepta observaciones completas y tiene perfiles propios para
2–6 jugadores: un millón de iteraciones por perfil, stack nominal 800. Se
preservaron ejecutable y fuentes exactos antes del entrenamiento. El motor
adaptado pasó 16 pruebas Rust y 1.000 manos de paridad con stacks variados:
5.487 consultas, sin rechazo de estados ni acciones ilegales.

La prueba nueva con NoRegrets como rival fue separada de la matriz registrada:
33 mesas, 1.703 manos y solo dos grupos independientes. No permite confirmar
una política ganadora. El proceso funcionó sin fallos de infraestructura, pero
**269 de 660 decisiones de NoRegrets (40,76 %) recurrieron a su respaldo**:
210 por menú incompatible y 59 por estado no entrenado. En 610 consultas los
stacks diferían del perfil nominal. Su transferencia a sesiones desiguales
todavía es débil; no debe presentarse como rival fuerte validado.

El p95 de su API en esa prueba fue 402,85 ms y el máximo 888,38 ms, incluyendo
cambios de perfil. Son mediciones locales, no garantías. El
[informe de entrenamiento y cobertura](../research/noregrets_training_20261028/RESULTS_VALIDATED_V3.md)
y el [resumen de cross-play](../results/noregrets_crossplay_validated_2026-10-28/summary.json)
incluyen también los resultados desfavorables.

Las reglas y premios oficiales siguen desconocidos. No se infiere clasificación
al torneo, no se asignan victorias a líderes censurados y todos los lotes
observados pasan a desarrollo.

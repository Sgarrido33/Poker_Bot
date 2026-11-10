# Primera evaluación bot contra bot con un rival externo

Esta campaña se conserva sin sobrescribir. La etapa posterior tiene un
[protocolo separado](COMPETENCIA_SEGUNDA_METODO.md), nuevos identificadores y
semillas, piloto técnico de duración y otro escenario de diversidad externa.
Su [informe completo](COMPETENCIA_SEGUNDA_RESULTADOS.md) conserva por separado
los nuevos resultados, auditorías y limitaciones de fidelidad.

28 de octubre de 2026. **v2 sigue como política predeterminada. Ninguna candidata pasó el filtro registrado para ampliar la investigación.**

Se integró y ejecutó [Fullhouse, de Advit Arora](https://github.com/advitrocks9/fullhouse-bot/tree/e504793d480b1b975f25258d25939b45c6dbd5a4), con código y pesos fijados por commit y SHA-256. Aporta una familia externa aprendida; no es Pluribus ni un adversario de fuerza profesional demostrada aquí. Su runtime combina una red de ventajas con regret matching y un overlay manual preflop hasta 12 bb. No reprodujimos su entrenamiento. La [investigación de alternativas](RIVALES_EXTERNOS_INVESTIGACION.md) documenta licencias, disponibilidad, requisitos y las incompatibilidades de otros agentes.

## Contra quién jugamos y cuánto

Se compararon v2, v4, v4rb y v5 en cinco escenarios: reglas propias selectivas; reglas propias de presión; copias congeladas de v2; mezcla con dos Fullhouse, una v2 y un pressure (con seis jugadores añade LAG); y mesas donde todos los rivales son Fullhouse. TAG/LAG/pressure comparten componentes nuestros. Las copias v2 son una sola familia propia. Las instancias Fullhouse son una sola familia de otro autor, con pesos comunes y azar independiente. No se creó ningún rival sintético nuevo.

Las copias rivales v2 conservaron **512 muestras**; no representan un espejo a las 4.000 muestras del bot predeterminado. Las cuotas de todos los rivales se mantuvieron constantes entre brazos. Las candidatas usan 4.096 muestras y un presupuesto mayor que v2: la comparación no aísla perfectamente algoritmo y cómputo. El [método y los comandos](COMPETENCIA_METODO.md) y el [protocolo previo](../results/competition_2026-10-28/protocol.json) especifican cantidades y criterios.

- **3.520 ejecuciones con stacks reiniciados:** 20 celdas de cinco/seis jugadores, 8/100 bb y cinco escenarios; ocho bloques por celda y todas las rotaciones. Son 160 bloques independientes, no 3.520 observaciones independientes.
- **9.178 ejecuciones en sesiones:** 99 mesas por brazo, 396 en total, agrupadas en 18 semillas independientes. Inicio de 8 bb y máximo 24 manos; ciegas fijas 50/100, sin ante ni recompras. Son supuestos locales, no reglas del torneo.
- **Total: 12.698 ejecuciones de mano nuevas.** Replays, pruebas técnicas y mundos internos se excluyen de ese total.

Las 592 semillas previstas no se solapan con las 2.248 semillas únicas disponibles en las trazas JSONL históricas. Las cartas coinciden entre brazos; en sesiones, eliminaciones diferentes pueden cambiar quién recibe las cartas desde la misma semilla. Todos estos resultados ya son datos de desarrollo.

## Comparación principal

Diferencia frente a **v2 en la misma mesa mixta externa**, dando igual peso a formato y profundidad. Bootstrap de bloques completos; intervalos aproximados de 98,333 % para tres candidatas. Solo hay ocho bloques por celda y tres grupos por estrato de sesión: la incertidumbre es frágil y las réplicas del bootstrap no crean datos nuevos.

| Candidata | Δ bb/mano | Intervalo | Δ fichas finales / 800 en sesiones externas | Intervalo |
|---|---:|---|---:|---|
| v4 | +0,557 | [-0,112; +1,260] | +0,812 | [-0,131; +1,784] |
| v4rb | +0,580 | [-0,121; +1,270] | +0,900 | [-0,152; +1,928] |
| v5 | +0,499 | [-0,038; +1,059] | +0,882 | [-0,163; +1,674] |

Todos los intervalos principales incluyen cero. Las medias por formato son positivas, pero **ninguna candidata pasa el filtro**. Las diferencias son mejoras relativas frente a v2; no equivalen a una tasa de victoria contra un Fullhouse individual. Tampoco permiten ordenar con confianza v4, v4rb y v5.

El promedio cambia según el campo. Estas son diferencias descriptivas frente a v2, con igual peso por celda:

| Campo | v4 | v4rb | v5 |
|---|---:|---:|---:|
| Selectivos propios | +0,423 | +0,413 | +0,333 |
| Presión propia | -0,566 | -0,584 | -0,485 |
| Copias v2 | -0,026 | +0,074 | -0,005 |
| Mezcla externa | +0,557 | +0,580 | +0,499 |
| Solo Fullhouse | +0,251 | +0,220 | +0,205 |

En external_mix, las diferencias observadas proceden de 8 bb: a 100 bb los cuatro brazos obtuvieron exactamente el mismo resultado medio en ambos formatos. Eso aporta cobertura frente a la red externa en juego profundo, pero no evidencia de que las candidatas hayan mejorado nuestro juego profundo. En external_only de seis jugadores a 100 bb, las candidatas quedaron 0,074 bb/mano por debajo de v2. No se ocultan esas celdas. Las ganancias y diferencias de las 20 celdas están en [cells.csv](../results/competition_2026-10-28/cells.csv) y [audit.json](../results/competition_2026-10-28/audit.json); los contrastes e intervalos completos, en [summary.json](../results/competition_2026-10-28/summary.json).

## Fichas y eliminación no dicen lo mismo

Resumen descriptivo de 99 sesiones por brazo, con pila inicial de 800. Las medias de esta tabla ponderan mesas, mientras los contrastes anteriores ponderan estratos por igual.

| Versión | Fichas finales medias | Eliminaciones | Victorias observadas | Supervivientes censurados |
|---|---:|---:|---:|---:|
| v2 | 740,2 | 50 | 2 | 47 |
| v4 | 1.229,7 | 53 | 6 | 40 |
| v4rb | 1.281,7 | 54 | 8 | 37 |
| v5 | 1.208,0 | 57 | 7 | 35 |

Las candidatas acumularon más fichas de media y también terminaron eliminadas más veces. Las diferencias de eliminación siguen siendo inciertas. **346 de 396 mesas no terminaron** antes del límite: no se considera ganador al líder ni se inventa una clasificación final para supervivientes. Estas cifras no estiman la probabilidad de ganar PokerFight ni resuelven qué riesgo conviene bajo premios y reglas todavía desconocidos.

## Fidelidad y verificación

El rival externo tomó 4.924 decisiones por red y 5.950 por overlay. Hubo 67 traducciones explícitas de `all_in` a call/check cuando el contrato no permitía subir. Son adaptaciones legales contadas; no se ocultan como decisiones originales de subida. Las otras propuestas ilegales detienen la ejecución. Solo recibe cartas propias y datos públicos; las pruebas incluyen cambiar cartas ocultas ajenas manteniendo la observación y la decisión constantes.

Se aprobaron **99 pruebas**, incluida paridad contra los archivos originales de Fullhouse en otro proceso. La auditoría comprobó las 12.698 ejecuciones, 880 grupos pareados de asiento y todas las transiciones de las 396 sesiones. Coincidieron exactamente, excluyendo tiempos, 32 manos preseleccionadas y ocho sesiones completas (192 manos). Esas 224 repeticiones son comprobaciones técnicas, no evidencia nueva de rentabilidad. No hubo fallbacks, truncamientos por reloj, acciones ilegales aceptadas por el motor ni errores de fichas. `frozen_v2` y el código de juego registrado conservan sus huellas.

El comparador inicial de replay confundía tuplas de Python con listas JSON. Se conserva el log fallido; el auditor complementario normaliza solo esa representación, mantiene todos los valores y decisiones y rechaza cambios numéricos. La reconstrucción independiente de sesiones se añadió tras revisión estática, antes del análisis agregado; la corrección de representación se hizo durante la verificación final. Ambas están archivadas por separado, sin cambiar políticas, resultados ni criterios.

Los mundos internos se contabilizan aparte: **55.007.360 de equity**, **8.372.736 de evaluación de búsqueda** y **2.330.624 de entrenamiento de continuación de v5**. No son manos reales ni réplicas independientes del experimento.

Evidencia: [pruebas](../results/competition_2026-10-28/tests_final.txt), [auditoría de manos y replays](../results/competition_2026-10-28/audit.json), [reconstrucción de sesiones](../results/competition_2026-10-28/session_audit.json), [procedencia externa](../pokerfight/external/fullhouse/SOURCE.json), [fuentes registradas](../results/competition_2026-10-28/source/) y [añadido técnico](../results/competition_2026-10-28/technical_addendum/).

## Qué falta para acercarnos a la competencia

1. **Más independencia estratégica.** Incorporar una segunda familia de otro autor. NoRegrets es una opción concreta para auditar, compilar en Rust y entrenar un blueprint propio con semilla, iteraciones y huella registradas; no hay pesos públicos listos que hayamos verificado. No trasladar Slumbot de duelo ni DeepStack-Leduc a seis jugadores por cambiar una etiqueta.
2. **Una batería más representativa.** Mantener estos controles y añadir copias v2 a 4.000 muestras como otro estrato; varias permutaciones de rivales, stacks desiguales y casos de resubidas/pozos laterales. Medir la matriz entre familias para detectar dependencia del emparejamiento. Las posiciones iniciales y respuestas deben continuar siendo públicas.
3. **Más bloques y menos censura.** Usar estos datos para dimensionar un experimento nuevo, con semillas nuevas y un número de grupos suficiente para la precisión deseada. Un piloto técnico de sesiones más largas debe fijar el límite posterior antes de evaluar candidatas. Aumentar mundos internos no sustituye a jugar más repartos independientes.
4. **Reglas y conexión oficiales.** Integrar el kit cuando exista, verificar traducción de observaciones/acciones y adoptar entonces ciegas, antes, duración, eliminaciones y pagos reales. Hasta ahí, los resultados son del laboratorio local.

La mejora concreta de esta iteración es una evaluación verificable frente a una primera política externa aprendida. La evidencia estratégica sigue siendo insuficiente para reemplazar v2.

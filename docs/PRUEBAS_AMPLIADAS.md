# Pruebas ampliadas del bot inicial

Nota del 28 de octubre: esta campaña es histórica y sus semillas ya son desarrollo. Ahora puede elegirse un namespace distinto con `campaign --experiment-id identificador-nuevo`; antes de esta opción, otra carpeta no cambiaba las barajas. Para la candidata preflop v3 se usa el [nuevo protocolo de stacks cortos](PREFLOP_V3_METODO.md).

Los resultados de todas las etapas, incluida la corrección, están en [RESULTADOS_AMPLIADOS.md](RESULTADOS_AMPLIADOS.md).

Esta segunda etapa conserva la política `v1` como control y amplía su evaluación. Las mejoras de infraestructura permiten variar rivales, registrar pérdidas y reproducirlas, y probar mesas con eliminación y ciegas crecientes. No se han ajustado los rangos ni los umbrales de la estrategia a estos resultados.

La revisión de casos límite detectó una decisión incorrecta: con 72o, una ficha por pagar y 102 fichas elegibles, `v1` se retiraba por el filtro preflop. La política `v2` evalúa primero el precio cuando el call pone al bot all-in o todos sus rivales ya lo están. Los calls caros con equity insuficiente siguen retirándose. La corrección y su comparación se fijaron en un [segundo protocolo](../results/challenge_2026-10-27/correction_protocol.json) antes de mirar la validación reservada.

## Diseño fijado antes de medir

El [protocolo guardado](../results/challenge_2026-10-27/protocol.json) fija escenarios, cantidades de manos y tres conjuntos separados de semillas:

| Etapa | Muestras por decisión del candidato | Bloques por escenario/formato | Barajas por bloque | Rotaciones |
|---|---:|---:|---:|---|
| Desarrollo | 512 | 8 | 3 | Todos los asientos |
| Validación reservada | 1 000 | 16 | 4 | Todos los asientos |
| Comprobación con configuración predeterminada | 4 000 | 8 | 3 | Todos los asientos |

Desarrollo y validación recorren los cuatro escenarios con mesas de cinco y seis. La comprobación de 4 000 muestras utiliza el escenario de presión. Las cantidades se completan aunque un resultado sea favorable o desfavorable. Los manifiestos de cada campaña conservan la huella SHA-256 del código evaluado y permiten reanudar tareas terminadas con el mismo plan.

## Rivales

| Escenario | Rivales que se repiten en la mesa | Política de comparación |
|---|---|---|
| Básicos | calling, tight, random | tight |
| Selectivos | tag, tag, lag | tag |
| Presión | pressure, lag, tag | tag |
| Copias del bot | v1 | tag |

`tag` selecciona manos por posición y utiliza equity contra manos desconocidas uniformes para apostar y continuar. `lag` abre más manos, continúa con mayor frecuencia y añade faroles. `pressure` aumenta la frecuencia de apuestas sin fuerza para comprobar la respuesta del candidato. Estos rivales tienen reglas propias y no usan el modelo de rivales de `v1`; sí comparten el contrato público, el evaluador y las utilidades de muestreo.

Son pruebas sintéticas cuya fuerza no está certificada. Las copias de `v1` sirven para estudiar interacción entre políticas semejantes; no representan diversidad estratégica. Los rivales nuevos utilizan 256 muestras por decisión postflop. Los tamaños de muestra del candidato se registran para que no se confundan con la configuración predeterminada.

## Comparación y análisis de pérdidas

Se mantienen barajas compartidas, todos los asientos y stacks de 10 000 que se reinician cada mano. El resultado principal es la diferencia de ciegas grandes por mano entre `v1` y la política de comparación, frente a la misma composición de mesa.

Además del error estándar por bloques, se añade un intervalo percentil bootstrap del 95 % con 5 000 remuestreos de bloques completos. Las rotaciones y manos de una baraja no se remuestrean como si fueran independientes. Con pocos bloques, este intervalo sigue siendo aproximado y no controla comparaciones múltiples entre escenarios.

Cada reporte conserva las cinco mayores pérdidas del candidato. El JSONL contiene la semilla de reparto, asientos, acciones públicas, resultado y observaciones propias utilizadas al decidir. No se exportan cartas ocultas rivales al bot. `replay` reconstruye también las manos anteriores del bloque para recuperar los perfiles acumulados y comprueba board, acciones y fichas finales.

## Mesas con fichas conservadas

Se prueban mesas contra `tag`, `lag` y `pressure`, comenzando con 2 500 fichas, ciegas 50/100, sin ante, y duplicando las ciegas cada quince manos, hasta noventa manos como máximo o un único superviviente. Se rotan los asientos iniciales y se registra supervivencia, fichas finales y mesas terminadas.

El botón avanza al siguiente jugador que sigue en la mesa, usando el orden circular original. Esto corrige el desplazamiento de posiciones que podía ocurrir al calcular la rotación con el número de supervivientes. Es una regla local de botón móvil; no se presenta como la regla oficial de la arena.

Las rotaciones que comparten semilla son dependientes y sus conteos son descriptivos. No se modelan diez rondas, reasignaciones entre mesas, clasificación al top seis ni límites de tiempo del torneo.

## Reproducir

Desde la raíz del proyecto, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pokerfight campaign --phase development --samples 512 --blocks 8 --hands-per-block 3 --session-repeats 1 --output-dir results/challenge_2026-10-27/development
.\.venv\Scripts\python.exe -m pokerfight campaign --phase holdout --samples 1000 --blocks 16 --hands-per-block 4 --session-repeats 2 --output-dir results/challenge_2026-10-27/holdout

# Repetir una pérdida con todos los estados anteriores necesarios
.\.venv\Scripts\python.exe -m pokerfight replay results/challenge_2026-10-27/development/pressure_5p.json --worst 0 --output results/replay_loss.json

# Mesa individual configurable
.\.venv\Scripts\python.exe -m pokerfight simulate --players 6 --hands 90 --carry-stacks --starting-stack 2500 --blind-interval 15 --opponents tag lag pressure
```

Una carpeta con otro plan o código no se reutiliza. Para una campaña nueva se debe elegir otra carpeta. Una campaña terminada reutiliza sus reportes; para repetir el tiempo medido conviene una carpeta nueva con las mismas opciones.

La campaña de desarrollo conserva la huella del código anterior a la corrección. Su control `v1` puede reproducirse con las reglas preservadas. Para volver a ejecutar esa campaña con el código actual debe elegirse otra carpeta. La campaña reservada se ejecuta con el control `v1` explícito; la comparación adicional `v2`/`v1` se reproduce con `python -m scripts.compare_versions`, después de completar la campaña reservada.

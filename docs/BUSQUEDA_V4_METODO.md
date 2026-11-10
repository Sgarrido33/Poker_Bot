# Búsqueda de acciones preflop v4

Esta iteración dedica el presupuesto adicional a comparar acciones y respuestas rivales. Mantiene Python 3.12, Eval7, PokerKit y el entorno `.venv`. La política predeterminada sigue siendo v2 hasta demostrar una mejora. El [protocolo registrado](../results/action_search_2026-10-28/protocol.json) se guardó antes del piloto y la [evidencia](BUSQUEDA_V4_RESULTADOS.md) incluye resultados desfavorables.

## Qué calcula

`action_model.py` representa hipótesis de respuesta; `action_search.py` realiza el muestreo y decide. La observación continúa conteniendo únicamente cartas propias e información pública. Se preparan los rangos ponderados existentes, se muestrean conjuntamente las manos rivales rechazando todo reparto con colisiones y se completa el board. Las mismas manos, board y uniformes de respuesta se usan para todas las acciones y modelos de una simulación. Esto reduce el ruido de las diferencias entre acciones.

Con hasta 12 bb efectivas y antes del flop se consideran acciones legales distintas: la de v2, retirada/check, call ante una subida, apertura pequeña (2 bb; ante subida, dos veces la apuesta mayor) y all-in efectivo. No se añade un limp de apertura. Se respetan mínimos legales y cobertura máxima rival. Las decisiones con precio all-in que ya corregía v2 tienen prioridad y no entran en la búsqueda. Fuera del alcance, v4 coincide con el control de mayor muestreo si recibe el mismo estado y perfil.

Hay tres supuestos de continuación: selectivo, intermedio y amplio. La probabilidad de call depende de una ordenación heurística de las cartas muestreadas, el precio, calls previos de esta ronda hipotética y un ajuste pequeño basado en el perfil público. Los umbrales de fuerza son 0,72/0,64/0,56; el efecto del precio es 0,65 × (precio−0,20), con curva logística de pendiente 18 y soporte positivo entre 0,02 y 0,98. No se observa el tipo de bot rival ni se entregan cartas simuladas al modelo público.

Para cada respuesta se incorporan solamente las fichas realmente pagadas en esa rama. Se resuelven capas de pozo, dinero de retirados, empates y devoluciones. El valor es devolución bruta menos inversión adicional desde la observación actual. Retirarse vale cero desde ese punto: las contribuciones anteriores son costo hundido. No se comparan fracciones de equity como si fueran directamente valores de apostar.

**Límite sustancial:** el modelo de un paso permite fold/call y después showdown. Omite resubidas, apuestas futuras y reasignación de riesgo por clasificación. El valor de una apuesta que deja fichas detrás es una aproximación de checkdown; no es el EV completo del juego. Los tres modelos son hipótesis manuales, no una distribución posterior calibrada ni una solución GTO. La evaluación en partidas completas decide si esta aproximación ayuda.

## Muestreo adaptativo y tiempo

La candidata dedica hasta 4 000 muestras a obtener su acción base. Revisa la búsqueda en lotes de 256, a partir de 512 mundos. Solo cambia si la ganancia estimada frente a esa base supera **0,05 bb más dos errores estándar de la diferencia pareada en los tres modelos**. Puede terminar cuando no queda una mejora suficientemente prometedora o cuando una alternativa tiene ventaja clara. Conservar la base ante incertidumbre es parte de la política.

El tope predeterminado de v4 es 16 384 mundos y el presupuesto conjunto de preparación, equity base y búsqueda es 3 500 ms. El tope limita trabajo; no se intenta llenar el reloj artificialmente. Se comprueba el plazo cada dieciséis intentos de reparto y se reserva margen para construir la respuesta. Si se agota el tiempo de búsqueda, se conserva la acción base y se registra `deadline_keep_v2`. Eso se distingue de un respaldo por error y de un timeout del supervisor. Los dos errores estándar y la parada repetida son heurísticos; no proporcionan un intervalo de confianza secuencial garantizado.

`supervision.py` ejecuta v4 en un proceso persistente. El padre cubre con su reloj tanto la escritura al pipe como la espera de respuesta y puede matar al hijo bloqueado. El objetivo de respuesta local es 4 250 ms más una limpieza acotada; se devuelve check o fold legal en ese caso. Un reinicio pierde perfiles históricos del proceso hijo y se registra como respaldo. Las pruebas incluyen bloqueo del cálculo, bloqueo de escritura de un mensaje grande y una acción ilegal del hijo. `decide --policy v4` y `serve --policy v4` usan este supervisor; las campañas estratégicas ejecutan el bot directamente y el perfil separado mide el camino supervisado.

La inicialización del proceso se hace antes de las decisiones de un servidor persistente. Los tiempos publicados no incluyen arranque, parseo de entrada ni red. El cliente oficial deberá incorporar su recepción y envío a un plazo absoluto de cinco segundos; la API todavía no está integrada. No se promete un límite de cinco segundos extremo a extremo basándose en este microbenchmark local.

## Tres controles y presupuesto comparable

Se conserva la instantánea `frozen_v2` sin modificar y se comprueba su manifiesto. La variante `v2mc` usa exactamente sus rangos, muestreo y selección; solamente acepta un presupuesto de cálculo mayor. La comparación tiene tres brazos:

| Variante | Muestras máximas en validación | Presupuesto | Trabajo |
|---|---:|---:|---|
| v2 original | 4 000 | 1 600 ms | Política predeterminada conservada |
| v2mc | 16 384 | 3 500 ms | Más precisión de equity |
| v4 | 16 384 | 3 500 ms | Equity base + comparación de acciones; mismo plazo total |

v4 y v2mc tienen el mismo techo de tiempo y parámetro máximo de muestras, pero asignan el trabajo a tareas distintas. No se afirma que consuman el mismo CPU real: se publican latencias y mundos efectivamente completados. Comparar también con v2 original comprueba si la nueva asignación supera la solución actual.

La selección congelada resta un error estándar a la equity. Al aumentar las muestras, esa resta suele disminuir: v2mc puede cambiar decisiones por menor ruido y también por un descuento de incertidumbre menor, sin modificar sus reglas ni umbrales. No debe atribuirse automáticamente cualquier diferencia de fichas a una mejor estimación de la probabilidad real.

Los rivales de reglas siguen usando 256 muestras postflop. Las copias congeladas de v2 usan 512 muestras y 1 600 ms. Ese presupuesto rival es fijo en los tres brazos; no se multiplican sus muestras por dar más cómputo al héroe. Los reportes guardan ambas configuraciones y el replay las respeta.

## Evaluación registrada

Se usan namespaces `pf-response-search-20261028-b1:pilot:01` y `:validation:01`, que intervienen realmente en las semillas. Todos los resultados anteriores, incluidos v3 y los perfiles de cómputo, son desarrollo. Los escenarios son selectivos (tag, tag, lag), presión (pressure, lag, tag) y copias de v2.

| Contextos por escenario | Piloto | Validación |
|---|---|---|
| 5/6 jugadores, 4/8/12 bb | 2 bloques | 8 bloques |
| 2/3/4 jugadores, 4/8/12 bb | 1 bloque | 3 bloques |
| 5/6 jugadores, 20/100 bb | 1 bloque | 3 bloques |
| Manos por bloque y asiento | 1 | 1 |
| Cuota v4/v2mc | 1 024 | 16 384 |

Son 57 celdas por fase y los tres brazos rotan todos los asientos con barajas y semillas de políticas compartidas. Los bloques son independientes; las rotaciones no lo son. Se usa bootstrap de bloques completos por celda y remuestreo estratificado para agregados con igual peso a las celdas. No se ajustan parámetros después del piloto.

La barrida reinicia políticas por bloque y asiento, y cada uno contiene una mano: mide principalmente decisiones con perfiles iniciales. Las sesiones conservan perfiles y permiten observar la adaptación entre manos. No se atribuye a la barrida una evaluación extensa de aprendizaje de rivales.

Las sesiones comienzan a 8 bb y duplican las ciegas cada diez manos. El piloto fija un grupo contra presión y hasta dieciséis manos. La validación fija dos grupos por escenario y formato principal, hasta veinte manos o un único superviviente. Se rotan todos los asientos en cada grupo y se ejecutan los tres brazos. Se agrupan rotaciones al calcular incertidumbre. Si divergen las eliminaciones, los repartos posteriores pueden divergir por el cambio de jugadores activos.

El contraste principal exige un intervalo del 95 % completamente positivo para v4−v2mc y también para v4−v2 original, en 5/6 jugadores y 4/8/12 bb. La media por cada formato debe ser no negativa frente a ambos. El intervalo agregado de fichas finales de sesiones debe tener límite inferior no negativo frente a ambos controles. Se requieren cero acciones inválidas, propuestas ilegales recuperadas, respaldos por error o decisiones mayores de 4 250 ms, y conservación de fichas. El perfil supervisado debe pasar sus controles normales y la interrupción intencional. Con evidencia insuficiente se mantiene v2.

Las muestras de cada celda son pequeñas y los rivales sintéticos. Los intervalos por contexto son exploratorios, sin corrección de comparaciones múltiples. Bust con reposición y eliminación real se informan por separado. Ganar una mesa no equivale a clasificación al torneo.

## Reproducción

La optimización posterior del núcleo se documenta en [RENDIMIENTO_V4_RESULTADOS.md](RENDIMIENTO_V4_RESULTADOS.md). La campaña publicada exige su huella de código original, conservada en `research/policy_snapshots/pre_fast_v4_20261028`. Los comandos siguientes entran en esa instantánea para repetirla; los informes Markdown regenerados allí quedan en su propia carpeta `docs`. El código actual se usa para experimentos nuevos y para el benchmark de rendimiento.

```powershell
# Suite actual; la evaluación estratégica original cerró con 64 pruebas
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Fases existentes, reanudables con idéntico código y entorno
Push-Location research/policy_snapshots/pre_fast_v4_20261028
try {
    $pokerPython = (Resolve-Path ../../../.venv/Scripts/python.exe).Path
    & $pokerPython -m pokerfight.action_experiment --root ../../../results/action_search_2026-10-28 --phase pilot
    & $pokerPython -m pokerfight.action_experiment --root ../../../results/action_search_2026-10-28 --phase validation
    & $pokerPython -m scripts.profile_action_search --root ../../../results/action_search_2026-10-28
    & $pokerPython -m scripts.verify_terminal_payoffs --output ../../../results/action_search_2026-10-28/terminal_oracle.json
    & $pokerPython -m scripts.report_action_search --root ../../../results/action_search_2026-10-28 --reuse-analysis
} finally {
    Pop-Location
}

# Comparar búsquedas originales/optimizadas con el mismo trabajo
.\.venv\Scripts\python.exe -m scripts.benchmark_action_compilation --output results/action_compilation_repeticion/benchmark.json

# Registrar un experimento nuevo antes de obtener resultados
.\.venv\Scripts\python.exe -m pokerfight.action_experiment --root results/otro_id --init identificador-nuevo

# Candidata supervisada; v2 sigue siendo el valor predeterminado
.\.venv\Scripts\python.exe -m pokerfight decide examples/all_in_price.json --policy v4
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v4
.\.venv\Scripts\python.exe -m pokerfight serve --policy v4

# Una celda con idéntico techo de cálculo para v4/v2mc
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v4 --baseline v2mc --players 6 --starting-stack 800 --samples 16384 --budget-ms 3500 --rival-samples 512 --rival-budget-ms 1600 --opponents v2 --blocks 8 --hands-per-block 1 --experiment-id ejemplo-nuevo --trace results/ejemplo_v4.jsonl --output results/ejemplo_v4.json
```

Antes de cambiar código se guardó [el paquete y scripts previos a v4](../research/policy_snapshots/pre_v4_20261028/environment.json). Eso permite volver a ejecutar la campaña v3 con su huella original desde ese directorio. El control v2 conserva sus seis módulos originales y las pruebas de manos doradas; no se retocaron rangos compartidos para favorecer a la candidata.

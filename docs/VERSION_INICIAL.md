# PokerFight v0.1 · versión inicial local

Implementada el 27 de octubre de 2026. Python 3.12, Eval7 0.1.11 y PokerKit 0.7.7, siguiendo las decisiones previas. Ejecuta decisiones independientes, un proceso JSONL persistente, manos completas y evaluaciones pareadas. No usa servicios externos para jugar.

Actualización posterior: las [pruebas ampliadas](PRUEBAS_AMPLIADAS.md) conservan estas reglas como política `v1`. La política actual `v2` corrige los calls preflop que ponen al bot all-in o enfrentan solo rivales all-in: evalúa su precio antes del filtro de manos iniciales. Los demás parámetros permanecen como se describen aquí.

## Arquitectura

| Archivo | Responsabilidad |
|---|---|
| `pokerfight/domain.py` | Observación pública, acciones legales y capas de pozos elegibles |
| `pokerfight/preflop.py` | Rangos iniciales escritos a mano por posición |
| `pokerfight/opponents.py` | Conteos por rival/contexto y confianza acotada |
| `pokerfight/equity.py` | Rangos ponderados, muestreo conjunto y reparto estimado |
| `pokerfight/strategy.py` | Política heurística y respaldo ante errores/tiempo |
| `pokerfight/arena.py` | Adaptador local PokerKit; separación entre motor y políticas |
| `pokerfight/evaluation.py` | Mesas de prueba, comparación por bloques y latencia |
| `pokerfight/cli.py` | Comandos `decide`, `serve`, `simulate` y `evaluate` |

El bot recibe un objeto `Observation`, sin motor, mazo ni cartas rivales. Las cartas simuladas permanecen dentro del estimador. PokerKit recibe las decisiones y verifica las reglas independientemente del validador del bot.

## Decisiones de diseño adoptadas

Son parámetros propios de arranque, sin ajuste a los resultados publicados en esta evaluación. No son tablas GTO, parámetros extraídos de los artículos ni un modelo entrenado.

| Parámetro | Valor inicial |
|---|---|
| Muestras solicitadas por decisión | 4 000 |
| Presupuesto cooperativo de preparación y muestreo | 1 600 ms; configurable de 1 a 1 900 |
| Objetivo de decisión completa | Menos de 2 000 ms; límite oficial indicado en las bases: 5 000 ms |
| Confianza máxima sobre un rival | 0,35 |
| Suavizado de confianza | 40 observaciones pertinentes |
| Apertura preflop | 2,5 ciegas grandes + una por call previo |
| Resubida preflop de valor | Máximo entre tres veces la apuesta mayor y apuesta mayor + 0,75 del pozo |
| Apuesta/subida postflop | Apuesta mayor + 0,50 del pozo después del call; 0,75 con equity conservadora ≥ 0,80 |
| Umbral de subida postflop | 0,64 contra un rival; 0,55 contra varios; además superar precio + 0,15 |
| Margen de call | Preflop: 0,025 premium / 0,055 otras; flop: 0,045; turn: 0,025; river: 0 |

Se resta un error estándar de Monte Carlo a la equity para la decisión. Este error describe el muestreo bajo los rangos supuestos; no cuantifica el error de esos rangos ni asegura cobertura frente a estrategias reales. El margen se elimina si el call pone al bot all-in o todos los rivales ya están all-in. Los tamaños se recortan a los límites legales y al monto que un rival puede igualar, respetando el mínimo permitido por el motor.

## Política preflop

Los rangos completos están en `preflop.py`. Hay seis posiciones: UTG, HJ, CO, BTN, SB y BB; se utilizan las que corresponden al número de jugadores. En duelo, BTN también es la ciega pequeña. La posición se calcula desde el botón y el orden circular de asientos al inicio de la mano.

Ejemplos: UTG abre `66+,ATs+,KJs+,QJs,JTs,T9s,AJo+,KQo`; BTN usa un rango más amplio de 80 clases de mano. La defensa base es `55+,A9s+,KTs+,QTs+,JTs,T9s,98s,AJo+,KQo`; BB y BTN disponen de una defensa más amplia. Las clases no pesan igual: una pareja tiene seis combinaciones, una mano suited cuatro y una offsuit doce.

`QQ+` y `AK` pueden resubir por valor si la equity conservadora supera el precio con margen. Con hasta doce ciegas restantes, `TT+,AQs+,AKo` pueden abrir all-in cuando el rango de apertura lo admite. No se implementó una estrategia push/fold resuelta. Las manos no premium no pagan más de ocho ciegas grandes preflop. Un check gratuito se conserva aunque la mano no esté en rango.

## Rangos e información incompleta

Cada rival empieza con todas las combinaciones compatibles con la mano propia y el board. Sus acciones públicas preflop ajustan los pesos mediante un orden heurístico de manos: calls y subidas favorecen manos más fuertes; nuevas resubidas estrechan el supuesto. Ninguna combinación compatible se elimina por una acción: se mantiene soporte positivo.

En postflop, la última acción del rival en la calle actual cambia los pesos según la categoría de mano formada con el board ya visible. No se evalúan acciones pasadas usando cartas que aparecieron después. Esta aproximación omite muchos detalles: tamaño de apuesta, posición rival, proyectos, textura y secuencias completas. Se debe calibrar antes de aumentar su influencia.

Los contextos del perfil son `(identificador, calle, enfrentaba_apuesta)`. Solo cuentan eventos públicos únicos; repetir el historial de una mano no duplica observaciones. La confianza es `0,35 * n / (40 + n)`. Afecta moderadamente al rango y al margen de call; con cero observaciones no hay adaptación. Los perfiles se reinician si cambia `table_id`. No se intentan enlazar identidades entre mesas.

## Muestreo y pozos

Se extrae una mano de cada rango de forma independiente. Si dos rivales comparten una carta, se rechaza **el reparto conjunto completo**. De ese modo se muestrea el producto de los rangos condicionado a que todas las manos sean compatibles, evitando el sesgo de normalizar sucesivamente tras cada rival. Después se completa el board con cartas uniformes sin reemplazo.

Las contribuciones, incluyendo las de jugadores retirados, se dividen en capas después de añadir únicamente el call del bot. Se calcula la fracción ganada en cada capa elegible y se reparten empates. Se excluyen pozos laterales inaccesibles al bot. Las capas con un único jugador elegible incluyen devoluciones de apuestas no igualadas.

`equity` significa **fracción esperada del dinero elegible después del call**, ponderada por el importe de cada pozo. `expected_return` es la devolución bruta esperada, incluyendo fichas previamente aportadas y el call hipotético. No es ganancia neta de la mano. El costo incremental del call se compara con ese dinero elegible. No se supone que jugadores que aún deben actuar vayan a pagar; sus posibles calls y apuestas futuras no están modelados.

La política de apuestas utiliza esta estimación de showdown y reglas de valor. No calcula EV de apuestas, fold equity, respuestas futuras, ICM ni riesgo de clasificación. La distinción equity/valor de acción de W02 se conserva explícitamente como límite.

## Tiempo y recuperación

El reloj se consulta al preparar rangos y cada 32 intentos de reparto. Al agotarse, se utiliza la muestra parcial si contiene al menos `min(128, samples)` repartos válidos. Sin muestras suficientes o ante una excepción, el bot pasa si puede; en caso contrario se retira, o paga si el contrato no permite retirarse.

El presupuesto es cooperativo: no interrumpe forzosamente una llamada bloqueada, ni incluye importación inicial, parseo, transporte o red. Un futuro cliente oficial deberá añadir un supervisor con plazo absoluto y margen de envío. `serve` mantiene el proceso y las tablas precargadas para amortizar el inicio.

## Evaluación

Las barajas se fijan por mano antes de la estrategia. Cartas propias, quemadas y board mantienen sus posiciones aunque se retiren jugadores. El azar de cada política usa otra secuencia. Se rota al bot por todos los asientos y se repiten las mismas barajas para la variante candidata y una política base `tight`.

Los asientos de un mismo bloque comparten barajas y se agrupan para calcular la diferencia media; los bloques usan semillas distintas. El intervalo normal aproximado se calcula entre medias de bloques y se presenta como descriptivo con pocos bloques. Este procedimiento no implementa AIVAT.

`evaluate` reinicia las fichas a 10 000 en cada mano, con ciegas 50/100 y sin ante. `simulate --carry-stacks` permite observar eliminaciones en una sola mesa con ciegas fijas. Ninguno reproduce diez rondas con reasignaciones, clasificación al top seis, límites de reloj, cambios de ciegas ni la final oficial. Las bases dejan parámetros pendientes que requieren el kit.

Los resultados, comandos y límites de la validación están en [VALIDACION_V01.md](VALIDACION_V01.md).

## Relación con las cinco referencias

- W02: separación de rangos, estimación y política; no se reproduce Loki ni su comparación de EV.
- W03: hipótesis sobre cartas y acciones sin convertirlas en información observada; no hay posterior bayesiano completo.
- W05: confianza acotada por observaciones pertinentes; no se heredan garantías DBR.
- W14: conjunto pequeño de tamaños y trabajo precalculado; no hay blueprint aprendido ni búsqueda de Pluribus.
- W23: barajas compartidas, asientos rotados e incertidumbre entre bloques; no es el estimador AIVAT.

## Próximos pasos

Integrar el protocolo oficial y comprobar su semántica de apuestas, tiempo e identidad. Después incorporar bots del kit a evaluaciones más grandes, calibrar rangos con datos separados y modelar respuestas de rivales antes de estimar EV de apuestas. La simulación del torneo completo y una política de riesgo por clasificación quedan pendientes. El cálculo nativo se reconsiderará solo si una medición representativa lo requiere.

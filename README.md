# PokerFight

Proyecto para construir un bot autónomo de Texas Hold'em No-Limit para PokerFight 2026.

La elección inicial es **Python 3.12 + Eval7**, con **PokerKit para simular partidas locales**. El cálculo se mantendrá separado de la estrategia y de la conexión para poder incorporar un núcleo C/C++ si las mediciones de la estrategia completa lo justifican.

La **versión 0.1 ya funciona en local**: decide con información pública, estima equity frente a rangos ponderados y juega manos completas en PokerKit. Incluye selección por posición, pozos laterales, acciones legales, respuesta de respaldo y evaluación reproducible. El cliente TCP `pokerfight.official` conecta `v2` con la mesa del kit de la organización.

La política actual `v2` incorpora una corrección de precio en calls preflop all-in: una mano fuera del rango inicial puede pagar si la probabilidad estimada justifica el costo y ya no habrá apuestas propias posteriores. `v1` conserva las reglas anteriores como control. `decide` y `serve` usan la corrección; `simulate` y `evaluate` permiten elegir con `--hero v1` o `--hero v2`.

La primera iteración del 28 de octubre añade la candidata `v3` para aperturas limpias con hasta 8 bb efectivas. `v1` y `v2` están aisladas en una instantánea con sus propios rangos, modelo, contrato y muestreo; las modificaciones de la candidata no alteran el control. **Se mantiene v2 como predeterminada**: tras 15 334 manos nuevas, v3 perdió 0,069 bb/mano en el contraste principal y empeoró las fichas finales de sesiones. Esa etapa cerró con 45 pruebas aprobadas. Véanse el [método y reproducción](docs/PREFLOP_V3_METODO.md) y los [resultados completos, incluidos los desfavorables](docs/PREFLOP_V3_RESULTADOS.md). `decide --policy v3`, `serve --policy v3` y `simulate/evaluate --hero v3` permiten probar la candidata experimental.

La candidata posterior `v4` compara acciones preflop con hasta 12 bb efectivas, mediante respuestas hipotéticas y muestreo adaptativo. En **9 097 manos nuevas**, ganó +0,465 bb/mano frente a v2 original en el contraste principal con fichas reiniciadas, pero las sesiones con eliminaciones siguen siendo inciertas: **v4 permanece experimental y v2 sigue por defecto**. Esa etapa y su optimización cerraron con **67 pruebas**. `decide/serve --policy v4` usan un proceso supervisado, con presupuesto de cálculo de 3 500 ms y objetivo de corte local de 4 250 ms. `v2mc` conserva la selección congelada y permite medir el efecto de aumentar solamente el muestreo. Véanse el [método v4](docs/BUSQUEDA_V4_METODO.md) y los [resultados de tres brazos](docs/BUSQUEDA_V4_RESULTADOS.md).

La optimización posterior prepara una sola vez los costos y pozos de cada posible respuesta. La búsqueda con trabajo fijo fue **2,80 veces más rápida** en siete estados de desarrollo: conserva exactamente los resultados al comparar los mismos mundos. También coincidieron 57 decisiones guardadas y veinte manos completas por versión. Esta medición demuestra menor costo de cálculo; la fuerza estratégica sigue pendiente de más validación. Véanse [resultados y reproducción del rendimiento](docs/RENDIMIENTO_V4_RESULTADOS.md).

La iteración de calidad añade **v4rb**, que integra todas las respuestas fold/call en cada mundo de cartas, y **v5**, que permite una resubida all-in y aprende una continuación usando simulaciones separadas. La integración redujo un **23,4 % la varianza entre réplicas** en siete estados de desarrollo a igual cuota de mundos. Se completaron **8 155 ejecuciones nuevas de mano** entre piloto y validación de cinco brazos, sin fallbacks ni errores de fichas. La mejora frente a v4 sigue siendo incierta y ninguna candidata cumplió todos los criterios de promoción: **v2 conserva el valor predeterminado**. La suite actual pasa **87 pruebas**. El [método de calidad](docs/CALIDAD_V5_METODO.md) y los [resultados de cinco brazos](docs/CALIDAD_V5_RESULTADOS.md) distinguen precisión del estimador, ganancias locales y sesiones con eliminación.

La batería orientada a **bot contra bot** incorpora al rival externo **Fullhouse**, con su código y pesos públicos fijados por commit y SHA-256. Su red Deep CFR y su overlay preflop forman una familia estratégica independiente; varias instancias siguen siendo una sola familia. El adaptador usa solo observaciones propias y exige ciegas fijas 50/100, sin ante. La [investigación de agentes](docs/RIVALES_EXTERNOS_INVESTIGACION.md), la [revisión de evaluación académica](docs/EVALUACION_ACADEMICA.md) y el [protocolo de cross-play](docs/COMPETENCIA_METODO.md) describen disponibilidad, límites y comandos. **v2 sigue predeterminada**; esta batería no autoriza promoción automática.

La primera campaña externa completó **12.698 ejecuciones de mano** y la suite pasa **99 pruebas**. Las mejoras medias en la mesa mixta externa siguen siendo inciertas, y las sesiones tienen mucha censura: ninguna candidata pasó el filtro registrado. Véanse el [informe sencillo y los resultados desfavorables](docs/COMPETENCIA_RESULTADOS.md) y los [comandos de reproducción](docs/COMPETENCIA_METODO.md).

La segunda etapa incorpora una adaptación de **HonestPlayer** como política
externa educativa, además de Fullhouse, y un control de copias v2 con **4.000
muestras**. NoRegrets fue investigado pero no pudo integrarse con un blueprint
validado. Un piloto separado de **2.352 manos técnicas** seleccionó sesiones de
**128 manos**; el [método de la segunda batería](docs/COMPETENCIA_SEGUNDA_METODO.md)
registra la comparación, los resultados de eliminación y los comandos. La
[procedencia de la segunda familia](docs/SEGUNDA_FAMILIA_EXTERNA.md) explica su
alcance y sus limitaciones. **v2 conserva el valor predeterminado.**

La segunda batería completó **64.679 ejecuciones de comparación**, con **115
pruebas aprobadas** y **947 manos de replay** verificadas aparte. Extender las
sesiones de 24 a 128 manos redujo las mesas sin terminar de **732/880 a
152/880**. Las candidatas sufrieron más eliminaciones tempranas, pero menos
eliminaciones a 128; todos los intervalos principales incluyeron cero y ninguna
pasó el filtro. El [informe de la segunda etapa](docs/COMPETENCIA_SEGUNDA_RESULTADOS.md)
incluye los resultados desfavorables, el fallo de paridad del evaluador original
de Honest frente a Eval7 y el intento de compilación de NoRegrets.

## Probar ahora

**Candidata v8d (30 de octubre):** conserva las tablas de v8 y delega en v2
las respuestas no terminales en las que otro rival pueda cubrir más fichas que
el raiser usado para elegir la tabla. Observa el historial en cada solicitud
y registra los errores de tabla. `decide --policy v8d` permite probarla;
`v8d_open`, `v8d_reshove` y `v8d_call` separan sus componentes para desarrollo.
La evaluación ya terminó: **640.391 ejecuciones nuevas de mano y 9.636 mesas**,
con 212 pruebas aprobadas y 336 manos de replay exacto. En la comparación
principal de 424 grupos, v8d obtuvo **240 fichas más que v2** y **270 menos que
v4rb**; ambos intervalos ajustados excluyen cero. También tuvo
**+7,2 puntos de eliminación temprana frente a v2**. **No cumplió los criterios
de avance y v2 sigue predeterminada.** Los
[resultados por escenario y componente](docs/VALIDACION_V8D_RESULTADOS.md) y el
[método registrado](docs/VALIDACION_V8D_METODO.md) conservan también los resultados
desfavorables y las fuentes congeladas.

**Nueva candidata v8 (29 de octubre, noche):** rangos push/fold de equilibrio
**calculados**, no escritos a mano. Se aplican hasta 15 bb efectivas; el resto
del juego es v2 congelada. En `external_diverse`, v8 ganó **+337 fichas por
mesa** frente a v2 en la batería 1, con 80 grupos, y **+456** en una réplica con
semillas nuevas. También ganó **+10 a +12 puntos de victorias** y bajó **6–9
puntos la eliminación a 128 manos**; todos esos intervalos excluyen cero. El
resultado desfavorable aparece contra una mesa de copias de v2, muy tight: sin
diferencia concluyente en fichas, pero **+25 puntos de eliminación temprana**. Detalles, aproximaciones
y comandos en [PUSHFOLD_V8.md](docs/PUSHFOLD_V8.md). Para probarla:
`decide --policy v8`. v2 sigue predeterminada hasta decidir su promoción.

La [revisión independiente del 30 de octubre](docs/REVISION_V8_2026_10_30.md)
reproduce las medias desde los datos crudos y mantiene esa decisión. Detecta
re-shoves que exceden la profundidad de la tabla, observaciones omitidas durante
solicitudes de tabla (la arena sí las completa al cerrar la mano) y una
interpretación causal excesiva de v8c. Recomienda resolver
esos puntos en otra variante antes del contraste confirmatorio con v2 y v4rb.

La [comparación de seis versiones con v7](docs/INTEGRACION_RESUBIDAS_V7_RESULTADOS.md)
completó **55.806 ejecuciones nuevas de mano** y verificó 496 manos de replay.
La nueva candidata integra respuestas y una resubida, con continuaciones
ponderadas por su probabilidad de alcance; el [método](docs/INTEGRACION_RESUBIDAS_V7_METODO.md)
detalla el algoritmo. Redujo ruido del estimador, pero las sesiones fueron
desfavorables: **262 fichas menos de media y 16,94 puntos más de eliminación
temprana frente a v2**. v4rb tuvo la mayor media de fichas de esta batería.
Los intervalos son exploratorios y **v2 sigue predeterminada**. La suite actual
del proyecto pasa **191 pruebas**.

La [mejora técnica del 29 de octubre](docs/MEJORAS_TECNICAS_2026_10_29.md) reduce
un **45,3 % el tiempo de búsqueda integrada** en siete estados de desarrollo,
con los mismos resultados a igual cuota. También conserva la acción de
referencia cuando los rangos casi incompatibles agotan los intentos sin completar
la muestra. Coincidieron 40 pares de manos completas y esa etapa cerró con **156
pruebas**. Es una mejora de cálculo y robustez; **v2 sigue predeterminada**.

La [tercera evaluación ya está completa](docs/TERCERA_EVALUACION_RESULTADOS.md):
251.175 ejecuciones de mano, 3.960 mesas y 144 grupos independientes. v6 no
pasó las dos métricas principales; frente a v4rb tuvo más eliminaciones
tempranas y menos fichas de media. **v2 sigue predeterminada.** El diagnóstico
y la candidata experimental quedan documentados, incluidos los resultados
desfavorables. La suite final pasa 153 pruebas y coincidieron 551 manos de
replay desde el código congelado.

NoRegrets ya tiene [adaptador general y perfiles propios para 2–6
jugadores](research/noregrets_training_20261028/RESULTS_VALIDATED_V3.md), con un
millón de iteraciones por perfil. La prueba separada de 1.703 manos en nuestra
arena terminó sin errores, pero recurrió al respaldo en 40,76 % de sus
consultas al transferirse a stacks variables. Es una segunda familia aprendida
experimental; su fuerza competitiva sigue sin acreditarse. Las reglas oficiales
aún no están disponibles.

Desde esta carpeta, en PowerShell, usando el entorno `.venv` ya preparado:

```powershell
# Decidir una jugada del ejemplo (AA en una mesa de cinco)
.\.venv\Scripts\python.exe -m pokerfight decide examples/observation.json

# Jugar 20 manos locales contra tres tipos de rivales básicos
.\.venv\Scripts\python.exe -m pokerfight simulate --players 5 --hands 20

# Mesa de seis con fichas que se conservan y eliminación
.\.venv\Scripts\python.exe -m pokerfight simulate --players 6 --hands 50 --carry-stacks

# Verificar reglas, muestreo, respaldo y simulador
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Probar la búsqueda supervisada en una defensa preflop de ocho bb
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v4

# Probar las candidatas de calidad con el perfil evaluado
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v4rb --samples 4096
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v5 --samples 4096

# v7 experimental: cuota evaluada y presupuesto supervisado
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v7 --samples 1024
```

Para un entorno nuevo: instalar Python 3.12 x64, ejecutar `py -3.12 -m venv .venv` y luego `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. No se necesita activar el entorno, instalar OpenSpiel ni compilar C++ para ejecutar esta versión. La instalación requiere red; las decisiones y simulaciones son locales.

Para usar las tablas v8 y sus variantes o ejecutar las campañas, instalar
también `requirements-evaluation.txt`, que fija la dependencia NumPy.

## Comparar y conectar

```powershell
# Comparación pareada: barajas fijas, ocho bloques y todos los asientos
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v2 --players 5 --blocks 8 --hands-per-block 5 --output results/evaluation_current_5p.json
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v2 --players 6 --blocks 8 --hands-per-block 5 --output results/evaluation_current_6p.json

# Un JSON de entrada y una respuesta JSON por línea, proceso persistente
Get-Content examples/observation.json -Raw | .\.venv\Scripts\python.exe -c "import json,sys; print(json.dumps(json.load(sys.stdin)))" | .\.venv\Scripts\python.exe -m pokerfight serve
```

`serve` intercambia mensajes por stdin y stdout según el [protocolo local v1](docs/PROTOCOLO_LOCAL.md). Para jugar con el [kit oficial](https://github.com/aicspucp/pokerfight-arena-participantes), abre una mesa con cuatro rivales y ejecuta el cliente TCP desde este proyecto:

```powershell
.\.venv\Scripts\python.exe -m pokerfight.official -addr 127.0.0.1:9000 -token v2-local
```

En una mesa abierta del kit sirve cualquier token distinto al de los otros bots. Para una credencial real, usa la variable de entorno `POKERFIGHT_TOKEN`. El cliente reconecta con el mismo token tras un corte y conserva el socket abierto durante el silencio entre rondas. Si la sesión terminó, usa Ctrl+C. Para una mesa local que termina por EOF, agrega `--once`.

Para una sesión de práctica acotada, agrega `--duration 1800 --journal results/practica.jsonl` al comando del cliente. El resumen incluye tiempos, cortes y respuestas de respaldo. La bitácora registra acciones públicas por alias, cartas mostradas y si la acción del bot coincide con el historial de la mesa. Una acción segura idéntica a la enviada puede ocultar un timeout. Usa el contador de la arena cuando esté disponible.

`evaluate` admite también `--starting-stack`, ciegas y ante para medir profundidades distintas. `--experiment-id` cambia realmente las semillas en `evaluate`, `simulate` y `campaign`; cambiar solo la carpeta no genera barajas nuevas. La matriz corta se registra y ejecuta con `python -m pokerfight.shortstack_experiment`, según el método enlazado. Todos los lotes anteriores, incluidos los que se llamaban `holdout`, ya son datos de desarrollo.

La configuración predeterminada solicita 4 000 muestras y reserva 1 600 ms para el cálculo cooperativo. Se ajusta con `--samples`, `--budget-ms` y `--seed`. `simulate` permite `--starting-stack`, `--small-blind`, `--big-blind` y `--ante`; sus valores iniciales son supuestos locales. `--opponents calling tight random` cambia la mesa de prueba.

Los rivales disponibles también incluyen `tag`, `lag`, `pressure`, `v1` y `v2`. `--blind-interval 15 --carry-stacks` duplica las ciegas cada quince manos. `evaluate --trace ruta.jsonl` registra las observaciones propias; `replay reporte.json --worst 0` reconstruye una pérdida. El [ejemplo de call all-in barato](examples/all_in_price.json) permite comprobar la corrección con `decide`.

## Implementación y evidencia

- [Integración de respuestas y resubidas v7: método](docs/INTEGRACION_RESUBIDAS_V7_METODO.md)
- [Comparación de seis versiones, diagnóstico y resultados desfavorables](docs/INTEGRACION_RESUBIDAS_V7_RESULTADOS.md)
- [Diseño, parámetros y límites de la versión inicial](docs/VERSION_INICIAL.md)
- [Resultados de verificación y evaluación local](docs/VALIDACION_V01.md)
- [Pruebas ampliadas: rivales selectivos, presión, copias del bot y eliminaciones](docs/PRUEBAS_AMPLIADAS.md)
- [Resultados ampliados y comparación de la corrección v2/v1](docs/RESULTADOS_AMPLIADOS.md)
- [Diagnóstico, protocolo y candidata preflop v3](docs/PREFLOP_V3_METODO.md)
- [Resultados nuevos por jugadores, profundidad y eliminaciones](docs/PREFLOP_V3_RESULTADOS.md)
- [Búsqueda v4: más cómputo para comparar acciones y respuestas](docs/BUSQUEDA_V4_METODO.md)
- [Resultados v4, control de mayor muestreo y sesiones](docs/BUSQUEDA_V4_RESULTADOS.md)
- [Optimización de búsqueda: equivalencia y medición de rendimiento](docs/RENDIMIENTO_V4_RESULTADOS.md)
- [Integración de respuestas y búsqueda con resubidas: método](docs/CALIDAD_V5_METODO.md)
- [Resultados de calidad y comparación de cinco brazos](docs/CALIDAD_V5_RESULTADOS.md)
- [Ejemplo completo de observación](examples/observation.json)
- [Código del bot](pokerfight/strategy.py), [muestreo](pokerfight/equity.py) y [simulador](pokerfight/arena.py)

Las ganancias frente a rivales simples sirven para detectar problemas y establecer una referencia. Para estimar la clasificación al torneo faltan la simulación del formato completo y más familias de rivales externos. Fullhouse aporta una primera familia externa, con los límites del adaptador documentados.

## Investigación previa

- [Decisiones técnicas y alternativas consideradas](docs/DECISIONES_TECNICAS.md)
- [Cinco referencias elegidas y qué tomaremos de cada una](docs/TRABAJOS_ANTERIORES.md)
- [Catálogo de 33 publicaciones y motivos de selección o posposición](research/previous_work_2026-10-27/CATALOGO.md)
- [Comparación de herramientas y rendimiento del 27 de octubre de 2026](research/tool_comparison_2026-10-27/COMPARACION.md)

Los documentos de investigación conservan las decisiones y mediciones previas. Los parámetros adoptados ahora se especifican en el diseño de la versión 0.1.

## Alternativa experimental de river

El [cálculo exacto contra un rival en river](docs/RIVER_EXACTO_2026_10_29.md)
enumera las 990 combinaciones posibles. En seis estados con rango completo
tardó 2,88 ms frente a 28,62 ms de Monte Carlo con 4.000 muestras, sin ruido
de muestreo. Incluye una entrada independiente para probarlo sobre las
candidatas vivas y una corrección del cierre de workers en replay. Pasan 190
pruebas. La mejora estratégica aún no está evaluada; v2 sigue predeterminada.

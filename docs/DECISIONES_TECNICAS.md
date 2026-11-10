# Decisiones técnicas de PokerFight

Fecha: 27 de octubre de 2026. Estado: elección inicial aceptada y aplicada en la versión local 0.1. Los parámetros y la validación actuales están en [VERSION_INICIAL.md](VERSION_INICIAL.md) y [VALIDACION_V01.md](VALIDACION_V01.md).

Actualización del 28 de octubre: se mantiene el stack técnico y el `.venv`. La [iteración preflop v3](PREFLOP_V3_METODO.md) aísla el control v2 completo, añade identificadores reales de experimento y evaluación con 2–6 jugadores y 4/8/12/20 bb. La selección por defecto depende de los [criterios y resultados nuevos](PREFLOP_V3_RESULTADOS.md); los documentos históricos conservan sus mediciones originales.

La [candidata v4](BUSQUEDA_V4_METODO.md) usa un presupuesto conjunto de 3 500 ms para equity y comparación de acciones, con supervisión de proceso a 4 250 ms en el protocolo local. Amplía deliberadamente el objetivo inicial de dos segundos para experimentar dentro del plazo de cinco indicado por el usuario. Tras 9 097 manos nuevas hay mejora con fichas reiniciadas e incertidumbre con eliminaciones; [v2 continúa predeterminada](BUSQUEDA_V4_RESULTADOS.md). No se modifican sus dependencias congeladas ni se considera integrada la API oficial.

**Decisión adoptada**

Empezaremos con Python y Eval7. PokerKit será el simulador local de referencia. La estrategia, el cálculo de probabilidades y la conexión con la arena tendrán responsabilidades separadas para poder adaptar la API e incorporar cálculo nativo sin rehacer todo el bot.

| Componente | Elección inicial | Responsabilidad |
|---|---|---|
| Lenguaje principal | Python 3.12 | Estado de la partida, estrategia, validación de acciones, conexión y registros |
| Evaluación de manos | Eval7 0.1.11 | Cálculo rápido del valor de las manos mediante su evaluador compilado |
| Simulación local | PokerKit 0.7.7 | Aplicar reglas, ejecutar partidas y verificar escenarios |
| Optimización posterior | Núcleo de simulación C/C++ | Alternativa para las partes cuyo costo limite la estrategia elegida |
| Presupuesto de decisión | Objetivo interno inicial de 2 segundos | Dejar margen para validar y enviar la respuesta antes del límite de 5 segundos |

Las versiones de la tabla son las verificadas durante la comparación. El presupuesto de dos segundos es una decisión de ingeniería, no una regla adicional del torneo. Habrá que validarlo con la API real.

**Por qué elegimos esta base**

Python facilita experimentar con estrategias, analizar partidas y adaptar la conexión. El evaluador de Eval7 ejecuta su trabajo intensivo en código compilado. En el equipo de pruebas, la combinación pudo realizar 100 000 simulaciones desde el flop contra cinco rivales aleatorios en una mediana de 0,885 segundos.

El bucle C++ con PH Evaluator C redujo esa tarea a 0,032 segundos. Es una alternativa valiosa si necesitamos búsqueda más intensa, pero estas pruebas todavía no muestran que sea necesario trasladar todo el bot a C++.

Ambas cifras corresponden al cálculo de probabilidades del experimento. No incluyen búsqueda estratégica, selección de apuestas ni comunicación de red. La comparación no mide tasas de victoria.

Las mediciones, supuestos, repeticiones, limitaciones y fuentes están en la [comparación completa](../research/tool_comparison_2026-10-27/COMPARACION.md). Las observaciones se conservan en su carpeta `results`.

**Alternativas consideradas**

| Alternativa | Estado | Motivo |
|---|---|---|
| Python + Eval7 | Elegida para empezar | Buen margen medido y una integración inicial relativamente sencilla |
| Python + simulaciones en C/C++ | Reservada para optimización | Mucha más capacidad de cálculo; añade compilación e interfaz nativa |
| Bot completo en C++ | Pospuesta | La decisión requiere conocer el algoritmo completo; el rendimiento de un bot completo no se ha medido |
| PH Evaluator desde Python | Alternativa de evaluador | Funciona y tiene núcleo C; en el experimento, el wrapper público fue más lento que Eval7 |
| Treys | Referencia adicional | Evaluador sencillo en Python puro; rindió menos que las opciones compiladas |
| Evaluador de PokerKit para simulación intensiva | No elegido para ese uso | La tarea de 10 000 simulaciones excedió los cinco segundos; mantenemos PokerKit para simular partidas |
| OpenSpiel | Herramienta de investigación | Útil para algoritmos; el wheel de Windows probado no registra `universal_poker` y su wrapper de PokerKit añade costo |

Estas decisiones corresponden al alcance inicial. Una alternativa pospuesta puede reconsiderarse con evidencia nueva.

**Enfoque de estrategia inicial**

El punto de partida recomendado y aceptado es una estrategia de reglas y probabilidades: selección de manos según posición, estimación frente a posibles manos rivales y decisiones de apuesta que consideren el pozo, el costo de continuar y las fichas disponibles. Las reglas y parámetros iniciales ya se concretaron en [VERSION_INICIAL.md](VERSION_INICIAL.md), a partir de las referencias seleccionadas.

Los proyectos de investigación servirán como referencias de métodos. Se eligieron cinco referentes en [Trabajos anteriores](TRABAJOS_ANTERIORES.md), con sus aportes y límites de adaptación. Todavía no se ha elegido un algoritmo de aprendizaje ni se ha decidido reproducir un bot académico completo.

**Cuándo revisar la incorporación de C++**

Revisaremos esa decisión si una medición representativa de la estrategia completa muestra que el cálculo supera de forma recurrente el presupuesto interno, si no podemos ejecutar la búsqueda o el muestreo de rangos que consideremos necesarios, o si la velocidad de simulación limita la evaluación de mejoras.

Primero identificaremos la parte costosa. La opción preferente será sustituir ese cálculo conservando la interfaz con la estrategia. Superar un tiempo en una prueba aislada no obliga a migrar todo el proyecto.

**Qué falta decidir y verificar**

- Calibración de los parámetros iniciales con rivales más exigentes y datos separados.
- Mejora de los rangos y de los modelos de respuesta; ya existe un muestreo inicial ponderado.
- Validación de apuestas y comparación de versiones con el kit oficial; ya hay evaluación local por bloques.
- Campos, protocolo y acciones válidas de la API oficial.
- Ciegas, antes, horarios y demás detalles que deban confirmar las bases o la arena.
- Latencia de la decisión completa y calidad de juego frente a rivales variados.

La revisión de trabajos anteriores quedó documentada y la primera adaptación está implementada. La integración oficial y la evaluación del formato de torneo siguen pendientes.

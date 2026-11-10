# Trabajos anteriores elegidos para PokerFight

Actualización del 28 de octubre: la revisión orientada a bot contra bot está en [EVALUACION_ACADEMICA.md](EVALUACION_ACADEMICA.md) y [RIVALES_EXTERNOS_INVESTIGACION.md](RIVALES_EXTERNOS_INVESTIGACION.md). Se integra Fullhouse como agente externo experimental con pesos disponibles; no se lo identifica con Pluribus. El [método de cross-play](COMPETENCIA_METODO.md) registra una comparación nueva frente a los controles. La selección histórica que sigue se conserva como antecedente de diseño.

Fecha: 27 de octubre de 2026. Estado: selección de referencias para el diseño inicial, previa a implementar y probar el bot.

Actualización posterior del mismo día: ya se implementó una primera adaptación local. Este documento conserva el razonamiento de selección; los parámetros adoptados y lo que efectivamente se implementó están en [VERSION_INICIAL.md](VERSION_INICIAL.md), con resultados en [VALIDACION_V01.md](VALIDACION_V01.md).

De las **33 publicaciones del [catálogo](../research/previous_work_2026-10-27/CATALOGO.md)** elegimos **cinco referencias principales**. Adoptaremos partes de sus métodos y criterios; el bot será una adaptación propia a nuestra arena y al presupuesto de tiempo. Las cinco referencias no representan cinco agentes que vayamos a descargar o combinar directamente.

La elección técnica se mantiene: [Python + Eval7 y PokerKit como simulador local](DECISIONES_TECNICAS.md), con cálculo C/C++ reservado para necesidades demostradas de rendimiento.

**Criterios de selección**

Priorizamos relación con el póker multijugador No-Limit, utilidad para una versión sin entrenamiento costoso, adaptación al cálculo disponible, uso de información realmente observable y aportes complementarios. El código público ayuda a evaluar una herramienta, pero no convierte resultados de otro juego en evidencia para este torneo. La elección es un juicio de ingeniería basado en esos criterios, no una clasificación científica de los mejores bots.

| Referencia | Decisión concreta | Componente que orienta |
|---|---|---|
| W02 · Loki-2, 1999 | Simular manos rivales plausibles y distinguir equity de valor de una acción | Muestreo y decisión |
| W03 · Bayes' Bluff, 2005 | Mantener incertidumbre sobre estrategias y cartas ocultas | Modelo de rivales |
| W05 · Data Biased Robust Counter Strategies, 2009 | Graduar la adaptación según la evidencia disponible | Control de adaptación |
| W14 · Pluribus, 2019 | Acotar acciones y organizar el cálculo previo y durante la mano | Organización de la política |
| W23 · AIVAT, 2017 | Evaluar mejoras teniendo en cuenta la varianza | Método de evaluación |

**W02 Loki-2 como punto de partida del muestreo**

[Fuente de los autores, apartados 5.1–5.2](https://poker.cs.ualberta.ca/publications/AAAI99.pdf). El trabajo usa distribuciones de manos rivales y simulaciones para comparar alternativas de apuesta. Es un antecedente de Hold'em Limit, no una política No-Limit lista para usar.

Tomaremos su separación entre modelo, muestreo y decisión. Nuestra adaptación empezará estimando equity frente a rangos y proponiendo acciones legales; comparar su valor esperado requerirá además modelar respuestas y apuestas futuras. Ganar una proporción alta de showdowns no determina por sí solo qué apuesta conviene.

Quedan por definir rangos y política de continuación. Cada simulación deberá respetar cartas conocidas y evitar duplicaciones entre rivales. No afirmaremos que reproducimos Loki ni sus resultados.

**W03 Bayes' Bluff para tratar información incompleta**

[Fuente de los autores, apartados 3.3–3.4 y 4](https://poker.cs.ualberta.ca/publications/UAI05.pdf). El trabajo mantiene incertidumbre sobre estrategias y contempla manos cuyas cartas no se observan.

Tomaremos la distinción entre observaciones, hipótesis y confianza. Nuestra adaptación usará supuestos iniciales explícitos y actualizará posibles manos con acciones públicas; una subida no se traducirá en una mano rival conocida. Los datos sin cartas reveladas seguirán siendo observaciones incompletas.

El modelo multijugador, las probabilidades de acción y el muestreo conjunto deberán diseñarse y calibrarse. La primera versión no implementará el posterior completo sobre estrategias ni la respuesta bayesiana completa del artículo.

**W05 Data Biased Robust Counter Strategies para limitar la adaptación**

[Artículo y PDF, apartado 5.2](https://proceedings.mlr.press/v5/johanson09a.html). El método relaciona la confianza con observaciones de contextos comparables y limita cuánto depender de un modelo.

Tomaremos esa idea para graduar los ajustes frente a rivales. Como candidata de diseño, estudiaremos una curva acotada `confianza = c_max * n / (s + n)`; sus parámetros quedan sin fijar. `n` contará observaciones pertinentes, no cartas simuladas. Sin evidencia, mantendremos el comportamiento base.

Nuestra adaptación será una heurística inspirada en el trabajo, no el algoritmo DBR de resolución de juegos. No heredará sus garantías para dos jugadores. Tampoco acumularemos perfiles entre mesas si la identidad del rival no puede establecerse con la información oficial.

**W14 Pluribus como referencia del formato multijugador**

[Artículo original](https://doi.org/10.1126/science.aay2400) y [explicación técnica de los autores](https://ai.meta.com/blog/pluribus-first-ai-to-beat-pros-in-6-player-poker/). Es el referente elegido más cercano a seis jugadores No-Limit. Organiza la estrategia mediante abstracción, preparación previa y búsqueda durante el juego.

Tomaremos un conjunto manejable de acciones candidatas y la separación entre preparación y cálculo por jugada. Nuestra política inicial será heurística; no será el blueprint aprendido de Pluribus. Los tamaños de apuesta y la forma de mezclar acciones quedan por definir.

No reproduciremos ahora su entrenamiento ni su resolución de subjuegos. El artículo no publica el código completo y proporciona pseudocódigo suplementario. Además, Pluribus no adapta su estrategia a tendencias rivales: esa parte de nuestro diseño procederá de W03/W05.

**W23 AIVAT como referencia de evaluación**

[Artículo, introducción y conclusiones](https://arxiv.org/abs/1612.06915). AIVAT reduce varianza usando funciones de valor y probabilidades conocidas de una parte de las estrategias.

Tomaremos la exigencia de separar habilidad y azar al comparar versiones. Para la primera evaluación proponemos barajas predefinidas por mano, rotación de asientos, azar de políticas separado y lotes fijados de antemano. Este diseño experimental es nuestra propuesta; no es el estimador AIVAT.

Registraremos resultados e incertidumbre, eliminación, clasificación y latencia. El AIVAT completo queda pospuesto hasta disponer de probabilidades de política y funciones de valor adecuadas. Reutilizar semillas, por sí solo, no permite atribuirse su reducción de varianza ni sus garantías.

**Cómo encajan las cinco referencias**

La información pública y nuestra mano alimentarán un modelo incierto de los rivales. Ese modelo orientará el muestreo de cartas compatibles. La política comparará un número acotado de acciones y limitará sus ajustes según la evidencia. La evaluación externa al juego determinará si los cambios mejoran resultados y respetan el tiempo disponible.

Las cartas ocultas de una simulación servirán para calcular resultados, pero no se entregarán como información real a las políticas simuladas. Una futura estimación del valor de apuestas deberá respetar esa separación y contemplar los distintos pozos cuando haya stacks desiguales.

El primer objetivo será una base comprensible y medible. Un segundo nivel podrá incorporar modelos de respuesta para estimar el valor de apuestas. Aprender una estrategia mediante CFR/MCCFR o resolver subjuegos requerirá una decisión posterior y su propia evaluación.

**Qué dejamos fuera del alcance inicial y por qué**

| Familia o trabajo | Motivo de posposición | Condición para reconsiderarlo |
|---|---|---|
| CFR, MCCFR, CFR+, DCFR | Añaden entrenamiento y diseño de abstracciones | Necesidad concreta de aprender una política y presupuesto para medirla |
| Deep CFR, SD-CFR, NFSP, AlphaHoldem | Requieren datos de entrenamiento y validación del formato | Evidencia de que la base actual limita el rendimiento y recursos dimensionados |
| Libratus, DeepStack, búsqueda segura/anidada | Resolución avanzada, principalmente de duelos, con dependencias estratégicas | Una estrategia previa y un método de búsqueda compatible con varios jugadores |
| ReBeL y Student of Games | Mayor alcance de aprendizaje y búsqueda; resultados de póker de dos jugadores | Proyecto posterior de investigación con adaptación explícita |
| PokerBench y PokerSkill | Los escenarios o resultados con LLMs no validan nuestro torneo ni su latencia | Un uso y una evaluación concretos; no incorporamos llamadas a modelos ahora |
| GTO Wizard Benchmark, LBR y AV-AIVAT | Objetivos o requisitos distintos de la primera evaluación local | Evaluación específica de duelo, explotabilidad o detención estadística válida |

La evidencia primaria y el motivo por publicación están en el catálogo. Los artículos recientes de 2026 se registran como preprints y sus cifras no se usan como mediciones de nuestro hardware.

**Papel de las herramientas ya evaluadas**

PokerKit sigue elegido para simular reglas y partidas. OpenSpiel se conserva como referencia de algoritmos y posible entorno de experimentos; no constituye una política preentrenada para el torneo. Son infraestructura y no se cuentan como dos referentes adicionales de estrategia dentro de la selección principal.

**Límites y decisiones pendientes**

Ninguna combinación de estas ideas demuestra todavía que el bot vaya a ganar. Buena parte de la literatura seleccionada estudia partidas de dos jugadores o apuestas limitadas. Cada adaptación tendrá que contrastarse con cinco y seis jugadores, stacks variables y el objetivo de clasificación del torneo, que no equivale necesariamente a maximizar fichas por mano.

Antes de implementar quedan por concretar los rangos iniciales, agrupación de contextos, acciones candidatas, parámetros de confianza y diseño detallado de evaluación. La API determinará qué historial e identificadores podemos utilizar. El presupuesto interno inicial sigue siendo de dos segundos por decisión, sujeto a medición con la arena oficial.

Esta revisión elige referencias y extrae decisiones de diseño. No incorpora código académico al bot, pesos entrenados, servicios externos ni nuevas pruebas de juego.

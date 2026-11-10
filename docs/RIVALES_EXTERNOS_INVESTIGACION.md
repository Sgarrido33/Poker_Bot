# Investigación de rivales externos para Texas Hold’em No-Limit 5/6-max

**Fecha de revisión:** 28 de octubre de 2026  
**Contexto:** proyecto Python 3.12 basado en PokerKit y Eval7. Este documento distingue motores/simuladores de políticas que toman decisiones. La revisión no implica compatibilidad automática con la API de PokerKit ni valida rentabilidad.

## Recomendación

**Añadido de la segunda etapa:** se intentó NoRegrets y se inspeccionaron sus
fuentes/configuración; sin blueprint publicado ni bridge validado, y con el
intento de compilación portable bloqueado por el enlace GNU de Windows, no se
integró. El [registro de compilación](../research/noregrets_feasibility_20261028/RESULTS.md)
conserva la evidencia. Se añadió una adaptación de HonestPlayer de
PyPokerEngine como **baseline educativo independiente**, sin atribuirle fuerza
competitiva o entrenamiento. Su [procedencia, límites y pruebas](SEGUNDA_FAMILIA_EXTERNA.md)
y el [método nuevo](COMPETENCIA_SEGUNDA_METODO.md) complementan la investigación
original. Fullhouse sigue siendo el único rival externo aprendido integrado.

Para disponer ahora de un rival externo con una política aprendida y pesos publicados, la opción más concreta revisada es **Fullhouse `fullhouse-bot`**, usada como runtime aislado/adaptado y bajo su contrato documentado. El checkout local revisado está fijado en `e504793d480b1b975f25258d25939b45c6dbd5a4` dentro de `research/external_sources/fullhouse`. Incluye `data/deep_cfr_model.npz` (590.758 bytes) y `data/preflop_equity.npz` (2.160 bytes). El runtime es Deep CFR con un overlay manual de push/fold para stacks efectivos de hasta 12 BB; describirlo como Deep CFR puro en todas las situaciones sería inexacto.

La recomendación tiene dos límites importantes:

- Sus pesos se entrenaron y sirven con un encoder de 51 características y cinco acciones abstractas fijas. Integrar sus decisiones a PokerKit requiere conservar esa semántica y validar cuidadosamente la traducción a acciones legales del motor del proyecto.
- La licencia MIT del repositorio cubre el código propio identificado por el autor; excluye explícitamente `engine_vendored/`, cuyos términos son los del upstream. No se debe redistribuir ese motor vendorizado bajo la licencia MIT del bot. La licencia revisada no identifica por separado una licencia de los pesos del modelo; por ello no se afirma aquí una licencia independiente de pesos.

La siguiente opción de investigación es **NoRegrets**: declara NLHE de 2–6 jugadores y tiene licencia MIT en el repositorio público, pero el autor informa que los blueprints entrenados no se publican y se ofrecen bajo licencia comercial. Además, su runtime es Rust y no está integrado con PokerKit.

## Alternativas revisadas

| Proyecto | Qué es y modalidad declarada | Jugadores | Código/pesos y runtime | Licencia y ajuste al proyecto |
|---|---|---:|---|---|
| [Fullhouse `advitrocks9/fullhouse-bot`](https://github.com/advitrocks9/fullhouse-bot) | Bot Deep CFR para Texas Hold’em No-Limit. La política puntúa `FOLD`, `CHECK_CALL`, `BET_50`, `BET_POT` y `ALL_IN`. En runtime, un overlay manual utiliza un chart push/fold cuando el stack efectivo es ≤12 BB; el resto de las decisiones se sirve desde la red. | 6-max | Código Python y runtime NumPy; los pesos están incluidos en el checkout revisado como `data/deep_cfr_model.npz`; también incluye `preflop_equity.npz`. El README da un entorno de competición Python 3.10 con Eval7 y dependencias de su proyecto. | MIT para el código propio. La licencia excluye `engine_vendored/`; no atribuirle MIT. No se ha identificado una licencia separada y explícita para los pesos. Hay que portar/adaptar la interfaz y respetar el encoder/menú entrenados. |
| [NoRegrets `conorarmstrong/noregrets`](https://github.com/conorarmstrong/noregrets) | Implementación estilo Pluribus de MCCFR y resolución online de sub-juegos. Texas Hold’em No-Limit. | 2–6, con seis-max como objetivo principal | Código fuente Rust público; el README muestra cómo entrenar localmente un blueprint (p. ej. 200 millones de iteraciones; indica alrededor de una hora en 16 núcleos). El autor dice que los blueprints preentrenados no se publican en el repo y se ofrecen comercialmente. | La versión pública del repositorio indica MIT; la versión actual privada y los blueprints se ofrecen comercialmente. No es un artefacto Python ni plug-and-play. Es la mejor siguiente opción si se decide invertir en Rust y entrenamiento/integración. |
| [PyPokerEngine `ishikota/PyPokerEngine`](https://github.com/ishikota/PyPokerEngine) y su [HonestPlayer](https://github.com/ishikota/PyPokerEngine/blob/master/examples/players/honest_player.py) | PyPokerEngine es un engine/framework de simulación y callbacks, no un bot competitivo por sí mismo. `HonestPlayer` es un ejemplo de estrategia basada en estimación Monte Carlo de equity (`NB_SIMULATION = 1000`). Su código de ejemplo se limita a fold/call; no es una política entrenada ni un rival profesional. | El engine permite configurar varias sillas; la documentación ejemplifica una partida con tres jugadores. No atribuirle por ello una política 5/6-max fuerte. | Python; requiere adaptar el callback y el estado a la interfaz local. El README oficial solo declara soporte histórico de Python 2.7 y Python 3.5, de modo que Python 3.12 no está garantizado por el upstream. No se considera compatible de forma automática con PokerKit. | MIT, según el [LICENSE.md oficial](https://github.com/ishikota/PyPokerEngine/blob/master/LICENSE.md). Útil como ejemplo/baseline heurístico o para estudiar callbacks; no como modelo de rival fuerte. |
| [fedden/poker_ai](https://github.com/fedden/poker_ai) | Proyecto Python de investigación MCCFR y engine de poker en desarrollo. README presenta ejemplos de `ShortDeckPokerPlayer` con seis jugadores; eso es Short Deck, no evidencia de Hold’em estándar 6-max. Su roadmap conserva como trabajo pendiente un engine multijugador funcional. | Ejemplos multipersona, incluyendo Short Deck; no se confirmó bot estándar 5/6-max NLHE listo. | Código público, pero el repo fue archivado en julio de 2024. README indica Python ≥3.7; aun así no acredita una política 6-max estándar entrenada y lista para cargar. | GPL/copyleft según el LICENSE del proyecto. No recomendado como adversario inmediato para esta variante. |
| [EricSteinberger/PokerRL](https://github.com/EricSteinberger/PokerRL) | Framework para aprendizaje por refuerzo multiagente en poker, no un bot adversario preentrenado listo para enchufar. | Depende de los juegos/configuraciones del framework; no se verificó en este repaso una configuración concreta equivalente al estado/stack de la mesa local. | Código de framework de investigación; requiere montar experimento, entorno y entrenamiento. No hay en la fuente revisada evidencia de pesos listos para este proyecto. | MIT en el repo. Interesante para investigación propia, no para llenar la mesa ahora. |
| [CFR-NLHE-6max `dberweger2017/CFR-NLHE-6max`](https://github.com/dberweger2017/CFR-NLHE-6max) | Proyecto de investigación reproducible de CFR para Hold’em No-Limit; el README actual aclara que 6-max es una meta y que el resultado más sólido es en HU/3 jugadores. | Meta 6-max; evidencia reciente HU/3 jugadores | Código público y licencia MIT, pero el estado publicado no acredita un modelo seis-max listo que haya alcanzado su objetivo declarado. | No usar el nombre del repo o su historia para atribuirle compatibilidad o resultados 6-max actuales. |

## Qué afirma Fullhouse y qué no demuestra

La inspección local del archivo descargado confirmó 590.758 bytes, 146.694 parámetros numéricos finitos, entrada de 51 características y cinco salidas. Este checkpoint contiene una red de ventajas (`trunk_w0` 256×51, `adv_w1` 5×128), que el runtime transforma mediante regret matching; **no** contiene la red separada de estrategia media que también admite el código. La huella y las dimensiones están en [checkpoint_inspection.json](../results/competition_2026-10-28/checkpoint_inspection.json). Se ejecuta el artefacto efectivamente publicado, sin atribuirle convergencia a equilibrio ni afirmar que reprodujimos su entrenamiento.

El README del autor afirma que el bot terminó 15.º de 64 en la final del Fullhouse Hackathon 2026 y que clasificó 12.º entre más de 500 participantes. La captura del leaderboard está incluida en el repositorio. En esta investigación no se verificó el ranking mediante una fuente independiente; se presenta como afirmación del autor y captura incluida, no como validación independiente.

El README reporta para la línea v17 publicada `+22.41 bb/100` con intervalo de confianza del 95% `[+19.61, +25.21]` frente a su pool de bots local, además de `+19.89 bb/100` en un pool held-out. Esos son resultados del propio harness y no una prueba de superioridad general, de nivel profesional ni del rendimiento tras portar el agente a otro motor. El README distingue explícitamente esos resultados del único dato externo que cita: el puesto en la competencia.

El contrato de runtime documenta 51 características y cinco acciones. El propio repositorio advierte que las variantes con 52/56 características o con ocho acciones no se pueden cargar en el runtime v17 como si fueran un ajuste de configuración. La integración debe conservar la representación que corresponde a los pesos seleccionados y mapear apuestas mediante las reglas legales del motor anfitrión.

## Simulador, evaluador y rival

También se revisaron dos referencias que conviene excluir de una integración directa. [Slumbot2019](https://github.com/ericgjackson/slumbot2019) publica infraestructura CFR/MCCFR bajo MIT, requiere C++17 y documenta entrenamiento de checkpoints; su capacidad genérica multijugador no demuestra disponer del agente público de competición de seis jugadores. El [artículo del autor sobre Slumbot NL](https://cdn.aaai.org/ocs/ws/ws0979/7044-30516-1-PB.pdf) estudia duelo No-Limit. No lo trasladamos a esta mesa. [DeepStack-Leduc](https://github.com/lifrordi/DeepStack-Leduc) es la implementación de ejemplo de los autores para Leduc, con Lua/Torch; no es el agente de Hold’em que jugó contra profesionales, y no se verificó aquí una licencia de redistribución. Tampoco se localizó en las [publicaciones oficiales de Pluribus](https://ai.meta.com/blog/pluribus-first-ai-to-beat-pros-in-6-player-poker/) un agente completo descargable con blueprint y licencia para ejecutar localmente: el artículo, los métodos o las manos históricas no sustituyen a la política.

- **PokerKit** es un motor/reglas de juego; no aporta por sí solo una política estratégica rival.
- **Eval7** es una dependencia para evaluación/equity en este entorno; por sí sola no es un bot.
- **PyPokerEngine** aporta motor, callbacks y herramientas de simulación. `HonestPlayer` es un ejemplo básico de política escrito para ese API; no equivale a usar el motor como adversario 5/6-max ni a una integración ya probada con PokerKit.
- **Fullhouse** y **NoRegrets** sí son proyectos de agente. Fullhouse además tiene un runtime y pesos presentes en el checkout local revisado; NoRegrets ofrece código y entrenamiento, pero no publica sus blueprints entrenados según el autor.

No se atribuye compatibilidad con Limit, heads-up ni otras modalidades salvo donde las fuentes citadas lo declaran expresamente. La recomendación de Fullhouse se refiere a un rival experimental para mesas No-Limit de varios jugadores. El [método local](COMPETENCIA_METODO.md) y el informe de resultados de esta iteración deben consultarse por separado: los resultados del autor no son mediciones de PokerFight.

## Fuentes primarias

- Fullhouse: [repositorio](https://github.com/advitrocks9/fullhouse-bot), [README](https://github.com/advitrocks9/fullhouse-bot/blob/main/README.md), [runtime contract](https://github.com/advitrocks9/fullhouse-bot/blob/main/docs/research/runtime-contract.md), [LICENSE](https://github.com/advitrocks9/fullhouse-bot/blob/main/LICENSE).
- NoRegrets: [repositorio y README](https://github.com/conorarmstrong/noregrets), [LICENSE](https://github.com/conorarmstrong/noregrets/blob/main/LICENSE).
- PyPokerEngine: [repositorio y README](https://github.com/ishikota/PyPokerEngine), [HonestPlayer](https://github.com/ishikota/PyPokerEngine/blob/master/examples/players/honest_player.py), [LICENSE.md](https://github.com/ishikota/PyPokerEngine/blob/master/LICENSE.md).
- poker_ai: [repositorio y README](https://github.com/fedden/poker_ai), [LICENSE](https://github.com/fedden/poker_ai/blob/develop/LICENSE).
- PokerRL: [repositorio](https://github.com/EricSteinberger/PokerRL).
- CFR-NLHE-6max: [repositorio y estado actual del README](https://github.com/dberweger2017/CFR-NLHE-6max).

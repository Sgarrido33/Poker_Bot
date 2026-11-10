# Segunda familia externa: HonestPlayer

**Estado:** baseline externo educativo integrado. Esto no satisface la meta de
incorporar un segundo rival aprendido ni una política competitiva. Participa
como baseline en la [segunda batería local](COMPETENCIA_SEGUNDA_METODO.md);
su rendimiento medido se informa por separado y no acredita fuerza general.

## Decisión

Se integró una adaptación de `HonestPlayer`, el ejemplo incluido en
PyPokerEngine, como política `honest`. El ejemplo estima la probabilidad de
ganar por Monte Carlo (1,000 muestras) contra manos aleatorias y usa el umbral
`1 / player_num`: con una probabilidad igual o mayor hace check/call; por
debajo se retira. El código de origen cuenta los empates como victoria (`>=`).
La implementación conserva las 1,000 muestras por defecto y utiliza Eval7
para evaluar manos en PokerFight.

La adaptación no levanta PyPokerEngine ni importa su motor. Al empezar la mesa
registra el tamaño inicial por `table_id`, como lo hace upstream al comenzar
la partida. Si quedan menos asientos después de eliminaciones, sigue usando
ese tamaño inicial tanto para simular oponentes aleatorios como para el umbral
`1 / player_num`; una observación directa sin registro usa el tamaño que
contiene. No usa el costo del call, la posición, el historial ni apuestas
para decidir. Solo produce fold/check/call: no sube, modela rangos, aprende ni
tiene pesos entrenados. Por eso sirve para comparar integración y legalidad
2/5/6-max, no para representar nivel profesional.

## NoRegrets: por qué no se integró

**Estado actual:** el [adaptador general y la validación V3](../research/noregrets_training_20261028/RESULTS_VALIDATED_V3.md)
ya están completos. Hay perfiles propios de 2–6 jugadores, pero la cobertura
en sesiones con stacks variables todavía limita su fuerza. Los párrafos
siguientes conservan las etapas anteriores de investigación.

**Primera actualización posterior a la batería:** el bloqueo de compilación ya se
resolvió con Rust portable, rust-lld y LLVM-MinGW local. Se entrenaron y cargaron
blueprints técnicos de 1.000 iteraciones para 2/5/6 jugadores; hay perfiles de
5/6 con stack 800. Una extensión de prueba consulta distribuciones en aperturas
preflop y distingue lookups aprendidos de fallbacks. Dos entrenamientos 5-max
con la misma configuración produjeron tablas canónicas idénticas. Las recetas,
huellas y límites están en el [informe de desbloqueo](../research/noregrets_unlock_20261028/RESULTS.md).
La evidencia siguiente conserva el intento inicial y explica por qué esta
familia no participó en la segunda batería. El bridge de aperturas aún no es un
adaptador general de nuestras observaciones; los blueprints pequeños no tienen
fuerza validada ni sustituyen a Honest en los resultados históricos.

El README upstream presenta NoRegrets como una implementación Rust estilo
Pluribus para NLHE de 2–6 jugadores. Su repositorio público está bajo MIT, pero
declara que los blueprints entrenados no se publican y se ofrecen bajo licencia
comercial; también señala que el repositorio público va retrasado frente al
desarrollo privado. La documentación propone 200 millones de iteraciones
(aproximadamente una hora en 16 núcleos) para entrenar un blueprint 6-max.

Se inspeccionó el código/configuración publicado en el commit
`757f7692738069522195d2b486eec60a8b010c0c`. `Cargo.toml` requiere Cargo/Rust y
dependencias como rand 0.9, Rayon, DashMap, mimalloc, Clap, Serde y bincode.
`main.rs` expone `--train-seed` y `cfr.rs` inicializa un `SmallRng` por
iteración desde esa semilla; el entrenamiento actualiza mapas compartidos en
paralelo, por lo que el código no promete pesos bit a bit iguales con varios
workers. Incluye opción de checkpoint/reanudación. El CLI de juego es
interactivo; su `Policy` y formato de blueprint no son un protocolo externo
para PokerFight y no hay un blueprint publicado que se pueda cargar aquí.

El checkout local fijado ahora está disponible en
`research/external_sources/noregrets` en el commit
`757f7692738069522195d2b486eec60a8b010c0c`; la descarga se completó con
acceso de red autorizado. El primer intento de build encontró que no había
Rust ni linker instalado. Se instaló Rust **portable dentro del workspace**
(rustc 1.99.1, Cargo 1.99.1; no se modificó Rust global ni el PATH de usuario)
y se intentó compilar una prueba ligera con `CARGO_BUILD_JOBS=1`. Zig 0.13.0
está disponible, pero su linker no aporta las bibliotecas GNU de Windows que
Rust requiere. Tras adaptar el wrapper para omitir una opción GNU que Zig no
reconoce, el enlace de `proc-macro2` sigue fallando porque no encuentra
`gcc_eh`, `msvcrt` ni `gcc`. No se encontraron `link.exe`, `cl.exe`, `ld.exe` ni
`gcc.exe` en el PATH. Por tanto `cargo test regret_matching_math` no llega a
compilar el proyecto; no se ejecutó training smoke ni entrenamiento de un
blueprint. Los comandos, versiones, logs, commit y hashes del checkout están
en `research/noregrets_feasibility_20261028/`.

## Procedencia, licencia y hashes

- Proyecto upstream: [ishikota/PyPokerEngine](https://github.com/ishikota/PyPokerEngine).
- Commit fijado consultado: [`a52a048a15da276005eca4acae96fb6eeb4dc034`](https://github.com/ishikota/PyPokerEngine/commit/a52a048a15da276005eca4acae96fb6eeb4dc034).
- Fuente: `examples/players/honest_player.py`.
- Licencia upstream: MIT, Copyright (c) 2016 ishikota. El aviso se conserva
  junto al snapshot de fuente.
- SHA256 del snapshot formateado en
  `research/external_sources/pypokerengine_honest/`:
  - `honest_player.py`: `156fba1dc68d4208b48f9704d4ffcfcd21e4faaaa00d14f0ac2db2721e32ee43`
  - `LICENSE.md`: `2bf5fdb299f17836b772b266f6eb9d142c67d157c94da9bc365fbf30f5fcf5fe`
- `SOURCE.json` guarda commit, ruta, licencia y hashes; `verify_honest()` los
  comprueba antes de construir el rival.

No se redistribuye un modelo ni pesos. La integración de runtime es una
adaptación independiente: conserva el número de simulaciones, la comparación
de scores con empates como victoria y la regla `win_rate >= 1 / player_num`,
pero sustituye el evaluador y el protocolo callback por Eval7 y
`Observation`/`Action` de PokerFight.

## Fidelidad: resultado desfavorable de la comprobación adicional

Durante la ejecución registrada, sin cambiar políticas ni consultar contrastes,
se descargó además el repositorio completo fijado y se compararon los
evaluadores. **La adaptación no reproduce exactamente el runtime upstream.**
En 1.000 deals completos por formato, los conjuntos de ganadores difirieron en
51 casos de duelo, 62 de cinco jugadores y 78 de seis. En una mesa pública de
escalera real del mismo palo, Eval7 empata todos los asientos y el evaluador
antiguo incorpora diferencias de cartas propias en el desempate. Son diferencias
de evaluación de deals, **no porcentajes de decisiones distintas del bot**.

La regla de decisión sí coincidió en 12/12 casos con el estimador controlado:
debajo, igual y encima de 1/n, conservando el número inicial tras eliminaciones.
Esto comprueba el umbral y el callback; no comprueba paridad del Monte Carlo.
La sustitución por Eval7 ya estaba declarada en el registro antes de jugar. Los
resultados de la batería corresponden a **HonestPlayer adaptado con Eval7**,
no al agente original sin cambios. No se corrige ni reemplaza a mitad del lote.

El [informe técnico](../research/honest_parity_20261028/SUMMARY.md),
[datos y hashes](../research/honest_parity_20261028/RESULTS.json) y
[script reproducible](../research/honest_parity_20261028/compare_upstream.py)
conservan todos los casos y las diferencias. Los 3.006 deals sintéticos y los
12 casos con estimador controlado son comprobaciones técnicas, no manos de
evaluación ni evidencia de fuerza. La muestra no cubre exhaustivamente las manos.

El snapshot pequeño del paquete conserva el código de ejemplo con cambios de
espaciado y saltos de línea, sin cambios de lógica; sus hashes son locales, no
los del blob Git original. El checkout completo original en
`research/external_sources/pypokerengine_reference` y sus huellas se conservan
en el informe de paridad. La licencia mantiene el mismo contenido.
La [comprobación de formato](../research/honest_parity_20261028/source_format_audit.json)
confirma AST idéntico para el ejemplo e igualdad del texto de licencia tras
normalizar saltos de línea.

## Comprobaciones

`tests/test_second_external_opponent.py` comprueba la procedencia y los hashes,
el empate y la igualdad del umbral, tamaño inicial conservado tras
eliminaciones, RNG determinista/aislado, ausencia de acceso a estado privado
del motor y partidas con 2, 5 y 6 jugadores. Estas son pruebas de adaptación
y reglas; no miden fuerza de juego.

## Fuentes primarias revisadas

- PyPokerEngine: [HonestPlayer](https://github.com/ishikota/PyPokerEngine/blob/master/examples/players/honest_player.py), [estimador Monte Carlo](https://github.com/ishikota/PyPokerEngine/blob/master/pypokerengine/utils/card_utils.py), [licencia MIT](https://github.com/ishikota/PyPokerEngine/blob/master/LICENSE.md).
- NoRegrets: [README/licencia/entrenamiento](https://github.com/conorarmstrong/noregrets/tree/757f7692738069522195d2b486eec60a8b010c0c), [Cargo.toml](https://github.com/conorarmstrong/noregrets/blob/757f7692738069522195d2b486eec60a8b010c0c/Cargo.toml), [configuración CLI](https://github.com/conorarmstrong/noregrets/blob/757f7692738069522195d2b486eec60a8b010c0c/src/main.rs), [trainer MCCFR](https://github.com/conorarmstrong/noregrets/blob/757f7692738069522195d2b486eec60a8b010c0c/src/cfr.rs).

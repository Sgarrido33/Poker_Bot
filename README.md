# PokerFight 2026 · Bot de Texas Hold'em No-Limit

Bot autónomo que juega No-Limit Texas Hold'em en la arena de PokerFight 2026. Versión entregada: **política `v2`**. Está escrito en Python 3.12, usa [Eval7](https://pypi.org/project/eval7/) para evaluar manos y [PokerKit](https://pypi.org/project/pokerkit/) para simular partidas locales. No usa LLM ni servicios externos: todas las decisiones se calculan en la máquina del equipo y tardan menos de medio segundo, cuando el plazo es de 5 segundos.

## Cómo ejecutarlo

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:POKERFIGHT_TOKEN = "<token del equipo>"
.\.venv\Scripts\python.exe -m pokerfight.official -addr HOST:PUERTO --journal torneo.jsonl
```

- El token se lee de `POKERFIGHT_TOKEN` (o `-token`). Nunca se escribe en el repositorio y la bitácora lo oculta.
- Si se corta la conexión, el cliente vuelve a conectarse con el mismo token y retoma su silla. Mantiene el socket abierto durante el silencio entre rondas.
- Pruebas: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Mecánica de juego

Cada vez que la mesa envía `solicitar_accion`, el bot sigue cuatro pasos.

**1. Reconstruye el estado.** El cliente ([`official.py`](pokerfight/official.py)) traduce los mensajes JSON del protocolo a una observación interna con la información pública: posiciones, fichas, apuestas de la ronda, pozo, historial y board. A partir del historial reconstruye ciegas, calls y all-in cortos. También calcula los pozos laterales en los que el bot puede ganar.

**2. Estima los rangos rivales.** Cada rival empieza con todas las combinaciones posibles de cartas, y sus acciones públicas ajustan los pesos ([`frozen_v2/equity.py`](pokerfight/frozen_v2/equity.py)). Una subida o un call preflop favorecen las manos fuertes. Postflop, la última acción del rival pesa según la categoría de mano que formaría con el board. Ninguna combinación se descarta del todo. Un modelo de rivales por mesa ([`frozen_v2/opponents.py`](pokerfight/frozen_v2/opponents.py)) cuenta los folds, las acciones pasivas y las subidas de cada alias por calle. Con eso ajusta, con un límite de pocos puntos, el margen para pagar: paga más ligero contra rivales agresivos y exige más contra rivales pasivos. La confianza máxima es 0,35 y crece con las observaciones.

**3. Calcula la equity.** Hace una simulación Monte Carlo de 4.000 repartos con Eval7, sacando las manos rivales de esos rangos ponderados, con un presupuesto de 1,6 s. Para decidir se usa una **equity conservadora**: la estimación menos su error estándar.

**4. Elige la acción** ([`frozen_v2/strategy.py`](pokerfight/frozen_v2/strategy.py)):

| Situación | Regla |
|---|---|
| Preflop sin subidas | Abre según una tabla por posición (UTG…BB) a 2,5 bb más 1 bb por limper. Con 12 bb o menos, las manos fuertes (`TT+`, `AQs+`, `AKo`) van all-in. |
| Preflop con subida | `QQ+` y `AK` resuben (3× o apuesta + 0,75 del pozo) si la equity supera el precio por 12 puntos. El resto defiende según tabla y nunca paga más de 8 bb si no es premium. |
| Call que deja all-in | La tabla no veta: se paga si la equity conservadora supera las pot odds. Esta es la corrección que define a `v2`. |
| Postflop con mano fuerte | Sube por valor si la equity conservadora es al menos 0,64 contra un rival (0,55 contra varios) y supera el precio por 15 puntos. Apuesta medio pozo, o 3/4 de pozo con equity ≥ 0,80. |
| Postflop, pagar o retirarse | Paga si la equity supera las pot odds más un margen por calle (flop 4,5 %, turn 2,5 %, river 0 %), ajustado por el modelo del rival. |
| Sin coste | Pasa (check). |

El bot **no hace faroles**. Juega por valor y por precio, que es el estilo más estable contra bots que pagan mucho. Los tamaños se ajustan a lo legal y a lo que el rival puede pagar. El monto enviado es el total de la ronda, como pide el protocolo.

**Seguridad.** La decisión corre en un proceso hijo supervisado ([`supervision.py`](pokerfight/supervision.py), [`search_worker.py`](pokerfight/search_worker.py)). Si falla o pasa de 3 s, el bot juega el `check`/`fold` seguro y reinicia ese proceso. Solo envía acciones de `acciones_validas` y nunca responde un turno que ya venció.

## Lógica de creación

**Diseño inicial.** Empezamos estudiando 33 publicaciones y bots anteriores (CFR y Deep CFR, Libratus, DeepStack, Pluribus, y bots de equity con modelado de rivales). Concluimos que sin un blueprint entrenado para 5–6 jugadores con stacks variables, la opción más fiable era **equity contra rangos ponderados con reglas transparentes**. Cada decisión deja una razón legible (por ejemplo, `call:equity_covers_price_and_margin`), así que se puede auditar mano por mano.

**Mejora por experimentos, no por intuición.** Cada idea se implementó como una candidata separada. El control `v2` quedó congelado byte a byte en [`pokerfight/frozen_v2/`](pokerfight/frozen_v2/) con huellas SHA-256. Así cada comparación se hacía siempre contra el mismo bot.

| Candidata | Idea | Resultado |
|---|---|---|
| v1 → **v2** | Corregir calls all-in preflop que la tabla rechazaba aunque el precio fuera bueno | Promovida |
| v3 | Aperturas limpias con ≤ 8 bb | −0,069 bb/mano; descartada |
| v4 / v4rb / v5 / v7 | Búsqueda de acciones con respuestas hipotéticas de los rivales y resubidas | Más fichas en algunas mesas, pero más eliminaciones tempranas |
| v6 | Variante surgida del diagnóstico de eliminaciones tempranas | Menos top 6 que v2 |
| v8 / v8d | Push/fold de equilibrio calculado (≤ 15 bb) | Más fichas contra rivales externos, pero entre 7 y 25 puntos más de eliminación temprana |
| v9 | Rangos postflop que acumulan evidencia por calle | Empate con v2 (275 vs 273 top 6 en 384 torneos) |

**El criterio fue el formato real.** La métrica principal era **clasificar al top 6** en la clasificatoria: 10 rondas, 10.000 fichas, ciegas 50/100, fichas acumuladas y eliminación. Las fichas medias quedaban en segundo lugar. Construimos un simulador del torneo completo con rivales propios (tight, loose, agresivos, copias de v2) y dos familias externas: Fullhouse (Deep CFR, con código y pesos fijados por SHA-256) y HonestPlayer. Antes de mirar los resultados registramos los criterios de promoción, las semillas y los tamaños de muestra. Una candidata solo reemplazaba a v2 si mejoraba de forma demostrada sin aumentar las eliminaciones. **Ninguna lo logró**, así que se entrega v2. En total se jugaron **más de 1.000 torneos y 600.000 manos simuladas**.

**Validación final (21 de noviembre de 2026).**

- **Servidor de pruebas oficial:** 2.033 manos y 3.825 jugadas contra otros equipos y bots de la organización. Hubo 0 timeouts, 0 respuestas de respaldo de la política y 0 errores del servidor. La respuesta más lenta tardó 400 ms.
- **Bots del kit oficial** (estadístico, espía, bandido, darwin, base, conservador): 242 mesas pareadas de 50 manos contra v9, con las condiciones de la clasificatoria. v2 terminó con **14.336 fichas de media** partiendo de 10.000, por encima de todos los bots del kit (el mejor, darwin, sacó 12.913). La diferencia con v9 no fue significativa (−520 ± 1.144 fichas; eliminaciones 66 vs 57, p = 0,40). En esas mesas hubo 45.276 decisiones sin ninguna respuesta tardía.

## Para el premio sorpresa

- **Método científico.** Preregistramos los criterios de promoción y usamos experimentos pareados: mismas barajas, asientos rotados y semillas fijas. Los intervalos se ajustaron por agrupación. Para elegir solo contaron datos nuevos, nunca los que ya se habían usado para diseñar.
- **Resultados negativos documentados.** Ocho candidatas más sofisticadas (búsqueda, equilibrio push/fold, rangos postflop) no superaron a v2, y lo dejamos registrado. Entregamos la versión que mejor resistió la evidencia, no la más compleja.
- **Juego limpio.** El bot usa solo información pública y sus propias cartas. No hay intervención manual, colusión ni explotación de fallas de la arena. Encontramos un caso borde del protocolo: con una ciega grande corta all-in, la ciega nominal supera la apuesta real. En ese caso el bot juega la acción segura en vez de interpretarlo mal.
- **Explicable.** Cada jugada registra su motivo, su equity y su latencia en la bitácora JSONL. Eso permite revisar después de la partida por qué ganó o perdió cada mano.

## Estructura

```
pokerfight/
  official.py        cliente TCP del protocolo PokerFight (saludo, turnos, reconexión, bitácora)
  supervision.py     proceso supervisado con plazo y respaldo seguro
  search_worker.py   proceso hijo que calcula cada decisión
  arena.py           adaptador de políticas y simulador local con PokerKit
  controls.py        envoltorio de la política v2 congelada
  frozen_v2/         política v2: rangos, modelo de rivales, equity y selección de acciones
  strategy.py, domain.py, equity.py, opponents.py, preflop.py, cards.py   tipos y utilidades compartidas
tests/               pruebas del protocolo, reconexión y observación supervisada
examples/            observación de ejemplo
```

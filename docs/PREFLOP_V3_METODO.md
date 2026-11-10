# Iteración preflop corta del 28 de octubre de 2026

Se conserva Python 3.12, Eval7 y PokerKit. La candidata `v3` cambia solamente aperturas preflop sin calls ni subidas previas, cuando el máximo stack disputable es de hasta ocho ciegas grandes. La decisión de promoverla depende del [protocolo guardado antes del piloto](../results/shortstack_2026-10-28/protocol.json). Los resultados se publican en [PREFLOP_V3_RESULTADOS.md](PREFLOP_V3_RESULTADOS.md).

## Control y diagnóstico

La suite inicial de 29 pruebas pasó con el `.venv` existente. Esta carpeta no es un repositorio Git; se conserva una instantánea explícita del control. `pokerfight/frozen_v2/` contiene copias de estrategia, contrato, cartas, rangos, modelo y muestreo anteriores a los cambios. El manifiesto verifica sus SHA-256. El adaptador convierte la observación pública a ese contrato y devuelve la acción y equity al contrato común. No entra código estratégico vivo en el cálculo del control. `v1` usa también esta instantánea, con su selección anterior.

Se registraron diez manos completas de v2, cubriendo 2–6 jugadores, antes de cambiar la fábrica de políticas. Una prueba vuelve a obtener exactamente acciones y fichas. Otra modifica rangos, estimador y modelo vivos y comprueba que v2 no cambia. Las dependencias binarias externas siguen fijadas por requirements; el manifiesto no sustituye su instalación reproducible.

Los [casos públicos previos](../results/shortstack_2026-10-28/diagnosis_before.json) se ejecutaron antes de escribir las tablas de v3. Ejemplos: T9s UTG a 4 bb abre a 2,5 bb; K8o en duelo a 8 bb abre a 2,5 bb; AA con 100 bb contra un único rival con 4 bb también abre a 2,5 bb. Son hipótesis de mejora del compromiso, no demostraciones de EV negativo. Q7o en BB se retira ante una subida mínima; la estimación de showdown y un precio barato, por sí solos, no prueban que pagar sea rentable con apuestas futuras. Esa defensa queda pendiente y se conserva igual.

Se reproducen precio caro, precio barato, retirada, posición y stacks desiguales. La corrección de v2 para un call all-in barato tiene prioridad sobre las tablas nuevas. Se mantiene la retirada si ese precio no se cubre. No se usan cartas ocultas de los rivales en las observaciones.

| Caso reproducido, 4 000 muestras | Posición / rivales activos | Efectivo | Precio del call | Equity estimada v2 | Acción v2 |
|---|---|---:|---:|---:|---|
| T9s, apertura | UTG / 5 | 4 bb | 40,0 % | 44,8 % | Subir a 2,5 bb |
| K8o, duelo | BTN / 1 | 8 bb | 25,0 % | 56,0 % | Subir a 2,5 bb |
| AA, héroe profundo | SB / 1 | 4 bb | 25,0 % | 84,5 % | Subir a 2,5 bb |
| Q7o, defensa barata | BB / 1 | 8 bb | 22,2 % | 41,0 % | Retirarse por rango |
| Q7o, defensa cara | BB / 1 | 8 bb | 41,4 % | 41,0 % | Retirarse |
| 72o, call all-in de una ficha | BTN / 1 | 0,51 bb | 0,98 % | 33,0 % | Pagar |

La equity es la fracción de los pozos elegibles después de **solo el call propio**. En una apertura no incorpora las contribuciones futuras de jugadores que aún no pusieron fichas: no debe interpretarse como equity contra cinco calls a un all-in, aunque se muestreen cinco manos rivales. Esto refuerza la decisión de no convertir automáticamente equity favorable en un push. Las tablas nuevas son una hipótesis explícita sobre selección/compromiso que debe medirse en partidas completas. Los errores estándar de estos casos solo describen el muestreo bajo los rangos supuestos.

## Cambio acotado

El stack efectivo se define como `min(stack propio + apuesta propia en la calle, máximo stack rival + su apuesta en la calle) / bb`. Incluye las ciegas ya aportadas; no se decide con las fichas restantes solamente. El máximo rival evita que un tercer jugador casi eliminado convierta una confrontación profunda en una situación corta. Esta definición describe cobertura máxima, no elimina la necesidad de calcular pozos laterales al pagar.

En una apertura limpia, los rivales activos son los que todavía deben actuar: los anteriores solo pudieron retirarse. `shortstack.py` contiene dos tablas escritas a mano, hasta 5 bb y entre 5 y 8 bb, con cuatro grupos de rivales pendientes (1, 2, 3, 4–5). Son más selectivas al aumentar la cobertura o los rivales. Se empuja el monto efectivo si la mano pertenece al rango y se declina en otro caso. Se respetan los mínimos legales y las devoluciones del motor.

No son tablas Nash ni GTO. El muestreo conserva los rangos y el cálculo de showdown de v2; no estima fold equity ni el EV de empujar. No se cambia la defensa contra subidas, el juego con limpers ni el postflop. Una mano que llega a esos contextos usa v2. Los resultados de postflop sí pueden variar como consecuencia de decisiones preflop diferentes.

## Experimento fijado

Todos los lotes anteriores, incluidos los llamados `holdout`, son datos de desarrollo. Los namespaces nuevos del protocolo son `pf-preflop-short-20261028-a1:pilot:01`, `:validation:01` y `:production:01`. Se incorporan realmente al cálculo de semillas; otra carpeta por sí sola no cambia las barajas.

| Etapa | Jugadores | Stack inicial | Bloques por celda | Manos/bloque/asiento | Muestras v2/v3 |
|---|---|---|---:|---:|---:|
| Piloto | 2, 3, 4, 5, 6 | 4, 8, 12, 20 bb | 2 | 1 | 256 |
| Validación principal | 5, 6 | 4, 8, 12, 20 bb | 12 | 2 | 512 |
| Validación secundaria | 2, 3, 4 | 4, 8, 12, 20 bb | 4 | 2 | 512 |
| Comprobación predeterminada | 5, 6 | 4, 8 bb | 2 | 1 | 4 000 |

El piloto y la validación tienen tres composiciones: `selective` (tag, tag, lag), `pressure` (pressure, lag, tag) y `copies_v2` (solo copias congeladas de v2). Se repiten hasta llenar la mesa. La comprobación de 4 000 muestras usa pressure. Los rivales de reglas usan 256 muestras postflop. Ambas variantes reciben el mismo presupuesto cooperativo de 1 600 ms y la misma cuota de muestras en cada fase. Se registran muestras parciales y respaldos. La cuota de 512 es para evaluación; la configuración predeterminada sigue solicitando 4 000.

Cada par tiene las mismas barajas, semillas de políticas y composición rival. El héroe rota por todos los asientos, preservando el orden circular de los otros jugadores. Las rotaciones de un bloque no son independientes. El bootstrap por celda remuestrea bloques completos (5 000 repeticiones); el agregado principal remuestrea dentro de cada celda y les da el mismo peso. Las celdas usan semillas disjuntas. Los intervalos son descriptivos, con pocos bloques, y no están corregidos por comparaciones múltiples.

Con fichas conservadas se empieza a 8 bb, sin ante, y se duplican las ciegas cada diez manos. El piloto fija un grupo y hasta 24 manos contra pressure y copias; la validación fija tres grupos y hasta 30 manos contra las tres composiciones. Cada grupo rota todos los asientos. Se completan los límites o la mesa termina con un superviviente; no se detiene por el resultado del héroe. Se agrupan las rotaciones al estimar incertidumbre de fichas finales. Si divergen las eliminaciones, también pueden divergir los repartos posteriores por el cambio de jugadores activos, aunque se mantenga la semilla por número de mano.

El criterio principal considera solamente 5/6 jugadores y 4/8 bb: intervalo del 95 % de la diferencia de bb/mano estrictamente por encima de cero. Además, la diferencia media de cada formato debe ser no negativa y ninguna celda principal puede tener todo su intervalo por debajo de −0,25 bb/mano. El intervalo agregado de fichas finales de sesiones, expresadas en stacks iniciales, debe tener límite inferior no negativo. Se requieren cero acciones inválidas, propuestas ilegales recuperadas, respaldos o decisiones del héroe de más de dos segundos en todas las fases. Si falla un criterio o hay incertidumbre, se conserva v2. No se ajustan parámetros entre piloto y validación.

## Registros y reproducción

Cada celda conserva JSON de resultados y JSONL de todas las manos de ambas variantes, incluidas observaciones públicas del héroe. Hay ganancias en fichas, busts con reposición, latencia de ambas variantes, conteos y resultados por posición, rivales, precio, profundidad efectiva y tipo de situación. Cada mano se atribuye una sola vez a su primera decisión preflop; walks y all-ins forzados sin decisión tienen una categoría propia. Estas asociaciones no son estimaciones causales del EV de una acción.

Una acción inválida devuelta o rechazada por PokerKit aborta el lote; un reporte completo registra cero. Se contabilizan además los respaldos que pudieron ocultar una propuesta ilegal. Las trazas permiten revisar las razones y el número real de muestras. Las sesiones conservan parámetros, semillas, eliminaciones y contexto del héroe hasta que sale de la mesa.

```powershell
# Reanudar exactamente el protocolo existente; se rechaza otro código/entorno
.\.venv\Scripts\python.exe -m pokerfight.shortstack_experiment --root results/shortstack_2026-10-28 --phase pilot
.\.venv\Scripts\python.exe -m pokerfight.shortstack_experiment --root results/shortstack_2026-10-28 --phase validation
.\.venv\Scripts\python.exe -m pokerfight.shortstack_experiment --root results/shortstack_2026-10-28 --phase production

# Registrar otra campaña con barajas nuevas antes de medir
.\.venv\Scripts\python.exe -m pokerfight.shortstack_experiment --root results/otro_experimento --init identificador-nuevo-unico

# Celda individual: ocho bb, comparación pareada y todos los asientos
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v3 --baseline v2 --players 6 --starting-stack 800 --blocks 12 --hands-per-block 2 --samples 512 --experiment-id ejemplo-nuevo --opponents pressure lag tag --trace results/ejemplo.jsonl --output results/ejemplo.json

# Decisión aislada de la candidata; decide y serve siguen usando v2 por defecto
.\.venv\Scripts\python.exe -m pokerfight decide examples/all_in_price.json --policy v3
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Reconstruir una sesión completa de eliminación, ambas variantes
.\.venv\Scripts\python.exe -m scripts.replay_shortstack_session results/shortstack_2026-10-28/validation/session_selective_6p_g0_r0.json

# Regenerar CSV, auditoría, casos reproducidos y documento de resultados
.\.venv\Scripts\python.exe -m scripts.report_shortstack --root results/shortstack_2026-10-28
```

El protocolo se crea una sola vez, antes de medir, y fija también la huella de todo el paquete Python, incluido el control. Las fases son reanudables. Los registros anteriores ya examinados no recuperan condición de validación reservada por volver a ejecutarlos. Para repetir cálculos desde cero con las mismas semillas puede copiarse únicamente el protocolo a una carpeta vacía; para nueva evidencia se registra otro identificador.

Después de desarrollar v4, la huella del paquete activo cambia. Para reproducir esta campaña con su código original, ejecutar desde `research/policy_snapshots/pre_v4_20261028`, usando `../../../.venv/Scripts/python.exe` y la ruta `../../../results/shortstack_2026-10-28` como `--root`. Allí se conservaron los módulos y scripts previos; `environment.json` registra su huella. Otra opción es restaurar ese paquete en un checkout separado. No se debe editar el protocolo para hacer pasar una huella distinta.

La latencia incluye preparación, muestreo y selección; en v2 añade la conversión del adaptador. Excluye arranque del proceso, transporte y API. El límite es cooperativo. Las tasas de bust con reposición se distinguen de eliminaciones reales de sesión. Ganar una mesa local no mide clasificación al torneo. La API oficial, reasignación de mesas, ICM y formato completo siguen pendientes.

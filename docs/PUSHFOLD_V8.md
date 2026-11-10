# v8: rangos push/fold de equilibrio calculados

29 de octubre de 2026. **v8 es candidata; v2 sigue predeterminada hasta que el
usuario decida.** Las reglas oficiales siguen sin publicarse; se usan los mismos
supuestos locales que en la tercera evaluación: 800 fichas, ciegas 50/100, sin
ante ni recompras, sesiones de hasta 128 manos.

## Por qué este cambio

Con 800 fichas y ciegas de 100, cada jugador empieza con **8 bb**. A esa
profundidad casi todo el valor se decide preflop entre empujar o retirarse.
Las candidatas v3–v7 atacaron ese régimen con tablas escritas a mano (v3) o con
búsqueda Monte Carlo que valoraba respuestas aproximadas (v4–v7). Ninguna superó
a v2 en sesiones. Nunca se habían usado rangos de **equilibrio calculados**,
que son la solución estándar del push/fold. Los documentos anteriores lo decían
explícitamente: "no son tablas Nash".

## Qué hace

1. [`scripts/build_pushfold_equity.py`](../scripts/build_pushfold_equity.py)
   precalcula la equity all-in de las 169×169 clases de mano. Cada celda
   promedia todos los pares de combinaciones compatibles, con eliminación de
   cartas, y 4.000 tableros aleatorios. Tarda unos 45 s con 12 procesos.
   Comprobaciones: AA–KK 81,8 %, AKo–QQ 42,4 % y 72o–AA 11,8 %.
2. [`pokerfight/pushfold.py`](../pokerfight/pushfold.py) resuelve el juego
   push/fold en chip-EV. Usa iteración de mejor respuesta promediada (400
   iteraciones) para stacks de 1 a 20 bb en pasos de 0,5. Un mismo juego de seis
   posiciones cubre cualquier tamaño de mesa: quien abre con *k* jugadores detrás
   enfrenta las mismas ciegas aunque otros se hayan retirado antes.
   [`scripts/build_pushfold_charts.py`](../scripts/build_pushfold_charts.py)
   genera `pokerfight/data/pushfold_charts.json` en unos 30 s.
3. [`pokerfight/pushfold_bot.py`](../pokerfight/pushfold_bot.py) juega con
   estas tablas cuando el stack efectivo es de **15 bb o menos**:
   - Bote sin abrir: empuja si la frecuencia de equilibrio es ≥ 0,5; si no, se
     retira.
   - Un único raise sin calls: si el rival ya está all-in, paga o se retira según
     el rango de call. Si el raise no es all-in, re-empuja con ese mismo rango o
     se retira.
   - En los demás casos decide la v2 congelada: botes con limpers, varios raises,
     más de 15 bb y todo el postflop. Un error en las tablas también cae en v2.

Validación del solver: en duelo a 10 bb la SB empuja el 58,1 % y la BB paga el
37,3 %, que coincide con las tablas chip-EV publicadas (~58 % / ~37 %).

| Stack | UTG | HJ | CO | BTN | SB | BB paga vs SB | BB paga vs BTN |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 bb | 26,6 % | 29,7 % | 33,5 % | 40,9 % | 71,8 % | 62,1 % | 47,2 % |
| 8 bb | 17,6 % | 21,7 % | 28,4 % | 34,2 % | 61,9 % | 45,3 % | 28,7 % |
| 10 bb | 14,5 % | 18,7 % | 25,2 % | 31,9 % | 58,1 % | 37,3 % | 23,2 % |
| 15 bb | 10,0 % | 12,7 % | 17,3 % | 27,6 % | 45,3 % | 28,7 % | 16,0 % |

**Aproximaciones aceptadas:**
- Chip-EV, sin ICM ni riesgo de eliminación.
- Stacks efectivos iguales para todos.
- Un solo caller: los jugadores posteriores no hacen overcall.
- Eliminación de cartas solo entre las dos manos enfrentadas.
- El re-empuje contra un open pequeño usa el rango de call contra un shove, que
  es conservador.

Las tablas no se adaptan al rival.

## Resultados

[`scripts/v8_sessions.py`](../scripts/v8_sessions.py) juega sesiones pareadas
con las mismas barajas, semillas, asientos y rivales para cada brazo, rotando al
héroe por todos los asientos, en mesas de 5 y 6 jugadores. La unidad
independiente es el grupo. Se informa la diferencia media entre grupos con un
bootstrap percentil del 95 % (10.000 réplicas), sin corrección por
comparaciones múltiples. Se trata de una **batería nueva y más pequeña que la
tercera evaluación**, sin protocolo registrado de antemano. Sus intervalos son
descriptivos.

### Batería 1 (`v8-pushfold-sessions-20261029-01`)

| Escenario | Grupos | Mesas/brazo | Fichas finales v8 − v2 | Victorias | Elim. a 24 | Elim. a 128 |
|---|---:|---:|---|---|---|---|
| `external_diverse` (principal) | 80 | 440 | **+337** [+126; +540] (1.101 vs 765) | **+10,2 pp** [+5,8; +14,5] | +3,3 pp [−2,1; +8,6] | **−5,6 pp** [−10,8; −0,2] |
| `pressure` | 40 | 220 | **+1.133** [+867; +1.405] | **+21,8 pp** | **−19,0 pp** | **−31,5 pp** |
| `copies_v2` | 40 | 220 | −16 [−213; +183] | +5,3 pp [−0,3; +10,9] | **+24,8 pp** [+19,3; +30,4] | **+6,3 pp** [+0,9; +11,5] |

Hubo cero fallbacks y cero errores de conservación de fichas. En el escenario
principal, v8 mejoró la media de fichas en ambos formatos: 995 vs 734 con cinco
jugadores y 1.208 vs 795 con seis.

**Resultado desfavorable:** en una mesa formada solo por copias de v2, que
empujan muy tight (TT+, AQs+, AKo), la diferencia de fichas de v8 no fue
concluyente, pero se eliminó antes con mucha más frecuencia. Este lote no
demuestra equivalencia de fichas ni aísla el efecto de pagar frente al de
empujar. El rango propio de shove de v2 tampoco determina su rango de call
frente a nuestras apuestas. Si la métrica oficial premia supervivencia, este
costo importa. La [evaluación posterior de v8d](VALIDACION_V8D_RESULTADOS.md)
separa componentes y compara otras composiciones selectivas.

### Réplica con semillas nuevas (`v8-replication-20261029-02`)

Se jugó después de ver la batería 1, con barajas nuevas, `external_diverse`,
40 grupos por formato (80 en total) y tres brazos. v8b añade una sola regla:
empujar sobre limpers con el rango de call de la posición del primer limper.

| Contraste | Fichas finales | Victorias | Elim. a 24 | Elim. a 128 |
|---|---|---|---|---|
| v8 − v2 | **+456** [+206; +709] (1.231 vs 775) | **+12,0 pp** [+6,1; +17,9] | +2,7 pp [−1,9; +7,1] | **−9,0 pp** [−14,9; −3,0] |
| v8b − v2 | **+462** [+210; +716] | **+11,7 pp** | +2,8 pp | **−9,3 pp** |
| v8b − v8 | +6 [−58; +70] | −0,3 pp | +0,1 pp | −0,3 pp |

La réplica repite la señal favorable de v8 sobre v2 en fichas, victorias y
eliminación a 128 manos, dentro de una campaña exploratoria. El ligero aumento de eliminación temprana vuelve a
aparecer, pero su intervalo incluye cero. v8b no se distingue de v8: la
situación con limpers es poco frecuente. Se conserva como variante experimental
y no se recomienda.

### v8c: calls confirmados (`v8c-20261029-03`)

Hipótesis: la eliminación temprana en `copies_v2` venía de pagar shoves tight
con rangos de equilibrio. v8c paga solo si la tabla y la equity de v2 frente al
rango modelado del rival están de acuerdo. Se jugaron 12 grupos por formato en
`copies_v2` y en `external_diverse`, contrastando v8c con v8.

| Escenario | Fichas finales | Victorias | Elim. a 24 | Elim. a 128 |
|---|---|---|---|---|
| `copies_v2` | 0 (métricas agregadas idénticas) | 0 | 0 | 0 |
| `external_diverse` | −56 [−256; +121] | −1,7 pp | −0,8 pp | +0,8 pp |

**Corrección de la revisión del 30 de octubre:** no se observó mejora en estas
cuatro métricas, pero eso no descarta un problema de calls ni demuestra que el
costo venga de los shoves propios. Los resultados agregados son idénticos;
las partidas no: cambió la mano de eliminación en 6 de 132 parejas y la duración
de la mesa en 7. Sin trazas no puede afirmarse que ningún call fuera vetado.
La rama de tabla de v8 omite observar durante la solicitud, pero la arena sí
actualiza el modelo al final de cada mano; ese probe aislado no explica las
diferencias históricas. Véase la
[revisión independiente y los probes reproducibles](REVISION_V8_2026_10_30.md).
v8c no mostró una ventaja y no se recomienda promoverla.

## Verificación

- 9 pruebas nuevas en [`tests/test_pushfold.py`](../tests/test_pushfold.py):
  - tamaño de los rangos HU contra el Nash publicado y monotonía por posición y
    profundidad;
  - mapa de posiciones de 2 a 6 jugadores;
  - empujar o retirarse, pagar o retirarse;
  - aislamiento de v8b y confirmación de v8c;
  - delegación a v2 con más de 15 bb;
  - manos completas legales con 2 a 6 jugadores.
- Suite completa: **200 pruebas aprobadas** (log en `.tmp/v8_full_tests.txt`).
- Cero fallbacks y conservación de fichas en todas las sesiones de las tres
  baterías.
- Las decisiones cubiertas por las tablas tardan milisegundos, sin muestreo.
  Esta parte no requiere un presupuesto de cálculo.

## Reproducción

```powershell
.\.venv\Scripts\python.exe -m scripts.build_pushfold_equity --boards 4000
.\.venv\Scripts\python.exe -m scripts.build_pushfold_charts
.\.venv\Scripts\python.exe -m unittest tests.test_pushfold -v
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v8
.\.venv\Scripts\python.exe -m scripts.v8_sessions --root results/v8_sessions_2026-10-29 --groups 40 --scenarios external_diverse
.\.venv\Scripts\python.exe -m scripts.v8_sessions --root results/v8_sessions_2026-10-29 --summary
```

El lote principal usó `--groups 40` (40 grupos × 2 formatos = 80). Los
controles `pressure` y `copies_v2` usaron `--groups 20`.

## Próximos pasos

- Medir por separado aperturas, re-shoves y calls contra campos selectivos,
  manteniendo igual la actualización del modelo público. El origen del costo
  observado en `copies_v2` todavía no está aislado.
- Delimitar la profundidad de los re-shoves frente a todos los rivales que
  puedan responder: una tabla elegida por un raiser corto puede comprometer un
  stack mucho mayor contra otro jugador profundo. La revisión enlazada arriba
  reproduce este caso; cualquier corrección debe conservarse como otra variante.
- Usar rangos con ICM o con aversión a la eliminación si la métrica oficial
  premia la supervivencia.
- Hacer un contraste directo contra v4rb, que tuvo la mejor media de la tercera
  evaluación con otras semillas; no se midió aquí por tiempo.

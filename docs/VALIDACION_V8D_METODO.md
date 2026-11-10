# v8d: corrección, separación de componentes y validación local

30 de octubre de 2026, Lima. La candidata es **v8d**. v2 continúa predeterminada.
La v8 histórica y sus tablas no se modifican.

## Cambio de política

`pokerfight/guarded_pushfold.py` reutiliza las tablas de v8 y la v2 congelada.
Antes de una respuesta preflop no terminal, compara el stack efectivo frente
al raiser con el que podría enfrentar frente a cualquier rival activo. Si un
tercer jugador puede cubrir más fichas que el raiser, delega toda esa respuesta
en v2, incluida la decisión de retirarse. No sustituye una tabla de 8 bb por un
shove que pueda arriesgar 12 o 100 bb contra otro jugador. Los jugadores ya
retirados no amplían el riesgo.

Esta es una delimitación del uso del modelo, no un solver para stacks desiguales.
Se conservan las aproximaciones de caller único, ausencia de ante, frecuencias
convertidas a acciones con umbral 0,5 y el resto del juego delegado en v2.

v8d observa el historial público en cada solicitud, también cuando decide con
tablas. Esto evita depender del cierre de mano de la arena al usar `serve`.
La arena **ya** actualizaba el modelo al final de cada mano de las campañas
históricas: la revisión inicial exageró el alcance de esa omisión. El documento
de revisión se corrigió y una prueba comprueba explícitamente ese hook para v8
y v8d. Un error de tabla en v8d se registra como fallback aunque v2 pueda responder.

Las variantes de desarrollo son `v8d_open`, `v8d_reshove` y `v8d_call`: solo
activan, respectivamente, la rama de apertura, respuesta no terminal o respuesta
terminal de las tablas. Incluyen tanto apostar/pagar como retirarse en su
contexto. Las otras decisiones son v2. Todas observan del mismo modo.

## Registro previo a resultados

El [protocolo JSON](../results/v8d_validation_2026-10-30/protocol.json), su
[SHA-256](../results/v8d_validation_2026-10-30/protocol.sha256) y el snapshot de
fuentes incluyen **ambas fases**, cuotas, tablas y reglas de decisión. El
registro se hizo antes de ejecutar sus semillas nuevas. La fase de desarrollo
no selecciona otra candidata ni cambia el tamaño de la validación.

La [comprobación de semillas](../results/v8d_validation_2026-10-30/seed_check.json)
registra 70.656 barajas previstas y cero coincidencias entre fases o con las
66.077 semillas históricas identificadas. Se escanearon los `deck_seed` guardados
y se reconstruyeron además las semillas de las tres campañas compactas v8.
Eso cubre los artefactos examinados, no partidas externas desconocidas.

| Fase | Escenarios | Grupos por formato | Brazos | Mesas |
|---|---|---:|---|---:|
| Desarrollo | copias v2, selectiva | 8 por escenario | v2, v8, v8d, apertura, re-shove, call | 1.056 |
| Validación principal | diversa externa | 212 | v2, v4rb, v8d | 6.996 |
| Validación de controles | copias v2, selectiva | 24 por escenario | v2, v4rb, v8d | 1.584 |
| Total | — | — | — | **9.636** |

Cada grupo incluye todos los asientos cíclicos, cinco o seis según formato.
Se mantienen 800 fichas iniciales, ciegas fijas 50/100, sin ante ni recompras y
hasta 128 manos. Se juega la mesa aunque el héroe ya esté eliminado, para
distinguir finalización y censura. Todas las fichas se conservan por mano.

La mesa diversa contiene Fullhouse, Honest educativo, v2 y pressure; en seis
jugadores se añade otro Fullhouse. La selectiva contiene TAG, tight, v2, TAG y,
en seis jugadores, otro tight. Las copias v2 usan 4.000 muestras/1.600 ms.

v2, v8 y las variantes v8d usan 4.000 muestras/1.600 ms para la parte delegada;
v4rb usa 1.024/3.500, el perfil de la comparación anterior de seis versiones.
Las tablas no hacen Monte Carlo en tiempo de decisión. Es una comparación de
perfiles concretos, no de algoritmos a igual CPU. Los rivales mantienen cuotas
fijas y no heredan la del héroe. Se usan seis procesos y fuentes congeladas.

## Métricas y decisión fijadas

La unidad independiente es el grupo de semillas, no la mano ni el asiento.
Se promedia primero la diferencia pareada entre asientos, y después entre
grupos de cada formato. Cinco y seis jugadores reciben igual peso. No se
promedian los escenarios para construir una métrica principal favorable.

En validación, para **cada** control (v2 y v4rb) se exige:

- En la mesa diversa, diferencia de fichas finales media de al menos +80 y
  límite inferior de un intervalo bootstrap bilateral del 97,5 % mayor que cero.
  Ese nivel ajusta por Bonferroni los dos contrastes principales.
- Diferencia media de fichas no negativa en cada formato de la mesa diversa.
- En **cada uno de los tres escenarios**, límite superior unilateral del 97,5 %
  para el aumento de eliminación a 24 manos no mayor de 5 puntos porcentuales.

Todos los requisitos deben cumplirse; no se elige después uno de ellos.
Victorias, eliminación a 128 y supervivientes en mesas sin terminar son
secundarios y se informan con sus intervalos descriptivos. No se inventan
victorias para líderes de mesas incompletas. Se emplean 20.000 réplicas bootstrap
de grupos, estratificadas por formato. Estos intervalos son aproximaciones
frecuentistas por remuestreo, no certificados exactos de cobertura finita.

Los 212 grupos por formato principal proceden de la dispersión histórica
v8−v2 y dan aproximadamente 80 % de potencia normal para +160 fichas frente a
cero, ajustando los dos contrastes. No garantizan esa potencia para v8d−v4rb,
la puerta adicional de media +80 ni el límite de deterioro de 5 puntos. Si la
incertidumbre impide pasar una puerta, la decisión es **no avanzar**.

Además se exige matriz completa, ningún fallback ni corte de muestras por reloj,
coherencia de los artefactos y replay exacto salvo tiempos. Se reproducen, por
selección anterior a resultados, hasta ocho primeras manos de la rotación cero,
grupo cero, para todos los brazos de cada escenario y formato. Un fallo técnico
se conserva y no se reemplaza silenciosamente con una partida favorable.

Pasar esta prueba solo habilitaría una evaluación posterior del formato oficial.
No autoriza cambiar el valor predeterminado antes de disponer del objetivo y
las reglas que realmente puntúan en el torneo.

## Ejecución y reproducción

El [corredor](../scripts/v8_validation.py) comprueba protocolo y snapshot en cada
reanudación, rechaza trazas incompletas y verifica hashes de resultados. Un
cambio en el código del workspace no afecta las fuentes congeladas en ejecución.

```powershell
# El registro existente ya está sellado; no repetir register sobre esa carpeta.
.\.venv\Scripts\python.exe -m scripts.v8_validation run --root results/v8d_validation_2026-10-30 --phase development
.\.venv\Scripts\python.exe -m scripts.v8_validation audit --root results/v8d_validation_2026-10-30 --phase development
.\.venv\Scripts\python.exe -m scripts.v8_validation run --root results/v8d_validation_2026-10-30 --phase validation
.\.venv\Scripts\python.exe -m scripts.v8_validation audit --root results/v8d_validation_2026-10-30 --phase validation

# Uso manual experimental
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v8d
```

# Mejora de cálculo y protección de búsqueda incompleta

29 de octubre de 2026, hora de Lima. **v2 sigue predeterminada.** Esta iteración
reduce el tiempo de cálculo de las candidatas integradas y corrige un caso de
muestreo incompleto. No es una nueva evaluación de fuerza estratégica.

## Cambios

`IntegratedAction`, usado por v4rb y v6, resuelve cada precio y número de
callers distinto una sola vez por mundo y prior. Conserva separados los
resultados de cada rama. Los pagos terminales se reutilizan según qué rivales
ganan, empatan o pierden contra el héroe; ese cálculo no depende del prior ni
de la puntuación exacta de las cartas. La caché pertenece a una sola acción
y observación, con hasta 243 patrones en una mesa de seis. La integración
recorre el árbol desde las hojas y conserva el orden de las operaciones
aritméticas del código anterior.

En la búsqueda compartida por v4, v4rb y v6, agotar el límite de intentos por
colisiones de cartas conserva ahora el baseline si la cuota quedó incompleta.
Antes, si se habían obtenido algunos mundos válidos, se registraba
`sample_cap` y podía elegirse otra acción con una muestra insuficiente.
El nuevo motivo es `incompatible_ranges_keep_v2`. El baseline es la decisión
local calculada antes de buscar; no equivale necesariamente a repetir la
política v2 congelada con otro presupuesto.

Una prueba sintética reprodujo el defecto antes de corregirlo: dos mundos
ganadores válidos en 10.000 intentos producían una subida a 800, pese a que
se solicitaron 64 mundos. Después conserva fold y registra la causa correcta.
Esta prueba aísla la condición de parada; no demuestra que ocurriera en las
partidas históricas. Las paradas adaptativas normales conservan sus reglas.

## Tiempo de cálculo

Se preservó el paquete anterior completo antes de modificarlo, junto con su
entorno y huellas. El [protocolo](../results/improvements_2026-10-29/protocol.json)
fijó siete fixtures de desarrollo, 2.048 mundos por búsqueda, cinco repeticiones
y orden alternado anterior/nuevo. Cada pareja usó el mismo seed, cartas,
respuestas y cuota. Los tiempos incluyen preparar el árbol y llenar su caché;
excluyen la estimación inicial de equity y la preparación de rangos.

| Estado | Antes, mediana ms | Después, mediana ms | Factor |
|---|---:|---:|---:|
| UTG especulativa, 4 bb | 748,94 | 364,95 | 2,05× |
| Heads-up, 8 bb | 96,36 | 65,27 | 1,48× |
| UTG as débil, 4 bb | 529,32 | 271,75 | 1,95× |
| Botón as débil, 4 bb | 148,35 | 102,73 | 1,44× |
| Héroe profundo, rival de 4 bb | 98,16 | 65,65 | 1,50× |
| Defensa barata de BB | 92,65 | 59,06 | 1,57× |
| Defensa cara de BB | 43,64 | 32,09 | 1,36× |

El cociente entre las sumas de las medianas es **1,83×**, equivalente a
**45,3 % menos tiempo**. No es una mediana de latencia de producción ni
una estimación de todo el tiempo de una decisión.

## Equivalencia y verificación

El [benchmark completo](../results/improvements_2026-10-29/benchmark.json)
registra resultados y tiempos sin sustituir los datos históricos:

- **35 parejas de búsquedas con cuota fija:** igualdad exacta de acción,
  valores, errores de Monte Carlo, conteos y motivos de parada.
- **42 parejas de decisiones adaptativas:** siete fixtures, v4rb/v6 y tres
  seeds; igualdad exacta salvo el tiempo medido.
- **40 parejas de manos completas:** v4rb/v6, todas las rotaciones de mesas
  de 2–6 jugadores, 512 muestras y nuevas barajas. Son 80 ejecuciones técnicas,
  con 68 decisiones propias por versión de código. Coinciden acciones,
  historiales, fichas y trazas completas salvo tiempos.
- **16 decisiones supervisadas**, comparadas con su ejecución directa a
  4.096 muestras. Máximo observado del supervisor: 606,613 ms. Cero fallbacks,
  acciones ilegales, pérdidas de fichas o excesos del límite local de 4.250 ms.
- Los tests independientes enumeran las 243 relaciones de rango entre seis
  asientos para tres acciones y tres priors: **2.187 comparaciones exactas**,
  variando las puntuaciones entre consultas. Incluyen empates, dinero muerto,
  stacks desiguales, pozos laterales y retornos. Otros casos verifican check,
  all-ins y separación entre observaciones.

La suite completa pasa **156 pruebas**; el log se conserva en
[`tests_final.txt`](../results/improvements_2026-10-29/tests_final.txt).
Las fuentes congeladas y decisiones golden de v2 siguen coincidiendo.
La [comprobación de integridad](../results/improvements_2026-10-29/integrity.json)
identifica los dos módulos de producción modificados y las huellas finales.

El primer intento del benchmark se detuvo al crear un rival v2 con el
presupuesto extendido del héroe. Se corrigió el runner para usar 1.600 ms en
los rivales y se repitió la comprobación completa. Sus logs se guardaron como
`benchmark_attempt1_*`; el resultado final corresponde a la ejecución exitosa.
Ese ajuste no modificó estrategias, fixtures, cuotas ni barajas.

## Límites y reproducción

Estos resultados prueban menor costo de cálculo y equivalencia en las pruebas
realizadas. No acreditan más ganancias, menos eliminaciones ni una política
superior. Al usar un límite de tiempo en lugar de una cuota fija, el código
más rápido puede completar más mundos y cambiar una decisión. Las limitaciones
estratégicas de los priors y la aproximación sin apuestas posteriores siguen
vigentes. No se promueve v4rb ni v6.

Desde la raíz, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.benchmark_integrated_search --reference results/improvements_2026-10-29/source_before --output results/improvements_2026-10-29/benchmark_repeat.json
```

El benchmark verifica las fuentes de referencia y rechaza sobrescribir un
resultado existente. Para otra repetición se utiliza un nombre de salida nuevo.
Las manos repetidas son verificaciones técnicas, no evidencia estratégica nueva.

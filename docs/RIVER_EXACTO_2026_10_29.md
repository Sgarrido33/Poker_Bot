# Alternativa experimental: equity exacta en river

29 de octubre de 2026, hora de Lima. **v2 sigue predeterminada.** Esta alternativa
se desarrolló con dos subagentes mientras otra sesión evaluaba v7. No cambia
las reglas preflop ni las candidatas existentes.

## Resultado

En river, con un solo rival activo, quedan como máximo **990 combinaciones
distintas** de cartas rivales: 45 cartas desconocidas, tomadas de dos en dos.
Podemos enumerarlas y ponderarlas en vez de muestrearlas con reemplazo.

En seis fixtures con las 990 combinaciones, la enumeración consumió **2,880 ms**
frente a **28,624 ms** de Monte Carlo con 4.000 muestras: **9,94 veces más
rápida**, un **89,94 % menos tiempo de estimación**. Son cocientes entre sumas
de medianas de fixtures, no una mejora medida del tiempo de un torneo completo.
Las mediciones se hicieron con otra sesión trabajando en el mismo equipo.

| Cuota Monte Carlo | Tiempo MC, ms | Tiempo exacto, ms | Factor MC/exacto | RMSE de MC |
|---:|---:|---:|---:|---:|
| 128 | 1,131 | 2,880 | 0,39× | 0,02724 |
| 1.024 | 7,508 | 2,880 | 2,61× | 0,00902 |
| 4.000 | 28,624 | 2,880 | 9,94× | 0,00445 |

Cada cuota tiene 24 réplicas por fixture; el orden de estimación se alternó.
El tiempo excluye construir rangos y seleccionar apuestas. Con solo 128
muestras, Monte Carlo es más rápido y conserva error de muestreo. La equity
exacta tiene error de Monte Carlo cero **condicionado al rango suministrado**;
el rango y las reglas de apuesta continúan siendo aproximaciones.

El experimento contiene nueve fixtures: seis con soporte completo y tres
sintéticos con una o dos combinaciones para comprobar pesos, dinero muerto,
devoluciones y un precio límite. El agregado de los nueve arroja 14,66×, pero
está favorecido por esos soportes pequeños; por eso la comparación principal
de arriba usa solo los seis de 990 combinaciones.

## Implementación y alcance

[`estimate_river`](../pokerfight/river_exact.py) integra los incrementos de la
distribución acumulada de `WeightedRange`, respetando cartas conocidas,
empates, costo del call y capas elegibles del bote. Usa sumas compensadas y
rechaza rangos inválidos. Si vence el presupuesto, lanza una excepción en vez
de entregar una enumeración parcial como si fuera exacta.

`ExactRiverPolicy(base)` envuelve una candidata viva. En river contra un rival
actualiza el mismo modelo, construye los mismos rangos y entrega la equity
exacta a `base.select`. Fuera de ese ámbito delega directamente en
`base.decide`. Se conservan el historial de fin de mano y el cierre de procesos.
Los controles congelados se rechazan para preservar su identidad experimental.

`EquityResult.standard_error=0` expresa ausencia de ruido de Monte Carlo.
`samples` y `attempts` cuentan entradas enumeradas, no simulaciones aleatorias
independientes. Un soporte de una combinación es válido sin fingir un mínimo
de 128 muestras. La metadata identifica `exact_heads_up_river`; `changed=False`
solo indica que no se hizo búsqueda de acciones contra un baseline.

Eliminar el error estándar puede cambiar decisiones cerca de los umbrales
de las heurísticas actuales. En el fixture sintético de precio exactamente
igual a la equity, MC4.000 discrepa de la acción exacta en 21/24 réplicas.
Esto muestra sensibilidad al muestreo y al margen conservador, **no una
ganancia estratégica probada**.

## Verificación

- Doce pruebas específicas verifican pesos con solución conocida, empates,
  bloqueadores, capas del bote, devoluciones, vencimiento del plazo,
  compatibilidad de métricas, selección, delegación y cierre.
- Se jugaron **40 pares de manos completas**, con dos barajas por formato y
  todas las rotaciones de 2–6 jugadores, v4rb contra rivales calling y stacks
  de 50 bb. Son 80 ejecuciones técnicas, con 512 muestras para las decisiones
  delegadas. Coinciden todas las trazas anteriores al river, salvo tiempos.
- Solo **dos decisiones** de esas manos estuvieron dentro del ámbito exacto.
  La cobertura de casos de river procede principalmente de fixtures y tests;
  estas manos no constituyen una evaluación de fuerza.
- Cero fallbacks, acciones ilegales o pérdidas de fichas en las manos técnicas.
  Las nueve decisiones completas adicionales del wrapper tampoco tuvieron
  fallbacks; máximo observado **5,174 ms**. Esas nueve latencias son mediciones
  individuales, no medianas repetidas.
- El control v2 congelado pasó su verificación de integridad. No se tocaron
  sus fuentes, el selector global ni los archivos de la campaña v7.
- La suite completa pasó **190 pruebas** en 49,233 segundos; el
  [log](../results/exact_river_2026-10-29/tests_full.txt) incluye las 18 nuevas
  pruebas de esta iteración y las de v7 presentes al ejecutar la suite.

El [protocolo](../results/exact_river_2026-10-29/protocol.json) se escribió antes
de medir, junto con una copia de fuentes y sus huellas. El
[benchmark](../results/exact_river_2026-10-29/benchmark.json) contiene réplicas,
acciones y trazas; el [análisis](../results/exact_river_2026-10-29/analysis.json)
separa los fixtures de soporte completo. Los artefactos son de desarrollo.

## Corrección adicional de replay

[`replay_worst`](../pokerfight/replay.py) creaba políticas y no cerraba sus
workers al terminar o fallar. Ahora reutiliza la construcción con limpieza
parcial y cierra las políticas en un `finally`. Tres pruebas reproducen éxito,
error durante una mano y error creando la siguiente política. Las otras tres
pruebas nuevas comprueban las cuotas declaradas para rivales y el perfil fijo
`v2_4000`.

El campo `rival_samples` de evaluación ya fue corregido concurrentemente por
la sesión de v7; esta iteración agrega cobertura pero no se atribuye ese cambio.

## Probar y reproducir

Desde la raíz del proyecto, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_exact_river decide examples/river_exact.json --base v4rb
.\.venv\Scripts\python.exe -m unittest tests.test_river_exact tests.test_evidence_lifecycle -v
```

La entrada independiente admite bases v3/v4/v4rb/v5/v6/v7. La evaluación de
manos de esta iteración usa v4rb; no prueba la fuerza de combinaciones con v7.
El comando principal `pokerfight` conserva sus opciones actuales.

Para repetir las mismas barajas y cuotas en una carpeta nueva:

```powershell
$riverProject = (Get-Location).Path
$riverOutput = Join-Path $riverProject 'results/exact_river_reproduction'
.\.venv\Scripts\python.exe -m scripts.benchmark_exact_river register --output $riverOutput
Push-Location (Join-Path $riverOutput 'source')
try {
    & (Join-Path $riverProject '.venv/Scripts/python.exe') -m scripts.benchmark_exact_river run --output $riverOutput
} finally {
    Pop-Location
}
```

El registro rechaza carpetas existentes y la ejecución rechaza sobrescribir
resultados. Usa la copia congelada, comprueba sus hashes y conserva la semilla;
cambiar de carpeta no crea evidencia independiente.

La alternativa queda disponible para futuras comparaciones. No se promociona
a predeterminada ni se concluye que aumente ganancias o supervivencia.

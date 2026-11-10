# Validación local de PokerFight v0.1

Fecha: 27 de octubre de 2026. Equipo Windows 11 x64; Python 3.12.14, Eval7 0.1.11 y PokerKit 0.7.7. Se utilizó el escritorio activo, sin aislar frecuencia, temperatura ni otros procesos. Los tiempos describen este equipo; faltan transporte y latencia de la arena oficial.

## Pruebas automatizadas

**21 pruebas aprobadas**, con `python -m unittest discover -s tests -v`. El [registro completo](../results/unit_tests.txt) conserva la salida. Se verificaron:

- Parseo, campos desconocidos, cartas repetidas, posición y límites de apuesta.
- Acciones legales, imposibilidad de reabrir una subida corta y call all-in.
- Equity de manos resueltas y empates; rangos ponderados y muestreo conjunto contrastados con enumeración exacta en river.
- Pozos laterales con stacks desiguales, dinero de retirados y exclusión de capas inaccesibles.
- Separación de cartas ocultas y políticas, conservación de fichas y repetición exacta de manos con 2, 5 y 6 jugadores.
- Deduplificación de eventos y reinicio de perfiles al cambiar de mesa.
- Respuesta de respaldo ante excepciones, acciones propuestas inválidas y presupuesto agotado.
- Recuperación del proceso JSONL después de una entrada malformada.

Eval7 emite un aviso de deprecación de `pyparsing.parseString` en la suite; procede de la biblioteca y no impide el funcionamiento probado. Las pruebas no equivalen a una certificación exhaustiva de todas las secuencias posibles de apuestas.

También se comprobó el arranque mediante `python -m pokerfight`, la instalación editable del paquete y el ejecutable local `.venv/Scripts/pokerfight.exe`. La instalación se verificó sin descargar dependencias nuevas, reutilizando las herramientas de empaquetado disponibles en el runtime local.

## Evaluación pareada

Se fijaron antes de medir: semilla `20261027`, ocho bloques, cinco manos por bloque y todos los asientos. Cada variante empieza con 10 000 fichas por mano; ciegas locales 50/100, sin ante. El bot usa 4 000 muestras por decisión y presupuesto de 1 600 ms.

Se reemplaza únicamente a `hero`: candidato `v1` frente a base `tight`. Los demás asientos alternan `calling`, `tight` y `random`. Son rivales simples incluidos en el código, no bots oficiales ni agentes de nivel competitivo.

| Resultado | 5 jugadores | 6 jugadores |
|---|---:|---:|
| Manos por variante | 200 | 240 |
| Manos totales, ambas variantes | 400 | 480 |
| Decisiones del candidato | 421 | 422 |
| Tiempo mediano | 61,8 ms | 69,8 ms |
| Tiempo p95 | 95,8 ms | 107,5 ms |
| Tiempo máximo observado | 136,0 ms | 151,3 ms |
| Decisiones del candidato > 2 000 ms | 0 | 0 |
| Respuestas de respaldo del candidato | 0 | 0 |
| Decisiones con muestras parciales | 0 | 0 |
| Ganancia del candidato, bb/mano | +7,506 | +6,799 |
| Ganancia de la base, bb/mano | −0,0025 | −0,297 |
| Diferencia pareada, bb/mano | +7,508 | +7,096 |
| Error estándar entre bloques | 1,347 | 2,286 |
| Intervalo normal aproximado del 95 % para la diferencia | [4,868; 10,149] | [2,616; 11,576] |

En las **880 manos** se conservó el total de fichas y todas las acciones pasaron el validador propio y PokerKit. Un error de legalidad o de conservación aborta la evaluación; no se omiten manos fallidas para completar el lote.

Los reportes originales contienen configuración, versiones, diferencias por bloque y latencias: [cinco jugadores](../results/evaluation_5p.json) y [seis jugadores](../results/evaluation_6p.json). Las métricas se pueden reproducir con:

```powershell
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v1 --players 5 --blocks 8 --hands-per-block 5 --seed 20261027 --output results/evaluation_5p.json
.\.venv\Scripts\python.exe -m pokerfight evaluate --hero v1 --players 6 --blocks 8 --hands-per-block 5 --seed 20261027 --output results/evaluation_6p.json
```

La implementación añade también los promedios de cada variante por bloque a nuevas ejecuciones. Las cifras de tiempo cambian con la carga del equipo. Las acciones y ganancias se repiten con la misma configuración mientras no se trunque el muestreo por reloj. Las semillas de políticas están separadas de las barajas; no se usa el generador aleatorio global para decidir.

## Mesa con eliminaciones

Se realizaron otras 50 manos por formato, con semilla `71`, 600 fichas iniciales, ciegas 50/100, ante de 25 y 256 muestras por decisión. Se conservaron fichas entre manos y se retiraron los jugadores eliminados. Ambas pruebas conservaron todas las fichas y el candidato no activó el respaldo.

Los archivos [short_stack_5p.json](../results/short_stack_5p.json) y [short_stack_6p.json](../results/short_stack_6p.json) conservan resultados y eliminaciones. Se reproducen con `simulate --players 5` o `6`, añadiendo `--hands 50 --seed 71 --samples 256 --carry-stacks --starting-stack 600 --ante 25`.

## Interpretación y límites

La versión inicial funciona de principio a fin en la arena local y tiene margen observado dentro del objetivo interno de tiempo. La ventaja medida es una referencia frente a oponentes deliberadamente sencillos. No demuestra que vaya a clasificar, que pueda mantener esa ganancia frente a otros equipos ni que sus parámetros sean óptimos.

Hay solo ocho bloques independientes por formato; el intervalo normal es descriptivo y puede estar mal calibrado para distribuciones de resultados con colas amplias. Asientos del mismo bloque comparten barajas y no se cuentan como observaciones independientes del error estándar. Esto no implementa AIVAT ni mide explotabilidad.

No hubo ajuste de parámetros posterior para maximizar esta puntuación. Estos lotes deben tratarse como datos de desarrollo; las mejoras futuras necesitan nuevas semillas reservadas y rivales más exigentes.

La comparación reinicia stacks en cada mano y mide fichas, no supervivencia ni clasificación. La prueba con eliminaciones es de una sola mesa y ciegas fijas. Siguen pendientes la API real, el supervisor externo de plazos, los bots del kit y el formato completo de la competición.

# Diagnóstico temprano y candidata v6

**Actualización:** la campaña posterior ya terminó. La v6 no pasó el filtro
principal y empeoró las medias frente a v4rb; véanse los
[resultados nuevos](TERCERA_EVALUACION_RESULTADOS.md). Este documento conserva
el diagnóstico y la hipótesis anteriores a esa evaluación.

28 de octubre de 2026. **v2 sigue predeterminada. v6 es experimental.**
El usuario confirmó que todavía no hay reglas oficiales; seguimos usando
supuestos locales: stack inicial 800, ciegas fijas 50/100, sin ante ni recompras.
La métrica oficial de éxito sigue pendiente. No se decide entre fichas,
supervivencia, puestos o premios sin esas reglas.

## Evidencia observada

Se releyeron las 40 trazas de grupos de sesiones de la segunda batería,
incluyendo todos los escenarios, formatos y brazos. No se jugaron manos nuevas
para este diagnóstico. Los inputs están identificados por SHA-256 en
[`diagnosis.json`](../results/early_diagnosis_2026-10-28/diagnosis.json).
El horizonte temprano comprende los índices de mano 0–23. Una eliminación se
cuenta una vez, aunque la mesa continúe sin el héroe.

| Medida hasta 24 manos | v2 | v4 | v4rb | v5 |
|---|---:|---:|---:|---:|
| Eliminaciones / 220 mesas | 100 | 122 | 120 | 128 |
| Decisiones preflop | 3.667 | 2.648 | 2.705 | 2.555 |
| Cambios respecto del baseline local de búsqueda | — | 1.232 | 1.274 | 969 |
| Pushes efectivos | 89 | 396 | 414 | 709 |
| Subidas no terminales | 539 | 1.273 | 1.296 | 696 |
| Subidas no terminales resubidas antes del siguiente turno propio | 43 | 125 | 121 | 81 |
| Nuevas subidas no terminales propuestas por búsqueda | — | 884 | 910 | 309 |
| De esas nuevas subidas, recibieron resubida | — | 95 | 90 | 42 |

Un push efectivo alcanza la menor de la cobertura máxima rival y el stack
total propio de la calle; no exige apostar fichas que nadie puede disputar.
Los conteos son decisiones, no réplicas independientes ni tasas comparables
sin considerar los estados visitados. Las trayectorias de cada política cambian
las oportunidades de actuar.

En v4rb, 879 cambios fueron de fold a subida no terminal y 255 de fold a
push efectivo. Hubo 23 ocasiones con subida no terminal seguida de fold ante
una resubida. Estos números identifican una limitación que merece un cambio
aislado: el modelo fold/call de v4/v4rb asigna valor a una subida pequeña como
si no hubiera resubidas ni apuestas posteriores. No prueba que todas esas
subidas sean negativas, ni que expliquen causalmente el exceso de eliminaciones.
La revisión del código no encontró un error concreto en capas del bote,
precio del call o reapertura acumulativa que justificara cambiar esos cálculos.

La mayor agresión de v5 también importa: 709 pushes efectivos y 118 de sus
128 eliminaciones tempranas terminan con una decisión preflop del héroe. v5 ya
incluye una resubida hipotética, por lo que la limitación de v4rb no explica
por sí sola su perfil. Apostar all-in más a menudo no demuestra una mejora.

El CSV incluye posición, profundidad efectiva, rivales activos, situación,
precio del call, inversión en bb y fracción del stack, respuestas públicas y
cohorte de eliminación. Hay 362/360/500 decisiones de v4/v4rb/v5 en un estado
físico observado también con v2; sus acciones difieren en 222/224/219 casos.
No basta para un contraste causal: los perfiles aprendidos de manos anteriores
pueden ser distintos. `search.baseline` es la acción local previa a búsqueda;
no es un replay contrafactual exacto de la v2 congelada.

No se compararon probabilidades predichas de call con observaciones bajo un
modelo de calibración. Los porcentajes de calls seleccionados no autorizan
reajustar las priors ni clasificar una apuesta como rentable. Esa calibración
sigue siendo un experimento distinto.

## Cambio aislado en v6

[`terminal_search.py`](../pokerfight/terminal_search.py) conserva la integración
de respuestas de v4rb y restringe el conjunto de acciones alternativas:

- Conserva siempre la acción local previa a búsqueda como primer brazo.
- Permite fold/check y nuevos calls o raises que comprometan efectivamente al
  héroe o cubran a todos los rivales activos.
- Excluye nuevas inversiones no terminales, incluidas subidas pequeñas, que
  el modelo solo puede valorar mediante una aproximación de checkdown.

No se cambia el muestreo, las priors, el margen de selección ni el presupuesto.
La cuota para comparar es 4.096 muestras y 3.500 ms, como el perfil de v4rb.
El control predeterminado y sus fuentes congeladas se conservan. v6 está
disponible en `decide`, `serve`, `simulate` y `evaluate`, incluida la ejecución
supervisada con el mismo límite de proceso.

Es una hipótesis sobre el alcance de un estimador, no una corrección certificada
de rentabilidad. El valor del baseline continúa siendo una aproximación. La
restricción puede desplazar acciones hacia pushes y aumentar el riesgo; también
puede descartar subidas pequeñas rentables. Un héroe all-in puede seguir expuesto
a efectos de apuestas entre rivales por pozos laterales. Todo ello exige medir
por separado fichas, eliminación temprana y tardía, victorias y censura.

## Comprobación técnica

El protocolo de la prueba técnica se guardó antes de las nuevas ejecuciones:
[`protocol.json`](../results/v6_technical_2026-10-28/protocol.json).
Son **18 ejecuciones de mano**, sobre seis barajas nuevas compartidas por
v2/v4rb/v6, con formatos de cinco y seis y la mezcla externa diversa. Son una
prueba de funcionamiento, no grupos completos para inferencia estratégica.

Además se hicieron 32 decisiones sobre 16 observaciones históricas, seleccionadas
por orden de archivo y por tipo de acción, sin filtrar ganancias o pérdidas.
Ambos brazos empiezan con modelos sin historial anterior: son decisiones nuevas
sobre fixtures, no replays. v6 cambió la acción de v4rb en 14/16 fixtures.

La prueba técnica tuvo cero fallbacks, cortes de equity/búsqueda y errores de
conservación de fichas. El máximo observado por decisión fue 1.147,221 ms; no
es una garantía de latencia en otros estados o máquinas.
[`summary.json`](../results/v6_technical_2026-10-28/summary.json) conserva la
contabilidad. Las pruebas unitarias verifican la restricción efectiva con stacks
desiguales, precio del call, decisiones fuera de alcance, supervisión y manos
completas legales. No son evidencia de fuerza.

La suite completa pasó **134 pruebas**; el log está en
[`tests_final.txt`](../results/v6_technical_2026-10-28/tests_final.txt).
La [comprobación de integridad](../results/v6_technical_2026-10-28/integrity.json)
confirma las 40 trazas históricas, las fuentes originales congeladas de v2 y
la huella del código usado por la prueba técnica.

## Reproducción

Desde la raíz, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scripts.diagnose_early_eliminations
.\.venv\Scripts\python.exe -m unittest tests.test_terminal_search tests.test_early_diagnosis -v
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v6 --samples 4096
.\.venv\Scripts\python.exe -m scripts.plan_competition_stage3
```

`scripts.probe_terminal_search` conserva el protocolo existente y rechaza
sobrescribirlo; para otra prueba se cambia primero el directorio y el ID en una
copia revisada. Las campañas históricas no se sobrescribieron. Los nuevos
artefactos son de desarrollo. La [tercera evaluación](COMPETENCIA_TERCERA_PLAN.md)
está dimensionada, con semillas nuevas y controles, pero no ejecutada.

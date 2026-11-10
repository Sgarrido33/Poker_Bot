# Plan de tercera evaluación local

**Actualización:** la ejecución registrada ya terminó; véanse los
[resultados y auditorías](TERCERA_EVALUACION_RESULTADOS.md). Lo siguiente
conserva el plan de dimensionamiento anterior a la ejecución.

28 de octubre de 2026. **Plan de dimensionamiento: no está registrado ni
lanzado.** `v2` conserva el estado predeterminado. No se conocen las reglas
oficiales del torneo.

## Alcance y contraste

La fase principal queda centrada en `v6` frente a `v2` en `external_diverse`,
con dos resultados co-primarios: stack final observado/800 (mejor si sube) y
bust acumulado a H (mejor si baja). `v4`, `v4rb` y `v5` siguen como brazos de
contexto; sus contrastes son descriptivos y exploratorios. Así la corrección de
multiplicidad cubre solo las dos pruebas v6-v2, no seis comparaciones entre tres
candidatas.

Se mantienen cuatro controles en la matriz: `pressure`, `copies_v2`,
`copies_v2_4000` y `external_mix`. Cada uno tendría 8 grupos independientes por
formato. Se informan de forma diagnóstica; no se harán afirmaciones
confirmatorias con esos brazos ni escenarios.

La candidata experimental `v6` ya está implementada en
[`pokerfight/terminal_search.py`](../pokerfight/terminal_search.py) y se deriva de
`v4rb`. El brazo propuesto usa 4.096 muestras y 3.500 ms, igual al perfil de
`v4rb`. La búsqueda integrada restringe alternativas a fold/check y commits terminales
efectivos. Conserva como brazo cero la acción local previa a la búsqueda
(heredada del selector v2/equity); no ejecuta v4rb completo ni filtra su
decisión final. El baseline retenido no es una decisión final de v4rb. El valor
de checkdown no modela resubidas ni apuestas posteriores, y un all-in no impide apuestas de side pot: el cambio no garantiza menos all-ins, menor riesgo ni
mejores resultados. El perfil de héroe es 4.096 muestras / 3.500 ms, igual que
v4rb. Congelar el archivo y hashes de dependencias al registrar.

## Grupos, dispersión y potencia aproximada

Unidad independiente: grupo completo de semillas dentro de escenario y estrato
(5 o 6 jugadores). Un grupo incluye todos los brazos y rotaciones cíclicas
(cinco o seis); primero se promedia la diferencia pareada sobre rotaciones y
luego se comparan grupos. Asientos, manos y brazos de un grupo no aumentan el
número de réplicas independientes.

La etapa 2 solo aporta cuatro grupos por formato y no tiene observaciones de
v6. Para dimensionar provisionalmente v6 usé, por resultado, la mayor DE
observada entre las candidatas anteriores: 0,840 fichas/800 (v4) y 0,166 de
bust (v4rb). Es un proxy conservador entre las estimaciones antiguas, no una
varianza de v6 medida. Para cada métrica definí `DE_proxy=sqrt((s5²+s6²)/2)`.
Con n grupos independientes por formato, el error estándar de la media
estratificada equiponderada es `sqrt((s5²+s6²)/(4n)) = DE_proxy/sqrt(2n)`.
La aproximación normal usa 80 % de potencia, alfa familiar bilateral 0,05 y
Bonferroni para **dos** pruebas co-primarias v6-v2.

| Resultado primario v6 vs v2 | Umbral mínimo supuesto | Grupos requeridos por formato |
|---|---:|---:|
| Fichas finales / 800 | +0,10 | 336 |
| Bust a H | −5 puntos porcentuales | 53 |

El mayor requisito, 336 por formato, sería excesivo para esta evaluación local y
la varianza proxy es muy incierta. Como cribado configurable propongo 40 grupos
por formato en el escenario principal (80 grupos independientes), diez veces
los cuatro observados en etapa 2. Con la misma fórmula, a 40 grupos el efecto
detectable aproximado es 0,290 del stack para fichas y 5,7 puntos porcentuales
para bust. No se alcanza la potencia supuesta para los efectos mínimos. No se
reestima n mirando resultados de etapa 3.

Sensibilidad de grupos por formato bajo el mismo ajuste y proxy de varianza:

| Efecto mínimo | Fichas +0,05 | +0,10 | +0,20 | Bust −2,5 pp | −5 pp | −10 pp |
|---|---:|---:|---:|---:|---:|---:|
| N por formato | 1.343 | 336 | 84 | 210 | 53 | 14 |

Los tamaños son orientativos: solo cuatro grupos de etapa 2 por estrato
informaron las DE. El estudio no establece aptitud para el torneo oficial ni
permite promover automáticamente v6. Una decisión positiva solo justificaría
considerar una **validación futura separada**, con v6 congelada, nuevas semillas
y reglas oficiales disponibles.

## Matriz configurable propuesta

| Parte | Escenarios | Grupos/formato/escenario | Brazos | Estratos | Mesas máximas |
|---|---|---:|---:|---:|---:|
| Principal | `external_diverse` | 40 | 5 (`v2`, `v4`, `v4rb`, `v5`, `v6`) | 5p, 6p | 2.200 |
| Controles | cuatro listados arriba | 8 | los mismos 5 | 5p, 6p | 1.760 |
| **Total** | 5 escenarios | — | — | — | **3.960** |

El máximo a H=128 es 506.880 ejecuciones de mano; mesas que terminen antes
consumen menos. **No se ha ejecutado ninguna mano de etapa 3.** Los controles
quedan reducidos respecto a la fase principal y no se usan para ajustar o elegir
v6 según resultados.

La propuesta conserva stack inicial 800, ciegas locales 50/100, sin ante ni
intervalo de ciegas, y reporta horizontes 24, 64 y 128. Semillas deterministas
nuevas usan ID `crossplay-stage3-20261028-03`; hay 18.432 seeds de mano únicas
previstas para la matriz completa. Se compararon con 8.354 seeds únicas en 520
JSONL bajo `results/`; no hubo colisiones. Antes de registrar se debe repetir el
chequeo contra el ledger histórico completo y conservar sus huellas.

## Multiplicidad, censura y resultados

La única familia confirmatoria propuesta es v6 vs v2 en las dos métricas, con
Bonferroni bilateral alfa 0,05/2. Comparaciones de v4/v4rb/v5, escenarios de
control, stacks por formato y otros horizontes son exploratorios. Se informan
intervalos ajustados para ambos resultados, medias de fichas por formato y las
auditorías técnicas; `v2` permanece predeterminada. Aun si el cribado favorece
v6, no equivale a validación para competición oficial.

Bust es la eliminación observada del héroe antes o en H. Ser el único
superviviente observado es un evento competidor, no un bust ni una censura. “Sin
resolver” es no observar bust o victoria a H e incluye líderes censurados. Por
brazo, escenario y formato se reportan bust, victoria, sin resolver, mesa
completada y censura administrativa. No se asigna victoria ni rango a un líder
censurado. Stack a H no es equity de premios.

El estimador propuesto promedia primero las diferencias pareadas entre
rotaciones del grupo y luego las medias de los dos formatos con igual peso.
Los intervalos percentiles usarían 20.000 réplicas de bootstrap de grupos
completos dentro de cada formato, con semilla ya fijada en el plan y nivel
individual 97,5 % para cada uno de los dos resultados principales. La cobertura
es aproximada; el remuestreo no crea grupos nuevos. La asignación se completa
una sola vez: no se cambia la cantidad, se detiene ni se sustituyen semillas
según las ganancias observadas.

## Pendientes antes de registrar

1. Revisar el comportamiento de `pokerfight/terminal_search.py` y congelar su
   hash y los hashes de dependencias/código en el registro inmutable.
2. Confirmar elegibilidad/licencias de rivales externos y validez de sus
   adaptaciones al runtime.
3. Congelar cuotas; hacer un piloto técnico sin examinar diferencias entre
   candidatas, y validar censura y semillas.
4. Revalidar umbrales y varianza proxy con quien tome la decisión; después
   registrar el protocolo inmutable. Fallos técnicos invalidan inferencia.

Las reglas y pagos oficiales siguen desconocidos. Eso limita inferencias sobre
el torneo oficial, pero no bloquea una evaluación local bajo los supuestos
proxy fijados aquí.

## Artefactos reproducibles

- Cálculo: [`scripts/plan_competition_stage3.py`](../scripts/plan_competition_stage3.py)
- Plan JSON: [`plan.json`](../results/competition_stage3_plan_2026-10-28/plan.json)
- Pruebas: [`tests/test_stage3_planning.py`](../tests/test_stage3_planning.py)
- Fuente: [resultados etapa 2](COMPETENCIA_SEGUNDA_RESULTADOS.md) y
  [método](COMPETENCIA_SEGUNDA_METODO.md)

```powershell
.\.venv\Scripts\python.exe -m scripts.plan_competition_stage3
.\.venv\Scripts\python.exe -m unittest tests.test_stage3_planning -v
```

Tras ejecutar este estudio, no se reutiliza su ID ni se sobrescribe el plan.
Una propuesta nueva requiere `--id NUEVO_ID --output results/NUEVA_CARPETA/plan.json`.


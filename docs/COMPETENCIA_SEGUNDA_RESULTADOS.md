# Segunda evaluación local bot contra bot

28 de octubre de 2026. **v2 sigue predeterminada. Ninguna candidata pasó el filtro registrado.**

Se completaron **64.679 ejecuciones nuevas de mano**: 4.928 con
stacks reiniciados y 59.751 en sesiones.
Son 224 bloques de reset y 40 grupos completos de sesiones; las manos y los
asientos de un grupo no son observaciones independientes. Se jugaron 880 mesas,
220 por brazo, con cinco/seis jugadores iniciales y un máximo de 128 manos.
Todos estos resultados ya son datos de desarrollo.

## Qué cambió

Se conservaron los cinco campos anteriores y se añadieron copias v2 de 4.000
muestras y una mezcla con Fullhouse, HonestPlayer adaptado, v2/4.000 y pressure;
con seis jugadores se añade otro Fullhouse. Las cuotas rivales son constantes
entre brazos; las copias v2 antiguas conservan 512 muestras. Héroe v2 usa 4.000 y
las candidatas 4.096 con más tiempo: algoritmo y CPU no quedan aislados.

NoRegrets fue descargado y fijado por commit. Se intentó compilar con Rust
portable, pero falló el enlace por bibliotecas GNU de Windows faltantes; no se
entrenó ni integró un blueprint. El [registro técnico](../research/noregrets_feasibility_20261028/RESULTS.md)
conserva comandos, versiones y hashes.

HonestPlayer aporta una regla educativa externa de fold/call, sin pesos ni
fuerza competitiva demostrada. **No es una segunda familia aprendida.** Además,
la auditoría adicional encontró diferencias entre su evaluador original y Eval7:
62/1.000 deals de cinco jugadores y 78/1.000 de seis tuvieron distintos conjuntos
de ganadores; la regla de decisión coincidió 12/12 con el estimador controlado.
Esto no mide una tasa de decisiones distintas. La batería evalúa la adaptación
con Eval7 ya registrada, **no una reproducción exacta del agente original**.
Se conservan también ese [resultado desfavorable y su reproducción](SEGUNDA_FAMILIA_EXTERNA.md).

## Comparación principal

Diferencias pareadas frente a v2 en la mezcla diversa, dando igual peso a los
formatos de cinco y seis. Primero se promedian todos los asientos de un grupo;
se remuestrean grupos completos. Solo hay ocho grupos independientes en este
contraste, cuatro por formato. Intervalos bootstrap aproximados del 99,1667 %,
ajustados para seis contrastes principales. Con tan pocos grupos la cobertura
es frágil; las réplicas del bootstrap no crean datos nuevos.

| Candidata | Δ fichas finales / 800 [intervalo] | Δ eliminación a 128, puntos porcentuales [intervalo] | Pasa filtro |
|---|---|---|---|
| v4 | +0,157 [-0,375; +0,845] | -4,583 [-19,167; +6,250] | No |
| v4rb | +0,250 [-0,281; +0,838] | -7,500 [-21,250; +4,167] | No |
| v5 | +0,275 [-0,350; +0,801] | -6,667 [-18,333; +5,833] | No |

v4rb tuvo una diferencia media de -0,112 fichas/800 con 6 jugadores y tampoco cumplió la condición por formato.

El filtro exige evidencia favorable en **ambas** métricas: límite inferior de
fichas >0 y límite superior de diferencia de eliminación <0, más medias de
fichas no negativas en ambos formatos y verificación técnica. Las medias de
fichas y eliminación a 128 son favorables, pero todos los intervalos principales
incluyen cero. No se estima la
probabilidad de ganar PokerFight ni se pueden ordenar con confianza las
candidatas a partir de un campo tan limitado.

## Eliminaciones y censura

El piloto separado usó solo v2: 2.352 manos técnicas y 33 mesas de tres campos.
A 64 manos seguían sin terminar 17/33; a 128, 5/33. Su regla eligió 128 antes de
jugar candidatas. No cubrió todos los controles y no garantizaba esa misma tasa
en la comparación. Se mantuvieron ciegas locales fijas 50/100, sin ante ni
recompras, y se siguió cada mesa después de eliminar al héroe.

Mesas que siguen sin terminar en la misma comparación, agrupando los brazos:

| Campo | A 24 manos | A 128 manos |
|---|---:|---:|
| Presión propia | 117 / 176 | 7 / 176 |
| Copias v2 / 512 | 169 / 176 | 70 / 176 |
| Mezcla externa antigua | 154 / 176 | 8 / 176 |
| Copias v2 / 4.000 | 156 / 176 | 56 / 176 |
| Mezcla diversa adaptada | 136 / 176 | 11 / 176 |
| **Total** | **732 / 880** | **152 / 880** |

La extensión reduce censura observada, pero no la elimina. Se informa el
resultado de cada horizonte, sin convertir líderes en ganadores ni inventar
puestos para supervivientes. Victoria observada significa ser el único jugador
con fichas; es un desenlace competidor, no una eliminación ni un censurado.

Resumen descriptivo de las 220 mesas por brazo; estas medias ponderan mesas,
mientras los contrastes principales ponderan formatos por igual:

| Versión | Fichas finales medias | Eliminados a 24 / 128 | Victorias a 128 | Supervivientes censurados a 128 |
|---|---:|---:|---:|---:|
| v2 | 870,2 | 100 / 169 | 38 | 13 |
| v4 | 1447,4 | 122 / 141 | 66 | 13 |
| v4rb | 1497,8 | 120 / 138 | 68 | 14 |
| v5 | 1301,6 | 128 / 152 | 61 | 7 |

Las candidatas tienen **más eliminaciones tempranas** a 24 manos y menos
eliminaciones acumuladas a 128. No muestran una mejora uniforme de supervivencia.
En la mezcla diversa, el aumento descriptivo de eliminación a 24 es de
+12,5 puntos para v4, +9,58 para v4rb y +5,83 para v5 frente a v2. Este perfil
de riesgo importa; sin premios y reglas oficiales no se decide qué horizonte
conviene optimizar.

## Controles y resultados desfavorables

Diferencias descriptivas de bb/mano frente a v2 en reset, dando igual peso a
cinco/seis jugadores y 8/100 bb. No son contrastes confirmatorios adicionales:

| Campo | v4 | v4rb | v5 |
|---|---:|---:|---:|
| Selectivos propios | +0,732 | +0,743 | +0,472 |
| Presión propia | +0,057 | +0,341 | +0,498 |
| Copias v2 / 512 | +0,218 | +0,153 | -0,254 |
| Mezcla externa antigua | +0,533 | +0,494 | +0,398 |
| Solo Fullhouse | +0,020 | +0,009 | +0,068 |
| Copias v2 / 4.000 | +0,032 | +0,022 | -0,122 |
| Mezcla diversa adaptada | -0,128 | -0,110 | +0,150 |

Las ganancias absolutas, cada celda, intervalos, formatos y horizontes están en
[cells.csv](../results/competition_stage2_2026-10-28/cells.csv) y
[summary.json](../results/competition_stage2_2026-10-28/summary.json). No se
seleccionaron únicamente campos favorables ni se cambió el tamaño del lote al
ver ganancias.

## Verificación y contabilidad

- **115 pruebas unitarias aprobadas**, antes del registro. No se suman a la
  evidencia estratégica. La comprobación adicional de evaluadores no pasó
  paridad completa y queda expresamente separada.
- Auditorías corregidas: 64.679 ejecuciones comprobadas,
  1.232 grupos pareados de asientos y las 880 sesiones reconstruidas. Coincidieron
  48 replays de manos y 16 sesiones completas: **947 manos repetidas**,
  excluidas de las manos de comparación. Se normalizó solo tupla/lista JSON y
  se excluyeron tiempos; los demás valores y decisiones coinciden.
- Cero fallbacks, truncamientos de equity/búsqueda, acciones ilegales aceptadas
  o errores de fichas. Hubo 293 traducciones legales registradas de
  Fullhouse `all_in` a call/check cuando no existía derecho a subir.
- 4.865 semillas de mano observadas, sin solapamiento histórico. `frozen_v2`,
  fuentes y pesos conservan sus huellas; los 164 archivos sellados de la campaña
  anterior permanecen iguales.
- Mundos internos aparte: **362.774.752 de equity**,
  **19.799.552 de evaluación de búsqueda**,
  **5.138.432 de entrenamiento interno de v5**
  y **8.563.000 deals Monte Carlo de Honest**.
  No son manos reales ni réplicas independientes. Los 3.006 deals sintéticos de
  paridad y 12 casos con estimador controlado también quedan fuera.

El campo sigue siendo pequeño: un rival externo aprendido con overlay manual,
una adaptación educativa y controles propios. Fullhouse se entrenó para seis
jugadores; cinco y mesas tras eliminaciones siguen siendo transferencia. Las
eliminaciones diferentes cambian destinatarios y cartas públicas desde una
misma baraja. Las reglas oficiales, los premios y la conexión siguen pendientes.

[Método y comandos reproducibles](COMPETENCIA_SEGUNDA_METODO.md) ·
[Protocolo previo](../results/competition_stage2_2026-10-28/protocol.json) ·
[Auditoría completa](../results/competition_stage2_2026-10-28/stage2_audit.json) ·
[Pruebas](../results/competition_stage2_2026-10-28/tests_before_registration.txt) ·
[Parche revisable](../results/competition_stage2_2026-10-28/implementation.patch) ·
[Fuentes congeladas](../results/competition_stage2_2026-10-28/source/)

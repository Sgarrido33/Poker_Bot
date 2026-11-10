# Resultado de v8d: componentes y validación local

Campaña registrada el 30 de octubre de 2026, Lima. **v2 conserva el valor predeterminado.**

v8d no cumplió todos los criterios de avance registrados. No se promueve la candidata ni se elige otra variante por su mejor media posterior.

## Ejecución

Se completaron **640,391 ejecuciones nuevas de mano** en **9,636 mesas simuladas**, contando cada brazo, con 32 grupos de desarrollo y 520 de validación. Los replays y la repetición técnica de prefijos no se cuentan como evidencia nueva.

| Fase | Mesas simuladas | Manos nuevas | Verificación técnica |
|---|---:|---:|---|
| Desarrollo | 1,056 | 100,884 | Aprobada |
| Validación | 8,580 | 539,507 | Aprobada |

La candidata v8d, sus variantes y ambos tamaños de muestra se fijaron antes de observar resultados. El método y el protocolo se describen en [VALIDACION_V8D_METODO.md](VALIDACION_V8D_METODO.md). Las fuentes congeladas, cuotas y tablas se identifican con el hash de protocolo `8f763a78045dabad68f44404231b86b15988430d83b1d1d762667a1749ebe4b7`.

## Validación principal frente a los dos controles

Diferencia v8d−control en la mesa diversa externa. Fichas: intervalo bilateral del 97,5 % ajustado para los dos contrastes principales. Las otras columnas muestran intervalos descriptivos del 95 %. pp significa puntos porcentuales.

| Control | Δ fichas | Δ victorias, pp | Δ eliminación a 24, pp | Δ eliminación a 128, pp |
|---|---:|---:|---:|---:|
| v2 | +240 [+139; +342] | +7.0 [+4.9; +9.0] | +7.2 [+5.1; +9.4] | -4.4 [-6.7; -2.2] |
| v4rb | -270 [-393; -145] | -7.1 [-9.6; -4.6] | -1.3 [-3.8; +1.3] | +5.3 [+2.7; +7.9] |

La comparación principal distingue las tres versiones: v8d mejora las fichas de v2, pero v4rb supera a v8d. La candidata también aumenta la eliminación temprana frente a v2. El resultado no respalda sustituir v2 por v8d según las reglas de avance fijadas.

Los perfiles evaluados fueron v2 con 4.000 muestras/1.600 ms y v4rb con 1.024/3.500. La parte delegada de v8d usa 4.000/1.600; sus tablas deciden sin muestreo. Los resultados corresponden a estas configuraciones.

| Mesa | Versión | Fichas finales medias | Victorias | Eliminación a 24 |
|---|---|---:|---:|---:|
| external_diverse | v2 | 882 | 17.1 % | 47.2 % |
| external_diverse | v4rb | 1392 | 31.1 % | 55.7 % |
| external_diverse | v8d | 1122 | 24.0 % | 54.4 % |
| copies_v2 | v2 | 765 | 12.7 % | 44.5 % |
| copies_v2 | v4rb | 1597 | 33.1 % | 49.6 % |
| copies_v2 | v8d | 816 | 17.1 % | 64.9 % |
| selective | v2 | 1001 | 13.8 % | 39.3 % |
| selective | v4rb | 1443 | 29.1 % | 56.1 % |
| selective | v8d | 1618 | 30.5 % | 37.4 % |

| Escenario de control | Contraste | Δ fichas, IC95 | Δ eliminación a 24, IC95, pp | Límite superior unilateral 97,5 %, pp |
|---|---|---:|---:|---:|
| copies_v2 | v8d−v2 | +52 [-161; +269] | +20.4 [+13.6; +27.0] | +27.0 |
| copies_v2 | v8d−v4rb | -780 [-1082; -485] | +15.3 [+8.2; +22.6] | +22.6 |
| selective | v8d−v2 | +617 [+370; +867] | -1.9 [-7.2; +3.4] | +3.4 |
| selective | v8d−v4rb | +175 [-95; +441] | -18.7 [-26.6; -11.0] | -11.0 |

Contra copias de v2, v8d vuelve a tener más eliminación temprana y su diferencia de fichas frente a v2 sigue siendo incierta; frente a v4rb pierde fichas claramente en este control exploratorio. En la otra mesa selectiva, v8d gana fichas frente a v2 y se elimina menos temprano que v4rb, pero su ventaja de fichas frente a v4rb no es concluyente. La composición del campo importa: no conviene tratar todas las mesas selectivas como una sola categoría.

## Reglas de avance, incluidas las desfavorables

Se exigía superar ambos controles en fichas, ganar al menos 80 fichas de media, no perder media de fichas en ningún formato principal y excluir un aumento mayor de 5 pp de eliminación temprana en cada escenario. Todos los requisitos eran necesarios.

- `chips_vs_v2`: **pasa**.
- `formats_vs_v2`: **pasa**.
- `early_external_diverse_vs_v2`: **no pasa**.
- `early_copies_v2_vs_v2`: **no pasa**.
- `early_selective_vs_v2`: **pasa**.
- `chips_vs_v4rb`: **no pasa**.
- `formats_vs_v4rb`: **no pasa**.
- `early_external_diverse_vs_v4rb`: **pasa**.
- `early_copies_v2_vs_v4rb`: **no pasa**.
- `early_selective_vs_v4rb`: **pasa**.

Los intervalos que incluyen cero no prueban equivalencia. No pasar un límite de deterioro puede indicar daño observado o precisión insuficiente: las estimaciones e intervalos anteriores distinguen esos casos.

## Qué ocurre al separar componentes

Solo desarrollo: 8 grupos por formato y escenario. Cada componente activa tanto las acciones como los folds de su contexto; las demás decisiones son v2. Los intervalos son descriptivos sin ajuste por múltiples comparaciones. No se seleccionó una variante ganadora con estos datos.

| Mesa | Versión frente a v2 | Δ fichas, IC95 | Δ eliminación a 24, IC95, pp | Δ victorias, IC95, pp |
|---|---|---:|---:|---:|
| copies_v2 | v8 | -170 [-431; +87] | +29.0 [+17.3; +42.9] | +0.0 [-5.8; +5.8] |
| copies_v2 | v8d | -170 [-429; +87] | +26.7 [+16.0; +38.3] | +0.0 [-5.8; +5.8] |
| copies_v2 | v8d_open | -406 [-688; -126] | +18.5 [+4.8; +33.3] | -5.6 [-11.5; +0.6] |
| copies_v2 | v8d_reshove | -218 [-462; +66] | +20.2 [+12.5; +28.1] | +0.2 [-6.9; +7.7] |
| copies_v2 | v8d_call | -27 [-104; +53] | +4.4 [-1.0; +10.0] | +0.0 [-3.1; +3.1] |
| selective | v8 | +793 [+487; +1108] | +1.2 [-8.8; +11.7] | +18.7 [+11.5; +26.2] |
| selective | v8d | +761 [+419; +1110] | +1.5 [-7.5; +10.6] | +18.1 [+11.0; +26.5] |
| selective | v8d_open | +338 [+25; +672] | +0.2 [-8.1; +6.5] | +6.7 [+0.2; +12.5] |
| selective | v8d_reshove | +223 [-126; +592] | +4.0 [-4.6; +12.5] | +3.3 [-3.8; +10.4] |
| selective | v8d_call | -35 [-147; +76] | -2.3 [-5.6; +0.0] | -2.5 [-6.2; +0.0] |

La comparación registrada con la v8 histórica separa el efecto de la corrección del efecto conjunto de las tablas. Sigue siendo desarrollo, con intervalos descriptivos del 95 %.

| Mesa | Δ fichas v8d−v8 | Δ eliminación a 24, pp, v8d−v8 |
|---|---:|---:|
| copies_v2 | +0 [+0; +0] | -2.3 [-7.1; +2.5] |
| selective | -31 [-258; +231] | +0.2 [-2.9; +3.8] |

Estas diferencias comparan trayectorias completas de políticas. No identifican la pérdida contrafactual de cada shove o call, ni justifican extrapolar la mejor media a otras mesas.

En este desarrollo, activar solo aperturas o solo re-shoves elevó la eliminación temprana contra copias de v2. El contraste de solo calls fue menor e incierto. La candidata completa, en cambio, ganó fichas en la otra composición selectiva. Esto apunta a estudiar por separado los componentes de apuesta y las familias de rivales; no demuestra que los calls sean inocuos ni que un solo componente explique toda la diferencia de v8d.

Un diagnóstico posterior del brazo v8d describe las respuestas públicas en las situaciones alcanzadas. Excluye all-ins forzados ya presentes y cuenta calls o raises posteriores como continuación. Es exploratorio, no una prueba registrada ni una comparación de manos equivalentes.

| Mesa | Acción de v8d | Casos | Al menos un rival continuó |
|---|---|---:|---:|
| copies_v2 | open | 331 | 43.5 % |
| copies_v2 | reshove | 110 | 98.2 % |
| selective | reshove | 243 | 41.6 % |
| selective | open | 766 | 13.1 % |

En esas trayectorias, las copias de v2 continuaron mucho más contra los shoves que la otra mesa selectiva. La etiqueta tight describe mal por sí sola las respuestas frente a distintas apuestas. Las posiciones, profundidades y manos alcanzadas también cambian: estos porcentajes no aíslan causalmente la familia rival ni son rangos de call calibrados.

En el brazo v8d de desarrollo, el guard de profundidad intervino 259 veces; la v8 histórica habría usado tablas en esas 259 observaciones y habría elegido otra acción en 66. Esto compara acciones ante la misma información, no resultados contrafactuales de sesiones.

El mayor exceso detectado en esos estados fue una tabla de 3.5 bb que habría expuesto 17.5 bb. La acción de v8d fue `fold`. Caso: selective, 5 jugadores, grupo 6, rotación 2, índice de mano 56.

El [diagnóstico completo](../results/v8d_validation_2026-10-30/development/response_diagnostics.json) identifica el script, las exclusiones y los recuentos. Se añadió después del desarrollo y no modifica el criterio de promoción.

## Alcance de la corrección y auditoría

v8d delega en v2 una respuesta no terminal cuando otro rival activo puede cubrir más que el raiser usado para elegir la tabla. Actualiza el historial en cada solicitud y hace visibles los errores de tabla. No se alteraron las tablas históricas ni la v8 original. La arena ya completaba el historial al final de cada mano; la omisión del bot importa al operar sin ese hook y no demuestra pérdida de historial en las campañas locales.

- development: 192 manos de replay exacto; 100,884 manos reconstruidas desde trazas; 0 fallbacks, 0 cortes de equity y 0 cortes de búsqueda. Se observaron 559 delegaciones del héroe por el nuevo límite de profundidad, sumando los brazos v8d de esta fase.
- validation: 144 manos de replay exacto; 539,507 manos reconstruidas desde trazas; 0 fallbacks, 0 cortes de equity y 0 cortes de búsqueda. Se observaron 2,351 delegaciones del héroe por el nuevo límite de profundidad, sumando los brazos v8d de esta fase.

La reconstrucción comprueba además el espacio de semillas registrado, las semillas de cada política, el botón y los asientos, las cartas del héroe y el tablero prefijados y la identidad de las observaciones.

La primera ejecución se interrumpió porque las herramientas no mostraban las escrituras en curso. Se conservaron las seis trazas parciales y sus hashes; después se repitieron las mismas semillas. Coincidieron exactamente **10,997 registros de prefijo**, salvo tiempos. Esas repeticiones no aumentan la muestra. La incidencia está documentada en `results/v8d_validation_2026-10-30/interruption_001.json`.

La suite completa de implementación pasó 212 pruebas; el log está en `.tmp/v8d_full_tests.txt`. El auditor adicional se comprobó con una sesión técnica válida y rechazó alteraciones de métricas, trazas, semillas y cartas.

## Límites de la conclusión

La evaluación usa 800 fichas, ciegas fijas 50/100, sin ante y hasta 128 manos. No reproduce la puntuación ni el formato oficial aún no establecido para este trabajo. Fullhouse y Honest aportan familias concretas; repetir instancias no convierte ese campo en una muestra representativa de rivales. Las cuotas de cómputo difieren entre v4rb y v2/v8d. Las aproximaciones del modelo push/fold permanecen. El resultado decide el avance local bajo las reglas registradas, no una probabilidad de clasificación al torneo.

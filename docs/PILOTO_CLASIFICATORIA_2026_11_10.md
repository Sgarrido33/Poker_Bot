# Validación del cliente y piloto de la clasificatoria

**10 de noviembre de 2026.** Se mantiene `v2` como versión de entrega. Clasificó en 9 de 12 pares frente a 8 de 12 de `v4rb`. Ambas políticas respondieron con margen en la arena del kit. La validación con otros equipos sigue pendiente porque el servidor de práctica no aceptó la conexión TCP.

## Cliente local

El cliente abre una conexión con el token del equipo y vuelve a usarlo después de un corte. Conserva las cartas y apuestas iniciales de la mano en curso si coinciden el alias y el identificador de mano. Si faltan esos datos, usa el `check` o `fold` autorizado por el servidor. Si vence el límite local, evita enviar una acción que podría aplicarse al turno siguiente.

La prueba TCP controlada cortó la conexión a mitad de un mensaje de una mano de cinco jugadores. `v2` volvió a saludar en 278 ms y retomó esa mano sin volver a recibir sus cartas. Tras 180 segundos sin mensajes, la misma conexión recibió una mesa de seis con 10 150 fichas acumuladas. El servidor de prueba recibió las dos jugadas válidas en 75 y 90 ms desde sus solicitudes. El cierre programado se comprobó con el servidor en silencio. Pasaron las 216 pruebas de la suite. [Bitácora de la prueba](../results/local_connection_v2_final_2026-11-10.jsonl)

Se ejecutaron además tres partidas de 50 manos en la arena del kit con un plazo de 5 segundos. El tiempo va desde la recepción de la línea del turno hasta completar el envío de la respuesta. El contador de la arena incluye acciones inválidas y respuestas fuera de plazo.

| Política y mesa | Jugadas | p95 | Máximo | Timeouts de la arena |
| --- | ---: | ---: | ---: | ---: |
| v2, 5 jugadores, 100 BB | 90 | 75,5 ms | 77,4 ms | 0 |
| v4rb, 6 jugadores, 100 BB | 89 | 29,1 ms | 31,6 ms | 0 |
| v4rb, 6 jugadores, 12 BB | 88 | 49,1 ms | 212,5 ms | 0 |

Las configuraciones, las jugadas públicas y el resumen que emitió la arena están en [los resultados del kit](../results/official_kit_2026-11-10).

## Servidor de práctica

La dirección de la guía del equipo, `32.201.29.142:9000`, agotó el plazo TCP en nueve intentos. El cliente no llegó a enviar el saludo ni a validar la credencial. La bitácora contiene la última serie de cuatro intentos. [Conectividad de práctica](../results/practica_conectividad_2026-11-10.jsonl)

Cuando el puerto responda, el siguiente comando registra hasta 30 minutos de práctica con la credencial cargada en `POKERFIGHT_TOKEN`.

```powershell
.\.venv\Scripts\python.exe -m pokerfight.official -addr 32.201.29.142:9000 --duration 1800 --journal results/practica_v2.jsonl
```

`action_sent` registra la latencia de cada respuesta. `action_outcome` compara la jugada con el historial público y distingue coincidencias, sustituciones y jugadas sin confirmación. El protocolo puede omitir del historial visible la última acción de una mano. También puede aplicar una acción segura idéntica a la enviada, por lo que las coincidencias no permiten contar todos los rechazos. La bitácora conserva las acciones por alias y las cartas que los rivales mostraron en el showdown.

## Piloto por pares

Cada torneo tuvo 11 participantes, 10 rondas, ciegas fijas 50/100 y 10 000 fichas iniciales. Tras cada ronda se sortearon los jugadores con saldo positivo y se mantuvo su stack. Cada mesa paró al quedarse con un jugador, al llegar a 50 manos o al alcanzar seis minutos entre manos. El límite de tiempo no se activó en el piloto. Las 24 simulaciones completaron 16 167 ejecuciones de mano.

Se usaron seis pares con un campo diverso y seis con un campo selectivo. Cada par compartió los perfiles rivales y las semillas del sorteo, los bots y las barajas. Cuando las políticas eliminaron a jugadores distintos, el siguiente sorteo aplicó el mismo orden aleatorio a los supervivientes de cada versión. Eso puede cambiar los asientos y las cartas que recibe un jugador concreto. Se usaron mesas equilibradas de menos de cinco si la cantidad de supervivientes impedía armar mesas de cinco y seis. Si quedaban menos de seis supervivientes al final, se completó el top 6 por ronda y mano de eliminación, de más reciente a más antigua. Los empates restantes se resolvieron con un sorteo fijo por semilla.

| Campo | v2 top 6 | v4rb top 6 | Solo v2 | Solo v4rb |
| --- | ---: | ---: | ---: | ---: |
| Diverso | 5/6 | 4/6 | 1 | 0 |
| Selectivo | 4/6 | 4/6 | 0 | 0 |
| Total | 9/12 | 8/12 | 1 | 0 |

Cada política se quedó sin fichas en siete torneos. Cuatro de las clasificaciones de `v2` y tres de las de `v4rb` entraron por la regla que completa los seis puestos con los últimos eliminados. El único par discordante fue el de la semilla 20261112. En ese par, `v2` quedó quinta y `v4rb` octava.

| Ronda | Fichas medias v2 | Fichas medias v4rb | Eliminaciones v2 | Eliminaciones v4rb |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 11 246 | 11 319 | 2 | 2 |
| 2 | 12 867 | 12 691 | 0 | 0 |
| 3 | 12 790 | 11 002 | 3 | 3 |
| 4 | 12 679 | 10 861 | 1 | 2 |
| 5 | 13 698 | 12 475 | 0 | 0 |
| 6 | 13 886 | 11 973 | 0 | 0 |
| 7 | 14 357 | 13 577 | 1 | 0 |
| 8 | 15 187 | 14 680 | 0 | 0 |
| 9 | 16 069 | 14 991 | 0 | 0 |
| 10 | 15 156 | 15 211 | 0 | 0 |

Las fichas medias incluyen los ceros de los eliminados. El piloto es pequeño y el campo es simulado. La ventaja de 55 fichas medias de `v4rb` no vino acompañada de más clasificaciones. [Sorteos, fichas y eliminaciones por torneo y ronda](../results/qualifier_pilot_2026-11-10.json)

## Reproducción

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_official_connection --idle-seconds 180 --journal results/local_connection_repeticion.jsonl
.\.venv\Scripts\python.exe -m scripts.qualifier_pilot --pairs 12 --workers 6 --seed 20261110 --output results/qualifier_pilot_repeticion.json
```

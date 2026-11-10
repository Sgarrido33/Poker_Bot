# Segunda batería local de bot contra bot

28 de octubre de 2026. **v2 sigue predeterminada.** Las reglas oficiales y la
conexión siguen pendientes. Esta batería usa reglas locales, no las atribuye al
torneo y no permite promover automáticamente ninguna candidata.

La ejecución está completa: [resultados y auditorías](COMPETENCIA_SEGUNDA_RESULTADOS.md).

## Rivales y controles

Se conservan los cinco escenarios anteriores: `selective`, `pressure`,
`copies_v2`, `external_mix` y `external_only`. Se añaden:

| Escenario | Rivales de cinco jugadores | Sexto jugador |
|---|---|---|
| copies_v2_4000 | Cuatro copias v2, cada una con 4.000 muestras y 1.600 ms | Otra copia igual |
| external_diverse | Fullhouse, HonestPlayer, v2 de 4.000 muestras, pressure | Otro Fullhouse |

Las copias rivales antiguas conservan 512 muestras/1.600 ms; la nueva etiqueta
`v2_4000` fija explícitamente 4.000/1.600, sin heredar la cuota de la candidata.
TAG/LAG/pressure conservan su cálculo anterior. Héroe v2: 4.000/1.600;
candidatas v4/v4rb/v5: 4.096/3.500. No se aísla completamente algoritmo de CPU.

[HonestPlayer](SEGUNDA_FAMILIA_EXTERNA.md) es una segunda política de autor
independiente, pero es un ejemplo educativo de fold/call contra manos uniformes,
sin pesos entrenados, posiciones, rangos ni precio del call. No representa un
segundo rival aprendido o de fuerza competitiva demostrada. Se preservan 1.000
simulaciones, empates como victoria y umbral 1/n; Eval7 reemplaza su evaluador.
El tamaño inicial de mesa se mantiene después de eliminaciones, como en su
callback original. Fullhouse conserva su red y overlay manual hasta 12 bb; sus
instancias cuentan como una familia. NoRegrets fue investigado e intentado, pero
no integrado: el repositorio público carece de blueprints. Después se descargó
su fuente y se intentó compilar con Rust portable; el enlace de Windows falló
por bibliotecas GNU faltantes. Su interfaz exige además un bridge y entrenamiento.
El [registro técnico](../research/noregrets_feasibility_20261028/RESULTS.md)
conserva versiones, huellas, comandos y errores.

Una auditoría técnica adicional durante la ejecución encontró diferencias entre
los ganadores calculados por el evaluador antiguo de PyPokerEngine y Eval7:
62/1.000 deals de cinco y 78/1.000 de seis jugadores. La regla con estimador
controlado coincidió 12/12. Por ello la batería mide expresamente la política
**adaptada con Eval7**, no una réplica fiel del runtime original. La
[comprobación de paridad](../research/honest_parity_20261028/SUMMARY.md)
queda aparte, con su propia huella y sin cambios de la política registrada.

## Piloto y registro previo

El piloto tiene **solo héroe v2**: mezcla externa antigua, copias v2 de 4.000 y
mezcla diversa; ambos formatos; un grupo por estrato y todas las rotaciones:
33 mesas, máximo 128 manos. Son pruebas técnicas, excluidas de las manos de
comparación. Mide finalización a 64 y 128 manos, sin mirar diferencias entre
candidatas, que todavía no existen.

La regla registrada elige el primer horizonte con ≤25 % de mesas sin terminar
en total y ≤35 % en cada formato. Si ninguno cumple, fija 128 y declara que la
meta técnica no se logró. El piloto no autoriza aumentar la cantidad de grupos,
modificar estrategias ni cambiar condiciones según las ganancias.

Antes del piloto se fija la matriz posterior: siete escenarios, cinco/seis
jugadores, stacks reiniciados de 8/100 bb, ocho bloques independientes por celda,
todos los asientos y cuatro brazos: **4.928 ejecuciones, 224 bloques base**.
Sesiones: pressure, copies_v2, external_mix, copies_v2_4000 y external_diverse;
ambos formatos, **cuatro grupos independientes por estrato**, todos los asientos
y cuatro brazos: **880 mesas, 220 por brazo**, agrupadas en 40 grupos. El límite
sale de la regla del piloto y queda registrado antes de jugar candidatas.

Stack inicial 800, ciegas fijas 50/100, sin ante ni recompras. Se sigue cada mesa
después de la eliminación del héroe. El máximo de manos es administrativo: el
líder no recibe una victoria o un puesto final. Las eliminaciones simultáneas
comparten puestos. Usar Fullhouse con cinco o después de eliminaciones sigue
siendo transferencia de su modelo de seis jugadores.

Cada fase tiene identificador y carpeta nuevos. `protocol.json`, su SHA-256,
el snapshot `source/`, los pesos/licencias/manifiestos y las versiones quedan
sellados. Reanudar verifica esas huellas. Se comprueban las semillas previstas
contra las trazas históricas, incluido el piloto. Cuatro procesos ejecutan
trabajos completos disjuntos, sin compartir estado de rivales. Cualquier corte
por reloj, fallback o problema legal invalida la inferencia; no se repite un
lote por ser desfavorable.

## Medición e inferencia

Los brazos comparten barajas, semillas de políticas y rotaciones. Tras
eliminaciones distintas una semilla por índice de mano puede repartir a
jugadores distintos; al cambiar el número de asientos cambia también el offset
de cartas públicas. Se comparte el orden de la baraja, no se garantiza idéntica
mesa pública después de trayectorias de eliminación diferentes. Ninguna política recibe baraja,
semilla de reparto ni cartas ocultas ajenas; las observaciones son propias y
públicas. Los identificadores públicos son opacos.

Los dos resultados principales son las diferencias frente a v2 en
`external_diverse`: fichas finales/800 y probabilidad observada de eliminación
al límite H. Se promedian diferencias pareadas entre rotaciones del mismo grupo
y luego los estratos de cinco/seis jugadores con igual peso. Se remuestrean
grupos completos dentro de estrato, 10.000 veces. Intervalos percentiles
aproximados del 99,1667 %: Bonferroni para tres candidatas por dos resultados.
Cuatro grupos por estrato siguen siendo pocos; el bootstrap no crea evidencia.

El filtro de seguimiento exige límite inferior de fichas >0, límite superior
de diferencia de eliminación <0, medias de fichas no negativas en ambos
formatos y auditorías técnicas aprobadas. **Aunque se cumpla, v2 sigue por
defecto.** El reset, los controles y los demás horizontes son diagnósticos;
no se les atribuye confirmación independiente o cobertura simultánea.

Se informa por horizonte disponible (24, 64 y H): eliminado, victoria observada
como único superviviente, resultado aún sin resolver y finalización de mesa.
Una victoria es un desenlace competidor, no una eliminación ni un censurado.
No se calcula una probabilidad de ganar el torneo ni se asignan rangos a los
supervivientes censurados. Fichas finales es un resultado observado a H, no
equity de premios. Los replays, pruebas, simulaciones de equity, búsqueda,
entrenamiento interno de v5 y deals Monte Carlo de Honest se cuentan aparte.

## Reproducción

Desde la raíz, PowerShell y el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Cada repetición requiere otras carpetas E identificadores.
.\.venv\Scripts\python.exe -m scripts.competition_stage2 register --phase pilot --root results/competition_stage2_pilot_repeat --id stage2-duration-pilot-repeat
.\.venv\Scripts\python.exe -m scripts.competition_stage2 run --root results/competition_stage2_pilot_repeat
.\.venv\Scripts\python.exe -m scripts.audit_competition_stage2 --root results/competition_stage2_pilot_repeat
.\.venv\Scripts\python.exe -m scripts.competition_stage2 summarize --root results/competition_stage2_pilot_repeat

.\.venv\Scripts\python.exe -m scripts.competition_stage2 register --phase comparison --root results/competition_stage2_repeat --id stage2-comparison-repeat --pilot-root results/competition_stage2_pilot_repeat
.\.venv\Scripts\python.exe -m scripts.competition_stage2 run --root results/competition_stage2_repeat
.\.venv\Scripts\python.exe -m scripts.audit_competition_stage2 --root results/competition_stage2_repeat --replay
.\.venv\Scripts\python.exe -m scripts.competition_stage2 summarize --root results/competition_stage2_repeat
```

El auditor complementario ejecuta primero los dos auditores corregidos
`research/competition_audit_20261028/audit_registered.py` (misma función y
comparador normalizado) y `audit_sessions.py`; añade cobertura exacta del
producto bloque × asiento × brazo, reconstrucción de contadores y eliminaciones
por horizonte, y replay de sesiones diverse grupo 0/asiento 0, todos los brazos
y formatos. El auditor original también repite resets de celdas cuyo nombre
empieza por `external`; conserva esa selección previa. Se comparan todos los
valores de decisión, cartas y trayectorias salvo tiempos, normalizando solamente
tuplas/listas JSON. Los replays nunca cuentan como nueva rentabilidad.

Para reejecutar el artefacto original con su identificador se restaura `source/`
en otro directorio y se instalan las versiones registradas. Para evidencia nueva
se exige otro identificador. Todos los resultados observados pasan a desarrollo.

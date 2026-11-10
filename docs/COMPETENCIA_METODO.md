# Primera batería de cross-play

28 de octubre de 2026. Investigación local; la política predeterminada sigue siendo **v2**.

El [protocolo JSON](../results/competition_2026-10-28/protocol.json) se escribe antes de jugar. Su SHA-256 queda en otro archivo y cada resultado lo referencia. Se conserva una copia de las fuentes, dependencias, pesos y manifiestos en `source/`. El ejecutor rechaza cambios en código, pesos, versiones o protocolo al reanudar. Todos los datos anteriores son desarrollo; esta campaña también pasa a desarrollo al examinarla. No se ajustan estrategias ni cantidades al mirar resultados.

## Contra quién jugamos

Se comparan v2 original, v4, v4rb y v5. Cinco escenarios, con idénticas familias y cantidades de rivales en todos los brazos:

| Escenario | Lista que se repite hasta llenar los 4/5 asientos rivales | Independencia |
|---|---|---|
| selective | TAG, TAG, LAG | Reglas sintéticas del proyecto; comparten tablas y estimador |
| pressure | pressure, LAG, TAG | Reglas sintéticas del proyecto |
| copies_v2 | v2 | Una familia propia congelada; semillas distintas no crean estrategias independientes |
| external_mix | Fullhouse, v2, Fullhouse, pressure, LAG | Dos instancias de una familia externa, más controles propios |
| external_only | Fullhouse | Una sola familia externa; diagnóstico de ese emparejamiento |

Con cinco jugadores external_mix tiene dos Fullhouse, una v2 y un pressure; con seis añade un LAG. No se cambia la mezcla entre versiones. Fullhouse es el código y modelo publicados por [Advit Arora](https://github.com/advitrocks9/fullhouse-bot/tree/e504793d480b1b975f25258d25939b45c6dbd5a4); la [investigación de alternativas](RIVALES_EXTERNOS_INVESTIGACION.md) documenta disponibilidad, licencia y límites. No se añade ningún rival sintético nuevo.

El adaptador preserva las 51 características, cinco acciones, pesos y chart preflop. La red toma decisiones fuera del overlay de hasta 12 bb. Importaciones relativas y datos fijados evitan cargar otro paquete o pesos por una variable de entorno. El generador de acciones pertenece a cada instancia. Se evita el `except Exception` del upstream: un error detiene la campaña. Un pedido `all_in` se traduce a call si el contrato no permite resubir; se cuenta aparte. No se corrigen silenciosamente otras propuestas ilegales.

Solo se envía `Observation`: cartas propias, mesa pública, stacks, apuestas e historial. Los identificadores públicos son opacos y no contienen la semilla de baraja. La traducción reconstruye apuestas y las comprueba contra el estado público. Exige ciegas fijas 50/100, sin ante, e historial completo. Son supuestos **locales**, no reglas oficiales. El modelo fue creado para 6-max: ejecutarlo con cinco o menos participantes es transferencia, sin afirmar que haya sido entrenado para ellos.

## Cantidades y criterios fijados

- Fichas reiniciadas: 5 escenarios × 2 formatos (5/6) × 2 stacks (8/100 bb) = **20 celdas**. Ocho bloques independientes por celda, un reparto por bloque, todas las rotaciones cíclicas y cuatro brazos: **3.520 ejecuciones de mano**, 880 por brazo. Las 160 barajas base no equivalen a 3.520 observaciones independientes.
- Eliminación: pressure, copies_v2 y external_mix; ambos formatos; **tres grupos de semillas** por estrato; todas las rotaciones: **99 mesas por brazo**, 396 en total. Stack 800, máximo 24 manos, ciegas fijas 50/100, sin recompras ni ante. Máximo teórico: 9.504 ejecuciones. Se sigue la mesa aunque el héroe haya sido eliminado.
- Héroe v2: 4.000 muestras/1.600 ms; candidatas: 4.096/3.500 ms. Rivales v2: 512/1.600 ms; reglas: 256 postflop; Fullhouse: pesos fijos, sin entrenamiento online. No hay igualdad de CPU entre héroes; las cuotas rivales sí son constantes.
- Contraste principal: diferencia pareada de bb/mano frente a v2 en external_mix, dando igual peso a sus cuatro celdas. Los demás escenarios son diagnósticos, incluidos los desfavorables.
- Se remuestrean bloques enteros dentro de cada celda. Para sesiones, primero se promedian rotaciones del mismo grupo y después se remuestrean grupos dentro de escenario/formato. Bootstrap de 10.000 réplicas; intervalos de 98,333 % por candidata (Bonferroni para tres comparaciones frente a v2). No ofrecen cobertura simultánea de todos los diagnósticos. Ocho bloques y tres grupos son muestras pequeñas; la cobertura aproximada puede ser deficiente.
- Señal para ampliar la investigación: límite inferior principal >0, medias no negativas en ambos formatos y límite inferior de fichas finales/800 no negativo en las sesiones external_mix. Sin fallbacks, errores legales, pérdidas de fichas ni truncamientos por reloj. **No se permite promover una candidata en esta primera batería**, aunque pase ese filtro.

Las barajas y semillas de políticas coinciden entre brazos. Los bloques de reset rotan todos los asientos; no enumeran todas las permutaciones de rivales. Las sesiones comparten la secuencia por índice de mano y rotan el asiento inicial: después de eliminaciones distintas, la misma semilla puede repartir cartas a jugadores distintos. Eso limita la reducción de varianza. No se denomina AIVAT a este diseño; véase [evaluación académica](EVALUACION_ACADEMICA.md).

Se informa ganancia bruta y diferencia por celda; fichas finales, eliminación, victorias observadas y censura por sesión. Un superviviente al límite de manos no recibe una victoria ni una clasificación final inventada. Las eliminaciones simultáneas comparten los puestos correspondientes. Las tablas sin terminar siguen censuradas aunque alguien lidere en fichas.

## Reproducir

Desde la raíz del proyecto en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-evaluation.txt
.\.venv\Scripts\python.exe -m scripts.fetch_fullhouse_reference
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Usar carpeta E identificador nuevos: cambiar solo la carpeta no cambia barajas.
.\.venv\Scripts\python.exe -m scripts.competition_experiment register --root results/competition_repeat --id crossplay-fullhouse-repeat-02
.\.venv\Scripts\python.exe -m scripts.competition_experiment run --root results/competition_repeat
.\.venv\Scripts\python.exe -m scripts.competition_experiment summarize --root results/competition_repeat
.\.venv\Scripts\python.exe -m research.competition_audit_20261028.audit_registered --root results/competition_repeat --replay
.\.venv\Scripts\python.exe -m research.competition_audit_20261028.audit_sessions --root results/competition_repeat --replay

# Partida local, bajo las restricciones de ciegas del adaptador
.\.venv\Scripts\python.exe -m pokerfight simulate --players 6 --hands 20 --opponents fullhouse v2 pressure --hero v2
```

`run --shard N --shards K` permite procesos independientes; no ejecutar dos veces el mismo shard a la vez. La ejecución publicada usa un proceso para evitar competencia por el presupuesto temporal. Se reanuda por trabajo completo, verificando las huellas de las trazas. `summarize` rechaza campañas incompletas.

Las pruebas de contrato, trayectorias de comprobación y replays son **verificación técnica**, no observaciones de rentabilidad nuevas. El auditor repite de antemano bloque 0/asiento 0 de cada brazo/celda externa (32 manos), compara decisiones y valores sin tiempos, comprueba reparto/semillas y busca intersecciones con semillas históricas. Los mundos internos de equity, entrenamiento de continuación de v5 y evaluación de búsqueda se contabilizan por separado de las manos resueltas realmente por PokerKit.

Una revisión estática durante la ejecución, sin consultar ganancias, motivó una auditoría técnica adicional en `research/competition_audit_20261028/audit_sessions.py`. Reconstruye todos los stacks, transiciones, eliminaciones, contadores y censura desde los JSONL, y coteja cada campo del resumen. Reproduce además las sesiones external_mix del grupo 0/asiento 0 de todos los brazos y formatos (ocho mesas). Guarda su propia huella y las de los archivos auditados. Este añadido no cambia el código de juego registrado ni el estimando. Los comandos de ejecución y replay requieren el mismo checkout y versiones; la instantánea `source/` es recuperable copiándola a un directorio de trabajo con las dependencias registradas.

El comando complementario `audit_registered` normaliza tuplas/listas mediante JSON para comparar trazas: el auditor original conservado en la instantánea daba un falso negativo por esa representación. Los valores numéricos y las decisiones se comparan exactamente; únicamente se excluye `elapsed_ms`. El añadido técnico, su versión inicial y la corrección final se conservan en `technical_addendum/`, con huellas separadas del código de juego registrado.

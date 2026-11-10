# Comparación de calidad: integración de respuestas y resubidas

Fecha local: 28 de octubre de 2026. La política predeterminada permanece en **v2**.

Esta iteración investiga dos fuentes diferentes de error de v4: el ruido de muestrear las respuestas rivales y el sesgo de omitir las resubidas. Las candidatas se pueden ejecutar desde `decide`, `serve`, `simulate` y `evaluate`: `v4rb` y `v5`. Ambas conservan el alcance preflop de hasta 12 bb efectivas y la excepción de precio para calls all-in. Las decisiones profundas y postflop conservan la política base.

## v4rb: integrar las respuestas

`IntegratedAction` reutiliza los árboles y pozos preparados de v4. En cada mundo de cartas calcula la esperanza de todas las hojas fold/call, con sus probabilidades y precios dependientes de las llamadas anteriores. Hay como máximo 32 hojas. Es una aplicación de esperanza condicional o Rao–Blackwell: elimina el sorteo Bernoulli de respuestas manteniendo muestreadas las manos rivales y la mesa.

El modelo de conducta, las acciones candidatas, la referencia v2, el margen de 0,05 bb y la selección de dos errores estándar conservan las definiciones de v4. Las muestras consumen más CPU. La reducción de varianza a igual número de mundos no implica una mejora a igual tiempo ni una mejora de ganancias. La regla adaptativa de dos errores estándar continúa siendo heurística.

## v5: una resubida all-in y continuación pública

`ResponseRollout` permite fold, call y una subida all-in rival. Después de esa subida, los jugadores anteriores que deben más fichas vuelven a responder en orden; el héroe puede pagar o retirarse. El cálculo mantiene contribuciones, dinero retirado, pozos laterales y devoluciones. Los jugadores sin fichas no se retiran. Las apuestas cortas y su acumulación se comparan con el último precio que enfrentó cada jugador para determinar si se reabrió su derecho a subir.

Se parte del mismo conjunto legal de acciones que v4. Las probabilidades de continuar utilizan sus tres supuestos de conducta. La fracción que resube se define con una curva logística de fuerza preflop, umbrales 0,86/0,80/0,74 y frecuencias máximas 0,45/0,60/0,75. Son hipótesis manuales de sensibilidad, sin calibración en rivales externos.

La mitad de los mundos aprende el valor de pagar después de una resubida. La clave de cada decisión contiene solo acciones y cantidades públicas hipotéticas, contribuciones, jugadores retirados y precio. Se fuerza el call en esa fase para estimar su valor contrafactual frente a retirarse. El bot hipotético paga cuando hay al menos 16 visitas y la media menos un error estándar supera 0,02 bb; en otros casos se retira.

La otra mitad de los mundos evalúa las acciones iniciales usando esas decisiones ya fijadas, con un generador separado. No se elige pagar viendo quién gana en el mundo oculto evaluado. Los mundos y uniformes se comparten entre acciones y supuestos para formar diferencias pareadas. Se exige una ganancia conservadora superior a 0,05 bb bajo los tres supuestos; si vence el reloj o hay rangos incompatibles, se conserva la decisión base.

La continuación es una política de rollout aproximada, diferente para cada supuesto. **No se guarda como un compromiso para decisiones futuras reales**: cuando vuelve a actuar, v5 estima de nuevo con el estado observado. Por eso el valor del rollout no representa exactamente el comportamiento futuro del bot desplegado. Los nodos públicos específicos pueden tener pocas visitas y producir un exceso de folds. Solo se modela una resubida rival; siguen faltando las subidas normales posteriores, más resubidas y apuestas postflop. Las ramas que terminan con fichas detrás se valoran como checkdown.

## Registro y evaluación

La implementación anterior está conservada completa en `research/policy_snapshots/pre_quality_20261028`, con su huella. `frozen_v2` permanece intacta. `scripts.verify_quality_controls` compara búsquedas con trabajo fijo y manos completas contra esa instantánea.

El protocolo `results/quality_2026-10-28/protocol.json` se guarda antes del piloto. La matriz tiene 18 celdas: cinco/seis jugadores, 4/8/12 bb y rivales selectivos, de presión y copias v2. Se ejecutan cinco brazos con las mismas barajas y semillas de políticas: v2 original, v2mc, v4, v4rb y v5. Las cartas y los resultados son fijados por PokerKit, independientemente del modelo de búsqueda.

El héroe usa 4 096 muestras y 3 500 ms en todos los brazos ampliados. La base preflop consume hasta 4 000 muestras; la cuota de búsqueda es adicional. v5 divide su cuota de búsqueda entre entrenamiento y evaluación; v4/v4rb pueden parar antes. El control original utiliza 4 000/1 600 ms y los rivales v2 mantienen una cuota fija de 512. Los rivales de reglas conservan su estimador de 256 muestras. Por tanto, son comparaciones de políticas y asignación de cálculo, sin igualdad exacta de CPU.

El piloto tiene dos bloques por celda y la validación seis, con namespaces distintos. Cada bloque contiene un reparto y todas las rotaciones de asiento. Se remuestrean bloques completos dentro de cada celda y se da el mismo peso a las dieciocho celdas. La validación añade mesas de eliminación en presión/copias v2: dos grupos de semillas por escenario y formato, todos los asientos, inicio 8 bb, máximo veinte manos y ciegas duplicadas cada diez. Los intervalos de sesiones remuestrean grupos completos dentro de escenario/formato.

No se ajustan parámetros después del piloto. Para promover una candidata se requiere una mejora con límite inferior positivo frente a v4 y v2, media no negativa en cada formato, límite inferior no negativo en fichas finales de sesiones y ausencia de errores de seguridad. Los intervalos son exploratorios y no corrigen la comparación de dos candidatas. No representan probabilidades de clasificación al torneo.

## Reproducir

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.verify_quality_controls
.\.venv\Scripts\python.exe -m scripts.benchmark_quality_variance

# Una nueva campaña: el identificador cambia realmente las barajas.
.\.venv\Scripts\python.exe -m scripts.quality_experiment register --root results/quality_repeat --id quality-repeat-02
.\.venv\Scripts\python.exe -m scripts.quality_experiment run --root results/quality_repeat --phase pilot
.\.venv\Scripts\python.exe -m scripts.quality_experiment summarize --root results/quality_repeat --phase pilot
.\.venv\Scripts\python.exe -m scripts.quality_experiment run --root results/quality_repeat --phase validation
.\.venv\Scripts\python.exe -m scripts.quality_experiment summarize --root results/quality_repeat --phase validation

# Decisión supervisada de cada candidata
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v4rb --samples 4096
.\.venv\Scripts\python.exe -m pokerfight decide examples/shortstack_search.json --policy v5 --samples 4096
```

`--shard N --shards K` divide los trabajos de una fase entre procesos. Cada celda se guarda de forma independiente y contiene un JSONL con observaciones y decisiones propias. El supervisor mantiene su corte local de 4 250 ms; los candidatos son experimentales y la conexión oficial sigue pendiente.

Los comandos anteriores eligen explícitamente el perfil medido de 4 096 muestras. La CLI conserva 16 384 como solicitud predeterminada para las políticas de cómputo ampliado; en las técnicas más costosas puede terminar el presupuesto y conservar la acción base.

# Protocolo local v1

Este contrato es propio del proyecto. No es una especificación de la API de PokerFight. `decide` recibe un archivo JSON; `serve` recibe un objeto JSON compacto por línea y responde con otro por línea, vaciando stdout después de cada respuesta. No hay conexión de red ni credenciales.

El [ejemplo ejecutable](../examples/observation.json) contiene una observación completa. Todas las fichas son enteros no negativos y las cartas usan `23456789TJQKA` más `cdhs`.

| Campo | Semántica |
|---|---|
| `schema_version` | 1; si se omite se interpreta como 1 |
| `table_id` | Identificador de sesión de mesa; cambiarlo borra los perfiles locales |
| `hand_id` | Identificador único de mano dentro de esa sesión |
| `hero_id` | Jugador al que le toca actuar |
| `button_index` | Índice de botón dentro de `players` |
| `players` | De 2 a 6 jugadores en orden circular; conservar los retirados durante la mano |
| `hole_cards` | Exactamente las dos cartas propias |
| `board` | Cero, tres, cuatro o cinco cartas comunitarias visibles |
| `big_blind` | Ciega grande de esta mano, positiva |
| `legal` | Acciones y límites autorizados por el motor |
| `history` | Eventos públicos de esta mano, ordenados y sin duplicados; puede omitirse |

Cada jugador tiene `player_id`, `stack` (fichas que le quedan), `street_bet` (aportación en la calle actual), `contribution` (aportación total aún comprometida en esta mano, incluyendo antes) y `folded` (opcional, falso por defecto). No se admiten cartas ajenas, nombres reales, mazos ni campos adicionales. Una apuesta devuelta deja de formar parte de `contribution`.

`legal` contiene `can_check`, `can_fold`, `call_amount`, `min_raise_to` y `max_raise_to`. Los dos límites son opcionales y deben omitirse juntos o valer ambos `null` cuando no se puede subir. `call_amount` es el costo incremental **recortado al stack propio**. `raise_to` es el **total de fichas apostadas en esta calle**, no el incremento ni la contribución de la mano. Un all-in corto puede tener mínimo igual a máximo. Una subida que no se reabre debe representarse sin límites de subida, aunque el stack sea grande. No basta con deducir la legalidad a partir del dinero disponible.

Cada evento contiene `event_id`, `player_id`, `street` (`preflop`, `flop`, `turn` o `river`), `kind` (`fold`, `check`, `call` o `raise_to`), `amount` (cero por defecto) y `facing_bet` (falso por defecto). `amount` representa el precio incremental para `call`, y el total de calle para `raise_to`. `facing_bet` indica si el actor debía fichas justo antes de actuar. El adaptador debe usar identificadores estables por evento y enviar el historial disponible completo de la mano. Un historial incompleto reduce la calidad de rangos y perfiles, aunque el bot puede funcionar sin él.

La respuesta contiene:

```json
{
  "schema_version": 1,
  "hand_id": "mano-1",
  "action": {"kind": "raise_to", "amount": 250},
  "reason": "preflop:open_position_chart",
  "elapsed_ms": 75.0,
  "fallback": false,
  "equity": {
    "equity": 0.77,
    "standard_error": 0.006,
    "expected_return": 192.5,
    "eligible_pot": 250,
    "samples": 4000,
    "attempts": 6500,
    "timed_out": false
  }
}
```

Las cifras son ilustrativas. Para `check`, `fold` y `call`, la acción no incluye `amount`. Ante una observación válida con fallo de cálculo, se devuelve una acción de respaldo y `fallback: true`. `equity` puede ser `null`. `timed_out` indica que se terminó con menos muestras de las solicitadas, por reloj o por límite de intentos; una muestra parcial suficiente puede usarse sin respaldo.

Ante JSON inválido o un estado inconsistente, `serve` devuelve `error: "invalid_observation"` y `detail`, sin acción inventada, y continúa con la línea siguiente. El cliente oficial deberá disponer de su propia ruta segura para mensajes inválidos o conexiones interrumpidas.

El estimador y los perfiles solo utilizan información suministrada en este contrato. El simulador local es el único componente que conoce todas las cartas para aplicar las reglas. La construcción de observaciones está cubierta por una prueba que inspecciona lo que recibe cada política.

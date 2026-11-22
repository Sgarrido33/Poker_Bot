# Prueba de conexión al servidor de pruebas — 2026-11-21

## Objetivo

Verificar que un bot puede conectarse al servidor de pruebas de PokerFight con el token del equipo, completar el saludo, recibir manos y responder acciones válidas.

## Datos de conexión

| Dato | Valor |
|---|---|
| Host | `34.230.114.164` |
| Puerto | `9000` |
| Token | Token del equipo (no se incluye en este documento) |

La guía de inicio para equipos (`PokerFight - Guía de inicio para equipos.docx`) indicaba el host `32.201.29.142`. Ese host no respondió en el puerto 9000 (timeout en la conexión TCP y en `Test-NetConnection`). La dirección `34.230.114.164` se tomó de un mensaje posterior del organizador.

## Resultado

- **Conexión:** exitosa.
- **Saludo:** aceptado; el servidor respondió `bienvenida` con `id_jugador` `j-adc337` y `silla` `-1` (sin silla asignada al momento del saludo).
- **Manos:** 24 manos completas (`mano_inicio` / `mano_fin` = 24 / 24), correspondientes a las rondas de práctica `practica-r418` y `practica-r419`.
- **Acciones:** 99 respuestas `solicitar_accion`, todas `call`, siempre dentro de `acciones_validas`.
- **Errores:** ningún mensaje `error` de la mesa; no hubo desconexión del servidor.
- **Cierre:** al terminar la sesión de prueba, la conexión quedó en silencio (`timeout de espera`), comportamiento que la guía describe como normal entre rondas.

## Método

Se usó un script de Python de un solo archivo que:

1. Abre una conexión TCP a `34.230.114.164:9000`.
2. Envía `{"tipo": "saludo", "version": "1.0.0", "token": <token>}`. El token se lee de una variable de entorno, no se escribe en el archivo.
3. Lee mensajes JSON línea por línea y los registra.
4. Ante `solicitar_accion`, responde `check` si está en `acciones_validas`; si no, `call`; si no, `fold`.
5. Termina al recibir `error`, al cerrarse la conexión o tras 90 segundos sin mensajes.

La estrategia es deliberadamente trivial: sirve para validar el protocolo y la conexión, no para medir el juego.

## Observaciones

- El campo `monto` del protocolo es el total de la apuesta en la ronda, según la guía. Esta prueba no envió apuestas con monto.
- La prueba confirma que el protocolo de la guía (saludo, bienvenida, `mano_inicio`, `solicitar_accion`, `accion`, `mano_fin`) coincide con el servidor de pruebas.

## Pendiente

- Probar un bot con estrategia real contra el servidor de pruebas.
- Confirmar con la organización si la dirección `32.201.29.142` de la guía debe considerarse obsoleta.

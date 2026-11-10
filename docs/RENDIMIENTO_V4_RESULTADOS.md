# Rendimiento de búsqueda v4

Fecha local: 28 de octubre de 2026.

La búsqueda con 8 192 mundos fue **2,80 veces más rápida** al agregar las medianas de siete estados de desarrollo. La comparación utiliza tres repeticiones por estado y versión, alterna el orden de ejecución y verifica igualdad exacta de acciones, valores, errores estándar y motivos de parada. Los tiempos incluyen la preparación nueva de cada búsqueda; excluyen construir rangos y calcular la equity base.

La política predeterminada sigue siendo **v2**. Esta etapa optimiza el costo de v4 y conserva su modelo de respuestas; sus [resultados estratégicos anteriores](BUSQUEDA_V4_RESULTADOS.md) siguen teniendo la misma incertidumbre en sesiones con eliminación.

## Cambio implementado

[PreparedAction](../pokerfight/action_model.py) prepara el árbol completo de fold/call de cada acción a partir de información pública. Hay como máximo cinco rivales que deben responder, por tanto 32 hojas. Cada nodo guarda el precio y número de calls anteriores; cada hoja guarda sus capas de pozo y participantes elegibles. Los jugadores retirados no responden y los que ya igualaron o están all-in no reciben una rama de fold.

Antes se reconstruían contribuciones, precios y pozos para cada acción, supuesto rival y mundo simulado. Ahora cada muestra recorre el árbol preparado. Las comparaciones de cartas contra el héroe también se comparten entre todas las acciones y supuestos del mismo mundo. Se conserva la misma función de probabilidad y el mismo orden de suma de pagos, incluidas divisiones por empate. La preparación mantiene dinero de retirados, antes, pozos laterales y devoluciones.

Los rangos, semillas, cartas y uniformes de respuesta, acciones candidatas, umbrales y reglas de parada conservan sus definiciones. Las 67 pruebas actuales incluyen tres nuevas pruebas de equivalencia: todas las combinaciones de respuesta en estados de 2–6 jugadores, una referencia de contabilidad sin preparar el árbol y la búsqueda adaptativa completa. Los casos incluyen posiciones del héroe distintas, empates, stacks desiguales y un supuesto rival adicional con parámetros distintos.

## Mediciones

| Estado | Antes, mediana | Ahora, mediana | Cociente |
|---|---:|---:|---:|
| UTG, mano especulativa, 4 bb | 1 591,6 ms | 546,7 ms | 2,91× |
| Heads-up, 8 bb | 614,8 ms | 252,3 ms | 2,44× |
| UTG, as débil, 4 bb | 1 160,2 ms | 440,5 ms | 2,63× |
| Botón, as débil, 4 bb | 1 064,5 ms | 333,9 ms | 3,19× |
| Héroe 100 bb, efectivo 4 bb | 742,4 ms | 259,2 ms | 2,86× |
| BB, defensa barata, 8 bb | 755,9 ms | 238,6 ms | 3,17× |
| BB, defensa cara, 8 bb | 242,0 ms | 133,5 ms | 1,81× |

Se completaron 172 032 mundos por versión en esta medición. Son mundos internos de Monte Carlo, no manos de evaluación estratégica. Se desactivó el corte de reloj y se fijó el mínimo al máximo de mundos para comparar el mismo trabajo. El caso de defensa cara ejercita el núcleo de búsqueda aunque la política adaptativa puede detenerse antes.

Comprobaciones adicionales, conservadas en [benchmark.json](../results/action_compilation_2026-10-28/benchmark.json):

- **57 estados guardados:** una decisión preflop de cada celda de la validación anterior, con 1 024 muestras y semillas iguales; todas las respuestas completas coinciden, salvo tiempo transcurrido.
- **20 manos completas por versión:** 2–6 jugadores, todos los asientos, 512 muestras del héroe y rivales de reglas/v2; coinciden trazas, valores, decisiones, cartas, fichas y acciones tras excluir tiempos. Cero respaldos y conservación de fichas. Son 40 ejecuciones de mano, con veinte repartos compartidos.
- **8 decisiones supervisadas:** perfil actual de 16 384 muestras/3 500 ms, proceso persistente; máximo observado 969,2 ms, sin respaldos ni acciones ilegales. Incluye la regresión de call all-in barato. Excluye arranque, parseo y red; estos ocho estados no estiman un percentil representativo.
- **40 escenarios de contabilidad contra PokerKit:** diferencia máxima cero. El [oráculo](../results/action_compilation_2026-10-28/terminal_oracle.json) valida pagos bajo respuestas fijadas.
- **67 pruebas aprobadas**, incluidas interrupción de un proceso bloqueado, escritura al pipe bloqueada y rechazo de una acción ilegal. Véase [tests.txt](../results/action_compilation_2026-10-28/tests.txt).

## Alcance y código anterior

La igualdad se exige con las mismas muestras y sin agotar el reloj. Con tiempo limitado la implementación más rápida puede completar más mundos y cambiar una decisión; no se promete igualdad ante un corte de reloj. Esta etapa no añade evidencia de ganancias ni elimina los sesgos del modelo fold/call/checkdown: siguen faltando resubidas y apuestas posteriores.

Antes de editar se guardó [la implementación completa anterior](../research/policy_snapshots/pre_fast_v4_20261028/environment.json), incluidos paquete, scripts, pruebas, ejemplos y documentos. Su huella coincide con el protocolo de la evaluación estratégica v4:

- Antes: `4d1fd238541090d1a1da72427e2c3d4f797b47c0b1ada95e7fb3647be254a78e`.
- Ahora: `609af185484a58a5db6a1ade04216ea995cd4cee0f16b564c516aae29efe75b2`.

El control `frozen_v2` y su manifiesto siguen intactos. El benchmark carga el paquete anterior bajo un nombre independiente y comprueba su huella antes de compararlo. Los estados de validación reutilizados se tratan como desarrollo.

## Reproducción

Desde la raíz del proyecto, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_action_compilation --output results/action_compilation_repeticion/benchmark.json
.\.venv\Scripts\python.exe -m scripts.verify_terminal_payoffs --output results/action_compilation_repeticion/terminal_oracle.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Los tiempos dependen de la carga y máquina; la igualdad de resultados con trabajo fijo es una comprobación determinista. Para repetir las campañas estratégicas antiguas con su huella original, véanse los comandos actualizados en [BUSQUEDA_V4_METODO.md](BUSQUEDA_V4_METODO.md).

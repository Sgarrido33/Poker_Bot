# Evaluación académica de agentes de póker

## Qué demuestra cada tipo de prueba

El autojuego sirve para construir una política; no es por sí mismo evidencia de que el bot gane a humanos ni a agentes externos. Pluribus construyó su estrategia base mediante autojuego, sin datos humanos ni de otros bots, y luego la mejoró en tiempo real. DeepStack entrenó redes con millones de situaciones generadas y resueltas. En ambos casos, la evaluación de rendimiento fue una etapa separada. [Pluribus, *Science* (2019)](https://noambrown.github.io/papers/19-Science-Superhuman.pdf); [DeepStack, *Science* (2017)](https://poker.cs.ualberta.ca/publications/17science.pdf).

Jugar varias copias de un bot tampoco equivale a jugar contra una población diversa. Un lote contra copias sin optimizar las políticas es evaluación de ese emparejamiento, no entrenamiento por autojuego. Pluribus probó cinco copias contra un profesional: el agente no identificaba ni adaptaba su estrategia a los rivales, así que los autores indican que no podían coludirse intencionalmente. Esa prueba mide el rendimiento del humano ante una mesa de copias con esa política. Otra prueba puso una copia contra cinco profesionales; responde una pregunta distinta. [Pluribus](https://noambrown.github.io/papers/19-Science-Superhuman.pdf).

El *cross-play* enfrenta agentes distintos. ACPC comparaba participantes entre sí, por emparejamientos, y archivaba resultados por rival además de clasificaciones agregadas. Esto mide el rendimiento relativo frente a ese campo de bots y esas reglas; no predice automáticamente el rendimiento contra bots ausentes o humanos. Slumbot aparece en los resultados oficiales archivados de 2016, y su sitio lo identifica como ganador de ACPC 2018. [Resultados ACPC 2016](https://www.cs.cmu.edu/~waugh/crosstable.html); [Slumbot](https://slumbot.com/).

Las pruebas humanas aportan evidencia para una población concreta, con costos de tiempo y alta varianza. Libratus jugó 120.000 manos heads-up contra cuatro profesionales. DeepStack jugó 44.852 partidas contra 33 profesionales; 11 completaron las 3.000 previstas. Pluribus jugó 10.000 manos contra grupos de cinco profesionales y, en otro formato, 5.000 manos por cada uno de dos humanos contra cinco copias. Reportar el agregado no implica que cada resultado individual sea estadísticamente concluyente. [Libratus](https://www.aeaweb.org/conference/2018/preliminary/paper/h9Bs5dth); [DeepStack](https://poker.cs.ualberta.ca/publications/17science.pdf); [Pluribus](https://noambrown.github.io/papers/19-Science-Superhuman.pdf).

## Control de suerte e incertidumbre

Las partidas duplicadas buscan controlar suerte de reparto y posición. En ACPC, los agentes juegan una tanda y luego se reinician, intercambian asientos y reciben el mismo reparto por posición. Para varios jugadores se rotan asientos para balancear quién ocupa cada posición. Libratus emparejó humanos para reflejar cartas y, ante ciertos all-ins tempranos, promedió los runouts posibles. Estos métodos reducen varianza, pero no hacen idénticas las decisiones ni eliminan incertidumbre. [Descripción ACPC](https://onlinelibrary.wiley.com/doi/pdf/10.1609/aimag.v34i2.2474); [Libratus](https://www.aeaweb.org/conference/2018/preliminary/paper/h9Bs5dth).

Prácticas útiles: fijar y registrar semillas; reiniciar agentes entre bloques; rotar asientos de manera balanceada; ocultar cartas futuras y semillas; separar bloques de entrenamiento y evaluación; analizar resultados por bloque y no asumir que cada mano es independiente; informar reglas, stacks, rivales, manos y métrica.

AIVAT es un estimador insesgado de varianza reducida que usa valores estimados de estados y estrategias conocidas para corregir parte de la variación por cartas y acciones del agente conocido. En una competición humano-máquina redujo la desviación estándar un 85 %; DeepStack reportó una estimación mucho más precisa con AIVAT que con el resultado bruto. No es una ganancia observada ni elimina los supuestos: conviene publicar ambos valores, explicar la aplicación y reportar intervalo/error y prueba estadística. El método no puede corregir del mismo modo las acciones de humanos cuya política se desconoce; Pluribus advierte que sus tasas individuales humanas no eran significativas. [AIVAT, AAAI 2018](https://poker.cs.ualberta.ca/publications/aaai18-burch-aivat.pdf); [DeepStack](https://poker.cs.ualberta.ca/publications/17science.pdf); [Pluribus](https://noambrown.github.io/papers/19-Science-Superhuman.pdf).

## Métricas y resultados: unidades importan

Reportar ganancias brutas y tasas normalizadas con unidades explícitas. **mbb** significa milésimas de ciega grande. Por tanto, 48 mbb/mano = 0,048 bb/mano = 4,8 bb/100 manos. No describirlo como “48 mbb por cada mil manos”. Acompañar la tasa con número de manos, bloques, asientos, rivales, error estándar o intervalo de confianza y método estadístico; separar resultados globales de los individuales. Los estudios de Pluribus, DeepStack y Libratus ilustran que las definiciones de unidad deben verificarse antes de comparar cifras. [Pluribus](https://noambrown.github.io/papers/19-Science-Superhuman.pdf); [DeepStack](https://poker.cs.ualberta.ca/publications/17science.pdf); [Libratus](https://www.aeaweb.org/conference/2018/preliminary/paper/h9Bs5dth).

ACPC utilizó **total bankroll**, que ordena por ganancias frente a todo el campo, e **instant runoff (IRO)**, que elimina iterativamente al agente peor clasificado y recalcula resultados entre los restantes. IRO es una regla de clasificación entre agentes, no eliminación de jugadores cuando pierden stacks. Un torneo por stacks incorpora ciegas, riesgo de quedarse sin fichas y pagos por posición; mide un objetivo distinto. [Bard et al., descripción de ACPC, *AI Magazine*](https://onlinelibrary.wiley.com/doi/pdf/10.1609/aimag.v34i2.2474).

## Fuentes primarias

- [Pluribus, artículo](https://noambrown.github.io/papers/19-Science-Superhuman.pdf)
- [DeepStack, artículo de *Science*](https://poker.cs.ualberta.ca/publications/17science.pdf)
- [Libratus, diseño de evaluación (AEA)](https://www.aeaweb.org/conference/2018/preliminary/paper/h9Bs5dth)
- [AIVAT, AAAI 2018](https://poker.cs.ualberta.ca/publications/aaai18-burch-aivat.pdf)
- [ACPC, descripción](https://onlinelibrary.wiley.com/doi/pdf/10.1609/aimag.v34i2.2474) y [resultados 2016](https://www.cs.cmu.edu/~waugh/crosstable.html)

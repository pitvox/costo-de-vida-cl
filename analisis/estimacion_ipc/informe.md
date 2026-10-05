# IPC de alimentos y canasta básica con precios de ODEPA: prueba hacia atrás

Pregunta: ¿puede Carestía publicar cada semana una estimación del IPC de alimentos y una valorización de la Canasta Básica de Alimentos con los precios al consumidor de ODEPA? Antes de publicar nada, esta prueba hacia atrás mide qué tan bien lo habría hecho entre enero de 2019 y agosto de 2026. Es solo análisis: no cambia el sitio ni el pipeline. Cómo reproducirlo, en [README.md](README.md).

## Respuesta corta

- **IPC de alimentos: cumple los dos criterios pedidos, pero por poco y sin ganarle a referencias igual de simples.** El error absoluto medio de la variación mensual es 0,62 puntos, contra 0,79 del pronóstico ingenuo (repetir la variación del mes anterior). Acierta la dirección en 64 de 92 meses (69,6%), sobre el umbral de 2 de cada 3. Pero el promedio de los últimos 12 meses del propio IPC de alimentos tiene casi el mismo error (0,63) y decir "sube" todos los meses acierta la dirección en 75% de los meses.
- **Canasta básica: se puede valorizar, pero no reemplaza al valor del Ministerio.** ODEPA da precio por kilo o litro al 61% del valor de la canasta. Con esos precios, la canasta de agosto de 2026 vale 89.100 pesos por persona, 3,5% bajo los 92.327 que publicó el Ministerio. La brecha cambia con los años (de 4,6% bajo en 2019 a 0,6% sobre en 2023) porque el Ministerio reajusta todo con un índice agregado y ODEPA sigue producto por producto.

## Cobertura

| | Productos con ODEPA | Peso cubierto |
|---|---|---|
| IPC de alimentos, base 2018 (2019 a 2023) | 35 de 76 | 61,1% |
| IPC de alimentos, base 2023 (desde 2024) | 35 de 81 | 58,5% |
| Canasta básica, metodología 2024 | 36 de 96 | 60,7% del valor |

Quedan fuera, entre otros, cecinas, bebidas, agua embotellada, pescados, galletas, repostería, platos preparados, café y pan envasado. En la canasta, además, las comidas en restaurantes (7,5% del valor) y lo que ODEPA cotiza por unidad y no por kilo (huevos, lechuga, choclo, pepino, pimentón, zapallo italiano, brócoli y ajo). El mapa producto por producto está en [mapa_productos.csv](mapa_productos.csv) y [mapa_cba.csv](mapa_cba.csv); lo revisaron agentes contra las definiciones del INE (microdatos, CCIF 2018.CL y metodologías) y cada cambio propuesto pasó por dos escépticos.

## Método

- **Agregación.** Laspeyres con las ponderaciones del INE, la misma fórmula del índice oficial. Aplicada a los índices oficiales de producto, reproduce la variación publicada de Alimentos en 91 de 92 meses (en el otro difiere en 0,1 por redondeo).
- **Productos con ODEPA.** Media geométrica de la variación de sus productos ODEPA en la Región Metropolitana (cada producto ODEPA, a su vez, media de sus series por unidad), con la limpieza de las series del sitio.
- **Productos sin ODEPA.** Su propia variación oficial del mes anterior (regla principal) o su variación mensual promedio de los últimos 12 meses (alternativa). Las dos ya estaban publicadas por el INE.
- **Sin mirar al futuro.** Para cada mes solo entran las semanas de ODEPA publicadas antes de la fecha del IPC, sacada de la portada de cada boletín del INE ([calendario_ipc.csv](calendario_ipc.csv)). El INE no revisó ninguna cifra de alimentos después de publicarla.
- **Cambio de base.** Base 2018 hasta diciembre de 2023 y base 2023 desde enero de 2024. En enero de 2019 y enero de 2024 el INE ya había publicado la canasta nueva, pero no los índices de sus productos en el año base: esos dos meses van con las ponderaciones sin reescalar y los productos sin ODEPA con la variación oficial de Alimentos.
- **Comparación.** La estimación se redondea a un decimal, como la publica el INE. Dirección: sube, baja o 0,0.

## Resultados del IPC de alimentos

| Año | Error estimación | Error ingenuo | Dirección estimación | Dirección ingenuo |
|---|---|---|---|---|
| 2019 | 0,50 | 0,63 | 58% | 50% |
| 2020 | 0,58 | 0,61 | 67% | 75% |
| 2021 | 0,63 | 0,96 | 75% | 58% |
| 2022 | 0,68 | 0,85 | 100% | 100% |
| 2023 | 0,38 | 0,61 | 83% | 58% |
| 2024 | 1,08 | 1,29 | 58% | 50% |
| 2025 | 0,55 | 0,71 | 58% | 50% |
| 2026 (a agosto) | 0,59 | 0,65 | 50% | 50% |
| **Total (92 meses)** | **0,62** | **0,79** | **69,6%** | **62,0%** |

Error: error absoluto medio de la variación mensual, en puntos porcentuales. La diferencia con el ingenuo es significativa (prueba de Diebold y Mariano, p = 0,007).

![Variación mensual del IPC de alimentos, oficial y estimada](grafico_estimado_oficial.png)

| Variante (92 meses salvo indicación) | Error | Dirección |
|---|---|---|
| Regla principal | 0,62 | 69,6% |
| Sin ODEPA con su promedio de 12 meses | 0,54 | 69,6% |
| Con las primeras 2 semanas del mes | 0,60 | 68,5% |
| ODEPA publicada una semana más tarde | 0,63 | 67,4% |
| Sin enero de 2019 ni enero de 2024 (90 meses) | 0,63 | 68,9% |
| Referencia: promedio de 12 meses del IPC de alimentos | 0,63 | 75,0% |
| Referencia: siempre sube | | 75,0% |
| Cota: productos con ODEPA con su variación oficial | 0,39 | 79,3% |

Lo que dicen las variantes:

- La estimación a mitad de mes, con dos semanas de ODEPA, es tan buena como la de mes completo. Publicarla cada semana es posible.
- Frente al promedio de 12 meses la ventaja desaparece: 0,62 contra 0,63 (p = 0,88). Con la regla alternativa baja a 0,54, pero tampoco es significativa (p = 0,11).
- La última fila usa, para los mismos productos, la variación del INE en vez de la de ODEPA. Baja el error de 0,62 a 0,39: la mayor parte del error viene de que la variación de ODEPA en la RM no es la que mide el INE en el país, no de los productos sin cubrir.

## Canasta básica

La canasta vigente (metodología 2024) son 96 productos con su cantidad mensual por persona, valorizados a marzo de 2022 en 66.896 pesos. El Ministerio la reajusta con el promedio ponderado del IPC de alimentos y del de restaurantes. Esa regla reconstruye lo publicado en 2026 con un error máximo de 0,02%. Antes de 2026 el Ministerio publicaba otra canasta (metodología 2013), que no es comparable, así que de 2019 a 2025 la comparación va contra la reconstrucción. Con ODEPA se valoriza cada producto con precio (cantidad por precio por kilo o litro) y el resto se deja con el valor del Ministerio, para que toda la diferencia quede en los productos con ODEPA.

| Mes | Ministerio | Con ODEPA | Diferencia | Solo productos con ODEPA |
|---|---|---|---|---|
| diciembre 2019 | 55.280 | 52.964 | -4,2% | -6,9% |
| diciembre 2021 | 62.790 | 62.256 | -0,8% | -1,4% |
| marzo 2022 (base) | 66.896 | 66.697 | -0,3% | -0,5% |
| diciembre 2023 | 81.599 | 82.398 | +1,0% | +1,7% |
| diciembre 2025 | 89.233 | 85.611 | -4,1% | -6,9% |
| agosto 2026 | 92.327 (publicado) | 89.100 | -3,5% | -6,0% |

La diferencia tiene dos partes:

1. **Nivel.** En marzo de 2022 los productos con ODEPA suman casi lo mismo (-0,5%), pero producto a producto las brechas son grandes y se compensan. En ODEPA el pollo cuesta cerca de 40% menos, la posta 36% menos y el plátano 42% menos, mientras que los espaguetis cuestan 146% más, las papas 25% más y el pan corriente 12% más. La canasta parte del gasto real de los hogares del primer quintil en la Encuesta de Presupuestos Familiares (marcas, formatos y lugares de compra), y ODEPA cotiza un formato fijo en ferias y supermercados de la RM.
2. **Movimiento.** El Ministerio mueve los 96 productos con un solo índice nacional, que incluye restaurantes. Los precios ODEPA de los productos cubiertos subieron más que ese índice entre 2019 y 2022 y menos desde 2024. La variación mensual de las dos canastas difiere en 0,45 puntos en promedio.

## Licencias

- **INE:** [CC BY-SA 4.0](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos). Lo que se publique a partir de sus series tiene que citar al INE, enlazar la licencia, decir qué se cambió, ir bajo la misma licencia y no dar a entender que la estimación es del INE.
- **Canasta básica:** el Observatorio Social del Ministerio de Desarrollo Social y Familia no declara licencia en sus páginas ni en los PDF ([metodología 2024](https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/Metodologia_de_Medicion_de_la_Pobreza_por_Ingresos_2024.pdf), [informes mensuales](https://observatorio.ministeriodesarrollosocial.gob.cl/nueva-serie-cba-2026)). Es información pública (Ley 20.285). Lo prudente es citar "Fuente: Ministerio de Desarrollo Social y Familia" y aclarar que la valorización con ODEPA es elaboración propia.
- **ODEPA:** [CC BY 4.0](https://datos.odepa.gob.cl/manual/terminos-y-condiciones.pdf).

## Conclusión

Con los criterios pedidos, la estimación pasa: le gana al ingenuo en error (0,62 contra 0,79) y acierta la dirección en 69,6% de los meses, más de 2 de cada 3. Aun así, no recomiendo publicarla como estimación del IPC de alimentos. Una regla que no usa ODEPA (el promedio de 12 meses) tiene el mismo error, y otra (siempre sube) acierta más la dirección. Con un error típico de 0,6 puntos en un indicador que se mueve 0,6% al mes en promedio, la cifra informaría poco. Si se quiere publicar algo, lo honesto es la variación de precios de los productos del IPC que ODEPA cubre en la RM, presentada como tal y no como anticipo del IPC.

Para la canasta básica vale lo mismo: la valorización con ODEPA es una medida distinta, no una estimación del valor oficial. Cubre el 61% del valor, mide la RM y no el país, y en 2026 queda 3,5% bajo lo publicado. Se puede publicar como "la canasta básica con precios de ferias y supermercados de la RM", con el valor del Ministerio al lado.

Límites de la prueba: ODEPA mide la RM y el INE el país; no hay copias históricas de ODEPA para saber si revisó datos ya publicados; se supone que publica cada semana el viernes; y la cobertura por kilo deja fuera productos de peso en la canasta.

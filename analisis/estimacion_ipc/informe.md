# IPC de alimentos y canasta básica con precios de ODEPA: prueba hacia atrás

Pregunta: ¿puede Carestía publicar cada semana una estimación del IPC de alimentos y una valorización de la Canasta Básica de Alimentos con los precios al consumidor de ODEPA? Esta prueba hacia atrás mide qué tan bien lo habría hecho entre enero de 2019 y agosto de 2026. Es solo análisis: no cambia el sitio ni el pipeline. Cómo reproducirlo, en [README.md](README.md).

## Respuesta corta

- **IPC de alimentos: cumple los dos criterios pedidos, pero no le gana a referencias igual de simples.** El error absoluto medio de la variación mensual es 0,62 puntos, contra 0,79 del pronóstico ingenuo (repetir la variación del mes anterior), y acierta la dirección en 64 de 92 meses (69,6%), sobre el umbral de 2 de cada 3. Pero el promedio de los últimos 12 meses del propio IPC de alimentos tiene casi el mismo error (0,63), y decir "sube" todos los meses acierta la dirección en 75% de los meses.
- **Canasta básica: se puede valorizar, pero no es el valor oficial.** ODEPA da precio por kilo o litro al 61% del valor de la canasta. Con esos precios, la canasta de agosto de 2026 vale 88.255 pesos por persona, 4,4% bajo los 92.327 que publicó el Ministerio. La brecha cambia con los años (4,4% bajo en 2019, pareja en 2022 y 2023, otra vez 4,5% bajo en 2026) porque el Ministerio reajusta toda la canasta con un índice agregado y ODEPA sigue producto por producto.

## Cobertura

| | Productos con ODEPA | Peso cubierto |
|---|---|---|
| IPC de alimentos, base 2018 (2019 a 2023) | 35 de 76 | 61,1% |
| IPC de alimentos, base 2023 (desde 2024) | 35 de 81 | 58,5% |
| Canasta básica, metodología 2024 | 36 de 96 | 60,7% del valor |

Mes a mes, la parte que efectivamente se mueve con ODEPA promedia 60,9% en la base 2018 y 56,9% en la base 2023 (el yogur de 125 g, por ejemplo, dejó de cotizarse en julio de 2023). Quedan fuera, entre otros, cecinas, bebidas, agua embotellada, pescados, galletas, repostería, platos preparados, café y pan envasado. En la canasta, además, las comidas en restaurantes (7,5% del valor) y lo que ODEPA cotiza por unidad y no por kilo (huevos, lechuga, choclo, pepino, pimentón, zapallo italiano, brócoli y ajo). Los mapas ([mapa_productos.csv](mapa_productos.csv) y [mapa_cba.csv](mapa_cba.csv)) se revisaron contra lo que el INE efectivamente cotiza (microdatos, manuales y CCIF 2018.CL) y cada cambio pasó por dos escépticos. Por eso, en frutas y verduras de estación solo quedan las que el INE cotiza: salieron, entre otras, arándano, cereza, mandarina, mango, apio y haba.

## Método

- **Agregación.** Laspeyres con las ponderaciones del INE, la misma fórmula del índice oficial. Aplicada a los índices oficiales de producto, reproduce la variación publicada de Alimentos en 91 de 92 meses (en el otro difiere en 0,1 por redondeo).
- **Productos con ODEPA.** Media geométrica de la variación de sus productos ODEPA en la Región Metropolitana (cada uno, media de sus series por unidad), con la limpieza de las series del sitio.
- **Productos sin ODEPA.** Su propia variación oficial del mes anterior (regla principal) o su variación mensual promedio de los últimos 12 meses (alternativa). Las dos ya estaban publicadas.
- **Sin mirar al futuro.** Para cada mes solo entran las semanas de ODEPA publicadas antes de la fecha del IPC, sacada de la portada de cada boletín del INE ([calendario_ipc.csv](calendario_ipc.csv)). El INE no revisó ninguna cifra de alimentos después de publicarla.
- **Cambio de base.** Base 2018 hasta diciembre de 2023 y base 2023 desde enero de 2024. En enero de 2019 y enero de 2024 el INE ya había publicado la canasta nueva, pero no los índices de sus productos en el año base. Esos dos meses van con las ponderaciones sin reescalar y los productos sin ODEPA con la variación oficial de Alimentos. Esa aproximación mueve la cifra en 0,1 a 0,2 puntos por sí sola.
- **Comparación.** La estimación se redondea a un decimal, como la publica el INE. Dirección: sube, baja o 0,0. Significancia: prueba de Diebold y Mariano con la corrección de Harvey, Leybourne y Newbold.

## Resultados del IPC de alimentos

| Año | Error estimación | Error ingenuo | Dirección estimación | Dirección ingenuo |
|---|---|---|---|---|
| 2019 | 0,48 | 0,62 | 75% | 50% |
| 2020 | 0,67 | 0,61 | 58% | 75% |
| 2021 | 0,62 | 0,96 | 75% | 58% |
| 2022 | 0,64 | 0,85 | 100% | 100% |
| 2023 | 0,29 | 0,61 | 83% | 58% |
| 2024 | 1,12 | 1,29 | 50% | 50% |
| 2025 | 0,57 | 0,71 | 58% | 50% |
| 2026 (a agosto) | 0,53 | 0,65 | 50% | 50% |
| **Total (92 meses)** | **0,62** | **0,79** | **69,6%** | **62,0%** |

Error: error absoluto medio de la variación mensual, en puntos porcentuales. La diferencia con el ingenuo es significativa (p = 0,008).

![Variación mensual del IPC de alimentos, oficial y estimada](grafico_estimado_oficial.png)

| Variante (92 meses salvo indicación) | Error | Dirección |
|---|---|---|
| Regla principal | 0,62 | 69,6% |
| Sin ODEPA con su promedio de 12 meses | 0,55 | 70,7% |
| Con las primeras 2 semanas del mes y del mes anterior | 0,63 | 65,2% |
| ODEPA publicada una semana más tarde | 0,62 | 69,6% |
| Sin enero de 2019 ni enero de 2024 (90 meses) | 0,62 | 68,9% |
| Referencia: promedio de 12 meses del IPC de alimentos | 0,63 | 75,0% |
| Referencia: siempre sube | | 75,0% |
| Cota: productos con ODEPA con su variación oficial | 0,39 | 79,3% |

Lo que dicen las variantes:

- Frente al promedio de 12 meses la ventaja desaparece: 0,62 contra 0,63 (p = 0,83). Con la regla alternativa baja a 0,55, pero tampoco es significativa (p = 0,16).
- A mitad de mes, con dos semanas de ODEPA, el error sube a 0,63 y la dirección cae a 65,2%, bajo el umbral. Una cifra semanal sería más débil que la mensual.
- La cota usa, para los mismos productos, la variación del INE en vez de la de ODEPA, y baja el error de 0,62 a 0,39. La mayor parte del error viene de que la variación de ODEPA en la RM no es la que mide el INE en el país. Los productos que más error aportan son pan, frutas de estación, carne de vacuno y pollo, todos con ODEPA. Entre los que no tienen ODEPA pesan las bebidas gaseosas y las cecinas ([aporte_error_productos.csv](resultados/aporte_error_productos.csv)).

## Canasta básica

La canasta vigente (metodología 2024) son 96 productos con su cantidad mensual por persona, valorizados a marzo de 2022 en 66.896 pesos. El Ministerio la reajusta con el promedio ponderado del IPC de alimentos y del de restaurantes, nacional. Esa regla reconstruye lo publicado en 2026 con un error máximo de 0,02%. Antes de 2026 el Ministerio publicaba otra canasta (metodología 2013), que no es comparable, así que de 2019 a 2025 la comparación va contra la reconstrucción.

Con ODEPA, cada producto parte de su precio promedio de marzo de 2022 y desde ahí se mueve con la variación de sus series ODEPA. Así un cambio de formato (el yogur pasó de vaso a bolsa de 1 kilo en julio de 2023) o una fruta fuera de temporada no se leen como cambio de precio. Lo que no tiene ODEPA queda con el valor del Ministerio, para que toda la diferencia quede en los productos con ODEPA. La última columna es la cifra que se podría publicar al cerrar cada mes: lo que no tiene ODEPA va con el valor del Ministerio del mes anterior, porque el del mes recién sale con el IPC.

| Mes | Ministerio | Con ODEPA | Diferencia | Solo productos con ODEPA | A fin de mes |
|---|---|---|---|---|---|
| diciembre 2019 | 55.280 | 53.081 | -4,0% | -6,5% | -3,9% |
| diciembre 2021 | 62.790 | 62.253 | -0,9% | -1,4% | -1,1% |
| marzo 2022 (base) | 66.896 | 66.697 | -0,3% | -0,5% | -1,6% |
| diciembre 2023 | 81.599 | 81.714 | +0,1% | +0,2% | +0,3% |
| diciembre 2025 | 89.233 | 84.832 | -4,9% | -8,1% | -4,9% |
| agosto 2026 | 92.327 (publicado) | 88.255 | -4,4% | -7,3% | -4,9% |

La diferencia tiene dos partes:

1. **Nivel.** En marzo de 2022 los productos con ODEPA suman casi lo mismo que en la canasta (-0,5%), pero producto a producto las brechas son grandes y se compensan. En ODEPA el pollo cuesta cerca de 40% menos, la posta 36% menos y el plátano 42% menos, mientras que los espaguetis cuestan 146% más, las papas 25% más y el pan corriente 12% más. La canasta parte del gasto de los hogares del primer quintil en la Encuesta de Presupuestos Familiares (marcas, formatos y lugares de compra reales), y ODEPA cotiza un formato fijo en ferias y supermercados de la RM.
2. **Movimiento.** El Ministerio mueve los 96 productos con un solo índice nacional que incluye restaurantes. Los precios ODEPA de los productos cubiertos subieron más que ese índice entre 2019 y 2022 y menos desde 2024. La variación mensual de las dos canastas difiere en 0,43 puntos en promedio (0,53 en la versión de fin de mes).

## Licencias

- **INE:** [CC BY-SA 4.0](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos). Lo que se publique a partir de sus series tiene que citar al INE, enlazar la licencia, decir qué se cambió, ir bajo la misma licencia y no dar a entender que la estimación es del INE.
- **Canasta básica:** el Observatorio Social del Ministerio de Desarrollo Social y Familia no declara licencia en sus páginas ni en los PDF ([metodología 2024](https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/Metodologia_de_Medicion_de_la_Pobreza_por_Ingresos_2024.pdf), [informes mensuales](https://observatorio.ministeriodesarrollosocial.gob.cl/nueva-serie-cba-2026)). Es información pública (Ley 20.285). Lo prudente es citar "Fuente: Ministerio de Desarrollo Social y Familia" y aclarar que la valorización con ODEPA es elaboración propia.
- **ODEPA:** [CC BY 4.0](https://datos.odepa.gob.cl/manual/terminos-y-condiciones.pdf).

## Conclusión

Con los criterios pedidos, la estimación pasa: le gana al ingenuo en error (0,62 contra 0,79) y acierta la dirección en 64 de 92 meses, más de 2 de cada 3. Aun así, no recomiendo publicarla como estimación del IPC de alimentos. Una regla que no usa ODEPA (el promedio de 12 meses) tiene el mismo error, y otra (siempre sube) acierta más la dirección. A mitad de mes, que es cuando una cifra semanal tendría sentido, queda bajo el umbral de dirección. Con un error típico de 0,6 puntos en un indicador que se mueve 0,6% al mes en promedio, la cifra informaría poco. Si se quiere publicar algo, lo honesto es la variación de precios de los productos del IPC que ODEPA cubre en la RM, presentada como tal y no como anticipo del IPC.

Para la canasta básica vale lo mismo: la valorización con ODEPA es otra medida, no una estimación del valor oficial. Cubre el 61% del valor, mide la RM y no el país, y en 2026 queda entre 4% y 5% bajo lo publicado. Se puede publicar como "la canasta básica con precios de ferias y supermercados de la RM", con el valor del Ministerio al lado.

Límites de la prueba:

- ODEPA mide la RM y el INE el país.
- Se supone que ODEPA publica cada semana el viernes.
- Los precios de ODEPA son la copia del 5 de octubre de 2026. El portal volvió a subir todos sus archivos el 25 de marzo de 2026, y el de 2025 otra vez el 29 de abril, así que no se puede saber si cambió datos ya publicados. Para medirlo habría que guardar una copia de cada semana.
- La cobertura por kilo deja fuera productos de peso en la canasta, como los huevos.

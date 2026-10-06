# Prerregistro de la prueba fuera de muestra

Escrito y subido al repositorio antes de calcular cualquier resultado de 2024 a 2026 con estas reglas. Lo que sigue no se cambia después de ver los resultados.

## Qué ya se había visto

El informe anterior midió la regla principal y la variante "promedio de 12 meses" en todo 2019 a 2026, así que sus cifras de 2024 a 2026 no son ciegas: se conocen por año. La variante AR(1) y la combinación son nuevas y no se han calculado en ningún período. La canasta anclada tampoco.

## Períodos

- **Desarrollo:** enero de 2019 a diciembre de 2023 (60 meses, base 2018). Ahí se estiman todos los parámetros.
- **Prueba:** enero de 2024 a agosto de 2026 (32 meses, base 2023). Solo se mide; los parámetros quedan fijos con lo estimado en desarrollo.

## Regla para que un producto pase

Se evalúa en el período de prueba, con la variación mensual redondeada a un decimal:

1. **Error.** El error absoluto medio de la estimación tiene que ser menor que el del mejor comparador simple, y la diferencia tiene que ser significativa: prueba de Diebold y Mariano con la corrección de Harvey, Leybourne y Newbold, t de Student con n-1 grados, dos colas, p < 0,05. El mejor comparador simple es el de menor error en el mismo período de prueba entre el ingenuo (repetir la variación oficial del mes anterior) y el promedio de las variaciones oficiales de los 12 meses anteriores.
2. **Dirección.** Tiene que acertar la dirección (sube, baja o 0,0) en más meses que la regla "siempre sube".

Pasa si cumple 1 y 2. Como se publicaría cada semana, un producto pasa solo si cumple la regla con 1, con 2 y con 3 semanas del mes. El mes completo se informa como referencia y no cuenta.

Se hacen 15 pruebas (cuatro versiones del IPC y la canasta, cada una con 1, 2 y 3 semanas). Además del umbral de 0,05 se informa si el resultado sobrevive al umbral corregido de Bonferroni, 0,05 / 15 = 0,0033. La conclusión usa el umbral de 0,05 y dice si el resultado depende de no corregir.

## Versiones del IPC de alimentos

Todas usan los productos con ODEPA igual que hasta ahora (media geométrica de sus variaciones). Con k semanas, la variación de un producto ODEPA compara las primeras k semanas del mes con las primeras k semanas del mes anterior. Cambia solo cómo se proyecta lo que no tiene variación ODEPA ese mes:

- **V0, regla principal (ya vista):** cada producto con su propia variación oficial del mes anterior.
- **V1, AR(1) (nueva):** con x la variación logarítmica mensual de un producto y μ su promedio de los 12 meses anteriores, x(m) = μ + φ · (x(m-1) - μ). φ es un solo coeficiente, estimado por mínimos cuadrados ponderados (por la ponderación del IPC) sobre todos los productos sin ODEPA de la base 2018, de enero de 2019 a diciembre de 2023. φ no se recorta.
- **V2, promedio de 12 meses (ya vista):** cada producto con su variación mensual promedio de los 12 meses anteriores.
- **V3, combinación (nueva):** w · V0 + (1 - w) · P12, con P12 el promedio de las variaciones oficiales de Alimentos de los 12 meses anteriores. w se estima en desarrollo por mínimos cuadrados (oficial - P12 sobre V0 - P12, sin constante), recortado entre 0 y 1, por separado para 1, 2 y 3 semanas.

En el primer mes de cada base (enero de 2019 y enero de 2024) sigue la regla del informe: lo que no tiene ODEPA se proyecta con la serie oficial de Alimentos (mes anterior, AR(1) o promedio de 12 meses, según la versión).

## Canasta básica anclada

Estima la variación mensual de la canasta oficial del Ministerio (metodología 2024; antes de 2026, su reconstrucción con el deflactor del Ministerio). Valor estimado del mes m = valor oficial de cada producto en m-1 por su variación ODEPA de las primeras k semanas de m frente a las primeras k de m-1. Como el Ministerio mueve todos los productos con el mismo índice, el peso de cada producto es su gasto de marzo de 2022 sobre el total. Lo que no tiene ODEPA, o no tiene variación comparable ese mes, se proyecta con el promedio de las variaciones oficiales de la canasta de los 12 meses anteriores (elegido porque en el desarrollo del IPC, 2019 a 2023, el promedio de 12 meses tuvo menos error que el mes anterior: 0,51 contra 0,54). Comparadores: el ingenuo y el promedio de 12 meses de la variación oficial de la canasta. Misma regla.

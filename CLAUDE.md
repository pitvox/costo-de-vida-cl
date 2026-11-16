# Carestía: guía para Claude

## Reglas de texto

Todo texto visible del sitio (páginas, meta descriptions, textos que arma el JS, leyendas de la captura PNG) suena escrito por una persona. Estas reglas valen para cualquier cambio de texto:

- Nada de rayas: ni "—" ni "–". Los rangos van con palabras: "33 a 66", "2008 a 2026".
- El "·" no une frases ni fragmentos: usa punto, coma o paréntesis. Solo puede quedar como marcador de dato faltante.
- "vs" se reemplaza por "sobre" o "bajo" según el signo: "+14% sobre su promedio histórico", "-5% bajo su promedio histórico".
- Dentro de una frase, los meses van con nombre completo y en minúscula ("diciembre"). Las abreviaturas ("Dic") quedan solo como etiquetas de las barras.
- Nada de inglés en las ayudas de uso ("zoom", "pinch"): "Para acercar, arrastra el eje...", "usa dos dedos".
- Nada de fórmulas típicas de texto generado por IA: "inédito", "al descuento", "sin precedentes" y parecidas.
- Los textos del dueño (`textos/*.md`) se copian literales. `build_site.py` solo les da formato HTML.
- El deslinde no se reformula: queda palabra por palabra. Va una sola vez en el sitio, en la sección Deslinde de metodología (decisión del dueño): no se repite en el pie, en las fichas ni en otras páginas.

La guardia está en `tests/test_texto.py` (pytest, sin red). Falla si aparece "—", "–", " · ", " vs ", "inédit", "al descuento" o "sin precedentes" en `textos/*.md`, en los strings de `build_site.py` que terminan en el sitio (docstrings y `print` de consola quedan fuera) o en el HTML de un build sintético. Corre con `python -m pytest -q tests`.

## Colores de las variaciones

Por decisión del dueño, esta regla reemplaza la de "flechas neutras". El número de cada variación de precio (la cinta de índices, las tarjetas de "Índices Carestía", "Esta semana", la tabla de la portada, la ficha de cada producto y la cifra del índice en /graficos.html) va en color con criterio de consumidor:

- Si el precio subió, rojo #c8321c (token `--sube`, que apunta a `--rojo`; clase `.v-sube`).
- Si bajó, verde #1a7f47 (token `--baja`, que apunta a `--verde`; clase `.v-baja`).
- Si no cambió (redondea a 0,0), en el color del texto, sin clase.

La flecha sigue al lado del número, en gris (`.f`, `--tinta3`), y el resto del texto va en tinta. Las clases las ponen `cambio()` y `fmt_delta()` en `build_site.py`, `fmtDelta()` en el JS de /graficos.html y `cifraTramo()` en la frase de "Comparar con" de las fichas (ahí la cifra va con su signo, "+38%", sin flecha). Las velas no cambian: siguen la convención de los gráficos (verde sube, rojo baja). El semáforo CARO/NORMAL/BARATO sigue reservado a los 4 índices.

## Identidad

Un boletín estadístico: tinta sobre blanco y sin color de marca (decisión del dueño, 16-11-2026). El único color del sitio es el dato: el semáforo de los 4 índices y el rojo o verde de las variaciones. Una sola familia, Archivo (400 y 500 texto, 600 etiquetas, 700 cifras, 800 wordmark), con `tabular-nums`. Los tokens viven solo en `CSS_BASE` de `build_site.py`:

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#ffffff` | fondo |
| `--panel` | `#f5f5f5` | superficies secundarias |
| `--line` | `#d9d9d9` | reglas y bordes |
| `--hover` | `#ebebeb` | hover de controles |
| `--grid` | `#ececec` | grilla de los gráficos |
| `--tinta` | `#111111` | texto |
| `--tinta2` | `#4d4d4d` | texto secundario |
| `--tinta3` | `#6b6b6b` | texto terciario, flechas |
| `--serie` | `#111111` | línea de índices oficiales |
| `--producto` | `#111111` | línea de productos |
| `--marca` | `#111111` | línea de la Í del wordmark |
| `--canasta` | `#767676` | línea de canastas de usuario |
| `--verde` | `#1a7f47` | semáforo, baja, vela que sube |
| `--rojo` | `#c8321c` | semáforo, sube, vela que baja |
| `--ambar` | `#f0b429` | semáforo como relleno |
| `--ambar-texto` | `#8a6100` | ámbar cuando es texto o trazo fino sobre blanco |
| `--sobre-ambar` | `#111111` | texto de la etiqueta NORMAL |
| `--cruz` | `rgba(17,17,17,.35)` | crosshair |
| `--sombra` | `rgba(17,17,17,.12)` | sombra de menús y buscador |

Todo texto cumple AA sobre `--bg` y `--panel`. El veredicto va como etiqueta rellena (`.ver-rojo`, `.ver-verde`, `.ver-ambar`), con el color sacado del nombre del veredicto, no del campo `color` de `indices.json` (ese campo sale de `COLORES` en `indices.py`, que vale lo mismo que `--verde`, `--ambar` y `--rojo`; un test los mantiene alineados). Comparar usa `--cmp1` a `--cmp4` (ver el comentario de `CSS_BASE`). Azul y celeste siguen vetados. El ícono es la única pieza en negativo.

**Modo oscuro (a pedido).** El claro es el predeterminado. El botón de la luna (en la fila de la navegación; en el celular, la última opción del menú) cambia solo la paleta a la anterior: carbón, hueso (también en la línea de los productos y de las canastas) y la brasa en la línea de los índices y en la Í del wordmark. Tipografía y forma no cambian. Los valores van en el bloque `:root[data-tema="oscuro"]` de `CSS_BASE` (y en `.theme-dark:root` del tema de Advanced Charts); fuera de ese bloque no puede aparecer la paleta anterior (lo revisa un test). La elección se guarda en el navegador (`carestia-tema`) y un script en el `<head>` la aplica antes de pintar. En las páginas con gráficos, cambiar de modo recarga la página, porque los gráficos leen los colores al montarse. Las tarjetas OG y el ícono quedan siempre en el claro.

## Alcance

Un cambio de texto no toca la lógica, los datos, el diseño, los colores ni las URLs. `indices.py`, `validar.py`, `resumen.json` y la metodología no se modifican sin autorización del dueño.

## Verificación con datos reales

Todo PR que toque el sitio se verifica con el `indices.json` real de carestia.cl antes de abrirse, no solo con datos sintéticos:

```bash
curl -O https://carestia.cl/indices.json
python build_site.py
python -m http.server
```

El build imprime el peso de `index.html`. Se revisa en el navegador la portada, Comparar, Arma tu canasta, un link de canasta compartido y la captura PNG. Si el entorno no alcanza carestia.cl, el PR no se abre hasta poder verificarlo, y se avisa.

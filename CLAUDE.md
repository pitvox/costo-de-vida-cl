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
- El deslinde no se reformula: queda palabra por palabra.

La guardia está en `tests/test_texto.py` (pytest, sin red). Falla si aparece "—", "–", " · ", " vs ", "inédit", "al descuento" o "sin precedentes" en `textos/*.md`, en los strings de `build_site.py` que terminan en el sitio (docstrings y `print` de consola quedan fuera) o en el HTML de un build sintético. Corre con `python -m pytest -q tests`.

## Colores de las variaciones

Por decisión del dueño, esta regla reemplaza la de "flechas neutras". El número de cada variación de precio (la cinta de índices, las tarjetas de "Índices Carestía", "Esta semana", la tabla de la portada, la ficha de cada producto y la cifra del índice en /graficos.html) va en color con criterio de consumidor:

- Si el precio subió, rojo #e0552f (token `--sube`, clase `.v-sube`).
- Si bajó, verde #5bbf7a (token `--baja`, clase `.v-baja`).
- Si no cambió (redondea a 0,0), en el color del texto, sin clase.

La flecha sigue al lado del número, en gris (`.f`), y el resto del texto va en hueso. Las clases las ponen `cambio()` y `fmt_delta()` en `build_site.py` y `fmtDelta()` en el JS de /graficos.html. Las velas no cambian: siguen la convención de los gráficos (verde sube, rojo baja). El semáforo CARO/NORMAL/BARATO sigue reservado a los 4 índices.

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

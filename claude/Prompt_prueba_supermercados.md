# Prueba de lectura de supermercados desde Actions

Del 20-11-2026. Arriba, lo que ya se leyó a mano desde Chrome. Abajo de la línea, el prompt para pegar completo en una sesión nueva de Claude Code sobre pitvox/costo-de-vida-cl. La sesión de chat no pudo empujar la rama (permiso de escritura al repo denegado), por eso va como prompt.

Es una prueba. La descripción del proyecto dice "sin scraping" y el plan dice que no hay comparador por cadena ni por SKU: nada de esto cambia esas reglas, y ninguna cifra de aquí va al sitio, a correos ni a redes. Antes de cualquier lectura periódica falta revisar los términos de uso de Cencosud.

## Lectura desde Chrome, 20-11-2026 entre 13:20 y 13:45

Navegador normal, sin iniciar sesión, sin elegir local ni comuna, sin aceptar cookies. Los 16 pedidos (8 insumos por 2 sitios) cargaron sin captcha ni bloqueo. La URL es `https://www.jumbo.cl/busqueda?ft=<término>` y `https://www.santaisabel.cl/busqueda?ft=<término>`. El HTML que devuelve el servidor a un pedido simple hecho desde la misma sesión del navegador trae el producto adentro (estado 200, cerca de 1,1 MB en Jumbo y 0,84 MB en Santa Isabel).

Insumos de la canasta `almuerzo-casino` (`CANASTAS_EJEMPLO` en `build_site.py`). Carestía es la semana del 09-11, en pesos de octubre de 2026, leída de carestia.cl/canastas/almuerzo-casino.html el 20-11. El producto de supermercado es el que elegí como comparable (granel o marca propia); esa elección es criterio mío y se puede discutir.

| Insumo | Carestía | Jumbo | Santa Isabel |
|---|---|---|---|
| Posta paleta, kilo | $11.461 | $11.790 (al vacío 1,6 kg) | $10.990 (al vacío 1,6 kg) |
| Trutro entero de pollo, kilo | $3.523 | $4.090 (granel) | $2.890 en oferta, $3.990 normal (granel) |
| Arroz largo delgado grado 2, kilo | $1.523 | $1.430 (Cuisine & Co) | $990 en oferta, $1.350 normal (Cuisine & Co) |
| Papa, kilo | $1.533 | $2.250 (granel) | $2.190 (granel) |
| Tomate, kilo | $1.878 | $2.090 (larga vida granel) | $1.990 (larga vida granel) |
| Cebolla, unidad | $386 | $617 (malla 3 un.) | $663 (malla 3 un.) |
| Aceite vegetal, litro | $2.446 | $2.100 (Cuisine & Co 900 ml) | $1.878 en oferta (Cuisine & Co 900 ml) |
| Marraqueta, kilo | $2.267 | $2.090 (granel) | $2.190 (granel) |
| Canasta para 10 | $20.574 | $23.360 | $21.276 con ofertas, $22.636 sin ellas |

Lo que se ve: carne, pan y tomate quedan a menos de 12% de Carestía. La papa sale 43% a 47% más cara en el supermercado y la cebolla por unidad, 60% a 72%. Arroz y aceite de marca propia salen más baratos que el promedio de ODEPA. La canasta completa queda entre 3% y 14% sobre Carestía.

Límites: son precios del 20-11 contra una semana del 09-11 ajustada a octubre; sin local elegido; las ofertas cambian la foto; un solo día.

Formato del texto de cada tarjeta (el `innerText` de `<main>`, cortado en cada "Agregar"), tal como salió:

```
$3.890
$1.945 x kg
Frutas y Verduras Propias
Papa Malla 2 kg
```

```
$1.125
x 500 g
$2.250 x kg
Frutas y Verduras Propias
Papa Granel
```

Con oferta aparece antes una etiqueta ("Oferta", "Los Imbatibles", "Santa Ofertas", "Lleva 2 por $3.000") y dos precios seguidos, el vigente y el anterior. La unidad puede ser `x kg`, `x lt` o `x un`. Antes del primer producto viene todo el texto de los filtros.

robots.txt leídos el 20-11: Jumbo permite el rastreo general, bloquea `?map=`, `?PS=`, `sc=`, carro y cuenta, y no bloquea `/busqueda?ft=`. Santa Isabel dice `Allow: /` con `Crawl-delay: 1` y bloquea `/api/`, `/_next/`, `/admin/` y `/private/`.

---

Eres Claude Code en el repo pitvox/costo-de-vida-cl (Carestía). Lee CLAUDE.md antes de empezar. Esta tarea es una prueba técnica aislada: saber si las páginas de búsqueda de jumbo.cl y santaisabel.cl se pueden leer desde GitHub Actions igual que desde un navegador normal. No toca el sitio, `indices.py`, `build_site.py`, `datos/`, `resumen.json` ni la metodología, y no publica nada.

Qué construir, en una rama nueva `claude/prueba-supermercados`:

1. `analisis/supermercados/prueba_lectura.py`. Para cada sitio y cada término de esta lista: `posta paleta`, `trutro entero pollo`, `arroz grado 2`, `papa`, `tomate`, `cebolla`, `aceite vegetal`, `marraqueta`.
   - Fase A, pedido simple: un GET a `https://www.<sitio>/busqueda?ft=<término>` con `requests`. Anota estado HTTP, bytes, cuántas veces aparece `x kg`, `x lt` o `x un`, y si el HTML trae nombres de producto.
   - Fase B, navegador sin interfaz: la misma URL con Playwright (Chromium), espera a que cargue, toma el `innerText` de `main`, lo corta en cada "Agregar" y saca de cada tarjeta nombre, marca, precio vigente, precio anterior si hay oferta, y precio por unidad con su unidad. Guarda las primeras 8 tarjetas.
   - Salida: `resultado.csv` (sitio, fase, término, posición, nombre, marca, precio, precio_unidad, unidad, oferta) y `resumen.md` con una tabla por sitio y fase: estado, si hubo precios, si hubo bloqueo.
2. `.github/workflows/prueba_supermercados.yml`, con `workflow_dispatch` y, solo mientras dure la prueba, `push` a esta rama. `permissions: contents: read`. Sube `resultado.csv` y `resumen.md` como artifact de 3 días e imprime `resumen.md` en el log. Sin commit, sin deploy.
3. `tests/test_supermercados.py`, sin red: el parser de tarjetas contra los ejemplos de texto de `claude/Prompt_prueba_supermercados.md` (precio simple, precio por 500 g, oferta con dos precios, unidad `x un`).

Reglas de la prueba, que no se negocian:
- Sin saltar barreras. Si un pedido devuelve 403, 429, un captcha o una página de desafío, se anota "bloqueado" con lo que se vio y no se reintenta ni se cambia de táctica para ese sitio. Nada de plugins para ocultar el navegador, proxies, rotación de IP ni cabeceras copiadas de un navegador real para parecer otro.
- Identificarse: el User-Agent, en las dos fases, termina en `CarestiaPrueba/0.1 (+https://carestia.cl; contacto@carestia.cl)`.
- Solo las páginas de búsqueda. No llamar a ninguna API de los sitios ni usar claves que vengan en su código, no leer `/api/` ni `/_next/` de Santa Isabel, sin sesión, sin elegir local.
- Como máximo 32 pedidos en toda la corrida (8 términos, 2 sitios, 2 fases), uno a la vez, con 3 segundos o más entre pedidos al mismo sitio. Una sola corrida válida; si falla por un error tuyo, se arregla y se corre una vez más, no en bucle.
- Respetar robots.txt: el script lo baja primero y no pide ninguna URL que ese archivo bloquee para `*`.
- Ninguna cifra de la prueba se escribe en textos del sitio ni en `textos/`.

Al terminar:
- Quita el disparo por `push` del workflow y deja solo `workflow_dispatch`.
- Abre un PR en borrador con: la tabla de `resumen.md`, la comparación de tus precios de la fase que funcionó contra la tabla "Lectura desde Chrome" de `claude/Prompt_prueba_supermercados.md` (mismo producto, diferencia en pesos), qué fase funcionó en cada sitio, cuánto tardó la corrida y lo que no pudiste verificar.
- No lo mergees ni lo saques de borrador. Si algo de esto choca con CLAUDE.md o con lo que ves en el repo, frena y explícalo en el PR en vez de inventar.

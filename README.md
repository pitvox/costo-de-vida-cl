# Índices del costo de vida · Chile

Índices propios del costo de la vida cotidiana en Chile, construidos sobre precios públicos y presentados como series de tiempo con gráficos. Empieza por cuatro canastas de la Región Metropolitana — **Asado, Ensalada, Fruta y Desayuno** — actualizadas cada semana.

La idea: que mirar cuánto cuesta lo de todos los días sea tan fácil como mirar el gráfico de un activo. No es un comparador de precios (no te dice dónde comprar más barato); te dice si algo está **caro o barato frente al mismo mes de los últimos 10 años**, descontada la inflación.

## Cómo funciona

- **`indices.py`** — descarga los precios al consumidor de ODEPA (2008–2026), arma cada canasta, la deflacta con el IPC a pesos del último mes con IPC y calcula la estadística, con el veredicto por temporada de cada índice (`comparar_temporada`, `resumen_temporada`). Escribe `indices.json`, con el mes del último IPC en `ipc_mes`.
- **`uf.py`** — aparte de `indices.py`: pide la UF diaria al Banco Central (secretos `BCCH_USER` y `BCCH_PASS`, con `mindicador.cl` de respaldo) y escribe `datos/uf.json` con la UF de cada lunes desde 2007-12-31. Nunca corta el build. La UF salió de la interfaz (decisión del dueño): `datos/uf.json` se sigue escribiendo y publicando con `datos/`, pero `build_site.py` no lo lee y ninguna página la ofrece.
- **`build_site.py`** — genera la portada `index.html` en formato tabla (lo que más se movió esta semana, la tabla de productos y los 4 índices con su veredicto, en HTML estático: cada fila lleva a su ficha) y `graficos.html`, la app con las cuatro pestañas, línea/velas, estacionalidad, desglose de componentes, Comparar y Arma tu canasta. Los links viejos de la app que entraban por la portada (`/#comparar`, `/#canasta=...`) se redirigen a `graficos.html` con el mismo hash. `graficos.html` trae inline solo el primer pantallazo (el resumen de los 4 índices, la serie del primero y la lista de productos); el resto va a `datos/` y se pide a demanda: `datos/indices/{codigo}.json` (cada índice con su serie completa), `datos/productos/{slug}.json` (la serie de cada producto, para Comparar y Arma tu canasta) y `datos/catalogo.json` (una fila liviana por producto, de donde sale también la portada). `indices.json` se sigue publicando igual.
- **Gráficos de TradingView (Advanced Charts)** — la librería está en un repo privado de TradingView y su licencia prohíbe que esté en un repo público: `actualizar.yml` la descarga al publicar (secreto `TV_LIBRARY_TOKEN`, tag fijo `v32.2.0` en el workflow o el que fije la variable `TV_LIBRARY_TAG`; con los dos vacíos, el último tag estable) y la deja solo en el sitio, en `/charting_library/`. Si la descarga falla, el sitio se publica igual con Lightweight Charts y el run termina en rojo para que llegue el correo. `build_site.py` genera `carestia-tv.js` (el datafeed, que lee `datos/` y calcula Tu canasta a partir de los productos que elige cada persona), `carestia-tv.css` (el tema) y `/prueba-graficos.html`, una página oculta de prueba. Los gráficos parten en línea y en 1S; el datafeed arma 2S, 1M, 3M, 6M y 12M juntando semanas, y cada serie existe ajustada por inflación y a precio de la época (`{slug}-epoca`); el datafeed todavía sabe armarlas en UF (`{slug}-uf`, con su opción `uf`), pero ninguna página la usa. La guardia `guardia-tradingview.yml` falla si la librería llega a entrar al repo.
- **`tarjetas.py`** — dibuja con Pillow (y las fuentes de `fuentes/`, licencia OFL) las og:image de 1200 x 630 que muestran WhatsApp y las redes: una por ficha, una por índice y la de la portada, en `og/`. Cada índice tiene además su página para compartir, `/indices/{codigo}.html`, y la prensa tiene `/prensa.html`.
- **`textos/`** — textos institucionales y legales (términos, privacidad, acerca, contacto, metodología, notas metodológicas, 404), literales: `build_site.py` solo les da formato HTML. `/metodologia.html` sale de `textos/metodologia.md` (Cómo se calcula, Fuentes y Deslinde), con las canastas generadas desde `BASKETS` y las notas metodológicas al final.
- **`.github/workflows/actualizar.yml`** — recalcula y republica el sitio **todos los viernes** de forma automática, después de que ODEPA publica.

Correr localmente:

```bash
pip install pandas numpy requests pillow
python indices.py
python uf.py            # opcional: escribe datos/uf.json (el sitio ya no ofrece la UF)
python build_site.py
python -m http.server   # y abrir http://localhost:8000 (graficos.html pide datos/ por fetch: no funciona abriendo el archivo directo)
```

## Metodología (resumen)

Cada índice es una **canasta fija** de cantidades (tipo Laspeyres): lo que cambia en el tiempo es el precio, no qué se compra. El costo semanal es la suma de `cantidad × precio` de cada producto.

- **Precio de la época y ajustado por inflación** — se muestran los dos. El precio de la época es el que se pagó esa semana; ajustado por inflación, cada semana se lleva con el IPC a pesos del último mes con IPC publicado (el sitio lo dice: "en pesos de agosto de 2026"), para comparar a través del tiempo sin que la inflación general distorsione. El número grande de cada ficha es el precio de esta semana. El veredicto y los percentiles se calculan siempre ajustados por inflación.
- **Deflactación** — por IPC empalmado del BCCh (base 2023=100, serie `G073.IPC.IND.2023.M`). Las variaciones del empalme BCCh pueden diferir marginalmente de las variaciones oficiales INE mes a mes; para series reales de largo plazo el empalme es el instrumento apropiado.
- **Caro / barato** — por **temporada**: el precio de esta semana frente al promedio del mismo mes en cada uno de los 10 años anteriores (los que tengan precio ese mes, si son al menos 5). CARO si es más caro que en 7 o más de cada 10, BARATO si en 3 o menos, NORMAL entre medio (escalado con menos de 10 años). El color de un índice cambia solo si la nueva zona se mantiene dos semanas seguidas, y su frase sigue al color con los números de esta semana ("Dentro de lo normal para octubre: más caro que en 7 de los últimos 10."). Mientras el color espera, la tarjeta de la portada, /graficos.html y la tarjeta og del índice dicen "Primera semana en zona cara; el color cambia si se repite la próxima." (o barata, o normal). Una ficha sin precio esta semana dice "Sin precio de ODEPA esta semana. Último dato: $X, semana del dd-mm-aaaa." (el precio de la época de esa semana) y lleva la frase de temporada solo si ese dato tiene 4 semanas o menos. Con menos de 5 años de ese mes vale el **percentil histórico** de antes (verde <33, amarillo 33–66, rojo >66), que además se sigue mostrando como dato secundario. Los productos llevan la frase, sin color.
- **Estacionalidad** — patrón típico por mes, quitando la tendencia; indica en qué meses la canasta suele estar más barata o más cara.
- **Unidades** — ODEPA cotiza por envase (`pan de 250 gramos`, `bandeja 12 unidades`, `caja de 1 litro`, etc.). El pipeline lee el contenido neto de cada envase y normaliza a precio por kilo / unidad / litro real.
- **Velas** (vista opcional) — semanales; el cuerpo es el cambio semana a semana y la mecha es el **rango real de precios entre puntos de venta** (mínimo–máximo que releva ODEPA esa semana).

**Límites declarados:** cubre solo la Región Metropolitana; usa el promedio de los puntos que ODEPA releva cada semana; cada canasta tiene distinta profundidad histórica porque los productos entran al registro de ODEPA en años distintos.

## Fuentes

- **Precios:** [ODEPA](https://datos.odepa.gob.cl) — Oficina de Estudios y Políticas Agrarias, precios al consumidor. Datos abiertos bajo licencia **Creative Commons Attribution (CC-BY)**.
- **Inflación:** IPC del Banco Central de Chile (con `mindicador.cl` como respaldo).
- **UF:** valor diario del Banco Central de Chile (con `mindicador.cl` como respaldo), en `datos/uf.json`; el sitio ya no la muestra.

## Deslinde

Información de consumo con fines informativos. No constituye asesoría ni recomendación de inversión. Los datos provienen de fuentes públicas de terceros y pueden contener errores o cambios de metodología.

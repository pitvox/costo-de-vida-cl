# Índices del costo de vida · Chile

Índices propios del costo de la vida cotidiana en Chile, construidos sobre precios públicos y presentados como series de tiempo con gráficos. Empieza por cuatro canastas de la Región Metropolitana — **Asado, Ensalada, Fruta y Desayuno** — actualizadas cada semana.

La idea: que mirar cuánto cuesta lo de todos los días sea tan fácil como mirar el gráfico de un activo. No es un comparador de precios (no te dice dónde comprar más barato); te dice si algo está **caro o barato respecto de su propia historia**, descontada la inflación.

## Cómo funciona

- **`indices.py`** — descarga los precios al consumidor de ODEPA (2008–2026), arma cada canasta, la deflacta a pesos de hoy con el IPC y calcula la estadística. Escribe `indices.json`.
- **`build_site.py`** — genera la portada `index.html` en formato tabla (los 4 índices con su veredicto, lo que más se movió esta semana y la tabla de productos, en HTML estático: cada fila lleva a su ficha) y `graficos.html`, la app con las cuatro pestañas, línea/velas, estacionalidad, desglose de componentes, Comparar y Arma tu canasta. Los links viejos de la app que entraban por la portada (`/#comparar`, `/#canasta=...`) se redirigen a `graficos.html` con el mismo hash. `graficos.html` trae inline solo el primer pantallazo (el resumen de los 4 índices, la serie del primero y la lista de productos); el resto va a `datos/` y se pide a demanda: `datos/indices/{codigo}.json` (cada índice con su serie completa), `datos/productos/{slug}.json` (la serie de cada producto, para Comparar y Arma tu canasta) y `datos/catalogo.json` (una fila liviana por producto, de donde sale también la portada). `indices.json` se sigue publicando igual.
- **Gráficos de TradingView (Advanced Charts)** — la librería está en un repo privado de TradingView y su licencia prohíbe que esté en un repo público: `actualizar.yml` la descarga al publicar (secreto `TV_LIBRARY_TOKEN`, tag fijo `v32.2.0` en el workflow o el que fije la variable `TV_LIBRARY_TAG`; con los dos vacíos, el último tag estable) y la deja solo en el sitio, en `/charting_library/`. Si la descarga falla, el sitio se publica igual con Lightweight Charts y el run termina en rojo para que llegue el correo. `build_site.py` genera `carestia-tv.js` (el datafeed, que lee `datos/` y calcula Tu canasta a partir de los productos que elige cada persona), `carestia-tv.css` (el tema) y `/prueba-graficos.html`, una página oculta de prueba. La guardia `guardia-tradingview.yml` falla si la librería llega a entrar al repo.
- **`textos/`** — textos institucionales y legales (términos, privacidad, acerca, contacto, metodología, notas metodológicas, 404), literales: `build_site.py` solo les da formato HTML. `/metodologia.html` sale de `textos/metodologia.md` (Cómo se calcula, Fuentes y Deslinde), con las canastas generadas desde `BASKETS` y las notas metodológicas al final.
- **`.github/workflows/actualizar.yml`** — recalcula y republica el sitio **todos los viernes** de forma automática, después de que ODEPA publica.

Correr localmente:

```bash
pip install pandas numpy requests
python indices.py
python build_site.py
python -m http.server   # y abrir http://localhost:8000 (graficos.html pide datos/ por fetch: no funciona abriendo el archivo directo)
```

## Metodología (resumen)

Cada índice es una **canasta fija** de cantidades (tipo Laspeyres): lo que cambia en el tiempo es el precio, no qué se compra. El costo semanal es la suma de `cantidad × precio` de cada producto.

- **Nominal vs. pesos de hoy** — se muestran ambos. El "real" reexpresa cada semana en pesos actuales usando el IPC, para comparar a través del tiempo sin que la inflación general distorsione.
- **Deflactación** — por IPC empalmado del BCCh (base 2023=100, serie `G073.IPC.IND.2023.M`). Las variaciones del empalme BCCh pueden diferir marginalmente de las variaciones oficiales INE mes a mes; para series reales de largo plazo el empalme es el instrumento apropiado.
- **Caro / barato** — por **percentil histórico**: dónde cae el costo de esta semana en la distribución de toda su historia (en pesos de hoy). Verde <33, amarillo 33–66, rojo >66. El umbral es una convención de presentación, no una verdad física.
- **Estacionalidad** — patrón típico por mes, quitando la tendencia; indica en qué meses la canasta suele estar más barata o más cara.
- **Unidades** — ODEPA cotiza por envase (`pan de 250 gramos`, `bandeja 12 unidades`, `caja de 1 litro`, etc.). El pipeline lee el contenido neto de cada envase y normaliza a precio por kilo / unidad / litro real.
- **Velas** (vista opcional) — semanales; el cuerpo es el cambio semana a semana y la mecha es el **rango real de precios entre puntos de venta** (mínimo–máximo que releva ODEPA esa semana).

**Límites declarados:** cubre solo la Región Metropolitana; usa el promedio de los puntos que ODEPA releva cada semana; cada canasta tiene distinta profundidad histórica porque los productos entran al registro de ODEPA en años distintos.

## Fuentes

- **Precios:** [ODEPA](https://datos.odepa.gob.cl) — Oficina de Estudios y Políticas Agrarias, precios al consumidor. Datos abiertos bajo licencia **Creative Commons Attribution (CC-BY)**.
- **Inflación:** IPC del Banco Central de Chile (con `mindicador.cl` como respaldo).

## Deslinde

Información de consumo con fines informativos. No constituye asesoría ni recomendación de inversión. Los datos provienen de fuentes públicas de terceros y pueden contener errores o cambios de metodología.

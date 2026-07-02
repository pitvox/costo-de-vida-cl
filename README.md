# Índices del costo de vida · Chile

Índices propios del costo de la vida cotidiana en Chile, construidos sobre precios públicos y presentados como series de tiempo con gráficos. Empieza por cuatro canastas de la Región Metropolitana — **Asado, Ensalada, Fruta y Desayuno** — actualizadas cada semana.

La idea: que mirar cuánto cuesta lo de todos los días sea tan fácil como mirar el gráfico de un activo. No es un comparador de precios (no te dice dónde comprar más barato); te dice si algo está **caro o barato respecto de su propia historia**, descontada la inflación.

## Cómo funciona

- **`indices.py`** — descarga los precios al consumidor de ODEPA (2008–2026), arma cada canasta, la deflacta a pesos de hoy con el IPC y calcula la estadística. Escribe `indices.json`.
- **`build_site.py`** — genera `index.html`, un sitio autocontenido con las cuatro pestañas, línea/velas, estacionalidad y desglose de componentes.
- **`.github/workflows/actualizar.yml`** — recalcula y republica el sitio **todos los viernes** de forma automática, después de que ODEPA publica.

Correr localmente:

```bash
pip install pandas numpy requests
python indices.py
python build_site.py
open index.html
```

## Metodología (resumen)

Cada índice es una **canasta fija** de cantidades (tipo Laspeyres): lo que cambia en el tiempo es el precio, no qué se compra. El costo semanal es la suma de `cantidad × precio` de cada producto.

- **Nominal vs. pesos de hoy** — se muestran ambos. El "real" reexpresa cada semana en pesos actuales usando el IPC, para comparar a través del tiempo sin que la inflación general distorsione.
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

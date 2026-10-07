# Carne de vacuno: nota de datos para prensa

Análisis aparte del sitio: no lo usa el pipeline ni se publica en carestia.cl.
El resultado está en [informe.md](informe.md) (y en [informe.pdf](informe.pdf),
una página carta) y el gráfico de 1080 x 1080, en
[grafico_vacuno.png](grafico_vacuno.png).

## Cómo reproducirlo

```bash
pip install pandas numpy requests matplotlib
cd analisis/vacuno
python descargar.py   # sitio, ODEPA, Banco Central e INE a datos_crudos/ (unos 720 MB)
python vacuno.py      # las cifras, en resultados/
python verificar.py   # cada cifra contra ODEPA, el IPC y el sitio (unos dos minutos)
python graficar.py    # grafico_vacuno.png
python imprimir.py    # informe.pdf (necesita pandoc y Chromium)
```

`datos_crudos/` no va al repositorio. `descargar.py` anota en
`datos_crudos/descarga.json` la URL, la hora (UTC), el tamaño y el sha256 de
cada archivo; las cifras de esta nota salen del `indices.json` de carestia.cl
del 7 de octubre de 2026 (sha256 `b73103d0639c...`, en `resultados/resumen.json`).
El sitio se actualiza cada viernes: para repetir estas cifras sin red, los
tests usan `resultados/series_vacuno.json`, las series de ese archivo.

## Las reglas

Son las del sitio, sobre la serie publicada de cada corte (precio por kilo
ajustado por inflación, en pesos del último IPC):

- **Precio de esta semana**: el último de la serie, el número grande de la
  ficha. En su semana, ajustado y de la época son el mismo.
- **Frente a toda su historia**: en qué parte de sus semanas el precio fue
  menor, como la frase de la ficha ("más caro que en el 96% de las semanas").
- **Mismo mes de los últimos 10 años**: `comparar_temporada` de `indices.py`,
  el precio de esta semana frente al promedio de septiembre de cada uno de los
  10 años anteriores.
- **A un año**: contra 52 semanas antes, la columna "1 año" de la portada.
- **En el 5% más caro de su historia**: más caro que en al menos el 95% de sus
  semanas, sin redondear.
- **En su precio más alto en al menos 10 años**: supera al precio de cada
  semana de los 10 años anteriores (desde la semana que contiene el mismo día
  de hace 10 años; la serie tiene que llegar hasta ahí), y se afirma solo si
  supera al máximo de esa ventana en más de 1%, para que una revisión del IPC
  no lo dé vuelta. Es semana contra semana; la comparación del promedio del
  mes, que el sitio no muestra, va solo en la robustez.

## Archivos

| Archivo | Qué es |
|---|---|
| `descargar.py` | Baja la foto del sitio desplegado (indices.json, catálogo, portada, fichas y series de los cortes), los CSV de ODEPA 2008 a 2026, dos cuadros públicos del Banco Central y el IPC del INE |
| `vacuno.py` | Las cifras de cada corte, con las reglas de arriba |
| `verificar.py` | Rehace las series desde los CSV crudos de ODEPA con `indices.series_productos`; compara el factor de inflación del sitio con el empalme del Banco Central (variación a 12 meses, G073.IPC.V12.2023.M) y con el INE desde 2024; compara cada cifra con lo que muestra el sitio; y mide qué tan firmes son A, B y C con otros deflactores, con el IPC de septiembre, sin la limpieza del sitio, sin los supermercados en línea y con el promedio de cada mes |
| `graficar.py` | El gráfico de los cuatro cortes principales desde 2016 |
| `imprimir.py` | `informe.pdf`, el informe en una página carta, con la huella de `informe.md` en su título |
| `resultados/series_vacuno.json` | Las 24 series usadas (del indices.json del 7 de octubre de 2026) |
| `resultados/cortes.csv` | Las cifras de cada corte |
| `resultados/resumen.json` | Las tres cifras de la nota y el sha256 del indices.json |
| `resultados/verificacion.csv` | Cada comparación, con su fuente y si coincide (las filas de robustez van con "ok" vacío) |
| `resultados/deflactor.csv` | El factor de inflación del sitio, mes a mes, frente al Banco Central y al INE |
| `resultados/robustez.csv` | A, B y C con cada escenario |

## Fuentes y licencias

- Carestía (carestia.cl), con datos de ODEPA.
- ODEPA, precios al consumidor: licencia [CC BY 4.0](https://datos.odepa.gob.cl/manual/terminos-y-condiciones.pdf).
- Banco Central de Chile, base de datos estadísticos: IPC con empalme del
  Banco Central (variación a 12 meses) y con empalme del INE.
- INE, Índice de Precios al Consumidor (bases 2018 y 2023): licencia
  [CC BY-SA 4.0](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos).
  `resultados/deflactor.csv` deriva en parte de series del INE y se comparte
  bajo la misma licencia.

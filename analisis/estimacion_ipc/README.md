# Prueba hacia atrás: IPC de alimentos y canasta básica con precios de ODEPA

Análisis aparte del sitio: no lo usa el pipeline ni se publica en carestia.cl.
El resultado está en [informe.md](informe.md).

## Cómo reproducirlo

```bash
pip install pandas numpy requests matplotlib
cd analisis/estimacion_ipc
python descargar.py      # INE y ODEPA a datos_crudos/ (unos 720 MB)
python odepa_mensual.py  # precios semanales limpios de la RM a datos/
python armar_mapa.py     # mapa_productos.csv y mapa_cba.csv
python estimar.py        # prueba hacia atrás del IPC de alimentos, en resultados/
python canasta.py        # canasta básica valorizada con ODEPA, en resultados/
python graficar.py       # grafico_estimado_oficial.png
```

`datos_crudos/` y `datos/` no van al repositorio: los regeneran los dos primeros pasos.

## Archivos

| Archivo | Qué es |
|---|---|
| `descargar.py` | Baja las series del IPC del INE (bases 2018 y 2023, referenciales y analíticos empalmados) y los precios al consumidor de ODEPA |
| `ine.py` | Lee los cuadros del INE |
| `odepa_mensual.py` | Precios de ODEPA en la RM por producto y unidad, con la limpieza del sitio |
| `armar_mapa.py` | Escribe los dos mapas a partir de las glosas del INE y de la canasta |
| `estimar.py` | Estimación mensual del IPC de alimentos y comparación con el dato oficial |
| `canasta.py` | Canasta Básica de Alimentos con precios de ODEPA frente al valor del Ministerio |
| `graficar.py` | Gráfico del informe |
| `mapa_productos.csv` | Producto del IPC (código, glosa, ponderación) y sus productos ODEPA |
| `mapa_cba.csv` | Producto de la canasta básica y sus productos ODEPA |
| `calendario_ipc.csv` | Fecha de publicación de cada IPC, sacada de la portada de cada boletín del INE |
| `cba_2024.csv` | Composición de la canasta básica, metodología 2024 (anexo 6.2) |
| `cba_publicada.csv` | Valor mensual publicado de la canasta básica, 2019 a 2026 (cuadro 1 de cada informe) |
| `resultados/` | Estimaciones, métricas, sensibilidad y canasta mes a mes |

## Fuentes y licencias

- INE, Índice de Precios al Consumidor (series de tiempo, referenciales y empalmadas): licencia
  [CC BY-SA 4.0](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos). Los archivos de
  esta carpeta que contienen o derivan de series del INE (`mapa_productos.csv`, `calendario_ipc.csv` y
  `resultados/`) se comparten bajo la misma licencia. Son elaboración propia: el INE no hizo ni revisó
  estas estimaciones.
- ODEPA, precios al consumidor: licencia [CC BY 4.0](https://datos.odepa.gob.cl/manual/terminos-y-condiciones.pdf).
- Ministerio de Desarrollo Social y Familia, Canasta Básica de Alimentos
  ([metodología 2024](https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2024/Metodologia_de_Medicion_de_la_Pobreza_por_Ingresos_2024.pdf)
  e [informes mensuales](https://observatorio.ministeriodesarrollosocial.gob.cl/nueva-serie-cba-2026)): el
  Observatorio Social no declara licencia; es información pública (Ley 20.285) y se cita como fuente.

"""
informe.py - Informe Carestía mensual (tabla de datos)
======================================================
Script independiente del pipeline del sitio: NO toca build_site.py, ni
indices.py, ni el workflow. Reutiliza (via import) las funciones de
indices.py para cargar la data ODEPA y el IPC (misma fusión BCCh /
mindicador / manual, misma compuerta de validación) y construir las
series REALES —en pesos de hoy— de los productos del catálogo con las
mismas compuertas de unidades (series_productos).

Métricas por producto, sobre su serie real semanal:
  a) Percentil histórico de la última semana: 100 · fracción de semanas
     históricas con precio <= al actual (mismo cálculo que indices.resumen).
  b) Percentil de temporada: la última semana contra las semanas históricas
     de su misma época del año — semana ISO a distancia circular <= 6
     (mod 52), la MISMA ventana del constructor de canastas del sitio; con
     menos de 30 comparables el percentil es ruido y se omite. Percentil =
     100 · fracción de comparables estrictamente menores al precio actual.
  c) z-score de la última semana contra la media y la desviación móviles de
     52 semanas (las últimas 52 semanas de la grilla semanal, ventana
     completa requerida: un producto estacional con huecos queda sin z).
  d) Variación a 4 y a 12 semanas: precio_actual / precio_hace_k_semanas - 1.

SCORE DE TENSIÓN — fórmula:
    score = promedio simple de los componentes disponibles entre:
      - percentil histórico                        (escala 0..100)
      - percentil de temporada                     (escala 0..100)
      - z-score normalizado a 0..100 con la CDF normal estándar:
            z_norm = 100 · Φ(z),  Φ(z) = 0.5 · (1 + erf(z / √2))
    Un componente sin dato (temporada con <30 comparables, z-score sin
    ventana completa de 52 semanas) se excluye del promedio y el score es
    el promedio de los que sí existen. Score alto = tensión al alza (zona
    alta del rango); score bajo = descuento estacional (zona baja del
    rango). Para entrar al ranking un producto necesita >= 30 semanas con
    dato y su última semana a <= 4 semanas de la semana más reciente del
    catálogo (así un producto descontinuado no distorsiona la tabla).

Salida: informe_YYYY-MM.md con
  - los 4 índices oficiales (precio real / percentil / vs promedio),
  - top-10 por tensión al alza y top-5 al descuento,
  - radar estacional: productos cuyo mes históricamente más caro o más
    barato (según la estacionalidad media de su serie,
    indices.estacionalidad) cae en los próximos 2 meses; se listan solo
    los de amplitud estacional >= 8% para que el radar no sea ruido.

Correr a mano:
  python informe.py        (imprime la ruta del .md generado)
"""

import math
import os

import numpy as np
import pandas as pd

from indices import (BASKETS, calcular, cargar_ipc, cargar_odepa, clp,
                     estacionalidad, series_productos)

VENTANA_TEMPORADA = 6        # semanas ISO a cada lado (circular, mod 52)
MIN_COMPARABLES = 30         # bajo esto el percentil de temporada se omite
VENTANA_Z = 52               # semanas de la media/desviación móviles
MIN_SEMANAS_RANKING = 30     # historia mínima para rankear un producto
MAX_REZAGO_SEMANAS = 4       # frescura: última semana vs la más nueva del catálogo
AMPLITUD_MIN_RADAR = 8       # % mínimo de amplitud estacional para el radar
TOP_ALZA, TOP_DESCUENTO = 10, 5

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# ---------------- reconstrucción de series del catálogo ----------------
def serie_producto(p: dict) -> pd.Series:
    """Serie real semanal desde el formato compacto {t0, v} del catálogo
    (enteros semanales consecutivos desde t0, None en semanas sin dato)."""
    idx = pd.date_range(p["t0"], periods=len(p["v"]), freq="7D")
    vals = [np.nan if v is None else float(v) for v in p["v"]]
    return pd.Series(vals, index=idx, dtype=float)


# ---------------- métricas ----------------
def _dist_circular(a: int, b: int) -> int:
    """Distancia entre semanas ISO mod 52: diciembre y enero son vecinos."""
    d = abs(int(a) - int(b)) % 52
    return min(d, 52 - d)


def percentil_historico(s: pd.Series):
    validos = s.dropna()
    if validos.empty:
        return None
    ult = float(validos.iloc[-1])
    return round(100.0 * float((validos <= ult).mean()))


def percentil_temporada(s: pd.Series):
    validos = s.dropna()
    if len(validos) < 2:
        return None
    ult = float(validos.iloc[-1])
    semanas = validos.index.isocalendar().week.astype(int)
    w_act = int(semanas.iloc[-1])
    hist = validos.iloc[:-1]
    cerca = [_dist_circular(w, w_act) <= VENTANA_TEMPORADA
             for w in semanas.iloc[:-1]]
    comp = hist[np.asarray(cerca)]
    if len(comp) < MIN_COMPARABLES:
        return None
    return round(100.0 * float((comp < ult).mean()))


def zscore_movil(s: pd.Series):
    """z de la última semana vs media/desviación de las últimas 52 semanas
    de la grilla semanal (la ventana debe estar completa)."""
    if len(s) < VENTANA_Z:
        return None
    ventana = s.iloc[-VENTANA_Z:]
    if ventana.isna().any():
        return None
    desv = float(ventana.std())
    if not desv or math.isnan(desv):
        return None
    return round(float((ventana.iloc[-1] - ventana.mean()) / desv), 2)


def variacion(s: pd.Series, k: int):
    """Variación % entre la última semana y k semanas atrás en la grilla."""
    if len(s) <= k or pd.isna(s.iloc[-1]) or pd.isna(s.iloc[-1 - k]):
        return None
    return round((float(s.iloc[-1]) / float(s.iloc[-1 - k]) - 1) * 100, 1)


def z_normalizado(z):
    """z-score llevado a escala 0..100 vía CDF normal: 100·Φ(z)."""
    if z is None:
        return None
    return 100.0 * 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))


def score_tension(pct_hist, pct_temp, z):
    """Promedio simple de los componentes disponibles (ver docstring)."""
    partes = [c for c in (pct_hist, pct_temp, z_normalizado(z)) if c is not None]
    if not partes:
        return None
    return round(sum(partes) / len(partes), 1)


def metricas_productos(productos: dict) -> list:
    """Lista de métricas por producto del catálogo, ya filtrada por las
    compuertas de historia mínima y frescura del docstring."""
    series = {slug: serie_producto(p) for slug, p in productos.items()}
    con_dato = {slug: s.dropna() for slug, s in series.items()}
    con_dato = {slug: s for slug, s in con_dato.items() if not s.empty}
    if not con_dato:
        return []
    tope = max(s.index[-1] for s in con_dato.values())
    filas = []
    for slug, validos in con_dato.items():
        if len(validos) < MIN_SEMANAS_RANKING:
            continue
        if (tope - validos.index[-1]).days > MAX_REZAGO_SEMANAS * 7:
            continue
        s = series[slug]
        p = productos[slug]
        pct_hist = percentil_historico(s)
        pct_temp = percentil_temporada(s)
        z = zscore_movil(s)
        filas.append({
            "slug": slug, "label": p["label"], "unidad": p["unidad"],
            "precio": float(validos.iloc[-1]),
            "pct_hist": pct_hist, "pct_temp": pct_temp, "z": z,
            "var4": variacion(s, 4), "var12": variacion(s, 12),
            "score": score_tension(pct_hist, pct_temp, z),
        })
    return [f for f in filas if f["score"] is not None]


def radar_estacional(productos: dict, hoy: pd.Timestamp) -> list:
    """Productos cuyo mes históricamente más caro o más barato (según la
    estacionalidad media de su serie) cae en los próximos 2 meses."""
    m1 = hoy.month % 12 + 1
    m2 = m1 % 12 + 1
    filas = []
    for p in productos.values():
        est = estacionalidad(serie_producto(p))
        if not est or est.get("amplitud", 0) < AMPLITUD_MIN_RADAR:
            continue
        if est["mes_caro"] in (m1, m2):
            filas.append({"label": p["label"], "tipo": "zona alta del rango",
                          "mes": est["mes_caro"], "amplitud": est["amplitud"]})
        if est["mes_barato"] in (m1, m2):
            filas.append({"label": p["label"], "tipo": "descuento estacional",
                          "mes": est["mes_barato"], "amplitud": est["amplitud"]})
    return sorted(filas, key=lambda f: -f["amplitud"])


def resumen_indices(df: pd.DataFrame, ipc: pd.Series) -> list:
    """Los 4 índices oficiales: precio real, percentil histórico y
    vs-promedio, con el mismo cálculo de indices.resumen."""
    filas = []
    for meta in BASKETS.values():
        d, _comp = calcular(df, ipc, meta["items"])
        real = d["real"].dropna()
        ur = float(real.iloc[-1])
        filas.append({
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
            "precio": ur,
            "percentil": round(100.0 * float((real <= ur).mean())),
            "vs_promedio": round((ur / float(real.mean()) - 1) * 100),
            "fecha": real.index[-1],
        })
    return filas


# ---------------- markdown ----------------
def _pc(v):
    return "s/d" if v is None else str(int(v))


def _pct(v):
    return "s/d" if v is None else f"{v:+.1f}%"


def _z(v):
    return "s/d" if v is None else f"{v:+.2f}"


def _fila_producto(f):
    return (f"| {f['label']} | {clp(f['precio'])} | {f['unidad']} | "
            f"{_pc(f['pct_hist'])} | {_pc(f['pct_temp'])} | {_z(f['z'])} | "
            f"{_pct(f['var4'])} | {_pct(f['var12'])} | {f['score']:.1f} |")


CABECERA_PRODUCTOS = (
    "| Producto | Precio real | Unidad | Perc. hist. | Perc. temporada | "
    "z-score | Var. 4s | Var. 12s | Score |\n"
    "|---|---:|---|---:|---:|---:|---:|---:|---:|")


def construir_informe(filas_indices: list, productos: dict,
                      hoy: pd.Timestamp) -> str:
    """Arma el markdown del informe a partir del resumen de índices y el
    catálogo de productos (formato compacto de series_productos)."""
    met = metricas_productos(productos)
    alza = sorted(met, key=lambda f: (-f["score"], -(f["pct_hist"] or 0)))
    descuento = sorted(met, key=lambda f: (f["score"], f["pct_hist"] or 0))
    radar = radar_estacional(productos, hoy)
    m1, m2 = hoy.month % 12 + 1, (hoy.month % 12 + 1) % 12 + 1

    fecha_dato = max((f["fecha"] for f in filas_indices), default=None)
    L = [f"# Informe Carestía — {MESES[hoy.month - 1]} {hoy.year}", ""]
    if fecha_dato is not None:
        L.append(f"Semana de datos: {fecha_dato:%d-%m-%Y}. "
                 "Precios reales (deflactados por IPC, en pesos de hoy), "
                 "Región Metropolitana, fuente ODEPA.")
        L.append("")

    L += ["## Índices oficiales", "",
          "| Índice | Precio real | Percentil histórico | vs promedio |",
          "|---|---:|---:|---:|"]
    for f in filas_indices:
        L.append(f"| {f['nombre']} ({f['subtitulo']}) | {clp(f['precio'])} | "
                 f"{f['percentil']} | {f['vs_promedio']:+d}% |")

    L += ["", f"## Top {TOP_ALZA}: tensión al alza", "",
          "Productos en la zona alta de su rango histórico y de temporada "
          "(score = promedio de percentil histórico, percentil de temporada "
          "y z-score normalizado; detalle en el docstring del script).", "",
          CABECERA_PRODUCTOS]
    L += [_fila_producto(f) for f in alza[:TOP_ALZA]]

    L += ["", f"## Top {TOP_DESCUENTO}: al descuento", "",
          "Productos en la zona baja de su rango: descuento estacional o "
          "precios bajo su historia reciente.", "",
          CABECERA_PRODUCTOS]
    L += [_fila_producto(f) for f in descuento[:TOP_DESCUENTO]]

    L += ["", "## Radar estacional", "",
          f"Productos cuyo mes históricamente más caro o más barato cae en "
          f"los próximos 2 meses ({MESES[m1 - 1]}, {MESES[m2 - 1]}), según "
          f"la estacionalidad media de su serie (amplitud >= "
          f"{AMPLITUD_MIN_RADAR}%).", ""]
    if radar:
        L += ["| Producto | Qué se acerca | Mes | Amplitud estacional |",
              "|---|---|---|---:|"]
        L += [f"| {f['label']} | {f['tipo']} | {MESES[f['mes'] - 1]} | "
              f"{f['amplitud']}% |" for f in radar]
    else:
        L.append("Sin productos con estacionalidad marcada en la ventana.")

    L += ["", f"_{len(met)} productos rankeados de {len(productos)} en el "
          "catálogo (se exigen >= "
          f"{MIN_SEMANAS_RANKING} semanas de historia y dato fresco)._", ""]
    return "\n".join(L)


def main() -> None:
    df = cargar_odepa()
    ipc = cargar_ipc()
    filas_indices = resumen_indices(df, ipc)
    productos = series_productos(df, ipc)
    hoy = pd.Timestamp.today()
    md = construir_informe(filas_indices, productos, hoy)
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"informe_{hoy:%Y-%m}.md")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(ruta)


if __name__ == "__main__":
    main()

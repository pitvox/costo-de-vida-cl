"""
odepa_mensual.py - precios mensuales de ODEPA en la Región Metropolitana
=======================================================================
Promedio mensual del precio al consumidor de cada producto ODEPA de la RM,
para la prueba hacia atrás del IPC de alimentos (estimar.py).

Receta, la de las series de producto del sitio (indices.py), con una
diferencia: aquí cada producto tiene una serie por unidad de ODEPA. El sitio
se queda con la unidad modal; para el IPC sirve más seguir también las otras,
porque ODEPA a veces cambia el envase (el aceite pasó de litro a botella de
900 ml en julio de 2023) y una variación solo se mide dentro de una misma
unidad. Los sacos de 5, 25 y 50 kilos de las legumbres quedan fuera: no son
compras de consumidor.
- precio semanal = promedio de las filas de la semana (W-MON);
- limpieza: mediana de 8 semanas, mediana de las últimas 52 semanas con dato
  y mínimo de 3 puntos de monitoreo (indices.limpiar_semanal y
  indices.pocos_puntos);
- precio mensual = promedio de las semanas limpias cuyo lunes cae en el mes
  (con un corte opcional: solo las semanas publicadas antes de una fecha).
  Sin semanas válidas en el mes, el mes queda sin dato (sin arrastre).

Los precios quedan en pesos de la época por envase; contenido() los lleva a
kilo, unidad o litro (para la canasta básica). Para el IPC solo importa la
variación, que no depende de la unidad.
"""
import os
import re
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402


def cargar_odepa_rm(carpeta_csv: str = None) -> pd.DataFrame:
    """Filas ODEPA de la RM con el punto de monitoreo. Con 'carpeta_csv'
    (archivos {año}.csv que bajó descargar.py) no descarga; si no, usa
    indices.cargar_odepa(), que baja 2008 a 2026 del portal de ODEPA."""
    if not carpeta_csv:
        return indices.cargar_odepa()
    frames = []
    for y in sorted(indices.RESOURCES):
        ruta = os.path.join(carpeta_csv, f"{y}.csv")
        if not os.path.exists(ruta):
            continue
        with open(ruta, "rb") as fh:
            df = indices._norm(indices._leer_csv(fh.read()), y)
        frames.append(df[df["region_rm"]])
    if not frames:
        raise SystemExit(f"no hay CSV de ODEPA en {carpeta_csv}")
    return pd.concat(frames, ignore_index=True)


def clave_producto(nombre: str) -> str:
    """La clave con que se agrupan las variantes de un mismo producto
    ("Lentejas 6 mm" y "Lentejas 6mm"): minúsculas, sin espacios."""
    return re.sub(r"\s+", "", str(nombre).lower())


def contenido(unidad: str):
    """(unidad base, cantidad) del envase: indices.parse_envase_estricto, más
    los mililitros ("$/botella 900 ml" = 0,9 litros). None si no se reconoce."""
    envase = indices.parse_envase_estricto(unidad)
    if envase:
        return envase
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*ml\b", str(unidad).lower())
    return ("l", float(m.group(1).replace(",", ".")) / 1000.0) if m else None


def precios_semanales(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por producto, unidad y semana limpia: clave, serie
    ("clave | unidad"), producto, unidad, base y contenido (contenido()),
    semana (el lunes, Timestamp), precio (pesos de la época por envase) y
    puntos (puntos de monitoreo de la semana)."""
    df = df.copy()
    df["clave"] = df["ProductoBase"].map(clave_producto)
    df["Unidad"] = df["Unidad"].astype(str).str.strip()
    df = df[~df["Unidad"].str.contains("saco", case=False)]
    partes = []
    for (clave, unidad), sub in df.groupby(["clave", "Unidad"]):
        nombre = re.sub(r"\s+", " ", indices._modal(sub["ProductoBase"]))
        envase = contenido(unidad)
        semanal = sub.groupby("fecha")["Precio promedio"].mean().sort_index()
        semanal = semanal.resample("W-MON").mean()
        n_puntos = indices._puntos(sub)
        limpio, _d8, _d52 = indices.limpiar_semanal(semanal)
        malo, _dp = indices.pocos_puntos(semanal, n_puntos)
        limpio = limpio.mask(malo).dropna()
        if limpio.empty:
            continue
        partes.append(pd.DataFrame({
            "clave": clave, "serie": f"{clave} | {unidad}", "producto": nombre,
            "unidad": unidad, "base": envase[0] if envase else None,
            "contenido": envase[1] if envase else None,
            "semana": limpio.index, "precio": limpio.values,
            "puntos": (n_puntos.reindex(limpio.index).values
                       if n_puntos is not None else float("nan")),
        }))
    return pd.concat(partes, ignore_index=True).sort_values(["clave", "unidad", "semana"])


def precios_mensuales(semanal: pd.DataFrame, corte: dict = None, atraso: int = 4) -> pd.DataFrame:
    """Promedio mensual por serie (producto y unidad) de las semanas limpias
    cuyo lunes cae en el mes. Con 'corte' ({Period M: Timestamp}), en ese mes
    solo entran las semanas que ODEPA ya había publicado antes de esa fecha
    (la publica el viernes de la misma semana: lunes + 'atraso' días, 4 por
    omisión). Columnas:
    clave, serie, producto, unidad, base, contenido, mes, precio, semanas,
    puntos."""
    s = semanal.copy()
    s["mes"] = s["semana"].dt.to_period("M")
    if corte:
        limite = s["mes"].map(corte)
        publicada = s["semana"] + pd.Timedelta(days=atraso)
        s = s[limite.isna() | (publicada < limite)]
    g = s.groupby(["clave", "serie", "mes"])
    out = g.agg(producto=("producto", "first"), unidad=("unidad", "first"),
                base=("base", "first"), contenido=("contenido", "first"),
                precio=("precio", "mean"), semanas=("precio", "size"),
                puntos=("puntos", "mean")).reset_index()
    return out.sort_values(["clave", "serie", "mes"]).reset_index(drop=True)


def precio_por_unidad_base(m: pd.DataFrame) -> pd.Series:
    """Precio por kilo, unidad o litro (precio del envase / contenido)."""
    return m["precio"] / m["contenido"]


if __name__ == "__main__":
    aqui = os.path.dirname(os.path.abspath(__file__))
    carpeta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(aqui, "datos_crudos", "odepa")
    s = precios_semanales(cargar_odepa_rm(carpeta if os.path.isdir(carpeta) else None))
    salida = os.path.join(aqui, "datos", "odepa_semanal.csv")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    s.to_csv(salida, index=False)
    print(f"{salida}: {len(s)} filas, {s['clave'].nunique()} productos, "
          f"{s['serie'].nunique()} series, "
          f"{s['semana'].min():%Y-%m-%d} a {s['semana'].max():%Y-%m-%d}")

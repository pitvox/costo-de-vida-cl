"""
odepa_mensual.py - precios mensuales de ODEPA en la Región Metropolitana
=======================================================================
Promedio mensual del precio al consumidor de cada producto ODEPA de la RM,
para la prueba hacia atrás del IPC de alimentos (estimar.py).

Receta, la misma de las series de producto del sitio (indices.py):
- filas de la RM, con la unidad modal del producto (un cambio de envase no
  se lee como variación de precio);
- precio semanal = promedio de las filas de la semana (W-MON);
- limpieza: mediana de 8 semanas, mediana de las últimas 52 semanas con dato
  y mínimo de 3 puntos de monitoreo (indices.limpiar_semanal y
  indices.pocos_puntos);
- precio mensual = promedio de las semanas limpias cuyo lunes cae en el mes.
  Sin semanas válidas en el mes, el mes queda sin dato (sin arrastre).

Los precios quedan en pesos de la época y en la unidad del envase de ODEPA;
precio_por_unidad_base los lleva a kilo, unidad o litro (para la canasta
básica). Para el IPC solo importa la variación, que no depende de la unidad.
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
    (archivos {año}.csv ya bajados) no descarga; si no, usa
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


def precios_mensuales(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por producto y mes: clave, producto, unidad (la modal de
    ODEPA), base y contenido (parse_envase_estricto), mes (Period M),
    precio (pesos de la época por envase), semanas (semanas válidas en el
    mes) y puntos (promedio de puntos de monitoreo de esas semanas)."""
    df = df.copy()
    df["clave"] = df["ProductoBase"].map(clave_producto)
    filas = []
    for clave, sub in df.groupby("clave"):
        unidad = indices._modal(sub["Unidad"])
        sub = sub[sub["Unidad"].astype(str).str.strip() == unidad]
        if sub.empty:
            continue
        nombre = re.sub(r"\s+", " ", indices._modal(sub["ProductoBase"]))
        envase = indices.parse_envase_estricto(unidad)
        semanal = sub.groupby("fecha")["Precio promedio"].mean().sort_index()
        semanal = semanal.resample("W-MON").mean()
        limpio, _d8, _d52 = indices.limpiar_semanal(semanal)
        malo, _dp = indices.pocos_puntos(semanal, indices._puntos(sub))
        limpio = limpio.mask(malo).dropna()
        if limpio.empty:
            continue
        n_puntos = indices._puntos(sub)
        mes = limpio.index.to_period("M")
        g = pd.DataFrame({"precio": limpio.values, "mes": mes,
                          "puntos": (n_puntos.reindex(limpio.index).values
                                     if n_puntos is not None else float("nan"))})
        for m, gm in g.groupby("mes"):
            filas.append({
                "clave": clave, "producto": nombre, "unidad": unidad,
                "base": envase[0] if envase else None,
                "contenido": envase[1] if envase else None,
                "mes": m, "precio": float(gm["precio"].mean()),
                "semanas": int(len(gm)), "puntos": float(gm["puntos"].mean()),
            })
    return pd.DataFrame(filas).sort_values(["clave", "mes"]).reset_index(drop=True)


def precio_por_unidad_base(m: pd.DataFrame) -> pd.Series:
    """Precio por kilo, unidad o litro (precio del envase / contenido)."""
    return m["precio"] / m["contenido"]


if __name__ == "__main__":
    carpeta = sys.argv[1] if len(sys.argv) > 1 else None
    m = precios_mensuales(cargar_odepa_rm(carpeta))
    salida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "odepa_mensual.csv")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    m.assign(mes=m["mes"].astype(str)).to_csv(salida, index=False)
    print(f"{salida}: {len(m)} filas, {m['clave'].nunique()} productos, "
          f"{m['mes'].min()} a {m['mes'].max()}")

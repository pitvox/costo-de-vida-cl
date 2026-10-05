"""
ine.py - lectores de los cuadros del IPC del INE
================================================
Todos los CSV del INE vienen en latin-1, con ';' y coma decimal. Los archivos
los baja descargar.py a datos_crudos/ (ver FUENTES ahí).

- productos(base): índices mensuales y ponderación de cada producto de la
  división 01 (Alimentos y bebidas no alcohólicas), con su código armado como
  "D.G.C.SC.P". Base 2018: enero 2019 a diciembre 2023 (más la serie
  referencial de 2018). Base 2023: enero 2024 en adelante (más la serie
  referencial de 2023).
- agregado(base, division, grupo): índice mensual de una división o un grupo
  (con la serie referencial delante), para el deflactor de la canasta básica.
- alimentos_oficial(): el índice y la variación mensual publicada de
  Alimentos, de la serie de analíticos empalmados (idéntica a la división 01:
  base 2018 entre 2019 y 2023 y base 2023 desde 2024).
"""
import os

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUDOS = os.path.join(AQUI, "datos_crudos")

ARCHIVOS = {   # clave: (archivo en datos_crudos/, filas de encabezado que se saltan)
    2018: ("ine/ipc_base2018.csv", 0),
    "ref2018": ("ine/ipc_base2018_referencial.csv", 4),
    2023: ("ine/ipc_base2023.csv", 0),
    "ref2023": ("ine/ipc_base2023_referencial.csv", 3),
    "empalmados": ("ine/analiticos_empalmados.csv", 0),
}


def _leer(clave) -> pd.DataFrame:
    ruta, saltar = ARCHIVOS[clave]
    d = pd.read_csv(os.path.join(CRUDOS, ruta), sep=";", decimal=",", encoding="latin-1",
                    skiprows=saltar)
    d.columns = [" ".join(str(c).split()).replace("( % )", "(%)") for c in d.columns]
    d = d[pd.to_numeric(d["Año"], errors="coerce").notna()].copy()
    d["Año"] = d["Año"].astype(int)
    d["Mes"] = pd.to_numeric(d["Mes"]).astype(int)
    for c in ("Índice", "Ponderación"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c].astype(str).str.replace(",", "."), errors="coerce")
    return d


def _codigo(fila) -> str:
    return ".".join(str(int(float(fila[c]))) for c in ("División", "Grupo", "Clase",
                                                        "Subclase", "Producto"))


def productos(base: int) -> pd.DataFrame:
    """Productos de la división 01 de una base, con la serie referencial
    del año base delante: columnas codigo, glosa, ponderacion, mes (Period
    M), indice. La ponderación es la de la canasta (en % del IPC total)."""
    partes = []
    for clave in (f"ref{base}", base):
        d = _leer(clave)
        d = d[(pd.to_numeric(d["División"], errors="coerce") == 1) & d["Producto"].notna()]
        partes.append(pd.DataFrame({
            "codigo": d.apply(_codigo, axis=1),
            "glosa": d["Glosa"].str.strip(),
            "ponderacion": d["Ponderación"],
            "mes": pd.PeriodIndex.from_fields(year=d["Año"], month=d["Mes"], freq="M"),
            "indice": d["Índice"],
        }))
    out = pd.concat(partes, ignore_index=True)
    # la referencial no siempre trae la ponderación: la de la canasta es fija
    pond = out.dropna(subset=["ponderacion"]).groupby("codigo")["ponderacion"].first()
    out["ponderacion"] = out["codigo"].map(pond)
    return out.drop_duplicates(["codigo", "mes"], keep="last").sort_values(["codigo", "mes"])


def agregado(base: int, division: int, grupo: int = None) -> tuple:
    """(índice mensual con PeriodIndex, ponderación) de la división, o del
    grupo si se pide, con la serie referencial del año base delante."""
    partes, pond = [], None
    for clave in (f"ref{base}", base):
        d = _leer(clave)
        cod = {c: pd.to_numeric(d[c], errors="coerce") for c in ("División", "Grupo", "Clase")}
        fila = (cod["División"] == division) & cod["Clase"].isna()
        fila &= (cod["Grupo"] == grupo) if grupo else cod["Grupo"].isna()
        d = d[fila]
        if d["Ponderación"].notna().any():
            pond = float(d["Ponderación"].dropna().iloc[0])
        partes.append(pd.Series(d["Índice"].values, index=pd.PeriodIndex.from_fields(
            year=d["Año"], month=d["Mes"], freq="M")))
    s = pd.concat(partes)
    return s[~s.index.duplicated(keep="last")].sort_index(), pond


def alimentos_oficial() -> pd.DataFrame:
    """mes (Period M), indice y variacion (% publicada, 1 decimal) de
    Alimentos, diciembre 2009 en adelante."""
    d = _leer("empalmados")
    d = d[d["Glosa"].str.strip() == "Alimentos"]
    var = [c for c in d.columns if c.startswith("Variación Mensual")][0]
    return pd.DataFrame({
        "mes": pd.PeriodIndex.from_fields(year=d["Año"], month=d["Mes"], freq="M"),
        "indice": d["Índice"].values,
        "variacion": pd.to_numeric(d[var].astype(str).str.replace(",", "."), errors="coerce").values,
    }).sort_values("mes").reset_index(drop=True)

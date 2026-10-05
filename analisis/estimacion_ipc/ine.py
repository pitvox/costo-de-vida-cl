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
- alimentos_oficial(): el índice y la variación mensual publicada de
  Alimentos, de la serie de analíticos empalmados (idéntica a la división 01:
  base 2018 entre 2019 y 2023 y base 2023 desde 2024).
"""
import os

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUDOS = os.path.join(AQUI, "datos_crudos")

ARCHIVOS = {
    2018: ("ine_base2018/ipc_base2018_series_tiempo.csv", 0),
    "ref2018": ("ine_base2018/ipc_base2018_serie_referencial.csv", 4),
    2023: ("ine_base2023/cuadros_series_de_tiempo/ipc_base_20237baa955a44fe4eada201c196338fb3be.csv", 0),
    "ref2023": ("ine_base2023/cuadros_series_referenciales/"
                "ipc_ref_base_20230bd18276c47b4ec68bda28582d82207d.csv", 3),
    "empalmados": ("ine_base2023/series_empalmadas/"
                   "serie_analíticos_empalmados047c1ef98b0e463c8c5fa4a657efaa20.csv", 0),
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

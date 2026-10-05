"""
canasta.py - la Canasta Básica de Alimentos valorizada con precios de ODEPA
==========================================================================
Valor mensual por persona de la Canasta Básica de Alimentos (CBA) del
Ministerio de Desarrollo Social y Familia, metodología 2024 (cba_2024.csv: 96
productos con su cantidad mensual en gramos o mililitros y su gasto a precios
de marzo de 2022), con precios de ODEPA en la Región Metropolitana, frente al
valor del Ministerio.

Cómo reajusta el Ministerio (sección 2.9 de la metodología 2024, verificado
con los informes de 2026): CBA(t) = 66.896 x D(t) / D(marzo 2022), donde D es
el promedio, con las ponderaciones del IPC, de los índices de la división 01
(alimentos y bebidas no alcohólicas) y del grupo 11.1 (restaurantes). Base
2018 hasta diciembre de 2023 y base 2023 desde enero de 2024, enlazadas con
la serie referencial de diciembre de 2023. Antes de 2026 el Ministerio
publicaba la canasta de la metodología 2013, que es otra canasta; para 2019 a
2025 la comparación va contra esta reconstrucción, no contra un valor
publicado.

Valor con ODEPA, producto por producto:
- precio encadenado: en marzo de 2022, el mes base de la canasta, el
  promedio simple de sus productos ODEPA en pesos por kilo o litro; antes y
  después, ese nivel se mueve con la variación (media geométrica, como en
  estimar.py) de las series ODEPA con precio en los dos meses. Así un cambio
  de formato (el yogur pasó de vaso de 125 g a bolsa de 1 kilo en julio de
  2023) o una fruta que sale de temporada no se leen como variación de
  precio. Para un producto con una sola serie, el precio encadenado es su
  precio de cada mes;
- un mes sin variación ODEPA comparable, el producto se mueve como el valor
  del Ministerio;
- producto sin ODEPA: el valor que le da el Ministerio, su gasto de marzo de
  2022 reajustado con D. Así toda la diferencia queda en los productos con
  ODEPA y se puede repartir por producto.
Lo del Ministerio en el mes m (D de m) se conoce recién con el IPC de m. La
versión de fin de mes, la cifra que se podría publicar al cerrar cada mes,
usa en su lugar D de m-1 (el IPC de m-1 ya salió).

Uso: python canasta.py   (después de odepa_mensual.py y armar_mapa.py)
"""
import os

import numpy as np
import pandas as pd

import estimar
import ine
import odepa_mensual

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
RESULTADOS = os.path.join(AQUI, "resultados")
VALOR_BASE, MES_BASE = 66896, pd.Period("2022-03", "M")
DESDE = pd.Period("2019-01", "M")
ENLACE = pd.Period("2023-12", "M")


def deflactor() -> pd.Series:
    """D(t): división 01 y grupo 11.1 promediados con sus ponderaciones,
    base 2018 hasta diciembre de 2023 y base 2023 después."""
    partes = {}
    for base in (2018, 2023):
        (div, w1), (grupo, w11) = ine.agregado(base, 1), ine.agregado(base, 11, 1)
        partes[base] = (w1 * div + w11 * grupo) / (w1 + w11)
    viejo, nuevo = partes[2018], partes[2023]
    enlazado = nuevo[nuevo.index > ENLACE] * viejo[ENLACE] / nuevo[ENLACE]
    return pd.concat([viejo[viejo.index <= ENLACE], enlazado])


def cba_ministerio() -> pd.DataFrame:
    """Valor de la CBA metodología 2024 por mes: el reconstruido con D y el
    publicado (2026 en adelante), más el publicado con la metodología 2013."""
    d = deflactor()
    out = pd.DataFrame({"reconstruida": VALOR_BASE * d / d[MES_BASE]})
    pub = pd.read_csv(os.path.join(AQUI, "cba_publicada.csv"))
    pub["mes"] = pd.PeriodIndex(pub["mes"], freq="M")
    for met in (2024, 2013):
        out[f"publicada_{met}"] = pub[pub["metodologia"] == met].set_index("mes")["cba"]
    out["ministerio"] = out["publicada_2024"].fillna(out["reconstruida"])
    return out


def precios_por_kilo(semanal: pd.DataFrame) -> pd.DataFrame:
    """Pivote mes x serie ODEPA en pesos por kilo o litro (solo las series
    que vienen en kilos o litros; promedio del mes, todas las semanas)."""
    m = odepa_mensual.precios_mensuales(semanal)
    m = m[m["base"].isin(["kg", "l"])].copy()
    m["por_kilo"] = odepa_mensual.precio_por_unidad_base(m)
    return m.pivot(index="mes", columns="serie", values="por_kilo")


def precio_encadenado(precios: pd.DataFrame, series: dict, claves: list,
                      mov_ministerio: pd.Series, meses) -> tuple:
    """(precio por kilo o litro del producto de la canasta en cada mes, si
    ese mes se movió con ODEPA). None si no tiene precio en el mes base."""
    base = [precios.loc[MES_BASE, [c for c in series.get(k, []) if c in precios.columns]]
            .dropna().mean() for k in claves] if MES_BASE in precios.index else []
    base = [b for b in base if pd.notna(b)]
    if not base:
        return None, None
    rel, con = {}, {}
    for m in meses:
        r, _ = estimar.jevons(precios, precios, series, claves, m)
        con[m] = r is not None
        rel[m] = r if r is not None else mov_ministerio[m]
    p = {MES_BASE: float(np.mean(base))}
    for m in [m for m in meses if m > MES_BASE]:
        p[m] = p[m - 1] * rel[m]
    for m in sorted([m for m in meses if m < MES_BASE], reverse=True):
        p[m] = p[m + 1] / rel[m + 1]
    con[MES_BASE] = True
    return pd.Series(p).sort_index(), pd.Series(con).sort_index()


def valorizar(semanal: pd.DataFrame):
    """(resumen mensual, detalle por producto y mes)."""
    cba = pd.read_csv(os.path.join(AQUI, "mapa_cba.csv")).dropna(subset=["gasto_mar2022"])
    cba["odepa"] = cba["odepa"].fillna("")
    precios = precios_por_kilo(semanal)
    series = {}
    for col in precios.columns:
        series.setdefault(col.split(" | ")[0], []).append(col)
    ministerio = cba_ministerio()
    d = deflactor()
    meses = pd.period_range(DESDE, ministerio.index.max(), freq="M")
    factor = ministerio["ministerio"] / cba["gasto_mar2022"].sum()
    versiones = {  # (factor para los productos sin ODEPA, movimiento sin variación ODEPA)
        "": (factor, d / d.shift(1)),
        "_fin_de_mes": (factor.shift(1), d.shift(1) / d.shift(2)),
    }
    filas = []
    for _, r in cba.iterrows():
        claves = [odepa_mensual.clave_producto(x) for x in r["odepa"].split("|") if x.strip()]
        caminos = {v: precio_encadenado(precios, series, claves, mov, meses) if claves
                   else (None, None) for v, (_f, mov) in versiones.items()}
        for m in meses:
            fila = {"mes": m, "producto": r["producto"], "mapeado": bool(claves),
                    "valor_ministerio": r["gasto_mar2022"] * factor[m]}
            for v, (fac, _mov) in versiones.items():
                p, con = caminos[v]
                if p is None:
                    fila[f"valor_odepa{v}"] = r["gasto_mar2022"] * fac[m]
                    fila[f"con_odepa{v}"] = False
                else:
                    fila[f"valor_odepa{v}"] = r["cantidad_mensual"] / 1000 * p[m]
                    fila[f"con_odepa{v}"] = bool(con[m])
                    fila[f"precio_odepa{v}"] = p[m]
            filas.append(fila)
    det = pd.DataFrame(filas)
    det["diferencia"] = det["valor_odepa"] - det["valor_ministerio"]
    g = det.groupby("mes")
    con = det[det["mapeado"] & det["precio_odepa"].notna()].groupby("mes")
    res = pd.DataFrame({
        "cba_ministerio": g["valor_ministerio"].sum(),
        "cba_odepa": g["valor_odepa"].sum(),
        "cba_odepa_fin_de_mes": g["valor_odepa_fin_de_mes"].sum(),
        "peso_con_odepa": det[det["con_odepa"]].groupby("mes")["valor_ministerio"].sum()
        / g["valor_ministerio"].sum() * 100,
        "cubiertos_odepa_sobre_ministerio_pct": (con["valor_odepa"].sum()
                                                 / con["valor_ministerio"].sum() - 1) * 100,
    })
    res = res.join(ministerio[["reconstruida", "publicada_2024", "publicada_2013"]])
    res["diferencia_pct"] = (res["cba_odepa"] / res["cba_ministerio"] - 1) * 100
    res["diferencia_fin_de_mes_pct"] = (res["cba_odepa_fin_de_mes"] / res["cba_ministerio"]
                                        - 1) * 100
    for c in ("cba_ministerio", "cba_odepa", "cba_odepa_fin_de_mes"):
        res[f"var_mensual_{c[4:]}"] = res[c].pct_change() * 100
    return res, det


if __name__ == "__main__":
    semanal = pd.read_csv(os.path.join(DATOS, "odepa_semanal.csv"), parse_dates=["semana"])
    res, det = valorizar(semanal)
    os.makedirs(RESULTADOS, exist_ok=True)
    res.round(2).to_csv(os.path.join(RESULTADOS, "canasta_mensual.csv"), index_label="mes")
    det.assign(mes=det["mes"].astype(str)).round(2).to_csv(
        os.path.join(RESULTADOS, "canasta_por_producto.csv"), index=False)
    chk = res.dropna(subset=["publicada_2024"])
    err = (chk["reconstruida"] / chk["publicada_2024"] - 1).abs().max() * 100
    print(f"reconstrucción del Ministerio frente a lo publicado en 2026: error máximo {err:.3f}%")
    print(res[["cba_ministerio", "cba_odepa", "diferencia_pct", "peso_con_odepa",
               "cubiertos_odepa_sobre_ministerio_pct"]].round(1).iloc[::6].to_string())

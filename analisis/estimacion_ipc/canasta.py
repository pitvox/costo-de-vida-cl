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

Valor con ODEPA:
- producto con precio ODEPA ese mes: cantidad x precio. El precio es el
  promedio simple de sus productos ODEPA, cada uno en pesos por kilo o litro
  (promedio del mes, todas las semanas limpias);
- producto sin ODEPA (o sin precio ese mes): el valor que le da el Ministerio,
  su gasto de marzo de 2022 reajustado con D. Así toda la diferencia queda en
  los productos que sí tienen precio ODEPA, y se puede repartir por producto.
  Ese valor del mes m solo se conoce después del IPC de m; la versión en
  tiempo real (lo que se podría publicar cada semana) usa el de m-1.

Uso: python canasta.py   (después de odepa_mensual.py y armar_mapa.py)
"""
import os

import numpy as np
import pandas as pd

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
    """Pivote mes x clave ODEPA en pesos por kilo o litro (promedio de las
    series del producto que vienen en kilos o litros)."""
    m = odepa_mensual.precios_mensuales(semanal)
    m = m[m["base"].isin(["kg", "l"])].copy()
    m["por_kilo"] = odepa_mensual.precio_por_unidad_base(m)
    return m.groupby(["mes", "clave"])["por_kilo"].mean().unstack()


def valorizar(semanal: pd.DataFrame):
    """(resumen mensual, detalle por producto y mes)."""
    cba = pd.read_csv(os.path.join(AQUI, "mapa_cba.csv")).dropna(subset=["gasto_mar2022"])
    cba["odepa"] = cba["odepa"].fillna("")
    precios = precios_por_kilo(semanal)
    ministerio = cba_ministerio()
    factor = ministerio["ministerio"] / cba["gasto_mar2022"].sum()
    # en tiempo real, al valorizar el mes m solo se conoce el valor del
    # Ministerio de m-1 (el IPC de m sale después)
    factor_previo = factor.shift(1)
    filas = []
    for mes, f in factor[factor.index >= DESDE].items():
        for _, r in cba.iterrows():
            claves = [odepa_mensual.clave_producto(x) for x in r["odepa"].split("|") if x.strip()]
            p = precios.loc[mes, [c for c in claves if c in precios.columns]].dropna() \
                if claves and mes in precios.index else pd.Series(dtype=float)
            valor_min = r["gasto_mar2022"] * f
            valor_previo = r["gasto_mar2022"] * factor_previo[mes]
            con_odepa = not p.empty
            filas.append({"mes": mes, "producto": r["producto"], "mapeado": bool(claves),
                          "con_odepa": con_odepa, "precio_odepa": p.mean() if con_odepa else np.nan,
                          "valor_ministerio": valor_min,
                          "valor_odepa": r["cantidad_mensual"] / 1000 * p.mean() if con_odepa
                          else valor_min,
                          "valor_odepa_tiempo_real": r["cantidad_mensual"] / 1000 * p.mean()
                          if con_odepa else valor_previo})
    det = pd.DataFrame(filas)
    det["diferencia"] = det["valor_odepa"] - det["valor_ministerio"]
    g = det.groupby("mes")
    res = pd.DataFrame({
        "cba_odepa": g["valor_odepa"].sum(),
        "cba_ministerio": g["valor_ministerio"].sum(),
        "cba_odepa_tiempo_real": g["valor_odepa_tiempo_real"].sum(),
        "peso_con_odepa": det[det["con_odepa"]].groupby("mes")["valor_ministerio"].sum()
        / g["valor_ministerio"].sum() * 100,
    })
    res = res.join(ministerio[["reconstruida", "publicada_2024", "publicada_2013"]])
    res["diferencia_pct"] = (res["cba_odepa"] / res["cba_ministerio"] - 1) * 100
    res["diferencia_tiempo_real_pct"] = (res["cba_odepa_tiempo_real"] / res["cba_ministerio"]
                                         - 1) * 100
    cub = det[det["con_odepa"]].groupby("mes")
    res["cubiertos_odepa_sobre_ministerio_pct"] = (cub["valor_odepa"].sum()
                                                   / cub["valor_ministerio"].sum() - 1) * 100
    res["var_mensual_odepa"] = res["cba_odepa"].pct_change() * 100
    res["var_mensual_ministerio"] = res["cba_ministerio"].pct_change() * 100
    res["var_mensual_tiempo_real"] = (res["cba_odepa_tiempo_real"]
                                      / res["cba_odepa"].shift(1) - 1) * 100
    return res, det


if __name__ == "__main__":
    semanal = pd.read_csv(os.path.join(DATOS, "odepa_semanal.csv"), parse_dates=["semana"])
    res, det = valorizar(semanal)
    os.makedirs(RESULTADOS, exist_ok=True)
    res.round(2).to_csv(os.path.join(RESULTADOS, "canasta_mensual.csv"), index_label="mes")
    det.round(2).to_csv(os.path.join(RESULTADOS, "canasta_por_producto.csv"), index=False)
    chk = res.dropna(subset=["publicada_2024"])
    err = (chk["reconstruida"] / chk["publicada_2024"] - 1).abs().max() * 100
    print(f"reconstrucción del Ministerio frente a lo publicado en 2026: error máximo {err:.3f}%")
    print(res[["cba_ministerio", "cba_odepa", "diferencia_pct", "peso_con_odepa",
               "cubiertos_odepa_sobre_ministerio_pct"]].round(1).iloc[::6].to_string())

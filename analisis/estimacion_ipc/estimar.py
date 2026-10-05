"""
estimar.py - prueba hacia atrás de la estimación del IPC de alimentos
=====================================================================
Para cada mes m de 2019 a 2026 estima la variación mensual del IPC de
"Alimentos y bebidas no alcohólicas" (división 01) con la información que
existía antes de que el INE la publicara, y la compara con el dato oficial.

Estimación (Laspeyres con las ponderaciones del INE, la misma agregación
que reproduce el índice oficial):

    V(m) = sum_i w_i * I_i(m-1) * r_i(m) / sum_i w_i * I_i(m-1) - 1

- w_i: ponderación del producto i en la canasta vigente (2018 hasta
  diciembre 2023, 2023 desde enero 2024).
- I_i(m-1): índice oficial del producto en el mes anterior, ya publicado.
  En enero de 2019 y enero de 2024, el primer mes de cada base, sale de la
  serie referencial del año base (el INE la publicó junto con ese IPC).
- r_i(m): relativo de precios del mes.
  * Producto cubierto por ODEPA: media geométrica (Jevons) de p_j(m)/p_j(m-1)
    de sus productos ODEPA con precio en ambos meses; en el mes m solo entran
    las semanas que ODEPA publicó antes de la fecha del IPC.
  * Producto no cubierto, o cubierto sin precio ODEPA ese mes: variante
    "mes anterior", su propia variación oficial de m-1; variante "12 meses",
    su variación mensual media (geométrica) de m-12 a m-1.

Comparación: error absoluto medio (EAM) de la variación mensual, con la
estimación redondeada a un decimal como la publica el INE, frente al
pronóstico ingenuo (repetir la variación oficial de m-1), y tasa de acierto
en la dirección (signo: sube, baja o 0,0), por año y total.

Uso: python estimar.py   (después de descargar.py y odepa_mensual.py)
"""
import os

import numpy as np
import pandas as pd

import ine
import odepa_mensual

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
RESULTADOS = os.path.join(AQUI, "resultados")
DESDE, HASTA = pd.Period("2019-01", "M"), None   # HASTA: el último IPC publicado
CAMBIO_BASE = pd.Period("2024-01", "M")


def base_de(m: pd.Period) -> int:
    return 2018 if m < CAMBIO_BASE else 2023


def fechas_publicacion(meses) -> dict:
    """{mes de referencia: fecha de publicación del IPC}. Del calendario del
    INE si está (datos/calendario_ipc.csv); si no, el día 8 del mes siguiente."""
    ruta = os.path.join(DATOS, "calendario_ipc.csv")
    out = {m: (m + 1).to_timestamp() + pd.Timedelta(days=7) for m in meses}
    if os.path.exists(ruta):
        cal = pd.read_csv(ruta)
        for _, r in cal.iterrows():
            out[pd.Period(r["mes_referencia"], "M")] = pd.Timestamp(r["fecha_publicacion"])
    return out


def mapa_odepa(base: int) -> dict:
    """{codigo IPC: [claves ODEPA]} de mapa_productos.csv."""
    mapa = pd.read_csv(os.path.join(AQUI, "mapa_productos.csv"), dtype={"codigo": str})
    out = {}
    for _, r in mapa[(mapa["base"] == base) & mapa["odepa"].notna()].iterrows():
        out[r["codigo"]] = [odepa_mensual.clave_producto(x) for x in r["odepa"].split("|")
                            if x.strip()]
    return out


def jevons(precios: pd.DataFrame, claves: list, m: pd.Period):
    """Media geométrica de p(m)/p(m-1) de las claves con precio en ambos
    meses, y cuántas entraron. precios: pivote mes x clave."""
    if m not in precios.index or (m - 1) not in precios.index:
        return None, 0
    cols = [c for c in claves if c in precios.columns]
    a, b = precios.loc[m, cols], precios.loc[m - 1, cols]
    ok = a.notna() & b.notna() & (a > 0) & (b > 0)
    if not ok.any():
        return None, 0
    return float(np.exp(np.log(a[ok] / b[ok]).mean())), int(ok.sum())


def relativo_propio(serie: pd.Series, m: pd.Period, variante: str):
    """Relativo de reemplazo de un producto con su propia historia oficial:
    'mes_anterior' = I(m-1)/I(m-2); '12_meses' = (I(m-1)/I(m-13))^(1/12), o
    con los meses que haya si la serie de la base es más corta."""
    if variante == "mes_anterior":
        return serie.get(m - 1) / serie.get(m - 2)
    previos = serie[(serie.index <= m - 1) & (serie.index >= m - 13)].dropna()
    k = (previos.index[-1] - previos.index[0]).n
    return (previos.iloc[-1] / previos.iloc[0]) ** (1 / k)


def estimar(odepa_semanal: pd.DataFrame, variante: str = "mes_anterior",
            oraculo: bool = False) -> pd.DataFrame:
    """Una fila por mes con la variación estimada (%), la cobertura efectiva
    (peso con relativo ODEPA ese mes) y el detalle. oraculo=True usa para los
    productos cubiertos su relativo oficial en vez del de ODEPA (aísla el
    error que viene de la parte no cubierta)."""
    oficial = ine.alimentos_oficial().set_index("mes")["variacion"]
    hasta = HASTA or oficial.index.max()
    meses = pd.period_range(DESDE, hasta, freq="M")
    corte = fechas_publicacion(meses)
    mensual = odepa_mensual.precios_mensuales(odepa_semanal, corte)
    precios = mensual.pivot(index="mes", columns="clave", values="precio")
    bases = {b: ine.productos(b) for b in (2018, 2023)}
    indices = {b: p.pivot(index="mes", columns="codigo", values="indice") for b, p in bases.items()}
    pesos = {b: p.groupby("codigo")["ponderacion"].first() for b, p in bases.items()}
    mapas = {b: mapa_odepa(b) for b in (2018, 2023)}
    filas = []
    for m in meses:
        b = base_de(m)
        I, w, mapa = indices[b], pesos[b], mapas[b]
        previo = I.loc[m - 1]
        num = den = peso_odepa = 0.0
        n_odepa = 0
        for cod, wi in w.items():
            r = None
            if cod in mapa:
                if oraculo:
                    r = I.loc[m, cod] / previo[cod] if m in I.index else None
                else:
                    r, n = jevons(precios, mapa[cod], m)
                    n_odepa += n
                if r is not None:
                    peso_odepa += wi
            if r is None:
                r = relativo_propio(I[cod], m, variante)
            num += wi * previo[cod] * r
            den += wi * previo[cod]
        filas.append({"mes": m, "base": b, "estimada": (num / den - 1) * 100,
                      "oficial": oficial.get(m), "ingenuo": oficial.get(m - 1),
                      "cobertura_mes": peso_odepa / w.sum() * 100, "productos_odepa": n_odepa,
                      "publicacion_ine": corte[m]})
    return pd.DataFrame(filas)


def signo(x: pd.Series) -> pd.Series:
    return np.sign(x.round(1))


def metricas(r: pd.DataFrame) -> pd.DataFrame:
    """EAM y acierto en la dirección, por año y total. La estimación va
    redondeada a un decimal, como la publica el INE."""
    r = r.dropna(subset=["oficial", "ingenuo"]).copy()
    r["est1"] = r["estimada"].round(1)
    r["error_est"] = (r["est1"] - r["oficial"]).abs()
    r["error_ing"] = (r["ingenuo"] - r["oficial"]).abs()
    r["dir_est"] = signo(r["est1"]) == signo(r["oficial"])
    r["dir_ing"] = signo(r["ingenuo"]) == signo(r["oficial"])
    r["anio"] = r["mes"].dt.year.astype(str)

    def resumen(g):
        return pd.Series({"meses": len(g),
                          "eam_estimacion": g["error_est"].mean(),
                          "eam_ingenuo": g["error_ing"].mean(),
                          "acierto_dir_estimacion": g["dir_est"].mean() * 100,
                          "acierto_dir_ingenuo": g["dir_ing"].mean() * 100})
    por_anio = r.groupby("anio").apply(resumen)
    total = resumen(r).to_frame("total").T
    return pd.concat([por_anio, total])


if __name__ == "__main__":
    semanal = pd.read_csv(os.path.join(DATOS, "odepa_semanal.csv"), parse_dates=["semana"])
    os.makedirs(RESULTADOS, exist_ok=True)
    for variante in ("mes_anterior", "12_meses"):
        r = estimar(semanal, variante)
        r.assign(mes=r["mes"].astype(str)).to_csv(
            os.path.join(RESULTADOS, f"estimacion_{variante}.csv"), index=False)
        print(f"\n== variante {variante} ==")
        print(metricas(r).round(2).to_string())
    r = estimar(semanal, "mes_anterior", oraculo=True)
    print("\n== oráculo (cubiertos con su relativo oficial) ==")
    print(metricas(r).round(2).to_string())

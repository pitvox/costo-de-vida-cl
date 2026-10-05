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
- r_i(m): relativo de precios del mes.
  * Producto cubierto por ODEPA: media geométrica (Jevons) de p_j(m)/p_j(m-1)
    de sus productos ODEPA con precio en ambos meses (cada producto ODEPA, a
    su vez, media geométrica de sus series por unidad); en el mes m solo
    entran las semanas que ODEPA publicó antes de la fecha del IPC.
  * Producto no cubierto, o cubierto sin precio ODEPA ese mes: variante
    "mes anterior", su propia variación oficial de m-1; variante "12 meses",
    su variación mensual media (geométrica) de m-12 a m-1.

Primer mes de cada base (enero de 2019 y enero de 2024). El INE publicó la
canasta nueva en diciembre del año anterior, pero los índices de sus
productos en el año base (la serie referencial) recién salieron junto con el
IPC de ese enero. Antes de esa publicación se conocían las ponderaciones y no
los I_i(m-1), así que en esos dos meses los pesos van sin reescalar
(I_i(m-1) = 100, el promedio del año base) y los productos sin ODEPA se
proyectan con la variación oficial de Alimentos (mes anterior, o promedio de
12 meses) de la base que terminaba.

Comparación: error absoluto medio (EAM) de la variación mensual, con la
estimación redondeada a un decimal como la publica el INE, frente al
pronóstico ingenuo (repetir la variación oficial de m-1), y tasa de acierto
en la dirección (signo: sube, baja o 0,0), por año y total.

Uso: python estimar.py   (después de descargar.py y odepa_mensual.py)
"""
import math
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


PRIMEROS_MESES = (pd.Period("2019-01", "M"), CAMBIO_BASE)


def base_de(m: pd.Period) -> int:
    return 2018 if m < CAMBIO_BASE else 2023


def fechas_publicacion(meses) -> dict:
    """{mes de referencia: fecha de publicación del IPC}, de calendario_ipc.csv
    (portada de cada boletín del INE, cruzada con sus comunicados y
    calendarios). El IPC sale a las 8:00, así que del día de publicación no
    entra nada."""
    cal = pd.read_csv(os.path.join(AQUI, "calendario_ipc.csv"))
    fechas = {pd.Period(r["mes_referencia"], "M"): pd.Timestamp(r["fecha_publicacion"])
              for _, r in cal.iterrows()}
    faltan = [str(m) for m in meses if m not in fechas]
    if faltan:
        raise SystemExit(f"calendario_ipc.csv no trae la fecha de: {faltan}")
    return {m: fechas[m] for m in meses}


def mapa_odepa(base: int) -> dict:
    """{codigo IPC: [claves ODEPA]} de mapa_productos.csv."""
    mapa = pd.read_csv(os.path.join(AQUI, "mapa_productos.csv"), dtype={"codigo": str})
    out = {}
    for _, r in mapa[(mapa["base"] == base) & mapa["odepa"].notna()].iterrows():
        out[r["codigo"]] = [odepa_mensual.clave_producto(x) for x in r["odepa"].split("|")
                            if x.strip()]
    return out


def jevons(anterior: pd.DataFrame, actual: pd.DataFrame, series: dict, claves: list,
           m: pd.Period):
    """Relativo de un producto del IPC con ODEPA y cuántos productos ODEPA
    entraron. Cada producto ODEPA da la media geométrica de p(m)/p(m-1) de sus
    series (una por unidad) con precio en ambos meses; el producto del IPC, la
    media geométrica de esos productos. anterior y actual: pivotes mes x serie
    con lo que se sabía al estimar m (p(m-1) sale de anterior y p(m) de
    actual); series: {clave: [series]}."""
    if m not in actual.index or (m - 1) not in anterior.index:
        return None, 0
    logs = []
    for clave in claves:
        cols = [c for c in series.get(clave, []) if c in anterior.columns and c in actual.columns]
        a, b = actual.loc[m, cols], anterior.loc[m - 1, cols]
        ok = a.notna() & b.notna() & (a > 0) & (b > 0)
        if ok.any():
            logs.append(np.log(a[ok] / b[ok]).mean())
    if not logs:
        return None, 0
    return float(np.exp(np.mean(logs))), len(logs)


def relativo_propio(serie: pd.Series, m: pd.Period, variante: str):
    """Relativo de reemplazo de un producto con su propia historia oficial:
    'mes_anterior' = I(m-1)/I(m-2); '12_meses' = (I(m-1)/I(m-13))^(1/12), o
    con los meses que haya si la serie de la base es más corta."""
    if variante == "mes_anterior":
        return serie.get(m - 1) / serie.get(m - 2)
    previos = serie[(serie.index <= m - 1) & (serie.index >= m - 13)].dropna()
    k = (previos.index[-1] - previos.index[0]).n
    return (previos.iloc[-1] / previos.iloc[0]) ** (1 / k)


def relativo_agregado(variacion: pd.Series, m: pd.Period, variante: str) -> float:
    """El mismo reemplazo, con la variación oficial publicada de Alimentos (%)
    en vez de la del producto: para el primer mes de cada base."""
    if variante == "mes_anterior":
        return 1 + variacion[m - 1] / 100
    previos = variacion[(variacion.index <= m - 1) & (variacion.index >= m - 12)]
    return float(np.prod(1 + previos / 100) ** (1 / len(previos)))


def comprobar_agregacion() -> pd.DataFrame:
    """La agregación de Laspeyres con las ponderaciones del INE, aplicada a los
    índices oficiales de producto, contra la variación publicada de Alimentos:
    si calzan, el error de la estimación viene de los relativos y no de la
    fórmula. Una fila por mes con las dos variaciones (1 decimal)."""
    oficial = ine.alimentos_oficial().set_index("mes")["variacion"]
    filas = []
    for b in (2018, 2023):
        p = ine.productos(b)
        I = p.pivot(index="mes", columns="codigo", values="indice")
        w = p.groupby("codigo")["ponderacion"].first()
        agregado = (I * w).sum(axis=1) / w.sum()
        for m in agregado.index[1:]:
            if base_de(m) == b and m >= DESDE and m in oficial.index:
                filas.append({"mes": m, "base": b, "oficial": oficial[m],
                              "agregada": round((agregado[m] / agregado[m - 1] - 1) * 100, 1)})
    return pd.DataFrame(filas)


def estimar(odepa_semanal: pd.DataFrame, variante: str = "mes_anterior",
            oraculo: bool = False, atraso_odepa: int = 4, semanas: int = None,
            detalle: list = None) -> pd.DataFrame:
    """Una fila por mes con la variación estimada (%), la cobertura efectiva
    (peso con relativo ODEPA ese mes) y el detalle. oraculo=True usa para los
    productos cubiertos su relativo oficial en vez del de ODEPA (aísla el
    error que viene de la parte no cubierta). atraso_odepa: días entre el
    lunes de una semana y su publicación en ODEPA (4 = el viernes).
    semanas: si viene, solo entran las primeras 'semanas' semanas de m y de
    m-1 (la estimación que se publicaría a mitad de mes). detalle: si viene una lista, se le agrega una fila por mes y
    producto con el aporte de su error a la variación estimada."""
    oficial = ine.alimentos_oficial().set_index("mes")["variacion"]
    hasta = HASTA or oficial.index.max()
    meses = pd.period_range(DESDE, hasta, freq="M")
    corte = fechas_publicacion(meses)
    # lo que se sabía al estimar m: de m, las semanas publicadas antes del
    # IPC de m; de m-1, todo lo publicado hasta esa misma fecha. A mitad de
    # mes se comparan las mismas k primeras semanas de m y de m-1.
    semanal = odepa_semanal
    if semanas:
        semanal = semanal[(semanal["semana"].dt.day - 1) // 7 + 1 <= semanas]

    def pivote(cortes):
        return odepa_mensual.precios_mensuales(semanal, cortes, atraso_odepa).pivot(
            index="mes", columns="serie", values="precio")
    actual = pivote(corte)
    anterior = pivote({m - 1: corte[m] for m in meses})
    series = odepa_semanal.groupby("clave")["serie"].unique().to_dict()
    bases = {b: ine.productos(b) for b in (2018, 2023)}
    indices = {b: p.pivot(index="mes", columns="codigo", values="indice") for b, p in bases.items()}
    pesos = {b: p.groupby("codigo")["ponderacion"].first() for b, p in bases.items()}
    mapas = {b: mapa_odepa(b) for b in (2018, 2023)}
    filas = []
    for m in meses:
        b = base_de(m)
        I, w, mapa = indices[b], pesos[b], mapas[b]
        primero = m in PRIMEROS_MESES
        # primer mes de la base: sin I_i(m-1) publicado todavía (ver arriba)
        previo = pd.Series(100.0, index=w.index) if primero and not oraculo else I.loc[m - 1]
        num = den = peso_odepa = 0.0
        n_odepa = 0
        for cod, wi in w.items():
            r = None
            if cod in mapa:
                if oraculo:
                    r = I.loc[m, cod] / previo[cod] if m in I.index else None
                else:
                    r, n = jevons(anterior, actual, series, mapa[cod], m)
                    n_odepa += n
                if r is not None:
                    peso_odepa += wi
            if r is None:
                r = (relativo_agregado(oficial, m, variante) if primero
                     else relativo_propio(I[cod], m, variante))
            num += wi * previo[cod] * r
            den += wi * previo[cod]
            if detalle is not None and m in I.index:
                detalle.append({"mes": m, "codigo": cod, "con_odepa": cod in mapa,
                                "aporte": wi * previo[cod] * (r - I.loc[m, cod] / I.loc[m - 1, cod])})
        if detalle is not None:
            for fila in detalle[-len(w):]:
                fila["aporte"] = fila["aporte"] / den * 100
        filas.append({"mes": m, "base": b, "estimada": (num / den - 1) * 100,
                      "oficial": oficial.get(m), "ingenuo": oficial.get(m - 1),
                      "promedio_12m": oficial.loc[m - 12:m - 1].mean(),
                      "cobertura_mes": peso_odepa / w.sum() * 100, "productos_odepa": n_odepa,
                      "publicacion_ine": corte[m]})
    return pd.DataFrame(filas)


def redondear(x):
    """A un decimal, con la mitad hacia arriba (lejos de cero), como publica
    el INE. El 1e-9 evita que el ruido de coma flotante decida un empate:
    el promedio de 12 variaciones de un decimal cae a veces justo en x,x5."""
    x = np.asarray(x, dtype=float)
    return np.sign(x) * np.floor(np.abs(x) * 10 + 0.5 + 1e-9) / 10


def signo(x: pd.Series) -> pd.Series:
    return np.sign(redondear(x))


def errores(r: pd.DataFrame) -> pd.DataFrame:
    """Meses con dato oficial, con la estimación redondeada a un decimal (como
    la publica el INE), los errores absolutos y los aciertos de dirección
    (signo de la variación: sube, baja o 0,0)."""
    r = r.dropna(subset=["oficial", "ingenuo"]).copy()
    r["est1"] = redondear(r["estimada"])
    r["error_est"] = (r["est1"] - r["oficial"]).abs()
    r["error_ing"] = (r["ingenuo"] - r["oficial"]).abs()
    r["dir_est"] = signo(r["est1"]) == signo(r["oficial"])
    r["dir_ing"] = signo(r["ingenuo"]) == signo(r["oficial"])
    # otras dos referencias simples: el promedio de los últimos 12 meses y
    # "siempre sube"
    r["error_p12"] = (redondear(r["promedio_12m"]) - r["oficial"]).abs()
    r["dir_p12"] = signo(r["promedio_12m"]) == signo(r["oficial"])
    r["dir_sube"] = signo(r["oficial"]) > 0
    r["anio"] = r["mes"].dt.year.astype(str)
    return r


def _beta_cf(a: float, b: float, x: float) -> float:
    """Fracción continua de la beta incompleta (método de Lentz)."""
    tiny, c, d = 1e-300, 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + num / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return h


def p_t_dos_colas(t: float, gl: int) -> float:
    """Valor p de dos colas de la t de Student con gl grados de libertad
    (beta incompleta regularizada I_x(gl/2, 1/2), x = gl / (gl + t^2))."""
    x, a, b = gl / (gl + t * t), gl / 2, 0.5
    if x <= 0:
        return 0.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1 - x)) if x < 1 else 0.0
    if x < (a + 1) / (a + b + 2):
        return bt * _beta_cf(a, b, x) / a
    return 1 - bt * _beta_cf(b, a, 1 - x) / b


def diebold_mariano(a: pd.Series, b: pd.Series) -> float:
    """Valor p (dos colas) de la prueba de Diebold y Mariano para horizonte 1
    con la corrección de Harvey, Leybourne y Newbold: ¿los errores absolutos
    a y b son distintos en promedio? Con horizonte 1 el estadístico corregido
    es la t de una muestra de las diferencias (varianza con n-1), y se compara
    con una t de n-1 grados de libertad."""
    d = (a - b).to_numpy()
    n = len(d)
    return p_t_dos_colas(d.mean() / math.sqrt(d.var(ddof=1) / n), n - 1)


def resumen(g: pd.DataFrame) -> pd.Series:
    return pd.Series({"meses": len(g),
                      "eam_estimacion": g["error_est"].mean(),
                      "eam_ingenuo": g["error_ing"].mean(),
                      "acierto_dir_estimacion": g["dir_est"].mean() * 100,
                      "acierto_dir_ingenuo": g["dir_ing"].mean() * 100,
                      "meses_mejor_que_ingenuo": (g["error_est"] < g["error_ing"]).mean() * 100,
                      "eam_promedio_12m": g["error_p12"].mean(),
                      "acierto_dir_promedio_12m": g["dir_p12"].mean() * 100,
                      "acierto_dir_siempre_sube": g["dir_sube"].mean() * 100})


def metricas(r: pd.DataFrame) -> pd.DataFrame:
    """EAM y acierto en la dirección, por año y total."""
    e = errores(r)
    por_anio = e.groupby("anio")[e.columns.tolist()].apply(resumen)
    total = resumen(e).to_frame("total").T
    total["p_dm_ingenuo"] = diebold_mariano(e["error_est"], e["error_ing"])
    total["p_dm_promedio_12m"] = diebold_mariano(e["error_est"], e["error_p12"])
    return pd.concat([por_anio, total])


def criterio(r: pd.DataFrame) -> str:
    """La pregunta del encargo: ¿le gana al ingenuo en EAM y acierta la
    dirección en al menos 2 de cada 3 meses? (cuenta meses, no porcentajes)"""
    e = errores(r)
    gana = e["error_est"].mean() < e["error_ing"].mean()
    aciertos, n = int(e["dir_est"].sum()), len(e)
    dos_tercios = 3 * aciertos >= 2 * n
    return (f"le gana al ingenuo en EAM: {'sí' if gana else 'no'} "
            f"({e['error_est'].mean():.2f} contra {e['error_ing'].mean():.2f}); "
            f"dirección en al menos 2 de cada 3 meses: {'sí' if dos_tercios else 'no'} "
            f"({aciertos} de {n})")


if __name__ == "__main__":
    semanal = pd.read_csv(os.path.join(DATOS, "odepa_semanal.csv"), parse_dates=["semana"])
    os.makedirs(RESULTADOS, exist_ok=True)
    agr = comprobar_agregacion()
    calzan = (agr["agregada"] == agr["oficial"]).sum()
    print(f"agregación con las ponderaciones del INE: calza con la variación publicada en "
          f"{calzan} de {len(agr)} meses; diferencia máxima "
          f"{(agr['agregada'] - agr['oficial']).abs().max():.1f} puntos")
    corridas = {
        "principal (mes anterior)": estimar(semanal, "mes_anterior"),
        "no cubiertos con promedio de 12 meses": estimar(semanal, "12_meses"),
        "ODEPA publicada una semana más tarde": estimar(semanal, "mes_anterior",
                                                         atraso_odepa=11),
        "oráculo: cubiertos con su variación oficial": estimar(semanal, "mes_anterior",
                                                               oraculo=True),
    }
    for k in (1, 2, 3):
        corridas[f"con las primeras {k} semanas del mes"] = estimar(semanal, "mes_anterior",
                                                                     semanas=k)
    principal = corridas["principal (mes anterior)"]
    corridas["principal sin enero 2019 ni enero 2024"] = principal[
        ~principal["mes"].isin(PRIMEROS_MESES)]
    for variante, r in (("mes_anterior", principal),
                        ("12_meses", corridas["no cubiertos con promedio de 12 meses"])):
        r.assign(mes=r["mes"].astype(str)).to_csv(
            os.path.join(RESULTADOS, f"estimacion_{variante}.csv"), index=False)
        m = metricas(r)
        m.round(3).to_csv(os.path.join(RESULTADOS, f"metricas_{variante}.csv"),
                          index_label="periodo")
        print(f"\n== {variante} ==\n{m.round(2).to_string()}\n{criterio(r)}")
    det = []
    estimar(semanal, "mes_anterior", detalle=det)
    det = pd.DataFrame(det)
    glosas = pd.read_csv(os.path.join(AQUI, "mapa_productos.csv"), dtype={"codigo": str})
    det["base"] = det["mes"].map(base_de)
    det = det.merge(glosas[["base", "codigo", "producto_ipc"]], on=["base", "codigo"])
    aportes = (det.assign(aporte_abs=det["aporte"].abs())
               .groupby(["producto_ipc", "con_odepa"])["aporte_abs"].sum() / det["mes"].nunique())
    aportes.sort_values(ascending=False).round(4).rename("error_medio_aportado").to_csv(
        os.path.join(RESULTADOS, "aporte_error_productos.csv"))
    print("\n== productos que más error aportan (puntos, promedio mensual) ==")
    print(aportes.sort_values(ascending=False).head(12).round(3).to_string())
    filas = []
    for nombre, r in corridas.items():
        t = metricas(r).loc["total"]
        filas.append({"corrida": nombre, **t.to_dict()})
    sens = pd.DataFrame(filas)
    sens.round(3).to_csv(os.path.join(RESULTADOS, "sensibilidad.csv"), index=False)
    print("\n== sensibilidad (total) ==")
    print(sens.round(2).to_string(index=False))

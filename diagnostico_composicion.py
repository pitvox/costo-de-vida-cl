"""
diagnostico_composicion.py - ¿Parte de la historia de los índices es cambio de muestra?
========================================================================================
Diagnóstico one-off, solo lectura. NO toca indices.py, build_site.py, el sitio
ni el workflow de Pages, y nada de esto se publica: importa las funciones de
indices.py sin cambiarlas (mismo match, misma conversión de unidad, mismas
canastas, mismo min_count, mismo deflactor IPC).

Contexto: precio_semanal promedia todas las filas RM de un producto sin
ponderar por tipo de punto de monitoreo (feria libre, supermercado,
carnicería...), y ODEPA amplió productos y puntos en marzo de 2013. Si cambia
la mezcla de tipos, el promedio se mueve aunque no cambie ningún precio.

Por cada ingrediente de las 4 canastas, semanal W-MON, RM, 2008 a 2026:
  1. Filas, puntos distintos (sector | tipo) y participación de cada tipo de
     punto en las filas (el peso implícito de cada tipo en precio_semanal).
     Por año (año de la fecha de la fila), marca los años en que algún tipo
     cambia más de 15 pp respecto del año anterior (si ese año no tiene
     filas, el último antes de él: anio_base). Las filas sin tipo de punto no
     entran a esa cuenta: se informan aparte, y un año con filas pero ninguna
     con tipo dentro del período de un índice queda sin evaluar.
  2. Serie agrupada (precio_semanal, la actual) y serie estratificada:
     promedio de las filas de cada fecha dentro de cada tipo de punto, de
     esas fechas en la semana W-MON (los dos pasos del pipeline, dentro del
     tipo) y luego promedio simple entre los tipos comunes, los que tienen
     filas antes y después del corte (1 de marzo de 2013). Un ingrediente
     sin filas antes del corte (empieza después) usa como "antes" su primer
     año de datos. Los tipos que no son comunes (un tipo que aparece después,
     como el supermercado en línea) quedan fuera de la estratificada.
     Semanas donde falta un tipo común: se usa el último precio de ese tipo
     de hasta 4 semanas antes (el mismo ffill(limit=4) del pipeline); si
     falta hace más de 4 semanas, el promedio va con los tipos comunes que
     tienen precio y la semana queda marcada (tipos_con_precio menor que
     tipos_comunes). Una semana sin filas de ningún tipo común no tiene
     estratificada, y el ffill de la canasta la completa como a cualquier
     semana sin dato.
  3. Con la estratificada, cada índice igual que el pipeline (_serie_canasta:
     cantidades, resample W-MON, ffill(limit=4), min_count; deflactado como
     calcular) y, lado a lado con lo que calcula el pipeline en esta misma
     corrida: percentil vigente, semana del máximo real y z-score. La
     agrupada se rearma con el mismo código y se exige que dé exactamente lo
     del pipeline: si no, la corrida se detiene. Si la estratificada de un
     índice no cubre las mismas semanas que el pipeline, ese índice no entra
     a la regla (bases distintas). Si falta un año de ODEPA, la corrida se
     detiene.

Regla preregistrada: QUIEBRE MATERIAL si algún índice mueve su percentil
vigente 5 puntos o más, si cambia la semana del máximo real o si algún tipo
de punto cambia más de 15 pp de participación entre años. Si no, ROBUSTO. Si
nada marca quiebre pero algo no se pudo evaluar (estratificada que no se
arma o con otras semanas que el pipeline, años sin tipo de punto), NO
VERIFICABLE. Cualquiera sea el resultado, solo se reporta: cero cambios de
metodología. El detalle del log trae además una descomposición (contexto, no
entra a la regla): la agrupada con solo los tipos comunes, la brecha por año
y, si cambia la semana del máximo, lo que trae cada tipo esas semanas.

Salida (en la carpeta actual):
  diagnostico_composicion_semanal.csv  ingrediente y semana: filas, puntos,
                                       mezcla, agrupada, estratificada
  diagnostico_composicion_anual.csv    ingrediente, año y tipo: filas,
                                       participación y cambio en pp
  diagnostico_composicion_indices.csv  índice y semana: nominal y real,
                                       agrupada y estratificada
  y en la consola el detalle y, al final, un resumen de máximo 15 líneas con
  el veredicto (el workflow no guarda copia del log: ver el .yml).

Correr (mismo entorno que indices.py; BCCH_USER y BCCH_PASS para el IPC):
  python diagnostico_composicion.py
  python diagnostico_composicion.py --prueba   (sintética, sin red)
"""

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import requests

from indices import (BASKETS, RESOURCES, YEARS, calcular, cargar_ipc, cargar_odepa,
                     de_su_unidad, factor_precio, precio_semanal, resumen, unidad_modal)

CORTE = pd.Timestamp("2013-03-01")    # ODEPA amplía productos y puntos
UMBRAL_PP = 15.0                      # participación: más de 15 pp entre años
UMBRAL_PERCENTIL = 5                  # percentil vigente: 5 puntos o más
FFILL = 4                             # semanas, el ffill(limit=4) del pipeline
SIN_TIPO = "(sin tipo)"
SITIO = "https://carestia.cl/indices.json"
PREFIJO = "diagnostico_composicion"
MAX_RESUMEN = 15


# ---------------- filas de cada ingrediente ----------------
def ingredientes() -> dict:
    """{match: (etiqueta, unidad)} de las 4 canastas, en orden. Un mismo texto
    de match (tomate, palta, marraqueta...) es un solo ingrediente, como en
    series_productos."""
    out = {}
    for meta in BASKETS.values():
        for (lab, match, _qty, uni) in meta["items"]:
            out.setdefault(match, (lab, uni))
    return out


def filas_ingrediente(df: pd.DataFrame, match: str, uni: str):
    """Las filas que promedia precio_semanal (mismo match, de_su_unidad), con
    el precio llevado a la unidad del ítem con el factor de _serie_canasta, y
    su punto y tipo de punto. Devuelve (filas, factor)."""
    f, _ = factor_precio(unidad_modal(df, match), uni)
    sub = de_su_unidad(df[df["ProductoBase"].str.contains(match, case=False, na=False)])
    if sub.empty:
        return pd.DataFrame(columns=["fecha", "precio", "punto", "tipo", "producto"]), f
    if "Punto" in sub.columns:
        punto = sub["Punto"].fillna("").astype(str).str.strip()
    else:
        punto = pd.Series("", index=sub.index)
    con_tipo = punto.str.contains(" | ", regex=False)
    tipo = punto.str.rpartition(" | ")[2].str.strip().where(con_tipo, "")
    out = pd.DataFrame({
        "fecha": sub["fecha"].to_numpy(),
        "precio": sub["Precio promedio"].to_numpy(dtype=float) * f,
        "punto": punto.to_numpy(),
        "tipo": tipo.replace("", SIN_TIPO).to_numpy(),
        "producto": sub["ProductoBase"].astype(str).to_numpy(),
    })
    return out.sort_values("fecha", kind="stable").reset_index(drop=True), f


def semana_de(fechas: pd.Series) -> pd.Series:
    """Etiqueta de la semana W-MON de cada fecha (la de resample("W-MON"):
    cierra y se rotula el lunes, así que un lunes es su propia semana)."""
    f = pd.to_datetime(fechas).dt.normalize()
    return f + pd.to_timedelta((-f.dt.day_of_week) % 7, unit="D")


# ---------------- 2. agrupada y estratificada ----------------
def por_tipo(filas: pd.DataFrame) -> pd.DataFrame:
    """Precio semanal W-MON de cada tipo de punto: promedio de las filas de
    cada fecha y tipo, y de esas fechas en la semana."""
    t = filas.groupby(["fecha", "tipo"])["precio"].mean().unstack("tipo")
    return t.resample("W-MON").mean()


def tipos_comunes(filas: pd.DataFrame):
    """Tipos con filas antes y después del corte, sin las filas sin tipo.
    Sin filas antes del corte, el "antes" es el primer año de datos del
    ingrediente. Devuelve (comunes, corte usado, solo antes, solo después)."""
    corte = CORTE
    if len(filas) and not (filas["fecha"] < CORTE).any():
        corte = filas["fecha"].min() + pd.Timedelta(weeks=52)
    antes = set(filas.loc[filas["fecha"] < corte, "tipo"]) - {SIN_TIPO}
    despues = set(filas.loc[filas["fecha"] >= corte, "tipo"]) - {SIN_TIPO}
    return sorted(antes & despues), corte, sorted(antes - despues), sorted(despues - antes)


def estratificada(semanal: pd.DataFrame, comunes: list):
    """Promedio simple entre los tipos comunes de su precio semanal. Un tipo
    sin precio en la semana usa el suyo de hasta FFILL semanas antes; si no,
    el promedio va con los que hay. Sin precio de ningún tipo común esa
    semana: sin dato. Devuelve (serie, tipos con precio por semana)."""
    if not comunes:
        vacia = pd.Series(np.nan, index=semanal.index, dtype=float)
        return vacia, vacia
    p = semanal.reindex(columns=comunes)
    hay = p.notna().any(axis=1)
    lleno = p.ffill(limit=FFILL)
    return lleno.mean(axis=1).where(hay), lleno.notna().sum(axis=1).where(hay)


# ---------------- 1. filas, puntos y mezcla ----------------
def tabla_semanal(lab: str, filas: pd.DataFrame, agr: pd.Series, est: pd.Series,
                  n_est: pd.Series, n_comunes: int) -> pd.DataFrame:
    """Una fila por semana con filas de ODEPA: filas, puntos distintos
    (sector | tipo), mezcla (participación de cada tipo en las filas), las
    dos series en pesos nominales por la unidad del ítem (sin cantidad ni
    ffill), y cuántos tipos comunes tienen precio."""
    s = filas.assign(semana=semana_de(filas["fecha"]))
    n = s.groupby("semana").size()
    idx = n.index
    if set(agr.dropna().index) != set(idx):
        raise RuntimeError(f"{lab}: las semanas de la agrupada no son las de sus filas")
    puntos = (s[s["punto"] != ""].groupby("semana")["punto"].nunique()
              .reindex(idx, fill_value=0))
    cuenta = s.groupby(["semana", "tipo"]).size().unstack(fill_value=0)
    part = cuenta.div(cuenta.sum(axis=1), axis=0)
    mezcla = [";".join(f"{t}={v:.3f}" for t, v in fila.items() if v > 0)
              for _, fila in part.reindex(idx).iterrows()]
    return pd.DataFrame({
        "ingrediente": lab, "semana": idx.strftime("%Y-%m-%d"),
        "filas": n.to_numpy(), "puntos": puntos.to_numpy(), "mezcla": mezcla,
        "agrupada": agr.reindex(idx).round(2).to_numpy(),
        "estratificada": est.reindex(idx).round(2).to_numpy(),
        "tipos_con_precio": n_est.reindex(idx).astype("Int64").to_numpy(),
        "tipos_comunes": n_comunes,
    })


def participacion_anual(lab: str, filas: pd.DataFrame) -> pd.DataFrame:
    """Participación de cada tipo de punto en las filas con tipo, por año de
    la fecha, y su cambio en pp respecto del año anterior con filas con tipo
    (anio_base: el anterior, o el último antes de él si ese año no tiene
    filas, como la mandarina en 2012). 'marca': cambio de más de 15 pp. Las
    filas sin tipo van aparte (filas_sin_tipo) y no entran a la cuenta; un
    año con filas pero ninguna con tipo no se evalúa (ver anios_sin_tipo)."""
    anio = filas["fecha"].dt.year
    con = filas[filas["tipo"] != SIN_TIPO]
    if con.empty:
        return pd.DataFrame()
    cuenta = con.groupby([con["fecha"].dt.year, "tipo"]).size().unstack(fill_value=0)
    part = cuenta.div(cuenta.sum(axis=1), axis=0) * 100
    cambio = part.diff()                               # contra el año con tipo anterior
    base = pd.Series(part.index, index=part.index).shift(1)
    puntos = filas[filas["punto"] != ""].groupby(anio)["punto"].nunique()
    sin_tipo = (filas["tipo"] == SIN_TIPO).groupby(anio).sum()
    productos = filas.groupby(anio)["producto"].agg(lambda p: "; ".join(sorted(set(p))))
    filas_anio = filas.groupby(anio).size()
    reg = []
    for a in part.index:
        for t in part.columns:
            c = cambio.loc[a, t]
            reg.append({"ingrediente": lab, "anio": int(a), "tipo": t,
                        "anio_base": None if pd.isna(base.loc[a]) else int(base.loc[a]),
                        "filas": int(cuenta.loc[a, t]),
                        "participacion": round(float(part.loc[a, t]), 2),
                        "cambio_pp": None if pd.isna(c) else round(float(c), 2),
                        # redondeado: el error de punto flotante no decide el borde
                        "marca": bool(pd.notna(c) and round(abs(c), 6) > UMBRAL_PP),
                        "filas_anio": int(filas_anio.get(a, 0)),
                        "filas_sin_tipo": int(sin_tipo.get(a, 0)),
                        "puntos_anio": int(puntos.get(a, 0)),
                        "productos": productos.get(a, "")})
    return pd.DataFrame(reg)


def anios_sin_tipo(filas: pd.DataFrame) -> list:
    """Años con filas del ingrediente pero ninguna con tipo de punto: su
    participación no se puede evaluar."""
    anio = filas["fecha"].dt.year
    return sorted(set(anio) - set(anio[filas["tipo"] != SIN_TIPO]))


MIN_SEMANAS_ANIO = 20      # semanas con fecha en un año para darlo por bajado


def anios_faltantes(df: pd.DataFrame, anios=None) -> list:
    """Años de ODEPA que no se bajaron: cargar_odepa salta en silencio el año
    que falla, y el diagnóstico sobre datos incompletos no vale. Una fila no
    basta para darlo por bajado: el CSV de un año trae filas con fecha en el
    anterior (el de 2013, la semana del 31 de diciembre de 2012), así que se
    piden MIN_SEMANAS_ANIO semanas con fecha en ese año, salvo el último, que
    al empezar el año trae pocas."""
    anios = [y for y in YEARS if y in RESOURCES] if anios is None else list(anios)
    f = pd.to_datetime(df["fecha"])
    semanas = semana_de(f).groupby(f.dt.year).nunique()
    return [y for y in anios
            if semanas.get(y, 0) < (1 if y == max(anios) else MIN_SEMANAS_ANIO)]


# ---------------- 3. los índices ----------------
def canasta(series: dict, items: list) -> pd.Series:
    """_serie_canasta con las series dadas ({match: precio por la unidad del
    ítem}): por la cantidad, resample W-MON, ffill(limit=4) y suma con
    min_count = todos los ítems."""
    cols = {lab: series[match] * qty for (lab, match, qty, _uni) in items}
    return (pd.DataFrame(cols).resample("W-MON").mean().ffill(limit=FFILL)
            .sum(axis=1, min_count=len(items)))


def deflactar(nominal: pd.Series, ipc: pd.Series) -> pd.Series:
    """La deflactación de calcular: IPC del último mes a la fecha de cada
    semana (merge_asof hacia atrás), en pesos del IPC de la última semana."""
    izq = (nominal.dropna().rename("nominal").rename_axis("fecha").reset_index()
           .sort_values("fecha"))
    der = ipc.rename("ipc").rename_axis("fecha").reset_index().sort_values("fecha")
    m = pd.merge_asof(izq, der, on="fecha", direction="backward").set_index("fecha")
    return m["nominal"] * (m["ipc"].iloc[-1] / m["ipc"])


def metricas(real: pd.Series):
    """Percentil vigente y z-score como resumen() de indices.py, y la semana
    del máximo real. None si la serie no tiene datos."""
    r = real.dropna()
    if r.empty:
        return None
    u = r.iloc[-1]
    return {"semana": r.index[-1], "percentil": round(100.0 * (r <= u).mean()),
            "z": round(float((u - r.mean()) / r.std()), 2), "maximo": r.idxmax(),
            "n": int(len(r)), "inicio": r.index[0]}


def _igual(a: pd.Series, b: pd.Series) -> bool:
    a, b = a.dropna(), b.dropna()
    return a.index.equals(b.index) and np.allclose(a.to_numpy(float), b.to_numpy(float),
                                                   rtol=1e-9, atol=1e-6)


def brecha(agr: pd.Series, est: pd.Series, corte: pd.Timestamp):
    """Diferencia media (%) de la estratificada sobre la agrupada, real,
    antes y después del corte (None si no hay semanas de ese lado)."""
    d = ((est / agr) - 1).dropna() * 100
    antes, despues = d[d.index < corte], d[d.index >= corte]
    return (None if antes.empty else float(antes.mean()),
            None if despues.empty else float(despues.mean()))


# ---------------- descomposición (contexto, no entra a la regla) ----------------
def solo_comunes(filas: pd.DataFrame, comunes: list, indice: pd.Index) -> pd.Series:
    """La agrupada con solo las filas de los tipos comunes, ponderada por
    filas como precio_semanal: frente a la agrupada aísla el efecto de los
    tipos que no son comunes (los que entran después, como el supermercado en
    línea); frente a la estratificada, el de reponderar los tipos comunes."""
    sub = filas[filas["tipo"].isin(comunes)]
    if sub.empty:
        return pd.Series(np.nan, index=indice, dtype=float)
    return sub.groupby("fecha")["precio"].mean().resample("W-MON").mean().reindex(indice)


def imprimir_participacion(anual: pd.DataFrame) -> None:
    """Participación de cada tipo por año (aa:% de las filas con tipo) y
    puntos distintos por año."""
    if anual.empty:
        return
    for t, g in anual.groupby("tipo"):
        print(f"    {t}: " + " ".join(f"{int(r.anio) % 100:02d}:{r.participacion:.0f}"
                                     for r in g.itertuples()))
    pts = anual.drop_duplicates("anio")
    print("    puntos distintos: " + " ".join(f"{int(r.anio) % 100:02d}:{r.puntos_anio}"
                                           for r in pts.itertuples()))


def _por_anio(x: pd.Series, base: pd.Series) -> str:
    d = ((x / base) - 1).dropna() * 100
    return " ".join(f"{a % 100:02d}:{v:+.1f}" for a, v in d.groupby(d.index.year).mean().items())


def imprimir_semana(semana: pd.Timestamp, items: list, ing: dict) -> None:
    """Lo que trae cada ingrediente en una semana: agrupada, estratificada y
    el precio de cada tipo de punto con sus filas y la mediana de ese tipo en
    las 4 semanas antes y después (para ver si un tipo saltó solo esa
    semana). Pesos nominales por la unidad del ítem."""
    print(f"    en {semana:%Y-%m-%d}:")
    for (lab, m, _q, _u) in items:
        x = ing[m]
        tipos, cuenta = x["tipos"], x["cuenta"]
        partes = []
        for t in tipos.columns:
            p = tipos[t].get(semana, np.nan)
            if pd.isna(p):
                continue
            vecinas = tipos[t].loc[semana - pd.Timedelta(weeks=4):semana + pd.Timedelta(weeks=4)]
            med = vecinas.drop(semana, errors="ignore").median()
            n = int(cuenta[t].get(semana, 0)) if t in cuenta.columns else 0
            partes.append(f"{t} {p:,.0f} ({n} filas, mediana vecina {med:,.0f})")
        print(f"      {lab}: agrupada {x['agr'].get(semana, np.nan):,.0f}, estratificada "
              f"{x['est'].get(semana, np.nan):,.0f} | " + " | ".join(partes))


def imprimir_descomposicion(items, com_ing, ipc, real_agr, real_est, agr, est,
                            ing: dict = None) -> None:
    """Tres versiones del índice: agrupada (todas las filas, la del
    pipeline), solo tipos comunes por filas, y estratificada; la brecha media
    por año de las dos últimas sobre la agrupada, qué tan lejos queda cada
    máximo en la otra serie y, si cambia la semana del máximo, lo que trae
    cada ingrediente en las dos semanas."""
    nom_com = canasta({m: com_ing[m] for (_l, m, _q, _u) in items}, items)
    real_com = deflactar(nom_com, ipc) if nom_com.notna().any() else nom_com
    com = metricas(real_com)
    if com is not None:
        print(f"    solo tipos comunes, por filas: percentil {com['percentil']}, máximo "
              f"{com['maximo']:%Y-%m-%d}, z {com['z']} ({com['n']} semanas)")
        print(f"    comunes por filas sobre agrupada, por año (%): {_por_anio(real_com, real_agr)}")
    if est is None:
        return
    print(f"    estratificada sobre agrupada, por año (%): {_por_anio(real_est, real_agr)}")
    ma, me = agr["maximo"], est["maximo"]
    print(f"    máximos: en {ma:%Y-%m-%d} (el de la agrupada) la estratificada queda "
          f"{(real_est.get(ma, np.nan) / real_est.max() - 1) * 100:+.1f}% de su máximo; en "
          f"{me:%Y-%m-%d} (el de la estratificada) la agrupada queda "
          f"{(real_agr.get(me, np.nan) / real_agr.max() - 1) * 100:+.1f}% del suyo")
    if ing is not None and ma != me:
        for semana in (ma, me):
            imprimir_semana(semana, items, ing)


# ---------------- veredicto ----------------
def veredicto(indices_res: dict, saltos: list, sin_evaluar: list = ()) -> dict:
    """La regla preregistrada sobre los resultados por índice
    ({codigo: {"agr": metricas, "est": metricas o None, "comparable": bool}})
    y los saltos de participación de más de 15 pp. Un índice cuya
    estratificada no se arma o no cubre las mismas semanas que el pipeline
    no entra a (a) ni a (b): queda no verificable, igual que un año con filas
    sin tipo de punto dentro del período de un índice ('sin_evaluar')."""
    calc = {k: v for k, v in indices_res.items()
            if v["est"] is not None and v.get("comparable", True)}
    deltas = {k: v["est"]["percentil"] - v["agr"]["percentil"] for k, v in calc.items()}
    a = [k for k, d in deltas.items() if abs(d) >= UMBRAL_PERCENTIL]
    b = [k for k, v in calc.items() if v["est"]["maximo"] != v["agr"]["maximo"]]
    c = bool(saltos)
    falta = sorted(set(indices_res) - set(calc))
    if a or b or c:
        v = "QUIEBRE MATERIAL"
    elif falta or sin_evaluar:
        v = "NO VERIFICABLE"
    else:
        v = "ROBUSTO"
    return {"veredicto": v, "percentil": a, "maximo": b, "participacion": c,
            "deltas": deltas, "no_verificable": falta, "sin_evaluar": list(sin_evaluar)}


# ---------------- el diagnóstico ----------------
def diagnostico(df: pd.DataFrame, ipc: pd.Series, carpeta: str = ".",
                publicado: dict = None) -> dict:
    """Corre los tres pasos sobre las filas RM de ODEPA ya cargadas (las de
    cargar_odepa) y el IPC de cargar_ipc, escribe los CSV en 'carpeta' e
    imprime el detalle y, al final, el resumen. Devuelve los resultados."""
    print("\n" + "=" * 72)
    print("DETALLE POR INGREDIENTE (tipos comunes, cobertura, productos)")
    semanal, anual, agr_ing, est_ing, com_ing, ing, info = [], [], {}, {}, {}, {}, {}
    for match, (lab, uni) in ingredientes().items():
        filas, f = filas_ingrediente(df, match, uni)
        if filas.empty:
            raise RuntimeError(f"{lab}: sin filas en ODEPA para '{match}'")
        # la agrupada es la del pipeline: precio_semanal, por el factor
        agr_fecha = precio_semanal(df, match) * f
        if not _igual(filas.groupby("fecha")["precio"].mean(), agr_fecha):
            raise RuntimeError(f"{lab}: las filas no rearman precio_semanal")
        agr = agr_fecha.resample("W-MON").mean()
        tipos = por_tipo(filas)
        comunes, corte, solo_antes, solo_despues = tipos_comunes(filas)
        est, n_est = estratificada(tipos, comunes)
        agr_ing[match], est_ing[match] = agr, est
        com_ing[match] = solo_comunes(filas, comunes, agr.index)
        semanal.append(tabla_semanal(lab, filas, agr, est, n_est, len(comunes)))
        anual.append(participacion_anual(lab, filas))
        # cobertura sobre las semanas con agrupada: una semana sin
        # estratificada cuenta como incompleta
        con_agr = agr.dropna().index
        n_completas = int((n_est.reindex(con_agr) == len(comunes)).sum()) if comunes else 0
        completas = 100.0 * n_completas / len(con_agr) if len(con_agr) else 0.0
        s = filas.assign(semana=semana_de(filas["fecha"]))
        ing[match] = {"agr": agr, "est": est, "tipos": tipos,
                      "cuenta": s.groupby(["semana", "tipo"]).size().unstack(fill_value=0)}
        primera = filas[filas["tipo"] != SIN_TIPO].groupby("tipo")["fecha"].min()
        info[lab] = {"comunes": comunes, "completas": completas, "semanas": len(con_agr),
                     "n_completas": n_completas, "sin_tipo_anios": anios_sin_tipo(filas)}
        print(f"{lab} [{match}]: {len(filas)} filas {filas['fecha'].min():%Y-%m-%d} a "
              f"{filas['fecha'].max():%Y-%m-%d}; corte {corte:%Y-%m-%d}; "
              f"comunes {comunes or 'NINGUNO'}; solo antes {solo_antes or '-'}; "
              f"solo después {solo_despues or '-'}; sin tipo "
              f"{int((filas['tipo'] == SIN_TIPO).sum())} filas; semanas con todos los "
              f"comunes {completas:.1f}% de {len(con_agr)} con precio")
        print("    primera fila de cada tipo: " + ", ".join(
            f"{t} {d:%Y-%m-%d}" for t, d in primera.sort_values().items()))
        prods = filas.groupby("producto")["fecha"].agg(["min", "max", "size"])
        print("    productos: " + "; ".join(
            f"{p} ({r['min']:%Y} a {r['max']:%Y}, {r['size']} filas)" for p, r in prods.iterrows()))
        imprimir_participacion(anual[-1])

    tabla = pd.concat(semanal, ignore_index=True)
    anual = [a for a in anual if not a.empty]
    anual = (pd.concat(anual, ignore_index=True) if anual else pd.DataFrame(
        {"ingrediente": [], "anio": [], "tipo": [], "anio_base": [], "filas": [],
         "participacion": [], "cambio_pp": [], "marca": pd.Series([], dtype=bool)}))
    print("\nÍNDICES: pipeline de esta corrida y estratificada")
    res, filas_idx = {}, []
    for code, meta in BASKETS.items():
        items = meta["items"]
        d, comp = calcular(df, ipc, items)
        r = resumen(d, meta, comp)
        nom_agr = canasta({m: agr_ing[m] for (_l, m, _q, _u) in items}, items)
        real_agr = deflactar(nom_agr, ipc)
        if not (_igual(nom_agr, d["nominal"]) and _igual(real_agr, d["real"])):
            raise RuntimeError(f"{meta['nombre']}: la agrupada rearmada no es la del pipeline")
        agr = metricas(d["real"])
        if (agr["percentil"], agr["z"]) != (r["percentil"], r["zscore"]):
            raise RuntimeError(f"{meta['nombre']}: percentil o z distinto de resumen()")
        nom_est = canasta({m: est_ing[m] for (_l, m, _q, _u) in items}, items)
        real_est = deflactar(nom_est, ipc) if nom_est.notna().any() else nom_est
        est = metricas(real_est)
        # la regla compara las dos series sobre las mismas semanas: si la
        # estratificada no cubre las del pipeline, el índice no se evalúa
        comparable = est is not None and real_est.dropna().index.equals(d["real"].dropna().index)
        antes, despues = brecha(d["real"], real_est, CORTE) if est else (None, None)
        motivo = None
        if est is None:
            motivo = "estratificada sin datos: algún ingrediente sin tipos comunes"
        elif not comparable:
            motivo = (f"bases distintas: estratificada {est['n']} semanas de "
                      f"{est['inicio']:%Y-%m-%d} a {est['semana']:%Y-%m-%d}, pipeline "
                      f"{agr['n']} de {agr['inicio']:%Y-%m-%d} a {agr['semana']:%Y-%m-%d}")
        res[code] = {"nombre": meta["nombre"], "agr": agr, "est": est, "comparable": comparable,
                     "motivo": motivo, "brecha": (antes, despues)}
        tabla_idx = pd.DataFrame({"nominal_agrupada": nom_agr, "real_agrupada": d["real"],
                                  "nominal_estratificada": nom_est,
                                  "real_estratificada": real_est.reindex(nom_est.index)
                                  if est else np.nan}).dropna(how="all")
        tabla_idx.insert(0, "indice", code)
        filas_idx.append(tabla_idx.round(2).rename_axis("semana").reset_index())
        if est is None:
            print(f"  {meta['nombre']}: {motivo}")
            continue
        if not comparable:
            comun = d["real"].dropna().index.intersection(real_est.dropna().index)
            ac, ec = metricas(d["real"].reindex(comun)), metricas(real_est.reindex(comun))
            print(f"  {meta['nombre']}: NO ENTRA A LA REGLA ({motivo})")
            if ac and ec:
                print(f"    en las {ac['n']} semanas comunes: percentil {ac['percentil']} -> "
                      f"{ec['percentil']}; máximo {ac['maximo']:%Y-%m-%d} -> "
                      f"{ec['maximo']:%Y-%m-%d}; z {ac['z']} -> {ec['z']}")
        f_ = lambda x: "s/d" if x is None else f"{x:+.1f}%"  # noqa: E731
        print(f"  {meta['nombre']}: semana {agr['semana']:%Y-%m-%d}, {agr['n']} semanas "
              f"desde {agr['inicio']:%Y-%m-%d} (estratificada {est['n']} desde "
              f"{est['inicio']:%Y-%m-%d}); percentil {agr['percentil']} -> "
              f"{est['percentil']}; máximo {agr['maximo']:%Y-%m-%d} -> "
              f"{est['maximo']:%Y-%m-%d}; z {agr['z']} -> {est['z']}; estratificada sobre "
              f"agrupada: antes del corte {f_(antes)}, después {f_(despues)}")
        imprimir_descomposicion(items, com_ing, ipc, d["real"], real_est, agr, est, ing)
        if publicado and code in publicado:
            p = publicado[code]
            igual = (p.get("percentil"), p.get("zscore"), p.get("fecha")) == (
                r["percentil"], r["zscore"], r["fecha"])
            print(f"    publicado en carestia.cl: semana {p.get('fecha')}, percentil "
                  f"{p.get('percentil')}, z {p.get('zscore')} "
                  f"({'igual a esta corrida' if igual else 'DISTINTO de esta corrida'})")

    # contexto, no cambia la regla: el año cae dentro del período de algún
    # índice que usa el ingrediente (el índice tiene datos el año anterior)
    usa = {lab: [code for code, meta in BASKETS.items()
                 if match in [i[1] for i in meta["items"]]]
           for match, (lab, _u) in ingredientes().items()}
    anual["en_indice"] = [any(res[c]["agr"]["inicio"].year <= a - 1 for c in usa[i])
                          for i, a in zip(anual["ingrediente"], anual["anio"])]
    saltos = anual[anual["marca"].astype(bool)].sort_values("cambio_pp", key=abs,
                                                            ascending=False)
    sin_evaluar = [f"{lab} {y}" for lab, i in info.items() for y in i["sin_tipo_anios"]
                   if any(res[c]["agr"]["inicio"].year <= y for c in usa[lab])]
    if sin_evaluar:
        print("\nAÑOS CON FILAS SIN TIPO DE PUNTO dentro del período de su índice (no se "
              "evalúa su participación): " + ", ".join(sin_evaluar))
    print("\nSALTOS DE PARTICIPACIÓN (más de 15 pp respecto del año anterior)")
    for _, r in saltos.iterrows():
        print(f"  {r['ingrediente']} {r['anio']}: {r['tipo']} {r['cambio_pp']:+.1f} pp "
              f"respecto de {r['anio_base']} (queda en {r['participacion']:.1f}%)"
              f"{'' if r['en_indice'] else ', fuera del período de su índice'}")
    if saltos.empty:
        print("  ninguno")

    os.makedirs(carpeta, exist_ok=True)
    tabla.to_csv(os.path.join(carpeta, f"{PREFIJO}_semanal.csv"), index=False)
    anual.to_csv(os.path.join(carpeta, f"{PREFIJO}_anual.csv"), index=False)
    pd.concat(filas_idx, ignore_index=True).assign(
        semana=lambda x: x["semana"].dt.strftime("%Y-%m-%d")).to_csv(
        os.path.join(carpeta, f"{PREFIJO}_indices.csv"), index=False)
    print(f"\nEscritos {PREFIJO}_semanal.csv ({len(tabla)} filas), {PREFIJO}_anual.csv "
          f"({len(anual)} filas) y {PREFIJO}_indices.csv")

    v = veredicto(res, saltos.to_dict("records"), sin_evaluar)
    rango = f"{df['fecha'].min():%Y} a {df['fecha'].max():%Y}"
    lineas = lineas_resumen(res, saltos, info, v, rango)
    print("\n" + "\n".join(lineas))
    return {"indices": res, "saltos": saltos, "info": info, "veredicto": v,
            "semanal": tabla, "anual": anual, "resumen": lineas, "ing": ing}


def lineas_resumen(res: dict, saltos: pd.DataFrame, info: dict, v: dict,
                   rango: str = "2008 a 2026") -> list:
    """El resumen del final del log, de máximo 15 líneas."""
    ok = {lab: i for lab, i in info.items() if i["comunes"]}
    sem = sum(i["semanas"] for i in ok.values())
    comp = 100.0 * sum(i["n_completas"] for i in ok.values()) / sem if sem else 0.0
    peor = min(ok, key=lambda lab: ok[lab]["completas"]) if ok else None
    lineas = [
        "=" * 20 + " RESUMEN: composición de puntos ODEPA " + "=" * 20,
        f"RM, semanal W-MON, {rango}. Corte {CORTE:%Y-%m-%d}. Estratificada: promedio "
        "por tipo de punto y luego simple entre los tipos con filas antes y después del corte.",
        f"Tipo común sin precio: su último precio hasta {FFILL} semanas; más, los tipos que "
        f"hay ({comp:.1f}% de las semanas con todos los tipos comunes"
        + (f"; mínimo {peor} {ok[peor]['completas']:.1f}%)." if peor else ")."),
        "Índice: percentil vigente agrupada/estratificada (dif.) | semana del máximo real | "
        "z-score",
    ]
    for code, r in res.items():
        a, e = r["agr"], r["est"]
        if e is None:
            lineas.append(f"{r['nombre']}: {a['percentil']}/s/d | {a['maximo']:%Y-%m-%d}/s/d "
                          f"| {a['z']}/s/d (sin tipos comunes)")
            continue
        lineas.append(f"{r['nombre']}: {a['percentil']}/{e['percentil']} "
                      f"({e['percentil'] - a['percentil']:+d}) | {a['maximo']:%Y-%m-%d}/"
                      f"{e['maximo']:%Y-%m-%d} | {a['z']}/{e['z']}"
                      + ("" if r.get("comparable", True) else
                         " (bases distintas: no entra a la regla)"))
    d = v["deltas"]
    mayor = max(d, key=lambda k: abs(d[k])) if d else None
    lineas.append(f"(a) percentil 5 puntos o más: {'sí, ' + ', '.join(res[k]['nombre'] for k in v['percentil']) if v['percentil'] else 'no'}"
                  + (f" (mayor diferencia {d[mayor]:+d}, {res[mayor]['nombre']})" if mayor else ""))
    lineas.append(f"(b) cambia la semana del máximo real: "
                  f"{'sí, ' + ', '.join(res[k]['nombre'] for k in v['maximo']) if v['maximo'] else 'no'}")
    if len(saltos):
        top = saltos.iloc[0]
        lineas.append(f"(c) tipo con más de 15 pp entre años: sí, {len(saltos)} casos en "
                      f"{saltos['ingrediente'].nunique()} ingredientes, "
                      f"{int(saltos['en_indice'].sum())} dentro del período de su índice "
                      f"(mayor: {top['ingrediente']} {top['anio']}, {top['tipo']} "
                      f"{top['cambio_pp']:+.1f} pp)")
    else:
        lineas.append("(c) tipo con más de 15 pp entre años: no")
    if v["no_verificable"] or v["sin_evaluar"]:
        partes = [f"{res[k]['nombre']} ({res[k]['motivo'].split(':')[0]})"
                  for k in v["no_verificable"]]
        if v["sin_evaluar"]:
            ing = {x.rsplit(" ", 1)[0] for x in v["sin_evaluar"]}
            anios = [int(x.rsplit(" ", 1)[1]) for x in v["sin_evaluar"]]
            partes.append(f"(c) sin evaluar por filas sin tipo: {len(v['sin_evaluar'])} casos "
                          f"de ingrediente y año ({len(ing)} ingredientes, {min(anios)} a "
                          f"{max(anios)})")
        lineas.append("No verificable: " + "; ".join(partes) + ".")
    lineas.append(f"VEREDICTO: {v['veredicto']}")
    lineas.append("Solo diagnóstico: cero cambios de metodología. Decide Pedro.")
    if len(lineas) > MAX_RESUMEN:
        raise RuntimeError(f"el resumen tiene {len(lineas)} líneas (máximo {MAX_RESUMEN})")
    return lineas


def leer_publicado() -> dict:
    """Los 4 índices de indices.json en carestia.cl, para contrastar con esta
    corrida. Vacío si no se puede leer (no es parte del veredicto)."""
    try:
        r = requests.get(SITIO, timeout=60)
        r.raise_for_status()
        return r.json().get("indices", {})
    except Exception as e:  # noqa
        print(f"[no se pudo leer {SITIO}: {e}]")
        return {}


def main() -> None:
    df = cargar_odepa()
    faltan = anios_faltantes(df)
    if faltan:
        raise RuntimeError(f"ODEPA sin filas RM en {faltan} (cargar_odepa los saltó): el "
                           "diagnóstico no es verificable con datos incompletos; volver a correrlo")
    ipc = cargar_ipc()
    diagnostico(df, ipc, ".", leer_publicado())


# ---------------- prueba sintética (sin red) ----------------
PRODUCTOS_PRUEBA = {
    # match: (ProductoBase, unidad ODEPA, precio base, desde)
    "Asado de tira": ("Asado de tira", "$/kilo", 9000, "2014-01-06"),
    "Asado Carnicero": ("Asado Carnicero", "$/kilo", 7000, None),
    "Tomate": ("Tomate", "$/kilo", 1000, None),
    "Cebolla": ("Cebolla", "$/unidad", 300, None),
    "Palta": ("Palta Hass", "$/kilo", 3000, None),
    "Lim": ("Limón", "$/kilo", 1100, None),
    "Marraqueta": ("Marraqueta", "$/kilo", 1800, None),
    "Lechuga": ("Lechuga", "$/unidad", 700, None),
    "Pepino ensalada": ("Pepino ensalada", "$/unidad", 400, None),
    "Pimiento": ("Pimiento", "$/unidad", 600, None),
    "Manzana": ("Manzana", "$/kilo", 1200, None),
    "tano": ("Plátano", "$/kilo", 1000, None),
    "Naranja": ("Naranja", "$/kilo", 900, None),
    "Pera": ("Pera", "$/kilo", 1100, None),
    "Mandarina": ("Mandarina", "$/kilo", 1300, None),
    "Mantequilla": ("Mantequilla", "$/pan de 250 gramos", 2500, None),
    "Queso Gauda": ("Queso Gauda", "$/envase 1 kilo", 9000, None),
    "Huevo color": ("Huevo color", "$/bandeja 12 unidades", 2400, "2014-01-06"),
    "Leche Fluida Entera": ("Leche Fluida Entera", "$/Caja de 1 Litro", 900, None),
}
MULT = {"Feria libre": 1.0, "Supermercado": 1.3, "Supermercado en Línea": 1.6}
SEMANAS_PRUEBA = pd.date_range("2010-01-04", "2016-12-26", freq="W-MON")


def _puntos_prueba(semana: pd.Timestamp, sin_cambio: bool = False) -> list:
    """Antes del corte, 3 ferias y 1 supermercado; después, 3 ferias y 4
    supermercados; desde 2015, además un supermercado en línea. Sin cambio:
    3 ferias y 1 supermercado siempre."""
    ferias = [f"{s} | Feria libre" for s in ("Norte", "Sur", "Oriente")]
    sup = ["Centro | Supermercado"]
    if sin_cambio:
        return ferias + sup
    if semana >= CORTE:
        sup += [f"{s} | Supermercado" for s in ("Norte", "Sur", "Oriente")]
    linea = ["Oriente | Supermercado en Línea"] if semana >= pd.Timestamp("2015-01-05") else []
    return ferias + sup + linea


def df_prueba(huecos: dict = None, sin_tipo_antes: set = frozenset(), sin_cambio: bool = False,
              sin_tipo_hasta: str = None) -> pd.DataFrame:
    """Filas como las de cargar_odepa para los 19 ingredientes. Cada tipo
    tiene un precio fijo relativo a la feria (MULT) por una tendencia común,
    así que la estratificada no salta en el corte y la agrupada sí.
    huecos: {match: [semanas sin filas de supermercado]}; sin_tipo_antes:
    productos sin tipo de punto antes del corte; sin_tipo_hasta: todos sin
    tipo de punto antes de esa fecha."""
    huecos = huecos or {}
    reg = []
    for i, semana in enumerate(SEMANAS_PRUEBA):
        tendencia = 1 + 0.002 * i
        for match, (prod, unidad, base, desde) in PRODUCTOS_PRUEBA.items():
            if desde and semana < pd.Timestamp(desde):
                continue
            for punto in _puntos_prueba(semana, sin_cambio):
                tipo = punto.split(" | ")[1]
                if tipo == "Supermercado" and semana in huecos.get(match, ()):
                    continue
                p = base * tendencia * MULT[tipo]
                if match in sin_tipo_antes and semana < CORTE:
                    punto = ""
                if sin_tipo_hasta and semana < pd.Timestamp(sin_tipo_hasta):
                    punto = ""
                reg.append({"ProductoBase": prod, "Precio promedio": p, "Precio minimo": p * 0.9,
                            "Precio maximo": p * 1.1, "Unidad": unidad, "Grupo": "Prueba",
                            "fecha": semana, "region_rm": True, "Punto": punto})
    return pd.DataFrame(reg)


def prueba() -> None:
    """Propiedades del diagnóstico con datos sintéticos, sin red."""
    ipc = pd.Series(1.003 ** np.arange(90), index=pd.date_range("2009-12-01", periods=90,
                                                                  freq="MS"))
    hueco_corto = list(SEMANAS_PRUEBA[300:303])           # 3 semanas sin supermercado
    hueco_largo = list(SEMANAS_PRUEBA[320:326])           # 6 semanas sin supermercado
    df = df_prueba({"Palta": hueco_corto + hueco_largo})
    with tempfile.TemporaryDirectory() as tmp:
        out = diagnostico(df, ipc, tmp)
        for nombre in ("semanal", "anual", "indices"):
            assert os.path.exists(os.path.join(tmp, f"{PREFIJO}_{nombre}.csv")), nombre
        leido = pd.read_csv(os.path.join(tmp, f"{PREFIJO}_semanal.csv"))
    assert list(leido.columns[:7]) == ["ingrediente", "semana", "filas", "puntos", "mezcla",
                                       "agrupada", "estratificada"]
    t = out["semanal"]
    tom = t[t["ingrediente"] == "Tomate"].set_index("semana")
    tend = {f"{s:%Y-%m-%d}": 1 + 0.002 * i for i, s in enumerate(SEMANAS_PRUEBA)}
    esperado = 1000 * tom.index.map(tend).to_numpy() * (1.0 + 1.3) / 2
    # la estratificada no ve el cambio de muestra: feria y supermercado, mitad y mitad
    assert np.allclose(tom["estratificada"].to_numpy(float), esperado, atol=0.01)
    # la agrupada sí: 1 de 4 filas en supermercado antes, 4 de 7 después (y la en línea)
    antes, despues = tom.loc["2012-12-31"], tom.loc["2013-03-04"]
    assert np.isclose(antes["agrupada"], 1000 * tend["2012-12-31"] * (3 + 1.3) / 4, atol=0.01)
    assert np.isclose(despues["agrupada"], 1000 * tend["2013-03-04"] * (3 + 4 * 1.3) / 7,
                      atol=0.01)
    assert antes["filas"] == 4 and despues["puntos"] == 7
    assert despues["mezcla"] == "Feria libre=0.429;Supermercado=0.571"
    assert out["info"]["Tomate"]["comunes"] == ["Feria libre", "Supermercado"]
    # sin filas antes del corte: el "antes" es su primer año; la en línea (2015) no entra
    assert out["info"]["Huevos"]["comunes"] == ["Feria libre", "Supermercado"]
    assert out["info"]["Asado de tira"]["comunes"] == ["Feria libre", "Supermercado"]
    # huecos: 3 semanas se cubren con el último precio; de 6, las 2 últimas van sin él
    pal = t[t["ingrediente"] == "Palta"].set_index("semana")
    corto = [f"{s:%Y-%m-%d}" for s in hueco_corto]
    largo = [f"{s:%Y-%m-%d}" for s in hueco_largo]
    assert (pal.loc[corto, "tipos_con_precio"] == 2).all()
    assert (pal.loc[largo[:4], "tipos_con_precio"] == 2).all()
    assert (pal.loc[largo[4:], "tipos_con_precio"] == 1).all()
    assert np.allclose(pal.loc[largo[4:], "estratificada"].to_numpy(float),
                       [round(3000 * tend[s] * MULT["Feria libre"], 2) for s in largo[4:]])
    # participación: el supermercado salta en 2013 (25% a 54%); la en línea entra
    # en 2015 con 12,5% (no llega a 15 pp)
    a = out["anual"]
    tom_a = a[a["ingrediente"] == "Tomate"]
    marcados = tom_a[tom_a["marca"]]
    assert set(zip(marcados["anio"], marcados["tipo"])) == {(2013, "Feria libre"),
                                                            (2013, "Supermercado")}
    assert not a[(a["anio"] == 2015) & (a["tipo"] == "Supermercado en Línea")]["marca"].any()
    sal = out["saltos"].groupby("ingrediente")["en_indice"].all()
    assert sal["Tomate"] and sal["Manzana"] and not sal["Mantequilla"] and not sal["Asado carnicero"]
    # los índices: la estratificada sigue la tendencia; Ensalada y Fruta cruzan el corte
    v = out["veredicto"]
    assert v["veredicto"] == "QUIEBRE MATERIAL" and v["participacion"]
    assert all(r["est"] is not None for r in out["indices"].values())
    assert len(out["resumen"]) <= MAX_RESUMEN

    # la composición de una semana, también con el supermercado ausente
    import contextlib
    import io
    texto = io.StringIO()
    with contextlib.redirect_stdout(texto):
        for semana in (SEMANAS_PRUEBA[200], hueco_largo[-1]):
            imprimir_semana(semana, BASKETS["asado"]["items"], out["ing"])
    texto = texto.getvalue()
    # semana 200 (tendencia 1,4): palta 4.200 en feria y 5.460 en supermercado
    assert ("Palta: agrupada 4,920, estratificada 4,830 | Feria libre 4,200 (3 filas, "
            "mediana vecina 4,200) | Supermercado 5,460 (4 filas" in texto)
    # en el hueco largo la palta no trae supermercado y la estratificada es la feria
    palta = [l for l in texto.splitlines() if "Palta:" in l][-1]
    assert "estratificada 4,950 | Feria libre 4,950" in palta
    assert palta.count("| Supermercado") == 1 and "| Supermercado en Línea" in palta

    # la regla, en sus bordes
    m = {"percentil": 50, "maximo": pd.Timestamp("2020-01-06")}
    caso = lambda p, mx: {"x": {"agr": m, "est": {"percentil": p, "maximo": mx}}}  # noqa: E731
    assert veredicto(caso(55, m["maximo"]), [])["veredicto"] == "QUIEBRE MATERIAL"
    assert veredicto(caso(45, m["maximo"]), [])["veredicto"] == "QUIEBRE MATERIAL"
    assert veredicto(caso(54, m["maximo"]), [])["veredicto"] == "ROBUSTO"
    assert veredicto(caso(50, pd.Timestamp("2020-01-13")), [])["veredicto"] == "QUIEBRE MATERIAL"
    assert veredicto(caso(50, m["maximo"]), [{"x": 1}])["veredicto"] == "QUIEBRE MATERIAL"
    assert veredicto({"x": {"agr": m, "est": None}}, [])["veredicto"] == "NO VERIFICABLE"
    # 15 pp justos no marcan; más de 15 sí
    dos = pd.DataFrame({"fecha": pd.to_datetime(["2011-01-03"] * 20 + ["2012-01-02"] * 20),
                        "precio": 1.0, "punto": "x | y", "producto": "p",
                        "tipo": ["A"] * 10 + ["B"] * 10 + ["A"] * 13 + ["B"] * 7})
    assert not participacion_anual("p", dos)["marca"].any()                     # 15 pp
    dos.loc[dos.index[-1], "tipo"] = "A"                                         # 14/6: 20 pp
    assert participacion_anual("p", dos)["marca"].any()

    # sin tipo de punto antes del corte: no hay tipos comunes y la estratificada
    # no se arma (no se inventa); la participación no cuenta las filas sin tipo
    sin = diagnostico(df_prueba(sin_tipo_antes={"Tomate"}), ipc, tempfile.mkdtemp())
    assert sin["info"]["Tomate"]["comunes"] == []
    assert sin["indices"]["ensalada"]["est"] is None and sin["indices"]["asado"]["est"] is None
    assert sin["indices"]["fruta"]["est"] is not None

    # sin cambio de muestra: mezcla fija, sin tipos nuevos; da ROBUSTO
    rob = diagnostico(df_prueba(sin_cambio=True), ipc, tempfile.mkdtemp())
    assert rob["veredicto"]["veredicto"] == "ROBUSTO", rob["resumen"]
    assert rob["saltos"].empty and all(r["comparable"] for r in rob["indices"].values())

    # sin tipo de punto hasta 2012: la estratificada de Ensalada y Fruta parte
    # en 2012 y la del pipeline en 2010; no se comparan (bases distintas) y
    # los años sin tipo no se evalúan: NO VERIFICABLE, no QUIEBRE
    bas = diagnostico(df_prueba(sin_cambio=True, sin_tipo_hasta="2012-01-02"), ipc,
                      tempfile.mkdtemp())
    assert bas["veredicto"]["veredicto"] == "NO VERIFICABLE", bas["resumen"]
    assert set(bas["veredicto"]["no_verificable"]) == {"ensalada", "fruta"}
    assert "Tomate 2010" in bas["veredicto"]["sin_evaluar"]
    assert bas["indices"]["asado"]["comparable"] and bas["indices"]["desayuno"]["comparable"]
    assert any(l.startswith("No verificable") and "casos de ingrediente y año" in l
               for l in bas["resumen"])

    # ninguna fila con tipo: NO VERIFICABLE, sin caerse, y escribe los CSV
    nada = df_prueba(sin_cambio=True).assign(Punto="")
    with tempfile.TemporaryDirectory() as tmp:
        sin_tipo = diagnostico(nada, ipc, tmp)
        assert len(os.listdir(tmp)) == 3
    assert sin_tipo["veredicto"]["veredicto"] == "NO VERIFICABLE"

    # un año de ODEPA que no se bajó detiene la corrida (main)
    falta = df_prueba(sin_cambio=True)
    falta = falta[falta["fecha"].dt.year != 2011]
    assert anios_faltantes(falta, range(2010, 2017)) == [2011]
    assert anios_faltantes(df_prueba(sin_cambio=True), range(2010, 2017)) == []
    # el CSV de 2013 trae la semana del 31 de diciembre de 2012: no da 2012 por bajado
    sin_2012 = df_prueba(sin_cambio=True)
    sin_2012 = sin_2012[(sin_2012["fecha"].dt.year != 2012)
                        | (sin_2012["fecha"] == pd.Timestamp("2012-12-31"))]
    assert anios_faltantes(sin_2012, range(2010, 2017)) == [2012]
    # el último año, con pocas semanas (enero), no detiene la corrida
    enero = df_prueba(sin_cambio=True)
    enero = enero[enero["fecha"] <= pd.Timestamp("2016-01-11")]
    assert anios_faltantes(enero, range(2010, 2017)) == []
    print("\nPRUEBA SINTÉTICA OK")


if __name__ == "__main__":
    if "--prueba" in sys.argv[1:]:
        prueba()
    else:
        main()

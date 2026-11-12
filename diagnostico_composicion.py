"""
diagnostico_composicion.py - La serie anterior contra la oficial por tipo de punto
==================================================================================
Diagnóstico de solo lectura: no toca el sitio ni el workflow de Pages y nada
de esto se publica.

Historia: el diagnóstico preregistrado (PR #88 y #90, corrida real
40625766095 del 28-10-2026) comparó el promedio simple de las filas de cada
producto (la serie de entonces) con una serie estratificada por tipo de punto
de monitoreo y dio QUIEBRE MATERIAL. El 12-11-2026 el dueño autorizó cambiar
la metodología: la serie oficial pasa a ser la de indices.precio_oficial
(tipos estables, promedio dentro de cada tipo y luego simple entre ellos).
Este script importa esa regla de indices.py, sin copiarla, y compara:

  anterior  el promedio simple entre filas: de cada fecha y luego de esas
            fechas en la semana W-MON (lo que hacía precio_semanal hasta el
            12-11-2026), rearmado aquí solo para comparar;
  oficial   precio_semanal de indices.py, la que se publica.

Por cada ingrediente de las 4 canastas, semanal W-MON, RM, 2008 a 2026:
  1. Filas, puntos, tipos estables y no estables, cobertura de cada tipo
     antes y desde el corte (1 de marzo de 2013) y semanas en que algún tipo
     estable usa su último precio o queda fuera.
  2. Participación de cada tipo de punto por año, de dos maneras: en las
     filas de ODEPA (el peso implícito de cada tipo en la serie anterior,
     solo contexto) y en la serie oficial (el peso de cada tipo estable en
     el promedio de cada semana, promediado en el año). Marca los años en que
     algún tipo cambia más de 15 pp respecto del año anterior.
  3. Cada índice con las dos series (cantidades, resample W-MON,
     ffill(limit=4), min_count y deflactor de calcular): percentil vigente,
     semana del máximo real y z-score. La oficial se rearma con la regla
     importada y se exige que dé exactamente lo de calcular(): si no, la
     corrida se detiene. Si falta un año de ODEPA, también.

Criterio para seguir (el de participación del diagnóstico, ahora sobre la
serie oficial): CUMPLE si ningún tipo de punto cambia más de 15 pp de peso
entre años en la serie oficial de ningún ingrediente; si no, NO CUMPLE. Las
diferencias de percentil y de máximo entre anterior y oficial se informan:
son el efecto del cambio, no un criterio.

Salida (en la carpeta actual):
  diagnostico_composicion_semanal.csv   ingrediente y semana: filas, puntos,
                                        mezcla, anterior, oficial
  diagnostico_composicion_anual.csv     ingrediente, año y tipo: participación
                                        en las filas y en la serie oficial
  diagnostico_composicion_indices.csv   índice y semana: nominal y real,
                                        anterior y oficial
  y en la consola el detalle y, al final, un resumen de máximo 15 líneas.

Con --comparar indices.json no baja ODEPA: compara el indices.json recién
calculado con el resumen.json y el indices.json publicados en carestia.cl
(tabla antes y después de los 4 índices y cambios del catálogo).

Correr (mismo entorno que indices.py; BCCH_USER y BCCH_PASS para el IPC):
  python diagnostico_composicion.py
  python diagnostico_composicion.py --comparar indices.json
  python diagnostico_composicion.py --prueba   (sintética, sin red)
"""

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import requests

from indices import (BASKETS, CORTE_MUESTRA, RESOURCES, SIN_TIPO, TIPO_ESTABLE, TIPO_FFILL,
                     YEARS, calcular, cargar_ipc, cargar_odepa, combinar_tipos, de_su_unidad,
                     factor_precio, por_tipo, precio_semanal, resumen, tipo_punto,
                     tipos_estables, unidad_modal)

CORTE = CORTE_MUESTRA                 # ODEPA amplía productos y puntos
UMBRAL_PP = 15.0                      # participación: más de 15 pp entre años
FFILL = 4                             # semanas, el ffill(limit=4) de la canasta
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
    """Las filas que usa precio_semanal (mismo match, de_su_unidad), con el
    precio llevado a la unidad del ítem con el factor de _serie_canasta, su
    punto y su tipo de punto (tipo_punto). Devuelve (filas, factor)."""
    f, _ = factor_precio(unidad_modal(df, match), uni)
    sub = de_su_unidad(df[df["ProductoBase"].str.contains(match, case=False, na=False)])
    if sub.empty:
        return pd.DataFrame(columns=["fecha", "precio", "Punto", "tipo", "producto"]), f
    if "Punto" in sub.columns:
        punto = sub["Punto"].fillna("").astype(str).str.strip()
    else:
        punto = pd.Series("", index=sub.index)
    out = pd.DataFrame({
        "fecha": sub["fecha"].to_numpy(),
        "precio": sub["Precio promedio"].to_numpy(dtype=float) * f,
        "Punto": punto.to_numpy(),
        "tipo": tipo_punto(sub).to_numpy(),
        "producto": sub["ProductoBase"].astype(str).to_numpy(),
    })
    return out.sort_values("fecha", kind="stable").reset_index(drop=True), f


def semana_de(fechas: pd.Series) -> pd.Series:
    """Etiqueta de la semana W-MON de cada fecha (la de resample("W-MON"):
    cierra y se rotula el lunes, así que un lunes es su propia semana)."""
    f = pd.to_datetime(fechas).dt.normalize()
    return f + pd.to_timedelta((-f.dt.day_of_week) % 7, unit="D")


# ---------------- las dos series ----------------
def anterior(filas: pd.DataFrame) -> pd.Series:
    """La serie de antes del 12-11-2026: promedio simple de las filas de cada
    fecha y luego de esas fechas en la semana W-MON."""
    return filas.groupby("fecha")["precio"].mean().resample("W-MON").mean()


def oficial(filas: pd.DataFrame):
    """La serie oficial con la regla de indices.py: (precio semanal por tipo,
    tipos estables, serie, pesos de cada tipo estable por semana)."""
    tipos = por_tipo(filas, "precio")
    estables = tipos_estables(tipos)
    serie, pesos = combinar_tipos(tipos, estables)
    return tipos, estables, serie, pesos


# ---------------- 1. filas, puntos y mezcla ----------------
def tabla_semanal(lab: str, filas: pd.DataFrame, ant: pd.Series, ofi: pd.Series,
                  pesos: pd.DataFrame, propios: pd.Series, n_estables: int) -> pd.DataFrame:
    """Una fila por semana con filas de ODEPA: filas, puntos distintos,
    mezcla (participación de cada tipo en las filas), las dos series en pesos
    nominales por la unidad del ítem (sin cantidad ni ffill), cuántos tipos
    estables entran al promedio y cuántos con precio propio esa semana."""
    s = filas.assign(semana=semana_de(filas["fecha"]))
    n = s.groupby("semana").size()
    idx = n.index
    if set(ant.dropna().index) != set(idx):
        raise RuntimeError(f"{lab}: las semanas de la serie anterior no son las de sus filas")
    puntos = (s[s["Punto"] != ""].groupby("semana")["Punto"].nunique()
              .reindex(idx, fill_value=0))
    cuenta = s.groupby(["semana", "tipo"]).size().unstack(fill_value=0)
    part = cuenta.div(cuenta.sum(axis=1), axis=0)
    mezcla = [";".join(f"{t}={v:.3f}" for t, v in fila.items() if v > 0)
              for _, fila in part.reindex(idx).iterrows()]
    return pd.DataFrame({
        "ingrediente": lab, "semana": idx.strftime("%Y-%m-%d"),
        "filas": n.to_numpy(), "puntos": puntos.to_numpy(), "mezcla": mezcla,
        "anterior": ant.reindex(idx).round(2).to_numpy(),
        "oficial": ofi.reindex(idx).round(2).to_numpy(),
        "tipos_en_promedio": (pesos > 0).sum(axis=1).reindex(idx).astype("Int64").to_numpy(),
        "tipos_con_precio_propio": propios.reindex(idx).astype("Int64").to_numpy(),
        "tipos_estables": n_estables,
    })


# ---------------- 2. participación por año ----------------
def _marcar(lab: str, part: pd.DataFrame, fuente: str, extra: dict = None) -> list:
    """Filas de participación (en %) por año y tipo con su cambio en pp
    respecto del año anterior con datos y la marca de más de 15 pp."""
    cambio = part.diff()
    base = pd.Series(part.index, index=part.index).shift(1)
    reg = []
    for a in part.index:
        for t in part.columns:
            c = cambio.loc[a, t]
            r = {"ingrediente": lab, "fuente": fuente, "anio": int(a), "tipo": t,
                 "anio_base": None if pd.isna(base.loc[a]) else int(base.loc[a]),
                 "participacion": round(float(part.loc[a, t]), 2),
                 "cambio_pp": None if pd.isna(c) else round(float(c), 2),
                 # redondeado: el error de punto flotante no decide el borde
                 "marca": bool(pd.notna(c) and round(abs(c), 6) > UMBRAL_PP)}
            if extra:
                r.update({k: v(a, t) for k, v in extra.items()})
            reg.append(r)
    return reg


def participacion_anual(lab: str, filas: pd.DataFrame) -> pd.DataFrame:
    """Participación de cada tipo de punto en las filas de ODEPA, por año de
    la fecha (el peso implícito de cada tipo en la serie anterior). Las
    filas sin tipo de punto no entran a la cuenta."""
    con = filas[filas["tipo"] != SIN_TIPO]
    if con.empty:
        return pd.DataFrame()
    cuenta = con.groupby([con["fecha"].dt.year, "tipo"]).size().unstack(fill_value=0)
    part = cuenta.div(cuenta.sum(axis=1), axis=0) * 100
    return pd.DataFrame(_marcar(lab, part, "filas",
                                {"filas": lambda a, t: int(cuenta.loc[a, t])}))


def participacion_oficial(lab: str, pesos: pd.DataFrame) -> pd.DataFrame:
    """Peso de cada tipo estable en la serie oficial, por año: el promedio
    en las semanas del año de su peso en el promedio de la semana (1/k entre
    los k que entran, 0 si queda fuera por más de 4 semanas sin precio)."""
    if pesos.empty:
        return pd.DataFrame()
    part = pesos.groupby(pesos.index.year).mean() * 100
    return pd.DataFrame(_marcar(lab, part, "oficial"))


def anios_sin_tipo(filas: pd.DataFrame) -> list:
    """Años con filas del ingrediente pero ninguna con tipo de punto."""
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


def brecha(ant: pd.Series, ofi: pd.Series, corte: pd.Timestamp):
    """Diferencia media (%) de la oficial sobre la anterior, real, antes y
    después del corte (None si no hay semanas de ese lado)."""
    d = ((ofi / ant) - 1).dropna() * 100
    antes, despues = d[d.index < corte], d[d.index >= corte]
    return (None if antes.empty else float(antes.mean()),
            None if despues.empty else float(despues.mean()))


def _por_anio(x: pd.Series, base: pd.Series) -> str:
    d = ((x / base) - 1).dropna() * 100
    return " ".join(f"{a % 100:02d}:{v:+.1f}" for a, v in d.groupby(d.index.year).mean().items())


def imprimir_participacion(anual: pd.DataFrame) -> None:
    """Participación de cada tipo por año (aa:%)."""
    for t, g in anual.groupby("tipo"):
        print(f"      {t}: " + " ".join(f"{int(r.anio) % 100:02d}:{r.participacion:.0f}"
                                       for r in g.itertuples()))


def imprimir_semana(semana: pd.Timestamp, items: list, ing: dict) -> None:
    """Lo que trae cada ingrediente en una semana: anterior, oficial y el
    precio de cada tipo de punto con sus filas (estable o no) y la mediana de
    ese tipo en las 4 semanas antes y después. Pesos nominales por la unidad
    del ítem."""
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
            marca = "" if t in x["estables"] else ", no estable"
            partes.append(f"{t} {p:,.0f} ({n} filas{marca}, mediana vecina {med:,.0f})")
        print(f"      {lab}: anterior {x['ant'].get(semana, np.nan):,.0f}, oficial "
              f"{x['ofi'].get(semana, np.nan):,.0f} | " + " | ".join(partes))


# ---------------- criterio ----------------
def criterio(saltos_oficial: list) -> str:
    """El criterio de participación sobre la serie oficial: ningún tipo de
    punto cambia más de 15 pp de peso entre años."""
    return "NO CUMPLE" if saltos_oficial else "CUMPLE"


# ---------------- el diagnóstico ----------------
def diagnostico(df: pd.DataFrame, ipc: pd.Series, carpeta: str = ".",
                publicado: dict = None) -> dict:
    """Corre los tres pasos sobre las filas RM de ODEPA ya cargadas (las de
    cargar_odepa) y el IPC de cargar_ipc, escribe los CSV en 'carpeta' e
    imprime el detalle y, al final, el resumen. Devuelve los resultados."""
    print("\n" + "=" * 72)
    print("TIPOS ESTABLES POR INGREDIENTE (regla de indices.py: precio en al menos "
          f"{TIPO_ESTABLE:.0%} de las semanas antes y desde {CORTE:%Y-%m-%d})")
    semanal, anual, ant_ing, ofi_ing, ing, info = [], [], {}, {}, {}, {}
    for match, (lab, uni) in ingredientes().items():
        filas, f = filas_ingrediente(df, match, uni)
        if filas.empty:
            raise RuntimeError(f"{lab}: sin filas en ODEPA para '{match}'")
        tipos, estables, ofi, pesos = oficial(filas)
        # la oficial rearmada aquí es la de indices.py: precio_semanal, por el factor
        if not _igual(ofi, precio_semanal(df, match) * f):
            raise RuntimeError(f"{lab}: las filas no rearman la serie oficial de indices.py")
        ant = anterior(filas)
        ant_ing[match], ofi_ing[match] = ant, ofi
        propios = tipos.reindex(columns=estables).notna().sum(axis=1)
        semanal.append(tabla_semanal(lab, filas, ant, ofi, pesos, propios, len(estables)))
        a_filas, a_ofi = participacion_anual(lab, filas), participacion_oficial(lab, pesos)
        anual += [a_filas, a_ofi]
        con = ofi.dropna().index
        arrastre = int(((propios.reindex(con) < len(estables))
                        & ((pesos.reindex(con) > 0).sum(axis=1) == len(estables))).sum())
        fuera = int(((pesos.reindex(con) > 0).sum(axis=1) < len(estables)).sum())
        s = filas.assign(semana=semana_de(filas["fecha"]))
        ing[match] = {"ant": ant, "ofi": ofi, "tipos": tipos, "estables": estables,
                      "cuenta": s.groupby(["semana", "tipo"]).size().unstack(fill_value=0)}
        info[lab] = {"estables": estables, "semanas": len(con), "arrastre": arrastre,
                     "fuera": fuera, "sin_tipo_anios": anios_sin_tipo(filas)}
        hay = tipos.notna()[tipos.notna().any(axis=1)]
        antes, desde = hay[hay.index < CORTE], hay[hay.index >= CORTE]

        def pct(x, t):
            return "s/s" if x.empty else f"{100 * x[t].mean():.0f}%"
        print(f"{lab} [{match}]: estables {estables}; {len(filas)} filas "
              f"{filas['fecha'].min():%Y-%m-%d} a {filas['fecha'].max():%Y-%m-%d}; "
              f"sin tipo {int((filas['tipo'] == SIN_TIPO).sum())} filas")
        print("    semanas con precio de cada tipo (antes / desde el corte): " + "; ".join(
            f"{t} {pct(antes, t)} / {pct(desde, t)}{'' if t in estables else ' (no estable)'}"
            for t in hay.columns))
        print(f"    {len(con)} semanas con precio oficial; {arrastre} con algún tipo estable "
              f"usando su último precio (hasta {TIPO_FFILL} semanas) y {fuera} con algún "
              "tipo estable fuera del promedio")
        prods = filas.groupby("producto")["fecha"].agg(["min", "max", "size"])
        print("    productos: " + "; ".join(
            f"{p} ({r['min']:%Y} a {r['max']:%Y}, {r['size']} filas)" for p, r in prods.iterrows()))
        if not a_filas.empty:
            print("    participación en las filas de ODEPA (serie anterior):")
            imprimir_participacion(a_filas)
        if not a_ofi.empty:
            print("    participación en la serie oficial:")
            imprimir_participacion(a_ofi)

    tabla = pd.concat(semanal, ignore_index=True)
    anual = [a for a in anual if not a.empty]
    anual = (pd.concat(anual, ignore_index=True) if anual else pd.DataFrame(
        {"ingrediente": [], "fuente": [], "anio": [], "tipo": [], "anio_base": [],
         "participacion": [], "cambio_pp": [], "marca": pd.Series([], dtype=bool)}))
    anual["anio_base"] = anual["anio_base"].astype("Int64")      # sin el .0 del concat

    print("\nÍNDICES: serie anterior (promedio entre filas) y oficial (por tipo de punto)")
    res, filas_idx = {}, []
    for code, meta in BASKETS.items():
        items = meta["items"]
        d, comp = calcular(df, ipc, items)
        r = resumen(d, meta, comp)
        nom_ofi = canasta({m: ofi_ing[m] for (_l, m, _q, _u) in items}, items)
        real_ofi = deflactar(nom_ofi, ipc)
        if not (_igual(nom_ofi, d["nominal"]) and _igual(real_ofi, d["real"])):
            raise RuntimeError(f"{meta['nombre']}: la oficial rearmada no es la de calcular()")
        ofi = metricas(d["real"])
        if (ofi["percentil"], ofi["z"]) != (r["percentil"], r["zscore"]):
            raise RuntimeError(f"{meta['nombre']}: percentil o z distinto de resumen()")
        nom_ant = canasta({m: ant_ing[m] for (_l, m, _q, _u) in items}, items)
        real_ant = deflactar(nom_ant, ipc)
        ant = metricas(real_ant)
        comparable = real_ant.dropna().index.equals(d["real"].dropna().index)
        antes, despues = brecha(real_ant, d["real"], CORTE)
        res[code] = {"nombre": meta["nombre"], "ant": ant, "ofi": ofi,
                     "comparable": comparable, "brecha": (antes, despues)}
        tabla_idx = pd.DataFrame({"nominal_anterior": nom_ant, "real_anterior": real_ant,
                                  "nominal_oficial": d["nominal"],
                                  "real_oficial": d["real"]}).dropna(how="all")
        tabla_idx.insert(0, "indice", code)
        filas_idx.append(tabla_idx.round(2).rename_axis("semana").reset_index())
        f_ = lambda x: "s/d" if x is None else f"{x:+.1f}%"  # noqa: E731
        print(f"  {meta['nombre']}: semana {ofi['semana']:%Y-%m-%d}; semanas {ant['n']} desde "
              f"{ant['inicio']:%Y-%m-%d} -> {ofi['n']} desde {ofi['inicio']:%Y-%m-%d}"
              f"{'' if comparable else ' (BASES DISTINTAS)'}; percentil {ant['percentil']} -> "
              f"{ofi['percentil']}; máximo {ant['maximo']:%Y-%m-%d} -> {ofi['maximo']:%Y-%m-%d}; "
              f"z {ant['z']} -> {ofi['z']}; oficial sobre anterior: antes del corte "
              f"{f_(antes)}, después {f_(despues)}")
        print(f"    oficial sobre anterior, por año (%): {_por_anio(d['real'], real_ant)}")
        if ant["maximo"] != ofi["maximo"]:
            for semana in (ant["maximo"], ofi["maximo"]):
                imprimir_semana(semana, items, ing)
        if publicado and code in publicado:
            p = publicado[code]
            igual = (p.get("percentil"), p.get("zscore"), p.get("n")) == (
                ant["percentil"], ant["z"], ant["n"])
            print(f"    publicado en carestia.cl: semana {p.get('fecha')}, percentil "
                  f"{p.get('percentil')}, z {p.get('zscore')}, {p.get('n')} semanas "
                  f"({'igual a la serie anterior de esta corrida' if igual else 'DISTINTO de la serie anterior de esta corrida'})")

    # el año cae dentro del período de algún índice que usa el ingrediente
    usa = {lab: [code for code, meta in BASKETS.items()
                 if match in [i[1] for i in meta["items"]]]
           for match, (lab, _u) in ingredientes().items()}
    anual["en_indice"] = [any(res[c]["ofi"]["inicio"].year <= a - 1 for c in usa[i])
                          for i, a in zip(anual["ingrediente"], anual["anio"])]
    marcados = anual[anual["marca"].astype(bool)].sort_values("cambio_pp", key=abs,
                                                              ascending=False)
    saltos_filas = marcados[marcados["fuente"] == "filas"]
    saltos = marcados[marcados["fuente"] == "oficial"]
    sin_tipo = [f"{lab} {y}" for lab, i in info.items() for y in i["sin_tipo_anios"]]
    if sin_tipo:
        print("\nAÑOS CON FILAS SIN TIPO DE PUNTO (estrato propio en la oficial): "
              + ", ".join(sin_tipo))
    for titulo, tabla_s in (("EN LAS FILAS DE ODEPA (serie anterior, contexto)", saltos_filas),
                            ("EN LA SERIE OFICIAL (criterio)", saltos)):
        print(f"\nSALTOS DE PARTICIPACIÓN {titulo}: más de 15 pp respecto del año anterior")
        for _, x in tabla_s.iterrows():
            print(f"  {x['ingrediente']} {x['anio']}: {x['tipo']} {x['cambio_pp']:+.1f} pp "
                  f"respecto de {x['anio_base']} (queda en {x['participacion']:.1f}%)"
                  f"{'' if x['en_indice'] else ', fuera del período de su índice'}")
        if tabla_s.empty:
            print("  ninguno")

    os.makedirs(carpeta, exist_ok=True)
    tabla.to_csv(os.path.join(carpeta, f"{PREFIJO}_semanal.csv"), index=False)
    anual.to_csv(os.path.join(carpeta, f"{PREFIJO}_anual.csv"), index=False)
    pd.concat(filas_idx, ignore_index=True).assign(
        semana=lambda x: x["semana"].dt.strftime("%Y-%m-%d")).to_csv(
        os.path.join(carpeta, f"{PREFIJO}_indices.csv"), index=False)
    print(f"\nEscritos {PREFIJO}_semanal.csv ({len(tabla)} filas), {PREFIJO}_anual.csv "
          f"({len(anual)} filas) y {PREFIJO}_indices.csv")

    c = criterio(saltos.to_dict("records"))
    rango = f"{df['fecha'].min():%Y} a {df['fecha'].max():%Y}"
    lineas = lineas_resumen(res, saltos, saltos_filas, info, c, rango)
    print("\n" + "\n".join(lineas))
    return {"indices": res, "saltos": saltos, "saltos_filas": saltos_filas, "info": info,
            "criterio": c, "semanal": tabla, "anual": anual, "resumen": lineas, "ing": ing}


def _salto(t: pd.DataFrame) -> str:
    x = t.iloc[0]
    return (f"{len(t)} casos en {t['ingrediente'].nunique()} ingredientes (mayor: "
            f"{x['ingrediente']} {x['anio']}, {x['tipo']} {x['cambio_pp']:+.1f} pp)")


def lineas_resumen(res: dict, saltos: pd.DataFrame, saltos_filas: pd.DataFrame, info: dict,
                   c: str, rango: str = "2008 a 2026") -> list:
    """El resumen del final del log, de máximo 15 líneas."""
    sem = sum(i["semanas"] for i in info.values())
    fuera = sum(i["fuera"] for i in info.values())
    un_tipo = [lab for lab, i in info.items() if len(i["estables"]) == 1]
    lineas = [
        "=" * 16 + " RESUMEN: serie anterior y oficial por tipo de punto " + "=" * 16,
        f"RM, semanal W-MON, {rango}. Oficial: promedio por tipo de punto y luego simple "
        f"entre los tipos estables (al menos {TIPO_ESTABLE:.0%} de las semanas antes y desde "
        f"{CORTE:%Y-%m-%d}).",
        f"Tipo estable sin precio: su último precio hasta {TIPO_FFILL} semanas; más, los que "
        f"hay ({fuera} de {sem} semanas-ingrediente con algún tipo estable fuera). Un solo "
        f"tipo estable: {', '.join(un_tipo) or 'ninguno'}.",
        "Índice: percentil vigente anterior/oficial (dif.) | semana del máximo real | z-score "
        "| semanas",
    ]
    for r in res.values():
        a, o = r["ant"], r["ofi"]
        lineas.append(f"{r['nombre']}: {a['percentil']}/{o['percentil']} "
                      f"({o['percentil'] - a['percentil']:+d}) | {a['maximo']:%Y-%m-%d}/"
                      f"{o['maximo']:%Y-%m-%d} | {a['z']}/{o['z']} | {a['n']}/{o['n']}"
                      + ("" if r["comparable"] else " (bases distintas)"))
    lineas.append("Saltos de más de 15 pp en las filas de ODEPA (contexto): "
                  + (_salto(saltos_filas) if len(saltos_filas) else "ninguno"))
    lineas.append("Saltos de más de 15 pp en la serie oficial (criterio): "
                  + (_salto(saltos) if len(saltos) else "ninguno"))
    lineas.append(f"CRITERIO DE PARTICIPACIÓN EN LA SERIE OFICIAL: {c}")
    if len(lineas) > MAX_RESUMEN:
        raise RuntimeError(f"el resumen tiene {len(lineas)} líneas (máximo {MAX_RESUMEN})")
    return lineas


def leer_publicado() -> dict:
    """Los 4 índices de indices.json en carestia.cl, para contrastar con la
    serie anterior de esta corrida. Vacío si no se puede leer."""
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
    t = tipo_punto(df)
    mixtos = sorted(set(df.loc[t == SIN_TIPO, "ProductoBase"])
                    & set(df.loc[t != SIN_TIPO, "ProductoBase"]))
    print(f"Filas RM sin tipo de punto: {int((t == SIN_TIPO).sum())} de {len(df)}; productos "
          f"con filas con y sin tipo: {', '.join(mixtos) or 'ninguno'}")
    diagnostico(df, ipc, ".", leer_publicado())
    ruta = f"{PREFIJO}_mayores.json"
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            detalle_productos(df, json.load(fh))


def filas_producto(df: pd.DataFrame, slug: str) -> pd.DataFrame:
    """Las filas de un producto del catálogo por su slug, como las agrupa
    series_productos: por el texto de match si es de una canasta, o por su
    nombre sin espacios ni mayúsculas."""
    import indices as ind
    for match, (lab, _u) in ingredientes().items():
        if ind._slug(lab) == slug:
            return df[df["ProductoBase"].str.contains(match, case=False, na=False)]
    nombre = df["ProductoBase"].astype(str).str.replace(r"\s+", " ", regex=True)
    return df[nombre.map(ind._slug) == slug]


def detalle_productos(df: pd.DataFrame, productos: list) -> None:
    """Para los productos del catálogo que más cambian: tipos estables,
    semanas con precio de cada tipo antes y desde el corte, y el precio
    nominal de cada tipo y de las dos series en la semana comparada."""
    import indices as ind
    print("\nPRODUCTOS DEL CATÁLOGO CON MAYOR CAMBIO: por qué cambian (pesos nominales)")
    for x in productos:
        sub = ind.de_su_unidad(filas_producto(df, x["slug"]))
        if sub.empty:
            print(f"  {x['slug']}: sin filas")
            continue
        t = por_tipo(sub)
        est, resp = ind._estables(t)
        semana = pd.Timestamp(x["semana"])
        hay = t.notna()[t.notna().any(axis=1)]
        antes, desde = hay[hay.index < CORTE], hay[hay.index >= CORTE]
        ant = sub.groupby("fecha")["Precio promedio"].mean().resample("W-MON").mean()
        ofi = ind.precio_oficial(sub)
        filas = sub.assign(_t=tipo_punto(sub), _s=semana_de(sub["fecha"]))
        n = filas[filas["_s"] == semana].groupby("_t").size()

        def pct(h, c):
            return "s/s" if h.empty else f"{100 * h[c].mean():.0f}%"
        print(f"  {x['slug']}: estables {est}{' (respaldo)' if resp else ''}; en {x['semana']}: "
              f"anterior {ant.get(semana, np.nan):,.0f}, oficial {ofi.get(semana, np.nan):,.0f}")
        print("    " + "; ".join(
            f"{c} {pct(antes, c)} / {pct(desde, c)}, {t[c].get(semana, np.nan):,.0f} "
            f"({int(n.get(c, 0))} filas){'' if c in est else ', no estable'}" for c in t.columns))


# ---------------- comparación con el sitio publicado ----------------
CAMPOS = ("costo_pesos_hoy", "percentil", "veredicto", "percentil_temporada",
          "semanas_historia")


def _ultimo(p: dict):
    """(semana, valor) del último precio real con dato de un producto."""
    v = p.get("v") or []
    i = max((k for k, x in enumerate(v) if x is not None), default=None)
    if i is None:
        return None, None
    return (pd.Timestamp(p["t0"]) + pd.Timedelta(weeks=i)).strftime("%Y-%m-%d"), v[i]


def _en(p: dict, semana: str):
    """El precio real de un producto en una semana (aaaa-mm-dd), o None."""
    i = (pd.Timestamp(semana) - pd.Timestamp(p["t0"])).days // 7
    v = p.get("v") or []
    return v[i] if 0 <= i < len(v) else None


def comparar(nuevo: dict, resumen_sitio: dict, indices_sitio: dict) -> dict:
    """La tabla antes y después de los 4 índices (CAMPOS, del resumen.json
    publicado contra el que armaría build_site con el indices.json nuevo) y
    los cambios del catálogo contra el indices.json publicado, en la última
    semana del sitio. Si la semana o el mes del IPC no son los del sitio, lo
    dice: entonces la tabla mezcla el cambio de método con la semana nueva o
    con el deflactor. semanas_historia tiene que ser la del sitio más las
    semanas que avanzó la semana (como en validar.py). Imprime y devuelve
    {"semanas_iguales", "avance", "entran", "salen", "retroceden", "cambios"}."""
    import validar
    r_nuevo = validar.resumen_desde_indices(nuevo)
    s_sitio, s_nuevo = resumen_sitio.get("semana"), r_nuevo["semana"]
    avance = (pd.Timestamp(s_nuevo) - pd.Timestamp(s_sitio)).days // 7
    ipc_sitio, ipc_nuevo = indices_sitio.get("ipc_mes"), nuevo.get("ipc_mes")
    print("\nÍNDICES: sitio publicado -> metodología por tipo de punto")
    print(f"Semana: {s_sitio} -> {s_nuevo}; IPC: {ipc_sitio} -> {ipc_nuevo}")
    if avance:
        print(f"  AVISO: la semana avanzó {avance}; la tabla mezcla el cambio de método con "
              "la semana nueva")
    if ipc_sitio != ipc_nuevo:
        print("  AVISO: otro mes de IPC; los precios en pesos de hoy cambian también por el "
              "deflactor")
    print("| Índice | " + " | ".join(CAMPOS) + " |")
    print("|---|" + "---|" * len(CAMPOS))
    iguales = True
    for code, n in r_nuevo["indices"].items():
        a = resumen_sitio["indices"].get(code, {})
        celdas = []
        for c in CAMPOS:
            x, y = a.get(c), n.get(c)
            celdas.append(f"{x} -> {y}" if x != y else f"{y} (igual)")
        iguales &= (a.get("semanas_historia") is not None
                    and n.get("semanas_historia") == a["semanas_historia"] + avance)
        print(f"| {n['nombre']} | " + " | ".join(celdas) + " |")
    print("semanas_historia de los 4 índices " + ("igual a la del sitio" if not avance else
          f"igual a la del sitio más {avance}") + f": {'sí' if iguales else 'NO'}")

    viejo, prod = indices_sitio.get("productos", {}), nuevo.get("productos", {})
    entran, salen = sorted(set(prod) - set(viejo)), sorted(set(viejo) - set(prod))
    print(f"\nCATÁLOGO: {len(viejo)} productos en el sitio -> {len(prod)}")
    print(f"  entran: {', '.join(entran) or 'ninguno'}")
    print(f"  salen: {', '.join(salen) or 'ninguno'}")
    cambios, retroceden = [], []
    for slug in sorted(set(prod) & set(viejo)):
        sv, xv = _ultimo(viejo[slug])
        sn, _xn = _ultimo(prod[slug])
        if sv and (sn is None or sn < sv):
            retroceden.append(f"{slug} ({sv} a {sn})")
        xn = _en(prod[slug], sv) if sv else None
        if xv and xn:
            cambios.append((abs(xn / xv - 1), slug, sv, xv, xn))
    print(f"  última semana con precio que retrocede: {', '.join(retroceden) or 'ninguno'}")
    cambios.sort(reverse=True)
    print("  los 10 con mayor cambio en su último precio real (misma semana del sitio):")
    print("| Producto | unidad | semana | sitio | nuevo | cambio |")
    print("|---|---|---|---|---|---|")
    for _d, slug, sv, xv, xn in cambios[:10]:
        print(f"| {slug} | {prod[slug]['unidad']} | {sv} | {xv:,} | {xn:,} | "
              f"{(xn / xv - 1) * 100:+.1f}% |")
    sin_cambio = sum(1 for c in cambios if c[0] == 0)
    print(f"  {sin_cambio} de {len(cambios)} productos comunes con el mismo último precio")
    with open(f"{PREFIJO}_mayores.json", "w", encoding="utf-8") as fh:
        json.dump([{"slug": c[1], "semana": c[2]} for c in cambios[:10]], fh)
    return {"semanas_iguales": iguales, "avance": avance, "entran": entran, "salen": salen,
            "retroceden": retroceden, "productos": len(prod), "cambios": cambios}


def main_comparar(ruta: str) -> None:
    import validar
    with open(ruta, encoding="utf-8") as fh:
        nuevo = json.load(fh)
    rs, url_r, err_r = validar.descargar_json(validar.URLS_RESUMEN, validar._forma_resumen)
    ix, url_i, err_i = validar.descargar_json(validar.URLS_INDICES, validar._forma_indices)
    if rs is None or ix is None:
        raise RuntimeError("no se pudo bajar el sitio publicado: " + "; ".join(err_r + err_i))
    print(f"Referencia: {url_r} y {url_i}")
    out = comparar(nuevo, rs, ix)
    if not out["semanas_iguales"]:
        raise SystemExit("semanas_historia no cuadra con la del sitio: no seguir")


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


def df_prueba(huecos: dict = None, sin_cambio: bool = False) -> pd.DataFrame:
    """Filas como las de cargar_odepa para los 19 ingredientes. Cada tipo
    tiene un precio fijo relativo a la feria (MULT) por una tendencia común,
    así que la oficial no salta en el corte y la anterior sí. huecos:
    {match: [semanas sin filas de supermercado]}."""
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
                reg.append({"ProductoBase": prod, "Precio promedio": p, "Precio minimo": p * 0.9,
                            "Precio maximo": p * 1.1, "Unidad": unidad, "Grupo": "Prueba",
                            "fecha": semana, "region_rm": True, "Punto": punto})
    return pd.DataFrame(reg)


def prueba() -> None:
    """Propiedades del diagnóstico con datos sintéticos, sin red."""
    import contextlib
    import io
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
                                       "anterior", "oficial"]
    t = out["semanal"]
    tom = t[t["ingrediente"] == "Tomate"].set_index("semana")
    tend = {f"{s:%Y-%m-%d}": 1 + 0.002 * i for i, s in enumerate(SEMANAS_PRUEBA)}
    esperado = 1000 * tom.index.map(tend).to_numpy() * (1.0 + 1.3) / 2
    # la oficial no ve el cambio de muestra: feria y supermercado, mitad y mitad
    assert np.allclose(tom["oficial"].to_numpy(float), esperado, atol=0.01)
    # la anterior sí: 1 de 4 filas en supermercado antes, 4 de 7 después (y la en línea)
    antes, despues = tom.loc["2012-12-31"], tom.loc["2013-03-04"]
    assert np.isclose(antes["anterior"], 1000 * tend["2012-12-31"] * (3 + 1.3) / 4, atol=0.01)
    assert np.isclose(despues["anterior"], 1000 * tend["2013-03-04"] * (3 + 4 * 1.3) / 7,
                      atol=0.01)
    assert antes["filas"] == 4 and despues["puntos"] == 7
    assert despues["mezcla"] == "Feria libre=0.429;Supermercado=0.571"
    # la en línea (2015 y 2016) no llega al 80% de las semanas desde el corte;
    # Asado de tira y Huevos parten después del corte: 80% de todas sus semanas
    for lab in ("Tomate", "Huevos", "Asado de tira", "Palta"):
        assert out["info"][lab]["estables"] == ["Feria libre", "Supermercado"], lab
    # huecos: 3 semanas se cubren con el último precio; de 6, las 2 últimas sin él
    pal = t[t["ingrediente"] == "Palta"].set_index("semana")
    corto = [f"{s:%Y-%m-%d}" for s in hueco_corto]
    largo = [f"{s:%Y-%m-%d}" for s in hueco_largo]
    assert (pal.loc[corto + largo[:4], "tipos_en_promedio"] == 2).all()
    assert (pal.loc[corto + largo[:4], "tipos_con_precio_propio"] == 1).all()
    assert (pal.loc[largo[4:], "tipos_en_promedio"] == 1).all()
    assert np.allclose(pal.loc[largo[4:], "oficial"].to_numpy(float),
                       [round(3000 * tend[s], 2) for s in largo[4:]])
    assert out["info"]["Palta"]["arrastre"] == 7 and out["info"]["Palta"]["fuera"] == 2
    # participación en las filas: el supermercado salta en 2013 (25% a 54%);
    # en la oficial, mitad y mitad todos los años (la palta, casi: 2 semanas
    # de 2015 van solo con la feria)
    a = out["anual"]
    filas_tom = a[(a["ingrediente"] == "Tomate") & (a["fuente"] == "filas") & a["marca"]]
    assert set(zip(filas_tom["anio"], filas_tom["tipo"])) == {(2013, "Feria libre"),
                                                             (2013, "Supermercado")}
    ofi = a[a["fuente"] == "oficial"]
    assert set(ofi["tipo"]) == {"Feria libre", "Supermercado"}
    assert np.allclose(ofi[ofi["ingrediente"] != "Palta"]["participacion"], 50.0)
    assert out["saltos"].empty and out["criterio"] == "CUMPLE"
    assert not out["saltos_filas"].empty
    # los índices: la anterior sube en el corte (más supermercados), así que
    # la oficial queda sobre ella antes y bajo ella después
    ens = out["indices"]["ensalada"]
    assert ens["comparable"] and ens["brecha"][0] > 0 > ens["brecha"][1]
    assert all(r["comparable"] for r in out["indices"].values())
    assert len(out["resumen"]) <= MAX_RESUMEN

    # la composición de una semana, también con el supermercado ausente
    texto = io.StringIO()
    with contextlib.redirect_stdout(texto):
        for semana in (SEMANAS_PRUEBA[200], hueco_largo[-1]):
            imprimir_semana(semana, BASKETS["asado"]["items"], out["ing"])
    texto = texto.getvalue()
    # semana 200 (tendencia 1,4): palta 4.200 en feria y 5.460 en supermercado
    assert ("Palta: anterior 4,920, oficial 4,830 | Feria libre 4,200 (3 filas, "
            "mediana vecina 4,200) | Supermercado 5,460 (4 filas" in texto)
    # en el hueco largo la palta no trae supermercado y la oficial es la feria
    palta = [x for x in texto.splitlines() if "Palta:" in x][-1]
    assert "oficial 4,950 | Feria libre 4,950" in palta
    assert "Supermercado en Línea 7,920 (1 filas, no estable" in palta

    # un tipo estable (81,7% de las semanas antes del corte) sin precio en
    # 30 semanas de 2011 pesa 75% ese año en la oficial: marca 2011 y 2012
    huecos = {"Tomate": list(SEMANAS_PRUEBA[(SEMANAS_PRUEBA.year == 2011)][:30])}
    sal = diagnostico(df_prueba(huecos), ipc, tempfile.mkdtemp())
    assert sal["criterio"] == "NO CUMPLE"
    assert set(sal["saltos"]["ingrediente"]) == {"Tomate"}
    assert set(sal["saltos"]["anio"]) == {2011, 2012}

    # sin cambio de muestra: las dos series son la misma
    rob = diagnostico(df_prueba(sin_cambio=True), ipc, tempfile.mkdtemp())
    assert rob["saltos"].empty and rob["saltos_filas"].empty and rob["criterio"] == "CUMPLE"
    for r in rob["indices"].values():
        assert (r["ant"]["percentil"], r["ant"]["maximo"]) == (r["ofi"]["percentil"],
                                                               r["ofi"]["maximo"])

    # ninguna fila con tipo: la oficial es la anterior (un solo estrato)
    nada = df_prueba(sin_cambio=True).assign(Punto="")
    sin_tipo = diagnostico(nada, ipc, tempfile.mkdtemp())
    assert all(i["estables"] == [SIN_TIPO] for i in sin_tipo["info"].values())
    assert np.allclose(sin_tipo["semanal"]["anterior"], sin_tipo["semanal"]["oficial"])

    # la comparación con el sitio: misma semana y mismos conteos (en una
    # carpeta temporal: comparar deja ahí la lista de los mayores cambios)
    import indices as ind
    aqui = os.getcwd()
    os.chdir(tempfile.mkdtemp())
    with contextlib.redirect_stdout(io.StringIO()):
        nuevo = {"indices": {}, "productos": ind.series_productos(df, ipc)}
        for code, meta in BASKETS.items():
            d, comp = calcular(df, ipc, meta["items"])
            nuevo["indices"][code] = resumen(d, meta, comp)
        import validar
        sitio = validar.resumen_desde_indices(nuevo)
        viejo = json.loads(json.dumps({"productos": nuevo["productos"]}))
        viejo["productos"]["tomate"]["v"][-1] += 100
        viejo["productos"]["borrado"] = viejo["productos"].pop("pera")
        cmp_ = comparar(nuevo, sitio, viejo)
    assert cmp_["semanas_iguales"] and cmp_["avance"] == 0 and cmp_["entran"] == ["pera"]
    assert cmp_["salen"] == ["borrado"] and cmp_["cambios"][0][1] == "tomate"
    assert not cmp_["retroceden"] and sum(1 for c in cmp_["cambios"] if c[0]) == 1
    # el sitio va una semana atrás con el mismo método: cuadra con avance 1 y
    # el último precio se compara en la semana del sitio
    with contextlib.redirect_stdout(io.StringIO()):
        atras = df[df["fecha"] < df["fecha"].max()]
        viejo = {"indices": {}, "productos": ind.series_productos(atras, ipc)}
        for code, meta in BASKETS.items():
            d, comp = calcular(atras, ipc, meta["items"])
            viejo["indices"][code] = resumen(d, meta, comp)
        sitio = validar.resumen_desde_indices(viejo)
        cmp_ = comparar(nuevo, sitio, viejo)
        sitio["indices"]["fruta"]["semanas_historia"] -= 1
        mal = comparar(nuevo, sitio, viejo)
    assert os.path.exists(f"{PREFIJO}_mayores.json")
    os.chdir(aqui)
    assert cmp_["semanas_iguales"] and cmp_["avance"] == 1 and not cmp_["retroceden"]
    assert not mal["semanas_iguales"]

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
    elif "--comparar" in sys.argv[1:]:
        main_comparar(sys.argv[sys.argv.index("--comparar") + 1])
    else:
        main()

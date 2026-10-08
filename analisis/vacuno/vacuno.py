"""
vacuno.py - las cifras de la nota de vacuno, desde el indices.json del sitio
============================================================================
Segundo paso (ver README.md). Lee datos_crudos/sitio/indices.json, el que
publica carestia.cl, y para cada corte del grupo "Carne bovina" del catálogo
(Región Metropolitana) calcula, con las mismas reglas del sitio:

- el precio de esta semana, ajustado por inflación (el número grande de la
  ficha: en su semana, ajustado y de la época son el mismo);
- frente a toda su historia: en qué parte de sus semanas fue más barato (la
  frase "más caro que en el X% de las semanas" de la ficha) y el percentil
  del catálogo y la portada (semanas con precio menor o igual);
- frente al mismo mes de los 10 años anteriores (comparar_temporada de
  indices.py: "más caro que en N de los últimos 10 septiembres");
- la variación ajustada por inflación a un año (52 semanas, la columna
  "1 año" de la portada);
- si está en el 5% más caro de su historia: más caro que en al menos el 95%
  de sus semanas (sin redondear);
- si está en su precio más alto en al menos 10 años: su precio supera al de
  cada semana de los 10 años anteriores. Se afirma solo si supera al máximo
  anterior de esa ventana en más de 1% (MARGEN), para que una revisión del
  IPC o el IPC del mes siguiente no lo den vuelta.

Escribe resultados/series_vacuno.json (las series usadas, para repetir las
cuentas sin red), resultados/cortes.csv y resultados/resumen.json.

Uso: python vacuno.py   (después de descargar.py)
"""
import csv
import datetime
import hashlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUDOS = os.path.join(AQUI, "datos_crudos")
RESULTADOS = os.path.join(AQUI, "resultados")
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))
from indices import comparar_temporada, promedios_mes  # noqa: E402

GRUPO = "Carne bovina"
TOP = 95.0          # el 5% más caro: más caro que en al menos el 95% de sus semanas
ANIOS = 10          # "su precio más alto en al menos 10 años"
MARGEN = 1.0        # y solo si supera al máximo anterior en más de 1%
SEMANAS_ANIO = 52   # la variación a un año del catálogo (variacion_52s_pct)


# ---------------- las reglas, sobre una serie compacta (t0 + v) ----------------
def fechas(p: dict) -> list:
    t0 = datetime.date.fromisoformat(p["t0"])
    return [t0 + datetime.timedelta(weeks=j) for j in range(len(p["v"]))]


def ultima(v: list) -> int:
    """Índice de la última semana con precio."""
    return max(j for j, x in enumerate(v) if x is not None)


def historia(v: list, i: int) -> dict:
    """La semana i frente a todas las semanas con precio de la serie (ella
    incluida, como en build_site.py): cuántas fueron más baratas, cuántas
    más caras y cuántas hay. 'ficha' es el % de la frase de la ficha (más
    caro que en el X% de las semanas: pct_semanas de build_site.py, truncado
    y 100 solo si supera a todas las demás) y 'catalogo', el percentil del
    catálogo y la portada (semanas con precio menor o igual, truncado:
    percentil_catalogo)."""
    vals = [x for x in v if x is not None]
    ult, n = v[i], len(vals)
    debajo = sum(1 for x in vals if x < ult)
    encima = sum(1 for x in vals if x > ult)
    igual = sum(1 for x in vals if x <= ult)
    ficha = 100 if n > 1 and debajo == n - 1 else 100 * debajo // n
    return {"n": n, "debajo": debajo, "encima": encima,
            "pct_debajo": 100 * debajo / n, "pct_encima": 100 * encima / n,
            "ficha": ficha, "catalogo": 100 * igual // n}


def en_top(h: dict, top: float = TOP) -> bool:
    """En el 5% más caro de su historia: más caro que en al menos el 95% de
    sus semanas, sin redondear (en enteros, sin el ruido de la división)."""
    return 100 * h["debajo"] >= top * h["n"]


def variacion_anual(v: list, i: int, k: int = SEMANAS_ANIO):
    """Variación (%) contra k semanas antes, sin redondear; None si esa
    semana no tiene precio (como variacion_52s_pct del catálogo)."""
    j = i - k
    return (v[i] / v[j] - 1) * 100 if j >= 0 and v[j] else None


def hace_anios(f: datetime.date, anios: int) -> datetime.date:
    try:
        return f.replace(year=f.year - anios)
    except ValueError:                       # 29 de febrero
        return f.replace(year=f.year - anios, day=28)


def maximo(fs: list, v: list, i: int, anios: int = ANIOS, margen: float = MARGEN) -> dict:
    """La semana i frente a las semanas con precio de los 'anios' años
    anteriores (desde la semana que contiene el mismo día de hace 'anios'
    años, sin contar la semana i). 'margen_pct' es cuánto supera (o le falta, si es negativo) al
    máximo anterior de esa ventana; 'cubre' dice si la serie llega al
    comienzo de la ventana (si no, no se puede hablar de 10 años);
    'es_maximo', si es el precio más alto de la ventana, y 'se_afirma', si
    además lo supera en más de 'margen' %. 'ultima_igual_o_mayor' es la
    última semana anterior con un precio igual o mayor (None si no hay en
    toda la serie) y 'margen_total_pct', lo mismo que 'margen_pct' contra
    toda la serie anterior."""
    desde = hace_anios(fs[i], anios)
    con = [j for j, x in enumerate(v) if x is not None and j < i]
    # la semana que contiene el día de hace 'anios' años entra en la ventana,
    # y la serie cubre la ventana si parte ese día o antes
    ventana = [j for j in con if fs[j] + datetime.timedelta(days=6) >= desde]
    jmax = max(ventana, key=lambda j: (v[j], fs[j]))
    mayores = [j for j in con if v[j] >= v[i]]
    cubre = bool(con) and fs[con[0]] <= desde
    m = (v[i] / v[jmax] - 1) * 100
    total = max(v[j] for j in con)
    # sin restar: con precios enteros, (10100 / 10000 - 1) * 100 da
    # 1,0000000000000009 y pasaría por "más de 1%"
    return {"desde": desde, "max_anterior": v[jmax], "semana_max_anterior": fs[jmax],
            "margen_pct": m, "cubre": cubre, "es_maximo": cubre and v[i] > v[jmax],
            "se_afirma": cubre and v[i] * 100 > v[jmax] * (100 + margen),
            "ultima_igual_o_mayor": fs[mayores[-1]] if mayores else None,
            "margen_total_pct": (v[i] / total - 1) * 100}


def maximo_mensual(fs: list, v: list, i: int, anios: int = ANIOS,
                   margen: float = MARGEN) -> dict:
    """Otra medida, que el sitio no muestra: el promedio del mes de la semana
    i (sus semanas con precio hasta la i, cada una en el mes de su lunes)
    frente al promedio de cada uno de los 'anios' x 12 meses anteriores. Solo
    para la robustez de B."""
    prom = promedios_mes(fs[:i + 1], v[:i + 1])
    mes = (fs[i].year, fs[i].month)
    antes = {k: x for k, x in prom.items() if (mes[0] - anios, mes[1]) <= k < mes}
    kmax = max(antes, key=antes.get)
    return {"mes_max_anterior": kmax, "margen_pct": (prom[mes] / antes[kmax] - 1) * 100,
            "se_afirma": prom[mes] * 100 > antes[kmax] * (100 + margen)}


def propio(p: dict, j: int) -> bool:
    """Si la semana j tiene precio propio y no uno arrastrado por el ffill de
    indices.py: las semanas propias traen su rango (dato_propio de
    build_site.py)."""
    lo, hi = p.get("min"), p.get("max")
    if not lo or not hi:
        return p["v"][j] is not None
    return p["v"][j] is not None and (lo[j] is not None or hi[j] is not None)


def cifras(p: dict) -> dict:
    """Todas las cifras de un corte en su última semana con precio."""
    fs, v = fechas(p), p["v"]
    i = ultima(v)
    h = historia(v, i)
    t = comparar_temporada(fs, v, i)
    va = variacion_anual(v, i)
    mx = maximo(fs, v, i)
    return {"semana": fs[i], "precio": v[i], "desde": fs[[j for j, x in enumerate(v)
                                                          if x is not None][0]],
            "historia": h, "top": en_top(h), "temporada": t,
            "variacion_anual": va,
            "semana_anio_antes": fs[i - SEMANAS_ANIO] if i >= SEMANAS_ANIO else None,
            "anio_antes_propio": propio(p, i - SEMANAS_ANIO) if i >= SEMANAS_ANIO else None,
            "propio": propio(p, i), "maximo": mx}


# ---------------- formato de las cifras en el texto ----------------
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MESES_PLURAL = ["eneros", "febreros", "marzos", "abriles", "mayos", "junios",
                "julios", "agostos", "septiembres", "octubres", "noviembres",
                "diciembres"]


def clp(x: float) -> str:
    return "$" + f"{int(round(x)):,}".replace(",", ".")


def pct(x: float, decimales: int = 1, signo: bool = True) -> str:
    s = f"{x:+.{decimales}f}" if signo else f"{x:.{decimales}f}"
    return s.replace(".", ",") + "%"


def fecha_larga(f: datetime.date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


# ---------------- lectura y salida ----------------
def cargar(ruta: str = None) -> tuple:
    """(indices.json, su sha256) de la foto del sitio."""
    ruta = ruta or os.path.join(CRUDOS, "sitio", "indices.json")
    with open(ruta, "rb") as fh:
        crudo = fh.read()
    return json.loads(crudo), hashlib.sha256(crudo).hexdigest()


def cortes(data: dict) -> dict:
    """Los productos del grupo Carne bovina, por clave."""
    return {k: p for k, p in sorted(data["productos"].items()) if p.get("grupo") == GRUPO}


def max_semana(prods: dict) -> str:
    """La semana más reciente con precio entre los cortes (aaaa-mm-dd)."""
    return max(fechas(p)[ultima(p["v"])] for p in prods.values()).isoformat()


def series_vacuno(data: dict, sha: str) -> dict:
    """Lo que se guarda en resultados/series_vacuno.json: la serie ajustada
    de cada corte (t0, v) y los días sin precio propio, más lo necesario para
    saber de qué indices.json salió."""
    out = {"fuente": "https://carestia.cl/indices.json", "sha256": sha,
           "generado": data["generado"], "ipc_mes": data["ipc_mes"], "productos": {}}
    for k, p in cortes(data).items():
        out["productos"][k] = {"label": p["label"], "unidad": p["unidad"], "grupo": p["grupo"],
                               "t0": p["t0"], "v": p["v"],
                               "sin_rango": [j for j in range(len(p["v"]))
                                             if p["v"][j] is not None and not propio(p, j)]}
    return out


def desde_series(s: dict) -> dict:
    """Reconstruye min/max mínimos a partir de 'sin_rango' para que propio()
    dé lo mismo que con el indices.json completo."""
    out = {}
    for k, p in s["productos"].items():
        sin = set(p["sin_rango"])
        rango = [None if (x is None or j in sin) else x for j, x in enumerate(p["v"])]
        out[k] = {**p, "min": rango, "max": rango}
    return out


COLUMNAS = ["clave", "corte", "semana", "precio", "desde", "semanas", "pct_mas_barato",
            "ficha_pct", "percentil_catalogo", "top5", "mes", "anios_mes", "debajo_mes",
            "zona_mes", "variacion_anual", "semana_anio_antes", "max_10_anios",
            "semana_max_10_anios", "margen_max_10", "maximo_10_anios", "se_afirma_maximo",
            "ultima_igual_o_mayor", "margen_toda_la_serie"]


def fila(k: str, p: dict, c: dict) -> dict:
    h, t, mx = c["historia"], c["temporada"], c["maximo"]
    return {
        "clave": k, "corte": p["label"], "semana": c["semana"].isoformat(),
        "precio": c["precio"], "desde": c["desde"].isoformat(), "semanas": h["n"],
        "pct_mas_barato": round(h["pct_debajo"], 2), "ficha_pct": h["ficha"],
        "percentil_catalogo": h["catalogo"], "top5": int(c["top"]),
        "mes": t["mes"] if t else "", "anios_mes": t["anios"] if t else "",
        "debajo_mes": t["debajo"] if t else "", "zona_mes": t["zona"] if t else "",
        "variacion_anual": "" if c["variacion_anual"] is None else round(c["variacion_anual"], 1),
        "semana_anio_antes": c["semana_anio_antes"].isoformat() if c["semana_anio_antes"] else "",
        "max_10_anios": mx["max_anterior"],
        "semana_max_10_anios": mx["semana_max_anterior"].isoformat(),
        "margen_max_10": round(mx["margen_pct"], 2), "maximo_10_anios": int(mx["es_maximo"]),
        "se_afirma_maximo": int(mx["se_afirma"]),
        "ultima_igual_o_mayor": (mx["ultima_igual_o_mayor"].isoformat()
                                 if mx["ultima_igual_o_mayor"] else ""),
        "margen_toda_la_serie": round(mx["margen_total_pct"], 2),
    }


def margen_mismo_mes(fs: list, v: list, i: int):
    """Cuánto (%) supera el precio de la semana i al promedio más alto de su
    mes en los 10 años anteriores (los que usa comparar_temporada); None sin
    temporada."""
    prom = promedios_mes(fs, v)
    f = fs[i]
    antes = [prom[(a, f.month)] for a in range(f.year - 10, f.year) if (a, f.month) in prom]
    return (v[i] / max(antes) - 1) * 100 if len(antes) >= 5 else None


def contexto(prods: dict, cs: dict) -> dict:
    """Las cifras de contexto que cita el informe, para que no salgan de una
    cuenta a mano: el conteo de A en las últimas 4 semanas (cada una con su
    historia hasta ella), cuántos bajaron esta semana (como la portada:
    variación semanal redondeada a un decimal bajo 0), los cortes a menos de
    1% de su máximo de 10 años, si todos tuvieron una semana más cara en el
    año de esta semana, el corte que entra más justo al "10 de 10" del mismo
    mes y, del asado de tira, el promedio de su mes frente al mismo mes del
    año anterior."""
    semanas = []
    for atras in range(3, -1, -1):
        n, fecha = 0, None
        for p in prods.values():
            i = ultima(p["v"]) - atras
            if p["v"][i] is None:
                continue
            n += en_top(historia(p["v"][:i + 1], i))
            fecha = fechas(p)[i]
        semanas.append({"semana": fecha.isoformat(), "top5": n})
    bajaron, cerca, mas_cara, justo = 0, [], True, None
    for k, p in prods.items():
        fs, v, i = fechas(p), p["v"], ultima(p["v"])
        if v[i - 1] and round((v[i] / v[i - 1] - 1) * 100, 1) < 0:
            bajaron += 1
        m = cs[k]["maximo"]["margen_pct"]
        if -1 < m <= 0:
            cerca.append((round(m, 2), p["label"]))
        anio = fs[i].year
        mas_cara &= any(x is not None and x > v[i] and fs[j].year == anio
                        for j, x in enumerate(v[:i]))
        t = cs[k]["temporada"]
        if t and t["debajo"] == t["anios"]:
            mm = margen_mismo_mes(fs, v, i)
            if justo is None or mm < justo[0]:
                justo = (mm, p["label"])
    a = prods["asado_de_tira"]
    fs, v, i = fechas(a), a["v"], ultima(a["v"])
    prom = promedios_mes(fs, v)
    mes = (fs[i].year, fs[i].month)
    return {
        "top5_por_semana": semanas,
        "bajaron_esta_semana": bajaron,
        "a_menos_de_1_de_su_maximo": [lab for _, lab in sorted(cerca, reverse=True)],
        "todos_con_una_semana_mas_cara_este_anio": mas_cara,
        "mismo_mes_entra_mas_justo": {"corte": justo[1], "margen_pct": round(justo[0], 3)},
        "asado_de_tira_mes_sobre_mes_del_anio_anterior_pct":
            round((prom[mes] / prom[(mes[0] - 1, mes[1])] - 1) * 100, 1),
    }


def resumen(data: dict, sha: str, prods: dict) -> dict:
    cs = {k: cifras(p) for k, p in prods.items()}
    semanas = {c["semana"] for c in cs.values()}
    top = [prods[k]["label"] for k, c in cs.items() if c["top"]]
    afirma = [prods[k]["label"] for k, c in cs.items() if c["maximo"]["se_afirma"]]
    sin_margen = [prods[k]["label"] for k, c in cs.items()
                  if c["maximo"]["es_maximo"] and not c["maximo"]["se_afirma"]]
    meses_max = {}
    for c in cs.values():
        m = c["maximo"]["semana_max_anterior"].strftime("%Y-%m")
        meses_max[m] = meses_max.get(m, 0) + 1
    a = cs["asado_de_tira"]
    return {
        "fuente": "https://carestia.cl/indices.json", "sha256": sha,
        "generado": data["generado"], "ipc_mes": data["ipc_mes"],
        "semana": max(semanas).isoformat(), "todas_en_la_semana": len(semanas) == 1,
        "cortes": len(cs),
        "A": {"top5": len(top), "de": len(cs), "cortes": top},
        "B": {"se_afirman": afirma, "maximo_sin_margen": sin_margen},
        "C": {"precio": a["precio"], "variacion_anual": round(a["variacion_anual"], 1),
              "semana": a["semana"].isoformat(),
              "semana_anio_antes": a["semana_anio_antes"].isoformat(),
              "anio_antes_propio": a["anio_antes_propio"]},
        "mes_del_maximo_de_10_anios": dict(sorted(meses_max.items())),
        "mismo_mes_10_de_10": sum(1 for c in cs.values()
                                  if c["temporada"] and c["temporada"]["debajo"] == 10),
        "contexto": contexto(prods, cs),
    }


def main() -> None:
    data, sha = cargar()
    prods = cortes(data)
    os.makedirs(RESULTADOS, exist_ok=True)
    with open(os.path.join(RESULTADOS, "series_vacuno.json"), "w", encoding="utf-8") as fh:
        json.dump(series_vacuno(data, sha), fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(RESULTADOS, "cortes.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader()
        for k, p in prods.items():
            w.writerow(fila(k, p, cifras(p)))
    r = resumen(data, sha, prods)
    with open(os.path.join(RESULTADOS, "resumen.json"), "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
    print(f"indices.json generado el {r['generado']} (sha256 {sha[:12]}), "
          f"IPC de {r['ipc_mes']}, semana del {r['semana']}, {r['cortes']} cortes")
    print(f"A. En el 5% más caro de su historia: {r['A']['top5']} de {r['A']['de']}")
    print(f"B. En su precio más alto en al menos {ANIOS} años, con más de {MARGEN:g}% "
          f"sobre el máximo anterior: {', '.join(r['B']['se_afirman']) or 'ninguno'}"
          f" (máximo sin el margen: {', '.join(r['B']['maximo_sin_margen']) or 'ninguno'})")
    print(f"C. Asado de tira: {clp(r['C']['precio'])} por kilo, "
          f"{pct(r['C']['variacion_anual'])} a un año")


if __name__ == "__main__":
    main()

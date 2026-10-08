"""
verificar.py - cada cifra de la nota, contra ODEPA, el IPC y el sitio desplegado
================================================================================
Tercer paso (ver README.md), después de descargar.py y vacuno.py. Cuatro
pruebas, todas sobre datos_crudos/:

1. ODEPA. Vuelve a armar la serie de cada corte desde los CSV crudos de
   ODEPA con la misma función del sitio (indices.series_productos, con su
   limpieza) y la compara semana a semana con la publicada, deflactada con
   el mismo factor que usó el sitio. El precio de esta semana se compara
   además con el promedio simple de las filas crudas de ODEPA de esa semana,
   sin limpieza.
2. IPC. El factor con que el sitio llevó cada mes a pesos del último IPC
   (sale de los índices: valor ajustado sobre nominal). Su variación a 12
   meses, frente a la del empalme del Banco Central base 2023 (la familia de
   la serie G073.IPC.IND.2023.M con que deflacta indices.py, que sin usuario
   solo se publica como variación); desde enero de 2024 (misma base, sin
   empalme), frente al índice del INE. Antes de 2024, el empalme del INE y
   el IPC del INE encadenado por bases se apartan del del Banco Central en
   los años de cambio de base: eso va a la robustez.
3. Robustez. A, B y C con esos otros deflactores, con el IPC del mes de
   esta semana si el INE todavía no lo publica (si fuera -0,5%, 0,1%, 0,3%,
   0,5% o 1%), con la serie cruda de ODEPA sin la limpieza del sitio y sin los supermercados
   en línea (que ODEPA suma desde 2020), y B también con el promedio de cada
   mes en vez de la semana. Es informativa: dice qué tan firme es cada
   cifra, no si el sitio está bien.
4. Sitio. Lo que muestra carestia.cl hoy: el número grande, la frase de
   temporada y la de toda la historia de cada ficha, la serie de
   datos/productos/{slug}.json, la fila de datos/catalogo.json y la de la
   tabla de la portada.

Escribe resultados/verificacion.csv (una fila por comparación; las
informativas van con "ok" vacío), resultados/deflactor.csv y
resultados/robustez.csv. Termina con error si alguna comparación falla.

Uso: python verificar.py
"""
import contextlib
import csv
import datetime
import glob
import html
import io
import json
import os
import re
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(1, os.path.dirname(os.path.dirname(AQUI)))
import indices  # noqa: E402
import vacuno  # noqa: E402
from vacuno import CRUDOS, RESULTADOS  # noqa: E402

# el factor del sitio sale de índices redondeados a pesos: cada semana se
# compara con una tolerancia de 1 peso más lo que puede mover ese redondeo
# (cota_factor)
MESES_BCCH = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7,
              "Ago": 8, "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dic": 12}
FILAS = []
INFORMATIVA = "informativa"


def anotar(tipo, corte, cifra, informe, fuente, ok=None, nota=""):
    """Una fila de verificacion.csv. Sin 'ok', coincide si son iguales; con
    ok=INFORMATIVA es un dato (robustez, IPC de otro empalme) que no cuenta
    como comparación ni puede fallar."""
    if ok is None:
        ok = informe == fuente
    FILAS.append({"prueba": tipo, "corte": corte, "cifra": cifra, "nota_de_prensa": informe,
                  "fuente": fuente,
                  "ok": "" if ok == INFORMATIVA else int(bool(ok)), "detalle": nota})
    return ok


# ---------------- el factor del sitio ----------------
def mes_ipc(f: datetime.date, meses: set) -> str:
    """El mes del IPC con que indices.py deflactó una semana: el de su lunes
    o, si ese mes no tiene IPC (el último mes, antes de que el INE lo
    publique), el último anterior que lo tiene (merge_asof hacia atrás)."""
    m = f.strftime("%Y-%m")
    while m not in meses:
        m = (pd.Period(m, "M") - 1).strftime("%Y-%m")
    return m


def factor_sitio(data: dict) -> dict:
    """{"aaaa-mm": ajustado / nominal} de los 4 índices, sumados por mes: el
    factor con que indices.py llevó ese mes a pesos de ipc_mes (el mismo de
    factor_epoca en build_site.py, invertido). Solo meses hasta ipc_mes."""
    nom, real = {}, {}
    for d in data["indices"].values():
        nominal = {p["time"]: p["value"] for p in d["nominal"]}
        for p in d["real"]:
            n = nominal.get(p["time"])
            if n is None or p["value"] is None:
                continue
            m = p["time"][:7]
            if m > data["ipc_mes"]:
                continue
            nom[m] = nom.get(m, 0) + n
            real[m] = real.get(m, 0) + p["value"]
    return {m: real[m] / nom[m] for m in sorted(nom)}


def cota_factor(data: dict) -> dict:
    """{"aaaa-mm": error relativo máximo de factor_sitio}: cada valor de los
    índices viene redondeado a pesos (medio peso de error), así que el
    cociente de las sumas de un mes puede errar en hasta n/2 sobre cada
    suma. En 2008 y 2009 hay un solo índice, de unos 2.500 pesos, y la cota
    llega a unas décimas por mil."""
    n, nom, real = {}, {}, {}
    for d in data["indices"].values():
        nominal = {p["time"]: p["value"] for p in d["nominal"]}
        for p in d["real"]:
            x = nominal.get(p["time"])
            if x is None or p["value"] is None or p["time"][:7] > data["ipc_mes"]:
                continue
            m = p["time"][:7]
            n[m] = n.get(m, 0) + 1
            nom[m] = nom.get(m, 0) + x
            real[m] = real.get(m, 0) + p["value"]
    return {m: 0.5 * n[m] * (1 / nom[m] + 1 / real[m]) for m in n}


def ipc_desde_factor(factor: dict) -> pd.Series:
    """Niveles de IPC (el último mes = 1) que dan exactamente ese factor."""
    return pd.Series({pd.Timestamp(f"{m}-01"): 1 / f for m, f in factor.items()},
                     name="ipc").sort_index()


# ---------------- el IPC del Banco Central y del INE ----------------
def cuadro_bcch(ruta: str, serie: str) -> dict:
    """{"aaaa-mm": valor} de una serie ('serie' es su nombre en la tabla) de
    un cuadro público de la base de datos del Banco Central."""
    t = open(ruta, encoding="utf-8", errors="replace").read()
    cab = [html.unescape(re.sub("<[^>]+>", "", h)).strip()
           for h in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
    filas = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
    for fila in filas:
        celdas = [html.unescape(re.sub("<[^>]+>", "", c)).strip()
                  for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, re.S)]
        if len(celdas) > 2 and celdas[1] == serie:
            break
    else:
        raise RuntimeError(f"el cuadro del Banco Central no trae {serie}")
    out = {}
    for c, x in zip(cab[2:], celdas[2:]):
        if not x:
            continue
        mes, anio = c.split(".")
        out[f"{anio}-{MESES_BCCH[mes]:02d}"] = float(x.replace(".", "").replace(",", "."))
    return out


def ipc_ine(ruta2018: str, ruta2023: str) -> dict:
    """{"aaaa-mm": nivel} del IPC General del INE: base 2018 (2019 a 2023) y
    base 2023 (desde 2024), encadenadas con la variación oficial de enero de
    2024; más diciembre de 2018, desde la variación de enero de 2019."""
    def leer(ruta):
        d = pd.read_csv(ruta, sep=";", decimal=",", encoding="latin-1")
        d.columns = [" ".join(str(c).split()) for c in d.columns]
        d = d[d["Glosa"].astype(str).str.strip() == "IPC General"].drop_duplicates(["Año", "Mes"])
        var = [c for c in d.columns if c.startswith("Variación Mensual")][0]
        return {f"{int(a)}-{int(m):02d}": (float(i), float(v))
                for a, m, i, v in zip(d["Año"], d["Mes"], d["Índice"], d[var])}
    b18, b23 = leer(ruta2018), leer(ruta2023)
    out = {m: i for m, (i, _) in b18.items()}
    out["2018-12"] = b18["2019-01"][0] / (1 + b18["2019-01"][1] / 100)
    enlace = out["2023-12"] * (1 + b23["2024-01"][1] / 100) / b23["2024-01"][0]
    out.update({m: i * enlace for m, (i, _) in b23.items()})
    return dict(sorted(out.items()))


def factores(niveles: dict, ultimo: str) -> dict:
    return {m: niveles[ultimo] / x for m, x in niveles.items() if m <= ultimo}


def mes_siguiente(fsitio: dict) -> tuple:
    """("aaaa-mm", "nombre") del mes que sigue al último IPC."""
    m = pd.Period(max(fsitio), "M") + 1
    return m.strftime("%Y-%m"), vacuno.MESES[m.month - 1]


# ---------------- 1. ODEPA ----------------
def odepa_rm() -> pd.DataFrame:
    frames = []
    for ruta in sorted(glob.glob(os.path.join(CRUDOS, "odepa", "*.csv"))):
        anio = int(os.path.basename(ruta)[:4])
        with open(ruta, "rb") as fh:
            frames.append(indices._norm(indices._leer_csv(fh.read()), anio))
    df = pd.concat(frames, ignore_index=True)
    return df[df["region_rm"]]


def filas_del_corte(df: pd.DataFrame, k: str, p: dict) -> pd.DataFrame:
    """Las filas de ODEPA de un corte, como las junta series_productos: los
    dos de la canasta Asado por su texto (el de BASKETS), el resto por
    nombre sin espacios ni mayúsculas."""
    textos = {_slug(lab): match for meta in indices.BASKETS.values()
              for (lab, match, _q, _u) in meta["items"]}
    if k in textos:
        return df[df["ProductoBase"].str.contains(textos[k], case=False, na=False)]
    clave = df["ProductoBase"].astype(str).str.lower().str.replace(r"\s+", "", regex=True)
    return df[clave == re.sub(r"\s+", "", p["label"].lower())]


def _slug(label: str) -> str:
    return indices._slug(label)


def probar_odepa(df: pd.DataFrame, prods: dict, fsitio: dict, cota: dict) -> tuple:
    """Serie de cada corte armada desde ODEPA con indices.series_productos y
    el factor del sitio, semana a semana contra la publicada. Devuelve las
    series rehechas y las de ODEPA sin limpieza (promedio simple de las
    filas de cada semana, nominal), para la robustez."""
    with contextlib.redirect_stdout(io.StringIO()):
        rehecho = indices.series_productos(df, ipc_desde_factor(fsitio))
    meses = set(fsitio)
    crudas = {}
    for k, p in prods.items():
        q = rehecho.get(k)
        if q is None:
            anotar("odepa", p["label"], "serie rehecha desde ODEPA", "sí", "no está", False)
            continue
        anotar("odepa", p["label"], "primera semana", p["t0"], q["t0"])
        a, b = p["v"], q["v"]
        n = max(len(a), len(b))
        a, b = a + [None] * (n - len(a)), b + [None] * (n - len(b))
        huecos = sum(1 for x, y in zip(a, b) if (x is None) != (y is None))
        anotar("odepa", p["label"], "semanas con precio en una serie y no en la otra", 0, huecos)
        t0 = datetime.date.fromisoformat(p["t0"])
        difs, exceso, iguales = [], [], 0
        for j, (x, y) in enumerate(zip(a, b)):
            if x is None or y is None:
                continue
            m = mes_ipc(t0 + datetime.timedelta(weeks=j), meses)
            difs.append(abs(x - y))
            exceso.append(abs(x - y) - (1 + x * cota[m]))
            iguales += x == y
        anotar("odepa", p["label"], "semana a semana, dentro del redondeo del factor", "todas",
               "todas" if max(exceso) <= 0 else f"{sum(e > 0 for e in exceso)} fuera",
               nota=f"{iguales} de {len(difs)} semanas idénticas; diferencia máxima "
                    f"{max(difs)} pesos")
        # esta semana: el promedio simple de las filas crudas, sin limpieza
        sub = filas_del_corte(df, k, p)
        i = vacuno.ultima(p["v"])
        semana = vacuno.fechas(p)[i]
        filas = sub[sub["fecha"] == pd.Timestamp(semana)]
        anotar("odepa", p["label"], "precio de esta semana: promedio simple de las filas de ODEPA",
               p["v"][i], int(round(filas["Precio promedio"].mean())),
               nota=f"{len(filas)} filas de ODEPA (cada una, el promedio de un sector y "
                    f"tipo de local: {', '.join(sorted(filas['Punto']))}), "
                    f"factor {fsitio[mes_ipc(semana, meses)]:.6f}")
        semanal = sub.groupby("fecha")["Precio promedio"].mean().resample("W-MON").mean()
        crudas[k] = semanal.ffill(limit=4)
    return {k: {**prods[k], **{"v": rehecho[k]["v"], "t0": rehecho[k]["t0"]}}
            for k in prods if k in rehecho}, crudas


def probar_asado_de_tira(df: pd.DataFrame, prods: dict, fsitio: dict) -> dict:
    """Lo que cita el informe sobre el asado de tira y que sale de las filas
    crudas de ODEPA: las filas de esta semana y de 52 semanas antes, la
    variación ajustada por inflación con solo las filas (sector y tipo de
    local) que están en las dos, y las filas de la semana de su máximo de 10
    años. Escribe resultados/asado_de_tira.json."""
    k = "asado_de_tira"
    p = prods[k]
    sub = filas_del_corte(df, k, p)
    meses = set(fsitio)
    c = vacuno.cifras(p)

    def filas(f):
        x = sub[sub["fecha"] == pd.Timestamp(f)]
        return {r["Punto"]: float(r["Precio promedio"]) for _, r in x.iterrows()}
    hoy, antes = filas(c["semana"]), filas(c["semana_anio_antes"])
    comunes = sorted(set(hoy) & set(antes))
    f_antes = fsitio[mes_ipc(c["semana_anio_antes"], meses)]
    f_hoy = fsitio[mes_ipc(c["semana"], meses)]
    var = (sum(hoy[x] for x in comunes) * f_hoy /
           (sum(antes[x] for x in comunes) * f_antes) - 1) * 100
    maxima = filas(c["maximo"]["semana_max_anterior"])
    carnicerias = [x for n, x in maxima.items() if n.endswith("Carnicería")]
    sobre = {n: x for n, x in maxima.items() if not n.endswith("Carnicería")
             and x > max(carnicerias)}
    out = {"semana": c["semana"].isoformat(), "filas": hoy,
           "semana_anio_antes": c["semana_anio_antes"].isoformat(), "filas_anio_antes": antes,
           "filas_en_las_dos": comunes, "variacion_anual_en_las_dos_pct": round(var, 2),
           "semana_del_maximo": c["maximo"]["semana_max_anterior"].isoformat(),
           "filas_del_maximo": maxima, "sobre_todas_las_carnicerias": sobre}
    with open(os.path.join(RESULTADOS, "asado_de_tira.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    anotar("odepa", p["label"], "variación a un año con las filas que están en las dos semanas",
           "", f"{var:.1f}".replace(".", ","), INFORMATIVA, ", ".join(comunes))
    return out


# ---------------- 2. IPC ----------------
def probar_ipc(data: dict, fsitio: dict, v12: dict, fine_emp: dict, fine: dict) -> None:
    filas = []
    for m in fsitio:
        p = (pd.Period(m, "M") - 12).strftime("%Y-%m")
        s12 = (fsitio[p] / fsitio[m] - 1) * 100 if p in fsitio else None
        filas.append({
            "mes": m, "factor_sitio": round(fsitio[m], 6),
            "var12_sitio": "" if s12 is None else round(s12, 3),
            "var12_empalme_bcch": v12.get(m, ""),
            "factor_empalme_ine": round(fine_emp[m], 6) if m in fine_emp else "",
            "factor_ine_por_bases": round(fine[m], 6) if m in fine else "",
            "dif_empalme_ine_pct": (round((fsitio[m] / fine_emp[m] - 1) * 100, 4)
                                    if m in fine_emp else ""),
            "dif_ine_por_bases_pct": round((fsitio[m] / fine[m] - 1) * 100, 4) if m in fine else ""})
    with open(os.path.join(RESULTADOS, "deflactor.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    anotar("ipc", "", "último mes con IPC", data["ipc_mes"], max(v12),
           nota="el sitio y el cuadro del Banco Central")
    # 1. variación a 12 meses: publicada con un decimal (medio décimo de
    # redondeo) más el redondeo del factor
    d12 = [abs(f["var12_sitio"] - f["var12_empalme_bcch"]) for f in filas
           if f["var12_sitio"] != "" and f["var12_empalme_bcch"] != ""]
    anotar("ipc", "", "variación a 12 meses del factor del sitio frente al empalme BCCh "
           "(G073.IPC.V12.2023.M), diferencia máxima en puntos", "hasta 0,07",
           f"{max(d12):.3f}".replace(".", ","), max(d12) <= 0.07, f"{len(d12)} meses")
    # 2. desde enero de 2024, misma base y sin empalme: el factor tiene que
    # ser el del índice del INE (dentro del redondeo del factor y del índice)
    for nombre, ref in (("empalme del INE", fine_emp), ("INE por bases", fine)):
        d = [abs(fsitio[m] / ref[m] - 1) * 100 for m in fsitio if m >= "2024-01" and m in ref]
        anotar("ipc", "", f"desde enero de 2024, factor del sitio frente al {nombre}, "
               "diferencia máxima (%)", "hasta 0,01", f"{max(d):.4f}".replace(".", ","),
               max(d) <= 0.01, f"{len(d)} meses")
        d = [abs(fsitio[m] / ref[m] - 1) * 100 for m in fsitio if m in ref]
        anotar("ipc", "", f"antes de 2024, factor del sitio frente al {nombre}, "
               "diferencia máxima (%)", "", f"{max(d):.2f}".replace(".", ","), INFORMATIVA,
               "otro método de empalme: va a la robustez")


# ---------------- 3. robustez ----------------
def reescalar(p: dict, fsitio: dict, fnuevo: dict, extra=None) -> list:
    """La serie del sitio llevada a otro deflactor: v * fnuevo / fsitio en el
    mes de IPC de cada semana. Los meses anteriores al primero de fnuevo
    siguen las variaciones del sitio, encadenadas en ese primer mes (sin
    escalón). 'extra(semana)' multiplica además (el IPC del mes siguiente)."""
    meses, m0 = set(fsitio), min(fnuevo)
    out = []
    for f, x in zip(vacuno.fechas(p), p["v"]):
        if x is None:
            out.append(None)
            continue
        m = mes_ipc(f, meses)
        r = fnuevo[m] / fsitio[m] if m in fnuevo else fnuevo[m0] / fsitio[m0]
        out.append(x * r * (extra(f) if extra else 1))
    return out


def empalmar(base: dict, nuevo: dict) -> dict:
    """Factores de 'base' con los de 'nuevo' encima, llevados a la escala de
    'base' en el primer mes de 'nuevo'."""
    m0 = min(nuevo)
    out = {**base, **{m: base[m0] * f / nuevo[m0] for m, f in nuevo.items()}}
    return {m: f / out[max(out)] for m, f in out.items()}   # el último mes, 1


def alinear(q: dict, p: dict) -> list:
    """Los valores de la serie q en las semanas de la serie p (mismo t0 y
    largo que p; None donde q no tiene)."""
    corr = (datetime.date.fromisoformat(p["t0"]) - datetime.date.fromisoformat(q["t0"])).days // 7
    return [q["v"][j + corr] if 0 <= j + corr < len(q["v"]) else None
            for j in range(len(p["v"]))]


def abc(prods: dict, series: dict) -> dict:
    """A, B y C con otras series (mismas fechas que el sitio)."""
    top, afirma, cerca, mensual, c = [], [], [], [], None
    for k, p in prods.items():
        q = {**p, "v": series[k]}
        r = vacuno.cifras(q)
        if r["top"]:
            top.append(p["label"])
        if r["maximo"]["se_afirma"]:
            afirma.append(p["label"])
        elif r["maximo"]["es_maximo"]:
            cerca.append(p["label"])
        mm = vacuno.maximo_mensual(vacuno.fechas(q), q["v"], vacuno.ultima(q["v"]))
        if mm["se_afirma"]:
            mensual.append(f"{p['label']} ({vacuno.pct(mm['margen_pct'])} sobre "
                           f"{vacuno.MESES[mm['mes_max_anterior'][1] - 1]} de "
                           f"{mm['mes_max_anterior'][0]})")
        if k == "asado_de_tira":
            c = (r["precio"], r["variacion_anual"])
    return {"top5": len(top),
            "fuera_del_5": sorted(set(p["label"] for p in prods.values()) - set(top)),
            "se_afirman": afirma, "maximo_sin_margen": cerca, "mensual": mensual, "C": c}


def probar_robustez(prods, fsitio, fine_emp, fine, rehecho, crudas, sin_linea, base):
    sig, nombre_sig = mes_siguiente(fsitio)
    rehechas = {k: alinear(rehecho[k], p) for k, p in prods.items()}
    sin_linea = {k: alinear(sin_linea[k], p) for k, p in prods.items()}
    escenarios = [
        ("sitio", "las series del sitio (empalme BCCh, indices.py)",
         {k: p["v"] for k, p in prods.items()}),
        ("odepa", "serie rehecha desde los CSV crudos de ODEPA", rehechas),
        ("ine_empalme", "empalme del INE desde diciembre de 2009",
         {k: reescalar(p, fsitio, fine_emp) for k, p in prods.items()}),
        ("ine_bases", "IPC del INE por bases desde 2019, empalme del INE antes",
         {k: reescalar(p, fsitio, empalmar(fine_emp, fine)) for k, p in prods.items()}),
    ]
    # con el IPC del mes siguiente todo pasa a pesos de ese mes: las semanas
    # de ese mes quedan en su precio de la época y las anteriores suben x%.
    # Solo si esta semana es de un mes todavía sin IPC: si no, ese IPC mueve
    # todas las semanas por igual y no cambia ninguna cifra
    semana_mes = vacuno.max_semana(prods)[:7]
    for x in ((-0.5, 0.1, 0.3, 0.5, 1.0) if semana_mes >= sig else ()):
        escenarios.append((
            "ipc_siguiente", f"IPC de {nombre_sig} de {x:g}%".replace(".", ","),
            {k: reescalar(p, fsitio, fsitio,
                          lambda f, x=x: 1 if f.strftime("%Y-%m") >= sig else 1 + x / 100)
             for k, p in prods.items()}))
    meses = set(fsitio)
    sin_limpieza = {}
    for k, p in prods.items():
        s = crudas[k]
        sin_limpieza[k] = [None if pd.isna(y := s.get(pd.Timestamp(f), np.nan))
                           else y * fsitio[mes_ipc(f, meses)] for f in vacuno.fechas(p)]
    escenarios.append(("sin_limpieza", "ODEPA sin la limpieza del sitio", sin_limpieza))
    escenarios.append(("sin_linea", "ODEPA sin los supermercados en línea (desde 2020)",
                       sin_linea))
    filas = []
    for tipo, nombre, series in escenarios:
        r = abc(prods, series)
        filas.append({"escenario": nombre, "A_top5": r["top5"], "de": len(prods),
                      "fuera_del_5": "; ".join(r["fuera_del_5"]),
                      "B_se_afirman": "; ".join(r["se_afirman"]) or "ninguno",
                      "B_maximo_sin_margen": "; ".join(r["maximo_sin_margen"]) or "ninguno",
                      "B_con_el_promedio_del_mes": "; ".join(r["mensual"]) or "ninguno",
                      "C_precio": round(r["C"][0]), "C_variacion_anual": round(r["C"][1], 1)})
        # las series del sitio tienen que dar lo de resumen.json (control de
        # que está al día) y la rehecha desde ODEPA, lo mismo; los demás
        # escenarios dicen qué tan firme es cada cifra
        prueba = {"sitio": "control", "odepa": "odepa"}.get(tipo, "robustez")
        ok = None if prueba != "robustez" else INFORMATIVA
        anotar(prueba, "", f"A con {nombre}", base["A"]["top5"], r["top5"], ok,
               "fuera: " + ", ".join(r["fuera_del_5"]))
        anotar(prueba, "", f"B con {nombre}", ", ".join(base["B"]["se_afirman"]) or "ninguno",
               ", ".join(r["se_afirman"]) or "ninguno", ok,
               "máximo por menos de 1%: " + (", ".join(r["maximo_sin_margen"]) or "ninguno")
               + "; con el promedio del mes: " + (", ".join(r["mensual"]) or "ninguno"))
        anotar(prueba, "", f"C con {nombre}",
               f"{base['C']['precio']}, {base['C']['variacion_anual']}",
               f"{round(r['C'][0])}, {round(r['C'][1], 1)}", ok)
    with open(os.path.join(RESULTADOS, "robustez.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


# ---------------- 4. el sitio desplegado ----------------
def texto(t: str, clase: str) -> str:
    m = re.search(rf'<(?:p|div) class="{clase}">(.*?)</(?:p|div)>', t, re.S)
    return html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip() if m else None


def probar_sitio(data: dict, prods: dict) -> None:
    cat = json.load(open(os.path.join(CRUDOS, "sitio", "catalogo.json"), encoding="utf-8"))
    portada = open(os.path.join(CRUDOS, "sitio", "index.html"), encoding="utf-8").read()
    por_clave = {f["clave"]: f for f in cat["productos"]}
    mes_ipc_txt = vacuno.MESES[int(data["ipc_mes"][5:]) - 1] + " de " + data["ipc_mes"][:4]
    anotar("sitio", "", "semana del catálogo", vacuno.max_semana(prods), cat["semana"])
    anotar("sitio", "", "cortes de vacuno en el catálogo", len(prods),
           sum(1 for f in cat["productos"] if f["grupo"] == vacuno.GRUPO))
    for k, p in prods.items():
        c = vacuno.cifras(p)
        f = por_clave[k]
        slug = f["slug"]
        anotar("sitio", p["label"], "catálogo: precio", c["precio"], f["precio_pesos_hoy"])
        anotar("sitio", p["label"], "catálogo: variación a un año",
               round(c["variacion_anual"], 1), f["variacion_52s_pct"])
        anotar("sitio", p["label"], "catálogo: percentil", c["historia"]["catalogo"],
               f["percentil"])
        anotar("sitio", p["label"], "catálogo: semana", c["semana"].isoformat(), f["semana"])
        serie = json.load(open(os.path.join(CRUDOS, "sitio", "productos", f"{slug}.json"),
                               encoding="utf-8"))
        anotar("sitio", p["label"], "datos/productos: serie idéntica a indices.json", "sí",
               "sí" if serie["v"] == p["v"] and serie["t0"] == p["t0"] else "no")
        t = open(os.path.join(CRUDOS, "sitio", "fichas", f"{slug}.html"), encoding="utf-8").read()
        anotar("sitio", p["label"], "ficha: número grande", vacuno.clp(c["precio"]),
               texto(t, "oprice"))
        tm = c["temporada"]
        frase = texto(t, "pct") or ""
        m = re.search(r"que en (\d+) de los últimos (\d+) (\w+)", frase)
        anotar("sitio", p["label"], "ficha: mismo mes de los últimos 10 años",
               f"{tm['debajo']} de {tm['anios']} {vacuno.MESES_PLURAL[tm['mes'] - 1]}",
               f"{m.group(1)} de {m.group(2)} {m.group(3)}" if m else frase, nota=frase)
        hist = texto(t, "pct2") or ""
        m = re.search(r"más car\w+ que en el (\d+)% de las semanas desde (\d{4}), ajustad\w+ "
                      r"por inflación, en pesos de (\w+ de \d{4})", hist)
        anotar("sitio", p["label"], "ficha: frente a toda su historia",
               f"{c['historia']['ficha']}% desde {p['t0'][:4]}, pesos de {mes_ipc_txt}",
               f"{m.group(1)}% desde {m.group(2)}, pesos de {m.group(3)}" if m else hist,
               nota=hist)
        semana_txt = vacuno.fecha_larga(c["semana"])
        anotar("sitio", p["label"], "ficha: semana de los precios", semana_txt,
               semana_txt if f"Precios de la semana del {semana_txt}" in t else "otra")
        fila = re.search(rf'<a class="fila" href="/productos/{re.escape(slug)}\.html"[^>]*>',
                         portada)
        attrs = dict(re.findall(r'data-(\w)="([^"]*)"', fila.group(0))) if fila else {}
        anotar("sitio", p["label"], "portada: precio, a un año y percentil",
               f"{c['precio']}, {round(c['variacion_anual'], 1)}, {c['historia']['catalogo']}",
               f"{attrs.get('p')}, {attrs.get('y')}, {attrs.get('c')}")


def probar_descartes(data: dict, prods: dict, fsitio: dict) -> None:
    """Semanas que la limpieza del sitio sacó en la ventana de 10 años,
    ajustadas por inflación con el factor del sitio (vienen en pesos
    nominales). Si alguna quedara sobre el precio de esta semana y sobre el
    máximo de la ventana, B dependería de la limpieza: un corte que hoy no es
    máximo podría seguir sin serlo por ese descarte (no cambia B) y uno que
    sí lo es dejaría de serlo (cambia B, y la fila falla)."""
    meses = set(fsitio)
    for k, p in prods.items():
        c = vacuno.cifras(p)
        mx = c["maximo"]
        desde = (mx["desde"] - datetime.timedelta(days=6)).isoformat()
        fuera = [d for clave in ("descartes", "descartes_anuales", "descartes_puntos")
                 for d in data.get(clave, []) if d["slug"] == k and d["semana"] >= desde]
        reales = [(d["semana"], d["precio"] * fsitio[mes_ipc(
            datetime.date.fromisoformat(d["semana"]), meses)]) for d in fuera]
        sobre = [(s, x) for s, x in reales if x > c["precio"]]
        # devolver una semana descartada solo puede bajar el margen: importa
        # solo si el corte se afirma como máximo, y entonces lo da vuelta
        # una semana a menos de 1% bajo el precio de esta semana
        quita = [(s, x) for s, x in reales if x * (100 + vacuno.MARGEN) >= c["precio"] * 100]
        anotar("limpieza", p["label"], "semanas descartadas en la ventana de 10 años que "
               "darían vuelta B", "ninguna", "ninguna" if not quita else f"{len(quita)}",
               None if mx["se_afirma"] else INFORMATIVA,
               nota=f"{len(fuera)} descartadas; sobre el precio de esta semana: " +
                    (", ".join(f"{s} {vacuno.clp(x)}" for s, x in sobre) or "ninguna"))


def main() -> None:
    data, sha = vacuno.cargar()
    prods = vacuno.cortes(data)
    with open(os.path.join(RESULTADOS, "resumen.json"), encoding="utf-8") as fh:
        base = json.load(fh)
    anotar("entrada", "", "indices.json de vacuno.py y de esta prueba", base["sha256"], sha)
    fsitio, cota = factor_sitio(data), cota_factor(data)
    meses = set(fsitio)
    # en su semana, ajustado y de la época son el mismo: el factor del último mes es 1
    anotar("ipc", "", "factor del último mes con IPC", 1.0, round(fsitio[data["ipc_mes"]], 6))
    anotar("ipc", "", "primer mes con factor del sitio, antes de la primera semana de vacuno",
           "sí", "sí" if min(fsitio) <= min(p["t0"] for p in prods.values())[:7] else "no")
    v12 = cuadro_bcch(os.path.join(CRUDOS, "ipc", "bcch_empalme_bcch_v12.html"),
                      "General (empalme BCCh)")
    fine_emp = factores(cuadro_bcch(os.path.join(CRUDOS, "ipc", "bcch_empalme_ine.html"),
                                    "Índice IPC General"), data["ipc_mes"])
    fine = factores(ipc_ine(os.path.join(CRUDOS, "ipc", "ine_base2018.csv"),
                            os.path.join(CRUDOS, "ipc", "ine_base2023.csv")), data["ipc_mes"])
    print("1. ODEPA: armando las series desde los CSV crudos...")
    df = odepa_rm()
    rehecho, crudas = probar_odepa(df, prods, fsitio, cota)
    probar_asado_de_tira(df, prods, fsitio)
    with contextlib.redirect_stdout(io.StringIO()):
        sin_linea = indices.series_productos(
            df[~df["Punto"].str.endswith("Supermercado en Línea")], ipc_desde_factor(fsitio))
    print("2. IPC")
    probar_ipc(data, fsitio, v12, fine_emp, fine)
    print("3. Robustez")
    probar_robustez(prods, fsitio, fine_emp, fine, rehecho, crudas, sin_linea, base)
    print("4. Sitio desplegado")
    probar_sitio(data, prods)
    probar_descartes(data, prods, fsitio)
    with open(os.path.join(RESULTADOS, "verificacion.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FILAS[0]))
        w.writeheader()
        w.writerows(FILAS)
    comparaciones = [f for f in FILAS if f["ok"] != ""]
    malas = [f for f in comparaciones if not f["ok"]]
    for f in malas:
        print(f"  FALLA {f['prueba']} {f['corte']} {f['cifra']}: nota {f['nota_de_prensa']!r}, "
              f"fuente {f['fuente']!r} {f['detalle']}")
    print(f"{len(comparaciones) - len(malas)} de {len(comparaciones)} comparaciones coinciden "
          f"(y {len(FILAS) - len(comparaciones)} filas informativas de robustez)")
    sys.exit(1 if malas else 0)


if __name__ == "__main__":
    main()

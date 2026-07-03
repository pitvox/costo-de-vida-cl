"""
indices.py - pipeline multi-indice (Fase 0, v5)
===============================================
Novedades v5:
  - MOTOR CONSCIENTE DE UNIDADES: detecta la unidad de ODEPA de cada producto
    y convierte para que la canasta pueda mezclar productos por kilo, por
    unidad (huevo) y por litro (leche/aceite) sin error. Cada item declara en
    que unidad esta su cantidad: "kg", "un" o "l".
  - INDICE ONCE (mezcla unidades: pan/palta/mantequilla/queso por kg, huevo
    por unidad, leche por litro).
  - DESGLOSE DE COMPONENTES por indice (producto, unidad ODEPA, aporte $),
    para transparencia y para que valides en la corrida real.

Conserva: Asado, Ensalada, Fruta; deflactado a pesos de hoy (IPC BCCh o
mindicador); percentil, z-score, vs-promedio, estacionalidad, velas mensuales;
historico 2008-2026 blindado contra cambios de formato.

Correr:
  pip install pandas numpy requests statsmodels
  python indices.py
"""

import io
import os
import re
import json
import requests
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
YEARS = range(2008, 2027)
ID_REGION = "13"            # Region Metropolitana. None/"" = todas.
LISTAR_PRODUCTOS = False
P_BARATO, P_CARO = 33, 66

BCCH_USER = os.environ.get("BCCH_USER", "")
BCCH_PASS = os.environ.get("BCCH_PASS", "")

# Canastas: cada item = (etiqueta, texto_a_buscar, cantidad, unidad_de_la_cantidad)
# unidad: "kg" (por kilo), "un" (por unidad), "l" (por litro).
# El motor detecta la unidad real de ODEPA y convierte (ej: si ODEPA cotiza el
# huevo por docena y tu cantidad esta en "un", divide el precio por 12).
BASKETS = {
    "asado": {
        "nombre": "Índice Asado", "subtitulo": "Asado para 4 personas",
        "items": [
            ("Asado de tira",   "Asado de tira",   1.0, "kg"),
            ("Asado carnicero", "Asado Carnicero", 0.6, "kg"),
            ("Tomate",          "Tomate",          1.0, "kg"),
            ("Cebolla",         "Cebolla",         1,   "un"),
            ("Palta",           "Palta",           0.5, "kg"),
            ("Limón",           "Lim",             0.25, "kg"),
            ("Marraqueta",      "Marraqueta",      1.0, "kg"),
        ],
    },
    "ensalada": {
        "nombre": "Índice Ensalada", "subtitulo": "Ensalada chilena para 4",
        "items": [
            ("Tomate",   "Tomate",   1.0, "kg"), ("Cebolla",  "Cebolla",  1,   "un"),
            ("Palta",    "Palta",    0.5, "kg"), ("Limón",    "Lim",      0.2, "kg"),
            ("Lechuga",  "Lechuga",  1,   "un"), ("Pepino",   "Pepino ensalada", 1, "un"),
            ("Pimiento", "Pimiento", 1,   "un"),
        ],
    },
    "fruta": {
        "nombre": "Índice Fruta", "subtitulo": "Canasta de fruta semanal",
        "items": [
            ("Manzana",   "Manzana",   1.0, "kg"), ("Plátano",   "tano",      1.0, "kg"),
            ("Naranja",   "Naranja",   1.0, "kg"), ("Pera",      "Pera",      0.6, "kg"),
            ("Mandarina", "Mandarina", 0.6, "kg"),
        ],
    },
    "desayuno": {
        "nombre": "Índice Desayuno", "subtitulo": "Desayuno para 4 personas",
        "items": [
            ("Marraqueta",   "Marraqueta",          0.5,   "kg"),
            ("Palta",        "Palta",               0.4,   "kg"),
            ("Mantequilla",  "Mantequilla",         0.125, "kg"),   # ODEPA: pan 250g
            ("Queso Gauda",  "Queso Gauda",         0.25,  "kg"),   # ODEPA: envase 1 kilo
            ("Huevos",       "Huevo color",         6,     "un"),   # ODEPA: bandeja 12 u
            ("Leche entera", "Leche Fluida Entera", 1.0,   "l"),    # ODEPA: caja 1 litro
        ],
    },
}

DATASET = "d4646b7f-0d2e-4567-b6fa-932b1a6bb3f3"
RESOURCES = {
    2026: "9f885df4-afeb-4b75-8bab-9334f79db00f", 2025: "eab239c4-e338-4cde-a9e0-7c4f27826030",
    2024: "5f773b96-6c3a-4017-b871-6340d779ea96", 2023: "1a73ae5d-f4e2-4706-b2c3-e1e05a23fcb6",
    2022: "e9c3f2fc-9bb7-4f5f-a529-d1d60d7a61a5", 2021: "554ea0ea-071e-4947-8c09-b871ff75da05",
    2020: "a3862e70-e683-493e-913c-a68d0268c972", 2019: "4b3e90f8-6353-4d4b-83c5-ad71e09f9ac2",
    2018: "7b0d6880-cd64-452c-9866-da98df361ed3", 2017: "46ef5c90-8036-4b91-98ce-be3fb1aa63f4",
    2016: "d27e1917-c005-4032-b433-4b8ff6c43e2a", 2015: "c9cb178f-bf2f-440c-93a1-3cd783e29fdd",
    2014: "58faea42-a6b0-4947-9a52-3e38b217a190", 2013: "23301e1a-7cad-44d3-be0f-d9ea7d6d2696",
    2012: "398bbc6a-31f0-431d-bbe4-ae259ae11d6f", 2011: "27b2e7f6-c89a-4d92-9ce4-4dd30277651f",
    2010: "c73eda34-82dd-4c33-a6b3-e2297fe50298", 2009: "5fa11f38-7733-48c0-bbdf-23e80f4e262c",
    2008: "0c3bb1cb-d52e-4c22-8c8a-e8451123afcd",
}
URL = "https://datos.odepa.gob.cl/dataset/{ds}/resource/{rid}/download/precio_consumidor_{y}.csv"
COLORES = {"BARATO": "#5bbf7a", "NORMAL": "#e0a83c", "CARO": "#e0552f"}


# ---------------- ODEPA ----------------
def _leer_csv(content: bytes) -> pd.DataFrame:
    txt = content.decode("utf-8-sig", errors="replace")
    for sep in (",", ";"):
        df = pd.read_csv(io.StringIO(txt), dtype=str, sep=sep)
        if df.shape[1] > 3:
            df.columns = [c.strip() for c in df.columns]
            return df
    raise ValueError("no pude separar el CSV")


def _norm(df: pd.DataFrame, year: int) -> pd.DataFrame:
    cols = {c.lower().strip(): c for c in df.columns}

    def pick(*claves):
        for k in claves:
            if k in cols:
                return cols[k]
        return None

    c_prod = pick("producto")
    c_prom = pick("precio promedio", "precio_promedio", "promedio", "precio")
    if not c_prod or not c_prom:
        raise ValueError(f"faltan columnas clave en {year}")

    def num(col):
        return pd.to_numeric(df[col].astype(str).str.replace(".", "", regex=False)
                             .str.replace(",", ".", regex=False), errors="coerce")

    out = pd.DataFrame()
    out["ProductoBase"] = df[c_prod].astype(str).str.split("|").str[0].str.strip()
    out["Precio promedio"] = num(c_prom)
    c_min = pick("precio minimo", "precio_minimo", "minimo", "mínimo")
    c_max = pick("precio maximo", "precio_maximo", "maximo", "máximo")
    out["Precio minimo"] = num(c_min) if c_min else out["Precio promedio"]
    out["Precio maximo"] = num(c_max) if c_max else out["Precio promedio"]

    c_uni = pick("unidad")
    out["Unidad"] = df[c_uni].astype(str).str.strip() if c_uni else ""

    c_fini = pick("fecha inicio", "fecha_inicio", "fecha")
    if c_fini:
        out["fecha"] = pd.to_datetime(df[c_fini], errors="coerce")
    else:
        c_anio, c_sem = pick("anio", "año", "ano"), pick("semana")
        if c_anio and c_sem:
            a = pd.to_numeric(df[c_anio], errors="coerce")
            s = pd.to_numeric(df[c_sem], errors="coerce")
            out["fecha"] = pd.to_datetime(a.astype("Int64").astype(str) + "-01-01",
                                          errors="coerce") + pd.to_timedelta((s - 1) * 7, unit="D")
        else:
            raise ValueError(f"sin fecha utilizable en {year}")

    c_idr, c_reg = pick("id region", "id_region", "idregion"), pick("region", "región")
    if c_idr is not None:
        out["region_rm"] = df[c_idr].astype(str).str.strip() == "13"
    elif c_reg is not None:
        out["region_rm"] = df[c_reg].astype(str).str.contains("Metropolitana", case=False, na=False)
    else:
        out["region_rm"] = True

    return out.dropna(subset=["fecha", "Precio promedio"])


def cargar_odepa() -> pd.DataFrame:
    print("Descargando ODEPA 2008-2026:")
    frames = []
    for y in YEARS:
        if y not in RESOURCES:
            continue
        try:
            print(f"  {y}...")
            r = requests.get(URL.format(ds=DATASET, rid=RESOURCES[y], y=y), timeout=180)
            r.raise_for_status()
            frames.append(_norm(_leer_csv(r.content), y))
        except Exception as e:  # noqa
            print(f"  [ODEPA {y} saltado: {e}]")
    if not frames:
        raise RuntimeError("No se pudo cargar ningun anio de ODEPA.")
    df = pd.concat(frames, ignore_index=True)
    if ID_REGION == "13":
        df = df[df["region_rm"]]
    return df


# ---------------- IPC ----------------
def cargar_ipc() -> pd.Series:
    if BCCH_USER and BCCH_PASS:
        try:
            print("IPC: Banco Central (oficial)...")
            url = ("https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
                   f"?user={BCCH_USER}&pass={BCCH_PASS}"
                   "&firstdate=2008-01-01&lastdate=2026-12-31"
                   "&timeseries=G073.IPC.IND.2018.M&function=GetSeries")
            obs = requests.get(url, timeout=60).json()["Series"]["Obs"]
            s = pd.DataFrame(obs)
            s["fecha"] = pd.to_datetime(s["indexDateString"], format="%d-%m-%Y")
            s["valor"] = pd.to_numeric(s["value"], errors="coerce")
            return s.dropna(subset=["valor"]).set_index("fecha")["valor"].sort_index().rename("ipc")
        except Exception as e:  # noqa
            print(f"  [BCCh fallo: {e}; uso mindicador]")
    else:
        print("IPC: sin credenciales BCCh -> mindicador (fallback).")
    filas = []
    for y in YEARS:
        try:
            serie = requests.get(f"https://mindicador.cl/api/ipc/{y}", timeout=60).json().get("serie", [])
            if serie:
                filas.append(pd.DataFrame(serie))
        except Exception:  # noqa
            pass
    s = pd.concat(filas, ignore_index=True)
    s["fecha"] = pd.to_datetime(s["fecha"]).dt.tz_localize(None)
    s = s.set_index("fecha")["valor"].sort_index()
    return (1 + s / 100.0).cumprod().rename("ipc")


# ---------------- Unidades ----------------
def unidad_modal(df: pd.DataFrame, texto: str) -> str:
    sub = df[df["ProductoBase"].str.contains(texto, case=False, na=False)]
    if sub.empty or "Unidad" not in sub.columns:
        return ""
    u = sub["Unidad"].dropna().astype(str)
    u = u[u.str.strip() != ""]
    return str(u.mode().iloc[0]) if not u.empty else ""


def parse_envase(unidad_str: str):
    """Lee la unidad de ODEPA (que describe el ENVASE) y devuelve (base, contenido):
    base in {'kg','un','l'} y contenido = cuanto de esa base trae el envase.
    Precio por base = precio_ODEPA / contenido. Ejemplos:
      '$/pan de 250 gramos' -> ('kg', 0.25)   (precio del pan / 0.25 = precio por kg)
      '$/bandeja 12 unidades' -> ('un', 12.0)  (precio bandeja / 12 = precio por huevo)
      '$/Caja de 1 Litro' -> ('l', 1.0)        '$/unidad' -> ('un', 1.0)
    """
    u = (unidad_str or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:gramos|grs|gr|g\b)", u)
    if m:
        return ("kg", float(m.group(1).replace(",", ".")) / 1000.0)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kilo", u)
    if m and ("envase" in u or "bolsa" in u or "caja" in u):
        return ("kg", float(m.group(1).replace(",", ".")))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*litro", u)
    if m:
        return ("l", float(m.group(1).replace(",", ".")))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*unidad", u)
    if m:
        return ("un", float(m.group(1).replace(",", ".")))
    if "kilo" in u or u.strip() in ("$/kg", "kg"):
        return ("kg", 1.0)
    if "litro" in u:
        return ("l", 1.0)
    if "unidad" in u:
        return ("un", 1.0)
    return ("kg", 1.0)


def factor_precio(odepa_unit: str, objetivo: str):
    """Devuelve (factor, mismatch). El precio por la unidad objetivo del item es
    precio_ODEPA * factor. Si la base de ODEPA no coincide con la unidad pedida
    (ej: pides kg pero ODEPA vende por unidad), marca mismatch y no convierte."""
    base, contenido = parse_envase(odepa_unit)
    if base != objetivo:
        return 1.0, True            # unidades incompatibles -> avisar
    return 1.0 / contenido, False   # precio por unidad-objetivo real


# ---------------- Calculo de un indice ----------------
def precio_semanal(df: pd.DataFrame, texto: str, col: str = "Precio promedio") -> pd.Series:
    sub = df[df["ProductoBase"].str.contains(texto, case=False, na=False)]
    if sub.empty:
        if col == "Precio promedio":
            print(f"    [aviso] sin datos para '{texto}'")
        return pd.Series(dtype=float)
    return sub.groupby("fecha")[col].mean().sort_index()


def _serie_canasta(df, items, col):
    """Costo semanal de la canasta usando la columna de precio 'col'
    (promedio / minimo / maximo), con conversion de unidad de envase."""
    cols = {}
    for (lab, match, qty, uni) in items:
        f, _ = factor_precio(unidad_modal(df, match), uni)
        cols[lab] = precio_semanal(df, match, col) * f * qty
    return pd.DataFrame(cols).resample("W-MON").mean().ffill(limit=4).sum(axis=1, min_count=len(items))


def calcular(df: pd.DataFrame, ipc: pd.Series, items):
    comp = []
    for (lab, match, qty, uni) in items:
        odu = unidad_modal(df, match)
        f, mismatch = factor_precio(odu, uni)
        if mismatch:
            print(f"    [UNIDAD!] '{lab}': pediste {uni} pero ODEPA vende [{odu}] — revisar canasta")
        serie = precio_semanal(df, match) * f
        comp.append({"label": lab, "qty": qty, "unidad": uni, "odepa_unit": odu,
                     "factor": round(f, 4), "mismatch": mismatch,
                     "precio_ult": None, "aporte": None, "_serie": serie})

    # costo semanal: promedio (linea), minimo y maximo (rango real de las velas)
    prom = _serie_canasta(df, items, "Precio promedio")
    cmin = _serie_canasta(df, items, "Precio minimo")
    cmax = _serie_canasta(df, items, "Precio maximo")

    out = pd.DataFrame({"nominal": prom, "min_nom": cmin, "max_nom": cmax}).dropna(subset=["nominal"])

    # aporte de cada componente en la ultima semana
    for c in comp:
        s = c.pop("_serie").resample("W-MON").mean().ffill(limit=4)
        if len(s) and pd.notna(s.iloc[-1]):
            c["precio_ult"] = int(round(float(s.iloc[-1])))
            c["aporte"] = int(round(float(s.iloc[-1]) * c["qty"]))

    # deflactar a pesos de hoy
    izq = out.reset_index().rename(columns={"index": "fecha"}).sort_values("fecha")
    der = ipc.rename("ipc").rename_axis("fecha").reset_index().sort_values("fecha")
    m = pd.merge_asof(izq, der, on="fecha", direction="backward").set_index("fecha")
    factor = m["ipc"].iloc[-1] / m["ipc"]
    m["real"] = m["nominal"] * factor
    m["rmin"] = m["min_nom"] * factor
    m["rmax"] = m["max_nom"] * factor
    return m, comp


def velas_reales(m: pd.DataFrame) -> list:
    """Velas SEMANALES con rango real: cuerpo = cambio semana a semana
    (open = cierre previo, close = promedio de la semana); mecha = rango de
    precios entre puntos de venta (min-max que reporta ODEPA)."""
    velas = []
    prev = None
    for f, row in m.iterrows():
        close = row["real"]
        if pd.isna(close):
            continue
        op = prev if prev is not None else close
        lo = min(row["rmin"], op, close) if pd.notna(row["rmin"]) else min(op, close)
        hi = max(row["rmax"], op, close) if pd.notna(row["rmax"]) else max(op, close)
        velas.append({"time": f.strftime("%Y-%m-%d"), "open": int(round(op)),
                      "high": int(round(hi)), "low": int(round(lo)), "close": int(round(close))})
        prev = close
    return velas


# ---------------- Velas, estacionalidad, resumen ----------------
def estacionalidad(real: pd.Series) -> dict:
    s = real.dropna()
    trend = s.rolling(52, center=True, min_periods=26).mean()
    detr = (s / trend).dropna()
    if detr.empty:
        return {}
    fac = detr.groupby(detr.index.month).mean()
    fac = fac / fac.mean()
    return {"factores": {int(m): round(float(v), 3) for m, v in fac.items()},
            "mes_barato": int(fac.idxmin()), "mes_caro": int(fac.idxmax()),
            "amplitud": round(float((fac.max() - fac.min()) * 100))}


def clp(x: float) -> str:
    return "$" + f"{int(round(x)):,}".replace(",", ".")


def resumen(out: pd.DataFrame, meta: dict, comp: list) -> dict:
    real, nom = out["real"].dropna(), out["nominal"].dropna()
    ur, un = real.iloc[-1], nom.iloc[-1]
    pct = round(100.0 * (real <= ur).mean())
    z = (ur - real.mean()) / real.std()
    vsp = round(((ur / real.mean()) - 1) * 100)
    ver = "BARATO" if pct < P_BARATO else ("NORMAL" if pct < P_CARO else "CARO")
    return {
        "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
        "fecha": real.index[-1].strftime("%d-%m-%Y"),
        "costo_nominal": int(round(un)), "costo_real": int(round(ur)),
        "percentil": pct, "zscore": round(float(z), 2), "vs_promedio": vsp,
        "veredicto": ver, "color": COLORES[ver], "n": int(len(real)),
        "componentes": comp,
        "estacionalidad": estacionalidad(out["real"]),
        "velas": velas_reales(out),
        "nominal": [{"time": f.strftime("%Y-%m-%d"), "value": int(round(v))}
                    for f, v in zip(out.index, out["nominal"]) if pd.notna(v)],
        "real": [{"time": f.strftime("%Y-%m-%d"), "value": int(round(v))}
                 for f, v in zip(out.index, out["real"]) if pd.notna(v)],
    }


def main() -> None:
    df = cargar_odepa()
    if LISTAR_PRODUCTOS:
        for p in sorted(df["ProductoBase"].dropna().unique()):
            ej = df[df["ProductoBase"] == p]["Unidad"].dropna()
            print(f"  - {p}  [{ej.mode().iloc[0] if not ej.empty else '?'}]")
        return
    ipc = cargar_ipc()

    salida = {"generado": pd.Timestamp.today().strftime("%Y-%m-%d"), "indices": {}}
    print("\n" + "=" * 64)
    for code, meta in BASKETS.items():
        d, comp = calcular(df, ipc, meta["items"])
        r = resumen(d, meta, comp)
        salida["indices"][code] = r
        print(f"{r['nombre']}: hoy {clp(r['costo_real'])} (pesos de hoy) | "
              f"percentil {r['percentil']} | {r['vs_promedio']:+d}% vs prom | {r['veredicto']}")
        # desglose para que valides unidades y aportes
        for c in comp:
            ap = clp(c["aporte"]) if c.get("aporte") is not None else "s/d"
            print(f"    · {c['label']:<16} ODEPA[{c['odepa_unit'] or '?'}] x{c['factor']:g}"
                  f" → {c['qty']}{c['unidad']} = {ap}")
    print("=" * 64)

    with open("indices.json", "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False)
    print("Escrito indices.json")


if __name__ == "__main__":
    main()

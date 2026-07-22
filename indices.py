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
import time
import unicodedata
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

    c_gru = pick("grupo")
    out["Grupo"] = df[c_gru].astype(str).str.strip() if c_gru else ""

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
IPC_MES_INICIO = "2008-01"
IPC_MIN_MESES = 210
IPC_REINTENTOS = 3
IPC_MANUAL_ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipc_manual.json")


def _meses_ipc_esperados() -> pd.PeriodIndex:
    """Meses que la serie IPC debe cubrir: 2008-01 hasta el mes vigente-1."""
    return pd.period_range(IPC_MES_INICIO, pd.Timestamp.today().to_period("M") - 1, freq="M")


def _meses_ipc_faltantes(s: pd.Series) -> list:
    tiene = set(s.index.to_period("M"))
    return [m for m in _meses_ipc_esperados() if m not in tiene]


def _validar_ipc(s: pd.Series) -> pd.Series:
    """Compuerta de la deflactación: un hueco en la serie IPC deforma el
    cumprod y corre percentiles y vs-promedio de TODOS los índices, así que
    ante cobertura incompleta se aborta el build en vez de publicar cifras
    cojas (el Action falla visible y el sitio conserva el deploy anterior)."""
    faltan = _meses_ipc_faltantes(s)
    if faltan:
        raise RuntimeError("IPC incompleto: faltan " + ", ".join(str(m) for m in faltan))
    if len(s) <= IPC_MIN_MESES:
        raise RuntimeError(f"IPC incompleto: solo {len(s)} meses (esperaba >{IPC_MIN_MESES})")
    print(f"IPC OK: {len(s)} meses, {s.index[0]:%Y-%m} a {s.index[-1]:%Y-%m}")
    return s


def _ipc_bcch() -> pd.Series:
    url = ("https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
           f"?user={BCCH_USER}&pass={BCCH_PASS}"
           "&firstdate=2008-01-01&lastdate=2026-12-31"
           "&timeseries=G073.IPC.IND.2018.M&function=GetSeries")
    r = requests.get(url, timeout=60)
    try:
        data = r.json()
    except Exception:
        texto = " ".join(r.text[:300].split())
        print(f"  [BCCh respuesta {r.status_code}: {texto}]")
        raise
    # Con error (ej: Codigo -5) Series.Obs viene null: verificar Codigo antes
    # de tocar Obs para caer limpio a mindicador en vez de morir con KeyError.
    if data.get("Codigo") != 0:
        raise RuntimeError(f"[BCCh error {data.get('Codigo')}: {data.get('Descripcion')}]")
    serie = data.get("Series") or {}
    print(f"  [BCCh serie: {serie.get('descripEsp')}]")
    obs = serie.get("Obs") or []
    if not obs:
        raise RuntimeError("[BCCh: Codigo 0 pero sin observaciones]")
    s = pd.DataFrame(obs)
    s = s[s["statusCode"] == "OK"]
    s["fecha"] = pd.to_datetime(s["indexDateString"], format="%d-%m-%Y")
    s["valor"] = pd.to_numeric(s["value"], errors="coerce")  # value es string; "NaN" -> descartada
    s = s.dropna(subset=["valor"]).set_index("fecha")["valor"].sort_index().rename("ipc")
    if s.empty:
        raise RuntimeError("[BCCh: ninguna observacion valida tras filtrar statusCode/value]")
    # G073.IPC.IND.2018.M es el INDICE (nivel, base 2018), no variaciones: el
    # pipeline deflacta con ipc_hoy/ipc, que espera exactamente un nivel.
    print(f"  [BCCh: {len(s)} obs, {s.index[0]:%Y-%m} a {s.index[-1]:%Y-%m}]")
    return s


def _ipc_mindicador_anio(y: int):
    """DataFrame con las variaciones mensuales de un año en mindicador.
    Vacío si el año aún no tiene datos publicados (respuesta válida);
    None solo si la petición misma falló."""
    try:
        serie = requests.get(f"https://mindicador.cl/api/ipc/{y}", timeout=60).json().get("serie", [])
        print(f"  [mindicador {y}: {len(serie)} meses]")
        return pd.DataFrame(serie)
    except Exception as e:  # noqa
        print(f"  [mindicador {y} fallo: {e}]")
        return None


def _ipc_mindicador_var() -> pd.Series:
    """Variaciones mensuales (%) de mindicador, indexadas por Period mensual.
    Reintenta solo los años cuya petición FALLÓ: un año vacío (ej: 2026 sin
    publicar todavía) es respuesta válida y no se insiste sobre él."""
    datos, pendientes = [], list(YEARS)
    for intento in range(1, IPC_REINTENTOS + 1):
        if intento > 1:
            espera = 2 ** intento
            print(f"  [mindicador: fallaron {pendientes}; "
                  f"reintento {intento}/{IPC_REINTENTOS} en {espera}s]")
            time.sleep(espera)
        fallidos = []
        for y in pendientes:
            df = _ipc_mindicador_anio(y)
            if df is None:
                fallidos.append(y)
            elif not df.empty:
                datos.append(df)
        pendientes = fallidos
        if not pendientes:
            break
    if not datos:
        return pd.Series(dtype=float)
    s = pd.concat(datos, ignore_index=True)
    s["mes"] = pd.to_datetime(s["fecha"]).dt.tz_localize(None).dt.to_period("M")
    s = s.set_index("mes")["valor"].sort_index()
    return s[~s.index.duplicated(keep="last")]


def _ipc_manual() -> pd.Series:
    """Variaciones mensuales (%) tipeadas a mano en ipc_manual.json, formato
    {"2026-01": 0.3, ...}, sacadas de la fuente oficial (INE) por el dueño.
    Los null son placeholders a la espera del dato real y NO cuentan como
    dato: nada se inventa, y el mes queda faltante para la compuerta."""
    try:
        with open(IPC_MANUAL_ARCHIVO, encoding="utf-8") as fh:
            crudo = json.load(fh)
    except FileNotFoundError:
        return pd.Series(dtype=float)
    datos = {pd.Period(mes, freq="M"): float(v)
             for mes, v in crudo.items() if v is not None}
    if not datos:
        return pd.Series(dtype=float)
    return pd.Series(datos).sort_index()


def _empalmar(niveles: pd.Series, variaciones: pd.Series, fuente: str, tramos: list) -> pd.Series:
    """Empalme estándar por tasas: extiende la serie de NIVELES con las
    variaciones mensuales (%) de otra fuente, nivel_t = nivel_{t-1} *
    (1 + var_t/100). Nunca mezcla niveles de dos fuentes, así que es inmune
    a cambios de base (2018=100 vs 2023=100). Solo consume meses CONSECUTIVOS
    al último nivel: un hueco corta el empalme y el mes queda faltante."""
    if niveles.empty or variaciones.empty:
        return niveles
    nivel = float(niveles.iloc[-1])
    nuevos = {}
    mes = niveles.index[-1].to_period("M") + 1
    while mes in variaciones.index:
        nivel *= 1 + float(variaciones.loc[mes]) / 100.0
        nuevos[mes.to_timestamp()] = nivel
        mes += 1
    if nuevos:
        tramos.append(f"{fuente} {min(nuevos):%Y-%m}..{max(nuevos):%Y-%m}")
        niveles = pd.concat([niveles, pd.Series(nuevos)]).rename("ipc")
    return niveles


def cargar_ipc() -> pd.Series:
    """Serie de NIVELES IPC por FUSIÓN de tres fuentes, porque ninguna cubre
    todo: la serie BCCh (G073.IPC.IND.2018.M) quedó congelada en 2023-12
    cuando el INE recanastó a base 2023=100, y mindicador publica con rezago
    el año en curso. Base: niveles BCCh; los meses posteriores se extienden
    con las variaciones de mindicador y luego con las de ipc_manual.json.
    La compuerta _validar_ipc sigue igual de estricta sobre la serie
    fusionada, y la deflactación aguas abajo sigue recibiendo niveles
    (ipc_hoy/ipc) sin cambios."""
    tramos = []
    niveles = pd.Series(dtype=float, name="ipc")
    if BCCH_USER and BCCH_PASS:
        try:
            print("IPC: Banco Central (oficial)...")
            niveles = _ipc_bcch()
            tramos.append(f"BCCh {niveles.index[0]:%Y-%m}..{niveles.index[-1]:%Y-%m}")
        except Exception as e:  # noqa
            print(f"  [BCCh fallo: {e}; sigo con mindicador]")
    else:
        print("IPC: sin credenciales BCCh -> parto de mindicador.")

    var_mind = _ipc_mindicador_var()
    if niveles.empty:
        # Sin niveles BCCh: reconstruye niveles desde las variaciones de
        # mindicador (cumprod, base arbitraria = 1; la deflactación usa
        # cocientes ipc_hoy/ipc así que la escala no importa).
        if var_mind.empty:
            raise RuntimeError("IPC incompleto: sin niveles BCCh ni datos mindicador")
        niveles = (1 + var_mind / 100.0).cumprod().rename("ipc")
        niveles.index = niveles.index.to_timestamp()
        tramos.append(f"mindicador {niveles.index[0]:%Y-%m}..{niveles.index[-1]:%Y-%m}")
    else:
        niveles = _empalmar(niveles, var_mind, "mindicador", tramos)

    niveles = _empalmar(niveles, _ipc_manual(), "manual", tramos)
    print("[IPC fusión: " + " · ".join(tramos) + "]")
    return _validar_ipc(niveles)


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


def parse_envase_estricto(unidad_str: str):
    """La compuerta de unidades del catálogo completo: misma cadena de
    reconocimiento que parse_envase pero SIN fallback — si el envase no se
    reconoce con certeza devuelve None y el producto queda fuera del JSON.
    También rechaza 'N kilos' sin contexto de envase/bolsa/caja (una malla
    de 18 kilos tratada como $/kg publicaría un precio 18 veces menor).
    Un precio mal normalizado publicado es peor que un producto ausente."""
    u = (unidad_str or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:gramos|grs|gr|g\b)", u)
    if m:
        return ("kg", float(m.group(1).replace(",", ".")) / 1000.0)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kilo", u)
    if m:
        if "envase" in u or "bolsa" in u or "caja" in u:
            return ("kg", float(m.group(1).replace(",", ".")))
        return None                      # 'N kilos' suelto: envase incierto
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
    return None


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


# ---------------- Series por producto (vista Productos) ----------------
def _slug(label: str) -> str:
    """Normaliza un label a clave: minusculas, sin tildes, espacios -> '_'."""
    s = unicodedata.normalize("NFKD", label)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip().replace(" ", "_")


def _modal(serie) -> str:
    """Valor más frecuente no vacío de una columna, o ''."""
    if serie is None:
        return ""
    s = serie.dropna().astype(str).str.strip()
    s = s[s != ""]
    return str(s.mode().iloc[0]) if not s.empty else ""


def series_productos(df: pd.DataFrame, ipc: pd.Series) -> dict:
    """Catálogo COMPLETO de productos RM en formato compacto.

    Dos pasadas: (1) los productos de las canastas oficiales conservan su
    slug histórico y su agregación por texto de match — los deep links
    #canasta=... ya compartidos dependen de esos slugs; (2) el resto de los
    ProductoBase de la data, deduplicando variantes que difieren solo en
    espacios/mayúsculas ("Lentejas 6 mm" ≡ "Lentejas 6mm").

    COMPUERTA: solo entra al JSON el producto cuya unidad modal ODEPA se
    parsea con certeza (parse_envase_estricto) a kg/un/l; el resto se
    excluye y se reporta. Serie: precio por unidad base, W-MON +
    ffill(limit=4) como el pipeline, deflactada a pesos de hoy, y emitida
    compacta: {label, unidad, grupo, t0, v} con v = enteros semanales
    consecutivos desde t0 y null en las semanas sin dato (estacionales)."""
    ipc_hoy = float(ipc.iloc[-1])
    der = ipc.rename("ipc").rename_axis("fecha").reset_index().sort_values("fecha")
    out, excluidos = {}, []

    def emitir(slug, label, uni, grupo, precios, contenido):
        s = (precios / contenido).resample("W-MON").mean().ffill(limit=4)
        validos = s.dropna()
        if validos.empty:
            return
        s = s.loc[validos.index[0]:validos.index[-1]]   # recorta colas sin dato
        izq = s.rename("nominal").rename_axis("fecha").reset_index().sort_values("fecha")
        m = pd.merge_asof(izq, der, on="fecha", direction="backward").set_index("fecha")
        real = m["nominal"] * (ipc_hoy / m["ipc"])
        out[slug] = {
            "label": label, "unidad": uni, "grupo": grupo or "Otros",
            "t0": s.index[0].strftime("%Y-%m-%d"),
            "v": [int(round(v)) if pd.notna(v) else None for v in real],
        }

    # 1) canastas oficiales: slug y agregación históricos
    consumidos = pd.Series(False, index=df.index)
    universo = {}
    for meta in BASKETS.values():
        for (lab, match, _qty, uni) in meta["items"]:
            if match not in universo:
                universo[match] = (lab, uni)
    for match, (lab, uni) in universo.items():
        mask = df["ProductoBase"].str.contains(match, case=False, na=False)
        if not mask.any():
            continue
        consumidos |= mask
        sub = df[mask]
        odu = unidad_modal(df, match)
        p = parse_envase_estricto(odu)
        if p is None or p[0] != uni:
            excluidos.append((lab, odu))
            continue
        emitir(_slug(lab), lab, uni, _modal(sub.get("Grupo")),
               sub.groupby("fecha")["Precio promedio"].mean().sort_index(), p[1])

    # 2) resto del catálogo, deduplicado por espacios/mayúsculas
    resto = df[~consumidos]
    clave = resto["ProductoBase"].astype(str).str.lower().str.replace(r"\s+", "", regex=True)
    for _k, sub in resto.groupby(clave):
        label = re.sub(r"\s+", " ", _modal(sub["ProductoBase"]))
        if not label:
            continue
        odu = _modal(sub["Unidad"])
        p = parse_envase_estricto(odu)
        if p is None:
            excluidos.append((label, odu))
            continue
        slug = _slug(label)
        if slug in out:
            continue
        emitir(slug, label, p[0], _modal(sub.get("Grupo")),
               sub.groupby("fecha")["Precio promedio"].mean().sort_index(), p[1])

    for lab, odu in sorted(excluidos):
        print(f"EXCLUIDOS (unidad no parseada): {lab}: {odu or '(sin unidad)'}")
    print(f"Catálogo: {len(out)} incluidos, {len(excluidos)} excluidos")
    return out


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

    salida["productos"] = series_productos(df, ipc)   # imprime su propio reporte

    with open("indices.json", "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False)
    print("Escrito indices.json")


if __name__ == "__main__":
    main()

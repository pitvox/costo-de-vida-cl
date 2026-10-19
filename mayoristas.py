"""
mayoristas.py: precios mayoristas de frutas y hortalizas en los mercados de
Santiago, por semana y por kilo, en datos/mayoristas.json.

Corre aparte de indices.py (no lo importa ni lo toca) y aparte del sitio:
build_site.py no lee este archivo, ningún workflow lo corre y nada se publica
todavía.

Fuente: ODEPA, "Precios mayoristas de frutas y hortalizas", en el portal de
datos abiertos (CKAN) datos.odepa.gob.cl, licencia CC BY 4.0. Es un CSV por
año desde 1994, con un precio por día hábil, mercado, producto, variedad,
calidad, unidad de comercialización y origen. La lista de CSV sale de la API
del portal (package_show), así que un año nuevo entra solo. No lee HTML.

Qué hace:
  1. Se queda con la Región Metropolitana (ID region 13): Lo Valledor, Vega
     Central Mapocho, Mapocho venta directa y, hasta 2011, Vega Poniente.
  2. Pasa cada precio a pesos por kilo con los kilos que declara la propia
     unidad de comercialización ("$/malla 18 kilos": 18; "$/bins (400
     kilos)": 400; "$/kilo (en caja de 17 kilos)": 1, porque ya viene por
     kilo). Una unidad que no declara kilos ("$/caja 15 unidades", "$/docena
     de atados", "$/unidad") no tiene factor oficial: esas filas quedan fuera
     y se anotan por producto.
  3. Descarta las filas con precio cero y las de error de captura: las que
     quedan bajo un quinto o sobre cinco veces la mediana del precio por kilo
     de las filas del producto en esa semana (con menos de 3 filas, la de esa
     semana y las 8 anteriores; con menos de 3 ahí, no se juzga). Es la banda
     de limpiar_semanal en indices.py, aplicada a filas: ODEPA trae filas con
     la unidad cambiada (el precio de un bins rotulado "$/kilo", el de un
     kilo rotulado "$/saco 40 kilos").
  4. Agrupa por semana rotulada con su lunes, la convención W-MON de
     indices.py: la semana del lunes X va del lunes X al domingo siguiente,
     igual que la semana de precios al consumidor que indices.py rotula con
     su "Fecha inicio". En ODEPA mayorista son los días hábiles, y también el
     sábado hasta enero de 2012. (No sirve resample("W-MON") directo sobre
     fechas diarias: cierra por la derecha y mandaría de martes a domingo al
     lunes siguiente.) El precio de la semana es el promedio simple del
     precio por kilo de sus filas y obs es cuántas filas entraron. Las
     semanas sin filas no se rellenan.
  5. Un producto entra con al menos 52 semanas con precio; si no, va a
     "fuera" con su motivo.

Los productos que también están en indices.json llevan su mismo slug (la
tabla EQUIVALENCIAS); el resto, el slug que daría indices.py a su nombre. Si
hay un indices.json en la carpeta, avisa de los slugs que no calcen.

Escribe datos/mayoristas.json:

  {"fuente": ..., "licencia": "CC BY 4.0", "generado": "2026-10-19",
   "ultimo_dia": "2026-10-16", "mercados": [{"mercado", "desde", "hasta"}],
   "productos": {"tomate": {"producto_odepa": "Tomate",
                            "subsector": "Hortalizas y tubérculos",
                            "en_indices": true,
                            "filas_sin_factor": {"$/caja 10 unidades": 3},
                            "filas_descartadas": 96,
                            "semanas": [{"semana": "1994-02-28",
                                         "precio_kg": 123.45, "obs": 55}]}},
   "fuera": [{"producto_odepa": "Lechuga", "slug": "lechuga",
              "en_indices": true, "motivo": ..., "unidades": {...}}]}

Precios nominales (sin deflactar), en pesos por kilo.

Correr:
  pip install pandas numpy requests
  python mayoristas.py               # baja unos 940 MB de CSV
  python mayoristas.py --cache DIR   # los guarda en DIR y reusa los de años cerrados
"""
import argparse
import datetime
import io
import json
import os
import re
import time
import unicodedata

import numpy as np
import pandas as pd
import requests

DATASET = "precios-mayoristas-de-frutas-y-hortalizas"
API = "https://datos.odepa.gob.cl/api/3/action/package_show"
PAGINA = "https://datos.odepa.gob.cl/dataset/" + DATASET
ID_REGION = "13"
ARCHIVO = os.path.join("datos", "mayoristas.json")
REINTENTOS = 4
TIMEOUT = 300
BANDA = 5.0          # fuera de [mediana/5, mediana*5] = error de captura
VENTANA = 8          # semanas anteriores que entran en la mediana de la banda
MIN_FILAS = 3        # filas mínimas en la ventana para juzgar
MIN_SEMANAS = 52     # semanas con precio mínimas para que un producto entre

dormir = time.sleep  # los tests lo reemplazan para no esperar

# columnas del CSV de ODEPA (el diccionario de datos del recurso)
COLUMNAS = ("Fecha", "ID region", "Mercado", "Subsector", "Producto",
            "Unidad de comercializacion", "Precio promedio")

# Producto del CSV mayorista -> slug del mismo producto en indices.json
# (precios al consumidor). Revisada contra los 120 productos del indices.json
# de carestia.cl del 19-10-2026: son sus 45 frutas y hortalizas. Los marcados
# "un" tienen en indices.json precio por unidad; acá el precio es por kilo,
# así que esas dos series no se comparan directo. Los marcados "fuera" no
# tienen en Santiago ninguna unidad con kilos: quedan en "fuera".
EQUIVALENCIAS = {
    # Frutas
    "Arándano (blue)": "arandano_(blue)",
    "Cereza": "cereza",
    "Chirimoya": "chirimoya",
    "Ciruela": "ciruela",
    "Damasco": "damasco",
    "Durazno": "durazno",
    "Frambuesa": "frambuesa",
    "Frutilla": "frutilla",
    "Kiwi": "kiwi",
    "Limón": "limon",
    "Mandarina": "mandarina",
    "Mango": "mango",
    "Manzana": "manzana",
    "Naranja": "naranja",
    "Nectarín": "nectarin",
    "Palta": "palta",
    "Pera": "pera",
    "Plátano": "platano",
    "Tuna": "tuna",
    "Uva": "uva",
    # Hortalizas y tubérculos
    "Ajo": "ajo",                          # un
    "Alcachofa": "alcachofa",              # un, fuera
    "Apio": "apio",                        # un, fuera
    "Arveja Verde": "arveja_verde",
    "Brócoli": "brocoli",                  # un, fuera
    "Cebolla": "cebolla",                  # un
    "Choclo": "choclo",                    # un, fuera
    "Coliflor": "coliflor",                # un, fuera
    "Espárragos": "esparragos",
    "Espinaca": "espinaca",
    "Haba": "haba",
    "Lechuga": "lechuga",                  # un, fuera
    "Melón": "melon",                      # un, fuera (una sola semana por kilo)
    "Papa": "papa",
    "Pepino dulce": "pepino_dulce",
    "Pepino ensalada": "pepino",           # un, fuera
    "Pimiento": "pimiento",                # un
    "Poroto granado": "poroto_granado",
    "Poroto verde": "poroto_verde",
    "Repollo": "repollo",                  # un, fuera
    "Sandia": "sandia",                    # un
    "Tomate": "tomate",
    "Zanahoria": "zanahoria",
    "Zapallo": "zapallo",
    "Zapallo italiano": "zapallo_italiano",  # un, fuera
}


# ---------------- Nombres y unidades ----------------
def slug(nombre: str) -> str:
    """El slug de indices.py (_slug): minúsculas, sin tildes, espacios a '_'."""
    s = unicodedata.normalize("NFKD", nombre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip().replace(" ", "_")


def clave(producto: str) -> str:
    return EQUIVALENCIAS.get(producto) or slug(producto)


def kilos(unidad) -> float:
    """Kilos de la unidad de comercialización, leídos de su propio texto, o
    None si el texto no los declara (entonces no hay factor oficial):
      "$/kilo", "$/kilo (en caja de 17 kilos)", "$/kg caja 18 Kgs. Importado" -> 1
      "$/malla 18 kilos", "$/caja 18 kilos granel", "$/bins (400 kilos)" -> 18, 18, 400
      "$/bandeja 12 canastillos 125 gramos" -> 1.5
      "$/caja 15 unidades", "$/docena de atados", "$/atado 1 a 1,5 kilos" -> None
    Un rango de kilos no es un factor: queda fuera."""
    u = " ".join(str(unidad or "").lower().split())
    if re.match(r"\$/(kilo|kg)\b", u):
        return 1.0
    m = re.fullmatch(r"\$/bandeja (\d+) canastillos (\d+) gramos", u)
    if m:
        k = int(m[1]) * int(m[2]) / 1000
    else:
        m = re.fullmatch(r"\$/[a-z ]+?\(?(\d+(?:,\d+)?) kilos?\)?(?: [a-z]+)?", u)
        k = float(m[1].replace(",", ".")) if m else None
    return k if k else None


def lunes(fechas: pd.Series) -> pd.Series:
    """Lunes de la semana de cada fecha (la etiqueta W-MON de indices.py)."""
    f = pd.to_datetime(fechas).dt.normalize()
    return f - pd.to_timedelta(f.dt.dayofweek, unit="D")


def _numero(s: pd.Series) -> pd.Series:
    """"17666,6666" -> 17666.6666. Con coma decimal, el punto es de miles."""
    s = s.astype(str).str.strip()
    coma = s.str.contains(",", regex=False)
    s = s.where(~coma, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


# ---------------- Lectura ----------------
def leer_csv(contenido: bytes) -> pd.DataFrame:
    """Filas de la Región Metropolitana de un CSV anual de ODEPA, con su
    semana, los kilos de su unidad (NaN sin factor) y el precio por kilo."""
    df = pd.read_csv(io.BytesIO(contenido), dtype=str, encoding="utf-8-sig",
                     keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ValueError(f"al CSV le faltan columnas: {', '.join(faltan)}")
    df = df[df["ID region"].str.strip() == ID_REGION]
    unidad = df["Unidad de comercializacion"].str.strip()
    factores = {u: kilos(u) for u in unidad.unique()}
    out = pd.DataFrame({
        "fecha": pd.to_datetime(df["Fecha"].str.strip(), format="%Y-%m-%d", errors="coerce"),
        "mercado": df["Mercado"].str.strip(),
        "subsector": df["Subsector"].str.strip(),
        "producto": df["Producto"].str.strip(),
        "unidad": unidad,
        "kilos": unidad.map(factores).astype(float),
        "precio": _numero(df["Precio promedio"]),
    })
    malas = int(out["fecha"].isna().sum())
    if malas:
        print(f"  [{malas} filas sin fecha válida: quedan fuera]")
        out = out[out["fecha"].notna()]
    out["semana"] = lunes(out["fecha"])
    out["precio_kg"] = out["precio"] / out["kilos"]
    for c in ("mercado", "subsector", "producto", "unidad"):
        out[c] = out[c].astype("category")
    return out.reset_index(drop=True)


def _bajar(url: str, params: dict = None) -> bytes:
    """GET con hasta REINTENTOS intentos (esperas de 2, 4 y 8 s)."""
    for intento in range(1, REINTENTOS + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            if intento == REINTENTOS:
                raise
            espera = 2 ** intento
            print(f"  [{type(e).__name__}: {e}; reintento {intento + 1} de {REINTENTOS} en {espera} s]")
            dormir(espera)


def recursos(respuesta: dict) -> list:
    """[(año, url, bytes)] de los CSV anuales según package_show, por año.
    Sin CSV, con dos para un año o con años salteados, error: un hueco en la
    serie no puede pasar callado."""
    if not respuesta.get("success"):
        raise ValueError(f"package_show sin éxito: {respuesta.get('error')}")
    por_anio = {}
    for r in respuesta["result"]["resources"]:
        if str(r.get("format", "")).upper() != "CSV":
            continue
        m = (re.search(r"_(\d{4})\.csv$", str(r.get("url", "")))
             or re.search(r"\b(\d{4})\b", str(r.get("name", ""))))
        if not m:
            continue
        anio = int(m[1])
        if anio in por_anio:
            raise ValueError(f"el dataset trae dos CSV para {anio}")
        por_anio[anio] = (r["url"], r.get("size"))
    if not por_anio:
        raise ValueError("el dataset no trae CSV anuales")
    anios = sorted(por_anio)
    faltan = sorted(set(range(anios[0], anios[-1] + 1)) - set(anios))
    if faltan:
        raise ValueError(f"al dataset le faltan los años {faltan}")
    return [(a, *por_anio[a]) for a in anios]


def cargar(cache: str = None) -> pd.DataFrame:
    """Todas las filas de Santiago de todos los años. Con cache, los CSV se
    guardan ahí y los de años cerrados se reusan si tienen el tamaño que
    informa el portal (el del año en curso se baja siempre)."""
    lista = recursos(json.loads(_bajar(API, {"id": DATASET})))
    ultimo = lista[-1][0]
    print(f"ODEPA, precios mayoristas: {len(lista)} CSV, de {lista[0][0]} a {ultimo}")
    frames = []
    for anio, url, size in lista:
        ruta = os.path.join(cache, os.path.basename(url)) if cache else None
        if (ruta and anio < ultimo and os.path.exists(ruta)
                and (size is None or os.path.getsize(ruta) == size)):
            with open(ruta, "rb") as fh:
                contenido = fh.read()
            origen = "caché"
        else:
            contenido = _bajar(url)
            origen = f"{len(contenido) / 1e6:.0f} MB"
            if ruta:
                os.makedirs(cache, exist_ok=True)
                with open(ruta + ".tmp", "wb") as fh:
                    fh.write(contenido)
                os.replace(ruta + ".tmp", ruta)
        df = leer_csv(contenido)
        print(f"  {anio}: {len(df)} filas de Santiago ({origen})")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for c in ("mercado", "subsector", "producto", "unidad"):
        df[c] = df[c].astype("category")
    return df


# ---------------- Limpieza ----------------
def fuera_de_banda(df: pd.DataFrame) -> pd.Series:
    """True en las filas con precio por kilo bajo mediana/BANDA o sobre
    mediana*BANDA. La mediana es la de las filas del mismo producto en su
    semana si son al menos MIN_FILAS; si no, la de su semana y las VENTANA
    anteriores, si ahí hay al menos MIN_FILAS; si tampoco, la fila no se
    juzga. Primero la semana propia: con una ventana hacia atrás, cuando el
    precio cae rápido (el tomate en enero) la tercera calidad quedaría bajo
    la banda sin ser un error. df trae solo filas con precio por kilo."""
    fuera = pd.Series(False, index=df.index)
    atras = np.timedelta64(7 * VENTANA, "D")
    for _, sub in df.groupby("producto", observed=True):
        sub = sub.sort_values("semana", kind="stable")
        sem = sub["semana"].to_numpy()
        val = sub["precio_kg"].to_numpy()
        semanas = np.unique(sem)
        propia = np.searchsorted(sem, semanas, side="left")
        desde = np.searchsorted(sem, semanas - atras, side="left")
        hasta = np.searchsorted(sem, semanas, side="right")
        med = np.full(len(semanas), np.nan)
        for i, (p, a, b) in enumerate(zip(propia, desde, hasta)):
            if b - p >= MIN_FILAS:
                med[i] = np.median(val[p:b])
            elif b - a >= MIN_FILAS:
                med[i] = np.median(val[a:b])
        ref = med[np.searchsorted(semanas, sem)]
        fuera.loc[sub.index] = (val < ref / BANDA) | (val > ref * BANDA)
    return fuera


def estados(df: pd.DataFrame) -> pd.Series:
    """Estado de cada fila: 'sin_factor' (su unidad no declara kilos),
    'descartada' (precio cero o fuera de la banda) u 'ok'."""
    est = pd.Series("ok", index=df.index)
    est[df["kilos"].isna()] = "sin_factor"
    sin_precio = df["kilos"].notna() & ~(df["precio"] > 0)
    est[sin_precio] = "descartada"
    con = df[est == "ok"]
    est[con.index[fuera_de_banda(con).to_numpy()]] = "descartada"
    return est


# ---------------- Salida ----------------
def _conteo(s: pd.Series) -> dict:
    c = s.astype(str).value_counts()
    return {k: int(v) for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))}


def armar(df: pd.DataFrame, min_semanas: int = MIN_SEMANAS) -> dict:
    """{"productos", "fuera"} de datos/mayoristas.json a partir de las filas
    de cargar() (o de leer_csv())."""
    est = estados(df)
    productos, fuera = {}, []
    for nombre, sub in df.groupby("producto", observed=True, sort=True):
        nombre = str(nombre)
        k = clave(nombre)
        e = est.loc[sub.index]
        ok = sub[e == "ok"]
        semanal = ok.groupby("semana")["precio_kg"].agg(["mean", "size"])
        base = {"producto_odepa": nombre, "slug": k, "en_indices": nombre in EQUIVALENCIAS}
        if ok.empty or len(semanal) < min_semanas:
            if sub["kilos"].isna().all():
                motivo = "ninguna de sus unidades declara kilos: no hay factor oficial"
            else:
                n = len(semanal)
                motivo = (f"{n} {'semana' if n == 1 else 'semanas'} con precio por kilo "
                          f"(el mínimo es {min_semanas})")
            fuera.append({**base, "motivo": motivo, "unidades": _conteo(sub["unidad"])})
            continue
        if k in productos:
            raise ValueError(f"dos productos con el slug {k}")
        productos[k] = {
            "producto_odepa": nombre,
            "subsector": str(sub["subsector"].astype(str).mode().iloc[0]),
            "en_indices": base["en_indices"],
            "filas_sin_factor": _conteo(sub.loc[e == "sin_factor", "unidad"]),
            "filas_descartadas": int((e == "descartada").sum()),
            "semanas": [{"semana": f.strftime("%Y-%m-%d"), "precio_kg": round(float(p), 2),
                         "obs": int(n)} for f, p, n in semanal.itertuples()],
        }
    return {"productos": productos, "fuera": fuera}


def mercados(df: pd.DataFrame) -> list:
    g = df.groupby("mercado", observed=True)["fecha"].agg(["min", "max"]).sort_index()
    return [{"mercado": str(m), "desde": a.strftime("%Y-%m-%d"), "hasta": b.strftime("%Y-%m-%d")}
            for m, a, b in g.itertuples()]


def revisar_indices(salida: dict, ruta: str = "indices.json") -> list:
    """Avisos contra un indices.json local, si hay: una equivalencia cuyo slug
    no existe allá, o un producto sin equivalencia cuyo slug sí existe (le
    falta la fila en EQUIVALENCIAS)."""
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as fh:
        slugs = set(json.load(fh).get("productos", {}))
    avisos = [f"EQUIVALENCIAS: {n} -> {s} no está en {ruta}"
              for n, s in EQUIVALENCIAS.items() if s not in slugs]
    filas = [(k, p["producto_odepa"], p["en_indices"]) for k, p in salida["productos"].items()]
    filas += [(p["slug"], p["producto_odepa"], p["en_indices"]) for p in salida["fuera"]]
    avisos += [f"{n}: su slug {k} está en {ruta} pero no en EQUIVALENCIAS"
               for k, n, en in filas if not en and k in slugs]
    return avisos


def escribir(datos: dict, ruta: str = ARCHIVO) -> None:
    carpeta = os.path.dirname(ruta)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(ruta + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(ruta + ".tmp", ruta)


def generar(df: pd.DataFrame, hoy: datetime.date = None) -> dict:
    hoy = hoy or datetime.date.today()
    return {
        "fuente": ("ODEPA (Oficina de Estudios y Políticas Agrarias), "
                   "Precios mayoristas de frutas y hortalizas"),
        "url": PAGINA,
        "licencia": "CC BY 4.0",
        "modificaciones": ("Elaboración propia sobre los datos de ODEPA: solo la Región "
                           "Metropolitana, precio por kilo con los kilos de la unidad de "
                           "comercialización, sin las filas con precio cero o con error de "
                           "captura, y promedio por semana."),
        "generado": hoy.isoformat(),
        "ultimo_dia": df["fecha"].max().strftime("%Y-%m-%d"),
        "semana": "lunes de la semana (W-MON, como indices.py), de lunes a domingo",
        "precio_kg": "pesos nominales por kilo, promedio simple de las filas de la semana",
        "obs": "filas de ODEPA (día, mercado, variedad, calidad, unidad y origen) en el promedio",
        "mercados": mercados(df),
        **armar(df, MIN_SEMANAS),
    }


def main(argv: list = None) -> int:
    p = argparse.ArgumentParser(description="Precios mayoristas de ODEPA a datos/mayoristas.json")
    p.add_argument("--cache", help="carpeta donde guardar los CSV y reusar los de años cerrados")
    p.add_argument("--salida", default=ARCHIVO, help=f"archivo de salida (por omisión {ARCHIVO})")
    args = p.parse_args(argv)

    df = cargar(args.cache)
    datos = generar(df)
    for aviso in revisar_indices(datos):
        print(f"AVISO {aviso}")
    escribir(datos, args.salida)

    print(f"Escrito {args.salida}: {len(datos['productos'])} productos, "
          f"{len(datos['fuera'])} fuera, último día {datos['ultimo_dia']}")
    for k, x in datos["productos"].items():
        s = x["semanas"]
        linea = f"  {k}: {len(s)} semanas, {s[0]['semana']} a {s[-1]['semana']}"
        if not x["en_indices"]:
            linea += " (no está en indices.json)"
        sin = sum(x["filas_sin_factor"].values())
        if sin:
            linea += f", {sin} filas sin factor"
        if x["filas_descartadas"]:
            linea += f", {x['filas_descartadas']} descartadas"
        print(linea)
    for x in datos["fuera"]:
        print(f"  FUERA {x['producto_odepa']}: {x['motivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

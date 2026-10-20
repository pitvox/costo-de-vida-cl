"""
mayoristas.py: precios mayoristas de frutas y hortalizas en los mercados de
Santiago, por semana, por kilo y (en los productos que indices.json lleva por
unidad) por unidad, en datos/mayoristas.json.

Corre aparte de indices.py (no lo importa ni lo toca) y aparte del sitio:
build_site.py no lee este archivo, ningún workflow lo corre y nada se publica
todavía.

Fuente: ODEPA, "Precios mayoristas de frutas y hortalizas", en el portal de
datos abiertos (CKAN) datos.odepa.gob.cl, licencia CC BY 4.0. Es un CSV por
año desde 1994, con un precio y un volumen transado por día hábil, mercado,
producto, variedad, calidad, unidad de comercialización y origen. La lista
de CSV sale de la API del portal (package_show), así que un año nuevo entra
solo. No lee HTML.

Qué hace:
  1. Se queda con la Región Metropolitana (ID region 13): Lo Valledor, Vega
     Central Mapocho, Mapocho venta directa y, hasta 2011, Vega Poniente.
  2. Lee de la propia unidad de comercialización qué cubre el precio y qué
     cuenta la columna Volumen (medida()), sin inventar factores:
       "$/malla 18 kilos": el precio es de una malla de 18 kilos y el volumen
         cuenta mallas.
       "$/kilo (en caja de 17 kilos)": el precio ya es por kilo y el volumen
         cuenta cajas de 17 kilos.
       "$/kilo (volumen en unidades)": precio por kilo, pero el volumen cuenta
         piezas (zapallos, sandías): esas filas entran al promedio simple y no
         al ponderado.
       "$/caja 15 unidades", "$/unidad", "$/cien": precio de 15, 1 o 100
         unidades; el volumen cuenta cajas en la primera y unidades sueltas en
         las otras dos.
     Una unidad que no declara su cantidad ("$/docena de atados", "$/paquete")
     no tiene factor oficial: esas filas quedan fuera y se anotan por producto.
  3. Arma la serie por kilo de cada producto y, si indices.json lo lleva por
     unidad (POR_UNIDAD), también la serie por unidad.
  4. Descarta las filas con precio cero y las de error de captura: las que
     quedan bajo un quinto o sobre cinco veces la mediana del precio (por
     kilo o por unidad) de las filas del producto en esa semana (con menos de
     3 filas, la de esa semana y las 8 anteriores; con menos de 3 ahí, no se
     juzga). Es la banda de limpiar_semanal en indices.py, aplicada a filas:
     ODEPA trae filas con la unidad cambiada (el precio de un bins rotulado
     "$/kilo", el de un kilo rotulado "$/saco 40 kilos").
  5. Agrupa por semana rotulada con su lunes, la convención W-MON de
     indices.py: la semana del lunes X va del lunes X al domingo siguiente,
     igual que la semana de precios al consumidor que indices.py rotula con
     su "Fecha inicio". En ODEPA mayorista son los días hábiles, y también el
     sábado hasta enero de 2012. (No sirve resample("W-MON") directo sobre
     fechas diarias: cierra por la derecha y mandaría de martes a domingo al
     lunes siguiente.) El precio de la semana es el promedio ponderado por lo
     transado (kilos o unidades), solo si todas sus filas tienen volumen
     conocido, y sin las filas con un volumen de más de 20 veces el
     percentil 75 de su temporada (ODEPA trae volúmenes con dígitos de más);
     precio_simple es el promedio simple de sus filas y obs cuántas filas
     entraron. Las semanas sin filas no se rellenan.
  6. Una serie entra con al menos 52 semanas con precio; si no, va a "fuera"
     con su motivo.

Los productos que también están en indices.json llevan su mismo slug (la
tabla EQUIVALENCIAS); el resto, el slug que daría indices.py a su nombre. Si
hay un indices.json en la carpeta, avisa de los slugs o unidades que no
calcen.

Escribe datos/mayoristas.json:

  {"fuente": ..., "licencia": "CC BY 4.0", "generado": "2026-10-19",
   "ultimo_dia": "2026-10-16", "mercados": [{"mercado", "desde", "hasta"}],
   "productos": {"cebolla": {"producto_odepa": "Cebolla",
                             "subsector": "Hortalizas y tubérculos",
                             "en_indices": true, "unidad_indices": "un",
                             "filas_sin_factor": {"$/docena de atados": 1},
                             "kg": {"filas_descartadas": 25, "filas_sin_volumen": 0,
                                    "filas_volumen_dudoso": 3,
                                    "semanas": [{"semana": "1994-04-04",
                                                 "precio": 41.2, "precio_simple": 40.1,
                                                 "obs": 12, "volumen": 50000}]},
                             "un": {...}}},
   "fuera": [{"producto_odepa": "Lechuga", "slug": "lechuga", "en_indices": true,
              "serie": "kg", "motivo": ..., "unidades": {...}}]}

Precios nominales (sin deflactar). En la serie "kg", precio por kilo y
volumen en kilos; en la serie "un", precio por unidad y volumen en unidades.
precio y volumen quedan en null en una semana con alguna fila sin volumen
conocido (el zapallo y la sandía por kilo, cuyo volumen cuenta piezas, y las
filas de VOLUMEN_INCIERTO) o con todas sus filas de volumen dudoso.

Correr:
  pip install pandas numpy requests
  python mayoristas.py               # la primera vez baja unos 940 MB de CSV a
                                     # .cache/mayoristas/; después, solo el año en curso
                                     # y los años que ODEPA haya cambiado (otro md5)
  python mayoristas.py --completo    # baja de nuevo todos los años
  python mayoristas.py --cache DIR   # otra carpeta para los CSV
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import tempfile
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
CACHE = os.path.join(".cache", "mayoristas")   # los CSV anuales; fuera del repo
REINTENTOS = 4
TIMEOUT = 300
BANDA = 5.0          # fuera de [mediana/5, mediana*5] = error de captura
VENTANA = 8          # semanas anteriores que entran en la mediana de la banda
MIN_FILAS = 3        # filas mínimas en la ventana para juzgar
MIN_SEMANAS = 52     # semanas con precio mínimas para que una serie entre
BANDA_VOLUMEN = 20   # volumen sobre 20 veces el percentil 75 de su temporada = error
                     # de captura: la fila sale del ponderado (no del promedio simple)
VENTANA_VOLUMEN = 4  # semanas antes y después en ese percentil 75

dormir = time.sleep  # los tests lo reemplazan para no esperar

# columnas del CSV de ODEPA (el diccionario de datos del recurso)
COLUMNAS = ("Fecha", "ID region", "Mercado", "Subsector", "Producto",
            "Unidad de comercializacion", "Volumen", "Precio promedio")

# Producto del CSV mayorista -> slug del mismo producto en indices.json
# (precios al consumidor). Revisada contra los 120 productos del indices.json
# de carestia.cl del 19-10-2026: son sus 45 frutas y hortalizas.
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
    "Ajo": "ajo",
    "Alcachofa": "alcachofa",
    "Apio": "apio",
    "Arveja Verde": "arveja_verde",
    "Brócoli": "brocoli",
    "Cebolla": "cebolla",
    "Choclo": "choclo",
    "Coliflor": "coliflor",
    "Espárragos": "esparragos",
    "Espinaca": "espinaca",
    "Haba": "haba",
    "Lechuga": "lechuga",
    "Melón": "melon",
    "Papa": "papa",
    "Pepino dulce": "pepino_dulce",
    "Pepino ensalada": "pepino",
    "Pimiento": "pimiento",
    "Poroto granado": "poroto_granado",
    "Poroto verde": "poroto_verde",
    "Repollo": "repollo",
    "Sandia": "sandia",
    "Tomate": "tomate",
    "Zanahoria": "zanahoria",
    "Zapallo": "zapallo",
    "Zapallo italiano": "zapallo_italiano",
}

# Filas cuyo volumen viene en una escala que no se puede saber: (producto,
# comienzo de la unidad, mercado, desde, hasta). Entran al promedio simple,
# pero no al ponderado: su semana queda con precio y volumen en null.
#   Choclo en mallas de Lo Valledor, mayo de 2013 a diciembre de 2014: la
#   mediana de su volumen pasa de 300 a 800 mallas por fila a entre 4.000 y
#   45.000 en varios meses (45.000 en mayo de 2013, 14.250 en septiembre,
#   28.500 en mayo de 2014), como si contara choclos y no mallas, mientras en
#   la Vega Central sigue en 45 a 120. Ni la banda de volumen las separa: su
#   temporada entera viene inflada.
VOLUMEN_INCIERTO = [
    ("Choclo", "$/malla ", "Mercado Mayorista Lo Valledor de Santiago", "2013-05-01", "2014-12-31"),
]

# Slugs que indices.json lleva por unidad ("unidad": "un"): además de la serie
# por kilo, llevan la serie por unidad.
POR_UNIDAD = {"ajo", "alcachofa", "apio", "brocoli", "cebolla", "choclo", "coliflor",
              "lechuga", "melon", "pepino", "pimiento", "repollo", "sandia",
              "zapallo_italiano"}



# ---------------- Nombres y unidades ----------------
def slug(nombre: str) -> str:
    """El slug de indices.py (_slug): minúsculas, sin tildes, espacios a '_'."""
    s = unicodedata.normalize("NFKD", nombre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip().replace(" ", "_")


def clave(producto: str) -> str:
    return EQUIVALENCIAS.get(producto) or slug(producto)


def _cifra(texto: str) -> float:
    return float(texto.replace(",", "."))


def medida(unidad):
    """Qué mide una unidad de comercialización, leído solo de su texto:
    (base, por_precio, por_volumen), o None si el texto no declara cuánto
    trae (entonces no hay factor oficial).
      base: "kg" (se vende por peso) o "un" (por cantidad)
      por_precio: kilos o unidades que cubre el precio
      por_volumen: kilos o unidades que cuenta cada unidad de la columna
        Volumen, o None si no se puede saber
    Ejemplos:
      "$/malla 18 kilos", "$/bins (400 kilos)" -> ("kg", 18, 18), ("kg", 400, 400)
      "$/kilo (en caja de 17 kilos)" -> ("kg", 1, 17): el volumen cuenta cajas
      "$/kilo" -> ("kg", 1, 1)
      "$/kilo (volumen en unidades)" -> ("kg", 1, None): el volumen cuenta piezas
      "$/bandeja 12 canastillos 125 gramos" -> ("kg", 1.5, 1.5)
      "$/caja 15 unidades" -> ("un", 15, 15): el volumen cuenta cajas
      "$/paquete 20 unidades (volumen en unidades)" -> ("un", 20, 1)
      "$/unidad", "$/cien" -> ("un", 1, 1), ("un", 100, 1): el volumen cuenta unidades
      "$/docena de matas" -> ("un", 12, 12): una mata es una planta (apio); el
        volumen cuenta docenas ("$/media docena de matas", 6)
      "$/cien en rama (volumen en unidades)", "$/cien (a granel)" -> ("un", 100, 1):
        "en rama" y "a granel" dicen cómo viene, la cuenta sigue siendo cien
      "$/docena de atados", "$/paquete", "$/atado 1 a 1,5 kilos" -> None: un
        atado o un paquete no dicen cuántas unidades traen
    Un rango de kilos no es un factor: queda fuera."""
    u = " ".join(str(unidad or "").lower().split())
    # por kilo: si el texto nombra el envase, el volumen cuenta envases de esos
    # kilos ("$/kilo (en caja de 17 kilos)", "$/kg caja 18 Kgs. Importado");
    # un texto por kilo que no se entienda deja el volumen sin escala
    m = re.match(r"\$/(?:kilo|kg)\b(.*)$", u)
    if m:
        if not m[1]:
            return ("kg", 1.0, 1.0)
        envase = (re.fullmatch(r" \(en [a-z]+ de (\d+(?:,\d+)?) kilos ?\)(?: [a-z]+)?", m[1])
                  or re.fullmatch(r" caja (\d+) kgs\. [a-z]+", m[1]))
        return ("kg", 1.0, _cifra(envase[1]) if envase else None)
    m = re.fullmatch(r"\$/bandeja (\d+) canastillos (\d+) gramos", u)
    if m:
        k = int(m[1]) * int(m[2]) / 1000
        return ("kg", k, k) if k else None
    m = re.fullmatch(r"\$/[a-z ]+?\(?(\d+(?:,\d+)?) kilos?\)?(?: [a-z]+)?", u)
    if m:
        k = _cifra(m[1])
        return ("kg", k, k) if k else None
    # por cantidad
    m = re.fullmatch(r"\$/[a-z]+ (\d+) unidades( \(volumen en unidades\))?", u)
    if m:
        n = int(m[1])
        return ("un", float(n), 1.0 if m[2] else float(n)) if n else None
    if u == "$/unidad":
        return ("un", 1.0, 1.0)
    # cien y mil: el volumen cuenta unidades sueltas (brócoli, coliflor y
    # repollo pasaron de "$/cien" a "$/unidad" en abril de 2012 sin saltar)
    m = re.fullmatch(r"\$/(cien|mil)(?: unidades| matas| en rama)?"
                     r"(?: \(a granel\))?(?: \(volumen en unidades\))?", u)
    if m:
        return ("un", 100.0 if m[1] == "cien" else 1000.0, 1.0)
    # docena: el volumen cuenta docenas (la albahaca pasó de "$/cien matas" a
    # "$/docena" en 2013 con el mismo volumen diario contado en matas)
    if u in ("$/docena", "$/docena de matas"):
        return ("un", 12.0, 12.0)
    if u in ("$/media docena", "$/media docena de matas"):
        return ("un", 6.0, 6.0)
    return None


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
    semana, la medida de su unidad (base, por_precio y por_volumen; NaN sin
    factor), el precio y el volumen por kilo o por unidad (precio_base,
    volumen_base)."""
    df = pd.read_csv(io.BytesIO(contenido), dtype=str, encoding="utf-8-sig",
                     keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ValueError(f"al CSV le faltan columnas: {', '.join(faltan)}")
    df = df[df["ID region"].str.strip() == ID_REGION]
    unidad = df["Unidad de comercializacion"].str.strip()
    medidas = {u: medida(u) or (None, np.nan, np.nan) for u in unidad.unique()}
    out = pd.DataFrame({
        "fecha": pd.to_datetime(df["Fecha"].str.strip(), format="%Y-%m-%d", errors="coerce"),
        "mercado": df["Mercado"].str.strip(),
        "subsector": df["Subsector"].str.strip(),
        "producto": df["Producto"].str.strip(),
        "unidad": unidad,
        "base": unidad.map(lambda u: medidas[u][0]),
        "por_precio": unidad.map(lambda u: medidas[u][1]).astype(float),
        "por_volumen": unidad.map(lambda u: medidas[u][2]).astype(float),
        "precio": _numero(df["Precio promedio"]),
        "volumen": _numero(df["Volumen"]),
    })
    malas = int(out["fecha"].isna().sum())
    if malas:
        print(f"  [{malas} filas sin fecha válida: quedan fuera]")
        out = out[out["fecha"].notna()]
    out["semana"] = lunes(out["fecha"])
    for producto, unidad, mercado, desde, hasta in VOLUMEN_INCIERTO:
        incierto = ((out["producto"] == producto) & out["unidad"].str.startswith(unidad)
                    & (out["mercado"] == mercado) & out["fecha"].between(desde, hasta))
        out.loc[incierto, "por_volumen"] = np.nan
    out["precio_base"] = out["precio"] / out["por_precio"]
    out["volumen_base"] = out["volumen"] * out["por_volumen"]
    for c in ("mercado", "subsector", "producto", "unidad", "base"):
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
    """[(año, url, bytes, md5)] de los CSV anuales según package_show, por año
    (bytes y md5 en None si el portal no los informa).
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
        md5 = str(r.get("hash") or "").lower().removeprefix("md5:")
        por_anio[anio] = (r["url"], r.get("size"),
                          md5 if re.fullmatch(r"[0-9a-f]{32}", md5) else None)
    if not por_anio:
        raise ValueError("el dataset no trae CSV anuales")
    anios = sorted(por_anio)
    faltan = sorted(set(range(anios[0], anios[-1] + 1)) - set(anios))
    if faltan:
        raise ValueError(f"al dataset le faltan los años {faltan}")
    return [(a, *por_anio[a]) for a in anios]


def _guardar(ruta: str, contenido: bytes) -> None:
    """Escribe de una vez: a un temporal propio de la carpeta y después lo
    renombra, así dos corridas a la vez no se pisan ni dejan un archivo a
    medias con el nombre final."""
    carpeta = os.path.dirname(ruta) or "."
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=carpeta, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(contenido)
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def vigente(contenido: bytes, size, md5) -> bool:
    """Si el CSV guardado es el que publica el portal: mismo md5 si el portal
    lo informa (una corrección de ODEPA puede no cambiar el tamaño); si no,
    mismo tamaño; sin ninguno de los dos no se puede saber, y no lo es."""
    if md5:
        return hashlib.md5(contenido).hexdigest() == md5
    if size is not None:
        return len(contenido) == size
    return False


def cargar(cache: str = CACHE, completo: bool = False) -> pd.DataFrame:
    """Todas las filas de Santiago de todos los años, con descarga
    incremental: el CSV del año en curso (el último del listado) se baja
    siempre, y los de años anteriores salen de la caché si el archivo
    guardado es el que publica el portal (vigente(): mismo md5, o mismo
    tamaño si el portal no informa md5). Si ODEPA cambió uno, se vuelve a
    bajar. Con completo se bajan todos de nuevo."""
    lista = recursos(json.loads(_bajar(API, {"id": DATASET})))
    ultimo = lista[-1][0]
    print(f"ODEPA, precios mayoristas: {len(lista)} CSV, de {lista[0][0]} a {ultimo}")
    frames, reusados, bajados = [], 0, 0
    for anio, url, size, md5 in lista:
        ruta = os.path.join(cache, os.path.basename(url))
        contenido = None
        if not completo and anio < ultimo and os.path.exists(ruta):
            with open(ruta, "rb") as fh:
                guardado = fh.read()
            if vigente(guardado, size, md5):
                contenido, origen = guardado, "caché"
                reusados += 1
            else:
                print(f"  [{anio}: el archivo guardado no es el que publica el portal, "
                      f"se vuelve a bajar]")
        if contenido is None:
            contenido = _bajar(url)
            origen = f"{len(contenido) / 1e6:.0f} MB"
            bajados += 1
            _guardar(ruta, contenido)
        df = leer_csv(contenido)
        print(f"  {anio}: {len(df)} filas de Santiago ({origen})")
        frames.append(df)
    print(f"  {reusados} {'año' if reusados == 1 else 'años'} de la caché ({cache}), "
          f"{bajados} {'bajado' if bajados == 1 else 'bajados'}")
    df = pd.concat(frames, ignore_index=True)
    for c in ("mercado", "subsector", "producto", "unidad", "base"):
        df[c] = df[c].astype("category")
    return df


# ---------------- Limpieza ----------------
def fuera_de_banda(df: pd.DataFrame) -> pd.Series:
    """True en las filas con precio (por kilo o por unidad) bajo
    mediana/BANDA o sobre mediana*BANDA. La mediana es la de las filas del
    mismo producto y base en su semana si son al menos MIN_FILAS; si no, la de
    su semana y las VENTANA anteriores, si ahí hay al menos MIN_FILAS; si
    tampoco, la fila no se juzga. Primero la semana propia: con una ventana
    hacia atrás, cuando el precio cae rápido (el tomate en enero) la tercera
    calidad quedaría bajo la banda sin ser un error. df trae solo filas con
    precio_base."""
    fuera = pd.Series(False, index=df.index)
    atras = np.timedelta64(7 * VENTANA, "D")
    for _, sub in df.groupby(["producto", "base"], observed=True):
        sub = sub.sort_values("semana", kind="stable")
        sem = sub["semana"].to_numpy()
        val = sub["precio_base"].to_numpy()
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
    """Estado de cada fila: 'sin_factor' (su unidad no declara cuánto trae, o
    es por unidad en un producto sin serie por unidad), 'descartada' (precio
    cero o fuera de la banda) u 'ok'."""
    nombres = df["producto"].astype(str)
    por_unidad = nombres.map({n: clave(n) in POR_UNIDAD for n in nombres.unique()})
    usable = (df["base"] == "kg") | ((df["base"] == "un") & por_unidad)
    est = pd.Series("ok", index=df.index)
    est[~usable] = "sin_factor"
    est[usable & ~(df["precio"] > 0)] = "descartada"
    con = df[est == "ok"]
    est[con.index[fuera_de_banda(con).to_numpy()]] = "descartada"
    return est


# ---------------- Salida ----------------
def _conteo(s: pd.Series) -> dict:
    c = s.astype(str).value_counts()
    return {k: int(v) for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))}


def _redondo(x, decimales=None):
    if pd.isna(x):
        return None
    return round(float(x), decimales) if decimales else int(round(float(x)))


def volumen_dudoso(ok: pd.DataFrame) -> pd.Series:
    """True en las filas con un volumen (en kilos o unidades) de más de
    BANDA_VOLUMEN veces el percentil 75 del de las filas del mismo producto,
    base y mercado en su semana y las VENTANA_VOLUMEN antes y después, sea
    cual sea su envase. ODEPA trae volúmenes con dígitos de más (una tuna con
    19.000 cajas cuando la mediana de su temporada es 45, una zanahoria con
    37.000 sacos contra 15) o contados en otro envase (palta "en bins de 450
    kilos" con 1.000 bins, que parecen cajas), y una sola de esas filas se
    lleva el ponderado de su semana. La banda es más ancha que la del precio
    porque un lote puede ser muchas veces otro; la referencia es la
    temporada, para no castigar el pico de la cosecha, y el percentil 75 y no
    la mediana, para no castigar los lotes grandes de la calidad que más se
    transa frente a los chicos de las otras (la frutilla Primera en la
    cosecha de 2008, el limón 1a amarillo de 2015 a 2017). La fila sigue en
    el promedio simple."""
    dudoso = pd.Series(False, index=ok.index)
    v = ok["volumen_base"].where(ok["volumen_base"] > 0)
    margen = np.timedelta64(7 * VENTANA_VOLUMEN, "D")
    con = ok[v.notna()].sort_values("semana", kind="stable")
    for _, sub in con.groupby(["producto", "base", "mercado"], observed=True):
        sem = sub["semana"].to_numpy()
        val = sub["volumen_base"].to_numpy()
        semanas = np.unique(sem)
        desde = np.searchsorted(sem, semanas - margen, side="left")
        hasta = np.searchsorted(sem, semanas + margen, side="right")
        ref = np.array([np.percentile(val[a:b], 75) for a, b in zip(desde, hasta)])
        dudoso.loc[sub.index] = val > ref[np.searchsorted(semanas, sem)] * BANDA_VOLUMEN
    return dudoso


def semanal(ok: pd.DataFrame, dudoso: pd.Series = None) -> pd.DataFrame:
    """Por semana: promedio simple, filas y, si todas las filas de la semana
    tienen volumen conocido y mayor que cero, el precio ponderado por lo
    transado y el volumen. Con alguna fila sin volumen, precio y volumen
    quedan en NaN: ponderar solo una parte de la semana daría otro precio.
    Las filas dudoso (ver volumen_dudoso) cuentan como con volumen, pero no
    entran al ponderado ni al volumen: si todas lo son, la semana también
    queda en NaN."""
    v = ok["volumen_base"].where(ok["volumen_base"] > 0)
    peso = v if dudoso is None else v.where(~dudoso.reindex(ok.index, fill_value=False))
    g = pd.DataFrame({"semana": ok["semana"], "p": ok["precio_base"], "v": v, "w": peso,
                      "pw": ok["precio_base"] * peso}).groupby("semana")
    out = pd.DataFrame({"simple": g["p"].mean(), "obs": g["p"].size(),
                        "volumen": g["w"].sum(min_count=1), "pw": g["pw"].sum(min_count=1)})
    completa = g["v"].count() == out["obs"]
    out["volumen"] = out["volumen"].where(completa)
    out["precio"] = (out["pw"] / out["volumen"]).where(completa)
    return out


def armar(df: pd.DataFrame, min_semanas: int = MIN_SEMANAS) -> dict:
    """{"productos", "fuera"} de datos/mayoristas.json a partir de las filas
    de cargar() (o de leer_csv())."""
    est = estados(df)
    dudoso = volumen_dudoso(df[est == "ok"])
    productos, fuera = {}, []
    for nombre, sub in df.groupby("producto", observed=True, sort=True):
        nombre = str(nombre)
        k = clave(nombre)
        e = est.loc[sub.index]
        en_indices = nombre in EQUIVALENCIAS
        series = {}
        for base in ("kg", "un") if k in POR_UNIDAD else ("kg",):
            de_base = sub["base"] == base
            ok = sub[de_base & (e == "ok")]
            s = semanal(ok, dudoso)
            if len(s) < min_semanas:
                if not de_base.any():
                    motivo = ("ninguna de sus unidades declara kilos" if base == "kg" else
                              "ninguna de sus unidades declara cuántas unidades trae")
                    motivo += ": no hay factor oficial"
                else:
                    n = len(s)
                    motivo = (f"{n} {'semana' if n == 1 else 'semanas'} con precio por "
                              f"{'kilo' if base == 'kg' else 'unidad'} (el mínimo es {min_semanas})")
                fuera.append({"producto_odepa": nombre, "slug": k, "en_indices": en_indices,
                              "serie": base, "motivo": motivo, "unidades": _conteo(sub["unidad"])})
                continue
            series[base] = {
                "filas_descartadas": int((de_base & (e == "descartada")).sum()),
                "filas_sin_volumen": int((~(ok["volumen_base"] > 0)).sum()),
                "filas_volumen_dudoso": int(dudoso.reindex(ok.index, fill_value=False).sum()),
                "semanas": [{"semana": f.strftime("%Y-%m-%d"),
                             "precio": _redondo(x.precio, 2),
                             "precio_simple": _redondo(x.simple, 2),
                             "obs": int(x.obs), "volumen": _redondo(x.volumen)}
                            for f, x in s.iterrows()],
            }
        if not series:
            continue
        if k in productos:
            raise ValueError(f"dos productos con el slug {k}")
        productos[k] = {
            "producto_odepa": nombre,
            "subsector": str(sub["subsector"].astype(str).mode().iloc[0]),
            "en_indices": en_indices,
            "unidad_indices": ("un" if k in POR_UNIDAD else "kg") if en_indices else None,
            "filas_sin_factor": _conteo(sub.loc[e == "sin_factor", "unidad"]),
            **series,
        }
    return {"productos": productos, "fuera": fuera}


def mercados(df: pd.DataFrame) -> list:
    g = df.groupby("mercado", observed=True)["fecha"].agg(["min", "max"]).sort_index()
    return [{"mercado": str(m), "desde": a.strftime("%Y-%m-%d"), "hasta": b.strftime("%Y-%m-%d")}
            for m, a, b in g.itertuples()]


def revisar_indices(salida: dict, ruta: str = "indices.json") -> list:
    """Avisos contra un indices.json local, si hay: una equivalencia cuyo slug
    no existe allá, una unidad distinta de la de POR_UNIDAD, o un producto sin
    equivalencia cuyo slug sí existe (le falta la fila en EQUIVALENCIAS)."""
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as fh:
        prods = json.load(fh).get("productos", {})
    avisos = []
    for n, s in EQUIVALENCIAS.items():
        if s not in prods:
            avisos.append(f"EQUIVALENCIAS: {n} -> {s} no está en {ruta}")
        elif (prods[s].get("unidad") == "un") != (s in POR_UNIDAD):
            avisos.append(f"POR_UNIDAD: {s} va en {ruta} por {prods[s].get('unidad')}")
    filas = [(k, p["producto_odepa"], p["en_indices"]) for k, p in salida["productos"].items()]
    filas += [(p["slug"], p["producto_odepa"], p["en_indices"]) for p in salida["fuera"]]
    avisos += sorted({f"{n}: su slug {k} está en {ruta} pero no en EQUIVALENCIAS"
                      for k, n, en in filas if not en and k in prods})
    return avisos


def escribir(datos: dict, ruta: str = ARCHIVO) -> None:
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    _guardar(ruta, texto.encode("utf-8"))


def generar(df: pd.DataFrame, hoy: datetime.date = None) -> dict:
    hoy = hoy or datetime.date.today()
    return {
        "fuente": ("ODEPA (Oficina de Estudios y Políticas Agrarias), "
                   "Precios mayoristas de frutas y hortalizas"),
        "url": PAGINA,
        "licencia": "CC BY 4.0",
        "modificaciones": ("Elaboración propia sobre los datos de ODEPA: solo la Región "
                           "Metropolitana, precio por kilo o por unidad con la cantidad que "
                           "declara la unidad de comercialización, sin las filas con precio "
                           "cero o con error de captura, y promedio por semana."),
        "generado": hoy.isoformat(),
        "ultimo_dia": df["fecha"].max().strftime("%Y-%m-%d"),
        "semana": "lunes de la semana (W-MON, como indices.py), de lunes a domingo",
        "precio": ("pesos nominales por kilo (serie kg) o por unidad (serie un), promedio "
                   "ponderado por lo transado; null si alguna fila de la semana no tiene "
                   "volumen conocido o si todas tienen volumen dudoso"),
        "precio_simple": "promedio simple de las filas de la semana",
        "obs": "filas de ODEPA (día, mercado, variedad, calidad, unidad y origen) en el promedio simple",
        "volumen": ("kilos (serie kg) o unidades (serie un) transados en la semana, sin las "
                    "filas de volumen dudoso; null cuando precio es null"),
        "mercados": mercados(df),
        **armar(df, MIN_SEMANAS),
    }


def main(argv: list = None) -> int:
    p = argparse.ArgumentParser(description="Precios mayoristas de ODEPA a datos/mayoristas.json")
    p.add_argument("--cache", default=CACHE,
                   help=f"carpeta de los CSV anuales (por omisión {CACHE})")
    p.add_argument("--completo", action="store_true",
                   help="baja de nuevo todos los años, aunque ya estén en la caché")
    p.add_argument("--salida", default=ARCHIVO, help=f"archivo de salida (por omisión {ARCHIVO})")
    args = p.parse_args(argv)

    df = cargar(args.cache, args.completo)
    datos = generar(df)
    for aviso in revisar_indices(datos):
        print(f"AVISO {aviso}")
    escribir(datos, args.salida)

    print(f"Escrito {args.salida}: {len(datos['productos'])} productos, "
          f"{len(datos['fuera'])} series fuera, último día {datos['ultimo_dia']}")
    for k, x in datos["productos"].items():
        for base in ("kg", "un"):
            if base not in x:
                continue
            s = x[base]["semanas"]
            linea = (f"  {k} ({base}): {len(s)} {'semana' if len(s) == 1 else 'semanas'}, "
                     f"{s[0]['semana']} a {s[-1]['semana']}")
            if not x["en_indices"]:
                linea += " (no está en indices.json)"
            n = x[base]["filas_descartadas"]
            if n:
                linea += f", {n} {'fila descartada' if n == 1 else 'filas descartadas'}"
            sin_pond = sum(1 for w in s if w["precio"] is None)
            if sin_pond:
                linea += (f", {sin_pond} {'semana' if sin_pond == 1 else 'semanas'} "
                          f"sin precio ponderado")
            print(linea)
    for x in datos["fuera"]:
        print(f"  FUERA {x['producto_odepa']} ({x['serie']}): {x['motivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

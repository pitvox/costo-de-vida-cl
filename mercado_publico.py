"""
mercado_publico.py: precio neto por kilo que pagan los organismos públicos
por 15 alimentos, por mes, nacional y por macrozona. Piloto aprobado por
Pedro el 12-11-2026.

Corre aparte de indices.py (no lo importa ni lo toca) y aparte del sitio:
build_site.py no lo lee y la salida no va a datos/ (el deploy copia datos/
entero) ni al repo. Lo corre a mano el workflow precio_pagado.yml, que deja
el resultado como artifact. Es material para ventas, no se publica.

Fuente: ChileCompra, datos abiertos de Mercado Público, descarga masiva de
órdenes de compra. Un zip por mes desde 2007, actualizado a diario con un
día de desfase, en
https://transparenciachc.blob.core.windows.net/oc-da/AAAA-M.zip
(mes sin cero a la izquierda). Trae un CSV con una fila por línea de orden
de compra: separador punto y coma, windows-1252, texto entre comillas y
saltos de línea dentro de algunos campos. Las columnas se leen por nombre
(78 hasta 2020, 79 en 2026). Términos de ChileCompra: reutilización
permitida citando la fuente y sin sobrecargar el sistema, así que los meses
se bajan de a uno.

Qué hace, por mes:
  1. Deja las líneas de alimentos (código ONU que empieza con 50), en estado
     Aceptada o Recepción Conforme, en pesos, con precio neto mayor que cero
     y con unidad de medida por kilo.
  2. Asigna producto por la categoría genérica más el texto de las dos
     especificaciones (PRODUCTOS). Una línea que calza con más de un
     producto toma el primero de la lista.
  3. Descarta errores de captura: precios bajo un quinto o sobre cinco veces
     la mediana nacional del producto en el mes.
  4. Por producto, mes y zona (nacional y macrozonas): mediana, cuartiles,
     líneas, compradores distintos (organismo) y proveedores distintos. La
     celda es utilizable con al menos 30 líneas, 5 compradores y 5
     proveedores.

Privacidad: los códigos de comprador y proveedor solo se cuentan en memoria;
ningún archivo de salida trae nombres, RUT ni códigos.

Los precios son netos de IVA y nominales.

Correr:
  python mercado_publico.py --anio 2026 --salida precio_pagado_2026.csv
  python mercado_publico.py --mes 2026-10 --salida octubre.csv
"""

import argparse
import csv
import datetime
import io
import os
import re
import sys
import tempfile
import unicodedata
import zipfile
from statistics import median

import requests

URL = "https://transparenciachc.blob.core.windows.net/oc-da/{anio}-{mes}.zip"
FUENTE = "ChileCompra, datos abiertos de Mercado Público"

MIN_LINEAS, MIN_COMPRADORES, MIN_PROVEEDORES = 30, 5, 5
FACTOR_LIMPIEZA = 5.0

COLUMNAS = {
    "estado": "Estado",
    "region": "RegionUnidadCompra",
    "organismo": "CodigoOrganismoPublico",
    "proveedor": "CodigoProveedor",
    "onu": "codigoProductoONU",
    "generico": "NombreroductoGenerico",
    "esp_comprador": "EspecificacionComprador",
    "esp_proveedor": "EspecificacionProveedor",
    "unidad": "UnidadMedida",
    "moneda": "monedaItem",
    "precio": "precioNeto",
}

VERDURAS = ("verduras frescas",)
FRUTAS = ("fruta fresca",)
CARNES = ("carne de ave o carne fresca", "carnes frescas procesadas y preparadas")
PAN = ("pan fresco",)
AZUCAR = ("productos de edulcorantes o azucares naturales",)
HARINA = ("harina de trigo",)

# (producto, categorías genéricas admitidas o None para cualquiera, patrón)
PRODUCTOS = [
    ("papa", VERDURAS, r"\bpapas?\b"),
    ("tomate", VERDURAS, r"tomate"),
    ("cebolla", VERDURAS, r"cebolla"),
    ("zanahoria", VERDURAS, r"zanahoria"),
    ("zapallo", VERDURAS, r"zapallo"),
    ("platano", FRUTAS, r"platano"),
    ("manzana", FRUTAS, r"manzana"),
    ("naranja", FRUTAS, r"naranja"),
    ("pollo", CARNES, r"pollo|pechuga|trutro"),
    ("vacuno", CARNES, r"vacuno|posta|molida|asiento|lomo|osobuco|choclillo|plateada|tapapecho"),
    ("cerdo", CARNES, r"cerdo|chuleta"),
    ("pan", PAN, r"\bpan\b|hallulla|marraqueta|batido"),
    ("azucar", AZUCAR, r"azucar"),
    ("harina", HARINA, r"harina"),
    ("arroz", None, r"\barroz\b"),
]
# preparaciones que no son el insumo crudo ("asado de tira" es un corte y
# entra; "pollo asado" es una preparación y no; congelado sigue siendo crudo)
EXCLUIR = re.compile(r"pollos? asados?|cocid[oa]|apanad|nugget|hamburgues|frit[oa]s?\b|"
                     r"empanad|pure\b|sopa|deshidratad|en polvo|al jugo|conserva")

ZONAS = [
    ("Norte", ("arica", "tarapaca", "antofagasta", "atacama", "coquimbo")),
    ("Centro", ("valparaiso", "higgins", "maule")),
    ("RM", ("metropolitana",)),
    ("Sur", ("nuble", "biobio", "bio bio", "araucania", "los rios", "los lagos",
             "aysen", "aisen", "magallanes")),
]
NACIONAL = "Nacional"
ESTADOS = ("aceptada", "recepcion conforme")


def norm(s: str) -> str:
    """Minúsculas y sin tildes."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def numero(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def zona(region: str):
    r = norm(region)
    for nombre, claves in ZONAS:
        if any(c in r for c in claves):
            return nombre
    return None


def producto(generico: str, texto: str):
    g, t = norm(generico), norm(texto)
    if EXCLUIR.search(t):
        return None
    for nombre, cats, patron in PRODUCTOS:
        if cats is not None and g not in cats:
            continue
        if re.search(patron, t):
            return nombre
    return None


def es_kilo(unidad: str) -> bool:
    u = norm(unidad)
    return u.startswith("kilo") or u in ("kg", "kgs")


def lineas(filas, mes: str):
    """Lee las filas del CSV (la primera es el encabezado) y devuelve las
    líneas que entran, como dicts con mes, producto, zona, precio, organismo
    y proveedor. Falla si falta una columna."""
    filas = iter(filas)
    enc = [c.strip() for c in next(filas)]
    faltan = [c for c in COLUMNAS.values() if c not in enc]
    if faltan:
        raise ValueError(f"{mes}: faltan columnas {faltan}")
    i = {k: enc.index(c) for k, c in COLUMNAS.items()}
    n = len(enc)
    out = []
    for f in filas:
        if len(f) < n:
            continue
        if not f[i["onu"]].strip().startswith("50"):
            continue
        if norm(f[i["estado"]]) not in ESTADOS:
            continue
        if f[i["moneda"]].strip().upper() != "CLP" or not es_kilo(f[i["unidad"]]):
            continue
        p = numero(f[i["precio"]])
        if not p or p <= 0:
            continue
        prod = producto(f[i["generico"]], f[i["esp_comprador"]] + " " + f[i["esp_proveedor"]])
        if not prod:
            continue
        out.append({"mes": mes, "producto": prod, "zona": zona(f[i["region"]]),
                    "precio": p, "organismo": f[i["organismo"]].strip(),
                    "proveedor": f[i["proveedor"]].strip()})
    return out


def leer_zip(ruta: str, mes: str):
    with zipfile.ZipFile(ruta) as zf:
        miembro = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(miembro) as crudo:
            texto = io.TextIOWrapper(crudo, encoding="cp1252", errors="replace", newline="")
            return lineas(csv.reader(texto, delimiter=";", quotechar='"'), mes)


def bajar(anio: int, mes: int, carpeta: str) -> str:
    ruta = os.path.join(carpeta, f"{anio}-{mes}.zip")
    with requests.get(URL.format(anio=anio, mes=mes), stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(ruta, "wb") as fh:
            for trozo in r.iter_content(1 << 20):
                fh.write(trozo)
    return ruta


def limpiar(ls: list) -> tuple:
    """Saca los precios fuera de [mediana/5, mediana*5] de la mediana nacional
    del producto en el mes. Devuelve (líneas que quedan, descartadas)."""
    meds = {}
    for k in {(l["mes"], l["producto"]) for l in ls}:
        meds[k] = median(l["precio"] for l in ls if (l["mes"], l["producto"]) == k)
    quedan = [l for l in ls
              if meds[(l["mes"], l["producto"])] / FACTOR_LIMPIEZA
              <= l["precio"] <= meds[(l["mes"], l["producto"])] * FACTOR_LIMPIEZA]
    return quedan, len(ls) - len(quedan)


def _cuartil(xs: list, q: float) -> float:
    xs = sorted(xs)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def agregar(ls: list) -> list:
    """Una fila por producto, mes y zona (nacional y cada macrozona con
    líneas). Sin códigos de comprador ni de proveedor: solo cuántos hay."""
    celdas = {}
    for l in ls:
        for z in (NACIONAL, l["zona"]):
            if z is None:
                continue
            c = celdas.setdefault((l["mes"], l["producto"], z), ([], set(), set()))
            c[0].append(l["precio"])
            c[1].add(l["organismo"])
            c[2].add(l["proveedor"])
    out = []
    for (mes, prod, z), (ps, orgs, provs) in sorted(celdas.items()):
        utilizable = (len(ps) >= MIN_LINEAS and len(orgs) >= MIN_COMPRADORES
                      and len(provs) >= MIN_PROVEEDORES)
        out.append({"mes": mes, "producto": prod, "zona": z, "lineas": len(ps),
                    "compradores": len(orgs), "proveedores": len(provs),
                    "p25": round(_cuartil(ps, 0.25)), "mediana": round(median(ps)),
                    "p75": round(_cuartil(ps, 0.75)),
                    "utilizable": "si" if utilizable else "no"})
    return out


CAMPOS = ["mes", "producto", "zona", "lineas", "compradores", "proveedores",
          "p25", "mediana", "p75", "utilizable"]


def meses(anio: int = None, mes: str = None):
    if mes:
        a, m = mes.split("-")
        return [(int(a), int(m))]
    hoy = datetime.date.today()
    ultimo = 12 if anio < hoy.year else hoy.month - 1
    return [(anio, m) for m in range(1, ultimo + 1)]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--anio", type=int)
    g.add_argument("--mes", help="AAAA-M")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    if os.path.abspath(a.salida).startswith(os.path.abspath("datos") + os.sep):
        sys.exit("La salida no va en datos/: el deploy publica esa carpeta entera.")
    filas, descartes = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for anio, m in meses(a.anio, a.mes):
            etiqueta = f"{anio}-{m:02d}"
            ruta = bajar(anio, m, tmp)
            ls, d = limpiar(leer_zip(ruta, etiqueta))
            os.remove(ruta)
            descartes += d
            filas += agregar(ls)
            print(f"{etiqueta}: {len(ls)} líneas por kilo de los 15 productos, {d} descartadas")
    with open(a.salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(filas)
    print(f"Escrito {a.salida}: {len(filas)} celdas. Fuente: {FUENTE}.")


if __name__ == "__main__":
    main()

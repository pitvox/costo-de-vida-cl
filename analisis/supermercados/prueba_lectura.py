#!/usr/bin/env python3
"""Prueba de lectura de las páginas de búsqueda de jumbo.cl y santaisabel.cl.

Prueba técnica aislada del 20-11-2026 (ver claude/Prompt_prueba_supermercados.md):
saber si esas páginas se pueden leer desde GitHub Actions igual que desde un
navegador normal. No toca el sitio, indices.py, build_site.py, datos/,
resumen.json ni la metodología, y ninguna cifra de aquí va al sitio, a
textos/, a correos ni a redes. No cambia la regla de "sin scraping": es una
sola corrida de prueba, sin calendario.

Para cada término de TERMINOS y cada sitio de SITIOS:

  Fase A, pedido simple: un GET con requests a /busqueda?ft=<término>.
    Anota estado HTTP, bytes, cuántas veces aparece "x kg", "x lt" o "x un"
    y si el HTML trae nombres de producto. También lee las tarjetas del
    texto del <main> del HTML, con el mismo lector de la fase B.
  Fase B, navegador sin interfaz: la misma URL con Playwright (Chromium),
    espera a que cargue, toma el innerText de <main>, lo corta en cada
    "Agregar" y saca de cada tarjeta nombre, marca, precio vigente, precio
    anterior si hay oferta y precio por unidad con su unidad. Guarda las
    primeras 8.

Salida, en la carpeta de --salida: resultado.csv, resumen.md, corrida.json
(lo que pasó en cada pedido) y crudo/ (el texto que se leyó de cada página,
sin scripts), para volver a leer las tarjetas sin pedir nada otra vez
(--desde-crudo).

Reglas de la prueba, que no se negocian:

- Sin saltar barreras. Un 401, 403, 407, 429, un captcha o una página de
  desafío se anota "bloqueado" con lo que se vio, y a ese sitio no se le
  pide nada más: ni reintento ni la otra fase. Tampoco se insiste si el
  sitio no responde (tiempo agotado, conexión cortada) o responde 5xx: puede
  ser un bloqueo callado.
- El User-Agent de las dos fases termina en UA_SUFIJO. La fase A usa el de
  requests y la B el de Chromium sin interfaz ("HeadlessChrome"), cada uno
  con el sufijo. Sin plugins para ocultar el navegador, sin proxies (la
  fase A ignora los del entorno), sin rotar IP y sin cabeceras copiadas de
  otro navegador.
- Solo las páginas de búsqueda: ninguna API, sin sesión (ninguna fase guarda
  cookies de un pedido a otro), sin elegir local. La fase B corre con JavaScript apagado y el
  navegador deja salir solo el documento de la búsqueda y sus redirecciones
  dentro de /busqueda del mismo sitio que robots.txt permita. Hojas de
  estilo, scripts, imágenes, iframes, XHR y cualquier otro subpedido se
  frenan dentro del navegador, antes de salir (intercepción de Chromium con
  Fetch.requestPaused). Así cada pedido es una sola página, la página no
  puede llamar a /api/ ni a /_next/ y no puede resolver un desafío.
- Como máximo 32 pedidos de búsqueda en la corrida (8 términos, 2 sitios, 2
  fases), más el robots.txt de cada sitio. Uno a la vez y con PAUSA
  segundos o más entre pedidos al mismo sitio (nunca menos de 3 ni menos
  que su Crawl-delay), contados desde que termina el anterior.
- robots.txt primero: no se pide ninguna URL que bloquee para "*" (ni para
  CarestiaPrueba, si lo nombrara). Si robots.txt no responde, el sitio no se
  prueba; si no existe (404), no hay reglas.

Uso:
    python analisis/supermercados/prueba_lectura.py --salida salida
    python analisis/supermercados/prueba_lectura.py --desde-crudo salida
"""
import argparse
import csv
import datetime as dt
import functools
import json
import os
import platform
import re
import sys
import time
import unicodedata
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

TERMINOS = ["posta paleta", "trutro entero pollo", "arroz grado 2", "papa",
            "tomate", "cebolla", "aceite vegetal", "marraqueta"]
SITIOS = {"jumbo.cl": "https://www.jumbo.cl",
          "santaisabel.cl": "https://www.santaisabel.cl"}
RUTA_BUSQUEDA = "/busqueda"
UA_SUFIJO = "CarestiaPrueba/0.1 (+https://carestia.cl; contacto@carestia.cl)"
AGENTE_ROBOTS = "carestiaprueba"
PAUSA = 5.0                 # segundos entre pedidos al mismo sitio
PAUSA_MINIMA = 3.0          # la regla de la prueba: nunca menos
TOPE_BUSQUEDAS = 32         # 8 términos, 2 sitios, 2 fases
TARJETAS_POR_PAGINA = 8
MAX_REDIRECCIONES = 2
TIEMPO_CONEXION = 10
TIEMPO_LECTURA = 40
TIEMPO_PAGINA_MS = 45_000
# rutas que la prueba no lee aunque robots.txt las permita
RUTAS_PROHIBIDAS = ("/api/", "/_next/")
FASES = {"A": "pedido simple", "B": "navegador sin interfaz"}
COLUMNAS = ["sitio", "fase", "término", "posición", "nombre", "marca", "precio",
            "precio_unidad", "unidad", "oferta"]
# resultados de un pedido que frenan al sitio: no se le pide nada más
DETIENEN = ("bloqueado", "sin respuesta", "error del servidor")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# ---------------------------------------------------------------- formato

def miles(n) -> str:
    """1104233 -> "1.104.233"; 2111.5 -> "2.111,5"."""
    if n is None:
        return ""
    if isinstance(n, float) and not n.is_integer():
        entero, dec = f"{n:.2f}".rstrip("0").split(".")
        return f"{int(entero):,}".replace(",", ".") + "," + dec
    return f"{int(n):,}".replace(",", ".")


def pesos(n) -> str:
    return "" if n is None else "$" + miles(n)


def segundos(s: float) -> str:
    return f"{s:.1f}".replace(".", ",") + " s"


def duracion(s: float) -> str:
    m, s = divmod(int(round(s)), 60)
    seg = f"{s} segundo{'' if s == 1 else 's'}"
    return seg if m == 0 else f"{m} minuto{'' if m == 1 else 's'} {seg}"


def fecha_larga(d) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def ahora_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def hora_santiago(d: dt.datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return d.astimezone(ZoneInfo("America/Santiago")).strftime("%H:%M")
    except Exception:  # sin base de zonas horarias: solo UTC
        return ""


def url_busqueda(base: str, termino: str) -> str:
    return f"{base}{RUTA_BUSQUEDA}?ft={quote(termino, safe='')}"


def ruta_de(url: str) -> str:
    p = urlsplit(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(s).lower()).strip("-")


# ---------------------------------------------------------------- robots.txt

@functools.lru_cache(maxsize=None)
def _regex_robots(patron: str):
    fin = patron.endswith("$")
    if fin:
        patron = patron[:-1]
    cuerpo = "".join(".*" if c == "*" else re.escape(c) for c in patron)
    return re.compile(cuerpo + (r"\Z" if fin else ""), re.S)


class Robots:
    """robots.txt según RFC 9309, con comodín (*) y fin de ruta ($).

    Una URL se pide solo si la permiten las reglas de los grupos "*" y,
    si existe, también las del grupo que nombre a AGENTE_ROBOTS. Dentro de
    cada uno manda la regla más larga y, a igual largo, Allow. Se compara la
    ruta tal como se pide y también decodificada: si una de las dos queda
    bloqueada, no se pide."""

    def __init__(self, texto: str, agente: str = AGENTE_ROBOTS):
        grupos, actual, en_agentes = [], None, False
        for cruda in texto.lstrip("﻿").splitlines():
            linea = cruda.split("#", 1)[0].strip()
            if ":" not in linea:
                continue
            clave, valor = (p.strip() for p in linea.split(":", 1))
            clave = clave.lower()
            if clave == "user-agent":
                if actual is None or not en_agentes:
                    actual = {"agentes": set(), "reglas": [], "crawl_delay": None}
                    grupos.append(actual)
                actual["agentes"].add(valor.lower())
                en_agentes = True
            elif clave in ("allow", "disallow"):
                en_agentes = False
                if actual is not None and valor:
                    actual["reglas"].append((clave == "allow", valor))
            elif clave == "crawl-delay":
                en_agentes = False
                if actual is not None:
                    try:
                        actual["crawl_delay"] = float(valor.replace(",", "."))
                    except ValueError:
                        pass
        self.estrella = [g for g in grupos if "*" in g["agentes"]]
        self.propios = [g for g in grupos if agente.lower() in g["agentes"]]

    @staticmethod
    def _permite_en(grupos, ruta: str) -> bool:
        mejor = None                       # (largo de la regla, es Allow)
        for g in grupos:
            for permitir, patron in g["reglas"]:
                if any(_regex_robots(p).match(ruta) for p in {patron, unquote(patron)}):
                    clave = (len(patron), permitir)
                    if mejor is None or clave > mejor:
                        mejor = clave
        return True if mejor is None else mejor[1]

    def permite(self, ruta: str) -> bool:
        if not ruta.startswith("/"):
            ruta = "/" + ruta
        if ruta == "/robots.txt":
            return True
        formas = {ruta, unquote(ruta)}
        for grupos in (self.estrella, self.propios):
            if grupos and not all(self._permite_en(grupos, f) for f in formas):
                return False
        return True

    @property
    def crawl_delay(self):
        v = [g["crawl_delay"] for g in self.estrella + self.propios
             if g["crawl_delay"] is not None]
        return max(v) if v else None

    def resumen(self) -> str:
        reglas = [r for g in self.estrella for r in g["reglas"]]
        n_dis = sum(1 for permitir, _ in reglas if not permitir)
        n_all = len(reglas) - n_dis
        txt = f"{n_dis} Disallow y {n_all} Allow para *"
        if self.propios:
            txt += ", y un grupo propio para CarestiaPrueba"
        return txt


# ------------------------------------------------- texto visible de un HTML

_BLOQUE = {"address", "article", "aside", "blockquote", "body", "button", "caption",
           "dd", "details", "dialog", "div", "dl", "dt", "fieldset", "figcaption",
           "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
           "hgroup", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "summary",
           "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul"}
_SALTAR = {"script", "style", "noscript", "template", "svg", "math", "head", "title",
           "iframe", "object", "canvas", "select", "datalist", "textarea"}
_VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
           "meta", "param", "source", "track", "wbr"}
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.I)


class _Texto(HTMLParser):
    """Aproxima el innerText: una línea por bloque, sin scripts ni ocultos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.saltar = 0
        self.oculto = None          # [etiqueta, profundidad] del elemento oculto

    def handle_starttag(self, tag, attrs):
        if self.oculto is not None:
            if tag == self.oculto[0] and tag not in _VACIOS:
                self.oculto[1] += 1
            return
        if self.saltar:
            if tag in _SALTAR and tag not in _VACIOS:
                self.saltar += 1
            return
        if tag in _SALTAR:
            self.saltar = 1
            return
        atributos = dict(attrs)
        if tag not in _VACIOS and ("hidden" in atributos
                                   or _DISPLAY_NONE.search(atributos.get("style") or "")):
            self.oculto = [tag, 1]
            return
        if tag == "br" or tag in _BLOQUE:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if self.oculto is not None:
            if tag == self.oculto[0]:
                self.oculto[1] -= 1
                if self.oculto[1] == 0:
                    self.oculto = None
            return
        if self.saltar:
            if tag in _SALTAR:
                self.saltar -= 1
            return
        if tag in _BLOQUE:
            self.partes.append("\n")

    def handle_data(self, data):
        if self.oculto is None and not self.saltar:
            self.partes.append(data)


def texto_de_html(html: str):
    """(texto, hubo_main): el texto visible del <main>, o del <body> si no
    hay <main>, con una línea por bloque. Es la versión sin navegador del
    innerText que lee la fase B."""
    m = re.search(r"<main\b[^>]*>(.*)</main\s*>", html, re.I | re.S)
    hubo_main = m is not None
    if m is None:
        m = re.search(r"<body\b[^>]*>(.*)</body\s*>", html, re.I | re.S)
    lector = _Texto()
    lector.feed(m.group(1) if m else html)
    lector.close()
    lineas = (" ".join(l.split()) for l in "".join(lector.partes).split("\n"))
    return "\n".join(l for l in lineas if l), hubo_main


def titulo_de_html(html: str) -> str:
    m = re.search(r"<title\b[^>]*>(.*?)</title\s*>", html, re.I | re.S)
    return " ".join(unescape(m.group(1)).split()) if m else ""


# ---------------------------------------------------------------- tarjetas
#
# El innerText de cada tarjeta, según la lectura desde Chrome, va así:
#     [etiqueta de oferta]    "Oferta", "Santa Ofertas", "Lleva 2 por $3.000"
#     $vigente [$anterior]    dos precios seguidos si hay oferta
#     [x 500 g]               presentación, en los productos a granel
#     $1.945 x kg             precio por unidad (x kg, x lt o x un)
#     marca
#     nombre
#     Agregar
# Sin las hojas de estilo (la fase B no las baja) puede cambiar el corte de
# líneas: piezas que iban en líneas separadas quedan juntas ("Oferta$2.890$3.990")
# o al revés ("$1.945" y "x kg"). Por eso cada línea se parte en piezas
# (texto, precio, presentación, unidad, Agregar) y la tarjeta se arma con las
# piezas: el ancla es el precio por unidad; hacia atrás quedan los precios y
# la etiqueta, hacia adelante la marca y el nombre.

_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_UNI = r"kgs?|kilos?|grs?|g|lts?|litros?|l|ml|cc|unidad(?:es)?|unid|und|un|c/u"
_PRECIO = re.compile(r"\$\s?(" + _NUM + r")")
_TRAS_PRECIO = re.compile(r"\s*(?:x|por|/)\s*(?:(" + _NUM + r")\s*)?(" + _UNI + r")\.?(?![\w/])", re.I)
_PRESENTACION = re.compile(r"(?:x|por)\s*(" + _NUM + r")\s*(" + _UNI + r")\.?", re.I)
_UNIDAD_SOLA = re.compile(r"(?:x|por|/)\s*(" + _UNI + r")\.?", re.I)
# "Lleva 2 por $3.000", "3 x $5.000", "2do a $990": el precio es de la etiqueta
_CONECTOR = re.compile(r"(?:^|\s)(?:por|x|a|desde|hasta|de|con|en)\s*$", re.I)
_AGREGAR = re.compile(r"(.*?)\s*(Agregar|AGREGAR)(?: al carro| AL CARRO)?")
_ETIQUETA = re.compile(
    r"ofert|imbatible|lleva\s*\d|ll[eé]vate|\d+\s*(?:x|por)\s*\$|descuento|dcto|promo"
    r"|precio\s+especial|liquidaci|\d+\s*%|ahorra|exclusiv|cyber|black|\b2do\b|segunda"
    r"|club|tarjeta|cencosud|rebaja|nuevo\s+precio|baj[oó]\s+de\s+precio", re.I)


def a_numero(s: str):
    """"1.945" -> 1945; "2.111,5" -> 2111.5; "1,945" -> 1945; "990" -> 990."""
    s = s.strip().replace(" ", "")
    if "." in s and "," in s:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        s = s.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        partes = s.split(sep)
        s = "".join(partes) if all(len(p) == 3 for p in partes[1:]) else s.replace(sep, ".")
    v = float(s)
    return int(v) if v.is_integer() else round(v, 2)


def _unidad(u: str) -> str:
    u = u.lower().rstrip(".")
    if u.startswith("k"):
        return "kg"
    if u in ("l", "lt", "lts") or u.startswith("litro"):
        return "lt"
    if u.startswith("un") or u in ("und", "c/u"):
        return "un"
    if u.startswith("gr"):
        return "g"
    return u


def _piezas_linea(linea: str) -> list:
    s = " ".join(linea.split())
    if not s:
        return []
    m = _AGREGAR.fullmatch(s)
    if m:
        return _piezas_linea(m.group(1)) + [("agregar", None)]
    m = _PRESENTACION.fullmatch(s)
    if m:
        return [("pres", f"x {m.group(1)} {_unidad(m.group(2))}")]
    m = _UNIDAD_SOLA.fullmatch(s)
    if m:
        return [("unidad", _unidad(m.group(1)))]
    if not _PRECIO.search(s):
        return [("texto", s)]
    piezas, texto, pos = [], "", 0
    for m in _PRECIO.finditer(s):
        if m.start() < pos:
            continue
        texto += s[pos:m.start()]
        if texto.strip() and _CONECTOR.search(texto):
            texto += m.group(0)            # el precio es parte de la etiqueta
            pos = m.end()
            continue
        if texto.strip():
            piezas.append(("texto", texto.strip()))
        texto = ""
        piezas.append(("precio", a_numero(m.group(1))))
        pos = m.end()
        tras = _TRAS_PRECIO.match(s, pos)
        if tras:
            if tras.group(1):
                piezas.append(("pres", f"x {tras.group(1)} {_unidad(tras.group(2))}"))
            else:
                piezas.append(("unidad", _unidad(tras.group(2))))
            pos = tras.end()
    texto += s[pos:]
    if texto.strip():
        piezas.append(("texto", texto.strip()))
    return piezas


def piezas(texto: str) -> list:
    """Las piezas del texto en orden; un precio seguido de su unidad queda
    como una sola pieza "pu" (precio por unidad)."""
    crudas = [p for linea in texto.splitlines() for p in _piezas_linea(linea)]
    juntas = []
    for p in crudas:
        if p[0] == "unidad":
            if juntas and juntas[-1][0] == "precio":
                juntas[-1] = ("pu", (juntas[-1][1], p[1]))
            continue
        juntas.append(p)
    return juntas


def _tarjeta(ps: list, i: int):
    ancla = ps[i]
    precio_unidad = unidad = None
    precios, presentacion = [], None
    if ancla[0] == "pu":
        precio_unidad, unidad = ancla[1]
    else:                                   # ancla de respaldo: el último precio
        precios = [ancla[1]]
    j = i - 1
    while j >= 0 and len(precios) < 2 and ps[j][0] in ("precio", "pres"):
        if ps[j][0] == "precio":
            precios.insert(0, ps[j][1])
        elif presentacion is None:
            presentacion = ps[j][1]
        j -= 1
    etiqueta = ""
    if j >= 0 and ps[j][0] == "texto" and _ETIQUETA.search(ps[j][1]):
        etiqueta = ps[j][1]
    textos, k = [], i + 1
    while k < len(ps) and ps[k][0] == "texto":
        textos.append(ps[k][1])
        k += 1
    # sin "Agregar" entre tarjetas, la etiqueta de la siguiente no es nombre
    if (len(textos) >= 2 and k < len(ps) and ps[k][0] in ("precio", "pu")
            and _ETIQUETA.search(textos[-1])):
        textos.pop()
    marca, nombre = (textos[0], textos[1]) if len(textos) >= 2 else ("", textos[0] if textos else "")
    if not precios and precio_unidad is not None:
        precios = [precio_unidad]           # solo muestra el precio por unidad
    if not precios:
        return None
    vigente = precios[0]
    anterior = precios[1] if len(precios) > 1 else None
    if anterior is not None:
        if anterior == vigente:             # el mismo precio dos veces: no es oferta
            anterior = None
        elif anterior < vigente:            # el anterior es el más alto
            vigente, anterior = anterior, vigente
    oferta = ", ".join(x for x in (etiqueta, f"antes {pesos(anterior)}" if anterior else "") if x)
    return {"nombre": nombre, "marca": marca, "precio": vigente, "precio_anterior": anterior,
            "etiqueta": etiqueta, "presentacion": presentacion,
            "precio_unidad": precio_unidad, "unidad": unidad, "oferta": oferta}


def leer_tarjetas(texto: str, tope: int = TARJETAS_POR_PAGINA) -> list:
    """Las primeras `tope` tarjetas del innerText de una página de búsqueda."""
    ps = piezas(texto)
    anclas = [i for i, p in enumerate(ps) if p[0] == "pu"]
    # tramos que terminan en "Agregar" sin precio por unidad: se anclan en su último precio
    inicio = 0
    for k, p in enumerate(ps):
        if p[0] != "agregar":
            continue
        tramo = range(inicio, k)
        if not any(ps[x][0] == "pu" for x in tramo):
            con_precio = [x for x in tramo if ps[x][0] == "precio"]
            if con_precio:
                anclas.append(con_precio[-1])
        inicio = k + 1
    tarjetas = []
    for i in sorted(set(anclas)):
        t = _tarjeta(ps, i)
        if t is None:
            continue
        clave = (t["nombre"], t["marca"], t["precio"], t["precio_unidad"], t["unidad"])
        if tarjetas and clave == tarjetas[-1]["_clave"]:
            continue                        # la misma tarjeta repetida (copia oculta)
        t["_clave"] = clave
        tarjetas.append(t)
        if len(tarjetas) == tope:
            break
    for n, t in enumerate(tarjetas, 1):
        del t["_clave"]
        t["posicion"] = n
    return tarjetas


# ------------------------------------------------------- datos de la fase A

_UNIDADES_HTML = re.compile(r"(?<![a-zA-Z])x\s?(kg|lt|un)\b", re.I)
_NOMBRE_DATO = re.compile(
    r'"(?:productName|name|nombre|productTitle)"\s*:\s*"((?:[^"\\]|\\.){3,200})"')


def contar_unidades(html: str) -> dict:
    """Cuántas veces aparece "x kg", "x lt" o "x un" en el HTML."""
    limpio = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    conteo = {"kg": 0, "lt": 0, "un": 0}
    for m in _UNIDADES_HTML.finditer(limpio):
        conteo[m.group(1).lower()] += 1
    return conteo


def nombres_en_datos(html: str, termino: str) -> list:
    """Nombres con la primera palabra del término en los datos que trae la
    página (JSON dentro del HTML): una señal de que el HTML trae productos
    aunque su marcado no se deje leer."""
    clave = sin_tildes(termino.split()[0]).lower()
    vistos = []
    for m in _NOMBRE_DATO.finditer(html):
        try:
            valor = json.loads('"' + m.group(1) + '"')
        except ValueError:
            valor = m.group(1)
        if clave in sin_tildes(valor).lower() and valor not in vistos:
            vistos.append(valor)
    return vistos


# ---------------------------------------------------------------- bloqueos

# marcas que solo traen las páginas de desafío o de bloqueo, no las normales
_DESAFIO_HTML = [
    ("Cloudflare", re.compile(r"cf_chl_opt|/cdn-cgi/challenge-platform/h/|cf-chl-widget"
                              r"|challenges\.cloudflare\.com", re.I)),
    ("Imperva", re.compile(r"incapsula incident id|request unsuccessful\. incapsula", re.I)),
    ("DataDome", re.compile(r"captcha-delivery\.com", re.I)),
    ("HUMAN (PerimeterX)", re.compile(r"id=[\"']px-captcha|_pxcaptcha", re.I)),
    ("Akamai", re.compile(r"/_sec/cp_challenge|sec-if-cpt-container|errors\.edgesuite\.net", re.I)),
    ("AWS WAF", re.compile(r"captcha\.awswaf|awswafcaptcha", re.I)),
    ("Imperva o Distil", re.compile(r"pardon our interruption", re.I)),
]
# marcas genéricas: solo cuentan en el título o en un texto visible corto
_DESAFIO_TEXTO = re.compile(
    r"captcha|just a moment|attention required|access denied|acceso denegado"
    r"|verify (?:that )?you are (?:a )?human|are you a robot|eres un robot|no soy un robot"
    r"|verifica(?:r)? que eres|checking your browser|comprobando (?:tu|su) navegador"
    r"|request unsuccessful|pardon our interruption|forbidden", re.I)
_CABECERAS_VISTAS = ("server", "cf-ray", "cf-mitigated", "cf-cache-status", "x-datadome",
                     "x-iinfo", "x-cdn", "via", "x-cache", "akamai-grn", "x-akamai-transformed",
                     "content-type", "retry-after", "location", "x-amz-cf-pop")


def cabeceras_vistas(cabeceras: dict) -> dict:
    bajas = {k.lower(): v for k, v in (cabeceras or {}).items()}
    return {k: bajas[k][:120] for k in _CABECERAS_VISTAS if k in bajas}


def ver_bloqueo(estado, cabeceras: dict, html: str, texto: str, titulo: str, hay_precios: bool):
    """None si no hay señal de bloqueo; si no, qué se vio."""
    bajas = {k.lower(): v for k, v in (cabeceras or {}).items()}
    if estado in (401, 403, 407, 429):
        return f"HTTP {estado}"
    if bajas.get("cf-mitigated", "").lower() == "challenge":
        return "desafío de Cloudflare (cf-mitigated: challenge)"
    if hay_precios and (estado is None or estado < 500):
        return None                         # trae productos: no es una página de desafío
    for nombre, rx in _DESAFIO_HTML:
        if rx.search(html or ""):
            return f"página de desafío ({nombre})"
    if _DESAFIO_TEXTO.search(titulo or "") or (
            len(texto or "") < 5000 and _DESAFIO_TEXTO.search(texto or "")):
        return "página de desafío o captcha (por su texto)"
    return None


def lo_que_se_vio(estado, cabeceras: dict, titulo: str, texto: str) -> dict:
    return {"estado": estado, "cabeceras": cabeceras_vistas(cabeceras),
            "titulo": (titulo or "")[:200],
            "texto": " / ".join((texto or "").splitlines())[:400]}


# ------------------------------------------------------- ritmo y tope

def _reloj() -> float:
    return time.monotonic()


def _dormir(s: float):
    time.sleep(s)


class Ritmo:
    """Uno a la vez, con una pausa mínima entre pedidos al mismo sitio,
    contada desde que termina el anterior."""

    def __init__(self):
        self.pausas, self.fin = {}, {}

    def esperar(self, sitio: str):
        """Duerme lo que falte. Devuelve los segundos desde que terminó el
        pedido anterior a ese sitio (None si es el primero)."""
        if sitio not in self.fin:
            return None
        falta = self.fin[sitio] + self.pausas[sitio] - _reloj()
        if falta > 0:
            _dormir(falta)
        return _reloj() - self.fin[sitio]

    def termino(self, sitio: str):
        self.fin[sitio] = _reloj()


class Tope:
    def __init__(self, tope: int = TOPE_BUSQUEDAS):
        self.tope, self.usados = tope, 0

    def tomar(self):
        if self.usados >= self.tope:
            raise RuntimeError(f"se llegó al tope de {self.tope} pedidos de búsqueda")
        self.usados += 1


def pausa_del_sitio(pausa: float, base: str, crawl_delay) -> float:
    local = urlsplit(base).hostname in ("127.0.0.1", "localhost")
    return max(pausa, 0.0 if local else PAUSA_MINIMA, crawl_delay or 0.0)


def no_seguir(destino: str, robots: Robots, base: str, hechos: int):
    """Por qué no se sigue una redirección (None si se puede seguir)."""
    d, b = urlsplit(destino), urlsplit(base)
    if hechos >= MAX_REDIRECCIONES:
        return f"más de {MAX_REDIRECCIONES} redirecciones"
    if (d.scheme, d.hostname, d.port) != (b.scheme, b.hostname, b.port):
        return f"lleva a otro sitio ({d.scheme}://{d.netloc})"
    if any(d.path.startswith(p) for p in RUTAS_PROHIBIDAS):
        return "lleva a una ruta que la prueba no lee"
    if not robots.permite(ruta_de(destino)):
        return "robots.txt bloquea el destino"
    if not d.path.startswith(RUTA_BUSQUEDA):
        return "sale de la página de búsqueda"
    return None


# ---------------------------------------------------------------- fase A

def sesion_a():
    import requests
    from http.cookiejar import DefaultCookiePolicy
    s = requests.Session()
    s.trust_env = False                     # sin proxies ni otra configuración del entorno
    s.max_redirects = 5                     # solo para robots.txt (RFC 9309); la fase A no las sigue sola
    s.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))  # sin cookies: sin sesión
    s.headers["User-Agent"] = f"python-requests/{requests.__version__} {UA_SUFIJO}"
    return s


def decodificar(contenido: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w.:-]+)", content_type or "", re.I)
    try:
        return contenido.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        return contenido.decode("utf-8", errors="replace")


def bajar_robots(sesion, base: str):
    """(info, Robots o None). None: el sitio no se prueba."""
    import requests
    url = base + "/robots.txt"
    t0 = _reloj()
    info = {"url": url}
    try:
        r = sesion.get(url, timeout=(TIEMPO_CONEXION, TIEMPO_LECTURA))
    except requests.RequestException as e:
        info.update(resultado="sin respuesta", detalle=f"{type(e).__name__}: {e}"[:300],
                    dur=_reloj() - t0)
        return info, None
    texto = decodificar(r.content, r.headers.get("content-type", ""))
    info.update(estado=r.status_code, bytes=len(r.content), dur=_reloj() - t0,
                redirecciones=[h.headers.get("location", "") for h in r.history])
    bloqueo = ver_bloqueo(r.status_code, r.headers, texto, "", titulo_de_html(texto), False)
    if bloqueo:
        info.update(resultado="bloqueado", detalle=bloqueo,
                    visto=lo_que_se_vio(r.status_code, r.headers, titulo_de_html(texto),
                                        texto_de_html(texto)[0]))
        return info, None
    if r.status_code >= 500:
        info.update(resultado="sin respuesta", detalle=f"HTTP {r.status_code}")
        return info, None
    if r.status_code >= 400:                # no existe: sin reglas (RFC 9309)
        info.update(resultado="ok", detalle=f"HTTP {r.status_code}: sin robots.txt, sin reglas")
        return info, Robots("")
    if "<html" in texto[:2000].lower() and "user-agent" not in texto.lower():
        info.update(resultado="ok", detalle="devolvió HTML, no un robots.txt: sin reglas")
        return info, Robots("")
    info.update(resultado="ok", texto=texto[:20000])
    return info, Robots(texto)


def fase_a(sesion, base: str, termino: str, robots: Robots) -> dict:
    import requests
    url = url_busqueda(base, termino)
    p = {"url": url, "redirecciones": []}
    actual, t0 = url, _reloj()
    try:
        while True:
            r = sesion.get(actual, timeout=(TIEMPO_CONEXION, TIEMPO_LECTURA), allow_redirects=False)
            loc = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and loc:
                destino = urljoin(actual, loc)
                motivo = no_seguir(destino, robots, base, len(p["redirecciones"]))
                p["redirecciones"].append(destino)
                if motivo:
                    p.update(estado=r.status_code, bytes=len(r.content), dur=_reloj() - t0,
                             resultado="redirección no seguida", detalle=f"{destino}: {motivo}",
                             tarjetas=[])
                    return p
                r.close()
                actual = destino
                continue
            break
    except requests.RequestException as e:
        p.update(dur=_reloj() - t0, resultado="sin respuesta",
                 detalle=f"{type(e).__name__}: {e}"[:300], tarjetas=[])
        return p
    contenido = r.content
    html = decodificar(contenido, r.headers.get("content-type", ""))
    texto, hubo_main = texto_de_html(html)
    titulo = titulo_de_html(html)
    tarjetas = leer_tarjetas(texto)
    nombres = nombres_en_datos(html, termino)
    p.update(estado=r.status_code, bytes=len(contenido), dur=_reloj() - t0,
             titulo=titulo, hubo_main=hubo_main, unidades=contar_unidades(html),
             nombres_en_datos=len(nombres), ejemplos_nombres=nombres[:3],
             tarjetas=tarjetas, texto=texto, cabeceras=cabeceras_vistas(r.headers))
    bloqueo = ver_bloqueo(r.status_code, r.headers, html, texto, titulo, bool(tarjetas))
    if bloqueo:
        p.update(resultado="bloqueado", detalle=bloqueo,
                 visto=lo_que_se_vio(r.status_code, r.headers, titulo, texto))
    elif r.status_code >= 500:
        p.update(resultado="error del servidor", detalle=f"HTTP {r.status_code}",
                 visto=lo_que_se_vio(r.status_code, r.headers, titulo, texto))
    elif r.status_code >= 300:
        p.update(resultado="sin página", detalle=f"HTTP {r.status_code}")
    else:
        p.update(resultado="ok", detalle="con precios" if tarjetas else "sin precios")
    return p


# ---------------------------------------------------------------- fase B

class NavegadorB:
    """Chromium sin interfaz, con JavaScript apagado y una intercepción que
    deja salir solo el documento de la búsqueda (y sus redirecciones
    permitidas). Todo lo demás se frena antes de salir del navegador."""

    def __init__(self, pw):
        self.navegador = pw.chromium.launch(headless=True)
        previo = self.navegador.new_context()
        self.ua_base = previo.new_page().evaluate("navigator.userAgent")  # about:blank, sin red
        previo.close()
        self.ua = f"{self.ua_base} {UA_SUFIJO}"
        self.version = self.navegador.version
        # un contexto nuevo por pedido: sin cookies ni caché de la página anterior
        self.opciones = dict(user_agent=self.ua, java_script_enabled=False,
                             service_workers="block")

    def cerrar(self):
        self.navegador.close()

    @staticmethod
    def _decidir(ev: dict, marco: str, base: str, robots: Robots, estado: dict) -> str:
        """"sale" (el pedido sale a la red), "frena" (falla dentro del
        navegador) o "queda" (se contesta adentro con un 204 vacío: el
        navegador se queda en la página que ya tiene)."""
        if ev.get("resourceType") != "Document" or ev.get("frameId") != marco:
            return "frena"                  # subpedidos e iframes: no salen
        destino = ev["request"]["url"]
        if not estado["inicio"]:            # la búsqueda que se pidió
            estado["inicio"] = True
            d, b = urlsplit(destino), urlsplit(base)
            ok = ((d.scheme, d.hostname, d.port) == (b.scheme, b.hostname, b.port)
                  and d.path.startswith(RUTA_BUSQUEDA) and robots.permite(ruta_de(destino))
                  and not any(d.path.startswith(x) for x in RUTAS_PROHIBIDAS))
            return "sale" if ok else "frena"
        if ev.get("redirectedRequestId"):   # un salto de redirección del servidor
            motivo = no_seguir(destino, robots, base, len(estado["saltos"]))
            estado["saltos"].append(destino)
            if motivo:
                estado["frenada"] = f"{destino}: {motivo}"
                return "frena"
            return "sale"
        estado["extra"] = destino           # otra navegación (meta refresh, formulario)
        return "queda"

    def pedir(self, base: str, termino: str, robots: Robots) -> dict:
        from playwright.sync_api import Error as ErrorPW
        from playwright.sync_api import TimeoutError as TiempoPW
        url = url_busqueda(base, termino)
        p = {"url": url}
        estado = {"inicio": False, "saltos": [], "frenada": None, "extra": None,
                  "salieron": 0, "frenados": {}, "errores": []}
        contexto = self.navegador.new_context(**self.opciones)
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        marco = cdp.send("Page.getFrameTree")["frameTree"]["frame"]["id"]

        def pausado(ev):
            decision = "frena"
            try:
                decision = self._decidir(ev, marco, base, robots, estado)
            except Exception as e:          # ante la duda, no sale
                estado["errores"].append(repr(e)[:200])
            try:
                if decision == "sale":
                    estado["salieron"] += 1
                    cdp.send("Fetch.continueRequest", {"requestId": ev["requestId"]})
                    return
                tipo = ev.get("resourceType") or "Other"
                estado["frenados"][tipo] = estado["frenados"].get(tipo, 0) + 1
                if decision == "queda":
                    cdp.send("Fetch.fulfillRequest", {"requestId": ev["requestId"],
                                                      "responseCode": 204, "responseHeaders": [],
                                                      "body": ""})
                else:
                    cdp.send("Fetch.failRequest", {"requestId": ev["requestId"],
                                                   "errorReason": "BlockedByClient"})
            except Exception as e:
                estado["errores"].append(repr(e)[:200])

        # las respuestas del documento principal, por si la navegación termina con error
        respuestas = []
        pagina.on("response", lambda r: respuestas.append(r)
                  if r.frame == pagina.main_frame and r.request.is_navigation_request() else None)
        cdp.on("Fetch.requestPaused", pausado)
        cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
        t0 = _reloj()
        try:
            resp, error_nav = None, None
            try:
                resp = pagina.goto(url, wait_until="load", timeout=TIEMPO_PAGINA_MS)
            except (TiempoPW, ErrorPW) as e:
                error_nav = e
            if resp is None:                # la última respuesta del documento, si llegó
                finales = [r for r in respuestas if not 300 <= r.status < 400]
                resp = finales[-1] if finales else None
            p["dur"] = _reloj() - t0
            if resp is None:
                primera = str(error_nav or "sin respuesta").splitlines()[0][:300]
                if estado["frenada"]:
                    p.update(resultado="redirección no seguida", detalle=estado["frenada"])
                elif not estado["salieron"]:
                    p.update(resultado="error del script",
                             detalle=f"no salió ningún pedido: {primera}")
                elif isinstance(error_nav, TiempoPW):
                    p.update(resultado="sin respuesta", detalle=f"tiempo agotado: {primera}")
                else:
                    p.update(resultado="sin respuesta", detalle=f"error de red: {primera}")
                p["tarjetas"] = []
            else:
                self._leer(pagina, resp, p, error_nav, estado, ErrorPW)
        finally:
            try:
                contexto.close()
            except Exception:
                pass
        p["redirecciones"] = estado["saltos"]
        p["subpedidos"] = {"salieron": estado["salieron"], "frenados": estado["frenados"],
                           "navegacion_extra": estado["extra"], "errores": estado["errores"]}
        return p

    @staticmethod
    def _leer(pagina, resp, p: dict, error_nav, estado: dict, ErrorPW):
        """Lee la página que llegó: el innerText de <main> o, si la página ya
        no está (una navegación frenada la reemplazó), el HTML de la respuesta."""
        avisos = []
        if error_nav is not None:
            avisos.append("la navegación terminó con error: "
                          + str(error_nav).splitlines()[0][:200])
        try:
            cabeceras = resp.all_headers()
        except ErrorPW:
            cabeceras = dict(resp.headers)
        try:
            cuerpo = resp.body()
        except ErrorPW as e:
            cuerpo = b""
            avisos.append("no se pudo leer el HTML: " + str(e).splitlines()[0][:200])
        html = decodificar(cuerpo, cabeceras.get("content-type", ""))
        try:
            if not pagina.url.startswith(("http://", "https://")):
                raise ErrorPW(f"la página quedó en {pagina.url[:60]}")
            titulo = pagina.title()
            texto = pagina.evaluate(
                "() => { const m = document.querySelector('main'); return m ? m.innerText : null; }")
            hubo_main = texto is not None
            if texto is None:
                texto = pagina.evaluate("() => document.body ? document.body.innerText : ''")
            origen = "innerText"
        except ErrorPW as e:
            texto, hubo_main = texto_de_html(html)
            titulo = titulo_de_html(html)
            origen = "HTML de la respuesta"
            avisos.append("sin innerText (" + str(e).splitlines()[0][:150] + "): se leyó el HTML")
        if estado["extra"]:
            avisos.append(f"se frenó otra navegación, a {estado['extra']}")
        tarjetas = leer_tarjetas(texto)
        p.update(estado=resp.status, bytes=len(cuerpo), url_final=resp.url, titulo=titulo,
                 hubo_main=hubo_main, origen=origen, tarjetas=tarjetas, texto=texto,
                 cabeceras=cabeceras_vistas(cabeceras))
        if avisos:
            p["avisos"] = avisos
        bloqueo = ver_bloqueo(resp.status, cabeceras, html, texto, titulo, bool(tarjetas))
        if bloqueo:
            p.update(resultado="bloqueado", detalle=bloqueo,
                     visto=lo_que_se_vio(resp.status, cabeceras, titulo, texto))
        elif resp.status >= 500:
            p.update(resultado="error del servidor", detalle=f"HTTP {resp.status}",
                     visto=lo_que_se_vio(resp.status, cabeceras, titulo, texto))
        elif resp.status >= 300:
            p.update(resultado="sin página", detalle=f"HTTP {resp.status}")
        else:
            p.update(resultado="ok", detalle="con precios" if tarjetas else "sin precios")


# ---------------------------------------------------------------- corrida

def correr(salida: str, bases: dict, pausa: float) -> dict:
    inicio = ahora_utc()
    t0 = _reloj()
    corrida = {
        "inicio_utc": inicio.isoformat(timespec="seconds"),
        "sitios": list(bases), "bases": bases, "terminos": TERMINOS,
        "pausa_pedida": pausa, "pausas": {}, "tope": TOPE_BUSQUEDAS,
        "ua": {}, "robots": {}, "pedidos": [], "frenados": {},
        "entorno": {"python": platform.python_version(), "plataforma": platform.platform(),
                    "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                    "github_sha": os.environ.get("GITHUB_SHA"),
                    "runner": os.environ.get("ImageOS") or os.environ.get("RUNNER_OS")},
    }
    os.makedirs(os.path.join(salida, "crudo"), exist_ok=True)
    ritmo, tope = Ritmo(), Tope()
    robots = {}

    def anotar(p: dict, sitio: str, fase: str, termino, n_termino, desde):
        p.update(n=len(corrida["pedidos"]) + 1, sitio=sitio, fase=fase, termino=termino,
                 desde_anterior=desde)
        texto = p.pop("texto", None)
        if texto is not None:
            nombre = f"{fase}_{sitio}_{n_termino:02d}_{slug(termino)}.txt"
            with open(os.path.join(salida, "crudo", nombre), "w", encoding="utf-8") as fh:
                fh.write(texto)
            p["crudo"] = f"crudo/{nombre}"
        corrida["pedidos"].append(p)
        if p.get("resultado") in DETIENEN and sitio not in corrida["frenados"]:
            corrida["frenados"][sitio] = {"fase": fase, "termino": termino,
                                          "resultado": p["resultado"], "detalle": p.get("detalle")}
        guardar_corrida(salida, corrida)
        print(f"[{fase}] {sitio:15} {str(termino or ''):20} {p.get('estado', '-')!s:4} "
              f"{miles(p.get('bytes')):>10} bytes {len(p.get('tarjetas') or []):2} tarjetas "
              f"{p.get('resultado', '')}: {p.get('detalle', '')}"[:200], flush=True)

    sesion = sesion_a()
    corrida["ua"]["A"] = sesion.headers["User-Agent"]

    # 1. robots.txt de cada sitio, antes que nada
    for sitio, base in bases.items():
        ritmo.pausas[sitio] = pausa_del_sitio(pausa, base, None)
        inicio_p = ahora_utc()
        info, rob = bajar_robots(sesion, base)
        ritmo.termino(sitio)
        info["inicio_utc"] = inicio_p.isoformat(timespec="seconds")
        corrida["robots"][sitio] = info
        anotar(dict(info, url=info["url"], texto=None), sitio, "robots", None, 0, None)
        if rob is None:
            corrida["frenados"].setdefault(sitio, {"fase": "robots", "termino": None,
                                                   "resultado": info["resultado"],
                                                   "detalle": info.get("detalle")})
            continue
        robots[sitio] = rob
        info["crawl_delay"] = rob.crawl_delay
        info["reglas"] = rob.resumen()
        info["busqueda_permitida"] = all(rob.permite(ruta_de(url_busqueda(base, t))) for t in TERMINOS)
        ritmo.pausas[sitio] = pausa_del_sitio(pausa, base, rob.crawl_delay)
    corrida["pausas"] = dict(ritmo.pausas)

    def toca(sitio: str, base: str, fase: str, termino: str, n: int) -> bool:
        if sitio in corrida["frenados"]:
            return False
        if not robots[sitio].permite(ruta_de(url_busqueda(base, termino))):
            anotar({"url": url_busqueda(base, termino), "resultado": "no se pidió",
                    "detalle": "robots.txt bloquea esta búsqueda", "tarjetas": []},
                   sitio, fase, termino, n, None)
            return False
        return True

    # 2. fase A: pedido simple
    for n, termino in enumerate(TERMINOS, 1):
        for sitio, base in bases.items():
            if not toca(sitio, base, "A", termino, n):
                continue
            desde = ritmo.esperar(sitio)
            tope.tomar()
            inicio_p = ahora_utc()
            try:
                p = fase_a(sesion, base, termino, robots[sitio])
            except Exception as e:          # un error del script, no del sitio
                p = {"url": url_busqueda(base, termino), "resultado": "error del script",
                     "detalle": repr(e)[:300], "tarjetas": []}
            ritmo.termino(sitio)
            p["inicio_utc"] = inicio_p.isoformat(timespec="seconds")
            anotar(p, sitio, "A", termino, n, desde)

    # 3. fase B: navegador sin interfaz
    if any(s not in corrida["frenados"] for s in bases):
        nav = None
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                nav = NavegadorB(pw)
                corrida["ua"]["B"] = nav.ua
                corrida["chromium"] = nav.version
                for n, termino in enumerate(TERMINOS, 1):
                    for sitio, base in bases.items():
                        if not toca(sitio, base, "B", termino, n):
                            continue
                        previo = next((q for q in corrida["pedidos"] if q["sitio"] == sitio
                                       and q["fase"] == "A" and q["termino"] == termino), None)
                        if previo and previo.get("resultado") == "redirección no seguida":
                            anotar({"url": url_busqueda(base, termino), "resultado": "no se pidió",
                                    "detalle": "en la fase A redirige adonde la prueba no va: "
                                               + str(previo.get("detalle")), "tarjetas": []},
                                   sitio, "B", termino, n, None)
                            continue
                        desde = ritmo.esperar(sitio)
                        tope.tomar()
                        inicio_p = ahora_utc()
                        try:
                            p = nav.pedir(base, termino, robots[sitio])
                        except Exception as e:
                            p = {"url": url_busqueda(base, termino), "resultado": "error del script",
                                 "detalle": repr(e)[:300], "tarjetas": []}
                        ritmo.termino(sitio)
                        p["inicio_utc"] = inicio_p.isoformat(timespec="seconds")
                        anotar(p, sitio, "B", termino, n, desde)
                nav.cerrar()
        except Exception as e:              # Playwright o Chromium no partieron
            corrida["error_fase_b"] = repr(e)[:500]
            print(f"[B] la fase B no pudo correr: {e!r}"[:300], flush=True)

    corrida["fin_utc"] = ahora_utc().isoformat(timespec="seconds")
    corrida["segundos"] = round(_reloj() - t0, 1)
    corrida["busquedas_pedidas"] = tope.usados
    guardar_corrida(salida, corrida)
    return corrida


def guardar_corrida(salida: str, corrida: dict):
    ruta = os.path.join(salida, "corrida.json")
    with open(ruta + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(corrida, fh, ensure_ascii=False, indent=1)
    os.replace(ruta + ".tmp", ruta)


# ---------------------------------------------------------------- salidas

def busquedas(corrida: dict, sitio: str, fase: str) -> list:
    return [p for p in corrida["pedidos"] if p["sitio"] == sitio and p["fase"] == fase]


def _num_csv(v):
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else str(v)


def escribir_csv(salida: str, corrida: dict):
    with open(os.path.join(salida, "resultado.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNAS)
        for p in corrida["pedidos"]:
            if p["fase"] not in FASES:
                continue
            for t in p.get("tarjetas") or []:
                w.writerow([p["sitio"], p["fase"], p["termino"], t["posicion"], t["nombre"],
                            t["marca"], _num_csv(t["precio"]), _num_csv(t["precio_unidad"]),
                            t["unidad"] or "", t["oferta"]])


def _celda(s) -> str:
    return str(s if s is not None else "").replace("|", "/").replace("\n", " ")


def _estados(ps: list) -> str:
    conteo = {}
    for p in ps:
        clave = str(p["estado"]) if p.get("estado") is not None else p.get("resultado", "?")
        conteo[clave] = conteo.get(clave, 0) + 1
    if not conteo:
        return "no se pidió"
    if len(conteo) == 1:
        clave, n = next(iter(conteo.items()))
        return f"{clave} en {'la' if n == 1 else 'las'} {n}"
    return ", ".join(f"{k} en {v}" for k, v in conteo.items())


def _bloqueo_de(corrida: dict, sitio: str, fase: str, ps: list) -> str:
    for p in ps:
        if p.get("resultado") == "bloqueado":
            return f"sí: {p.get('detalle')} en \"{p['termino']}\""
        if p.get("resultado") in ("sin respuesta", "error del servidor"):
            return f"posible: {p['resultado']} en \"{p['termino']}\" ({p.get('detalle')})"
    frenado = corrida["frenados"].get(sitio)
    if frenado and frenado["fase"] != fase:
        if frenado["fase"] == "robots":
            return f"no se probó: robots.txt, {frenado['resultado']} ({frenado.get('detalle')})"
        if frenado["fase"] == "A" and fase == "B":
            return f"no se probó: el sitio quedó frenado en la fase A ({frenado['resultado']})"
    return "no"


def _primera(t) -> str:
    if not t:
        return ""
    txt = f"{t['nombre'] or '(sin nombre)'}, {pesos(t['precio'])}"
    if t.get("precio_unidad") is not None:
        txt += f" ({pesos(t['precio_unidad'])} x {t['unidad']})"
    if t.get("oferta"):
        txt += f", oferta: {t['oferta']}"
    return txt


def resumen_md(corrida: dict, nota: str = "") -> str:
    ini = dt.datetime.fromisoformat(corrida["inicio_utc"])
    fin = dt.datetime.fromisoformat(corrida.get("fin_utc") or corrida["inicio_utc"])
    santiago = (f" ({hora_santiago(ini)} a {hora_santiago(fin)} en Santiago)"
                if hora_santiago(ini) else "")
    ent = corrida.get("entorno", {})
    donde = "en GitHub Actions" if ent.get("github_run_id") else "fuera de GitHub Actions"
    if ent.get("github_run_id"):
        donde += f" (corrida {ent['github_run_id']}, {ent.get('runner') or 'runner'})"
    desdes = [p["desde_anterior"] for p in corrida["pedidos"] if p.get("desde_anterior") is not None]
    L = ["# Prueba de lectura de supermercados desde Actions", ""]
    L.append(f"Corrida del {fecha_larga(ini)} {donde}, de {ini:%H:%M:%S} a {fin:%H:%M:%S} UTC"
             f"{santiago}: {duracion(corrida.get('segundos') or 0)}.")
    if nota:
        L += ["", nota]
    L.append("")
    n_robots = sum(1 for p in corrida["pedidos"] if p["fase"] == "robots")
    L.append(f"- Pedidos de búsqueda: {corrida.get('busquedas_pedidas', 0)} de un tope de "
             f"{corrida['tope']}, uno a la vez, más {n_robots} de robots.txt.")
    pausas = sorted(set(corrida.get("pausas", {}).values()))
    if pausas:
        txt = " y ".join(segundos(x) for x in pausas)
        L.append(f"- Pausa entre pedidos al mismo sitio, desde que termina el anterior: {txt} o más"
                 + (f" (la menor que hubo fue {segundos(min(desdes))})." if desdes else "."))
    for fase, ua in corrida.get("ua", {}).items():
        L.append(f"- User-Agent de la fase {fase}: `{ua}`")
    if corrida.get("chromium"):
        L.append(f"- Fase B: Chromium {corrida['chromium']} sin interfaz, con JavaScript apagado. "
                 "Solo sale el documento de la búsqueda; estilos, scripts, imágenes, iframes y "
                 "XHR se frenan dentro del navegador.")
    if corrida.get("error_fase_b"):
        L.append(f"- La fase B no pudo correr: `{corrida['error_fase_b']}`")
    if any(urlsplit(b).hostname in ("127.0.0.1", "localhost") for b in corrida["bases"].values()):
        L.append("- Corrida local de ensayo, contra un servidor simulado.")

    L += ["", "## Por sitio y fase", "",
          "| Sitio | Fase | Búsquedas | Estado | Hubo precios | Hubo bloqueo |",
          "|---|---|---|---|---|---|"]
    for sitio in corrida["sitios"]:
        for fase, nombre in FASES.items():
            ps = busquedas(corrida, sitio, fase)
            hechas = [p for p in ps if p.get("resultado") != "no se pidió"]
            con = sum(1 for p in hechas if p.get("tarjetas"))
            precios = f"sí, en {con} de {len(hechas)}" if con else "no"
            L.append(f"| {sitio} | {fase}, {nombre} | {len(hechas)} de {len(corrida['terminos'])} "
                     f"| {_estados(hechas)} | {precios} | {_celda(_bloqueo_de(corrida, sitio, fase, ps))} |")

    L += ["", "## robots.txt", "",
          "| Sitio | Estado | Crawl-delay | Reglas | Búsquedas de la prueba |", "|---|---|---|---|---|"]
    for sitio in corrida["sitios"]:
        r = corrida["robots"].get(sitio, {})
        permitida = {True: "permitidas", False: "bloqueadas"}.get(r.get("busqueda_permitida"), "")
        cd = r.get("crawl_delay")
        L.append(f"| {sitio} | {r.get('estado', r.get('resultado', ''))} "
                 f"| {segundos(cd) if cd is not None else 'no tiene'} "
                 f"| {_celda(r.get('reglas') or r.get('detalle') or '')} | {permitida} |")

    for sitio in corrida["sitios"]:
        ps = busquedas(corrida, sitio, "A")
        if ps:
            L += ["", f"## {sitio}, fase A (pedido simple)", "",
                  "| Término | Estado | Bytes | x kg, x lt, x un | Nombres en el HTML | Tarjetas | Primera tarjeta |",
                  "|---|---|---|---|---|---|---|"]
            for p in ps:
                u = p.get("unidades") or {}
                conteo = f"{u.get('kg', 0)}, {u.get('lt', 0)}, {u.get('un', 0)}" if u else ""
                n_t = len(p.get("tarjetas") or [])
                if "nombres_en_datos" in p:
                    nombres = ("sí" if n_t or p["nombres_en_datos"] else "no") + \
                        f" ({n_t} en el texto, {p['nombres_en_datos']} en los datos)"
                else:
                    nombres = ""
                estado = p.get("estado", "")
                if p.get("resultado") not in ("ok",):
                    estado = f"{estado} {p.get('resultado')}: {p.get('detalle')}".strip()
                primera = _primera((p.get("tarjetas") or [None])[0])
                L.append(f"| {p['termino']} | {_celda(estado)} | {miles(p.get('bytes'))} | {conteo} "
                         f"| {nombres} | {n_t} | {_celda(primera)} |")
        ps = busquedas(corrida, sitio, "B")
        if ps:
            L += ["", f"## {sitio}, fase B (navegador sin interfaz)", "",
                  "| Término | Estado | Bytes del HTML | Tarjetas | Primera tarjeta | Subpedidos frenados |",
                  "|---|---|---|---|---|---|"]
            for p in ps:
                sub = p.get("subpedidos") or {}
                frenados = ", ".join(f"{k} {v}" for k, v in sorted((sub.get("frenados") or {}).items()))
                estado = p.get("estado", "")
                if p.get("resultado") not in ("ok",):
                    estado = f"{estado} {p.get('resultado')}: {p.get('detalle')}".strip()
                n_t = len(p.get("tarjetas") or [])
                primera = _primera((p.get("tarjetas") or [None])[0])
                L.append(f"| {p['termino']} | {_celda(estado)} | {miles(p.get('bytes'))} | {n_t} "
                         f"| {_celda(primera)} | {_celda(frenados or 'ninguno')} |")

    vistos = [p for p in corrida["pedidos"] if p.get("visto")]
    if vistos:
        L += ["", "## Lo que se vio en los bloqueos y errores", ""]
        for p in vistos:
            v = p["visto"]
            cab = ", ".join(f"{k}: {x}" for k, x in v.get("cabeceras", {}).items())
            L.append(f"- {p['sitio']}, fase {p['fase']}, \"{p.get('termino') or 'robots.txt'}\": "
                     f"{p.get('detalle')}. Estado {v.get('estado')}; cabeceras: {cab or 'ninguna de interés'}; "
                     f"título: \"{v.get('titulo')}\"; texto: \"{v.get('texto')}\"")

    con_avisos = [p for p in corrida["pedidos"] if p.get("avisos") or
                  (p.get("subpedidos") or {}).get("errores")]
    if con_avisos:
        L += ["", "## Avisos", ""]
        for p in con_avisos:
            avisos = list(p.get("avisos") or []) + [
                f"error en la intercepción: {x}" for x in (p.get("subpedidos") or {}).get("errores") or []]
            L.append(f"- {p['sitio']}, fase {p['fase']}, \"{p.get('termino')}\": " + "; ".join(avisos))

    L += ["", "## Registro de pedidos", "",
          "| # | Hora UTC | Sitio | Fase | Pedido | Estado | Bytes | Duración | Pausa previa |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p in corrida["pedidos"]:
        if p.get("resultado") == "no se pidió":
            continue
        hora = p.get("inicio_utc", "")[11:19]
        saltos = p.get("redirecciones") or []
        pedido = ruta_de(p["url"]) + (f" (redirigió a {', '.join(ruta_de(s) for s in saltos)})"
                                      if saltos else "")
        desde = segundos(p["desde_anterior"]) if p.get("desde_anterior") is not None else ""
        dur = segundos(p["dur"]) if p.get("dur") is not None else ""
        L.append(f"| {p['n']} | {hora} | {p['sitio']} | {p['fase']} | `{_celda(pedido)}` "
                 f"| {p.get('estado', p.get('resultado', ''))} | {miles(p.get('bytes'))} | {dur} | {desde} |")
    no_pedidos = [p for p in corrida["pedidos"] if p.get("resultado") == "no se pidió"]
    if no_pedidos:
        L += ["", "No se pidieron:"]
        for p in no_pedidos:
            L.append(f"- {p['sitio']}, fase {p['fase']}, \"{p['termino']}\": {p.get('detalle')}")
    L += ["", "Las tarjetas (hasta 8 por búsqueda) están en resultado.csv; el texto leído de cada "
              "página, en crudo/."]
    return "\n".join(L) + "\n"


def escribir_salidas(salida: str, corrida: dict, nota: str = ""):
    escribir_csv(salida, corrida)
    with open(os.path.join(salida, "resumen.md"), "w", encoding="utf-8") as fh:
        fh.write(resumen_md(corrida, nota))


def releer(salida: str):
    """Vuelve a leer las tarjetas desde crudo/, sin red."""
    with open(os.path.join(salida, "corrida.json"), encoding="utf-8") as fh:
        corrida = json.load(fh)
    for p in corrida["pedidos"]:
        if p.get("crudo"):
            with open(os.path.join(salida, p["crudo"]), encoding="utf-8") as fh:
                p["tarjetas"] = leer_tarjetas(fh.read())
    guardar_corrida(salida, corrida)
    escribir_salidas(salida, corrida,
                     f"Tarjetas leídas otra vez desde crudo/, sin red, el "
                     f"{fecha_larga(ahora_utc())} a las {ahora_utc():%H:%M} UTC.")
    return corrida


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--salida", default="salida", help="carpeta de salida")
    ap.add_argument("--desde-crudo", metavar="CARPETA",
                    help="no pide nada: vuelve a leer las tarjetas de CARPETA/crudo")
    ap.add_argument("--pausa", type=float, default=PAUSA,
                    help=f"segundos entre pedidos al mismo sitio (nunca menos de {PAUSA_MINIMA:g})")
    ap.add_argument("--base", action="append", default=[], metavar="SITIO=URL",
                    help="solo para ensayos locales: otra base para un sitio")
    a = ap.parse_args(argv)
    if a.desde_crudo:
        releer(a.desde_crudo)
        print(f"releído: {a.desde_crudo}/resultado.csv y resumen.md")
        return 0
    bases = dict(SITIOS)
    for b in a.base:
        sitio, _, url = b.partition("=")
        if sitio not in SITIOS or not url:
            ap.error(f"--base {b}: sitio desconocido o sin URL")
        bases[sitio] = url.rstrip("/")
    # la prueba es desde Actions: fuera de ahí no se toca a los supermercados
    reales = [s for s, b in bases.items() if urlsplit(b).hostname not in ("127.0.0.1", "localhost")]
    if reales and os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"No corre: {' y '.join(reales)} solo se {'leen' if len(reales) > 1 else 'lee'} "
              "desde GitHub Actions. Para ensayar, "
              "--base jumbo.cl=http://127.0.0.1:PUERTO --base santaisabel.cl=http://127.0.0.1:PUERTO",
              file=sys.stderr)
        return 2
    corrida = correr(a.salida, bases, a.pausa)
    escribir_salidas(a.salida, corrida)
    print(f"listo en {segundos(corrida['segundos'])}: {corrida['busquedas_pedidas']} pedidos de "
          f"búsqueda; {a.salida}/resultado.csv y {a.salida}/resumen.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

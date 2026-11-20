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
(lo que pasó en cada pedido) y crudo/: el texto que se leyó de cada página,
para volver a leer las tarjetas sin pedir nada otra vez (--desde-crudo), y
el HTML que llegó, comprimido y con los <script> vaciados.

Reglas de la prueba, que no se negocian:

- Sin saltar barreras. Un 4xx que no sea 404 ni 410, un 2xx distinto de 200
  sin precios, una cabecera de mitigación (Cloudflare, AWS WAF, Vercel), un
  captcha, una página de desafío o una redirección a una de ellas se anota
  "bloqueado" con lo que se vio, y a ese sitio no se le pide nada más: ni
  reintento ni la otra fase. Una página chica, sin <main> ni precios, cuenta
  como desafío. Tampoco se insiste si el sitio no responde (tiempo agotado,
  conexión cortada) o responde 5xx: puede ser un bloqueo callado. El estado
  y las cabeceras se revisan antes de leer la página, así que un error del
  lector no tapa un bloqueo.
- El User-Agent de las dos fases termina en UA_SUFIJO. La fase A usa el de
  requests y la B el de Chromium sin interfaz ("HeadlessChrome"), cada uno
  con el sufijo. Sin plugins para ocultar el navegador, sin proxies (ninguna
  fase usa los del entorno), sin rotar IP y sin cabeceras copiadas de otro
  navegador.
- Solo las páginas de búsqueda: ninguna API, sin sesión (ninguna fase guarda
  cookies de un pedido a otro), sin elegir local. La fase B corre con
  JavaScript apagado, por HTTP/1.1 (sin HTTP/2 ni QUIC: así Chromium no pide
  por su cuenta los recursos que anuncie un 103 Early Hints, que no pasan
  por la intercepción) y el navegador deja salir solo el documento de la
  búsqueda y sus redirecciones dentro de /busqueda del mismo sitio que
  robots.txt permita. Hojas de estilo, scripts, imágenes, iframes, XHR y
  cualquier otro subpedido se frenan dentro del navegador, antes de salir
  (intercepción de Chromium con Fetch.requestPaused). Así la página no puede
  llamar a /api/ ni a /_next/ y no puede resolver un desafío.
- Como máximo 32 pedidos de búsqueda en la corrida (8 términos, 2 sitios, 2
  fases), más el robots.txt de cada sitio. Cada salto de una redirección
  cuenta como un pedido más dentro de ese tope y espera la misma pausa. Uno
  a la vez y con PAUSA segundos o más entre pedidos al mismo sitio (nunca
  menos de 3 ni menos que su Crawl-delay), contados desde que termina el
  anterior. Chromium se prueba antes de pedir nada: si no parte, no se pide
  nada.
- robots.txt primero: no se pide ninguna URL que bloquee para "*" (ni para
  CarestiaPrueba, si lo nombrara). Sus redirecciones se siguen a mano, dentro
  del mismo sitio y con pausa. Si robots.txt no responde, llega como HTML o
  con un estado raro, el sitio no se prueba; si no existe (404 o 410), no hay
  reglas.

Uso:
    python analisis/supermercados/prueba_lectura.py --salida salida
    python analisis/supermercados/prueba_lectura.py --desde-crudo salida
    python analisis/supermercados/prueba_lectura.py --salida salida --saltar jumbo.cl
"""
import argparse
import csv
import datetime as dt
import functools
import gzip
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
TOPE_BUSQUEDAS = 32         # 8 términos, 2 sitios, 2 fases; los saltos de redirección entran aquí
TARJETAS_POR_PAGINA = 8
MAX_REDIRECCIONES = 2       # saltos dentro de /busqueda, cada uno con su pausa
MAX_SALTOS_ROBOTS = 5       # RFC 9309
TIEMPO_CONEXION = 10
TIEMPO_LECTURA = 40
TIEMPO_TOTAL_A = 60         # segundos: tope de un pedido de la fase A, de punta a punta
TIEMPO_PAGINA_MS = 45_000
MAX_BYTES = 30_000_000
PAGINA_CHICA = 20_000       # bytes; una página de búsqueda real pesa cerca de 1 MB
# Chromium por HTTP/1.1: los preloads de un 103 Early Hints salen del proceso
# del navegador sin pasar por Fetch.requestPaused, y por HTTP/1.1 Chromium
# ignora el 103. Sin proxy, igual que la fase A.
ARGS_CHROMIUM = ("--disable-http2", "--disable-quic", "--no-proxy-server")
# rutas que la prueba no lee aunque robots.txt las permita
RUTAS_PROHIBIDAS = ("/api/", "/_next/")
FASES = {"A": "pedido simple", "B": "navegador sin interfaz"}
COLUMNAS = ["sitio", "fase", "término", "posición", "nombre", "marca", "precio",
            "precio_unidad", "unidad", "oferta"]
# resultados de un pedido que frenan al sitio: no se le pide nada más
DETIENEN = ("bloqueado", "sin respuesta", "error del servidor",
            "redirección fuera de lo permitido")
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
                # no cierra la lista de User-agent: solo Allow y Disallow la
                # cierran (RFC 9309 2.2.4, igual que Sitemap)
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
                # los Disallow se comparan también decodificados (bloquea de
                # más, nunca de menos); los Allow, solo tal como vienen
                formas = {patron} if permitir else {patron, unquote(patron)}
                if any(_regex_robots(p).match(ruta) for p in formas):
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
_OCULTO_ESTILO = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
# segmento de React enviado en streaming (<div hidden id="S:0">): con
# JavaScript se mueve a su lugar; sin JavaScript se lee donde viene
_SEGMENTO = re.compile(r"S:\d")


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
        oculto = ("hidden" in atributos and not _SEGMENTO.match(atributos.get("id") or "")
                  or _OCULTO_ESTILO.search(atributos.get("style") or "")
                  or tag in ("dialog", "details") and "open" not in atributos)
        if tag not in _VACIOS and oculto:
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
            # como el innerText: los saltos del código fuente son espacios;
            # las líneas salen solo de br y de los bloques
            self.partes.append(re.sub(r"\s+", " ", data))


def _visible(html: str) -> str:
    lector = _Texto()
    lector.feed(html)
    lector.close()
    lineas = (" ".join(l.split()) for l in "".join(lector.partes).split("\n"))
    return "\n".join(l for l in lineas if l)


def texto_de_html(html: str):
    """(texto, hubo_main): el texto visible del <main>, con una línea por
    bloque. Si no hay <main>, o el <main> no trae ningún precio y el <body>
    sí (la grilla llegó en un segmento aparte), el del <body>. Es la versión
    sin navegador del innerText que lee la fase B."""
    m = re.search(r"<main\b[^>]*>(.*)</main\s*>", html, re.I | re.S)
    hubo_main = m is not None
    texto = _visible(m.group(1)) if m else ""
    if "$" not in texto:
        b = re.search(r"<body\b[^>]*>(.*)</body\s*>", html, re.I | re.S)
        cuerpo = _visible(b.group(1) if b else html)
        if not hubo_main or "$" in cuerpo:
            texto = cuerpo
    return texto, hubo_main


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
# Sin hojas de estilo la unidad puede quedar pegada a lo que sigue
# ("$1.945 x kgFrutas y Verduras"): vale si sigue una palabra con mayúscula
# inicial, no si sigue una minúscula, un dígito o una palabra en mayúsculas.
_FIN_UNIDAD = r"\.?(?-i:(?![a-zà-ÿ0-9_/])(?![A-ZÀ-Þ]{2}))"
_TRAS_PRECIO = re.compile(r"\s*(?:x|por|/)\s*(?:(" + _NUM + r")\s*)?(" + _UNI + r")" + _FIN_UNIDAD, re.I)
_PRESENTACION = re.compile(r"(?:x|por)\s*(" + _NUM + r")\s*(" + _UNI + r")" + _FIN_UNIDAD, re.I)
_UNIDAD_SOLA = re.compile(r"(?:x|por|/)\s*(" + _UNI + r")\.?", re.I)
# "Lleva 2 por $3.000", "3 x $5.000", "2x$5.000", "Ahorra $360": el precio es de la etiqueta.
# "dcto." no: en "20% dcto." el precio que sigue es el de la tarjeta
_CONECTOR = re.compile(r"(?:(?:^|\s)(?:por|x|a|desde|hasta|de|con|en|ahorr[ae]s?|ahorro)"
                       r"|\dx)\s*:?\s*$", re.I)
# "Normal: $1.350", "Antes $1.350", "Precio normal $1.350": ese precio es el anterior
_ANTES = re.compile(r"(?:^|\s)(?:precio\s+)?(?:normal|antes|anterior|regular)\s*:?\s*$", re.I)
_PORCENTAJE = re.compile(r"^-?\d+\s*%(?:\s*\w+)?$")
# un rango de los filtros ("$5.000 - $20.000", "$0 a $5.000") no es un precio de tarjeta
_RANGO = re.compile(r"\$\s?(?:" + _NUM + r")\s*(?:-|\u2013|a|hasta)\s*\$\s?(?:" + _NUM + r")", re.I)
# textos de la tarjeta que no son marca ni nombre
_NO_NOMBRE = re.compile(r"(?:agotado|sin stock|av[ií]same|patrocinado|nuevo|destacado"
                        r"|exclusivo(?: online| internet)?|últimas unidades)", re.I)
_AGREGAR = re.compile(r"(.*?)\s*(Agregar|AGREGAR)(?: al carro| AL CARRO)?")
_ETIQUETA = re.compile(
    r"ofert|imbatible|lleva\s*\d|ll[eé]vate|\d+\s*(?:x|por)\s*\$|descuento|dcto|promo"
    r"|precio\s+especial|liquidaci|\d+\s*%|ahorra|exclusivo\b|cyber|black|\b2do\b|segunda"
    r"|club|tarjeta|cencosud|rebaja|nuevo\s+precio|baj[oó]\s+de\s+precio", re.I)


def a_numero(s: str):
    """"1.945" -> 1945; "2.111,5" -> 2111.5; "1,945" -> 1945; "990" -> 990.
    None si no es un número que se pueda leer ("1.945.50")."""
    s = s.strip().replace(" ", "")
    if "." in s and "," in s:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        s = s.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        partes = s.split(sep)
        s = "".join(partes) if all(len(p) == 3 for p in partes[1:]) else s.replace(sep, ".")
    try:
        v = float(s)
    except ValueError:
        return None
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
    s = re.sub(r"\s*\bc/u\b\.?", " x un", s, flags=re.I)     # "$617 c/u" es "$617 x un"
    m = _AGREGAR.fullmatch(s)
    if m:
        return _piezas_linea(m.group(1)) + [("agregar", None)]
    m = _PRESENTACION.match(s)
    if m and (m.end() == len(s) or s[m.end():].lstrip().startswith("$")):
        # "x 500 g" sola, o pegada al precio por unidad ("x 500 g$2.250 x kg")
        return [("pres", f"x {m.group(1)} {_unidad(m.group(2))}")] + _piezas_linea(s[m.end():])
    m = _UNIDAD_SOLA.fullmatch(s)
    if m:
        return [("unidad", _unidad(m.group(1)))]
    if not _PRECIO.search(s) or _RANGO.search(s):
        return [("texto", s)]
    piezas, texto, pos = [], "", 0
    for m in _PRECIO.finditer(s):
        if m.start() < pos:
            continue
        valor = a_numero(m.group(1))
        if valor is None:                   # un número que no se lee: queda como texto
            continue
        texto += s[pos:m.start()]
        if texto.strip() and _ANTES.search(texto):
            resto = _ANTES.sub("", texto).strip()
            if resto:
                piezas.append(("texto", resto))
            piezas.append(("ant", valor))   # "Normal: $1.350": el precio anterior, dicho
            texto, pos = "", m.end()
            continue
        if texto.strip() and _CONECTOR.search(texto):
            texto += m.group(0)            # el precio es parte de la etiqueta
            pos = m.end()
            continue
        if texto.strip():
            piezas.append(("texto", texto.strip()))
        texto = ""
        piezas.append(("precio", valor))
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
        if p[0] == "precio" and juntas and juntas[-1][0] == "texto":
            previo = juntas[-1][1]
            if _ANTES.search(previo):       # "Precio normal" y "$1.350" en líneas distintas
                resto = _ANTES.sub("", previo).strip()
                if resto:
                    juntas[-1] = ("texto", resto)
                else:
                    juntas.pop()
                juntas.append(("ant", p[1]))
                continue
            if _CONECTOR.search(previo):    # "Lleva 2 por" y "$3.000" en líneas distintas
                juntas[-1] = ("texto", f"{previo} {pesos(p[1])}")
                continue
        if p[0] == "unidad":
            if juntas and juntas[-1][0] == "precio":
                juntas[-1] = ("pu", (juntas[-1][1], p[1]))
            continue
        juntas.append(p)
    return juntas


def _suelta(texto: str) -> bool:
    """Un texto corto que puede ir entre los precios de una tarjeta y su
    precio por unidad sin ser marca ni nombre: "Oferta", "-20%", "Normal"."""
    return len(texto) <= 40 and bool(_ETIQUETA.search(texto) or _PORCENTAJE.match(texto)
                                      or _ANTES.search(texto))


def _tarjeta(ps: list, i: int):
    ancla = ps[i]
    precio_unidad = unidad = None
    precios, presentacion, explicito = [], None, None
    primero = None                          # posición del primer precio de la tarjeta
    if ancla[0] == "pu":
        precio_unidad, unidad = ancla[1]
    else:                                   # ancla de respaldo: el último precio
        precios, primero = [ancla[1]], i
    sueltas = []                            # (precios vistos al pasar, texto)
    j = i - 1
    while j >= 0 and len(precios) < 2:
        tipo, valor = ps[j]
        if tipo == "precio":
            precios.insert(0, valor)
            primero = j
        elif tipo == "ant":
            if explicito is None:
                explicito = valor
        elif tipo == "pres":
            if presentacion is None:
                presentacion = valor
        elif tipo == "pu" and ancla[0] == "pu" and valor == ancla[1]:
            pass                            # copia del mismo precio por unidad
        elif tipo == "texto" and _suelta(valor):
            sueltas.append((len(precios), valor))
        else:
            break
        j -= 1
    etiqueta = ""
    # la etiqueta es un texto corto: lo que va antes de la primera tarjeta puede
    # ser la tira de categorías de los filtros ("DespensaMarcas Exclusivas...")
    if primero is not None and primero > 0 and ps[primero - 1][0] == "texto" \
            and len(ps[primero - 1][1]) <= 40 and _ETIQUETA.search(ps[primero - 1][1]):
        etiqueta = ps[primero - 1][1]
    if not etiqueta:                        # una etiqueta entre los precios o antes del ancla
        etiqueta = next((t for n, t in sueltas if _ETIQUETA.search(t)
                         and (n == 0 or n < len(precios))), "")
    k = i + 1
    # tras el precio por unidad pueden venir el anterior ("Normal: $1.350") o un "-20%"
    while k < len(ps) and (ps[k][0] == "ant" or ps[k][0] == "texto" and len(ps[k][1]) <= 40
                           and (_ANTES.search(ps[k][1]) or _PORCENTAJE.match(ps[k][1]))):
        if ps[k][0] == "ant" and explicito is None:
            explicito = ps[k][1]
        k += 1
    textos = []
    while k < len(ps) and ps[k][0] == "texto":
        textos.append(ps[k][1])
        k += 1
    # sin "Agregar" entre tarjetas, la etiqueta de la siguiente no es nombre
    if (len(textos) >= 2 and k < len(ps) and ps[k][0] in ("precio", "pu")
            and _ETIQUETA.search(textos[-1])):
        textos.pop()
    textos = [t for t in textos if not _NO_NOMBRE.fullmatch(t)]
    while len(textos) > 2 and len(textos[0]) <= 40 and _ETIQUETA.search(textos[0]):
        etiqueta = etiqueta or textos[0]    # una etiqueta antes de la marca
        textos.pop(0)
    marca, nombre = (textos[0], textos[1]) if len(textos) >= 2 else ("", textos[0] if textos else "")
    if not precios and precio_unidad is not None:
        precios = [precio_unidad]           # solo muestra el precio por unidad
    if not precios:
        return None
    vigente = precios[0]
    anterior = precios[1] if len(precios) > 1 else None
    if explicito is not None:               # "Normal: $1.350": ese es el anterior
        vigente, anterior = min(precios), explicito
    if anterior is not None:
        if anterior == vigente:             # el mismo precio dos veces: no es oferta
            anterior = None
        elif anterior < vigente:            # el anterior es el más alto
            vigente, anterior = anterior, vigente
    if anterior is not None and anterior > 3 * vigente:
        anterior = None                     # un precio de los filtros, no de la tarjeta
    return _con_oferta({"nombre": nombre, "marca": marca, "precio": vigente,
                        "precio_anterior": anterior, "etiqueta": etiqueta,
                        "presentacion": presentacion, "precio_unidad": precio_unidad,
                        "unidad": unidad})


def _con_oferta(t: dict) -> dict:
    t["oferta"] = ", ".join(x for x in (t["etiqueta"], f"antes {pesos(t['precio_anterior'])}"
                                        if t["precio_anterior"] else "") if x)
    return t


def _fundir(t: dict, copia: dict):
    """Pasa a t lo que trae la copia sin nombre de su bloque de precios."""
    if t["precio_anterior"] is None and copia["precio_anterior"] is not None:
        t["precio"], t["precio_anterior"] = copia["precio"], copia["precio_anterior"]
    t["etiqueta"] = t["etiqueta"] or copia["etiqueta"]
    t["presentacion"] = t["presentacion"] or copia["presentacion"]
    _con_oferta(t)


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
        # una copia del bloque de precios (la versión para celular o para
        # escritorio que el CSS esconde) deja una tarjeta sin marca ni nombre
        # junto a la verdadera, con el mismo precio por unidad: se funden
        previa = tarjetas[-1] if tarjetas else None
        if (previa is not None and t["precio_unidad"] is not None
                and (previa["precio_unidad"], previa["unidad"]) == (t["precio_unidad"], t["unidad"])):
            if not (previa["nombre"] or previa["marca"]):
                tarjetas.pop()
                _fundir(t, previa)
            elif not (t["nombre"] or t["marca"]):
                _fundir(previa, t)
                continue
        clave = (t["nombre"], t["marca"], t["precio"], t["precio_unidad"], t["unidad"])
        if tarjetas and clave == tarjetas[-1]["_clave"]:
            continue                        # la misma tarjeta repetida (copia oculta)
        t["_clave"] = clave
        tarjetas.append(t)
    tarjetas = tarjetas[:tope]
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
    # también dentro de la carga de Next con App Router, donde el JSON va con
    # las comillas escapadas: self.__next_f.push([1,"{\"name\":\"Papa\"}"])
    for fuente in (html, html.replace('\\"', '"')):
        for m in _NOMBRE_DATO.finditer(fuente):
            try:
                valor = json.loads('"' + m.group(1) + '"')
            except ValueError:
                valor = m.group(1)
            if clave in sin_tildes(valor).lower() and valor not in vistos:
                vistos.append(valor)
    return vistos


# ---------------------------------------------------------------- bloqueos

# marcas de las páginas de desafío o de bloqueo. Algunas también aparecen en
# páginas normales (los scripts de detección), por eso solo se buscan en una
# página chica o sin <main>, nunca en una página de búsqueda completa.
_DESAFIO_HTML = [
    ("Cloudflare", re.compile(r"cf_chl_opt|/cdn-cgi/challenge-platform/h/[a-z]/orchestrate/"
                              r"|cf-chl-widget", re.I)),
    ("Imperva", re.compile(r"incapsula incident id|request unsuccessful\. incapsula"
                           r"|_incapsula_resource", re.I)),
    ("DataDome", re.compile(r"captcha-delivery\.com", re.I)),
    ("HUMAN (PerimeterX)", re.compile(r"id=[\"']px-captcha|_pxcaptcha", re.I)),
    ("Akamai", re.compile(r"/_sec/cp_challenge|sec-if-cpt-container|errors\.edgesuite\.net", re.I)),
    ("AWS WAF", re.compile(r"captcha\.awswaf|awswafcaptcha|awswaf\.com", re.I)),
    ("F5", re.compile(r"the requested url was rejected|/tspd/", re.I)),
    ("Imperva o Distil", re.compile(r"pardon our interruption", re.I)),
]
# marcas genéricas: en el título siempre; en el texto, solo en una página
# chica o sin <main>
_DESAFIO_TEXTO = re.compile(
    r"captcha|just a moment|attention required|access denied|acceso denegado"
    r"|verify (?:that )?you are (?:a )?human|are you a robot|eres un robot|no soy un robot"
    r"|not a robot|verifica(?:r)? que eres|checking your browser"
    r"|comprobando (?:tu|su) navegador|request unsuccessful|pardon our interruption|forbidden"
    r"|request rejected|requested url was rejected|support id|enable javascript"
    r"|(?:habilita|activa|habilitar|activar) (?:el )?javascript|unusual traffic"
    r"|tr[aá]fico inusual", re.I)
# cabeceras que dicen que el borde mitigó el pedido
_CABECERAS_MITIGACION = ("cf-mitigated", "x-amzn-waf-action", "x-vercel-mitigated")
_CABECERAS_VISTAS = ("server", "cf-ray", "cf-mitigated", "cf-cache-status", "x-datadome",
                     "x-iinfo", "x-cdn", "via", "x-cache", "akamai-grn", "x-akamai-transformed",
                     "content-type", "retry-after", "location", "x-amz-cf-pop",
                     "x-amzn-waf-action", "x-vercel-mitigated", "link")


def cabeceras_vistas(cabeceras: dict) -> dict:
    bajas = {k.lower(): v for k, v in (cabeceras or {}).items()}
    return {k: bajas[k][:120] for k in _CABECERAS_VISTAS if k in bajas}


def ver_bloqueo_http(estado, cabeceras: dict):
    """El bloqueo que se ve en el estado o en las cabeceras, antes de leer
    la página (None si no hay). Un 4xx que no sea 404 ni 410 es un bloqueo:
    405 es el captcha de AWS WAF y 406 el bloqueo de Fastly."""
    bajas = {k.lower(): v for k, v in (cabeceras or {}).items()}
    if estado is not None and 400 <= estado < 500 and estado not in (404, 410):
        return f"HTTP {estado}"
    for nombre in _CABECERAS_MITIGACION:
        if nombre in bajas and (nombre != "cf-mitigated" or bajas[nombre].lower() == "challenge"):
            return f"el borde mitigó el pedido ({nombre}: {str(bajas[nombre])[:40]})"
    return None


def _texto_crudo(html: str) -> str:
    """Todo el texto de un HTML chico, también el de <noscript>."""
    return unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script\b.*?</script\s*>", " ", html,
                                                   flags=re.I | re.S)))


def ver_bloqueo(estado, cabeceras: dict, html: str, texto: str, titulo: str,
                hay_precios: bool, hubo_main: bool = True):
    """None si no hay señal de bloqueo; si no, qué se vio."""
    previo = ver_bloqueo_http(estado, cabeceras)
    if previo:
        return previo
    if hay_precios and (estado is None or estado < 500):
        return None                         # trae productos: no es una página de desafío
    if estado is not None and 200 < estado < 300:
        return f"HTTP {estado} sin precios (posible desafío)"
    if _DESAFIO_TEXTO.search(titulo or ""):
        return "página de desafío o captcha (por su título)"
    html = html or ""
    chica = len(html) < PAGINA_CHICA
    if chica or not hubo_main:
        for nombre, rx in _DESAFIO_HTML:
            if rx.search(html):
                return f"página de desafío ({nombre})"
        if (len(texto or "") < 5000 and _DESAFIO_TEXTO.search(texto or "")) or (
                chica and _DESAFIO_TEXTO.search(_texto_crudo(html))):
            return "página de desafío o captcha (por su texto)"
        if chica and not hubo_main and (estado is None or 200 <= estado < 300):
            return (f"posible página de desafío: {miles(len(html.encode('utf-8')))} bytes, "
                    "sin <main> ni precios")
    return None


def hay_precios_en(tarjetas: list, html: str) -> bool:
    """Si la página trae productos, aunque el lector no haya armado tarjetas:
    una página de desafío nunca trae "x kg", "x lt" ni "x un"."""
    return bool(tarjetas) or sum(contar_unidades(html or "").values()) > 0


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
    """Pedidos de búsqueda de la corrida, contando cada salto de redirección."""

    def __init__(self, tope: int = TOPE_BUSQUEDAS):
        self.tope, self.usados = tope, 0

    def queda(self) -> bool:
        return self.usados < self.tope

    def tomar(self):
        if self.usados >= self.tope:
            raise RuntimeError(f"se llegó al tope de {self.tope} pedidos de búsqueda")
        self.usados += 1


def pausa_del_sitio(pausa: float, base: str, crawl_delay) -> float:
    local = urlsplit(base).hostname in ("127.0.0.1", "localhost")
    return max(pausa, 0.0 if local else PAUSA_MINIMA, crawl_delay or 0.0)


# una redirección hacia una de estas URL es un desafío, no una búsqueda
_DESAFIO_URL = re.compile(r"captcha|challenge|perfdrive|recaptcha|/_sec/|incapsula|/cdn-cgi/"
                          r"|validate|blocked|denied|/tspd|awswaf|queue", re.I)


def _es_busqueda(ruta: str) -> bool:
    return ruta == RUTA_BUSQUEDA or ruta.startswith(RUTA_BUSQUEDA + "/")


def _con_puntos(ruta: str) -> bool:
    """Una ruta con segmentos "." o "..", o con puntos o barras codificados:
    el servidor podría resolverla fuera de lo que se revisó."""
    return (any(s in (".", "..") for s in unquote(ruta).split("/"))
            or bool(re.search(r"%2e|%2f|%5c", ruta, re.I)))


def clasificar_salto(destino: str, robots: Robots, base: str, pedidas: list, hechos: int):
    """(None, None) si una redirección se puede seguir; si no, (resultado, motivo).

    "bloqueado": lleva a una página de desafío, o vuelve a una URL ya pedida
    (un chequeo de cookie). "redirección fuera de lo permitido": otro sitio,
    fuera de /busqueda, una ruta que la prueba no lee o demasiados saltos; también
    frena al sitio. "redirección no seguida": robots.txt bloquea el destino; el
    sitio sigue con los demás términos."""
    d, b = urlsplit(destino), urlsplit(base)
    if _DESAFIO_URL.search(destino):
        return "bloqueado", "redirige a una página de desafío"
    if destino in pedidas:
        return "bloqueado", "redirige otra vez a una URL ya pedida (posible chequeo de cookie)"
    fuera = "redirección fuera de lo permitido"
    if (d.scheme, d.hostname, d.port) != (b.scheme, b.hostname, b.port):
        return fuera, f"lleva a otro sitio ({d.scheme}://{d.netloc})"
    if _con_puntos(d.path):
        return fuera, "la ruta trae segmentos de punto"
    if any(d.path.startswith(p) for p in RUTAS_PROHIBIDAS):
        return fuera, "lleva a una ruta que la prueba no lee"
    if not _es_busqueda(d.path):
        return fuera, "sale de la página de búsqueda"
    if hechos >= MAX_REDIRECCIONES:
        return fuera, f"más de {MAX_REDIRECCIONES} redirecciones"
    if not robots.permite(ruta_de(destino)):
        return "redirección no seguida", "robots.txt bloquea el destino"
    return None, None


# ---------------------------------------------------------------- fase A

def sesion_a():
    import requests
    from http.cookiejar import DefaultCookiePolicy
    s = requests.Session()
    s.trust_env = False                     # sin proxies ni otra configuración del entorno
    # las redirecciones se siguen a mano: cada pedido va con allow_redirects=False.
    # (max_redirects queda en su valor: con 0, requests falla ante cualquier 3xx)
    s.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))  # sin cookies: sin sesión
    s.headers["User-Agent"] = f"python-requests/{requests.__version__} {UA_SUFIJO}"
    return s


def decodificar(contenido: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w.:-]+)", content_type or "", re.I)
    try:
        return contenido.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        return contenido.decode("utf-8", errors="replace")


class RespuestaCortada(Exception):
    """La respuesta no terminó a tiempo o pasó del tamaño máximo."""


def _errores_red():
    import requests
    import urllib3
    return (requests.RequestException, urllib3.exceptions.HTTPError, RespuestaCortada, OSError)


def _normalizar(url: str) -> str:
    """La URL tal como la va a pedir requests (con "." y ".." ya resueltos),
    para revisar exactamente lo que sale."""
    import requests
    return requests.Request("GET", url).prepare().url


def _pedir_a(sesion, url: str):
    """(respuesta, cuerpo): un GET sin seguir redirecciones, con tiempo total
    de TIEMPO_TOTAL_A segundos (una respuesta que gotea no sostiene la
    corrida). Una respuesta informativa (1xx) vuelve sin leer."""
    r = sesion.get(url, timeout=(TIEMPO_CONEXION, TIEMPO_LECTURA), allow_redirects=False,
                   stream=True)
    if r.status_code < 200:
        r.close()
        return r, b""
    limite = _reloj() + TIEMPO_TOTAL_A
    leer = getattr(r.raw, "read1", None) or r.raw.read
    partes, total = [], 0
    try:
        while True:
            if _reloj() > limite:
                raise RespuestaCortada(f"la respuesta no terminó en {TIEMPO_TOTAL_A} s")
            trozo = leer(65536, decode_content=True)
            if not trozo:
                break
            partes.append(trozo)
            total += len(trozo)
            if total > MAX_BYTES:
                raise RespuestaCortada(f"la respuesta pasó de {miles(MAX_BYTES)} bytes")
    finally:
        r.close()
    return r, b"".join(partes)


def _es_html(texto: str) -> bool:
    return bool(re.search(r"<html|<!doctype html", texto[:2000], re.I)) and not re.search(
        r"(?im)^\s*user-agent\s*:", texto)


def bajar_robots(sesion, base: str, ritmo=None, sitio=None):
    """(info, Robots o None). None: el sitio no se prueba.

    Las redirecciones se siguen a mano (hasta 5, RFC 9309), solo dentro del
    mismo sitio y fuera de las rutas que la prueba no lee, con la pausa del
    sitio antes de cada salto. Solo 404 y 410 cuentan como "no hay
    robots.txt"; cualquier otro estado raro, o un HTML en vez del archivo,
    deja al sitio sin probar."""
    url = base + "/robots.txt"
    t0 = _reloj()
    info = {"url": url, "redirecciones": [], "pedidos_http": 0}
    actual, pedidas = url, [url]
    try:
        while True:
            info["pedidos_http"] += 1
            r, contenido = _pedir_a(sesion, actual)
            loc = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and loc:
                destino = _normalizar(urljoin(actual, loc))
                info["redirecciones"].append(destino)
                d, b = urlsplit(destino), urlsplit(base)
                info.update(estado=r.status_code, dur=_reloj() - t0,
                            cabeceras=cabeceras_vistas(r.headers))
                if _DESAFIO_URL.search(destino):
                    info.update(resultado="bloqueado",
                                detalle=f"robots.txt redirige a una página de desafío ({destino})",
                                visto=lo_que_se_vio(r.status_code, r.headers, "", ""))
                    return info, None
                motivo = None
                if (d.scheme, d.hostname, d.port) != (b.scheme, b.hostname, b.port):
                    motivo = "lleva a otro sitio"
                elif _con_puntos(d.path) or any(d.path.startswith(x) for x in RUTAS_PROHIBIDAS):
                    motivo = "lleva a una ruta que la prueba no lee"
                elif destino in pedidas:
                    motivo = "vuelve a una URL ya pedida"
                elif len(info["redirecciones"]) > MAX_SALTOS_ROBOTS:
                    motivo = f"más de {MAX_SALTOS_ROBOTS} redirecciones"
                if motivo:
                    info.update(resultado="no se pudo leer",
                                detalle=f"robots.txt redirige a {destino}: {motivo}")
                    return info, None
                if ritmo is not None:
                    ritmo.termino(sitio)
                    ritmo.esperar(sitio)
                pedidas.append(destino)
                actual = destino
                continue
            break
    except _errores_red() as e:
        info.update(resultado="sin respuesta", detalle=f"{type(e).__name__}: {e}"[:300],
                    dur=_reloj() - t0)
        return info, None
    estado = r.status_code
    info.update(estado=estado, bytes=len(contenido), dur=_reloj() - t0,
                cabeceras=cabeceras_vistas(r.headers))
    if estado < 200:
        sesion.close()                      # suelta la conexión: lo que queda en ella no se lee
        info.update(resultado="no se pudo leer", detalle=f"respuesta informativa (HTTP {estado})")
        return info, None
    texto = contenido.decode("utf-8", errors="replace")     # RFC 9309: el archivo es UTF-8
    es_html = _es_html(texto)
    bloqueo = ver_bloqueo_http(estado, r.headers)
    titulo, visible = "", texto[:400]
    if es_html:
        titulo = titulo_de_html(texto)
        visible, hubo_main = texto_de_html(texto)
        bloqueo = bloqueo or ver_bloqueo(estado, r.headers, texto, visible, titulo, False, hubo_main)
    if bloqueo:
        info.update(resultado="bloqueado", detalle=bloqueo,
                    visto=lo_que_se_vio(estado, r.headers, titulo, visible))
        return info, None
    if estado >= 500:
        info.update(resultado="sin respuesta", detalle=f"HTTP {estado}")
        return info, None
    if estado in (404, 410):                # no existe: sin reglas (RFC 9309)
        info.update(resultado="ok", detalle=f"HTTP {estado}: sin robots.txt, sin reglas")
        return info, Robots("")
    if estado != 200:
        info.update(resultado="no se pudo leer", detalle=f"HTTP {estado}",
                    visto=lo_que_se_vio(estado, r.headers, titulo, visible))
        return info, None
    if es_html:
        info.update(resultado="no se pudo leer", detalle="devolvió HTML, no un robots.txt",
                    visto=lo_que_se_vio(estado, r.headers, titulo, visible))
        return info, None
    info.update(resultado="ok", texto=texto[:20000])
    return info, Robots(texto)


def _sin_fallar(funcion, avisos: list, que: str, por_defecto):
    """Corre una parte del lector sin dejar que un error suyo tape la página."""
    try:
        return funcion()
    except Exception as e:
        avisos.append(f"error al {que}: {e!r}"[:200])
        return por_defecto


def fase_a(sesion, base: str, termino: str, robots: Robots, ritmo=None, sitio=None,
           tope=None) -> dict:
    url = url_busqueda(base, termino)
    p = {"url": url, "redirecciones": [], "saltos_seguidos": 0, "pausas_saltos": [],
         "pedidos_http": 0}
    pedidas, actual, t0 = [url], url, _reloj()
    try:
        while True:
            p["pedidos_http"] += 1
            r, contenido = _pedir_a(sesion, actual)
            if r.status_code < 200:
                sesion.close()              # suelta la conexión: el resto no es de este pedido
                p.update(estado=r.status_code, bytes=0, dur=_reloj() - t0, resultado="sin página",
                         detalle=f"respuesta informativa (HTTP {r.status_code}): la fase A no la lee",
                         tarjetas=[], cabeceras=cabeceras_vistas(r.headers))
                return p
            loc = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and loc:
                try:
                    destino = _normalizar(urljoin(actual, loc))
                    clase, motivo = clasificar_salto(destino, robots, base, pedidas,
                                                     p["saltos_seguidos"])
                except Exception:
                    destino, clase, motivo = loc, "redirección fuera de lo permitido", "URL que no se lee"
                p["redirecciones"].append(destino)
                if clase is None and tope is not None and not tope.queda():
                    clase, motivo = "redirección no seguida", f"se llegó al tope de {tope.tope} pedidos"
                if clase:
                    p.update(estado=r.status_code, bytes=len(contenido), dur=_reloj() - t0,
                             resultado=clase, detalle=f"{destino}: {motivo}", tarjetas=[],
                             cabeceras=cabeceras_vistas(r.headers))
                    if clase == "bloqueado":
                        p["visto"] = lo_que_se_vio(r.status_code, r.headers, "", "")
                    return p
                # el salto es un pedido más: cuenta en el tope y espera la pausa
                if tope is not None:
                    tope.tomar()
                if ritmo is not None:
                    ritmo.termino(sitio)
                    p["pausas_saltos"].append(ritmo.esperar(sitio))
                p["saltos_seguidos"] += 1
                pedidas.append(destino)
                actual = destino
                continue
            break
    except _errores_red() as e:
        p.update(dur=_reloj() - t0, resultado="sin respuesta",
                 detalle=f"{type(e).__name__}: {e}"[:300], tarjetas=[])
        return p
    html = decodificar(contenido, r.headers.get("content-type", ""))
    titulo = titulo_de_html(html)
    p.update(estado=r.status_code, bytes=len(contenido), dur=_reloj() - t0, titulo=titulo,
             cabeceras=cabeceras_vistas(r.headers), html=html)
    avisos = []
    # el estado y las cabeceras van antes que el lector: un error suyo no tapa un bloqueo
    bloqueo = ver_bloqueo_http(r.status_code, r.headers)
    if bloqueo:
        texto = _sin_fallar(lambda: texto_de_html(html)[0], avisos, "sacar el texto", "")
        p.update(texto=texto, tarjetas=[], resultado="bloqueado", detalle=bloqueo,
                 visto=lo_que_se_vio(r.status_code, r.headers, titulo, texto))
        return p
    texto, hubo_main = _sin_fallar(lambda: texto_de_html(html), avisos, "sacar el texto",
                                   ("", "<main" in html.lower()))
    tarjetas = _sin_fallar(lambda: leer_tarjetas(texto), avisos, "leer las tarjetas", [])
    nombres = _sin_fallar(lambda: nombres_en_datos(html, termino), avisos, "buscar nombres", [])
    p.update(hubo_main=hubo_main, unidades=contar_unidades(html), nombres_en_datos=len(nombres),
             ejemplos_nombres=nombres[:3], tarjetas=tarjetas, texto=texto)
    if avisos:
        p["avisos"] = avisos
    bloqueo = ver_bloqueo(r.status_code, r.headers, html, texto, titulo,
                          hay_precios_en(tarjetas, html), hubo_main)
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

# cabecera de las respuestas que arma la propia intercepción (nunca sale a la red)
MARCA_INTERNA = "x-carestia-interno"
# el texto de la página: el innerText de <main>; si <main> no trae ningún
# precio y el <body> sí (la grilla llegó en un segmento de React, <div hidden
# id="S:0">), el del <body> con esos segmentos a la vista
_LEER_TEXTO = """() => {
  for (const s of document.querySelectorAll('div[hidden][id^="S:"]')) s.removeAttribute('hidden');
  const m = document.querySelector('main');
  const enMain = m ? m.innerText : null;
  if (enMain !== null && enMain.includes('$')) return {texto: enMain, main: true};
  const cuerpo = document.body ? document.body.innerText : '';
  if (enMain === null) return {texto: cuerpo, main: false};
  return {texto: cuerpo.includes('$') ? cuerpo : enMain, main: true};
}"""


class NavegadorB:
    """Chromium sin interfaz, por HTTP/1.1, con JavaScript apagado y una
    intercepción que deja salir solo el documento de la búsqueda (y sus
    redirecciones permitidas, cada una con su pausa y dentro del tope). Todo
    lo demás se frena antes de salir del navegador."""

    def __init__(self, pw):
        self.navegador = pw.chromium.launch(headless=True, args=list(ARGS_CHROMIUM))
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
        """"sale" (el pedido sale a la red), "salto" (una redirección que se
        puede seguir: sale después de la pausa, si queda tope), "frena" (falla
        dentro del navegador) o "queda" (se contesta adentro con un 204 vacío:
        el navegador se queda en la página que ya tiene)."""
        if ev.get("resourceType") != "Document" or ev.get("frameId") != marco:
            return "frena"                  # subpedidos e iframes: no salen
        destino = ev["request"]["url"]
        if not estado["inicio"]:            # la búsqueda que se pidió
            estado["inicio"] = True
            estado["pedidas"] = [destino]
            d, b = urlsplit(destino), urlsplit(base)
            ok = ((d.scheme, d.hostname, d.port) == (b.scheme, b.hostname, b.port)
                  and _es_busqueda(d.path) and not _con_puntos(d.path)
                  and robots.permite(ruta_de(destino))
                  and not any(d.path.startswith(x) for x in RUTAS_PROHIBIDAS))
            return "sale" if ok else "frena"
        if ev.get("redirectedRequestId"):   # un salto de redirección del servidor
            clase, motivo = clasificar_salto(destino, robots, base, estado["pedidas"],
                                             len(estado["saltos"]))
            estado["saltos"].append(destino)
            if clase:
                estado["frenada"] = (clase, f"{destino}: {motivo}")
                return "frena"
            return "salto"
        estado["extra"] = destino           # otra navegación (meta refresh, Critical-CH)
        return "queda"

    def pedir(self, base: str, termino: str, robots: Robots, ritmo=None, sitio=None,
              tope=None) -> dict:
        from playwright.sync_api import Error as ErrorPW
        from playwright.sync_api import TimeoutError as TiempoPW
        url = url_busqueda(base, termino)
        p = {"url": url}
        estado = {"inicio": False, "saltos": [], "pedidas": [], "frenada": None, "extra": None,
                  "salieron": 0, "frenados": {}, "errores": [], "pausas_saltos": [],
                  "seguidos": 0, "early_hints": []}
        contexto = self.navegador.new_context(**self.opciones)
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        marco = cdp.send("Page.getFrameTree")["frameTree"]["frame"]["id"]

        def pausado(ev):
            decision = "frena"
            try:
                decision = self._decidir(ev, marco, base, robots, estado)
                if decision == "salto":
                    destino = ev["request"]["url"]
                    if tope is not None and not tope.queda():
                        estado["frenada"] = ("redirección no seguida",
                                             f"{destino}: se llegó al tope de {tope.tope} pedidos")
                        decision = "frena"
                    else:
                        # el salto es un pedido más: cuenta en el tope y espera la pausa
                        if tope is not None:
                            tope.tomar()
                        if ritmo is not None:
                            ritmo.termino(sitio)
                            estado["pausas_saltos"].append(ritmo.esperar(sitio))
                        estado["pedidas"].append(destino)
                        estado["seguidos"] += 1
                        decision = "sale"
            except Exception as e:          # ante la duda, no sale
                decision = "frena"
                estado["errores"].append(repr(e)[:200])
            try:
                if decision == "sale":
                    estado["salieron"] += 1
                    cdp.send("Fetch.continueRequest", {"requestId": ev["requestId"]})
                    return
                tipo = ev.get("resourceType") or "Other"
                estado["frenados"][tipo] = estado["frenados"].get(tipo, 0) + 1
                if decision == "queda":
                    cdp.send("Fetch.fulfillRequest", {
                        "requestId": ev["requestId"], "responseCode": 204,
                        "responseHeaders": [{"name": MARCA_INTERNA, "value": "1"}], "body": ""})
                else:
                    cdp.send("Fetch.failRequest", {"requestId": ev["requestId"],
                                                   "errorReason": "BlockedByClient"})
            except Exception as e:
                estado["errores"].append(repr(e)[:200])

        def hints(ev):
            cab = {k.lower(): v for k, v in (ev.get("headers") or {}).items()}
            estado["early_hints"].append(str(cab.get("link", "sin Link"))[:300])

        # las respuestas del documento principal (no las que arma la intercepción),
        # por si la navegación termina con error
        respuestas = []

        def respuesta(r):
            try:
                if (r.frame == pagina.main_frame and r.request.is_navigation_request()
                        and MARCA_INTERNA not in r.headers):
                    respuestas.append(r)
            except Exception as e:
                estado["errores"].append(repr(e)[:200])

        pagina.on("response", respuesta)
        cdp.on("Fetch.requestPaused", pausado)
        cdp.on("Network.responseReceivedEarlyHints", hints)
        cdp.send("Network.enable")
        cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
        t0 = _reloj()
        try:
            resp, error_nav = None, None
            try:
                resp = pagina.goto(url, wait_until="load", timeout=TIEMPO_PAGINA_MS)
            except (TiempoPW, ErrorPW) as e:
                error_nav = e
            if resp is not None and MARCA_INTERNA in resp.headers:
                resp = None                 # la respuesta la armó la intercepción
            agotado = isinstance(error_nav, TiempoPW)
            if resp is None and not agotado:    # la última respuesta del documento, si llegó
                finales = [r for r in respuestas if not 300 <= r.status < 400]
                resp = finales[-1] if finales else None
            p["dur"] = _reloj() - t0
            primera = str(error_nav or "sin respuesta").splitlines()[0][:300]
            if estado["frenada"]:
                clase, detalle = estado["frenada"]
                p.update(resultado=clase, detalle=detalle, tarjetas=[])
                tres = [r for r in respuestas if 300 <= r.status < 400]
                if tres:
                    p.update(estado=tres[-1].status, cabeceras=cabeceras_vistas(tres[-1].headers))
                    if clase == "bloqueado":
                        p["visto"] = lo_que_se_vio(tres[-1].status, tres[-1].headers, "", "")
            elif agotado:                   # no se lee un cuerpo que no terminó de llegar
                p.update(resultado="sin respuesta", detalle=f"tiempo agotado: {primera}",
                         tarjetas=[])
            elif resp is None:
                if not estado["salieron"]:
                    p.update(resultado="error del script",
                             detalle=f"no salió ningún pedido: {primera}")
                elif estado["extra"]:
                    p.update(resultado="sin página",
                             detalle=f"Chromium quiso navegar otra vez (a {estado['extra'][:150]}) "
                                     "y la prueba no lo dejó salir (posible Critical-CH)")
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
        p["saltos_seguidos"] = estado["seguidos"]
        p["pausas_saltos"] = estado["pausas_saltos"]
        p["pedidos_http"] = estado["salieron"]
        p["subpedidos"] = {"salieron": estado["salieron"], "frenados": estado["frenados"],
                           "navegacion_extra": estado["extra"], "errores": estado["errores"]}
        if estado["early_hints"]:
            # por HTTP/1.1 Chromium no los usa; si igual llega uno, no se sigue
            p["early_hints"] = estado["early_hints"]
            p["frena_sitio"] = ("llegó un 103 Early Hints (Link: " + estado["early_hints"][0][:120]
                                + "): la prueba no le pide nada más a este sitio")
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
        titulo = titulo_de_html(html)
        p.update(estado=resp.status, bytes=len(cuerpo), url_final=resp.url,
                 cabeceras=cabeceras_vistas(cabeceras), html=html, titulo=titulo)
        # el estado y las cabeceras van antes que el lector: un error suyo no tapa un bloqueo
        bloqueo = ver_bloqueo_http(resp.status, cabeceras)
        if bloqueo:
            texto = _sin_fallar(lambda: texto_de_html(html)[0], avisos, "sacar el texto", "")
            p.update(texto=texto, tarjetas=[], resultado="bloqueado", detalle=bloqueo,
                     visto=lo_que_se_vio(resp.status, cabeceras, titulo, texto))
            if avisos:
                p["avisos"] = avisos
            return
        try:
            if not pagina.url.startswith(("http://", "https://")):
                raise ErrorPW(f"la página quedó en {pagina.url[:60]}")
            titulo = pagina.title() or titulo
            leido = pagina.evaluate(_LEER_TEXTO)
            texto, hubo_main = leido["texto"] or "", bool(leido["main"])
            origen = "innerText"
        except ErrorPW as e:
            texto, hubo_main = _sin_fallar(lambda: texto_de_html(html), avisos, "sacar el texto",
                                           ("", "<main" in html.lower()))
            origen = "HTML de la respuesta"
            avisos.append("sin innerText (" + str(e).splitlines()[0][:150] + "): se leyó el HTML")
        if estado["extra"]:
            avisos.append(f"se frenó otra navegación, a {estado['extra']}")
        tarjetas = _sin_fallar(lambda: leer_tarjetas(texto), avisos, "leer las tarjetas", [])
        p.update(titulo=titulo, hubo_main=hubo_main, origen=origen, tarjetas=tarjetas, texto=texto)
        if avisos:
            p["avisos"] = avisos
        hay = hay_precios_en(tarjetas, html)
        bloqueo = ver_bloqueo(resp.status, cabeceras, html, texto, titulo, hay, hubo_main)
        if not bloqueo and estado["extra"] and not hay:
            bloqueo = ("la página quiso navegar a otra (posible chequeo del navegador) "
                       "y no trae precios")
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

def _sin_scripts(html: str) -> str:
    """El HTML con el contenido de cada <script> vaciado: lo que se guarda en
    crudo/ no lleva el código ni las claves que el sitio trae adentro."""
    return re.sub(r"(<script\b[^>]*>).*?(</script\s*>)", r"\1\2", html, flags=re.I | re.S)


def correr(salida: str, bases: dict, pausa: float, saltar=()) -> dict:
    inicio = ahora_utc()
    t0 = _reloj()
    corrida = {
        "inicio_utc": inicio.isoformat(timespec="seconds"),
        "sitios": list(bases), "bases": bases, "terminos": TERMINOS,
        "pausa_pedida": pausa, "pausas": {}, "tope": TOPE_BUSQUEDAS,
        "ua": {}, "robots": {}, "pedidos": [], "frenados": {}, "saltados": sorted(saltar),
        "terminada": False,
        "entorno": {"python": platform.python_version(), "plataforma": platform.platform(),
                    "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                    "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                    "github_sha": os.environ.get("GITHUB_SHA"),
                    "runner": os.environ.get("ImageOS") or os.environ.get("RUNNER_OS")},
    }
    os.makedirs(os.path.join(salida, "crudo"), exist_ok=True)
    ritmo, tope = Ritmo(), Tope()
    robots = {}

    def avance():
        """Lo que va de la corrida, guardado: si se corta, el resumen lo dice."""
        corrida["busquedas_pedidas"] = tope.usados
        corrida["ultimo_utc"] = ahora_utc().isoformat(timespec="seconds")
        corrida["segundos"] = round(_reloj() - t0, 1)
        guardar_corrida(salida, corrida)

    def en_curso(sitio: str, fase: str, termino):
        corrida["en_curso"] = {"sitio": sitio, "fase": fase, "termino": termino,
                               "inicio_utc": ahora_utc().isoformat(timespec="seconds")}
        avance()

    def anotar(p: dict, sitio: str, fase: str, termino, n_termino, desde):
        corrida.pop("en_curso", None)
        p.update(n=len(corrida["pedidos"]) + 1, sitio=sitio, fase=fase, termino=termino,
                 desde_anterior=desde)
        nombre = f"{fase}_{sitio}_{n_termino:02d}_{slug(termino or 'robots')}"
        texto, html = p.pop("texto", None), p.pop("html", None)
        try:
            if texto is not None:
                with open(os.path.join(salida, "crudo", nombre + ".txt"), "w",
                          encoding="utf-8") as fh:
                    fh.write(texto)
                p["crudo"] = f"crudo/{nombre}.txt"
            if html:
                with gzip.open(os.path.join(salida, "crudo", nombre + ".html.gz"), "wt",
                               encoding="utf-8") as fh:
                    fh.write(_sin_scripts(html))
                p["crudo_html"] = f"crudo/{nombre}.html.gz"
        except OSError as e:                # sin disco: el pedido igual queda anotado
            p.setdefault("avisos", []).append(f"no se pudo guardar en crudo/: {e!r}"[:200])
        corrida["pedidos"].append(p)
        motivo = None
        if p.get("resultado") in DETIENEN:
            motivo = {"resultado": p["resultado"], "detalle": p.get("detalle")}
        elif p.get("frena_sitio"):
            motivo = {"resultado": "frenado por la prueba", "detalle": p["frena_sitio"]}
        if motivo and sitio not in corrida["frenados"]:
            corrida["frenados"][sitio] = {"fase": fase, "termino": termino, **motivo}
        avance()
        print(f"[{fase}] {sitio:15} {str(termino or ''):20} {p.get('estado', '-')!s:4} "
              f"{miles(p.get('bytes')):>10} bytes {len(p.get('tarjetas') or []):2} tarjetas "
              f"{p.get('resultado', '')}: {p.get('detalle', '')}"[:200], flush=True)

    def terminar():
        corrida.pop("en_curso", None)
        corrida["fin_utc"] = ahora_utc().isoformat(timespec="seconds")
        corrida["terminada"] = True
        avance()
        return corrida

    # 0. Chromium primero, sin red: si no parte, no se pide nada (así una
    # segunda corrida no repite la fase A)
    gestor = nav = None
    try:
        from playwright.sync_api import sync_playwright
        gestor = sync_playwright()
        pw = gestor.__enter__()
        nav = NavegadorB(pw)
    except Exception as e:
        corrida["error_navegador"] = repr(e)[:500]
        print(f"Chromium no partió, no se pide nada: {e!r}"[:300], flush=True)
        if gestor is not None:
            try:
                gestor.__exit__(None, None, None)
            except Exception:
                pass
        return terminar()
    corrida["ua"]["B"] = nav.ua
    corrida["chromium"] = nav.version
    corrida["args_chromium"] = list(ARGS_CHROMIUM)
    try:
        _pedir_todo(corrida, bases, pausa, saltar, nav, ritmo, tope, robots, en_curso, anotar)
    finally:
        for cerrar in (nav.cerrar, lambda: gestor.__exit__(None, None, None)):
            try:
                cerrar()
            except Exception:
                pass
    return terminar()


def _pedir_todo(corrida, bases, pausa, saltar, nav, ritmo, tope, robots, en_curso, anotar):
    sesion = sesion_a()
    corrida["ua"]["A"] = sesion.headers["User-Agent"]

    # 1. robots.txt de cada sitio, antes que nada
    for sitio, base in bases.items():
        if sitio in saltar:
            corrida["frenados"][sitio] = {"fase": "saltado", "termino": None,
                                          "resultado": "no se probó",
                                          "detalle": "se saltó a pedido (--saltar)"}
            continue
        ritmo.pausas[sitio] = pausa_del_sitio(pausa, base, None)
        inicio_p = ahora_utc()
        en_curso(sitio, "robots", None)
        info, rob = bajar_robots(sesion, base, ritmo, sitio)
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
        info["busquedas_permitidas"] = sum(1 for t in TERMINOS
                                           if rob.permite(ruta_de(url_busqueda(base, t))))
        ritmo.pausas[sitio] = pausa_del_sitio(pausa, base, rob.crawl_delay)
    corrida["pausas"] = dict(ritmo.pausas)

    def toca(sitio: str, base: str, fase: str, termino: str, n: int) -> bool:
        if sitio in corrida["frenados"]:
            return False
        motivo = None
        if not robots[sitio].permite(ruta_de(url_busqueda(base, termino))):
            motivo = "robots.txt bloquea esta búsqueda"
        elif not tope.queda():
            motivo = f"se llegó al tope de {tope.tope} pedidos"
        if motivo:
            anotar({"url": url_busqueda(base, termino), "resultado": "no se pidió",
                    "detalle": motivo, "tarjetas": []}, sitio, fase, termino, n, None)
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
            en_curso(sitio, "A", termino)
            try:
                p = fase_a(sesion, base, termino, robots[sitio], ritmo, sitio, tope)
            except Exception as e:          # un error del script, no del sitio
                p = {"url": url_busqueda(base, termino), "resultado": "error del script",
                     "detalle": repr(e)[:300], "tarjetas": []}
            ritmo.termino(sitio)
            p["inicio_utc"] = inicio_p.isoformat(timespec="seconds")
            anotar(p, sitio, "A", termino, n, desde)

    # 3. fase B: navegador sin interfaz
    try:
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
                en_curso(sitio, "B", termino)
                try:
                    p = nav.pedir(base, termino, robots[sitio], ritmo, sitio, tope)
                except Exception as e:
                    p = {"url": url_busqueda(base, termino), "resultado": "error del script",
                         "detalle": repr(e)[:300], "tarjetas": []}
                ritmo.termino(sitio)
                p["inicio_utc"] = inicio_p.isoformat(timespec="seconds")
                anotar(p, sitio, "B", termino, n, desde)
    except Exception as e:                  # algo del navegador que no es de un pedido
        corrida["error_fase_b"] = repr(e)[:500]
        print(f"[B] la fase B no pudo seguir: {e!r}"[:300], flush=True)


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
        if p.get("resultado") in ("sin respuesta", "error del servidor",
                                  "redirección fuera de lo permitido"):
            return f"posible: {p['resultado']} en \"{p['termino']}\" ({p.get('detalle')})"
    frenado = corrida["frenados"].get(sitio)
    if frenado and frenado["fase"] != fase:
        if frenado["fase"] == "saltado":
            return "no se probó: se saltó a pedido"
        if frenado["fase"] == "robots":
            return f"no se probó: robots.txt, {frenado['resultado']} ({frenado.get('detalle')})"
        if frenado["fase"] == "A" and fase == "B":
            return f"no se probó: el sitio quedó frenado en la fase A ({frenado['resultado']})"
    if frenado and frenado["resultado"] == "frenado por la prueba" and frenado["fase"] == fase:
        return f"no; la prueba frenó al sitio: {frenado.get('detalle')}"
    return "no"


def _sin_pedidos(corrida: dict, sitio: str, fase: str, ps: list) -> str:
    """Por qué una fase quedó sin pedidos, para la celda de Estado."""
    frenado = corrida["frenados"].get(sitio)
    if frenado and frenado["fase"] == "saltado":
        return "no se pidió: se saltó a pedido"
    if corrida.get("error_navegador"):
        return "no se pidió: Chromium no partió"
    if frenado and frenado["fase"] == "robots":
        return "no se pidió: sin robots.txt que se pudiera usar"
    if ps and all("robots.txt" in str(p.get("detalle")) for p in ps):
        return "no se pidió: robots.txt la bloquea"
    if fase == "B" and corrida.get("error_fase_b"):
        return "no corrió: la fase B falló"
    if frenado and frenado["fase"] == "A" and fase == "B":
        return "no se pidió: el sitio quedó frenado en la fase A"
    if not corrida.get("terminada", True):
        return "no alcanzó a pedirse: la corrida se cortó"
    return "no se pidió"


def _primera(t) -> str:
    if not t:
        return ""
    txt = f"{t['nombre'] or '(sin nombre)'}, {pesos(t['precio'])}"
    if t.get("precio_unidad") is not None:
        txt += f" ({pesos(t['precio_unidad'])} x {t['unidad']})"
    if t.get("oferta"):
        txt += f", oferta: {t['oferta']}"
    return txt


def _de_fase(corrida: dict) -> list:
    return [p for p in corrida["pedidos"] if p["fase"] in FASES]


def resumen_md(corrida: dict, nota: str = "") -> str:
    terminada = corrida.get("terminada", "fin_utc" in corrida)
    ini = dt.datetime.fromisoformat(corrida["inicio_utc"])
    fin = dt.datetime.fromisoformat(corrida.get("fin_utc") or corrida.get("ultimo_utc")
                                    or corrida["inicio_utc"])
    santiago = (f" ({hora_santiago(ini)} a {hora_santiago(fin)} en Santiago)"
                if hora_santiago(ini) else "")
    ent = corrida.get("entorno", {})
    donde = "en GitHub Actions" if ent.get("github_run_id") else "fuera de GitHub Actions"
    if ent.get("github_run_id"):
        donde += f" (corrida {ent['github_run_id']}, {ent.get('runner') or 'runner'})"
    pedidos = _de_fase(corrida)
    desdes = [p["desde_anterior"] for p in corrida["pedidos"] if p.get("desde_anterior") is not None]
    desdes += [x for p in pedidos for x in (p.get("pausas_saltos") or []) if x is not None]
    L = ["# Prueba de lectura de supermercados desde Actions", ""]
    L.append(f"Corrida del {fecha_larga(ini)} {donde}, de {ini:%H:%M:%S} a {fin:%H:%M:%S} UTC"
             f"{santiago}: {duracion(corrida.get('segundos') or 0)}.")
    if not terminada:
        L += ["", "**La corrida se cortó antes de terminar**: lo de abajo es lo que alcanzó a "
                  "anotarse, hasta las " + f"{fin:%H:%M:%S} UTC."]
        cur = corrida.get("en_curso")
        if cur:
            que = "robots.txt" if cur.get("termino") is None else f"\"{cur['termino']}\""
            L.append(f"El pedido de {que} a {cur['sitio']} (fase {cur['fase']}) salió a las "
                     f"{cur['inicio_utc'][11:19]} UTC y no alcanzó a anotarse.")
    if nota:
        L += ["", nota]
    L.append("")
    n_saltos = sum(p.get("saltos_seguidos") or 0 for p in pedidos)
    n_busq = corrida.get("busquedas_pedidas")
    if n_busq is None:
        n_busq = sum(1 + (p.get("saltos_seguidos") or 0) for p in pedidos
                     if p.get("resultado") != "no se pidió")
    robots_p = [p for p in corrida["pedidos"] if p["fase"] == "robots"]
    n_robots = sum(p.get("pedidos_http") or 1 for p in robots_p)
    linea = f"- Pedidos de búsqueda: {n_busq} de un tope de {corrida['tope']}, uno a la vez"
    if n_saltos:
        linea += (f" ({n_saltos} de ellos, saltos de redirección dentro de /busqueda, cada uno "
                  "con su pausa)")
    linea += f", más {n_robots} de robots.txt"
    if any(p.get("redirecciones") for p in robots_p):
        linea += " (contando sus redirecciones)"
    L.append(linea + ".")
    pausas = sorted(set(corrida.get("pausas", {}).values()))
    if pausas:
        txt = " y ".join(segundos(x) for x in pausas)
        L.append(f"- Pausa entre pedidos al mismo sitio, desde que termina el anterior: {txt} o más"
                 + (f" (la menor que hubo fue {segundos(min(desdes))})." if desdes else "."))
    for fase, ua in corrida.get("ua", {}).items():
        L.append(f"- User-Agent de la fase {fase}: `{ua}`")
    if corrida.get("chromium"):
        L.append(f"- Fase B: Chromium {corrida['chromium']} sin interfaz, con JavaScript apagado "
                 "y por HTTP/1.1 (sin HTTP/2 ni QUIC, para que no pida por su cuenta lo que "
                 "anuncie un 103 Early Hints). Solo sale el documento de la búsqueda; estilos, "
                 "scripts, imágenes, iframes y XHR se frenan dentro del navegador.")
    if corrida.get("saltados"):
        L.append(f"- Sin pedirles nada, a pedido: {', '.join(corrida['saltados'])}.")
    if corrida.get("error_navegador"):
        L.append(f"- Chromium no partió, así que no se pidió nada: `{corrida['error_navegador']}`")
    if corrida.get("error_fase_b"):
        L.append(f"- La fase B no pudo seguir: `{corrida['error_fase_b']}`")
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
            estado = _estados(hechas) if hechas else _sin_pedidos(corrida, sitio, fase, ps)
            L.append(f"| {sitio} | {fase}, {nombre} | {len(hechas)} de {len(corrida['terminos'])} "
                     f"| {_celda(estado)} | {precios} | {_celda(_bloqueo_de(corrida, sitio, fase, ps))} |")

    L += ["", "## robots.txt", "",
          "| Sitio | Estado | Crawl-delay | Reglas | Búsquedas de la prueba |", "|---|---|---|---|---|"]
    n_terminos = len(corrida["terminos"])
    for sitio in corrida["sitios"]:
        r = corrida["robots"].get(sitio, {})
        if not r and sitio in corrida.get("saltados", []):
            L.append(f"| {sitio} | no se pidió | sin dato | se saltó a pedido | |")
            continue
        leido = "reglas" in r
        n_ok = r.get("busquedas_permitidas")
        if n_ok is None and r.get("busqueda_permitida") is not None:    # corridas anteriores
            n_ok = n_terminos if r["busqueda_permitida"] else 0
        if n_ok is None:
            permitidas = ""
        elif n_ok == n_terminos:
            permitidas = f"permitidas en las {n_terminos}"
        elif n_ok == 0:
            permitidas = f"bloqueadas en las {n_terminos}"
        else:
            permitidas = f"permitidas en {n_ok} de {n_terminos}"
        cd = r.get("crawl_delay")
        crawl = segundos(cd) if cd is not None else ("no tiene" if leido else "sin dato")
        estado = str(r.get("estado", r.get("resultado", "")))
        saltos = r.get("redirecciones") or []
        if saltos:
            estado += f" (redirigió a {', '.join(_ruta_o_url(s, corrida['bases'][sitio]) for s in saltos)})"
        reglas = "; ".join(x for x in (r.get("reglas"), r.get("detalle")) if x)
        L.append(f"| {sitio} | {_celda(estado)} | {crawl} | {_celda(reglas)} | {permitidas} |")

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
    numero = 0
    for p in corrida["pedidos"]:
        if p.get("resultado") == "no se pidió":
            continue
        numero += 1
        hora = p.get("inicio_utc", "")[11:19]
        base = corrida["bases"].get(p["sitio"], "")
        saltos = p.get("redirecciones") or []
        seguidos = p.get("saltos_seguidos")
        pedido = ruta_de(p["url"])
        if saltos:
            pedido += f" (redirigió a {', '.join(_ruta_o_url(s, base) for s in saltos)}"
            if seguidos is not None and p["fase"] in FASES:
                pedido += f"; se siguieron {seguidos}"
            pedido += ")"
        desde = segundos(p["desde_anterior"]) if p.get("desde_anterior") is not None else ""
        pausas_saltos = [x for x in (p.get("pausas_saltos") or []) if x is not None]
        if pausas_saltos:
            desde += " y " + ", ".join(segundos(x) for x in pausas_saltos) + " antes de los saltos"
        dur = segundos(p["dur"]) if p.get("dur") is not None else ""
        L.append(f"| {numero} | {hora} | {p['sitio']} | {p['fase']} | `{_celda(pedido)}` "
                 f"| {p.get('estado', p.get('resultado', ''))} | {miles(p.get('bytes'))} | {dur} "
                 f"| {desde.strip()} |")
    no_pedidos = [p for p in corrida["pedidos"] if p.get("resultado") == "no se pidió"]
    if no_pedidos:
        L += ["", "No se pidieron:"]
        for p in no_pedidos:
            L.append(f"- {p['sitio']}, fase {p['fase']}, \"{p['termino']}\": {p.get('detalle')}")
    L += ["", "Las tarjetas (hasta 8 por búsqueda) están en resultado.csv. En crudo/ quedan el "
              "texto leído de cada página y el HTML que llegó, comprimido y sin el contenido de "
              "sus scripts."]
    return "\n".join(L) + "\n"


def _ruta_o_url(url: str, base: str) -> str:
    """La ruta, si es del mismo sitio; la URL completa, si es de otro."""
    d, b = urlsplit(url), urlsplit(base)
    return ruta_de(url) if (d.scheme, d.netloc) == (b.scheme, b.netloc) else url


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
    ap.add_argument("--saltar", action="append", default=[], metavar="SITIO",
                    help="no le pide nada a ese sitio (por ejemplo, si bloqueó en una corrida "
                         "anterior: no se reintenta)")
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
    for sitio in a.saltar:
        if sitio not in SITIOS:
            ap.error(f"--saltar {sitio}: sitio desconocido")
    saltar = set(a.saltar)
    # la prueba es desde Actions: fuera de ahí no se toca a los supermercados
    reales = [s for s, b in bases.items()
              if s not in saltar and urlsplit(b).hostname not in ("127.0.0.1", "localhost")]
    if reales and os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"No corre: {' y '.join(reales)} solo se {'leen' if len(reales) > 1 else 'lee'} "
              "desde GitHub Actions. Para ensayar, "
              "--base jumbo.cl=http://127.0.0.1:PUERTO --base santaisabel.cl=http://127.0.0.1:PUERTO",
              file=sys.stderr)
        return 2
    corrida = correr(a.salida, bases, a.pausa, saltar)
    escribir_salidas(a.salida, corrida)
    if corrida.get("error_navegador"):
        print(f"no se pidió nada: Chromium no partió; {a.salida}/resumen.md", file=sys.stderr)
        return 1
    print(f"listo en {segundos(corrida['segundos'])}: {corrida['busquedas_pedidas']} pedidos de "
          f"búsqueda; {a.salida}/resultado.csv y {a.salida}/resumen.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

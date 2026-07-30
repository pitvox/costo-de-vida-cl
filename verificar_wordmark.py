"""
verificar_wordmark.py - test de aceptación de la capa de texto del wordmark
===========================================================================
Corre DESPUÉS del build (python build_site.py) y verifica que la capa de
texto del DOM contenga exactamente "CARESTÍA" (una sola Í precompuesta) en
index.html y en 2 páginas de producto de muestra: es lo que leen Google,
el copy-paste y los lectores de pantalla.

El adorno en brasa vive en un pseudo-elemento CSS (content), que NO forma
parte de la capa de texto, así que basta con extraer el texto visible del
HTML (sin <script>/<style> ni tags) y comprobar:
  - "CARESTÍA" presente (NFC, Í única precompuesta)
  - "CARESTIÍA" ausente y ninguna secuencia "IÍ" (el bug: I + Í apiladas)

Solo stdlib. Sale con código 1 si alguna página falla.

Correr:
  python build_site.py
  python verificar_wordmark.py
"""

import glob
import html
import re
import sys
import unicodedata


def texto_visible(path: str) -> str:
    """Aproximación de innerText para páginas estáticas: HTML sin scripts,
    estilos ni tags, con entidades resueltas, normalizado a NFC (la Í puede
    venir precompuesta o como I + tilde combinante; NFC unifica)."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    src = re.sub(r"<(script|style)\b.*?</\1>", " ", src, flags=re.S | re.I)
    src = re.sub(r"<[^>]+>", "", src)
    return unicodedata.normalize("NFC", html.unescape(src))


def verificar(path: str) -> bool:
    t = texto_visible(path)
    bien = "CARESTÍA" in t
    mal = "CARESTIÍA" in t or re.search("IÍ", t) is not None
    ok = bien and not mal
    detalle = "" if ok else (
        "  → " + ("falta CARESTÍA con Í única" if not bien else "") +
        ("contiene la secuencia I+Í del bug" if mal else ""))
    print(("OK     " if ok else "FALLA  ") + path + detalle)
    return ok


paginas = ["index.html"] + sorted(glob.glob("productos/*.html"))[:2]
if len(paginas) < 3:
    print("AVISO: faltan páginas de producto; ¿corriste build_site.py?")
resultados = [verificar(p) for p in paginas]
sys.exit(0 if resultados and all(resultados) else 1)

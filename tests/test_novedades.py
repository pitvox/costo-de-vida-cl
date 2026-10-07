"""/novedades.html y la leyenda de Advanced Charts. Sin red: el build corre en
un directorio temporal con el indices.json sintético de test_datos.

Verifica que la nota del dueño vaya literal (título, fecha y texto, con el
link a TradingView sin rel), que la página esté en el pie de todas las
páginas, en el sitemap y en el workflow de publicación, y que la leyenda de
la librería no muestre los parámetros de comparaciones e indicadores."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_datos import indices_realista  # noqa: E402

TITULO = "Carestía ahora usa los gráficos de TradingView"
FECHA = "7 de octubre de 2026"
TEXTO = ("Desde octubre de 2026, los gráficos de Carestía funcionan con Advanced Charts, "
         "la librería de gráficos de [TradingView](https://www.tradingview.com/). Ahora puedes "
         "acercarte y moverte por toda la historia, cambiar entre línea y velas, comparar "
         "productos entre sí y usar herramientas de dibujo e indicadores, en el computador y en "
         "el celular. Los datos no cambian: siguen siendo los precios al consumidor que publica "
         "ODEPA cada semana, ajustados por inflación con el IPC del Banco Central de Chile. "
         "Carestía es gratis y no pide cuenta. Gracias a TradingView por la licencia que lo hace "
         "posible.")


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_novedades")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(indices_realista(), ensure_ascii=False),
                                    encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8", CARESTIA_TARJETAS="0")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def test_nota_del_dueno_literal():
    with open(os.path.join(RAIZ, "textos", "novedades.md"), encoding="utf-8") as fh:
        md = fh.read()
    assert md == f"## {TITULO}\n\n{FECHA}\n\n{TEXTO}\n"


def test_pagina_de_novedades(sitio):
    h = _leer(sitio, "novedades.html")
    assert "<title>Novedades | Carestía</title>" in h
    assert '<link rel="canonical" href="https://carestia.cl/novedades.html">' in h
    main = h[h.index("<main"):h.index("</main>")]
    assert main.startswith('<main class="doc novedades">')
    assert "<h1>Novedades</h1>" in main
    # el título de cada nota, como titular
    assert ".novedades h2 { font:600 20px/1.3 var(--sans); letter-spacing:0; color:var(--bone);" in h
    assert f"<h2>{TITULO}</h2>" in main
    # la fecha de la nota, legible y en la etiqueta
    assert f'<p class="meta"><time datetime="2026-10-07">{FECHA}</time></p>' in main
    texto = TEXTO.replace("[TradingView](https://www.tradingview.com/)",
                          '<a href="https://www.tradingview.com/">TradingView</a>')
    assert f"<p>{texto}</p>" in main
    # el link a TradingView, sin rel (ni nofollow, ni ugc, ni sponsored)
    links = re.findall(r'<a\b[^>]*href="https://www\.tradingview\.com/"[^>]*>', main)
    assert links == ['<a href="https://www.tradingview.com/">']
    assert main.index(f"<h2>{TITULO}</h2>") < main.index("<time") < main.index("Desde octubre")


def test_novedades_en_el_pie_el_sitemap_y_el_workflow(sitio):
    for p in ["index.html", "graficos.html", "productos/producto-000.html", "acerca.html",
              "metodologia.html", "prensa.html", "404.html", "indices/asado.html"]:
        assert '<a href="https://carestia.cl/novedades.html">Novedades</a>' in _leer(sitio, p), p
    assert ('<a href="https://carestia.cl/novedades.html" aria-current="page">Novedades</a>'
            in _leer(sitio, "novedades.html"))
    locs = re.findall(r"<loc>([^<]+)</loc>", _leer(sitio, "sitemap.xml"))
    assert "https://carestia.cl/novedades.html" in locs
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        assert "cp novedades.html public/novedades.html" in fh.read()


def test_leyenda_sin_parametros_de_comparaciones_e_indicadores(sitio):
    """El "close" de cada comparada (la librería no lo traduce) y el largo de
    cada indicador no van en la leyenda: en /graficos.html, las fichas y
    /prueba-graficos.html, que usan los mismos overrides."""
    tv = _leer(sitio, "carestia-tv.js")
    assert ("const SIN_PARAMETROS = { 'paneProperties.legendProperties.showStudyArguments': "
            "false };") in tv
    ov = tv[tv.index("function overrides(tok)"):tv.index("const colorLinea")]
    assert "const o = Object.assign({}, SIN_PARAMETROS, {" in ov
    # lo que la librería guarda en el navegador manda sobre 'overrides': se
    # vuelve a aplicar al quedar listo el widget (montar y alistarWidget)
    assert "try { widget.applyOverrides(SIN_PARAMETROS); } catch (e) {}" in tv
    montar = tv[tv.index("function montar(o)"):tv.index("function capturaCliente(")]
    assert "if (hecho) return;\n          sinParametros(widget);" in montar
    alistar = tv[tv.index("function alistarWidget(widget, feed, tok) {"):tv.index("function estiloPorSimbolo(")]
    assert "sinParametros(widget);" in alistar
    # las tres páginas arman el widget con opcionesWidget, que usa overrides
    assert "const ov = overrides(o.tok);" in tv
    for p in ["graficos.html", "prueba-graficos.html"]:
        assert "TV.montar(" in _leer(sitio, p) or "TV.opcionesWidget({" in _leer(sitio, p), p
    assert "TV.montar(" in _leer(sitio, "carestia-ficha.js")

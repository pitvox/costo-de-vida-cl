"""El buscador de productos (carestia-busca.js) y la pantalla completa de los
gráficos. Sin red: build_site.py corre en un directorio temporal con el
indices.json del tamaño real de test_datos.py.

El buscador va entero en su archivo: las páginas llevan solo su etiqueta
(la portada tiene un tope de peso y las fichas no llevan nada del catálogo).
La pantalla completa se prueba en Node (tests/pantalla_node.js) con un
documento y un gráfico de mentira."""
import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
from test_datos import indices_realista  # noqa: E402
from test_tradingview import _build, _leer  # noqa: E402

NODE = shutil.which("node")
ETIQUETA = re.compile(r'<script defer src="/carestia-busca\.js\?v=([0-9a-f]{10})"></script>')


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build_buscador"), indices_realista())


def _paginas(sitio) -> list:
    return sorted(glob.glob(os.path.join(sitio, "*.html")) +
                  glob.glob(os.path.join(sitio, "*", "*.html")))


# ---------- el buscador ----------
def test_todas_las_paginas_llevan_el_buscador_una_vez(sitio):
    """Cada página con encabezado lleva la etiqueta del archivo, con la misma
    versión, y nada más del buscador: ni su CSS ni su JS."""
    versiones = set()
    for ruta in _paginas(sitio):
        h = open(ruta, encoding="utf-8").read()
        if 'class="sitenav"' not in h:
            continue
        m = ETIQUETA.findall(h)
        assert len(m) == 1, ruta
        versiones.add(m[0])
        assert "sb-caja" not in h and "pbusca" not in h, ruta
    assert len(versiones) == 1
    # el encabezado de todas: portada, gráficos, ficha, catálogo y textos
    for p in ["index.html", "graficos.html", "productos/index.html",
              "productos/producto-000.html", "metodologia.html", "404.html"]:
        assert ETIQUETA.search(_leer(sitio, p)), p


def test_el_archivo_del_buscador(sitio):
    js = _leer(sitio, "carestia-busca.js")
    # el catálogo, con la versión de los datos, se pide al usarlo
    assert re.search(r"fetch\('/datos/catalogo\.json\?v=[0-9a-f]{10}'\)", js)
    assert js.count("fetch(") == 1
    # los 4 índices van al gráfico de cada uno
    for code in ["asado", "ensalada", "fruta", "desayuno"]:
        assert f'"h":"/graficos.html#{code}"' in js, code
    # su CSS viaja con él; 16px en los campos: con menos, Safari del iPhone
    # acerca la página al enfocarlos
    assert ".sb-q { display:block; width:100%; height:44px; padding:0 12px;" in js
    assert "font:400 16px var(--sans)" in js
    assert "Ningún producto con ese nombre." in js
    # sin tokens del build sin reemplazar
    assert not re.search(r"__[A-Z_]+__", js)
    if NODE:
        r = subprocess.run([NODE, "--check", os.path.join(sitio, "carestia-busca.js")],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_la_portada_y_el_catalogo_reservan_el_lugar_del_campo(sitio):
    """El campo llega con el archivo: su alto ya está en la página, para que
    la tabla y la lista no salten."""
    portada = _leer(sitio, "index.html")
    assert portada.count('<div id="pbh" style="min-height:44px"></div>') == 1
    assert portada.index('id="pbh"') < portada.index('class="chips"')
    assert "#pbh, .chips { order:1; }" in portada
    catalogo = _leer(sitio, "productos/index.html")
    assert catalogo.count('<div id="pbh" style="min-height:44px;margin-top:20px"></div>') == 1
    assert catalogo.index('id="pbh"') < catalogo.index('class="grupos"')
    # las demás no
    assert 'id="pbh"' not in _leer(sitio, "graficos.html")
    assert 'id="pbh"' not in _leer(sitio, "productos/producto-000.html")


def test_el_workflow_publica_el_archivo_del_buscador():
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"), encoding="utf-8") as fh:
        assert "cp carestia-busca.js public/carestia-busca.js" in fh.read()


# ---------- la pantalla completa ----------
def test_la_ficha_lleva_la_pantalla_completa(sitio):
    h = _leer(sitio, "productos/producto-000.html")
    assert h.count('id="pc-abrir"') == 1 and h.count('id="pc-cerrar"') == 1
    assert "<span>pantalla completa</span>" in h
    # la barra, dentro del marco y antes del gráfico, con el nombre del producto
    marco = h[h.index('<div class="marco" id="marco">'):h.index('<div id="grafico">')]
    assert re.search(r'<div class="pc-barra"><span class="pc-tit" id="pc-tit">[^<]+</span>', marco)
    assert ".marco.pc #grafico { flex:1 1 0; aspect-ratio:auto; min-height:0;" in h
    assert "html.pc-abierta, html.pc-abierta body { overflow:hidden; }" in h
    js = _leer(sitio, "carestia-ficha.js")
    assert js.count("function pantallaCompleta(o)") == 1
    assert ("pantallaCompleta({ caja: $('marco'), abrir: [$('pc-abrir')], "
            "cerrar: $('pc-cerrar'),") in js
    assert not re.search(r"__[A-Z_]+__", js)


def test_graficos_lleva_la_pantalla_completa(sitio):
    h = _leer(sitio, "graficos.html")
    # el botón de la fila de controles y, para el celular, el del lienzo
    assert h.count('id="pc-abrir"') == 1 and h.count('class="pc-abrir pc-lienzo"') == 1
    hero = h[h.index('<section class="hero-wrap" id="hero">'):h.index('<div id="chart"')]
    assert 'class="pc-barra"' in hero and 'class="pc-abrir pc-lienzo"' in hero
    assert h.count("function pantallaCompleta(o)") == 1
    assert "abrir: [...document.querySelectorAll('.pc-abrir')]" in h
    assert ".hero-wrap.pc .overlay { display:none !important; }" in h
    assert "__BOTON_PC" not in h and "__BARRA_PC__" not in h and "__CSS_PANTALLA__" not in h


@pytest.mark.skipif(NODE is None, reason="requiere node")
def test_pantalla_completa_en_node(sitio):
    r = subprocess.run([NODE, os.path.join(RAIZ, "tests", "pantalla_node.js"), str(sitio)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(NODE is None, reason="requiere node")
def test_en_el_celular_la_barra_de_dibujo_parte_cerrada(sitio):
    """En el celular la barra de dibujo de la librería parte cerrada (sigue
    disponible: no se desactiva); en pantallas anchas, abierta como siempre."""
    codigo = """
      const TV = require(process.argv[1]);
      const base = { contenedor: 'tv', libreria: '/charting_library/', simbolo: 'asado',
        datafeed: {}, tok: n => '#000000', css: 'x' };
      const mov = TV.opcionesWidget(Object.assign({ movil: true }, base));
      const esc = TV.opcionesWidget(Object.assign({ movil: false }, base));
      const F = 'hide_left_toolbar_by_default';
      if (!mov.enabled_features.includes(F) || esc.enabled_features.includes(F) ||
          mov.disabled_features.includes('left_toolbar')) process.exit(1);
    """
    r = subprocess.run([NODE, "-e", codigo, os.path.join(sitio, "carestia-tv.js")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

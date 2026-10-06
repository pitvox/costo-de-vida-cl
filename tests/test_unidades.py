"""Unidades de los gráficos (ajustado por inflación y precio de la época) en
el build, sin red. build_site.py corre en directorios temporales con el
indices.json sintético de test_datos.py: sin datos/uf.json, con uno que cubre
todas las semanas y con uno roto.

La UF salió de la interfaz por decisión del dueño: ninguna página la ofrece,
haya o no datos/uf.json, que uf.py sigue escribiendo y se publica tal cual
con datos/ (el build ya no lo lee, así que un uf.json roto tampoco lo corta).
Verifica además los nombres y las líneas literales del selector (con el mes
del último IPC), que todos los gráficos partan en línea y en 1S, y que el
workflow siga obteniendo la UF con uf.py antes de generar el sitio."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_datos import indices_realista  # noqa: E402
from test_tradingview import uf_sintetica  # noqa: E402


def _build(d, uf=None):
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(indices_realista(), ensure_ascii=False),
                                    encoding="utf-8")
    if uf is not None:
        (d / "datos").mkdir()
        (d / "datos" / "uf.json").write_text(json.dumps(uf), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d, r.stdout


@pytest.fixture(scope="module")
def sin_uf(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("sin_uf"))


@pytest.fixture(scope="module")
def con_uf(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("con_uf"), uf_sintetica())


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _app(d):
    h = _leer(d, "graficos.html")
    return json.loads(re.search(r"const DATA = (\{.*?\});\n", h).group(1).replace("<\\/", "</"))


PAGINAS = ["graficos.html", "productos/producto-000.html"]


def _con_js(d, p):
    """La página y, en una ficha, su JS común (carestia-ficha.js)."""
    h = _leer(d, p)
    return h + _leer(d, "carestia-ficha.js") if p.startswith("productos/") else h


def test_sin_uf_dos_unidades(sin_uf):
    d, log = sin_uf
    assert "AVISO UF" not in log
    assert "uf" not in _app(d)
    for p in PAGINAS:
        h = _leer(d, p)
        assert re.findall(r'data-unidad="(\w+)"', h) == ["real", "epoca"], p
        assert re.findall(r'<option value="(\w+)">', h) == ["real", "epoca"], p


def test_con_uf_la_interfaz_no_la_ofrece_y_se_publica_igual(con_uf, sin_uf):
    d, log = con_uf
    assert "AVISO UF" not in log
    assert "uf" not in _app(d)
    for p in PAGINAS + ["prueba-graficos.html"]:
        h = _leer(d, p)
        assert 'data-unidad="uf"' not in h and '<option value="uf">' not in h, p
        assert ">UF<" not in h and "en UF" not in h and "asado-uf" not in h, p
        # ningún datafeed de las páginas pide los símbolos en UF
        assert "uf: " not in _script(h), p
        if p.startswith("productos/"):
            assert "uf: " not in _leer(d, "carestia-ficha.js"), p
    for p in PAGINAS:
        assert re.findall(r'data-unidad="(\w+)"', _leer(d, p)) == ["real", "epoca"], p
    # datos/uf.json queda tal cual en datos/, que se publica entero
    assert json.loads(_leer(d, "datos/uf.json")) == uf_sintetica()
    # el build no lo lee: la versión de datos/ es la misma con y sin él
    assert _app(d)["ver"] == _app(sin_uf[0])["ver"]


def _script(h):
    return "\n".join(re.findall(r"<script>\n(.*?)</script>", h, re.S))


@pytest.mark.parametrize("caso, contenido", [
    ("texto", lambda: "esto no es json"),
    ("infinito", lambda: _con(100, "Infinity")),
    ("fecha absurda", lambda: '{"t0":"9999-12-27","v":[1]}'),
])
def test_uf_rota_no_corta_el_build(tmp_path, caso, contenido):
    """Un datos/uf.json roto: el build no lo lee, así que sigue igual."""
    shutil.copytree(os.path.join(RAIZ, "textos"), tmp_path / "textos")
    (tmp_path / "indices.json").write_text(json.dumps(indices_realista(), ensure_ascii=False),
                                           encoding="utf-8")
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "uf.json").write_text(contenido(), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, (caso, r.stdout + r.stderr)
    assert 'data-unidad="uf"' not in (tmp_path / "graficos.html").read_text(encoding="utf-8")
    assert (tmp_path / "datos" / "uf.json").read_text(encoding="utf-8") == contenido()


def _con(i, valor):
    """La UF sintética con el lunes i reemplazado por un literal."""
    uf = uf_sintetica()
    v = [json.dumps(x) for x in uf["v"]]
    v[i] = valor
    return '{"t0":"%s","v":[%s]}' % (uf["t0"], ",".join(v))


def test_unidad_y_tipo_por_defecto(con_uf):
    d, _ = con_uf
    tv = _leer(d, "carestia-tv.js")
    # línea por defecto en todos los gráficos; 1S por defecto
    assert "'mainSeriesProperties.style': 2," in tv
    assert "const RESOLUCION = '1W';" in tv
    assert "const RESOLUCIONES = ['1W', '2W', '1M', '3M', '6M', '12M'];" in tv
    assert ("favorites: { intervals: movil ? FAVORITAS_MOVIL : RESOLUCIONES, "
            "chartTypes: ['Line', 'Candles'] },") in tv
    assert "const FAVORITAS_MOVIL = ['1W', '1M', '12M'];" in tv
    # los botones no parten su texto: si no caben, va el desplegable
    for p in PAGINAS:
        assert re.search(r"\.vbtn \{[^}]*white-space:nowrap;", _leer(d, p)), p
    # el selector de temporalidades también en el celular
    solo = re.search(r"const SOLO_ESCRITORIO = \[(.*?)\];", tv, re.S).group(1)
    assert "header_resolutions" not in solo
    for p in PAGINAS:
        h = _con_js(d, p)
        assert ('<button class="vbtn ubtn active" type="button" data-unidad="real" '
                'aria-pressed="true">Ajustado por inflación</button>') in h, p
        # el desplegable, si los dos botones no caben en su fila
        assert "fila.classList.add('midiendo');" in h, p
        assert "if (desborda) caja.classList.add('compacta');" in h, p
    g = _leer(d, "graficos.html")
    assert "let cur = CODES[0], vista = 'linea', unidad = 'real';" in g
    # la leyenda de la línea: las dos unidades en el escritorio y en el
    # celular, la elegida a la vista (pintarLeyenda la sigue)
    assert re.findall(r'<span data-leyenda="(\w+)"', g) == ["real", "epoca"]
    assert re.findall(r'<span class="mleg m-ind" data-leyenda="(\w+)"', g) == ["real", "epoca"]
    assert ('<span data-leyenda="real"><span class="sw"></span>Ajustado por inflación</span>'
            in g)
    assert "e.style.opacity = e.dataset.leyenda === unidad ? '' : '.35';" in g
    # la unidad vale para los índices y Comparar, no para la canasta
    assert 'body[data-modo="canasta"] .m-uni { display:none !important; }' in g
    assert '<div class="unidad m-uni" id="unidad" data-fila="cbar">' in g


# la línea bajo el selector de unidad: textos del dueño, palabra por palabra,
# con el mes del último IPC (indices_realista trae "ipc_mes": "2026-08")
UNIDAD_TXT = {
    "real": "Cada precio pasado, llevado a pesos de agosto de 2026 con el IPC. Sirve para "
            "comparar años distintos.",
    "epoca": "Lo que costaba en su momento, tal como salía en la boleta.",
}


def test_textos_de_la_unidad_literales(con_uf):
    d, _ = con_uf
    for p in PAGINAS:
        h = _con_js(d, p)
        unidad_txt = json.loads(re.search(r"const UNIDAD_TXT = (\{.*?\});", h).group(1))
        assert unidad_txt == UNIDAD_TXT, p
        # la de ajustado por inflación ya va en el HTML, antes del JS
        assert f'id="utxt">{UNIDAD_TXT["real"]}</p>' in h, p
        # los nombres de las opciones, en este orden
        assert re.findall(r'aria-pressed="(?:true|false)">([^<]+)</button>', h) == \
            ["Ajustado por inflación", "Precio de la época"], p
        assert re.findall(r'<option value="\w+">([^<]+)</option>', h) == \
            ["Ajustado por inflación", "Precio de la época"], p


def test_workflow_obtiene_la_uf_antes_de_generar_el_sitio():
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        wf = fh.read()
    pasos = re.findall(r"\n      - name: (.+)", wf)
    assert pasos.index("Validar contra sitio desplegado") < pasos.index("UF") < \
        pasos.index("Generar sitio")
    paso = re.search(r"\n      - name: UF\n(.*?)(?=\n      - name: |\n\s*#)", wf, re.S).group(1)
    assert "BCCH_USER: ${{ secrets.BCCH_USER }}" in paso
    assert "BCCH_PASS: ${{ secrets.BCCH_PASS }}" in paso
    assert "run: python uf.py" in paso
    # uf.py nunca falla: el paso no necesita continue-on-error
    assert "continue-on-error" not in paso
    # datos/ (con uf.json) se publica entero
    assert "cp -r datos public/datos" in wf

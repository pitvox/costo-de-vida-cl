"""Unidades de los gráficos (pesos de hoy, precio de la época y UF) en el
build, sin red. build_site.py corre en directorios temporales con el
indices.json sintético de test_datos.py: sin datos/uf.json, con uno que cubre
todas las semanas y con uno que se queda corto.

Verifica que la opción UF exista solo con un datos/uf.json que cubra todas
las semanas de las series (si no, el build sigue y lo avisa), que la versión
de datos/ cambie con la UF, que todos los gráficos partan en línea y en 1S, y
que el workflow obtenga la UF con uf.py antes de generar el sitio, sin que
pueda cortar el build."""
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
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
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


@pytest.fixture(scope="module")
def uf_corta(tmp_path_factory):
    # la UF termina antes de la última semana de las series (2026-09-21)
    return _build(tmp_path_factory.mktemp("uf_corta"), uf_sintetica(fin="2026-09-14"))


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _app(d):
    h = _leer(d, "graficos.html")
    return json.loads(re.search(r"const DATA = (\{.*?\});\n", h).group(1).replace("<\\/", "</"))


PAGINAS = ["graficos.html", "productos/producto-000.html"]


def test_sin_uf_el_sitio_sale_sin_la_opcion(sin_uf):
    d, log = sin_uf
    assert "AVISO UF: no está datos/uf.json" in log
    assert "El sitio sale sin la opción UF." in log
    assert _app(d)["uf"] is False
    for p in PAGINAS:
        h = _leer(d, p)
        assert 'data-unidad="uf"' not in h and '<option value="uf">' not in h, p
        # pesos de hoy y precio de la época siguen
        assert 'data-unidad="real"' in h and 'data-unidad="epoca"' in h, p
    assert "const UF = false;" in _leer(d, "productos/producto-000.html")
    assert "en pesos de hoy o a precio de la época (por ejemplo, asado-epoca)" in \
        _leer(d, "prueba-graficos.html")


def test_con_uf_la_opcion_existe(con_uf):
    d, log = con_uf
    assert "AVISO UF" not in log
    assert re.search(r"UF: datos/uf\.json, prueba, de 2007-12-31 a 2026-11-02; "
                     r"la del lunes 2026-09-21: [0-9.]+", log)
    assert _app(d)["uf"] is True
    for p in PAGINAS:
        h = _leer(d, p)
        botones = re.findall(r'data-unidad="(\w+)"', h)
        assert botones == ["real", "epoca", "uf"], (p, botones)
        assert re.findall(r'<option value="(\w+)">', h) == ["real", "epoca", "uf"], p
    # datos/uf.json se publica tal cual con datos/
    assert json.loads(_leer(d, "datos/uf.json")) == uf_sintetica()


def test_uf_que_no_cubre_las_series_no_se_ofrece(uf_corta):
    d, log = uf_corta
    assert ("AVISO UF: datos/uf.json va de 2007-12-31 a 2026-09-14 y las series, "
            "de 2008-01-07 a 2026-09-21. El sitio sale sin la opción UF.") in log
    assert _app(d)["uf"] is False
    assert 'data-unidad="uf"' not in _leer(d, "graficos.html")


def test_uf_con_un_lunes_sin_valor(tmp_path):
    uf = uf_sintetica()
    uf["v"][100] = None
    d, log = _build(tmp_path, uf)
    assert "AVISO UF: datos/uf.json no trae la UF de 1 lunes (el primero, 2009-11-30)" in log
    assert _app(d)["uf"] is False


@pytest.mark.parametrize("caso, contenido, motivo", [
    ("infinito", lambda: _con(100, "Infinity"), "no se puede leer (ValueError: Infinity no es JSON)"),
    ("nan al final", lambda: _con(-1, "NaN"), "no se puede leer (ValueError: NaN no es JSON)"),
    ("cero al final", lambda: _con(-1, "0"), "no trae la UF de 1 lunes"),
    ("fecha absurda", lambda: '{"t0":"9999-12-27","v":[1]}', "va de 9999-12-27"),
    ("anidado", lambda: "[" * 100000, "no se puede leer (RecursionError"),
    ("no es un objeto", lambda: "[1, 2]", "no se puede leer (TypeError"),
    ("texto", lambda: "esto no es json", "no se puede leer (JSONDecodeError"),
    ("t0 sin guiones", lambda: _con(0, "19622.66").replace('"2007-12-31"', '"20071231"'),
     "no viene por semanas desde un lunes"),
    ("t0 en semanas ISO", lambda: _con(0, "19622.66").replace('"2007-12-31"', '"2008-W01-1"'),
     "no viene por semanas desde un lunes"),
    ("surrogate suelto", lambda: _con(0, "19622.66").replace('{"t0"', '{"fuente":"\\ud800","t0"'),
     "no se puede leer (UnicodeEncodeError"),
])
def test_uf_rota_no_corta_el_build(tmp_path, caso, contenido, motivo):
    """Un datos/uf.json roto o que el navegador no puede leer: el build sigue,
    sin la opción UF y con el aviso."""
    shutil.copytree(os.path.join(RAIZ, "textos"), tmp_path / "textos")
    (tmp_path / "indices.json").write_text(json.dumps(indices_realista(), ensure_ascii=False),
                                           encoding="utf-8")
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "uf.json").write_text(contenido(), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "AVISO UF: " in r.stdout and motivo in r.stdout, (caso, r.stdout[:400])
    assert 'data-unidad="uf"' not in (tmp_path / "graficos.html").read_text(encoding="utf-8")


def _con(i, valor):
    """La UF sintética con el lunes i reemplazado por un literal."""
    uf = uf_sintetica()
    v = [json.dumps(x) for x in uf["v"]]
    v[i] = valor
    return '{"t0":"%s","v":[%s]}' % (uf["t0"], ",".join(v))


def test_la_version_de_datos_cambia_con_la_uf(sin_uf, con_uf):
    """Los pedidos a datos/ llevan la versión en la URL: si cambia la UF, el
    navegador no mezcla un uf.json viejo con datos nuevos."""
    assert re.fullmatch(r"[0-9a-f]{10}", _app(sin_uf[0])["ver"])
    assert _app(sin_uf[0])["ver"] != _app(con_uf[0])["ver"]


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
        h = _leer(d, p)
        assert ('<button class="vbtn ubtn active" type="button" data-unidad="real" '
                'aria-pressed="true">Pesos de hoy</button>') in h, p
        # el desplegable, si los tres botones no caben en su fila
        assert "fila.classList.add('midiendo');" in h, p
        assert "if (desborda) caja.classList.add('compacta');" in h, p
    g = _leer(d, "graficos.html")
    assert "let cur = CODES[0], vista = 'linea', unidad = 'real';" in g
    # la leyenda de la línea: las tres unidades en el escritorio y en el
    # celular, la elegida a la vista (pintarLeyenda la sigue)
    assert re.findall(r'<span data-leyenda="(\w+)"', g) == ["real", "epoca", "uf"]
    assert re.findall(r'<span class="mleg m-ind" data-leyenda="(\w+)"', g) == ["real", "epoca", "uf"]
    assert "e.style.opacity = e.dataset.leyenda === unidad ? '' : '.35';" in g
    # la ficha en UF: el antetítulo deja de decir "en pesos de hoy"
    assert "miga.textContent = MIGA.replace(/, en pesos de hoy$/, '');" in \
        _leer(d, "productos/producto-000.html")
    # la unidad vale para los índices y Comparar, no para la canasta
    assert 'body[data-modo="canasta"] .m-uni { display:none !important; }' in g
    assert '<div class="unidad m-uni" id="unidad" data-fila="cbar">' in g


# la línea bajo el selector de unidad: textos del dueño, palabra por palabra
UNIDAD_TXT = {
    "real": "Cada precio pasado, llevado a pesos de hoy con la inflación. Sirve para "
            "comparar años distintos.",
    "epoca": "Lo que costaba en su momento, tal como salía en la boleta.",
    "uf": "Cada precio dividido por el valor de la UF de esa semana. Como la UF sube con "
          "la inflación, también sirve para comparar años distintos.",
}


def test_textos_de_la_unidad_literales(con_uf):
    d, _ = con_uf
    for p in PAGINAS:
        h = _leer(d, p)
        unidad_txt = json.loads(re.search(r"const UNIDAD_TXT = (\{.*?\});", h).group(1))
        assert unidad_txt == UNIDAD_TXT, p
        # la de pesos de hoy ya va en el HTML, antes del JS
        assert f'id="utxt">{UNIDAD_TXT["real"]}</p>' in h, p
        # los nombres de las opciones, en este orden
        assert re.findall(r'aria-pressed="(?:true|false)">([^<]+)</button>', h) == \
            ["Pesos de hoy", "Precio de la época", "UF"], p


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

"""Fichas: "Comparar con" (Nivel B). Sin red: el build corre en un directorio
temporal con un indices.json sintético con grupos y variaciones a un año
conocidas.

Verifica las sugerencias de cada ficha (productos de su grupo con datos
recientes, por variación a un año, y los índices que lo llevan), la franja
en el HTML, que Comparar de /graficos.html y la franja de la ficha sean el
mismo componente (el mismo JS y CSS de build_site.py en las dos páginas),
el link compartible (#comparar=...) sin tocar los links de #comparar de
siempre, la captura PNG con la leyenda y la frase, y el componente y la
frase en Node (tests/comparar_node.js, si hay Node)."""
import ast
import datetime
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
from test_datos import FIN, _semanas, indices_realista  # noqa: E402

NODE = shutil.which("node")


def _serie(cambio_anual: float, semanas: int = 160, fin_atras: int = 0) -> list:
    """Precios semanales que terminan 'fin_atras' semanas antes de FIN, con
    el último 'cambio_anual' sobre el de 52 semanas antes."""
    v = [1000 + (i % 7) for i in range(semanas)]
    v[-1] = round(v[-53] * (1 + cambio_anual))
    return v


def _producto(label, grupo, v, fin_atras=0):
    ini = FIN - datetime.timedelta(weeks=len(v) - 1 + fin_atras)
    return {"label": label, "unidad": "kg", "grupo": grupo, "t0": ini.isoformat(), "v": v}


def datos() -> dict:
    """Los índices de test_datos (con sus canastas: la palta va en Asado,
    Ensalada y Desayuno) y productos de dos grupos con variaciones a un año
    conocidas."""
    out = indices_realista()
    p = {
        "palta": _producto("Palta", "Frutas", _serie(0.05)),
        "f_sube": _producto("Sube", "Frutas", _serie(0.50)),
        "f_baja": _producto("Baja", "Frutas", _serie(-0.60)),
        "f_quieto": _producto("Quieto", "Frutas", _serie(0.01)),
        "f_corto": _producto("Corto", "Frutas", [900] * 30),        # sin variación a un año
        "f_medio": _producto("Medio", "Frutas", _serie(-0.20)),
        "f_viejo": _producto("Viejo", "Frutas", _serie(0.90), fin_atras=10),   # sin datos recientes
        "f_otro": _producto("Otro", "Frutas", _serie(0.30)),
        "f_mas": _producto("Más", "Frutas", _serie(0.10)),
        "c_uno": _producto("Carne uno", "Carne bovina", _serie(0.70)),
        "c_dos": _producto("Carne dos", "Carne bovina", _serie(0.20)),
        "tomate": _producto("Tomate", "Hortalizas", _serie(0.02)),
    }
    out["productos"] = p
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_comparar")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(datos(), ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8", CARESTIA_TARJETAS="0")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _script(h):
    """El JS inline de la página (el último <script> sin src)."""
    return re.findall(r"<script>\n(.*?)</script>", h, re.S)[-1]


def _constantes() -> dict:
    """Los strings de nivel superior de build_site.py (los componentes)."""
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    return {n.targets[0].id: n.value.value for n in arbol.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)}


def _sugerencias(h):
    franja = h[h.index('<section class="comparar"'):h.index("</section>", h.index('<section class="comparar"'))]
    return re.findall(r'data-cmp="([^"]+)" aria-pressed="false"><span class="dot"></span>([^<]+)</button>',
                      franja)


# ---------- las sugerencias ----------
def test_sugerencias_del_grupo_por_variacion_y_sus_indices(sitio):
    # la palta va en tres índices: quedan tres lugares para su grupo, por
    # variación a un año en valor absoluto (Baja -60%, Sube +50%, Otro +30%);
    # nunca ella misma ni un producto sin datos recientes (Viejo)
    assert _sugerencias(_leer(sitio, "productos/palta.html")) == [
        ("baja", "Baja"), ("sube", "Sube"), ("otro", "Otro"),
        ("asado", "Índice Asado"), ("ensalada", "Índice Ensalada"),
        ("desayuno", "Índice Desayuno")]


def test_sugerencias_sin_indice_son_seis_del_grupo(sitio):
    # sin índice, seis del grupo; sin variación a un año (Corto), al final
    assert [s for s, _n in _sugerencias(_leer(sitio, "productos/sube.html"))] == \
        ["baja", "otro", "medio", "mas", "palta", "quieto"]
    assert [s for s, _n in _sugerencias(_leer(sitio, "productos/quieto.html"))] == \
        ["baja", "sube", "otro", "medio", "mas", "palta"]
    # un grupo chico: lo que haya, y su índice (el tomate va en Asado y Ensalada)
    assert _sugerencias(_leer(sitio, "productos/carne-uno.html")) == [("carne-dos", "Carne dos")]
    assert _sugerencias(_leer(sitio, "productos/tomate.html")) == [
        ("asado", "Índice Asado"), ("ensalada", "Índice Ensalada")]


# ---------- la franja ----------
def test_franja_bajo_el_grafico(sitio):
    h = _leer(sitio, "productos/palta.html")
    franja = h[h.index('<section class="comparar"'):h.index("</section>", h.index('<section class="comparar"'))]
    assert '<h2 class="otros-h" id="cmp-h">Comparar con</h2>' in franja
    assert ('<input class="psearch" id="cmp-busca" type="search" placeholder="busca otro producto..." '
            'autocomplete="off" aria-label="Busca otro producto para comparar">') in franja
    assert '<p class="cmp-nota" id="cmp-nota" hidden>Puedes comparar hasta 4 a la vez.</p>' in franja
    # la línea de la escala y la frase: las arma el JS con algo elegido
    assert '<p class="cmp-escala" id="cmp-escala" hidden></p>' in franja
    assert '<p class="cmp-frase" id="cmp-frase" hidden></p>' in franja
    # bajo el gráfico y su fecha, antes de los otros productos del grupo
    assert (h.index('<div id="grafico">') < h.index('<div class="fecha">') <
            h.index('<section class="comparar"') < h.index('<section class="otros"'))
    # la captura PNG, junto a la unidad, y el velo mientras se prepara
    assert '<button class="vbtn nomtoggle" id="shot" type="button">captura PNG</button>' in h
    assert '<div class="velo" id="velo" role="status" hidden>Preparando la captura...</div>' in h


def test_max_cuatro_ademas_del_producto(sitio):
    js = _script(_leer(sitio, "productos/palta.html"))
    assert ("const cmp = comparador({ colores: [1, 2, 3, 4].map(i => tok('cmp' + i)), max: 4,\n"
            "    simbolo: k => k + SUF[unidad], principal: () => SLUG + SUF[unidad] });") in js


# ---------- el mismo componente en las dos páginas ----------
def test_comparar_y_la_ficha_son_el_mismo_componente(sitio):
    c = _constantes()
    g, f = _leer(sitio, "graficos.html"), _leer(sitio, "productos/palta.html")
    for nombre in ["JS_COMPARAR", "JS_CAPTURA", "CSS_COMPARAR"]:
        assert c[nombre] in g, nombre
        assert c[nombre] in f, nombre
    for h in [g, f]:
        assert h.count("function comparador(o)") == 1
        assert h.count("async function componerCaptura(o)") == 1
        assert h.count("async function fotoTV(w, prop, caja, marco, velo)") == 1
    # build_site.py la escribe una sola vez
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        fuente = fh.read()
    for marca in ["function comparador(o)", "c.createStudy('Compare', false, false,",
                  "async function componerCaptura(o)", "function fotoLW(ch, prop)",
                  "function marcaDeAgua(ctx, xDer, yBase, size)", ".pchip { display:flex;"]:
        assert fuente.count(marca) == 1, marca
    # la frase y el tramo, solo en las fichas
    assert c["JS_FRASE"] in f and "function tramoVisible(" not in g


def test_comparar_de_graficos_sigue_igual(sitio):
    js = _script(_leer(sitio, "graficos.html"))
    # 8 a la vez, 4 tonos y del 5º al 8º punteados; la primera elegida es la
    # serie principal (sin 'principal')
    assert "const PMAX = PALETTE.length * 2;" in js
    assert ("const cmp = comparador({ colores: PALETTE, max: PMAX,\n"
            "    simbolo: k => PRODS[k].slug + SUF[unidad] });") in js
    assert "['asado_de_tira', 'palta', 'huevo_color'].forEach(w => {" in js
    # los links de #comparar de siempre: el alias de #productos en
    # /graficos.html y la redirección de la portada
    assert "if (location.hash === '#productos' || location.hash === '#comparar') return 'productos';" in js
    assert "canasta(?:=.*)?|comparar|productos|" in _leer(sitio, "index.html")
    # la escala porcentual de Lightweight con coma decimal, como Advanced Charts
    assert "localization: { percentageFormatter: fmtPct }," in js


# ---------- el link compartible ----------
def test_link_compartible(sitio):
    js = _script(_leer(sitio, "productos/palta.html"))
    # se escribe al elegir, en el orden de los colores, y se lee al abrir (y
    # si cambia con la página abierta); lo que no es sugerencia ni índice se
    # busca en el catálogo
    assert "(k.length ? '#comparar=' + k.join(',') : ''));" in js
    assert "const m = location.hash.match(/^#comparar=([^&]*)/);" in js
    assert "window.addEventListener('hashchange', leerHash);\n  leerHash();" in js
    assert "pedirCatalogo().then(poner, poner);" in js
    # el datafeed y la franja piden los mismos archivos
    assert "pedir: pedirJSON," in js


# ---------- la escala, la frase y la línea de 0% ----------
def test_escala_frase_y_linea_igual_que_la_inflacion(sitio):
    h = _leer(sitio, "productos/palta.html")
    js = _script(h)
    assert "let s = 'Todas las líneas parten en 0% el ' + fechaTxt(t.t0);" in js
    assert "const EN_UNIDAD = { real: 'ajustado por inflación', epoca: 'a precio de la época' };" in js
    assert "const IGUAL = 'Igual que la inflación';" in js
    # Advanced Charts: un dibujo horizontal en el 0%, solo ajustado por
    # inflación; Lightweight: una línea constante, que en porcentaje queda en 0%
    assert "if (widget) lineaTV(u === 'real' ? t.base : null, t.t0);" in js
    assert "shape: 'horizontal_line'" in js
    assert "if (hay && u === 'real') {" in js
    assert "lwRef.setData(lwSemanas.map(p => p.value == null ? { time: p.time } : { time: p.time, value: 1 }));" in js
    # la escala y la frase siguen al tramo a la vista en los dos motores
    assert "c.onVisibleRangeChanged().subscribe(null, programarFrase);" in js
    assert "chart.timeScale().subscribeVisibleTimeRangeChange(programarFrase);" in js
    # Lightweight dibuja cada comparada en las semanas de la ficha
    assert "barrasDe(k, uu).then(b => enSemanasDe(b, lwSemanas))" in js
    # las cifras con las clases de color de siempre
    assert ".v-sube { color:var(--sube); }" in h and ".v-baja { color:var(--baja); }" in h


# ---------- la captura PNG ----------
def test_captura_con_las_lineas_la_leyenda_y_la_frase(sitio):
    js = _script(_leer(sitio, "productos/palta.html"))
    cap = js[js.index("async function capturar()"):js.index("$('shot').onclick")]
    assert "o.lineas = [{ texto: NOMBRE, color: tok('bone'), punteada: false }]" in cap
    assert "o.frase = (ultimaFrase || []).filter(x => !x.muestra);" in cap
    assert "o.precio = ONOTE[u];" in cap
    assert "await componerCaptura(o);" in cap
    # Advanced Charts: la captura del cliente, con el tramo de la pantalla
    assert "fotoTV(w, prop, el, $('marco')" in cap
    assert not re.search(r"\bw\.takeScreenshot\(", js)
    tv = js[js.index("async function fotoTV("):js.index("async function componerCaptura(o)")]
    assert tv.count("TV.capturaCliente(w, tok, caja)") == 2
    assert "const c = w.activeChart(), tramo = c.getVisibleRange();" in tv
    # sin comparados: el producto y su precio de esta semana
    h = _leer(sitio, "productos/palta.html")
    captura = json.loads(re.search(r"CAPTURA = (\{.*?\});\n", js).group(1))
    precio = re.search(r'<div class="oprice">([^<]+)</div>', h).group(1)
    assert captura == {"titulo": "PALTA POR KILO", "precio": precio, "chico": False}


def test_ficha_sin_precio_esta_semana(sitio):
    js = _script(_leer(sitio, "productos/viejo.html"))
    captura = json.loads(re.search(r"CAPTURA = (\{.*?\});\n", js).group(1))
    assert captura["chico"] and captura["precio"].startswith("Sin precio de ODEPA esta semana. Último dato: $")
    # la frase dice "Del ... al ...": su última semana no es esta
    assert "const FECHA = '" in js and "AL_DIA = false" in js
    assert "AL_DIA = true" in _script(_leer(sitio, "productos/palta.html"))


# ---------- en Node ----------
def test_componente_y_frase_en_node(tmp_path):
    if not NODE:
        pytest.skip("sin Node.js")
    c = _constantes()
    archivo = tmp_path / "js.json"
    archivo.write_text(json.dumps({"comparar": c["JS_COMPARAR"], "frase": c["JS_FRASE"]}),
                       encoding="utf-8")
    r = subprocess.run([NODE, os.path.join(RAIZ, "tests", "comparar_node.js"), str(archivo)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "chequeos OK" in r.stdout

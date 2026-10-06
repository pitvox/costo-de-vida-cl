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
import hashlib
import json
import math
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


def _ficha(d, slug):
    """El JS de una ficha: sus datos, inline, y el JS común de las fichas
    (carestia-ficha.js)."""
    return _script(_leer(d, f"productos/{slug}.html")) + _leer(d, "carestia-ficha.js")


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
    return re.findall(r'data-cmp="([^"]+)" (?:data-medida="[^"]+" )?aria-pressed="false">'
                      r'<span class="dot"></span>([^<]+)</button>', franja)


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
    # aparte, las que no tienen precio reciente
    assert '<p class="cmp-sin" id="cmp-sin" hidden></p>' in franja
    # bajo el gráfico y su fecha, antes de los otros productos del grupo
    assert (h.index('<div id="grafico">') < h.index('<div class="fecha">') <
            h.index('<section class="comparar"') < h.index('<section class="otros"'))
    # la captura PNG, junto a la unidad, y el velo mientras se prepara
    assert '<button class="vbtn nomtoggle" id="shot" type="button">captura PNG</button>' in h
    assert '<div class="velo" id="velo" role="status" hidden>Preparando la captura...</div>' in h


def test_max_cuatro_ademas_del_producto(sitio):
    js = _ficha(sitio, "palta")
    assert ("const cmp = comparador({ colores: [1, 2, 3, 4].map(i => tok('cmp' + i)), max: 4,\n"
            "    simbolo: k => k + SUF[unidad], principal: () => SLUG + SUF[unidad] });") in js


# ---------- el mismo componente en las dos páginas ----------
def test_comparar_y_la_ficha_son_el_mismo_componente(sitio):
    c = _constantes()
    g = _leer(sitio, "graficos.html")
    f = _leer(sitio, "productos/palta.html") + _leer(sitio, "carestia-ficha.js")
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
    assert c["JS_FRASE"] in f and "function tramoComun(" not in g


# ---------- el peso: cada ficha lleva sus datos; el JS, común y en caché ----------
def test_ficha_con_sus_datos_y_el_js_comun(sitio):
    ver = None
    for slug in ["palta", "sube", "viejo", "tomate"]:
        h = _leer(sitio, f"productos/{slug}.html")
        # inline, solo los datos de la ficha: ninguna función
        datos = _script(h)
        assert "function" not in datos and "=>" not in datos, slug
        assert re.findall(r"^  const (\w+)", datos, re.M) == [
            "T0", "V", "MIN", "MAX", "REP", "SLUG", "NOMBRE", "UNIDAD", "VER", "FECHA"], slug
        # el JS común, después de los datos, con su versión en la URL; async:
        # no espera a otros scripts (el de Cloudflare, en el <head>)
        m = re.search(r'<script async src="/carestia-ficha\.js\?v=([0-9a-f]{10})"></script>\n</body>', h)
        assert m and h.index(datos) < m.start(), slug
        assert ver in (None, m.group(1)), slug
        ver = m.group(1)
        # las sugerencias van en el HTML; el catálogo, a demanda
        assert "catalogo" not in h and "ultimas_52" not in h, slug
    js = _leer(sitio, "carestia-ficha.js")
    assert hashlib.sha1(js.encode("utf-8")).hexdigest()[:10] == ver
    # nada de una ficha en particular ni marcadores sin reemplazar
    assert not re.search(r"__[A-Z_]+__", js)
    for nombre in ["T0", "V", "MIN", "MAX", "REP", "SLUG", "NOMBRE", "UNIDAD", "VER", "FECHA"]:
        assert not re.search(rf"^  const {nombre} =", js, re.M), nombre
    # el buscador pide el catálogo al usarlo, con la versión de datos/; el
    # datafeed conoce las sugerencias (su unidad de medida va en el botón) y
    # no lo pide para compararlas
    assert "catalogo = pedirJSON('catalogo.json').then(c => {" in js
    h = _leer(sitio, "productos/palta.html")
    assert '<button class="pchip" type="button" data-cmp="baja" data-medida="kg" aria-pressed="false">' in h
    assert '<button class="pchip" type="button" data-cmp="asado" aria-pressed="false">' in h
    assert ".concat([...chips.querySelectorAll('[data-medida]')]" in js
    tv = _leer(sitio, "carestia-tv.js")
    assert "const listo = () => catalogo || (catalogo = pedir('catalogo.json').then(cat => {" in tv
    assert "busca.addEventListener('focus', () => pedirCatalogo().catch(() => {}));" in js


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
    js = _ficha(sitio, "palta")
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
    js = _ficha(sitio, "palta")
    assert "let s = 'Todas las líneas parten en 0% el ' + fechaTxt(e.t0);" in js
    assert "const EN_UNIDAD = { real: 'ajustado por inflación', epoca: 'a precio de la época' };" in js
    assert "const IGUAL = 'Igual que la inflación';" in js
    # Advanced Charts: un dibujo horizontal en el 0% de la escala (lo que
    # dibuja el gráfico), solo ajustado por inflación; Lightweight: una línea
    # constante, que en porcentaje queda en 0%
    assert "if (widget) lineaTV(e && u === 'real' ? e.base : null, e && e.t0);" in js
    assert "e = escalaVisible(barras[0], barras.slice(1), rango[0], rango[1], res);" in js
    # la frase, solo con las semanas de precio propio de cada serie
    assert "Promise.all(todas.map(k => propiasDe(k, u).catch(() => null)))" in js
    # un solo período para todas: desde el 0% del gráfico hasta lo que
    # muestra (a lo más, el último dato de la ficha)
    assert "t = tramoComun(propias, e.t0, Math.min(e.fin, FIN), AL_DIA && e.fin >= FIN);" in js
    assert "const FIN = Date.parse(T0 + 'T00:00:00Z') + (V.length - 1) * SEMANA;" in js
    # las que no tienen precio reciente, en la nota aparte
    assert "ultimaNota = t ? notaTramo(t, series.map(s => s.nombre)) : '';" in js
    # el tramo se conserva al cambiar lo elegido o la unidad y, al agregar una
    # serie que parte después, parte en su primer precio
    assert "if (widget) cmp.tv(widget).then(() => { programarFrase(); ponerTramoPedido(); });" in js
    assert "pedirTramo(ks.filter(k => antes.indexOf(k) === -1));" in js
    assert "if (u !== unidad && cmp.claves().length) pedirTramo([]);" in js
    assert "if (widget && TV.rangoListo) await TV.rangoListo(widget);" in js
    assert "const ini = Math.max(...primeros.filter(x => x != null && x <= FIN));" in js
    assert "if (r && Math.abs(r[0] - desde) > SEMANA / 2) await ponerTramo(desde, hasta);" in js
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
    js = _ficha(sitio, "palta")
    cap = js[js.index("async function capturar()"):js.index("$('shot').onclick")]
    assert "o.lineas = [{ texto: NOMBRE, color: tok('bone'), punteada: false }]" in cap
    assert "o.frase = (ultimaFrase || []).filter(x => !x.muestra);" in cap
    # la nota de las que no tienen precio reciente, en su propia línea y en gris
    assert ("if (ultimaNota) o.frase = o.frase.concat(o.frase.length ? [{ salto: true }] : [],\n"
            "        [{ texto: ultimaNota, clase: 'nota' }]);") in cap
    assert "const COLOR_CIFRA = { 'v-sube': tok('sube'), 'v-baja': tok('baja'), nota: tok('ash') };" in js
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
    js = _ficha(sitio, "viejo")
    captura = json.loads(re.search(r"CAPTURA = (\{.*?\});\n", js).group(1))
    assert captura["chico"] and captura["precio"].startswith("Sin precio de ODEPA esta semana. Último dato: $")
    # la frase dice "Del ... al ...": su última semana no es esta
    assert "const FECHA = '" in js and "AL_DIA = false" in js
    assert "AL_DIA = true" in _ficha(sitio, "palta")


# ---------- la frase: solo precios propios ----------
def test_plazo_del_ultimo_dato_es_el_de_las_fichas():
    """La frase dice "hasta la semana del ..." pasado el mismo plazo con que
    una ficha sin precio esta semana deja de llevar la frase de temporada."""
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        fuente = fh.read()
    plazo = int(re.search(r"^SEMANAS_FRASE_ULTIMO = (\d+)$", fuente, re.M).group(1))
    assert f"const SEMANAS_ULTIMO = {plazo};" in _constantes()["JS_FRASE"]


def _funciones(*nombres) -> dict:
    """Funciones y constantes de build_site.py sin importarlo (construye el
    sitio al importarse): su código, tal cual."""
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    nodos = [n for n in arbol.body if (isinstance(n, ast.FunctionDef) and n.name in nombres) or
             (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and
              n.targets[0].id in ("SEMANAS_ARRASTRE", "TOLERANCIA_NOMINAL"))]
    espacio = {"datetime": datetime}
    exec(compile(ast.Module(body=nodos, type_ignores=[]), "build_site.py", "exec"), espacio)
    return espacio


def _repetida(ini, nominales, factor, rango=None):
    """Un producto como lo escribe indices.py: el nominal de cada semana
    (None sin dato) llevado a pesos de hoy con el factor de su mes y
    redondeado; el rango, solo en las semanas de 'rango'."""
    t0 = datetime.date.fromisoformat(ini)
    meses = [(t0 + datetime.timedelta(weeks=i)).strftime("%Y-%m") for i in range(len(nominales))]
    v = [None if n is None else int(round(n / factor[m])) for n, m in zip(nominales, meses)]
    p = {"t0": ini, "v": v}
    if rango is not None:
        p["min"] = [x - 50 if x is not None and i in rango else None for i, x in enumerate(v)]
        p["max"] = [x + 50 if x is not None and i in rango else None for i, x in enumerate(v)]
    return p


def test_semanas_repetidas():
    """Las semanas que indices.py completó repitiendo el precio nominal de la
    anterior (ffill de hasta 4): sin rango y con el mismo nominal, también
    entre dos meses con distinto IPC; nunca una semana con rango, ni una
    quinta seguida."""
    f = _funciones("semanas_repetidas")
    rep, factor = f["semanas_repetidas"], {"2026-01": 0.97, "2026-02": 0.98, "2026-03": 0.99}
    # 05-01 a 23-03: propias con rango; la 1, la 2 (cambia de mes en la 4)
    # y la 4 a la 6 repiten el nominal de la anterior y no tienen rango
    nom = [1000, 1000, 1000, 1210, 1210, 1210, 1210, 1300, 1300, 1300, 1300, 1300]
    p = _repetida("2026-01-05", nom, factor, rango={0, 3, 7})
    assert rep(p, factor) == [1, 2, 4, 5, 6, 8, 9, 10, 11]
    # el ajustado cambia al pasar a febrero aunque el nominal se repita
    assert p["v"][3] != p["v"][4]
    # una semana con rango nunca es repetida, aunque tenga el mismo precio
    con = _repetida("2026-01-05", [1000, 1000, 1000], factor, rango={0, 1, 2})
    assert rep(con, factor) == []
    # a lo más 4 seguidas (el tope del ffill): la quinta es un precio propio
    largo = _repetida("2026-01-05", [800] * 7, factor, rango={0})
    assert rep(largo, factor) == [1, 2, 3, 4, 6]
    # otro precio nominal (más de un peso de diferencia) es una semana propia
    distinto = _repetida("2026-01-26", [1000, 1002], factor, rango={0})
    assert rep(distinto, factor) == []
    # antes de 2013 ODEPA casi no trae rango: sin rango en el archivo, el precio decide
    viejo = _repetida("2026-01-05", [500, 510, 510, None, 520], factor)
    assert rep(viejo, factor) == [2]


def test_repetidas_publicadas_y_en_la_ficha(sitio):
    """datos/repetidas/{slug}.json por cada producto (su serie en
    datos/productos/ sigue siendo la de indices.json, tal cual) y la de la
    ficha, inline."""
    for slug in ["palta", "sube", "viejo", "tomate"]:
        archivo = json.loads(_leer(sitio, f"datos/repetidas/{slug}.json"))
        assert isinstance(archivo, list) and all(isinstance(i, int) for i in archivo)
        js = _ficha(sitio, slug)
        assert json.loads(re.search(r"const REP = (\[.*?\]);", js).group(1)) == archivo
    js = _ficha(sitio, "palta")
    assert "propio ? REP : pedirJSON('repetidas/' + k + '.json')" in js
    assert "if (e && propias.every(Boolean)) {" in js


@pytest.mark.skipif(not os.environ.get("CARESTIA_INDICES_REAL"),
                    reason="sin CARESTIA_INDICES_REAL (indices.json real de carestia.cl)")
def test_semanas_repetidas_con_datos_reales():
    """Con los datos de carestia.cl: desde 2013, casi todas las semanas sin
    rango son repetidas (las que no, semanas propias sin rango) y ninguna
    con rango lo es; las rachas no pasan de 4."""
    with open(os.environ["CARESTIA_INDICES_REAL"], encoding="utf-8") as fh:
        data = json.load(fh)
    f = _funciones("semanas_repetidas")
    nom, real = {}, {}
    for d in data["indices"].values():
        n = {p["time"]: p["value"] for p in d["nominal"]}
        for p in d["real"]:
            if p["time"] in n:
                m = p["time"][:7]
                nom[m] = nom.get(m, 0) + n[p["time"]]
                real[m] = real.get(m, 0) + p["value"]
    factor = {m: nom[m] / r for m, r in real.items() if r}
    sin_rango = repetidas = con_rango_rep = 0
    for p in data["productos"].values():
        rep = set(f["semanas_repetidas"](p, factor))
        t0 = datetime.date.fromisoformat(p["t0"])
        lo, hi = p.get("min") or [], p.get("max") or []
        for i, x in enumerate(p["v"]):
            if x is None or (t0 + datetime.timedelta(weeks=i)).year < 2013 or len(lo) != len(p["v"]):
                continue
            if lo[i] is None and hi[i] is None:
                sin_rango += 1
                repetidas += i in rep
            else:
                con_rango_rep += i in rep
        racha = 0
        for i in range(len(p["v"])):
            racha = racha + 1 if i in rep else 0
            assert racha <= 4
    assert con_rango_rep == 0
    assert repetidas >= 0.98 * sin_rango, (repetidas, sin_rango)


# ---------- el tercer color ----------
_MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}


def _lineal(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def _oklab(rgb):
    r, g, b = rgb
    lms = [0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
           0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b]
    l, m, s = [math.copysign(abs(x) ** (1 / 3), x) for x in lms]
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _distancia(a, b, vision="normal"):
    """OKLab x100 entre dos colores, con daltonismo simulado (Machado 2009,
    severidad 1)."""
    def ver(h):
        rgb = _lineal(h)
        if vision != "normal":
            rgb = [min(1, max(0, sum(f * x for f, x in zip(fila, rgb)))) for fila in _MACHADO[vision]]
        return _oklab(rgb)
    return 100 * math.dist(ver(a), ver(b))


def _contraste(a, b):
    lum = lambda h: sum(k * x for k, x in zip((0.2126, 0.7152, 0.0722), _lineal(h)))
    x, y = sorted([lum(a), lum(b)])
    return (y + 0.05) / (x + 0.05)


def test_tercer_color_distinto_del_hueso_y_de_los_otros():
    """--cmp3 (mostaza): lejos del hueso de la ficha y de los otros tres con
    visión normal y con protanopía y deuteranopía simuladas (18 o más; con
    tritanopía, 8 o más), legible sobre el fondo y el panel, y fuera de los
    azules, verdes, naranjos y rojos (tono OKLCH de los amarillos)."""
    base = _constantes()["CSS_BASE"]
    t = dict(re.findall(r"--([a-z0-9]+):(#[0-9a-f]{6})", base))
    cmp3 = t["cmp3"]
    assert cmp3 == "#9d8519"
    for otro in ["bone", "cmp1", "cmp2", "cmp4"]:
        for vision in ["normal", "protan", "deutan"]:
            assert _distancia(cmp3, t[otro], vision) >= (28 if otro == "bone" else 18), (otro, vision)
        assert _distancia(cmp3, t[otro], "tritan") >= 8, otro
    assert _contraste(cmp3, t["bg"]) >= 4.5 and _contraste(cmp3, t["panel"]) >= 4.5
    _L, a, b = _oklab(_lineal(cmp3))
    assert 85 <= math.degrees(math.atan2(b, a)) % 360 <= 100


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

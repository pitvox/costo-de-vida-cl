"""Guardia de texto del sitio: sin rayas (— y –), sin " · " entre frases, sin
" vs " y sin muletillas de texto generado. Sin red: el build corre en un
directorio temporal con un indices.json sintético.

Revisa (1) textos/*.md, (2) los strings de build_site.py que terminan en el
sitio (vía AST; docstrings y print de consola quedan fuera) y (3) todo el HTML
del build sintético. Un "·" solo, sin espacios alrededor, se permite: es el
marcador de dato faltante."""
import ast
import datetime
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from indices import BASKETS  # noqa: E402

PROHIBIDOS = [
    ("raya larga", re.compile("—")),
    ("raya media", re.compile("–")),
    ('" · " entre frases', re.compile(r"(?:\s|&nbsp;| )·|·(?:\s|&nbsp;| )")),
    ('" vs "', re.compile(r"\bvs\b", re.I)),
    ("inédit", re.compile("inédit", re.I)),
    ("al descuento", re.compile("al descuento", re.I)),
    ("sin precedentes", re.compile("sin precedentes", re.I)),
]


def infracciones(texto: str) -> list:
    return [(nombre, m.group(0)) for nombre, rx in PROHIBIDOS
            for m in rx.finditer(texto)]


# ---------- 1. textos/*.md ----------
@pytest.mark.parametrize("ruta", sorted(glob.glob(os.path.join(RAIZ, "textos", "*.md"))))
def test_textos_md_sin_rayas_ni_muletillas(ruta):
    with open(ruta, encoding="utf-8") as fh:
        assert infracciones(fh.read()) == []


# ---------- 2. strings de build_site.py que llegan al sitio ----------
def _strings_del_sitio(archivo: str = "build_site.py") -> list:
    with open(os.path.join(RAIZ, archivo), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    fuera = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and nodo.body:
            primero = nodo.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                fuera.add(id(primero.value))                 # docstring
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "print"):
            fuera.update(id(n) for n in ast.walk(nodo))      # consola
    return [(n.lineno, n.value) for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in fuera]


@pytest.mark.parametrize("archivo", ["build_site.py", "tarjetas.py"])
def test_strings_de_build_site_sin_rayas_ni_muletillas(archivo):
    # tarjetas.py dibuja las og:image: su texto también llega al sitio
    malos = [(lin, inf) for lin, s in _strings_del_sitio(archivo)
             for inf in infracciones(s)]
    assert malos == []


def test_la_guardia_detecta_lo_prohibido():
    for texto in ["a — b", "a – b", "uno · dos", "uno&nbsp;· dos", "x vs y",
                  "algo inédito", "Al descuento", "sin precedentes"]:
        assert infracciones(texto), texto
    for texto in ["dato faltante '·'", "+14% sobre su promedio", "vs_promedio",
                  "33 a 66"]:
        assert infracciones(texto) == [], texto


# ---------- 3. HTML del build sintético ----------
def _semanas(fin: datetime.date, n: int) -> list:
    return [(fin - datetime.timedelta(weeks=n - 1 - i)).isoformat() for i in range(n)]


def indices_sintetico() -> dict:
    fin = datetime.date(2026, 9, 21)
    # sin el veredicto por temporada (como un indices.json anterior a ese
    # cambio: build_site lo calcula) y con el mes del último IPC
    out = {"generado": "2026-09-26", "ipc_mes": "2026-08", "indices": {}, "productos": {},
           "descartes": []}
    costos = {"asado": 52000, "ensalada": 8000, "fruta": 12000, "desayuno": 15000}
    colores = {"BARATO": "#5bbf7a", "NORMAL": "#e0a83c", "CARO": "#e0552f"}
    for k, (code, meta) in enumerate(BASKETS.items()):
        n = 300
        fechas = _semanas(fin, n)
        c = costos[code]
        real = [{"time": t, "value": round(c * (0.8 + 0.2 * ((i + 5 * k) % 40) / 40))}
                for i, t in enumerate(fechas)]
        real[-1]["value"] = c
        velas = [{"time": p["time"], "open": p["value"], "high": p["value"] + 300,
                  "low": p["value"] - 300, "close": p["value"]} for p in real[-40:]]
        ver = ["NORMAL", "CARO", "BARATO", "NORMAL"][k]
        out["indices"][code] = {
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
            "fecha": "21-09-2026", "costo_nominal": c, "costo_real": c,
            "percentil": 50 + k * 10, "zscore": 0.1, "vs_promedio": [14, 6, -5, 0][k],
            "veredicto": ver, "color": colores[ver], "n": n,
            "componentes": [{"label": lab, "qty": qty, "unidad": uni,
                             "odepa_unit": "$/kg", "factor": 1.0, "mismatch": False,
                             "precio_ult": c // 6, "aporte": c // 6}
                            for (lab, _m, qty, uni) in meta["items"]],
            "estacionalidad": {"factores": {str(m): 1 + 0.03 * ((m * 5) % 7 - 3)
                                            for m in range(1, 13)},
                               "mes_barato": 12, "mes_caro": 6, "amplitud": 3},
            "velas": velas, "nominal": real, "real": real,
        }
    grupos = ["Carne de Cerdo - Ave - Cordero", "Lácteos - Huevos - Margarinas",
              "Frutas", "Otros"]
    for i in range(24):
        n = 60
        out["productos"][f"prod_{i:03d}"] = {
            "label": f"Producto {i}", "unidad": ["kg", "un", "l"][i % 3],
            "grupo": grupos[i % 4], "t0": _semanas(fin, n)[0],
            "v": [1000 + 10 * j + 50 * (i % 5) for j in range(n)]}
    out["productos"]["viejo"] = {
        "label": "Chirimoya", "unidad": "kg", "grupo": "Frutas",
        "t0": "2024-01-01", "v": [2500] * 10}
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    """Corre build_site.py en un directorio aislado: solo indices.json y
    textos/ (sin README.md: /metodologia.html no lo lee)."""
    d = tmp_path_factory.mktemp("build")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(indices_sintetico()), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0",
               CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


def _leer(sitio, ruta):
    with open(os.path.join(sitio, ruta), encoding="utf-8") as fh:
        return fh.read()


def _paginas(sitio):
    return sorted(glob.glob(os.path.join(sitio, "*.html")) +
                  glob.glob(os.path.join(sitio, "productos", "*.html")))


def test_html_del_build_sin_rayas_ni_muletillas(sitio):
    paginas = _paginas(sitio)
    assert len(paginas) > 25
    malos = [(os.path.relpath(p, sitio), inf) for p in paginas
             for inf in infracciones(_leer(sitio, p))]
    assert malos == []


def test_portada_textos(sitio):
    h = _leer(sitio, "index.html")
    for esperado in [
        "<title>Carestía: índices del costo de vida en Santiago</title>",
        'content="Carestía: índices del costo de vida en Santiago"',
        "Índices del costo de vida en la Región Metropolitana: asado, desayuno,",
        "Cuánto cuesta la vida cotidiana en la Región Metropolitana, ajustado por inflación, "
        "en pesos de agosto de 2026.",
        "asado, desayuno, ensalada y fruta, ajustados por inflación, en pesos de agosto de 2026,",
        "Índices del costo de vida en Chile</div>",
        "Se actualiza los viernes.",
        ">Índices Carestía</h2>",
        "Canastas fijas, ajustadas por inflación, en pesos de agosto de 2026. El color compara "
        "el precio de esta semana con el mismo mes de los últimos 10 años.",
        "en su historia</span>",
        "+14% sobre su promedio",       # vs_promedio positivo
        "-5% bajo su promedio",         # y negativo: "bajo", nunca "vs"
        ">Esta semana</h2>",
        "<h3>Más subieron</h3>", "<h3>Más bajaron</h3>",
        "<h3>Más caros respecto de su historia</h3>",
        "Frente al promedio de las 4 semanas anteriores",
        ">API pública (uso no comercial)</a>",
        ">Prensa</a>",
        ">Productos</h2>",
        "Precios al consumidor ODEPA, Región Metropolitana, ajustados por inflación, en pesos "
        "de agosto de 2026.",
        "Percentil en su historia",
        ">Ver todos los productos</a>",
        "© 2026 Carestía SpA, ",
        "TradingView Lightweight Charts™. Copyright (c) 2023 TradingView, Inc.",
        "Fuente: precios al consumidor de ODEPA",
        "licencia CC-BY), deflactados con el IPC.",
    ]:
        assert esperado in h, esperado
    # el deslinde va solo en metodología (ver test_deslinde_solo_en_metodologia)
    assert "No constituye asesoría" not in h
    # los productos primero: Esta semana, la tabla y después los índices
    assert h.index('id="h-semana"') < h.index('id="h-productos"') < h.index('id="h-indices"')
    # "pesos de hoy" ya no se dice: ajustado por inflación, en pesos del mes del IPC
    assert "pesos de hoy" not in h
    # los textos de ejemplo de la referencia no llegan al sitio
    for ejemplo in ["Cifras de ejemplo", "Los 125 productos", "Ver los 125 productos",
                    ".dc.html"]:
        assert ejemplo not in h, ejemplo


def test_graficos_textos(sitio):
    h = _leer(sitio, "graficos.html")
    for esperado in [
        "<title>Gráficos de los índices del costo de vida en Santiago | Carestía</title>",
        "Índices del costo de vida en Chile</div>",
        "Se actualiza los viernes.",
        # bajo el selector de unidad, la línea de la unidad elegida (la de
        # ajustado por inflación ya en el HTML; las dos en el JS)
        '<p class="utxt" id="utxt">Cada precio pasado, llevado a pesos de agosto de 2026 con '
        'el IPC. Sirve para comparar años distintos.</p>',
        # la leyenda de la línea del índice, con las dos opciones (en el
        # escritorio y en la franja del celular)
        '<span data-leyenda="real"><span class="sw"></span>Ajustado por inflación</span>',
        '<span class="mleg m-ind" data-leyenda="epoca" style="opacity:.35"><span class="sw">'
        '</span>Precio de la época</span>',
        "Lo que costaba en su momento, tal como salía en la boleta.",
        ">Ajustado por inflación</button>", ">Precio de la época</button>",
        # el tooltip del respaldo: etiqueta corta
        '<small id="tt-u">pesos de agosto 2026</small>',
        "Para acercar, arrastra el eje de los años o el de los precios. "
        "En el celular, usa dos dedos.",
        "Desliza hacia los lados para moverte. Usa dos dedos para acercar.",
        "Velas semanales. La mecha va del precio más bajo al más alto que ODEPA "
        "encontró entre los locales encuestados.",
        "Cambio del precio ajustado por inflación, en porcentaje",
        "ARMA TU CANASTA <span>Y COMPÁRTELA</span>",
        "Esta canasta la armaste tú con datos de ODEPA. No es un índice de Carestía.",
        "COMPONENTES DE LA CANASTA <span>(aporte de cada uno al total)</span>",
        "© 2026 Carestía SpA, ",
        "TradingView Lightweight Charts™. Copyright (c) 2023 TradingView, Inc.",
        "Fuente: precios al consumidor de ODEPA",
        "licencia CC-BY), deflactados con el IPC.",
        "La diferencia entre esos meses es de ",
        "MESES_LARGO[e.mes_barato]",
    ]:
        assert esperado in h, esperado
    # los grupos ODEPA se muestran con su nombre nuevo; las claves no cambian
    assert '"Carne de cerdo, ave y cordero"' in h
    assert "Carne de Cerdo - Ave - Cordero" in h        # la clave en los datos
    # el deslinde va solo en metodología
    assert "No constituye asesoría" not in h
    # ni "pesos de hoy" ni la UF
    assert "pesos de hoy" not in h and "Cada precio dividido por el valor de la UF" not in h
    assert ">UF</button>" not in h


def test_pie_con_la_fuente_en_una_linea(sitio):
    """Pedido del dueño: el pie solo cita la fuente (la licencia CC-BY lo
    pide); cómo se arma cada precio está en metodología."""
    fuente = ('<p class="pie-attr">Fuente: precios al consumidor de ODEPA '
              '(<a href="https://datos.odepa.gob.cl">datos.odepa.gob.cl</a>, licencia '
              'CC-BY), deflactados con el IPC.</p>')
    for pagina in _paginas(sitio):
        assert fuente in _leer(sitio, pagina), pagina
    met = " ".join(_visible(_leer(sitio, "metodologia.html")).split())
    for detalle in ["suele ser menor que el precio de supermercado", "Canastas fijas.",
                    "ferias libres, supermercados y carnicerías"]:
        assert detalle in met, detalle


def test_deslinde_solo_en_metodologia(sitio):
    """Pedido del dueño: el deslinde (no es asesoría de inversión) va una
    sola vez en el sitio, en la sección Deslinde de metodología, con su
    texto palabra por palabra. Ni el pie ni las fichas lo repiten. Los
    términos de uso lo cubren dentro de su cláusula 2, que es texto del
    dueño y no se toca."""
    with open(os.path.join(RAIZ, "textos", "metodologia.md"), encoding="utf-8") as fh:
        md = fh.read()
    deslinde = md.split("## Deslinde", 1)[1].strip().split("\n\n", 1)[0]
    assert deslinde.startswith("Información de consumo con fines informativos. No constituye "
                               "asesoría ni recomendación de inversión.")
    con = []
    for pagina in _paginas(sitio):
        h = _leer(sitio, pagina)
        assert "Información de consumo con fines analíticos" not in h, pagina
        if "No constituye asesoría" in h:
            con.append(os.path.relpath(pagina, sitio))
    assert con == ["metodologia.html"], con
    assert _leer(sitio, "metodologia.html").count("No constituye asesoría") == 1
    plano = lambda t: " ".join(t.split())
    assert plano(deslinde) in plano(_visible(_leer(sitio, "metodologia.html")))


def _visible(h: str) -> str:
    """El texto que se ve: sin <script>, <style> ni etiquetas."""
    h = re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def test_precio_de_la_epoca_reemplaza_a_nominal(sitio):
    """"Precio de la época" reemplaza a "Nominal" en todo el sitio: ni en el
    texto de las páginas ni en los textos que arma el JS."""
    for p in _paginas(sitio):
        assert not re.search(r"nominal", _visible(_leer(sitio, p)), re.I), p
    for p in ["graficos.html", "productos/producto-0.html", "prueba-graficos.html", "carestia-tv.js"]:
        h = _leer(sitio, p)
        for viejo in ["' nominal'", "', nominal'", "+ nominal", "NOMINAL", "'-nominal'"]:
            assert viejo not in h, (p, viejo)


def test_ficha_textos_nuevos(sitio):
    h = _leer(sitio, "productos/producto-0.html")
    for esperado in [
        "Índices del costo de vida en Chile</span>",
        # el número grande es el precio de esta semana, sin etiqueta de ajuste
        '<div class="miga">Precio de esta semana en Santiago</div>',
        '<div class="ouni">por kilo</div>',
        "Serie desde ",
        "Se actualiza los viernes.",
        "Carne de cerdo, ave y cordero",
        # el selector de unidad y su línea
        ">Ajustado por inflación</button>", ">Precio de la época</button>",
        '<p class="utxt" id="utxt">Cada precio pasado, llevado a pesos de agosto de 2026 con '
        'el IPC. Sirve para comparar años distintos.</p>',
    ]:
        assert esperado in h, esperado
    assert "pesos de hoy" not in h
    assert re.search(r"Semana del \d\d-\d\d-\d{4}\. Serie desde \d{4}\. "
                     r"Se actualiza los viernes\.", h)


def test_listado_de_productos(sitio):
    h = _leer(sitio, "productos/index.html")
    assert "Catálogo en pesos de agosto 2026" in h
    assert ("Precios de 24 productos en la Región Metropolitana, ajustados por inflación, en "
            "pesos de agosto de 2026: el promedio") in h
    assert re.search(r"<h2>Frutas <span>\(\d+\)</span></h2>", h)
    assert re.search(r"Sin datos hace más de un año <span>\(1\)</span></h2>", h)
    assert "Carne de cerdo, ave y cordero" in h
    assert "Lácteos, huevos y margarinas" in h
    # las anclas siguen saliendo del nombre original de ODEPA
    assert 'id="carne-de-cerdo-ave-cordero"' in h


def test_metodologia_usa_el_texto_del_dueno_y_las_canastas(sitio):
    h = _leer(sitio, "metodologia.html")
    with open(os.path.join(RAIZ, "textos", "metodologia.md"), encoding="utf-8") as fh:
        md = fh.read()
    assert [t for t in re.findall(r"^## (.+)$", md, re.M)] == \
        ["Cómo se calcula", "Fuentes", "Deslinde"]
    for parrafo in [l for l in md.splitlines() if l.strip() and not l.startswith("##")]:
        sin_negrita = re.sub(r"\*\*(.+?)\*\*", r"\1", parrafo)
        assert sin_negrita in re.sub(r"</?strong>", "", h), parrafo[:40]
    # orden: cómo se calcula, canastas, fuentes, deslinde, notas
    orden = [h.index(f"<h2>{t}</h2>") for t in
             ["Cómo se calcula", "Las canastas", "Fuentes", "Deslinde",
              "Notas metodológicas"]]
    assert orden == sorted(orden)
    # canastas desde BASKETS, en formato "Asado de tira: 1 kg"
    assert "<li>Asado de tira: 1 kg</li>" in h
    assert "<li>Cebolla: 1 unidad</li>" in h
    assert "<li>Leche entera: 1 litro</li>" in h
    assert h.count('<div class="canasta"') == len(BASKETS)
    # ya no se copia el README
    assert "Metodología (resumen)" not in h
    # precio de la época y ajustado por inflación, y caro o barato: los
    # párrafos del dueño
    assert ("<strong>Precio de la época y ajustado por inflación.</strong> El sitio muestra "
            "cada serie de dos formas.") in h
    assert "El número grande de cada ficha es siempre el precio de esta semana." in h
    assert ("<strong>Caro o barato.</strong> Se compara el precio de esta semana, ajustado por "
            "inflación, con el mismo mes de los últimos 10 años, o de todos los disponibles si "
            "son al menos 5.") in h
    assert "El percentil contra toda la historia se sigue mostrando como referencia." in h
    for viejo in ["Nominal y en pesos de hoy", "Pesos de hoy, precio de la época y UF",
                  "Se mide con el percentil histórico", "pesos de hoy"]:
        assert viejo not in md, viejo
    # la nota metodológica del cambio, al final de las notas
    notas = h[h.index("<h2>Notas metodológicas</h2>"):]
    notas = notas[:notas.index("</section>") + len("</section>")]
    assert notas.endswith(
        '<li><strong><span class="nw">05-10-2026</span>.</strong> El veredicto pasa a '
        "compararse con el mismo mes de "
        "los últimos 10 años en vez de con toda la historia, para no confundir la temporada "
        "con un alza ni marcar casi todo como caro por la tendencia de largo plazo. Los "
        "veredictos publicados antes de esta fecha no son comparables con los nuevos.</li>\n"
        "</ul>\n    </section>")


def test_paginas_del_dueno(sitio):
    assert "Carestía no compara tiendas ni te dice dónde comprar más barato." \
        in _leer(sitio, "acerca.html")
    assert "No es un comparador de precios" not in _leer(sitio, "acerca.html")
    assert "Carestía SpA, RUT" in _leer(sitio, "contacto.html")
    assert "78.521.796-9</span>. Santiago, Chile.</p>" in _leer(sitio, "contacto.html")
    h404 = _leer(sitio, "404.html")
    # el número de productos con datos del último año, calculado en el build
    # (24 sintéticos con datos recientes; la chirimoya es de 2024)
    assert '<a href="/">Volver al inicio</a> o <a href="/productos/">ver los 24 productos</a>.' in h404
    assert "las series de 24 productos de la Región Metropolitana" in _leer(sitio, "acerca.html")
    for p in _paginas(sitio):
        assert not re.search(r"\b125 (productos|alimentos)", _leer(sitio, p)), p

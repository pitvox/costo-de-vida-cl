"""Canastas de ejemplo (/canastas/{slug}.html). Sin red: build_site.py corre
en un directorio temporal con el indices.json sintético de test_texto.py más
los 8 insumos del almuerzo de casino (con las claves de indices.json, el
aceite con menos historia que el resto y el tomate con semanas sin precio) y
dos productos para los casos de la franja: uno de historia corta y uno que
baja.

Verifica que las funciones de Python de la página (serie_canasta,
lineas_canasta, hash_canasta y las que usan) den lo mismo que el JS de Arma
tu canasta de /graficos.html, corrido en Node sobre el mismo build
(tests/canasta_node.js): la misma serie, el mismo percentil, el mismo % y la
misma línea de temporada, también con una canasta truncada y con una de
menos de 30 semanas comparables, y que leerHash lea el link del botón con las
mismas claves y cantidades. Sin Node, esas comparaciones se saltan y quedan
las cuentas hechas a mano. Verifica también la página (orden, cifras, tabla,
botón, cita y Dataset), su tarjeta en hueso, el párrafo de /compras.html, el
sitemap y el workflow, que una canasta con un insumo sin precio en las
últimas 4 semanas no se escriba (y una con uno de hace 2 semanas sí, con su
semana) y la guardia de texto."""
import ast
import datetime
import html
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
from test_texto import indices_sintetico, infracciones  # noqa: E402

NODE = shutil.which("node")
FIN = datetime.date(2026, 9, 21)   # lunes de la semana vigente del sintético
SLUG = "almuerzo-casino"
TITULO = "Almuerzo de casino para 10 personas"
URL = f"https://carestia.cl/canastas/{SLUG}.html"
INSUMOS = [("posta_paleta", 0.8), ("pollo_trutro_entero", 1),
           ("arroz_grano_largo_delgado_grado_2", 0.6), ("papa", 1.5), ("tomate", 0.8),
           ("cebolla", 4), ("aceite_vegetal", 0.2), ("marraqueta", 0.5)]
HASH = ("#canasta=posta_paleta:0.8,pollo_trutro_entero:1,arroz_grano_largo_delgado_grado_2:0.6,"
        "papa:1.5,tomate:0.8,cebolla:4,aceite_vegetal:0.2,marraqueta:0.5")
LINEA = ("Canasta de ejemplo con precios de Santiago, ajustados por inflación. Cámbiale los "
         "insumos y las cantidades en el gráfico. No es un índice de Carestía.")
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

# las canastas que se comparan con el JS
CANASTAS_PRUEBA = [
    INSUMOS,                                    # truncada por el aceite, con temporada
    [("papa", 1), ("corto", 0.5)],              # truncada, con menos de 30 comparables
    [("baja", 2), ("tomate", 0.5)],             # más barata, bajo su promedio
    [("tomate", 1)],                            # sola, con semanas sin precio
    [("aceite_vegetal", 1), ("papa", 0.3)],     # el primero es el que la limita
    [("no_existe", 1), ("papa", 1)],            # una clave que no está queda fuera
]


def _serie(base: int, n: int, ultimo: int, fase: float = 0.0, huecos=()) -> list:
    """n precios semanales con estacionalidad y algo de tendencia, el último
    'ultimo' y sin precio en las posiciones de 'huecos'."""
    v = [round(base * (1 + 0.08 * math.sin(2 * math.pi * i / 52 + fase) + 0.0004 * i))
         for i in range(n)]
    v[-1] = ultimo
    for i in huecos:
        v[i] = None
    return v


def _producto(label: str, unidad: str, grupo: str, v: list, atraso: int = 0) -> dict:
    """Una serie semanal 'v' que termina 'atraso' semanas antes de FIN."""
    fin = FIN - datetime.timedelta(weeks=atraso)
    return {"label": label, "unidad": unidad, "grupo": grupo,
            "t0": (fin - datetime.timedelta(weeks=len(v) - 1)).isoformat(), "v": v}


def sintetico(atraso_tomate: int = 0, sin_marraqueta: bool = False) -> dict:
    """El sintético de test_texto.py con los insumos de la canasta. La última
    semana suma 20.320,5 pesos: Math.round da 20.321 y el round() de Python,
    20.320."""
    out = indices_sintetico()
    p = out["productos"]
    p["posta_paleta"] = _producto("Posta Paleta", "kg", "Carne bovina", _serie(11000, 260, 11580, 0.3))
    p["pollo_trutro_entero"] = _producto("Pollo Trutro Entero", "kg", "Carne de Cerdo - Ave - Cordero",
                                         _serie(3400, 260, 3580, 1.1))
    p["arroz_grano_largo_delgado_grado_2"] = _producto(
        "Arroz grano largo delgado grado 2", "kg", "Abarrotes y otros", _serie(1400, 260, 1510, 2.0))
    p["papa"] = _producto("Papa", "kg", "Hortalizas", _serie(1200, 260, 1431, 0.7))
    tomate = _serie(1500, 260, 1695, 2.9, huecos=(100, 101, 102))
    p["tomate"] = _producto("Tomate", "kg", "Hortalizas",
                            tomate[:len(tomate) - atraso_tomate], atraso_tomate)
    p["cebolla"] = _producto("Cebolla", "un", "Hortalizas", _serie(330, 260, 358, 1.7))
    # tres años: la canasta parte con él (2023), con 30 o más comparables
    p["aceite_vegetal"] = _producto("Aceite vegetal", "l", "Abarrotes y otros",
                                    _serie(2400, 156, 2505, 0.9))
    if not sin_marraqueta:
        p["marraqueta"] = _producto("Marraqueta", "kg", "Pan", _serie(2100, 260, 2270, 0.2))
    p["corto"] = _producto("Corto", "kg", "Frutas", _serie(900, 40, 990))
    p["baja"] = _producto("Baja", "kg", "Frutas", _serie(1000, 200, 610))
    return out


def _construir(d, datos: dict, tarjetas: bool = False) -> str:
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    env.pop("CARESTIA_TARJETAS", None)
    if not tarjetas:
        env["CARESTIA_TARJETAS"] = "0"
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


@pytest.fixture(scope="module")
def datos():
    return sintetico()


@pytest.fixture(scope="module")
def sitio(tmp_path_factory, datos):
    # con las tarjetas dibujadas: la de la canasta va en hueso
    d = tmp_path_factory.mktemp("build_canastas")
    _construir(d, datos, tarjetas=True)
    return d


@pytest.fixture(scope="module")
def atrasado(tmp_path_factory):
    """El tomate sin precio hace 4 semanas y sin marraqueta: no se escribe."""
    d = tmp_path_factory.mktemp("build_canastas_atrasado")
    return d, _construir(d, sintetico(atraso_tomate=4, sin_marraqueta=True))


@pytest.fixture(scope="module")
def esa_semana(tmp_path_factory):
    """El tomate con su último precio hace 2 semanas: va, con esa semana."""
    d = tmp_path_factory.mktemp("build_canastas_esa_semana")
    _construir(d, sintetico(atraso_tomate=2))
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _main(h):
    return h[h.index("<main"):h.index("</main>")]


def _f() -> dict:
    """Las funciones de Python de las canastas, de build_site.py sin
    importarlo (construye el sitio al importarse): su código, tal cual."""
    nombres = {"redondeo_js", "fmt_clp_js", "numero_js", "semanas_con_precio", "serie_canasta",
               "semana_iso", "distancia_semanas", "lineas_canasta", "hash_canasta",
               "cantidad_del_link", "nombre"}
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    nodos = [n for n in arbol.body if (isinstance(n, ast.FunctionDef) and n.name in nombres) or
             (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and
              n.targets[0].id == "NOMBRES")]
    espacio = {"datetime": datetime, "math": math}
    exec(compile(ast.Module(body=nodos, type_ignores=[]), "build_site.py", "exec"), espacio)
    return espacio


@pytest.fixture(scope="module")
def f():
    return _f()


def _nombres(f, datos) -> dict:
    return {k: f["nombre"](p["label"]) for k, p in datos["productos"].items()}


# ---------- la cuenta, contra el JS de /graficos.html ----------
def _script(h):
    """El JS inline de /graficos.html (el último <script> sin src)."""
    return re.findall(r"<script>\n(.*?)</script>", h, re.S)[-1]


def _inline(h) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\n", h)
    return json.loads(m.group(1).replace("<\\/", "</"))


def _fechas() -> list:
    d, out = datetime.date(1999, 12, 20), []
    while d <= datetime.date(2040, 12, 31):
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


MAPAS = [[("a", 0.1), ("b", 0.25), ("c", 0.3), ("d", 0.7), ("e", 1), ("f", 1.5), ("g", 2.05),
          ("h", 12), ("i", 0.15), ("j", 0.35), ("k", 4)], INSUMOS]


@pytest.fixture(scope="module")
def js(sitio, tmp_path_factory):
    """Lo que dice el JS de Arma tu canasta (el de la página construida) de
    CANASTAS_PRUEBA, del link del botón y de otros links, de las semanas ISO
    de cada día de 2000 a 2040 y de la distancia entre semanas."""
    if not NODE:
        pytest.skip("sin Node: la cuenta se compara con el JS solo donde hay Node")
    h = _leer(sitio, "graficos.html")
    s = _script(h)
    pagina = _leer(sitio, f"canastas/{SLUG}.html")
    boton = re.search(r'<a href="https://carestia\.cl/graficos\.html(#canasta=[^"]+)">'
                      r'Abrir en el gráfico y cambiarla</a>', pagina).group(1)
    entrada = {
        "datos": s[s.index("  const DIA = 864e5;"):s.index("  Object.keys(DATA.series")],
        "fmt": re.search(r"^  const fmt = v => .*$", s, re.M).group(0),
        "canasta": s[s.index("  /* ---------- vista Tu canasta ---------- */"):
                     s.index("  function buildCanasta()")],
        "prods": _inline(h)["productos"],
        "dir": str(sitio),
        "canastas": CANASTAS_PRUEBA,
        # el del botón, uno que leerHash redondea y otro con claves que no están
        "hashes": [html.unescape(boton), "#canasta=papa:0.25,cebolla:2.6,tomate:0",
                   "#canasta=no_existe:1,papa:2,papa:3"],
        "mapas": MAPAS,
        "fechas": _fechas(),
    }
    archivo = tmp_path_factory.mktemp("canasta_node") / "entrada.json"
    archivo.write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([NODE, os.path.join(RAIZ, "tests", "canasta_node.js"), str(archivo)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_la_cuenta_es_la_del_js(js, datos, f):
    """La misma serie (semana a semana, al último decimal), el mismo
    limitante, el mismo costo, el mismo percentil con su %, la misma línea
    de temporada y el mismo aviso, salvo "tu canasta", que en la página es
    "esta canasta"."""
    nombres = _nombres(f, datos)
    for c, j in zip(CANASTAS_PRUEBA, js["canastas"]):
        r = f["serie_canasta"](c, datos["productos"])
        assert [list(x) for x in r["serie"]] == j["serie"], c
        assert (r["truncada"], r["limitante"]) == (j["truncada"], j["limitante"]), c
        lineas = f["lineas_canasta"](r, nombres)
        assert lineas["costo"] == j["costo"], c
        assert lineas["stats"] == j["stats"], c
        assert lineas["temporada"] == j["temporada"], c
        assert lineas["aviso"] == j["aviso"].replace("tu canasta", "esta canasta"), c
        assert "tu canasta" not in " ".join(lineas.values())


def test_los_casos_son_los_que_dicen(js):
    """Cada canasta de prueba cubre lo que dice: así la comparación con el
    JS no pasa por casos vacíos."""
    almuerzo, corta, baja, sola, primero, falta = js["canastas"]
    assert almuerzo["truncada"] and almuerzo["limitante"] == "aceite_vegetal"
    assert almuerzo["temporada"].startswith("en esta época del año: ")
    assert almuerzo["aviso"] == "tu canasta tiene datos desde 2023 (limitada por Aceite vegetal)"
    # el costo de su última semana suma 20.320,5: Math.round sube
    assert almuerzo["costo"] == "$20.321"
    assert corta["truncada"] and corta["limitante"] == "corto"
    assert corta["temporada"] == "" and len(corta["serie"]) == 40
    assert "% bajo su promedio histórico" in baja["stats"]
    assert "más barata que el" in baja["temporada"]
    assert not sola["truncada"] and sola["aviso"] == ""
    assert len(sola["serie"]) == 257   # 260 semanas menos los 3 huecos
    assert primero["truncada"] and primero["limitante"] == "aceite_vegetal"
    assert falta["serie"] and falta["limitante"] == "papa" and not falta["truncada"]


def test_el_boton_lleva_la_misma_canasta(js, datos):
    """leerHash lee el link del botón con las mismas claves y cantidades, en
    el mismo orden (la cebolla, en unidades), y hashCanasta lo vuelve a
    escribir igual."""
    boton = js["hashes"][0]
    assert boton["leido"] is True
    assert boton["canasta"] == [[k, q] for k, q in INSUMOS]
    assert datos["productos"]["cebolla"]["unidad"] == "un"
    assert ["cebolla", 4] in boton["canasta"]
    assert boton["hash"] == HASH


def test_cantidades_que_el_link_no_lleva_tal_cual(js, f):
    """leerHash redondea a 0,1 (por unidad, a enteros) y cambia lo que no es
    positivo: esas cantidades no pasan cantidad_del_link, la que deja fuera
    una canasta de ejemplo cuyo link no diría lo mismo. Las de la canasta sí
    pasan."""
    leido = js["hashes"][1]["canasta"]
    assert leido == [["papa", 0.3], ["cebolla", 3], ["tomate", 0.5]]
    for q, uni in [(0.25, "kg"), (2.6, "un"), (0, "kg"), (0.05, "l"), (0.5, "un")]:
        assert not f["cantidad_del_link"](q, uni), (q, uni)
    unidades = {k: p["unidad"] for k, p in sintetico()["productos"].items()}
    for k, q in INSUMOS:
        assert f["cantidad_del_link"](q, unidades[k]), k
    # una clave que no está no entra, y una repetida entra una sola vez
    assert js["hashes"][2]["canasta"] == [["papa", 2]]


def test_hash_como_lo_escribe_el_js(js, f):
    for c, j in zip(MAPAS, js["mapas"]):
        assert f["hash_canasta"](c) == j
    assert f["hash_canasta"](INSUMOS) == HASH


def test_semana_iso_y_distancia_como_en_el_js(js, f):
    assert [f["semana_iso"](t) for t in _fechas()] == js["iso"]
    assert [f["distancia_semanas"](a, b) for a in range(1, 54) for b in range(1, 54)] == js["dist"]


def test_cuentas_hechas_a_mano(f):
    """Sin Node: un producto plano con un salto al final, por 1,5. La última
    semana es 1,5 x 1.431 = 2.146,5, que Math.round lleva a 2.147 (round()
    de Python, a 2.146); el promedio es 60.646,5 / 40 = 1.516,16, así que
    está 42% sobre él; percentil 100; solo 6 semanas comparables (sin
    temporada). Con un segundo producto que parte 10 semanas después, la
    canasta queda truncada."""
    t0 = datetime.date(2025, 12, 29)
    prods = {"a": {"label": "Pera", "unidad": "kg", "t0": t0.isoformat(), "v": [1000] * 39 + [1431]},
             "b": {"label": "Cerdo Lomo", "unidad": "kg",
                   "t0": (t0 + datetime.timedelta(weeks=10)).isoformat(), "v": [500] * 30}}
    r = f["serie_canasta"]([("a", 1.5)], prods)
    assert len(r["serie"]) == 40 and r["serie"][-1] == ("2026-09-28", 2146.5)
    assert f["lineas_canasta"](r, {"a": "Pera"}) == {
        "costo": "$2.147",
        "stats": "percentil 100 de 40 semanas de esta canasta (+42% sobre su promedio histórico)",
        "temporada": "", "aviso": ""}
    r = f["serie_canasta"]([("a", 1), ("b", 2)], prods)
    assert r["serie"][0] == ("2026-03-09", 2000.0) and r["truncada"] and r["limitante"] == "b"
    assert f["lineas_canasta"](r, {"a": "Pera", "b": "Lomo de cerdo"})["aviso"] == \
        "esta canasta tiene datos desde 2026 (limitada por Lomo de cerdo)"
    assert f["redondeo_js"](-2.5) == -2 and f["redondeo_js"](2.5) == 3
    assert f["redondeo_js"](0.49999999999999994) == 0
    assert f["numero_js"](4.0) == "4" and f["numero_js"](0.8) == "0.8"


def test_la_definicion_de_la_canasta():
    """La canasta del pedido, tal cual: claves de indices.json, cantidades y
    la frase de /compras.html."""
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    nodo = next(n for n in arbol.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "CANASTAS_EJEMPLO")
    canastas = ast.literal_eval(nodo.value)
    assert canastas[0] == {
        "slug": SLUG, "titulo": TITULO,
        "compras": "Estos insumos juntos, como un almuerzo para 10 personas, semana a semana",
        "insumos": INSUMOS}


# ---------- la página ----------
def test_url_title_y_description(sitio):
    h = _leer(sitio, f"canastas/{SLUG}.html")
    assert f'<link rel="canonical" href="{URL}">' in h
    assert f"<title>{TITULO}: costo semanal en Santiago | Carestía</title>" in h
    desc = (f"{TITULO}: $20.321 la semana del 21 de septiembre de 2026 en Santiago, ajustado por "
            f"inflación. Canasta de ejemplo con precios de ODEPA, semana a semana.")
    assert f'<meta name="description" content="{desc}">' in h
    assert f'<meta property="og:description" content="{desc}">' in h
    # dentro de Arma tu canasta en el menú, sin ser esa página
    assert '<a href="https://carestia.cl/graficos.html#canasta" data-modo="canasta" ' \
           'aria-current="true">Arma tu canasta</a>' in h


def test_la_pagina_en_su_orden(sitio):
    m = _main(_leer(sitio, f"canastas/{SLUG}.html"))
    piezas = [f"<h1>{TITULO}</h1>", f'<p class="intro">{LINEA}</p>',
              '<div class="ind-cifra"><span class="ind-precio">$20.321</span>'
              '<span class="can-sem">semana del 21 de septiembre de 2026</span></div>',
              '<p class="cstats">percentil ', '<p class="cstats ctemporada">en esta época del año: ',
              '<p class="caviso">esta canasta tiene datos desde 2023 (limitada por Aceite vegetal)</p>',
              '<table class="can-tabla"', '<p class="can-nota">Precios al consumidor ODEPA, Región '
              'Metropolitana, ajustados por inflación, en pesos de agosto de 2026.</p>',
              f'<a href="https://carestia.cl/graficos.html{HASH}">Abrir en el gráfico y cambiarla</a>',
              '<p class="cita">Para citar: Carestía (carestia.cl), con datos de ODEPA, semana del 21 '
              'de septiembre de 2026.</p>',
              '<script type="application/ld+json">']
    pos = [m.index(p) for p in piezas]
    assert pos == sorted(pos)


def test_las_lineas_son_las_del_js(sitio, js):
    """Lo que dice la página es lo que dice /graficos.html abierto con el
    link de su botón."""
    m = _main(_leer(sitio, f"canastas/{SLUG}.html"))
    j = js["canastas"][0]
    assert f'<span class="ind-precio">{j["costo"]}</span>' in m
    assert f'<p class="cstats">{html.escape(j["stats"])}</p>' in m
    assert f'<p class="cstats ctemporada">{html.escape(j["temporada"])}</p>' in m
    aviso = j["aviso"].replace("tu canasta", "esta canasta")
    assert f'<p class="caviso">{html.escape(aviso)}</p>' in m


FILA = re.compile(r'<tr><th scope="row"><a href="https://carestia\.cl/productos/([^"]+)\.html">'
                  r'([^<]+)</a></th><td class="can-n can-q">([^<]+)</td>'
                  r'<td class="can-n can-p">(\$[\d.]+) <small>por (\w+)</small></td>'
                  r'<td class="can-n can-a">(\$[\d.]+)</td></tr>')


def test_la_tabla_con_las_cifras_de_cada_ficha(sitio):
    """Cada insumo con link a su ficha y su nombre, su cantidad, su precio de
    esta semana (el número grande de su ficha) y lo que aporta: cantidad por
    precio, con Math.round como el costo (1,5 x 1.431 = 2.146,5 da $2.147)."""
    m = _main(_leer(sitio, f"canastas/{SLUG}.html"))
    assert ('<thead><tr><th scope="col">Insumo</th><th class="can-n" scope="col">Cantidad</th>'
            '<th class="can-n" scope="col">Precio esta semana</th>'
            '<th class="can-n" scope="col">Aporte</th></tr></thead>') in m
    filas = FILA.findall(m)
    assert [(c, u, a) for _s, _n, c, _p, u, a in filas] == [
        ("0,8 kg", "kilo", "$9.264"), ("1 kg", "kilo", "$3.580"), ("0,6 kg", "kilo", "$906"),
        ("1,5 kg", "kilo", "$2.147"), ("0,8 kg", "kilo", "$1.356"),
        ("4 unidades", "unidad", "$1.432"), ("0,2 litros", "litro", "$501"),
        ("0,5 kg", "kilo", "$1.135")]
    for slug, nombre, _c, precio, _u, _a in filas:
        ficha = _leer(sitio, f"productos/{slug}.html")
        assert f"<h1>{nombre}</h1>" in ficha, slug
        assert f'<div class="oprice">{precio}</div>' in ficha, slug
    assert [s for s, *_r in filas] == ["posta-paleta", "pollo-trutro-entero",
                                       "arroz-grano-largo-delgado-grado-2", "papa", "tomate",
                                       "cebolla", "aceite-vegetal", "marraqueta"]


def test_la_cita_y_el_dataset(sitio, datos, f):
    h = _leer(sitio, f"canastas/{SLUG}.html")
    lds = [json.loads(x) for x in LD.findall(h)]
    assert len(lds) == 1
    ld = lds[0]
    titulo = html.unescape(re.search(r"<title>(.*?)</title>", h).group(1))
    assert ld["@type"] == "Dataset"
    assert ld["name"] == titulo.removesuffix(" | Carestía") == f"{TITULO}: costo semanal en Santiago"
    assert ld["url"] == URL
    # la licencia de los términos de uso y la de ODEPA, como en las fichas
    assert ld["license"] == "https://carestia.cl/terminos.html"
    assert ld["isBasedOn"][0]["license"] == "http://www.opendefinition.org/licenses/cc-by"
    assert ld["creditText"] == "Carestía (carestia.cl), con datos de ODEPA"
    assert "distribution" not in ld
    # desde la primera semana de la canasta, abierta
    r = f["serie_canasta"](INSUMOS, datos["productos"])
    assert ld["temporalCoverage"] == f"{r['serie'][0][0]}/.." == "2023-10-02/.."
    assert ld["variableMeasured"] == "Costo semanal de la canasta, en pesos chilenos"
    assert ld["keywords"][0] == TITULO
    assert ld["description"].startswith(
        "Costo semanal de una canasta de ejemplo (almuerzo de casino para 10 personas) en la "
        "Región Metropolitana: serie semanal desde 2023 con datos ODEPA. La canasta lleva posta "
        "paleta (0,8 kg), trutro entero de pollo (1 kg), arroz grano largo delgado grado 2 "
        "(0,6 kg), papa (1,5 kg), tomate (0,8 kg), cebolla (4 unidades), aceite vegetal "
        "(0,2 litros) y marraqueta (0,5 kg). No es un índice de Carestía. ")
    # solo ajustada por inflación, como Arma tu canasta: sin precio de la época
    assert "La serie se publica ajustada por inflación con el IPC del Banco Central de Chile." \
        in ld["description"]
    assert "época" not in ld["description"]
    # las fichas y los índices siguen diciendo lo de antes
    ficha = json.loads(LD.findall(_leer(sitio, "productos/tomate.html"))[0])
    assert "La serie se publica como precio de la época y ajustada por inflación" in ficha["description"]


def test_la_tarjeta_va_en_hueso(sitio):
    """og/canastas/{slug}.png, como la de un producto, con la línea en hueso;
    la de un producto sigue en brasa."""
    from PIL import Image
    h = _leer(sitio, f"canastas/{SLUG}.html")
    og = re.search(r'<meta property="og:image" content="([^"]+)">', h).group(1)
    assert re.fullmatch(rf"https://carestia\.cl/og/canastas/{SLUG}\.png\?v=[0-9a-f]+", og)
    assert '<meta property="og:image:width" content="1200">' in h
    alt = html.unescape(re.search(r'<meta property="og:image:alt" content="([^"]+)">', h).group(1))
    assert alt.startswith(f"{TITULO}: $20.321, semana del 21-09-2026. En esta época del año: más ")
    assert alt.endswith(".") and "tu canasta" not in alt

    def tonos(ruta):
        """Los píxeles del gráfico (la caja GRAFICO de tarjetas.py) cerca del
        hueso y cerca de la brasa."""
        img = Image.open(sitio / ruta).convert("RGB")
        assert img.size == (1200, 630)
        b = img.crop((624, 206, 1137, 487)).tobytes()
        caja = [b[i:i + 3] for i in range(0, len(b), 3)]
        cerca = lambda c, t: sum(abs(x - y) for x, y in zip(c, t)) <= 30  # noqa: E731
        return (sum(1 for c in caja if cerca(c, (0xe4, 0xda, 0xcc))),
                sum(1 for c in caja if cerca(c, (0xe8, 0x74, 0x3b))))
    hueso, brasa = tonos(f"og/canastas/{SLUG}.png")
    assert hueso > 1000 and brasa == 0
    hueso, brasa = tonos("og/productos/tomate.png")
    assert brasa > 1000 and hueso == 0


def test_el_parrafo_de_compras(sitio):
    """Después de la tabla "Esta semana" (y su etiqueta) y antes del texto
    del dueño que sigue, el link a la canasta."""
    h = _leer(sitio, "compras.html")
    p = (f'<p>Estos insumos juntos, como un almuerzo para 10 personas, semana a semana: '
         f'<a href="{URL}">{TITULO}</a>.</p>')
    assert h.count(p) == 1
    assert h.index("</table>") < h.index('<p class="ins-nota">') < h.index(p) < \
        h.index("<h2>Para un área de compras</h2>")
    # el texto del dueño no cambia
    with open(os.path.join(RAIZ, "textos", "compras.md"), encoding="utf-8") as fh:
        assert "almuerzo" not in fh.read()


def test_sitemap_y_workflow(sitio):
    locs = re.findall(r"<loc>([^<]+)</loc>", _leer(sitio, "sitemap.xml"))
    assert locs.count(URL) == 1
    # salud.yml chequea la primera URL con /productos/: sigue siendo una ficha
    assert locs.index(URL) > locs.index(next(l for l in locs if "/productos/" in l))
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        assert "cp -r canastas public/canastas" in fh.read()


def test_sin_precio_reciente_no_se_escribe(atrasado):
    """Un insumo sin precio en las últimas 4 semanas (o sin ficha): la página
    no se escribe y la consola lo avisa, como en /compras.html. Tampoco van
    su link en /compras.html, su URL en el sitemap ni su tarjeta, pero la
    carpeta sí (actualizar.yml la copia)."""
    d, salida = atrasado
    assert ("AVISO canastas/almuerzo-casino.html: no se escribe: tomate (último precio: "
            "24-08-2026), marraqueta (sin ficha)") in salida
    assert not (d / "canastas" / f"{SLUG}.html").exists()
    assert (d / "canastas").is_dir()
    assert "canastas/" not in _leer(d, "compras.html")
    assert URL not in _leer(d, "sitemap.xml")
    assert "0 páginas en canastas/" in salida


def test_con_un_insumo_de_hace_2_semanas_va_con_esa_semana(esa_semana):
    """Con el tomate de hace 2 semanas (dentro de las 4), la canasta termina
    esa semana: el costo, la tabla y la cita son de esa semana y nada dice
    "esta semana"."""
    m = _main(_leer(esa_semana, f"canastas/{SLUG}.html"))
    assert '<span class="can-sem">semana del 7 de septiembre de 2026</span>' in m
    assert '<th class="can-n" scope="col">Precio esa semana</th>' in m
    assert "Precio esta semana" not in m
    assert ('<p class="cita">Para citar: Carestía (carestia.cl), con datos de ODEPA, semana del 7 '
            'de septiembre de 2026.</p>') in m


def test_sin_rayas_ni_muletillas(sitio):
    for ruta in [f"canastas/{SLUG}.html", "compras.html"]:
        h = _leer(sitio, ruta)
        assert infracciones(h) == [], ruta
    # el deslinde va solo en metodología
    assert "No constituye asesoría" not in _leer(sitio, f"canastas/{SLUG}.html")

"""Fichas: el precio de hace diez años, a precio de esa época. Sin red:
build_site.py corre en un directorio temporal con el indices.json sintético
de test_texto.py, con los 4 índices alargados a doce años y el precio de la
época (nominal) en su propia lista, distinto del ajustado por inflación (un
factor por mes que baja hacia atrás, como la inflación). Encima, productos
con precio justo 522 semanas antes (por kilo, por unidad y por litro), sin
precio esa semana pero sí dentro de dos antes o después, sin precio en esa
ventana, con la serie partiendo dentro o fuera de ella, con semanas de la
ventana completadas por el arrastre de indices.py y sin precio esta semana.

Verifica la línea bajo la frase citable: qué semana usa (la de referencia o
la más cercana con precio propio, en empate la anterior: las del arrastre no
cuentan), sus tres cifras (la primera, la del factor mensual del datafeed
para ese mes, calculada aquí aparte y, si hay Node, leída del datafeed del
build en "Precio de la época", con el redondeo de Math.round; la tercera, la
de esta semana), que no va sin precio propio en la ventana, sin factor ese
mes ni sin precio esta semana, que va solo en el HTML de la ficha y la
guardia de texto."""
import ast
import datetime
import glob
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from test_texto import indices_sintetico, infracciones  # noqa: E402

NODE = shutil.which("node")
FIN = datetime.date(2026, 9, 21)            # lunes de la semana vigente del sintético
REF = FIN - datetime.timedelta(weeks=522)   # lunes 19 de septiembre de 2016
SEMANAS_INDICES = 52 * 12                   # los índices: doce años hasta FIN
LARGO = 600                                 # los productos largos parten antes de REF
I_REF = LARGO - 1 - 522                     # la semana de REF en un producto largo
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ARTICULO = {"kg": "el kilo", "un": "la unidad", "l": "el litro"}
# las fichas que llevan la línea: {slug: semanas de REF a la semana que usa}
CON_LINEA = {"marraqueta": 0, "repollo": 0, "leche-entera": 0, "choclo": -1,
             "papa": -1, "betarraga": 1, "zanahoria": -2, "zapallo": 2, "apio": 1,
             "pimiento": 1}
# con precio esta semana y sin la línea
SIN_LINEA = ["pepino", "acelga", "lechuga", "producto-0"]
# las semanas que completó el arrastre de indices.py: {slug: semanas de REF}
ARRASTRE = {"choclo": [0], "pimiento": [-4, -3, -2, -1], "lechuga": [-2, -1, 0, 1]}
LINEA = re.compile(r"Hace diez años, la semana del \d{1,2} de (?:" + "|".join(MESES) +
                   r") de \d{4}, (?:el kilo|la unidad|el litro) costaba \$[\d.]+\. Si solo "
                   r"hubiera subido con la inflación, hoy costaría \$[\d.]+\. Esta semana "
                   r"cuesta \$[\d.]+\.")
# el cierre de cada semana a precio de la época, del datafeed del build
# (carestia-tv.js), como lo pide el gráfico: {slug: {"aaaa-mm-dd": cierre}}
JS_EPOCA = r"""
const fs = require('fs'), path = require('path');
const dir = process.argv[1], slugs = JSON.parse(process.argv[2]);
const leer = r => JSON.parse(fs.readFileSync(path.join(dir, r), 'utf8'));
const TV = require(path.join(dir, 'carestia-tv.js'));
const DATA = leer('indices.json');
const indices = Object.keys(DATA.indices).map(c => ({ codigo: c, nombre: DATA.indices[c].nombre }));
const feed = TV.crearDatafeed({ indices, uf: false,
  pedir: r => Promise.resolve(leer(path.join('datos', r))) });
(async () => {
  const out = {};
  for (const s of slugs) {
    out[s] = {};
    for (const b of (await feed.barras(s + '-epoca')) || []) {
      out[s][new Date(b.time).toISOString().slice(0, 10)] = b.close;
    }
  }
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _k(f: datetime.date) -> float:
    """Pesos de la época por peso ajustado en la semana f: 1 desde agosto de
    2026 (el mes del IPC del sintético) y 0,4% menos por cada mes anterior."""
    return 1.004 ** -max(0, (2026 - f.year) * 12 + 8 - f.month)


def _indices_largos(out: dict, semanas: int) -> None:
    """Los 4 índices con 'semanas' semanas hasta FIN y el nominal en su
    propia lista (en test_texto.py es la misma lista del real)."""
    for k, d in enumerate(out["indices"].values()):
        c = d["costo_real"]
        fechas = [FIN - datetime.timedelta(weeks=semanas - 1 - i) for i in range(semanas)]
        real = [round(c * (0.8 + 0.2 * ((i + 5 * k) % 40) / 40)) for i in range(semanas)]
        real[-1] = c
        d["real"] = [{"time": f.isoformat(), "value": x} for f, x in zip(fechas, real)]
        d["nominal"] = [{"time": f.isoformat(), "value": round(x * _k(f))}
                        for f, x in zip(fechas, real)]
        d["velas"] = [{"time": p["time"], "open": p["value"], "high": p["value"] + 300,
                       "low": p["value"] - 300, "close": p["value"]} for p in d["real"][-40:]]
        d["n"] = semanas


def _producto(label: str, unidad: str, grupo: str, v: list, atraso: int = 0) -> dict:
    """Una serie semanal 'v' que termina 'atraso' semanas antes de FIN."""
    fin = FIN - datetime.timedelta(weeks=atraso)
    return {"label": label, "unidad": unidad, "grupo": grupo,
            "t0": (fin - datetime.timedelta(weeks=len(v) - 1)).isoformat(), "v": v}


def _serie(base: int, huecos=()) -> list:
    """LARGO semanas hasta FIN, cada una con otro precio (base más 3 pesos
    por semana: cada semana de la ventana da otra cifra) y sin precio en las
    semanas 'huecos', contadas desde REF."""
    return [None if j - I_REF in huecos else base + 3 * j for j in range(LARGO)]


def _con_arrastre(label: str, unidad: str, base: int, propia: int, semanas: int,
                  huecos=()) -> dict:
    """Un producto de _serie(base, huecos), con rango (min y max), en que el
    precio de la semana 'propia' (contada desde REF) se repite en las
    'semanas' siguientes como las completa el arrastre de indices.py (ffill
    de hasta 4): sin rango y con el mismo precio nominal, que en otro mes es
    otro ajustado."""
    v = _serie(base, huecos)
    k = I_REF + propia
    arrastre = range(k + 1, k + 1 + semanas)
    nominal = v[k] * _k(REF + datetime.timedelta(weeks=propia))
    for j in arrastre:
        v[j] = round(nominal / _k(REF + datetime.timedelta(weeks=j - I_REF)))
    return {**_producto(label, unidad, "Hortalizas", v),
            "min": [None if x is None or j in arrastre else x - 50 for j, x in enumerate(v)],
            "max": [None if x is None or j in arrastre else x + 50 for j, x in enumerate(v)]}


def sintetico(semanas_indices: int = SEMANAS_INDICES) -> dict:
    out = indices_sintetico()
    _indices_largos(out, semanas_indices)
    p = out["productos"]
    # con precio justo 522 semanas antes: por kilo, por unidad y por litro
    p["marraqueta"] = _producto("Marraqueta", "kg", "Pan", _serie(1500))
    p["repollo"] = _producto("Repollo", "un", "Hortalizas", _serie(600))
    # la leche cuesta esta semana menos de lo que costaría si solo hubiera
    # subido con la inflación (como la real en octubre de 2026) y menos que
    # la semana anterior: la tercera cifra no es la más alta de la serie
    v = _serie(700)
    v[-1] = 900
    p["leche_entera"] = _producto("Leche entera", "l", "Lácteos - Huevos - Margarinas", v)
    # las semanas que completó el arrastre de indices.py no cuentan. Choclo:
    # REF repite el precio de la anterior
    p["choclo"] = _con_arrastre("Choclo", "kg", 1700, -1, 1)
    # pimiento (como el real en octubre de 2026): sin precio en REF y la
    # anterior repite el de cinco semanas antes (de agosto)
    p["pimiento"] = _con_arrastre("Pimiento", "un", 1900, -5, 4, {0})
    # lechuga: de dos semanas antes a una después repiten el de tres antes
    # (de agosto) y dos después no tiene precio: ninguna con precio propio
    p["lechuga"] = _con_arrastre("Lechuga", "un", 2000, -3, 4, {2})
    # sin precio esa semana: la más cercana dentro de dos antes o después y,
    # en empate, la anterior
    p["papa"] = _producto("Papa", "kg", "Hortalizas", _serie(800, {0}))
    p["betarraga"] = _producto("Betarraga", "kg", "Hortalizas", _serie(900, {0, -1}))
    p["zanahoria"] = _producto("Zanahoria", "kg", "Hortalizas", _serie(1000, {0, -1, 1}))
    # la que queda, dos semanas después, ya es de octubre
    p["zapallo"] = _producto("Zapallo", "kg", "Hortalizas", _serie(1100, {0, -1, 1, -2}))
    # sin precio en esa ventana: no va
    p["pepino"] = _producto("Pepino", "kg", "Hortalizas", _serie(1200, {-2, -1, 0, 1, 2}))
    # la serie parte una semana después de REF (va, con esa semana) o tres
    # (no va: ninguna semana de la ventana está en la serie)
    p["apio"] = _producto("Apio", "kg", "Hortalizas", [1300 + 3 * j for j in range(522)])
    p["acelga"] = _producto("Acelga", "kg", "Hortalizas", [1400 + 3 * j for j in range(520)])
    # sin precio esta semana (último dato hace 3 semanas), aunque tenga
    # precio diez años antes
    p["uva"] = _producto("Uva", "kg", "Frutas", _serie(1600), atraso=3)
    return out


def _construir(d, datos: dict) -> None:
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0", CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def datos():
    return sintetico()


@pytest.fixture(scope="module")
def sitio(tmp_path_factory, datos):
    d = tmp_path_factory.mktemp("build_diez")
    _construir(d, datos)
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _slug(label: str) -> str:
    s = unicodedata.normalize("NFKD", label)
    return "-".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def _de(datos: dict, slug: str) -> dict:
    """El producto del sintético con ese slug."""
    return next(p for p in datos["productos"].values() if _slug(p["label"]) == slug)


def _fecha_larga(f: datetime.date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def _clp(x: int) -> str:
    return "$" + f"{x:,}".replace(",", ".")


def _diez(h: str) -> list:
    """Las líneas <p class="diez"> de una página, en texto."""
    return [html.unescape(m) for m in re.findall(r'<p class="diez">(.*?)</p>', h, re.S)]


def _cifras(linea: str) -> list:
    return [int(x.replace(".", "")) for x in re.findall(r"\$([\d.]+)", linea)]


def _factor(datos: dict) -> dict:
    """{"aaaa-mm": factor} calculado aquí aparte, como factorMensual del
    datafeed: el nominal sobre el real de los 4 índices, sumados por mes."""
    nom, real = {}, {}
    for d in datos["indices"].values():
        nominal = {x["time"]: x["value"] for x in d["nominal"]}
        for x in d["real"]:
            m = x["time"][:7]
            nom[m] = nom.get(m, 0) + nominal[x["time"]]
            real[m] = real.get(m, 0) + x["value"]
    return {m: nom[m] / r for m, r in real.items()}


def _precio(p: dict, semana: datetime.date) -> int:
    """El precio ajustado por inflación de p en esa semana."""
    return p["v"][(semana - datetime.date.fromisoformat(p["t0"])).days // 7]


def _esperada(p: dict, semana: datetime.date, factor: dict) -> str:
    """La línea de p con la semana 'semana', armada aquí aparte."""
    x = _precio(p, semana)
    epoca = math.floor(x * factor[semana.strftime("%Y-%m")] + 0.5)   # Math.round
    return (f"Hace diez años, la semana del {_fecha_larga(semana)}, {ARTICULO[p['unidad']]} "
            f"costaba {_clp(epoca)}. Si solo hubiera subido con la inflación, hoy costaría "
            f"{_clp(x)}. Esta semana cuesta {_clp(p['v'][-1])}.")


# ---------- 1. con precio 522 semanas antes ----------
@pytest.mark.parametrize("slug,unidad", [("marraqueta", "el kilo"), ("repollo", "la unidad"),
                                         ("leche-entera", "el litro")])
def test_con_precio_justo_522_semanas_antes(sitio, datos, slug, unidad):
    h = _leer(sitio, f"productos/{slug}.html")
    p = _de(datos, slug)
    assert _diez(h) == [_esperada(p, REF, _factor(datos))]
    linea = _diez(h)[0]
    assert linea.startswith(f"Hace diez años, la semana del 19 de septiembre de 2016, {unidad} "
                            f"costaba $")
    epoca, ajustado, esta = _cifras(linea)
    # la segunda, el ajustado por inflación de esa semana; la primera, el
    # mismo precio en pesos de entonces (más bajo); la tercera, el número
    # grande de la ficha
    assert ajustado == p["v"][I_REF] and epoca < ajustado
    assert esta == p["v"][-1]
    assert f'<div class="oprice">{_clp(esta)}</div>' in h


def test_tercera_cifra_la_de_esta_semana(sitio, datos):
    """La tercera cifra es el precio de esta semana aunque no sea el más alto
    de la serie ni pase al de la inflación: la leche cuesta $900, menos que
    los $931 que costaría si solo hubiera subido con la inflación (como la
    real en octubre de 2026: $1.175 y $1.150)."""
    p = _de(datos, "leche-entera")
    _epoca, ajustado, esta = _cifras(_diez(_leer(sitio, "productos/leche-entera.html"))[0])
    assert esta == p["v"][-1] < ajustado < max(x for x in p["v"] if x is not None)


# ---------- 2. sin precio esa semana: la más cercana ----------
@pytest.mark.parametrize("slug", ["papa", "betarraga", "zanahoria", "zapallo", "apio"])
def test_sin_precio_esa_semana_la_mas_cercana(sitio, datos, slug):
    """Papa: sin REF, con la anterior y la siguiente: la anterior. Betarraga:
    sin REF ni la anterior: la siguiente, antes que la de dos semanas antes.
    Zanahoria: solo dos antes y dos después: dos antes. Zapallo: solo dos
    después. Apio: la serie parte una semana después de REF."""
    semana = REF + datetime.timedelta(weeks=CON_LINEA[slug])
    (linea,) = _diez(_leer(sitio, f"productos/{slug}.html"))
    assert linea == _esperada(_de(datos, slug), semana, _factor(datos))
    assert f"la semana del {_fecha_larga(semana)}," in linea


def test_las_semanas_del_arrastre_no_cuentan(sitio, datos):
    """Las semanas que completó el arrastre de indices.py (las de REP en la
    ficha, que la frase de "Comparar con" tampoco usa) no cuentan: la línea
    nombra la semana y en ellas ODEPA no publicó precio. Choclo: REF repite
    la anterior: la anterior. Pimiento: sin REF, y la anterior repite la de
    cinco semanas antes: la siguiente, no la anterior. Lechuga: de dos
    semanas antes a una después repiten la de tres antes (la primera ya en
    septiembre, con otro ajustado y el mismo nominal de agosto) y dos
    después no tiene precio: no va."""
    for slug, semanas in ARRASTRE.items():
        h = _leer(sitio, f"productos/{slug}.html")
        rep = json.loads(re.search(r"const REP = (\[[^\]]*\]);", h).group(1))
        assert rep == [I_REF + s for s in semanas], slug
    for slug in ("choclo", "pimiento"):
        semana = REF + datetime.timedelta(weeks=CON_LINEA[slug])
        assert _diez(_leer(sitio, f"productos/{slug}.html")) == [
            _esperada(_de(datos, slug), semana, _factor(datos))], slug
    assert _diez(_leer(sitio, "productos/lechuga.html")) == []


# ---------- 3 y 4. cuándo no va ----------
@pytest.mark.parametrize("slug", SIN_LINEA)
def test_sin_precio_en_la_ventana_no_va(sitio, slug):
    """Pepino: sin precio de dos semanas antes a dos después. Acelga: la
    serie parte tres semanas después de REF. Lechuga: en esa ventana, solo
    semanas del arrastre. Producto 0: 60 semanas."""
    h = _leer(sitio, f"productos/{slug}.html")
    # con precio esta semana: la frase citable va, la línea no
    assert '<p class="citable">' in h
    assert 'class="diez"' not in h and "Hace diez años" not in h


@pytest.mark.parametrize("slug", ["uva", "chirimoya"])
def test_sin_precio_esta_semana_no_va(sitio, slug):
    h = _leer(sitio, f"productos/{slug}.html")
    assert "Sin precio de ODEPA esta semana." in h
    assert 'class="citable"' not in h and 'class="diez"' not in h and "Hace diez años" not in h


def test_mes_sin_factor_no_va(tmp_path):
    """Sin los índices de ese mes, el gráfico no tiene el precio de la
    época de esa semana: la línea no va, nunca con otra cifra. Aquí los
    índices parten el 10 de octubre de 2016: la marraqueta (con precio en
    REF, en septiembre) queda sin línea y el zapallo (el 3 de octubre) la
    lleva."""
    datos = sintetico(semanas_indices=520)
    _construir(tmp_path, datos)
    factor = _factor(datos)
    assert "2016-09" not in factor and "2016-10" in factor
    h = _leer(tmp_path, "productos/marraqueta.html")
    assert '<p class="citable">' in h and 'class="diez"' not in h
    assert _diez(_leer(tmp_path, "productos/zapallo.html")) == [
        _esperada(_de(datos, "zapallo"), REF + datetime.timedelta(weeks=2), factor)]


# ---------- 5. la primera cifra: la del gráfico en "Precio de la época" ----------
def test_primera_cifra_con_el_factor_mensual(sitio, datos):
    """La primera cifra es el ajustado de esa semana por el factor de su mes
    (factorMensual del datafeed, calculado aquí aparte), con el redondeo de
    Math.round; el del zapallo, ya en octubre, es el de octubre."""
    factor = _factor(datos)
    for slug, semanas in CON_LINEA.items():
        semana = REF + datetime.timedelta(weeks=semanas)
        x = _precio(_de(datos, slug), semana)
        f = factor[semana.strftime("%Y-%m")]
        assert 0.5 < f < 0.7   # lejos de 1: el sintético distingue las dos cifras
        epoca, ajustado, _esta = _cifras(_diez(_leer(sitio, f"productos/{slug}.html"))[0])
        assert (epoca, ajustado) == (math.floor(x * f + 0.5), x), slug
    x = _precio(_de(datos, "zapallo"), REF + datetime.timedelta(weeks=2))
    epoca = _cifras(_diez(_leer(sitio, "productos/zapallo.html"))[0])[0]
    assert epoca != math.floor(x * factor["2016-09"] + 0.5)


def test_primera_cifra_en_el_datafeed(sitio):
    """La misma cifra que da el datafeed del build (carestia-tv.js) para esa
    semana en "Precio de la época", corrido en Node."""
    if not NODE:
        pytest.skip("sin Node.js")
    r = subprocess.run([NODE, "-e", JS_EPOCA, str(sitio), json.dumps(list(CON_LINEA))],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    cierres = json.loads(r.stdout)
    for slug, semanas in CON_LINEA.items():
        semana = (REF + datetime.timedelta(weeks=semanas)).isoformat()
        epoca = _cifras(_diez(_leer(sitio, f"productos/{slug}.html"))[0])[0]
        assert cierres[slug][semana] == epoca, slug


# ---------- 6. dónde va ----------
def test_bajo_la_frase_citable(sitio):
    for slug in CON_LINEA:
        h = _leer(sitio, f"productos/{slug}.html")
        # justo bajo la frase citable y antes de la línea de la semana
        assert re.search(r'<p class="citable">[^<]*</p>\n    <p class="diez">[^<]*</p>\n'
                         r'    <div class="fecha">', h), slug
    # con el aspecto de la frase citable, cuyas reglas no cambian, y la
    # línea de la semana igual de cerca
    h = _leer(sitio, "productos/marraqueta.html")
    for regla in [".citable { font:400 13px/1.6 var(--sans); color:var(--ash); margin-top:14px;\n"
                  "    text-wrap:pretty; }\n  .citable + .fecha { margin-top:4px; }",
                  ".diez { font:400 13px/1.6 var(--sans); color:var(--ash); margin-top:4px;\n"
                  "    text-wrap:pretty; }\n  .diez + .fecha { margin-top:4px; }"]:
        assert regla in h, regla


def test_solo_en_el_html_de_la_ficha(sitio):
    """Una vez en la ficha, en su párrafo: ni en la tarjeta (og:image:alt),
    la description o el Dataset (JSON-LD), ni en datos/catalogo.json, la
    portada, /graficos.html, carestia-ficha.js u otro archivo del build."""
    fichas = set()
    for slug in CON_LINEA:
        ruta = os.path.join("productos", f"{slug}.html")
        fichas.add(ruta)
        h = _leer(sitio, ruta)
        assert h.count("Hace diez años") == 1, slug
        cabeza = h[:h.index("</head>")]
        assert "Hace diez años" not in cabeza and "Si solo hubiera subido" not in cabeza, slug
        for meta in re.findall(r'<meta (?:name|property)="[^"]+" content="([^"]*)">', h):
            assert "Hace diez años" not in meta, slug
        for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            assert "Hace diez años" not in json.dumps(json.loads(ld), ensure_ascii=False), slug
    otros = [r for r in glob.glob(os.path.join(sitio, "**", "*"), recursive=True)
             if os.path.isfile(r) and os.path.relpath(r, sitio) not in fichas]
    for r in ["index.html", "graficos.html", "carestia-ficha.js", "carestia-tv.js",
              "compras.html", os.path.join("datos", "catalogo.json"),
              os.path.join("productos", "index.html")]:
        assert os.path.join(sitio, r) in otros, r
    for r in otros:
        with open(r, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
        assert "Hace diez años" not in texto and 'class="diez"' not in texto, r


# ---------- 7. guardia de texto ----------
def test_guardia_de_texto(sitio):
    for slug in CON_LINEA:
        h = _leer(sitio, f"productos/{slug}.html")
        assert infracciones(h) == [], slug
        (linea,) = _diez(h)
        # el mes con su nombre completo y en minúscula, sin rayas ni "·"
        assert LINEA.fullmatch(linea), linea


# ---------- 8. el redondeo de la primera cifra ----------
def _linea_diez_anios():
    """linea_diez_anios de build_site.py sin importarlo (construye el sitio
    al importarse): su código y el de lo que usa, tal cual."""
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    nodos = [n for n in arbol.body
             if (isinstance(n, ast.FunctionDef) and
                 n.name in ("linea_diez_anios", "fin_serie", "fecha_larga", "fmt_clp")) or
             (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and
              n.targets[0].id in ("SEMANAS_DIEZ_ANIOS", "VENTANA_DIEZ_ANIOS", "UNI_ARTICULO",
                                  "MESES"))]
    espacio = {"datetime": datetime, "math": math}
    exec(compile(ast.Module(body=nodos, type_ignores=[]), "build_site.py", "exec"), espacio)
    return espacio["linea_diez_anios"]


def test_la_mitad_sube_como_math_round():
    """La primera cifra redondea como Math.round del datafeed, con la mitad
    hacia arriba: $1.524 por 0,625 da 952,5, que es $953 (round() de Python
    daría $952). Un factor que en el build no sale de los índices, para
    llegar justo a la mitad."""
    linea = _linea_diez_anios()
    v = [2000] * LARGO
    v[I_REF], v[-1] = 1524, 1800
    p = {"unidad": "kg", "t0": (FIN - datetime.timedelta(weeks=LARGO - 1)).isoformat(), "v": v}
    assert linea(p, {"2016-09": 0.625}, []) == (
        "Hace diez años, la semana del 19 de septiembre de 2016, el kilo costaba $953. Si solo "
        "hubiera subido con la inflación, hoy costaría $1.524. Esta semana cuesta $1.800.")

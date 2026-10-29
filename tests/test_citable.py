"""Cifras legibles para buscadores con IA. Sin red: build_site.py corre en un
directorio temporal con el indices.json sintético de test_texto.py, más un
producto con veredicto por temporada, uno que parte con semanas sin precio,
uno sin precio esta semana (último dato hace 8 semanas) y el Índice Asado
partiendo después que los demás. La chirimoya del sintético no tiene precio
hace más de un año.

Verifica el Dataset (JSON-LD) de cada ficha y cada página de índice, la
frase citable y la línea de cita de las fichas, la línea de cita de las
páginas de índice y el bloque estático "ESTA SEMANA" de /graficos.html (con
la semana propia del índice que termina antes, como el Fruta sin mandarina)."""
import datetime
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from indices import BASKETS, DATASET  # noqa: E402
from test_texto import indices_sintetico, infracciones  # noqa: E402

FIN = datetime.date(2026, 9, 21)   # lunes de la semana vigente del sintético
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
CITA = "Carestía (carestia.cl), con datos de ODEPA"
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
PROHIBIDAS = ["señal", "comprar", "vender", "oportunidad", "sobrecompra", "sobreventa",
              "soporte", "resistencia", "alcista", "bajista", "inversión", "rentabilidad"]


def _producto(label: str, unidad: str, grupo: str, v: list, atraso: int = 0) -> dict:
    """Una serie semanal 'v' que termina 'atraso' semanas antes de FIN."""
    fin = FIN - datetime.timedelta(weeks=atraso)
    return {"label": label, "unidad": unidad, "grupo": grupo,
            "t0": (fin - datetime.timedelta(weeks=len(v) - 1)).isoformat(), "v": v}


def sintetico() -> dict:
    out = indices_sintetico()
    p = out["productos"]
    # 13 años de historia: con veredicto por temporada
    p["tomate"] = _producto("Tomate", "kg", "Hortalizas",
                            [1500 + 10 * (j % 9) for j in range(52 * 13)])
    # las primeras 5 semanas sin precio: la serie parte en la sexta
    p["lechuga"] = _producto("Lechuga", "un", "Hortalizas", [None] * 5 + [700] * 55)
    # sin precio esta semana: último dato hace 8 semanas (serie abierta)
    p["uva"] = _producto("Uva", "kg", "Frutas", [1200] * 60, atraso=8)
    # el Índice Asado parte 100 semanas después que los demás
    a = out["indices"]["asado"]
    a["real"] = a["nominal"] = a["real"][100:]
    return out


def _construir(d, datos: dict):
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0", CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


@pytest.fixture(scope="module")
def datos():
    return sintetico()


@pytest.fixture(scope="module")
def sitio(tmp_path_factory, datos):
    d = tmp_path_factory.mktemp("build_citable")
    _construir(d, datos)
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _slug(label: str) -> str:
    s = unicodedata.normalize("NFKD", label)
    return "-".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def _fecha_larga(f: datetime.date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def _fin(p: dict) -> datetime.date:
    return datetime.date.fromisoformat(p["t0"]) + datetime.timedelta(weeks=len(p["v"]) - 1)


def _primera(p: dict) -> datetime.date:
    i = next(i for i, v in enumerate(p["v"]) if v is not None)
    return datetime.date.fromisoformat(p["t0"]) + datetime.timedelta(weeks=i)


def _fichas(sitio, datos) -> dict:
    """{ruta: producto} de las fichas publicadas."""
    out = {}
    for p in datos["productos"].values():
        ruta = f"productos/{_slug(p['label'])}.html"
        if (sitio / ruta).exists():
            out[ruta] = p
    return out


def _parrafo(h: str, clase: str) -> list:
    return [html.unescape(m) for m in re.findall(rf'<p class="{clase}">(.*?)</p>', h, re.S)]


def _jsonld(h: str) -> list:
    return [json.loads(x) for x in LD.findall(h)]


def _todos_los_jsonld(sitio) -> dict:
    return {os.path.relpath(r, sitio): _jsonld(open(r, encoding="utf-8").read())
            for r in sorted(glob.glob(os.path.join(sitio, "productos", "*.html")) +
                            glob.glob(os.path.join(sitio, "indices", "*.html")))
            if not r.endswith("index.html")}


# ---------- 1. JSON-LD Dataset ----------
def test_un_dataset_por_ficha_y_por_indice(sitio, datos):
    fichas = _fichas(sitio, datos)
    assert len(fichas) == len(datos["productos"])
    paginas = {**fichas, **{f"indices/{c}.html": d for c, d in datos["indices"].items()}}
    for ruta, serie in paginas.items():
        h = _leer(sitio, ruta)
        lds = _jsonld(h)
        assert len(lds) == 1, ruta
        ld = lds[0]
        assert ld["@context"] == "https://schema.org" and ld["@type"] == "Dataset", ruta
        titulo = html.unescape(re.search(r"<title>(.*?)</title>", h).group(1))
        assert ld["name"] == titulo.removesuffix(" | Carestía") != titulo, ruta
        assert 50 <= len(ld["description"]) <= 5000, ruta
        canonical = re.search(r'<link rel="canonical" href="([^"]+)">', h).group(1)
        assert ld["url"] == canonical == f"https://carestia.cl/{ruta}", ruta
        assert ld["license"] == "https://carestia.cl/terminos.html", ruta
        assert ld["acquireLicensePage"] == "https://carestia.cl/contacto.html"
        assert ld["creditText"] == CITA and ld["isAccessibleForFree"] is True
        assert ld["creator"] == {"@type": "Organization", "name": "Carestía",
                                 "url": "https://carestia.cl"}
        assert ld["spatialCoverage"] == {"@type": "Place",
                                         "name": "Región Metropolitana de Santiago, Chile"}
        assert ld["includedInDataCatalog"] == {"@type": "DataCatalog", "name": "Carestía",
                                               "url": "https://carestia.cl/productos/"}
        # la serie desde su primera semana con valor
        desde = (_primera(serie) if ruta.startswith("productos/")
                 else datetime.date.fromisoformat(serie["real"][0]["time"]))
        assert ld["temporalCoverage"].startswith(f"{desde.isoformat()}/"), ruta
        assert str(desde.year) in ld["description"], ruta
        # describe la serie, no el dato de la semana: sin cifras en pesos
        assert "$" not in ld["description"], ruta
    # las fichas antes de </head>; las páginas de índice, al final del cuerpo
    h = _leer(sitio, "productos/tomate.html")
    assert h.index("application/ld+json") < h.index("</head>")
    h = _leer(sitio, "indices/fruta.html")
    assert h.index('<p class="cita">') < h.index("application/ld+json") < h.index("</main>")


def test_cobertura_temporal(sitio):
    lds = _todos_los_jsonld(sitio)
    cob = lambda r: lds[r][0]["temporalCoverage"]
    # abierta, aunque no tenga precio esta semana (último dato hace 8 semanas)
    assert cob("productos/uva.html").endswith("/..")
    assert cob("productos/producto-0.html").endswith("/..")
    # parte en la primera semana con precio, no en t0
    assert cob("productos/lechuga.html") == \
        f"{(FIN - datetime.timedelta(weeks=54)).isoformat()}/.."
    # sin precio hace más de un año: cerrada en su última semana
    assert cob("productos/chirimoya.html") == "2024-01-01/2024-03-04"
    # cada índice desde su primera semana, nunca un año fijo
    asado = FIN - datetime.timedelta(weeks=199)
    assert cob("indices/asado.html") == f"{asado.isoformat()}/.."
    assert cob("indices/ensalada.html") == \
        f"{(FIN - datetime.timedelta(weeks=299)).isoformat()}/.."


def test_variable_tecnica_fuentes_y_fecha(sitio):
    with open(os.path.join(RAIZ, "textos", "metodologia.md"), encoding="utf-8") as fh:
        limites = next(l for l in fh if l.startswith("**Límites.**"))
    with open(os.path.join(RAIZ, "indices.py"), encoding="utf-8") as fh:
        fuente_indices = fh.read()
    lastmod = set(re.findall(r"<lastmod>([^<]+)</lastmod>", _leer(sitio, "sitemap.xml")))
    assert len(lastmod) == 1
    for ruta, (ld,) in _todos_los_jsonld(sitio).items():
        if ruta.startswith("productos/"):
            assert re.fullmatch(r"Precio al consumidor por (kilo|unidad|litro), en pesos "
                                r"chilenos", ld["variableMeasured"]), ruta
        else:
            assert ld["variableMeasured"] == "Costo semanal de la canasta, en pesos chilenos"
        # la frase de Límites, literal
        assert ld["measurementTechnique"].startswith("Cada precio es el promedio de los puntos")
        assert ld["measurementTechnique"] in limites
        assert ld["measurementTechnique"] in ld["description"]
        assert ld["dateModified"] == next(iter(lastmod)), ruta
        odepa, bcch = ld["isBasedOn"]
        assert odepa == {"@type": "CreativeWork", "name": "Precios al consumidor, ODEPA",
                         "url": f"https://datos.odepa.gob.cl/dataset/{DATASET}",
                         "license": "http://www.opendefinition.org/licenses/cc-by"}
        assert set(bcch) == {"@type", "name"} and bcch["@type"] == "CreativeWork"
        codigo = re.search(r"\((G[\w.]+), base 2023=100\)", bcch["name"]).group(1)
        assert codigo in fuente_indices
        assert ld["keywords"][1:] == ["precio", "Santiago", "Región Metropolitana", "ODEPA",
                                      "IPC", "costo de vida"]
    ld = _todos_los_jsonld(sitio)["indices/asado.html"][0]
    assert ld["keywords"][0] == "Índice Asado"
    # lo que lleva la canasta, con sus cantidades
    assert "La canasta lleva asado de tira (1 kg), asado carnicero (0,6 kg)" in ld["description"]
    assert "cebolla (1 unidad)" in ld["description"]
    assert _todos_los_jsonld(sitio)["productos/tomate.html"][0]["keywords"][0] == "tomate"


def test_licencia_y_sin_datos_personales_ni_trading(sitio):
    with open(os.path.join(RAIZ, "textos", "acerca.md"), encoding="utf-8") as fh:
        personas = re.findall(r"fundada en \d{4} por ([^.]+)\.", fh.read())
    assert personas   # el nombre sale del texto del dueño, no se escribe aquí
    for ruta, (ld,) in _todos_los_jsonld(sitio).items():
        assert "creativecommons.org" not in ld["license"]
        texto = json.dumps(ld, ensure_ascii=False)
        assert "creativecommons.org" not in texto, ruta
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texto), ruta     # correos
        assert '"Person"' not in texto and "pitvox" not in texto.lower(), ruta
        for persona in personas:
            for parte in persona.split():
                assert parte.lower() not in texto.lower(), ruta
        for palabra in PROHIBIDAS:
            assert palabra not in texto.lower(), (ruta, palabra)
        assert infracciones(texto) == [], ruta


def test_distribution_solo_en_los_indices(sitio):
    for ruta, (ld,) in _todos_los_jsonld(sitio).items():
        if ruta.startswith("indices/"):
            assert ld["distribution"] == {"@type": "DataDownload",
                                          "contentUrl": "https://carestia.cl/resumen.json",
                                          "encodingFormat": "application/json"}
        else:
            assert "distribution" not in ld, ruta


# ---------- 2. Frase citable y línea de cita ----------
def test_frase_citable_con_el_precio_de_esta_semana(sitio, datos):
    con_precio = 0
    for ruta, p in _fichas(sitio, datos).items():
        if _fin(p) != FIN:
            continue
        con_precio += 1
        h = _leer(sitio, ruta)
        precio = re.search(r'<div class="oprice">([^<]+)</div>', h).group(1)
        uni = re.search(r'<div class="ouni">por ([^<]+)</div>', h).group(1)
        nombre = html.unescape(re.search(r"<h1>(.*?)</h1>", h).group(1))
        frase = _parrafo(h, "pct")[0]
        citable = _parrafo(h, "citable")
        # la misma cifra del número grande y la semana de los precios
        assert citable == [f"{nombre} en la Región Metropolitana: {precio} por {uni} la semana "
                           f"del {_fecha_larga(FIN)}. {frase}"], ruta
        assert _parrafo(h, "cita") == [f"Para citar: {CITA}, semana del {_fecha_larga(FIN)}."]
        assert f"Precios de la semana del {_fecha_larga(FIN)}," in h
        # bajo el gráfico: frase, línea de la semana y línea de cita, en ese orden
        assert (h.index('id="marco"') < h.index('<p class="citable">')
                < h.index('<div class="fecha">') < h.index('<p class="cita">'))
    assert con_precio >= 25
    # con veredicto por temporada, la frase de temporada
    assert re.search(r"<p class=\"citable\">Tomate en la Región Metropolitana: \$1\.\d{3} por "
                     r"kilo la semana del 21 de septiembre de 2026\. Más (caro|barato) que en "
                     r"\d+ de los últimos \d+ septiembres, aun descontando la inflación\.</p>"
                     r"|Dentro de lo normal para septiembre",
                     _leer(sitio, "productos/tomate.html"))


@pytest.mark.parametrize("slug,fin", [("uva", FIN - datetime.timedelta(weeks=8)),
                                      ("chirimoya", datetime.date(2024, 3, 4))])
def test_ficha_sin_precio_esta_semana(sitio, slug, fin):
    h = _leer(sitio, f"productos/{slug}.html")
    assert "Sin precio de ODEPA esta semana." in h
    # sin frase citable: un precio viejo nunca se presenta como de esta semana
    assert 'class="citable"' not in h and 'class="oprice"' not in h
    # la línea de cita, con la semana de su último dato
    assert _parrafo(h, "cita") == [f"Para citar: {CITA}, semana del {_fecha_larga(fin)}."]
    assert f"Precios de la semana del {_fecha_larga(fin)}," in h


def test_linea_de_cita_en_las_paginas_de_indice(sitio, datos):
    for code, d in datos["indices"].items():
        h = _leer(sitio, f"indices/{code}.html")
        fin = datetime.date.fromisoformat(d["real"][-1]["time"])
        assert _parrafo(h, "cita") == [f"Para citar: {CITA}, semana del {_fecha_larga(fin)}."]
        # después de la línea de la fuente; la frase no se repite
        assert h.index("Fuente: precios al consumidor de ODEPA") < h.index('<p class="cita">')
        assert 'class="citable"' not in h
        # ceniza y chica, sin colores nuevos ni semáforo
        assert ".cita { font:400 12px/1.6 var(--sans); color:var(--ash);" in h
        assert infracciones(h) == []


# ---------- 3. La semana de los índices en /graficos.html ----------
def _bloque(h: str) -> str:
    i = h.index('<section class="ctx-semana m-ind"')
    return h[i:h.index("</section>", i)]


def test_bloque_esta_semana_en_graficos(sitio, datos):
    h = _leer(sitio, "graficos.html")
    b = _bloque(h)
    # bajo la franja de contexto del modo índices, que es con el que carga
    assert h.index('<section class="contexto m-ind">') < h.index(b)
    assert '<body data-modo="indices">' in h
    assert '<h2 class="ctx-h" id="h-semana-ind">ESTA SEMANA</h2>' in b
    assert _parrafo(b, "sem-intro") == [
        f"Costo de cada canasta en la Región Metropolitana, semana del {_fecha_larga(FIN)}."]
    lineas = re.findall(r'<p class="sem-ind"><a href="([^"]+)">([^<]+)</a>: (\$[\d.]+)\. '
                        r'(.*?)</p>', b)
    assert [x[0] for x in lineas] == [f"https://carestia.cl/indices/{c}.html" for c in BASKETS]
    for (href, nombre, cifra, frase), code in zip(lineas, BASKETS):
        pagina = _leer(sitio, f"indices/{code}.html")
        # la misma cifra y la misma frase de la página del índice
        assert f'<span class="ind-precio">{cifra}</span>' in pagina
        assert f'<p class="intro">{frase} Está en el percentil' in pagina
        assert nombre == datos["indices"][code]["nombre"]
    assert "<li" not in b and "<ul" not in b
    assert infracciones(b) == []


def test_bloque_con_un_indice_atrasado(tmp_path):
    """El Índice Fruta termina antes casi todos los veranos (sin mandarina):
    el bloque va igual, con la semana más reciente en la línea de entrada y
    la suya al lado de su nombre (decisión del dueño). Cada página de índice
    cita la semana de su propio último dato."""
    datos = indices_sintetico()
    f = datos["indices"]["fruta"]
    f["real"] = f["nominal"] = f["real"][:-8]
    f["velas"] = f["velas"][:-8]
    _construir(tmp_path, datos)
    fruta = FIN - datetime.timedelta(weeks=8)
    b = _bloque((tmp_path / "graficos.html").read_text(encoding="utf-8"))
    assert _parrafo(b, "sem-intro") == [
        f"Costo de cada canasta en la Región Metropolitana, semana del {_fecha_larga(FIN)}."]
    lineas = re.findall(r'<p class="sem-ind"><a href="https://carestia\.cl/indices/(\w+)\.html">'
                        r'([^<]+)</a>( \(semana del [^)]+\))?: (\$[\d.]+)\. (.*?)</p>', b)
    assert [x[0] for x in lineas] == list(BASKETS)
    for code, nombre, cuando, cifra, frase in lineas:
        pagina = (tmp_path / f"indices/{code}.html").read_text(encoding="utf-8")
        # solo el atrasado lleva su semana, y es la de su último dato
        assert cuando == ("" if code != "fruta" else f" (semana del {_fecha_larga(fruta)})")
        assert f'<span class="ind-precio">{cifra}</span>' in pagina
        assert f'<p class="intro">{frase} Está en el percentil' in pagina
        fin = fruta if code == "fruta" else FIN
        assert _parrafo(pagina, "cita") == [
            f"Para citar: {CITA}, semana del {_fecha_larga(fin)}."], code
    assert infracciones(b) == []


def test_frases_nuevas_sin_maximos_ni_records(sitio):
    nuevas = [_bloque(_leer(sitio, "graficos.html"))]
    for r in glob.glob(os.path.join(sitio, "productos", "*.html")) + \
            glob.glob(os.path.join(sitio, "indices", "*.html")):
        h = open(r, encoding="utf-8").read()
        nuevas += _parrafo(h, "citable") + _parrafo(h, "cita") + LD.findall(h)
    for texto in nuevas:
        for palabra in ["máximo", "maximo", "récord", "record", "peak"]:
            assert palabra not in texto.lower(), (palabra, texto[:80])

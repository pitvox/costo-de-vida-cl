"""Higiene de datos y credibilidad: lo que más subió y bajó contra el promedio
de 4 semanas, nombres para mostrar, Santiago en los títulos, el número de
productos calculado en el build, las tarjetas og:image, las páginas de los
índices, /prensa.html y el aviso de semana sin datos nuevos. Sin red:
build_site.py corre en un directorio temporal con un indices.json sintético."""
import ast
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from indices import BASKETS  # noqa: E402

FIN = datetime.date(2026, 9, 21)          # lunes de la semana vigente
VIERNES = "2026-09-25T15:00"              # ODEPA ya publicó esa semana
N = 80


def _t0(n: int = N, fin: datetime.date = FIN) -> str:
    return (fin - datetime.timedelta(weeks=n - 1)).isoformat()


def _producto(label, grupo, v, unidad="kg", propio=None, fin=FIN):
    """Un producto con su rango (min y max) en las semanas con precio propio
    y sin rango en las que completó el arrastre ('propio' False)."""
    propio = propio or [x is not None for x in v]
    return {"label": label, "unidad": unidad, "grupo": grupo, "t0": _t0(len(v), fin),
            "v": v,
            "min": [x - 50 if x is not None and p else None for x, p in zip(v, propio)],
            "max": [x + 50 if x is not None and p else None for x, p in zip(v, propio)]}


def sintetico() -> dict:
    out = {"generado": "2026-09-26", "ipc_mes": "2026-08", "indices": {}, "productos": {},
           "descartes": []}
    colores = {"BARATO": "#5bbf7a", "NORMAL": "#e0a83c", "CARO": "#e0552f"}
    for k, (code, meta) in enumerate(BASKETS.items()):
        fechas = [(FIN - datetime.timedelta(weeks=99 - i)).isoformat() for i in range(100)]
        # el último valor es mayor que 81 de las 100 semanas: 8 de cada 10
        real = [{"time": t, "value": 10000 + 10 * i} for i, t in enumerate(fechas)]
        real[-1]["value"] = 10815
        ver = ["CARO", "NORMAL", "BARATO", "NORMAL"][k]
        out["indices"][code] = {
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
            "fecha": "21-09-2026", "costo_nominal": 10815, "costo_real": 10815,
            "percentil": 82, "zscore": 0.1, "vs_promedio": [14, 0, -5, 6][k],
            "veredicto": ver, "color": colores[ver], "n": len(real),
            "componentes": [{"label": lab, "qty": qty, "unidad": uni,
                             "odepa_unit": "$/kg", "factor": 1.0, "mismatch": False,
                             "precio_ult": 1000, "aporte": 1000}
                            for (lab, _m, qty, uni) in meta["items"]],
            "estacionalidad": {"factores": {str(m): 1.0 for m in range(1, 13)},
                               "mes_barato": 1, "mes_caro": 2, "amplitud": 1},
            "velas": [], "nominal": real, "real": real,
        }
    p = out["productos"]
    # vuelve de temporada: las 4 semanas anteriores las completó el arrastre
    # (sin rango); sube 150% contra la semana anterior pero no entra a la lista
    v = [1000] * (N - 1) + [2500]
    p["arveja_verde"] = _producto("Arveja Verde", "Hortalizas", v,
                                  propio=[True] * (N - 5) + [False] * 4 + [True])
    # con precio propio en las 5 semanas: +20% sobre el promedio de las 4
    p["tomate"] = _producto("Tomate", "Hortalizas", [900] * (N - 5) + [950, 1050, 1000, 1000, 1200])
    p["papa"] = _producto("Papa", "Hortalizas", [1000] * (N - 1) + [800])
    p["cerdo_pulpa_c/hueso"] = _producto("Cerdo Pulpa c/hueso", "Carne de Cerdo - Ave - Cordero",
                                         [5000] * N)
    p["lentejas_6_mm"] = _producto("Lentejas 6 mm", "Abarrotes y otros", [2000] * N)
    p["leche_en_polvo_entera"] = _producto("Leche en Polvo Entera",
                                           "Lácteos - Huevos - Margarinas", [9000] * N)
    # sin datos hace más de un año: no cuenta entre los productos recientes
    p["maracuya"] = _producto("Maracuyá", "Frutas", [3000] * 10,
                              fin=datetime.date(2014, 11, 10))
    return out


def _construir(d, ahora):
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(sintetico()), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8", CARESTIA_AHORA=ahora)
    env.pop("CARESTIA_BORRADOR", None)
    env.pop("CARESTIA_TARJETAS", None)      # aquí sí se dibujan las tarjetas
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    return _construir(tmp_path_factory.mktemp("build_credibilidad"), VIERNES)


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _lista(h, lid):
    bloque = re.search(rf'id="{lid}">(.*?)</ul>', h, re.S).group(1)
    return [(n, re.sub(r"<[^>]+>", "", v)) for n, v in
            re.findall(r'<b>([^<]+)</b>.*?<span class="sv">(.*?)</span></a>', bloque)]


# ---------- 2. lo que más subió y bajó ----------
def test_mas_subio_y_bajo_contra_el_promedio_de_4_semanas(sitio):
    h = _leer(sitio, "index.html")
    # +20%: 1.200 sobre el promedio de 950, 1.050, 1.000 y 1.000
    assert _lista(h, "sem-sub") == [("Tomate", "▲ 20,0%")]
    assert _lista(h, "sem-baj") == [("Papa", "▼ 20,0%")]
    assert h.count("<span>Frente al promedio de las 4 semanas anteriores</span>") == 2
    assert "Contra la semana anterior" not in h
    # la arveja volvió de temporada: sube 150% en la semana (la tabla lo
    # muestra) pero no entra a la lista
    fila = re.search(r'<a class="fila" href="/productos/arveja-verde.html".*?</a>', h).group(0)
    assert 'data-w="150.0"' in fila
    cat = json.loads(_leer(sitio, "datos/catalogo.json"))
    arveja = next(f for f in cat["productos"] if f["clave"] == "arveja_verde")
    assert arveja["variacion_1s_pct"] == 150.0 and arveja["variacion_prom4s_pct"] is None


# ---------- 3. nombres para mostrar ----------
def test_nombres_para_mostrar_sin_tocar_datos_ni_slugs(sitio):
    h = _leer(sitio, "index.html")
    nombres = re.findall(r'<span class="nm">([^<]+)</span>', h)
    assert "Arveja verde" in nombres and "Pulpa de cerdo con hueso" in nombres
    assert "Arveja Verde" not in nombres and "Cerdo Pulpa c/hueso" not in h
    # la URL sale del nombre de ODEPA, como siempre
    ficha = _leer(sitio, "productos/cerdo-pulpa-chueso.html")
    assert "<h1>Pulpa de cerdo con hueso</h1>" in ficha
    assert ("<title>Precio de la pulpa de cerdo con hueso en Santiago: histórico desde "
            "2025 | Carestía</title>") in ficha
    assert 'href="https://carestia.cl/graficos.html#canasta=cerdo_pulpa_c/hueso:0.5"' in ficha
    # los datos no cambian: datos/productos/ e indices.json con el nombre de ODEPA
    dato = json.loads(_leer(sitio, "datos/productos/cerdo-pulpa-chueso.json"))
    assert dato["label"] == "Cerdo Pulpa c/hueso"
    # /graficos.html (selectores, Comparar y canasta) y /productos/ muestran el nuevo
    g = _leer(sitio, "graficos.html")
    assert '"cerdo_pulpa_c/hueso":{"label":"Pulpa de cerdo con hueso"' in g
    assert ">Pulpa de cerdo con hueso<" in _leer(sitio, "productos/index.html")


def test_concordancia_de_genero_y_numero(sitio):
    lentejas = _leer(sitio, "productos/lentejas-6-mm.html")
    assert "Hoy las lentejas 6 mm cuestan $2.000 por kilo en la Región Metropolitana" in lentejas
    assert "<title>Precio de las lentejas 6 mm en Santiago" in lentejas
    leche = _leer(sitio, "productos/leche-en-polvo-entera.html")
    assert "Hoy la leche en polvo entera cuesta $9.000 por kilo" in leche
    assert "<title>Precio de la leche en polvo entera en Santiago" in leche


# ---------- 4. precisión ----------
def _cabecera(h):
    return " ".join(re.findall(r"<title>.*?</title>|<meta (?:name=\"description\"|property=\"og:"
                               r"(?:title|description)\")[^>]*>", h))


def test_santiago_en_titulos_y_region_metropolitana_en_descripciones(sitio):
    paginas = (["index.html", "graficos.html", "productos/index.html", "acerca.html",
                "prensa.html"] + [os.path.relpath(p, sitio) for p in
                                  glob.glob(str(sitio / "productos" / "*.html")) +
                                  glob.glob(str(sitio / "indices" / "*.html"))])
    for p in paginas:
        assert "en Chile" not in _cabecera(_leer(sitio, p)), p
    tomate = _leer(sitio, "productos/tomate.html")
    assert "<title>Precio del tomate en Santiago: histórico desde" in tomate
    assert "por kilo en la Región Metropolitana (promedio de ferias" in tomate
    assert '<div class="miga">Precio de esta semana en Santiago</div>' in tomate


def test_numero_de_productos_calculado_en_el_build(sitio):
    # 6 con datos recientes; el maracuyá es de 2014
    listado = _leer(sitio, "productos/index.html")
    assert ("<title>Precios de 6 alimentos en Santiago, en pesos de agosto 2026 | "
            "Carestía</title>") in listado
    assert "Precios de 6 productos en la Región Metropolitana" in listado
    assert "ver los 6 productos</a>" in _leer(sitio, "404.html")
    for md in ("acerca.md", "404.md"):
        with open(os.path.join(RAIZ, "textos", md), encoding="utf-8") as fh:
            texto = fh.read()
        assert "125" not in texto and "{productos}" in texto, md


def test_api_publica_en_el_pie(sitio):
    for p in ["index.html", "productos/tomate.html", "metodologia.html", "indices/asado.html"]:
        h = _leer(sitio, p)
        assert '<a href="https://carestia.cl/resumen.json">API pública (uso no comercial)</a>' in h, p
        assert "Datos abiertos (resumen.json)" not in h, p


# ---------- aviso de semana sin datos nuevos ----------
def _funciones_del_aviso() -> dict:
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    piezas = [n for n in arbol.body if
              (isinstance(n, ast.FunctionDef) and n.name in ("semana_esperada", "sin_datos_nuevos"))
              or (isinstance(n, ast.Assign) and any(getattr(t, "elts", None) and
                                                     t.elts[0].id == "ODEPA_DIA" for t in n.targets))]
    g = {"datetime": datetime}
    exec(compile(ast.Module(body=piezas, type_ignores=[]), "build_site.py", "exec"), g)
    return g


def test_semana_esperada_segun_el_viernes_de_odepa():
    g = _funciones_del_aviso()
    tz = datetime.timezone(datetime.timedelta(hours=-3))
    lunes = datetime.date(2026, 9, 28)
    casos = [("2026-10-02T11:59", lunes - datetime.timedelta(weeks=1)),   # viernes antes de las 12
             ("2026-10-02T12:00", lunes),                                   # viernes a mediodía
             ("2026-10-02T16:30", lunes),
             ("2026-10-05T09:00", lunes),                                   # lunes siguiente
             ("2026-10-08T23:00", lunes),                                   # jueves
             ("2026-10-09T13:00", lunes + datetime.timedelta(weeks=1))]
    for ahora, esperada in casos:
        f = datetime.datetime.fromisoformat(ahora).replace(tzinfo=tz)
        assert g["semana_esperada"](f) == esperada, ahora
    viernes = datetime.datetime(2026, 10, 2, 14, 0, tzinfo=tz)
    assert g["sin_datos_nuevos"](lunes - datetime.timedelta(weeks=1), viernes)
    assert not g["sin_datos_nuevos"](lunes, viernes)


def test_portada_sin_aviso_con_la_semana_al_dia(sitio):
    h = _leer(sitio, "index.html")
    assert ('<div class="semana">Semana del <span class="nw">21-09-2026</span>. '
            '<span>Se actualiza los viernes.</span></div>') in h
    assert "Sin datos nuevos de ODEPA" not in h


def test_portada_avisa_si_odepa_no_publico(tmp_path):
    # una semana después: ODEPA debió publicar la del 28-09 y los datos llegan al 21-09
    d = _construir(tmp_path, "2026-10-02T16:30")
    h = _leer(d, "index.html")
    assert ('<div class="semana">Semana del <span class="nw">21-09-2026</span>. '
            '<span class="sin-nuevos">Sin datos nuevos de ODEPA esta semana.</span></div>') in h
    assert ".semana .sin-nuevos { color:var(--bone); }" in h


# ---------- 5. tarjetas para WhatsApp ----------
def _og(h):
    img = re.search(r'<meta property="og:image" content="https://carestia.cl/([^"?]+)\?v=([0-9a-f]{10})">', h)
    assert img, "sin og:image propia"
    assert '<meta property="og:image:width" content="1200">' in h
    assert '<meta property="og:image:height" content="630">' in h
    assert re.search(r'<meta property="og:image:alt" content="[^"]+">', h)
    assert f'<meta name="twitter:image" content="https://carestia.cl/{img.group(1)}?v={img.group(2)}">' in h
    return img.group(1)


def test_cada_ficha_indice_y_portada_tiene_su_tarjeta(sitio):
    rutas = {"index.html": "og/portada.png"}
    for p in glob.glob(str(sitio / "productos" / "*.html")):
        slug = os.path.basename(p)[:-5]
        if slug != "index":
            rutas[f"productos/{slug}.html"] = f"og/productos/{slug}.png"
    for code in BASKETS:
        rutas[f"indices/{code}.html"] = f"og/indices/{code}.png"
    assert len(rutas) == 1 + 7 + len(BASKETS)
    for pagina, png in rutas.items():
        assert _og(_leer(sitio, pagina)) == png, pagina
        with Image.open(sitio / png) as im:
            assert im.size == (1200, 630) and im.format == "PNG", png
    # las demás páginas siguen con la genérica
    assert '<meta property="og:image" content="https://carestia.cl/og.png">' in \
        _leer(sitio, "metodologia.html")


def test_la_frase_y_el_alt_de_las_tarjetas(sitio):
    asado = _leer(sitio, "indices/asado.html")
    # menos de 5 años de cada mes: la frase contra toda la historia
    assert ('content="Índice Asado: $10.815, CARO, semana del 21-09-2026. '
            'Más caro que en 8 de cada 10 semanas desde 2024, descontada la inflación."') in asado
    tomate = _leer(sitio, "productos/tomate.html")
    assert ('content="Tomate: $1.200 por kilo, semana del 21-09-2026. '
            'Más caro que en 10 de cada 10 semanas desde 2025, descontada la inflación."') in tomate
    papa = _leer(sitio, "productos/papa.html")
    assert "Más barata que en 10 de cada 10 semanas desde 2025, descontada la inflación." in papa
    portada = _leer(sitio, "index.html")
    assert ('content="Índices Carestía, semana del 21-09-2026: Asado $10.815, CARO. '
            'Ensalada $10.815, NORMAL.') in portada


# ---------- páginas de los índices ----------
def test_pagina_de_cada_indice(sitio):
    h = _leer(sitio, "indices/asado.html")
    assert '<link rel="canonical" href="https://carestia.cl/indices/asado.html">' in h
    assert "<title>Índice Asado: asado para 4 personas en Santiago | Carestía</title>" in h
    assert "<h1>Índice Asado</h1>" in h
    assert '<span class="ind-precio">$10.815</span>' in h
    assert 'style="background:var(--rojo)">CARO</span>' in h
    assert "Más caro que en 8 de cada 10 semanas desde 2024, descontada la inflación." in h
    assert "+14% sobre su promedio histórico" in h
    assert '<a href="https://carestia.cl/graficos.html#asado">Ver el gráfico</a>' in h
    assert re.search(r'<a href="/og/indices/asado.png\?v=[0-9a-f]{10}" '
                     r'download="carestia-asado.png">Descargar la tarjeta</a>', h)
    assert re.search(r'<img class="tarjeta" src="/og/indices/asado.png\?v=[0-9a-f]{10}" '
                     r'width="1200" height="630" alt="Índice Asado: ', h)
    assert "<li><span>Asado de tira <small>1 kg</small></span><b>$1.000</b></li>" in h
    assert 'aria-current="true">Índices</a>' in h


# ---------- 6. prensa ----------
def test_pagina_de_prensa(sitio):
    h = _leer(sitio, "prensa.html")
    assert "<h1>Prensa</h1>" in h
    assert "<strong>Fuente: Carestía (carestia.cl), con datos de ODEPA</strong>" in h
    assert '<a href="mailto:pedro@carestia.cl">pedro@carestia.cl</a>' in h
    assert "los viernes después de las 14:00" in h
    assert ("<p>Carestía publica información de consumo. No opina sobre tasas, "
            "mercados ni inversiones.</p>") in h
    assert "Fundador: Pedro Larraín." in h
    for code in BASKETS:
        assert f'href="https://carestia.cl/indices/{code}.html"' in h
    assert 'href="https://carestia.cl/og/portada.png" download="carestia-indices.png"' in h
    assert "captura PNG" in h
    # enlazada en el pie de todas las páginas, y en el sitemap
    for p in ["index.html", "graficos.html", "productos/tomate.html", "acerca.html"]:
        assert '<a href="https://carestia.cl/prensa.html">Prensa</a>' in _leer(sitio, p), p
    assert '<a href="https://carestia.cl/prensa.html" aria-current="page">Prensa</a>' in h
    locs = re.findall(r"<loc>([^<]+)</loc>", _leer(sitio, "sitemap.xml"))
    assert "https://carestia.cl/prensa.html" in locs
    assert all(f"https://carestia.cl/indices/{c}.html" in locs for c in BASKETS)


# ---------- publicación ----------
def test_workflow_publica_tarjetas_indices_y_prensa():
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"), encoding="utf-8") as fh:
        wf = fh.read()
    for linea in ["cp prensa.html public/prensa.html", "cp -r indices public/indices",
                  "cp -r og public/og", "pip install pandas numpy requests pillow"]:
        assert linea in wf, linea
    with open(os.path.join(RAIZ, ".github", "workflows", "tests.yml"), encoding="utf-8") as fh:
        assert "pillow" in fh.read()


def test_fuentes_de_las_tarjetas_con_su_licencia():
    for ttf in ["SpaceGrotesk-Bold.ttf", "IBMPlexSans-Regular.ttf", "IBMPlexSans-SemiBold.ttf",
                "IBMPlexMono-Medium.ttf"]:
        assert os.path.exists(os.path.join(RAIZ, "fuentes", ttf)), ttf
    for lic in ["OFL-SpaceGrotesk.txt", "OFL-IBMPlex.txt"]:
        with open(os.path.join(RAIZ, "fuentes", lic), encoding="utf-8") as fh:
            assert "SIL Open Font License" in fh.read(), lic

"""Portada en formato tabla y mudanza de la app a /graficos.html. Sin red:
build_site.py corre en un directorio temporal con un indices.json sintético
de valores controlados.

Verifica las tarjetas de índices (único lugar del semáforo), las listas de
"Esta semana" (solo productos con dato en la semana vigente), la tabla
estática (productos con dato en las últimas 4 semanas, cada fila un <a href>
a su ficha), la redirección de los links viejos de la app a /graficos.html,
el menú, el sitemap y el workflow de publicación."""
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
from indices import BASKETS  # noqa: E402

FIN = datetime.date(2026, 9, 21)   # lunes de la semana vigente
N = 120


def _t0(n: int, fin: datetime.date = FIN) -> str:
    return (fin - datetime.timedelta(weeks=n - 1)).isoformat()


def _serie(ultima: float, penultima: float, base: float = 1000) -> list:
    """N semanas planas en 'base' y las dos últimas a elección."""
    return [base] * (N - 2) + [penultima, ultima]


def sintetico() -> dict:
    out = {"generado": "2026-09-26", "indices": {}, "productos": {}, "descartes": []}
    colores = {"BARATO": "#5bbf7a", "NORMAL": "#e0a83c", "CARO": "#e0552f"}
    for k, (code, meta) in enumerate(BASKETS.items()):
        fechas = [(FIN - datetime.timedelta(weeks=59 - i)).isoformat() for i in range(60)]
        real = [{"time": t, "value": 10000 + 10 * i} for i, t in enumerate(fechas)]
        ver = ["CARO", "NORMAL", "BARATO", "NORMAL"][k]
        out["indices"][code] = {
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
            "fecha": "21-09-2026", "costo_nominal": real[-1]["value"],
            "costo_real": real[-1]["value"], "percentil": [88, 50, 12, 63][k],
            "zscore": 0.1, "vs_promedio": [14, 0, -5, 6][k], "veredicto": ver,
            "color": colores[ver], "n": len(real),
            "componentes": [{"label": lab, "qty": qty, "unidad": uni,
                             "odepa_unit": "$/kg", "factor": 1.0, "mismatch": False,
                             "precio_ult": 1000, "aporte": 1000}
                            for (lab, _m, qty, uni) in meta["items"]],
            "estacionalidad": {"factores": {str(m): 1.0 for m in range(1, 13)},
                               "mes_barato": 1, "mes_caro": 2, "amplitud": 1},
            "velas": [], "nominal": real, "real": real,
        }
    p = out["productos"]
    # subidas y bajadas de la última semana (en orden de magnitud)
    for i, pct in enumerate([30, 25, 20, 15, 10, 5]):
        p[f"sube_{i}"] = {"label": f"Sube {i}", "unidad": "kg", "grupo": "Hortalizas",
                          "t0": _t0(N), "v": _serie(1000 * (1 + pct / 100), 1000, 900)}
    for i, pct in enumerate([30, 25, 20, 15, 10, 5]):
        p[f"baja_{i}"] = {"label": f"Baja {i}", "unidad": "un", "grupo": "Frutas",
                          "t0": _t0(N), "v": _serie(1000 * (1 - pct / 100), 1000, 2000)}
    # sin cambio esta semana: flecha "="
    p["quieto"] = {"label": "Quieto", "unidad": "l", "grupo": "Otros",
                   "t0": _t0(N), "v": [1000] * N}
    # precio de hace 2 semanas: en la tabla (con su fecha), no en las listas
    p["atrasado"] = {"label": "Atrasado", "unidad": "kg", "grupo": "Frutas",
                     "t0": _t0(N, FIN - datetime.timedelta(weeks=2)),
                     "v": [500] * (N - 1) + [5000]}
    # último precio hace 6 semanas: fuera de la tabla
    p["viejo"] = {"label": "Viejo", "unidad": "kg", "grupo": "Frutas",
                  "t0": _t0(N, FIN - datetime.timedelta(weeks=6)), "v": [700] * N}
    # estacional: huecos en el último año (la sparkline se corta)
    v = [800 + (j % 7) for j in range(N)]
    for j in range(N - 30, N - 20):
        v[j] = None
    p["estacional"] = {"label": "Estacional", "unidad": "kg", "grupo": "Frutas",
                       "t0": _t0(N), "v": v}
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_portada")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(sintetico()), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _lista(h, lid):
    bloque = re.search(rf'id="{lid}">(.*?)</ul>', h, re.S).group(1)
    return re.findall(r'<b>([^<]+)</b>', bloque)


# ---------- Índices Carestía ----------
def test_tarjetas_de_indices_llevan_a_su_grafico(sitio):
    h = _leer(sitio, "index.html")
    tarjetas = re.findall(r'<a class="icard" href="([^"]+)">(.*?)</a>', h, re.S)
    assert [href for href, _ in tarjetas] == [f"/graficos.html#{c}" for c in BASKETS]
    asado = tarjetas[0][1]
    assert "ÍNDICE </span>ASADO" in asado
    assert 'style="background:var(--rojo)">CARO<' in asado
    assert ">percentil 88<" in asado and 'style="left:88%"' in asado
    assert "+14% sobre su promedio" in asado
    assert "+0% sobre su promedio" in tarjetas[1][1]
    assert "-5% bajo su promedio" in tarjetas[2][1]
    assert 'style="background:var(--verde)">BARATO<' in tarjetas[2][1]
    # cambio semanal con flecha neutra
    assert '<i class="f">▲</i> 0,1% esta semana' in asado


def test_cinta_con_links_a_cada_indice(sitio):
    h = _leer(sitio, "index.html")
    links = re.findall(r'<a class="titem" href="([^"]+)"', h)
    # dos vueltas para el desplazamiento continuo; la segunda, oculta
    assert links == [f"/graficos.html#{c}" for c in BASKETS] * 2
    assert h.count('aria-hidden="true" tabindex="-1"><span class="tn">') == len(BASKETS)


def test_semaforo_solo_en_los_indices(sitio):
    h = _leer(sitio, "index.html")
    productos = h[h.index('id="h-semana"'):h.index("</main>")]
    for token in ["--verde", "--ambar", "--rojo", "#5bbf7a", "#e0a83c", "#e0552f"]:
        assert token not in productos, token


# ---------- Esta semana ----------
def test_listas_de_esta_semana(sitio):
    h = _leer(sitio, "index.html")
    assert _lista(h, "sem-sub") == ["Sube 0", "Sube 1", "Sube 2", "Sube 3", "Sube 4"]
    assert _lista(h, "sem-baj") == ["Baja 0", "Baja 1", "Baja 2", "Baja 3", "Baja 4"]
    caros = _lista(h, "sem-car")
    assert len(caros) == 5
    # solo productos con dato en la semana vigente
    for lid in ["sem-sub", "sem-baj", "sem-car"]:
        assert "Atrasado" not in _lista(h, lid) and "Viejo" not in _lista(h, lid)
    # empate de percentil 100: primero el que más subió en un año
    assert caros[:3] == ["Sube 0", "Sube 1", "Sube 2"]
    assert '<i class="f">▲</i> 30,0%' in h and '<i class="f">▼</i> 30,0%' in h
    assert re.search(r'id="sem-car">.*?percentil 100</span>', h, re.S)


def test_listas_llevan_a_la_ficha(sitio):
    h = _leer(sitio, "index.html")
    bloque = h[h.index('id="sem-sub"'):h.index('id="h-productos"')]
    for href in re.findall(r'href="([^"]+)"', bloque):
        assert re.fullmatch(r"/productos/[a-z0-9-]+\.html", href), href
        assert (sitio / href.lstrip("/")).exists(), href


# ---------- Productos ----------
def test_tabla_estatica_con_las_ultimas_4_semanas(sitio):
    h = _leer(sitio, "index.html")
    filas = re.findall(r'<a class="fila" href="(/productos/[a-z0-9-]+\.html)"', h)
    nombres = re.findall(r'<span class="nm">([^<]+)</span>', h)
    # orden alfabético, sin el producto de hace 6 semanas
    assert "Viejo" not in nombres and "Atrasado" in nombres
    assert len(filas) == len(nombres) == 15
    assert nombres == sorted(nombres)
    for href in filas:
        assert (sitio / href.lstrip("/")).exists(), href
    # el precio de otra semana dice de cuándo es
    atrasado = re.search(r'<a class="fila" href="/productos/atrasado.html"[^>]*>.*?</a>', h).group(0)
    assert "<small>semana del 07-09</small>" in atrasado


def test_fila_con_sus_columnas_y_datos_para_ordenar(sitio):
    h = _leer(sitio, "index.html")
    fila = re.search(r'<a class="fila" href="/productos/sube-0.html"([^>]*)>(.*?)</a>', h)
    attrs, cuerpo = fila.group(1), fila.group(2)
    assert 'data-p="1300.0"' in attrs and 'data-w="30.0"' in attrs
    assert 'data-c="100"' in attrs and "data-y=" in attrs and "data-t=" in attrs
    assert '<span class="mg">Hortalizas, </span>por kilo' in cuerpo
    assert '<span class="mp">, percentil 100</span>' in cuerpo
    assert '<span class="c-p">$1.300</span>' in cuerpo
    assert '<span style="width:100%"></span>' in cuerpo            # barra neutra
    assert re.search(r'<svg class="sp" viewBox="0 0 51 100"[^>]*><path d="M0 \d+ 1 ', cuerpo)
    # sin cambio: flecha "="
    quieto = re.search(r'href="/productos/quieto.html".*?</a>', h).group(0)
    assert '<i class="f">=</i> 0,0%' in quieto
    # huecos en el último año: la línea se corta (más de un trazo)
    estacional = re.search(r'href="/productos/estacional.html".*?</a>', h).group(0)
    assert re.search(r'<path d="([^"]+)"', estacional).group(1).count("M") == 2


def test_chips_de_grupos_y_orden(sitio):
    h = _leer(sitio, "index.html")
    chips = re.findall(r'<button type="button" data-g="(\d*)" aria-pressed="\w+">([^<]+)</button>', h)
    assert chips == [("", "Todos"), ("0", "Frutas"), ("1", "Hortalizas"), ("2", "Otros")]
    for g, _ in chips[1:]:
        assert f'data-g="{g}" data-p=' in h
    for opcion in ["Alfabético", "Más subió esta semana", "Más bajó esta semana",
                   "Más caro frente a su historia", "Mayor alza en un año"]:
        assert f">{opcion}</option>" in h
    for col in ["Producto", "Precio hoy", "1 semana", "3 meses", "1 año",
                "Percentil en su historia"]:
        assert re.search(rf'data-k="\w" aria-pressed="\w+">{col} <span', h), col
    assert '<a class="ver-todos" href="/productos/">Ver todos los productos</a>' in h


# ---------- redirección de los links de la app ----------
def test_links_viejos_de_la_app_redirigen_a_graficos(sitio):
    h = _leer(sitio, "index.html")
    # el script va antes que todo lo demás del <head>
    assert h.index("location.replace('graficos.html'") < h.index("<title>")
    rx = re.compile(re.search(r"if \(/(.+?)/\.test\(location\.hash\)\)", h).group(1))
    for hash_ in ["#canasta", "#canasta=palta:0.5,marraqueta:0.1", "#comparar",
                  "#productos"] + [f"#{c}" for c in BASKETS]:
        assert rx.match(hash_), hash_
    for hash_ in ["", "#", "#otro", "#canastas", "#asado2", "#h-productos"]:
        assert not rx.match(hash_), hash_
    assert "location.search + location.hash" in h


def test_graficos_es_la_app(sitio):
    h = _leer(sitio, "graficos.html")
    assert '<link rel="canonical" href="https://carestia.cl/graficos.html">' in h
    assert "lightweight-charts" in h and "const DATA = " in h
    # #asado, #ensalada, #fruta y #desayuno abren ese índice
    assert "render(indiceDelHash() || CODES[0], true);" in h
    assert "const code = indiceDelHash();" in h
    # el wordmark vuelve a la portada
    assert '<a class="wordmark" href="https://carestia.cl/">' in h


# ---------- menú, fichas, sitemap y publicación ----------
def test_menu_apunta_a_graficos(sitio):
    for pagina in ["index.html", "graficos.html", "productos/sube-0.html",
                   "productos/index.html", "metodologia.html", "404.html"]:
        h = _leer(sitio, pagina)
        assert '<a href="https://carestia.cl/graficos.html" data-modo="indices"' in h, pagina
        assert '<a href="https://carestia.cl/graficos.html#comparar" data-modo="productos"' in h
        assert '<a href="https://carestia.cl/graficos.html#canasta" data-modo="canasta"' in h
        assert '<a href="https://carestia.cl/productos/"' in h
        assert '<a href="https://carestia.cl/metodologia.html"' in h
    # la portada no marca ninguna sección; /graficos.html marca Índices
    assert 'aria-current' not in re.search(r'<nav class="sitenav".*?</nav>',
                                           _leer(sitio, "index.html"), re.S).group(0)
    assert 'data-modo="indices" aria-current="page"' in _leer(sitio, "graficos.html")


def test_ficha_arma_la_canasta_en_graficos(sitio):
    h = _leer(sitio, "productos/sube-0.html")
    assert 'href="https://carestia.cl/graficos.html#canasta=sube_0:0.5"' in h


def test_sitemap_incluye_graficos_despues_de_las_fichas(sitio):
    locs = re.findall(r"<loc>([^<]+)</loc>", _leer(sitio, "sitemap.xml"))
    assert locs[0] == "https://carestia.cl/"
    assert "https://carestia.cl/graficos.html" in locs
    # salud.yml chequea la primera URL con /productos/: sigue siendo una ficha
    primera = next(l for l in locs if "/productos/" in l)
    assert primera.endswith(".html") and primera != "https://carestia.cl/productos/"
    assert locs.index("https://carestia.cl/graficos.html") > locs.index(primera)


def test_referencia_de_diseno_fuera_del_sitio_publicado():
    assert os.path.exists(os.path.join(RAIZ, "diseno", "diseno_referencia.html"))
    assert not os.path.exists(os.path.join(RAIZ, "Carestía · Rediseño.html"))
    assert not os.path.exists(os.path.join(RAIZ, "diseno_referencia.html"))
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        wf = fh.read()
    assert "cp graficos.html public/graficos.html" in wf
    assert "diseno" not in wf and "design" not in wf
    # nada se copia por comodín: solo archivos y carpetas nombrados
    assert not re.search(r"cp\s+(-r\s+)?(\.|\*|\./\*)\s", wf)

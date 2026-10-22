"""/compras.html, para áreas de compras de alimentos. Sin red: build_site.py
corre en un directorio temporal con el indices.json sintético de
test_texto.py, más algunos de los insumos de la página (con las claves de
indices.json) en los casos que importan: con precio esta semana, con el
último precio de hace 2 semanas (va, con su semana) o de hace 6 (no va), sin
el cambio de 4 semanas, sin cambio y con veredicto por temporada.

Verifica el canonical, el title y la description, el texto del dueño
(textos/compras.md, literal) en su orden alrededor de la tabla, que cada
fila tenga las cifras de la ficha de su producto y su link, los colores de la regla de
CLAUDE.md sin semáforo, la tabla que se apila en el celular, el link "Para
compras" en el pie de todas las páginas, el sitemap y el workflow, y la
guardia de texto."""
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
from test_texto import indices_sintetico, infracciones  # noqa: E402

FIN = datetime.date(2026, 9, 21)   # lunes de la semana vigente del sintético
URL = "https://carestia.cl/compras.html"
LINK_PIE = '<a href="https://carestia.cl/compras.html">Para compras</a>'


def _producto(label: str, unidad: str, grupo: str, v: list, atraso: int = 0) -> dict:
    """Una serie semanal 'v' que termina 'atraso' semanas antes de FIN."""
    fin = FIN - datetime.timedelta(weeks=atraso)
    return {"label": label, "unidad": unidad, "grupo": grupo,
            "t0": (fin - datetime.timedelta(weeks=len(v) - 1)).isoformat(), "v": v}


def sintetico() -> dict:
    out = indices_sintetico()
    p = out["productos"]
    # Proteínas: sube y baja en 4 semanas, uno de hace 2 semanas (va, con su
    # semana) y uno de hace 6 (no va)
    p["posta_paleta"] = _producto("Posta Paleta", "kg", "Carne bovina",
                                  [1000] * 56 + [1100] * 4)
    p["pollo_trutro_entero"] = _producto("Pollo Trutro Entero", "kg",
                                         "Carne de Cerdo - Ave - Cordero", [1000] * 56 + [900] * 4)
    p["huevos"] = _producto("Huevos", "un", "Lácteos - Huevos - Margarinas",
                            [100] * 56 + [110] * 4, atraso=2)
    p["cerdo_pulpa_s/hueso"] = _producto("Cerdo Pulpa s/hueso", "kg",
                                         "Carne de Cerdo - Ave - Cordero", [5000] * 60, atraso=6)
    # Abarrotes: sin cambio y sin las 8 semanas del cambio de 4 semanas; el
    # resto del bloque no está en indices.json
    p["spaghetti_n°5"] = _producto("Spaghetti N°5", "kg", "Abarrotes y otros", [2000] * 60)
    p["lentejas_6_mm"] = _producto("Lentejas 6 mm", "kg", "Abarrotes y otros", [3000] * 6)
    # Verduras: solo el tomate, de hace 10 semanas: el bloque no va
    p["tomate"] = _producto("Tomate", "kg", "Hortalizas", [1500] * 60, atraso=10)
    # Pan y lácteos: la marraqueta con 13 años de historia (veredicto por
    # temporada) y la leche por litro
    p["marraqueta"] = _producto("Marraqueta", "kg", "Pan", [2000] * (52 * 13 - 1) + [2500])
    p["leche_entera"] = _producto("Leche entera", "l", "Lácteos - Huevos - Margarinas",
                                  [800] * 56 + [840] * 4)
    return out


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_compras")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(sintetico(), ensure_ascii=False),
                                    encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0", CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d, r.stdout


@pytest.fixture(scope="module")
def sitio(build):
    return build[0]


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _main(h):
    return h[h.index("<main"):h.index("</main>")]


FILA = re.compile(r'<tr><th class="ins-n" scope="row"><a href="https://carestia\.cl/productos/'
                  r'([^"]+)\.html">([^<]+)</a></th><td class="ins-p">(.*?)</td>'
                  r'<td class="ins-4">(.*?)</td><td class="ins-f">(.*?)</td></tr>')


def _filas(sitio) -> dict:
    """{slug: (nombre, precio, 4 semanas, frase)}, en el orden de la tabla."""
    return {s: resto for s, *resto in FILA.findall(_leer(sitio, "compras.html"))}


def _visible(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", h))


# ---------- la página ----------
def test_canonical_title_y_description(sitio):
    h = _leer(sitio, "compras.html")
    assert f'<link rel="canonical" href="{URL}">' in h
    assert "<title>Precios de alimentos para áreas de compras | Carestía</title>" in h
    desc = ("Los insumos de una minuta con su precio de esta semana en Santiago, ajustado por "
            "inflación, y cómo está frente al mismo mes de los últimos 10 años. Datos de ODEPA, "
            "cada viernes.")
    assert f'<meta name="description" content="{desc}">' in h
    assert f'<meta property="og:description" content="{desc}">' in h
    assert '<main class="doc compras">' in h


def test_texto_del_dueno_en_orden(sitio):
    m = _main(_leer(sitio, "compras.html"))
    partes = [
        "<h1>Para compras de alimentación</h1>",
        "<p>Los insumos de una minuta, con su precio de esta semana en Santiago, el cambio de las "
        "últimas 4 semanas y cómo está frente al mismo mes de los últimos 10 años. Los precios son "
        "de ODEPA, van ajustados por inflación y se actualizan solos cada viernes.</p>",
        # la línea de la semana de la portada (con CARESTIA_AHORA el viernes 25-09)
        '<p class="meta">Precios de la semana del 21 de septiembre de 2026, publicados por ODEPA '
        "el viernes 25 de septiembre. Próxima actualización: viernes 2 de octubre en la tarde.</p>",
        '<h2 id="h-semana">Esta semana</h2>',
        '<table class="insumos" aria-labelledby="h-semana">',
        '<p class="ins-nota">Precios al consumidor ODEPA, Región Metropolitana, ajustados por '
        "inflación, en pesos de agosto de 2026.</p>",
        "<h2>Para un área de compras</h2>",
        "<p>Esto es lo público. Con áreas de compras queremos construir tres cosas:</p>",
        "<li>El costo semanal de su propia minuta, con sus recetas y gramajes.</li>",
        "<li>Un aviso cuando un insumo que usan entra en zona cara para la época.</li>",
        "<li>El precio de los mercados mayoristas de Santiago al lado del precio al consumidor, "
        "para negociar con proveedores.</li>",
        "<p>¿Lleva las compras de alimentos de un casino, un colegio, una clínica o un hotel? "
        'Conversemos 30 minutos: <a href="mailto:contacto@carestia.cl">contacto@carestia.cl</a></p>',
    ]
    pos = [m.index(p) for p in partes]
    assert pos == sorted(pos)
    # el deslinde va solo en metodología; la atribución ODEPA, en el pie
    assert "No constituye asesoría" not in m and "CC-BY" not in m


def test_el_texto_sale_literal_de_textos_compras_md(sitio):
    """El texto del dueño va en textos/compras.md, palabra por palabra:
    build_site.py solo le da formato."""
    with open(os.path.join(RAIZ, "textos", "compras.md"), encoding="utf-8") as fh:
        md = fh.read()
    texto = " ".join(_visible(_main(_leer(sitio, "compras.html"))).split())
    lineas = [l.strip() for l in md.splitlines() if l.strip()]
    assert len(lineas) == 7
    for linea in lineas:
        plano = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", linea.lstrip("#- ").strip())
        assert plano in texto, linea[:40]


def test_fuera_del_menu_principal(sitio):
    h = _leer(sitio, "compras.html")
    nav = h[h.index('<nav class="sitenav"'):h.index("</nav>", h.index('<nav class="sitenav"'))]
    assert "compras" not in nav and "aria-current" not in nav
    for p in ["index.html", "graficos.html", "metodologia.html"]:
        h = _leer(sitio, p)
        cab = h[:h.index("</header>")]
        assert "compras.html" not in cab, p


# ---------- la tabla ----------
def test_productos_de_la_lista_con_link_a_su_ficha(sitio):
    filas = _filas(sitio)
    # en el orden de los bloques; sin precio en las últimas 4 semanas no van
    # (la pulpa de cerdo, de hace 6, y el tomate, de hace 10), ni lo que no
    # está en la lista
    assert list(filas) == ["posta-paleta", "pollo-trutro-entero", "huevos", "spaghetti-n5",
                           "lentejas-6-mm", "marraqueta", "leche-entera"]
    m = _main(_leer(sitio, "compras.html"))
    for fuera in ["Pulpa de cerdo sin hueso", "Tomate", "Producto 0", "Chirimoya"]:
        assert fuera not in m, fuera
    for slug, (nombre, *_r) in filas.items():
        ficha = _leer(sitio, f"productos/{slug}.html")
        # el nombre como lo muestra la ficha
        assert f"<h1>{nombre}</h1>" in ficha, slug
    assert filas["spaghetti-n5"][0] == "Espagueti n.º 5"
    assert filas["pollo-trutro-entero"][0] == "Trutro entero de pollo"


def test_bloques_con_su_subtitulo(sitio):
    h = _leer(sitio, "compras.html")
    grupos = re.findall(r'<tr class="ins-g"><th colspan="4" scope="rowgroup">([^<]+)</th></tr>', h)
    # sin filas, el bloque no va
    assert grupos == ["Proteínas", "Abarrotes", "Pan y lácteos"]
    assert h.count("<tbody>") == 3
    assert ('<thead><tr><th scope="col">Insumo</th><th class="ins-p" scope="col">Precio esta '
            'semana</th><th class="ins-4" scope="col">4 semanas</th><th scope="col">Frente al '
            'mismo mes</th></tr></thead>') in h


def test_lo_que_queda_fuera_se_avisa_en_la_consola(build):
    _d, consola = build
    aviso = next(l for l in consola.splitlines() if l.startswith("AVISO compras.html"))
    for clave in ["cerdo_pulpa_s/hueso (último precio: 10-08-2026)",
                  "tomate (último precio: 13-07-2026)", "azucar (sin ficha)"]:
        assert clave in aviso, clave


def test_precio_y_frase_como_la_ficha(sitio):
    filas = _filas(sitio)
    for slug in ["posta-paleta", "pollo-trutro-entero", "spaghetti-n5", "lentejas-6-mm",
                 "marraqueta", "leche-entera"]:
        _n, precio, _c, frase = filas[slug]
        ficha = _leer(sitio, f"productos/{slug}.html")
        op = re.search(r'<div class="oprice">(.*?)</div>', ficha).group(1)
        ou = re.search(r'<div class="ouni">(.*?)</div>', ficha).group(1)
        assert precio == f"{op} <small>{ou}</small>", slug
        # la frase de la ficha y de su tarjeta (og:image:alt)
        alt = re.search(r'<meta property="og:image:alt" content="([^"]*)">', ficha).group(1)
        assert alt.endswith(f". {frase}"), slug
    assert filas["leche-entera"][1] == "$840 <small>por litro</small>"
    assert filas["posta-paleta"][3] == ("Más cara que en 9 de cada 10 semanas desde 2025, "
                                        "descontada la inflación.")
    # con 13 años de historia, la frase de temporada, igual que en la ficha
    frase = "Más cara que en 10 de los últimos 10 septiembres, aun descontando la inflación."
    assert filas["marraqueta"][3] == frase
    assert f'<p class="pct">{frase}</p>' in _leer(sitio, "productos/marraqueta.html")


def test_precio_de_otra_semana_con_su_semana(sitio):
    """Los huevos tienen su último precio hace 2 semanas: va el último dato
    de la ficha (ultimo_dato) con su semana, nunca como si fuera de esta."""
    _n, precio, cuatro, frase = _filas(sitio)["huevos"]
    assert precio == '$110 <small>por unidad</small><small class="ins-sem">semana del 07-09-2026</small>'
    ficha = _leer(sitio, "productos/huevos.html")
    assert "Último dato: $110, semana del 07-09-2026." in ficha
    assert '<i class="f">▲</i><span class="v-sube">10,0%</span>' == cuatro
    assert frase == "Más caros que en 9 de cada 10 semanas desde 2025, descontada la inflación."


def test_cuatro_semanas_con_los_colores_de_la_regla(sitio):
    filas = _filas(sitio)
    assert filas["posta-paleta"][2] == '<i class="f">▲</i><span class="v-sube">10,0%</span>'
    assert filas["pollo-trutro-entero"][2] == '<i class="f">▼</i><span class="v-baja">10,0%</span>'
    # sin cambio, en el color del texto; sin dato, vacío
    assert filas["spaghetti-n5"][2] == '<i class="f">▲</i>0,0%'
    assert filas["lentejas-6-mm"][2] == ""
    # el mismo HTML que el cambio de 4 semanas de la ficha
    for slug in ["posta-paleta", "pollo-trutro-entero", "spaghetti-n5", "marraqueta",
                 "leche-entera"]:
        ficha = _leer(sitio, f"productos/{slug}.html")
        odelta = re.search(r'<div class="odelta">(.*?) <small>4 semanas</small></div>', ficha)
        assert odelta.group(1) == filas[slug][2], slug
    assert '<small>4 semanas</small>' not in _leer(sitio, "productos/lentejas-6-mm.html")


def test_ninguna_fila_con_el_semaforo(sitio):
    """El semáforo CARO/NORMAL/BARATO es solo de los 4 índices."""
    h = _leer(sitio, "compras.html")
    tabla = h[h.index('<table class="insumos"'):h.index("</table>")]
    for semaforo in ["ic-pill", "ind-pill", "var(--verde)", "var(--ambar)", "var(--rojo)",
                     "CARO", "NORMAL", "BARATO", "zonas", "style="]:
        assert semaforo not in tabla, semaforo
    clases = set(re.findall(r'class="([^"]+)"', tabla))
    assert clases <= {"insumos", "ins-g", "ins-n", "ins-p", "ins-4", "ins-f", "ins-sem",
                      "f", "v-sube", "v-baja"}, clases


def test_en_el_celular_cada_fila_se_apila(sitio):
    """Hasta 760px (como la tabla de la portada) la tabla deja de serlo: la
    cabecera no va y cada fila es una grilla con el nombre arriba y el precio,
    el cambio de 4 semanas (con su etiqueta) y la frase abajo. El CSS va solo
    en esta página."""
    h = _leer(sitio, "compras.html")
    movil = h[h.index("@media (max-width:760px) {\n    .insumos"):]
    movil = movil[:movil.index("\n  }\n")]
    for regla in [".insumos, .insumos tbody, .insumos tr, .insumos th, .insumos td { display:block; }",
                  ".insumos thead { display:none; }",
                  ".insumos tbody tr:not(.ins-g) { display:grid;",
                  ".ins-n, .ins-f { grid-column:1 / -1; width:auto; }",
                  '.ins-4:not(:empty)::after { content:" 4 semanas";']:
        assert regla in movil, regla
    # con los tokens de color que ya existen
    assert "var(--line)" in h and "#" not in movil
    for p in ["index.html", "metodologia.html", "prensa.html", "productos/index.html",
              "productos/posta-paleta.html", "indices/asado.html"]:
        assert ".insumos" not in _leer(sitio, p), p


# ---------- pie, sitemap y publicación ----------
def _todas(sitio):
    return sorted(glob.glob(str(sitio / "*.html")) + glob.glob(str(sitio / "productos" / "*.html"))
                  + glob.glob(str(sitio / "indices" / "*.html")))


def test_pie_de_todas_las_paginas_con_para_compras(sitio):
    paginas = _todas(sitio)
    assert len(paginas) > 30
    for p in paginas:
        h = _leer(sitio, os.path.relpath(p, sitio))
        pie = h[h.index('<footer class="sitefoot">'):h.index("</footer>")]
        # después de Prensa
        assert re.search(r'>Prensa</a></li>\s*<li><a href="https://carestia\.cl/compras\.html"'
                         r'( aria-current="page")?>Para compras</a></li>', pie), p
    assert ('<a href="https://carestia.cl/compras.html" aria-current="page">Para compras</a>'
            in _leer(sitio, "compras.html"))
    assert LINK_PIE in _leer(sitio, "index.html")


def test_sitemap_y_workflow(sitio):
    locs = re.findall(r"<loc>([^<]+)</loc>", _leer(sitio, "sitemap.xml"))
    assert locs.count(URL) == 1
    assert locs.index("https://carestia.cl/prensa.html") < locs.index(URL)
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        assert "cp compras.html public/compras.html" in fh.read()


def test_sin_rayas_ni_muletillas(sitio):
    h = _leer(sitio, "compras.html")
    assert infracciones(h) == []
    assert infracciones(_visible(_main(h))) == []

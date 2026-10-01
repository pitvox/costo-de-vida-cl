"""TradingView paso A: librería, datafeed y página de prueba. Sin red: el
build corre en un directorio temporal con el indices.json sintético de
test_datos.py (el tamaño del real).

Verifica que el workflow descargue la librería solo al publicar (fuera del
árbol del repo, sin cortar el build si falla y con un job final que avisa),
que la librería nunca entre al repo, robots.txt, la página oculta
/prueba-graficos.html (noindex, fuera del menú y del sitemap, respaldo con
Lightweight Charts), la atribución a TradingView en el pie de las páginas con
gráficos, los textos del dueño y el datafeed (tests/feed_node.js, si hay
Node). Con CARESTIA_INDICES_REAL=ruta/a/indices.json, el datafeed se prueba
además con los datos reales (curl -O https://carestia.cl/indices.json)."""
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

TV = "https://www.tradingview.com/"
NODE = shutil.which("node")


def _build(d, data):
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build_tv"), indices_realista())


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _wf():
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        return fh.read()


def _paso(wf, nombre):
    """El bloque de un paso del workflow, desde su '- name:' hasta el siguiente."""
    m = re.search(rf"\n      - name: {re.escape(nombre)}\n(.*?)(?=\n      - name: |\n  \w|\Z)",
                  wf, re.S)
    assert m, nombre
    return m.group(1)


# ---------- workflow: la librería se descarga solo al publicar ----------
def test_workflow_clona_la_libreria_despues_del_checkout():
    wf = _wf()
    pasos = re.findall(r"\n      - name: (.+)", wf)
    assert pasos[:2] == ["Clonar repo", "Librería TradingView"]
    paso = _paso(wf, "Librería TradingView")
    assert "TV_LIBRARY_TOKEN: ${{ secrets.TV_LIBRARY_TOKEN }}" in paso
    assert "https://github.com/tradingview/charting_library.git" in paso
    # la última versión estable: el tag vX.Y.Z más alto (sin -beta ni -rc),
    # salvo que la variable del repo fije otro
    assert "git ls-remote --tags --refs" in paso
    assert r"grep -E '^v?[0-9]+(\.[0-9]+)*$' | sort -V | tail -n 1" in paso
    assert 'git clone --quiet --depth 1 --branch "$tag"' in paso
    # fuera del árbol del repo; a public/ (ruta absoluta) va solo charting_library/
    assert 'DEST="$RUNNER_TEMP/tv"' in paso
    assert 'PUBLIC="$GITHUB_WORKSPACE/public"' in paso
    assert re.findall(r"cp -r (\S+) (\S+)", paso) == \
        [('"$DEST/charting_library"', '"$PUBLIC/charting_library"')]
    # el token nunca en la URL
    assert "x-access-token:%s" in paso and "@github.com" not in paso


def test_workflow_manda_un_solo_encabezado_de_autorizacion():
    """Si git lee la configuración del checkout, al encabezado del
    TV_LIBRARY_TOKEN se suma el del GITHUB_TOKEN y GitHub responde 400
    ("Duplicate header: Authorization"). El checkout no persiste credenciales
    y git corre desde RUNNER_TEMP, fuera del árbol."""
    wf = _wf()
    assert re.search(r"uses: actions/checkout@\S+\n\s+with:\n\s+persist-credentials: false\n",
                     _paso(wf, "Clonar repo"))
    paso = _paso(wf, "Librería TradingView")
    cd = paso.index('cd "$RUNNER_TEMP"')
    assert cd < paso.index("git ls-remote") and cd < paso.index("git clone")
    assert "GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null" in paso
    # nada relativo al checkout después del cd
    assert not re.search(r"(?<![$/\w])public/", paso[cd:].replace(
        'echo "Librería TradingView $tag en public/charting_library/"', ""))


def test_workflow_sigue_sin_la_libreria_y_avisa_despues_del_deploy():
    wf = _wf()
    paso = _paso(wf, "Librería TradingView")
    assert "set -e" not in paso and "continue-on-error" not in paso
    falla = re.search(r"fallar\(\) \{(.*?)\n          \}", paso, re.S).group(1)
    assert 'echo "libreria=falla" >> "$GITHUB_OUTPUT"' in falla
    assert 'rm -rf "$DEST" "$PUBLIC/charting_library"' in falla
    assert "exit 0" in falla
    assert "libreria: ${{ steps.tv.outputs.libreria }}" in wf
    aviso = wf[wf.index("\n  aviso-libreria:"):]
    assert "needs: [build, deploy]" in aviso
    assert "if: ${{ !cancelled() && needs.build.outputs.libreria == 'falla' }}" in aviso
    assert 'echo "::error::No se pudo descargar la librería de TradingView"' in aviso
    assert aviso.rstrip().endswith("exit 1")


def test_workflow_publica_la_pagina_de_prueba_y_el_datafeed():
    generar = _paso(_wf(), "Generar sitio")
    for archivo in ["prueba-graficos.html", "carestia-tv.js", "carestia-tv.css"]:
        assert f"cp {archivo} public/{archivo}" in generar
    # nunca se commitea nada desde el workflow
    assert not re.search(r"git (add|commit|push)", _wf())


def test_workflows_con_runner_fijo():
    """ubuntu-latest cambia de imagen sin aviso en el repo; cada job fija la suya."""
    carpeta = os.path.join(RAIZ, ".github", "workflows")
    for nombre in sorted(os.listdir(carpeta)):
        with open(os.path.join(carpeta, nombre), encoding="utf-8") as fh:
            wf = fh.read()
        runners = re.findall(r"runs-on: (\S+)", wf)
        assert runners and set(runners) == {"ubuntu-24.04"}, (nombre, runners)


# ---------- la librería nunca entra al repo ----------
def test_gitignore_y_guardia_intactos():
    with open(os.path.join(RAIZ, ".gitignore"), encoding="utf-8") as fh:
        gi = fh.read()
    for linea in ["charting_library/", "datafeeds/", "**/charting_library*", "**/datafeeds*"]:
        assert linea in gi.splitlines()
    with open(os.path.join(RAIZ, ".github", "workflows", "guardia-tradingview.yml"),
              encoding="utf-8") as fh:
        guardia = fh.read()
    assert "(charting_library|datafeeds)[^/]*(/|$)|(^|/)bundles/" in guardia
    assert "TradingView Charting Library" in guardia


def test_ningun_archivo_versionado_parece_la_libreria():
    """La misma revisión que la guardia, sobre el árbol local."""
    r = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True)
    if r.returncode != 0:
        pytest.skip("sin git")
    archivos = [f for f in r.stdout.decode("utf-8").split("\0") if f]
    rx = re.compile(r"(^|/)(charting_library|datafeeds)[^/]*(/|$)|(^|/)bundles/", re.I)
    assert [f for f in archivos if rx.search(f)] == []
    for f in archivos:
        ruta = os.path.join(RAIZ, f)
        if os.path.isfile(ruta):
            with open(ruta, "rb") as fh:
                cabeza = b"".join(fh.readline() for _ in range(5))
            assert b"tradingview charting library" not in cabeza.lower(), f


# ---------- robots, sitemap y menú ----------
def test_robots_excluye_la_libreria(sitio):
    robots = _leer(sitio, "robots.txt")
    assert "Disallow: /charting_library/" in robots.splitlines()
    assert "Allow: /" in robots.splitlines()


def test_pagina_de_prueba_oculta(sitio):
    h = _leer(sitio, "prueba-graficos.html")
    assert '<meta name="robots" content="noindex, nofollow">' in h
    assert 'rel="canonical"' not in h
    assert "prueba-graficos" not in _leer(sitio, "sitemap.xml")
    for pagina in ["index.html", "graficos.html", "productos/index.html",
                   "productos/producto-000.html", "metodologia.html", "404.html"]:
        assert "prueba-graficos" not in _leer(sitio, pagina), pagina
    # la navegación común, sin marcar ninguna sección
    nav = re.search(r'<nav class="sitenav".*?</nav>', h, re.S).group(0)
    assert "aria-current" not in nav


def test_pagina_de_prueba_advanced_charts_con_respaldo(sitio):
    h = _leer(sitio, "prueba-graficos.html")
    # Índice Asado, la librería desde /charting_library/ y 8 segundos de plazo
    assert "const SIMBOLO = 'asado';" in h
    assert "const LIBRERIA = '/charting_library/';" in h
    assert "cargarScript(LIBRERIA + 'charting_library.standalone.js').then(iniciar, () => respaldo('falta'));" in h
    assert "const ESPERA = 8000;" in h
    assert "setTimeout(() => respaldo('tarde'), ESPERA)" in h
    # el respaldo usa el mismo Lightweight Charts que /graficos.html
    lw = re.search(r'https://unpkg\.com/lightweight-charts@[^"\']+', _leer(sitio, "graficos.html")).group(0)
    assert f"const LIGHTWEIGHT = '{lw}';" in h
    # datafeed: los índices del build y la misma versión de datos/
    app = json.loads(re.search(r"const DATA = (\{.*?\});\n", _leer(sitio, "graficos.html"))
                     .group(1).replace("<\\/", "</"))
    assert f"const VER = '{app['ver']}';" in h
    indices = json.loads(re.search(r"const INDICES = (\[.*?\]);\n", h).group(1))
    assert indices == [{"codigo": c, "nombre": d["nombre"]} for c, d in app["indices"].items()]
    assert re.search(r'<script src="/carestia-tv\.js\?v=[0-9a-f]{10}"></script>', h)
    assert "css: location.origin + '/carestia-tv.css?v=" in h
    # sin la librería no se carga nada de TradingView desde otro sitio
    assert "tradingview.com/charting_library" not in h and "charting_library.esm" not in h


# ---------- atribución ----------
def _links_tv(h):
    return re.findall(r'<a\b[^>]*href="https://www\.tradingview\.com/"[^>]*>[^<]*</a>', h)


def test_atribucion_en_las_paginas_con_graficos(sitio):
    for pagina in ["prueba-graficos.html", "graficos.html", "productos/producto-000.html"]:
        h = _leer(sitio, pagina)
        pie = h[h.index('<footer class="sitefoot">'):h.index("</footer>")]
        assert f'<p class="pie-tv"><a href="{TV}">Gráficos de TradingView</a></p>' in pie, pagina
        # el aviso de Lightweight Charts sigue
        assert ("TradingView Lightweight Charts™. Copyright (c) 2023 TradingView, Inc."
                in pie), pagina
    for pagina in ["index.html", "metodologia.html", "acerca.html"]:
        assert "Gráficos de TradingView" not in _leer(sitio, pagina), pagina


def test_links_a_tradingview_sin_rel(sitio):
    for pagina in ["prueba-graficos.html", "graficos.html", "productos/producto-000.html",
                   "acerca.html", "index.html"]:
        links = _links_tv(_leer(sitio, pagina))
        assert links, pagina
        for a in links:
            assert " rel=" not in a, (pagina, a)


# ---------- textos del dueño ----------
def test_textos_del_dueno(sitio):
    acerca = _leer(sitio, "acerca.html")
    frase = ('<p>Los gráficos usan la librería Advanced Charts de '
             f'<a href="{TV}">TradingView</a>.</p>')
    assert frase in acerca
    assert acerca.index(frase) < acerca.index("<p>Contacto: ")
    priv = _leer(sitio, "privacidad.html")
    p33 = re.search(r'<p class="sub">3\.3\. (.*?)</p>', priv).group(1)
    assert p33.endswith("La librería de gráficos se aloja en este sitio y puede guardar "
                        "en tu navegador tus preferencias de visualización y tus "
                        "dibujos; no se envían a Carestía.")


# ---------- tema ----------
def test_tema_del_iframe_con_los_tokens(sitio):
    css = _leer(sitio, "carestia-tv.css")
    assert css.startswith("/* Tema de Carestía para Advanced Charts")
    assert ('@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600'
            '&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@700'
            '&display=swap");') in css
    for var, valor in [("platform-background", "#0f0f0e"), ("pane-background", "#0f0f0e"),
                       ("popup-background", "#171716"), ("toolbar-divider-background", "#2b2a27"),
                       ("popup-element-text", "#e4dacc"), ("toolbar-button-text", "#a39e95")]:
        assert f"--tv-color-{var}: {valor};" in css, var


def test_pagina_de_prueba_lee_los_colores_de_los_tokens(sitio):
    h = _leer(sitio, "prueba-graficos.html")
    assert h.count(":root {") == 1
    # la brasa y el semáforo, solo en sus tokens
    for color in ["#e8743b", "#5bbf7a", "#e0552f", "#e4dacc"]:
        assert h.count(color) == 1, color
    js = _leer(sitio, "carestia-tv.js")
    for color in ["#e8743b", "#5bbf7a", "#e0552f", "#e4dacc", "#0f0f0e"]:
        assert color not in js, color


# ---------- datafeed ----------
def _feed_node(d):
    if not NODE:
        pytest.skip("sin Node.js")
    r = subprocess.run([NODE, os.path.join(RAIZ, "tests", "feed_node.js"), str(d)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_datafeed_con_datos_sinteticos(sitio):
    assert "chequeos OK" in _feed_node(sitio)


@pytest.mark.skipif(not os.environ.get("CARESTIA_INDICES_REAL"),
                    reason="sin CARESTIA_INDICES_REAL (indices.json real de carestia.cl)")
def test_datafeed_con_datos_reales(tmp_path):
    with open(os.environ["CARESTIA_INDICES_REAL"], encoding="utf-8") as fh:
        data = json.load(fh)
    salida = _feed_node(_build(tmp_path, data))
    print(salida)
    assert "chequeos OK" in salida

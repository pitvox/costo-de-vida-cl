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
import base64
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading

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
    assert 'git -C "$RUNNER_TEMP" ls-remote --tags --refs "$REPO"' in paso
    assert r"grep -E '^v?[0-9]+(\.[0-9]+)*$' | sort -V | tail -n 1" in paso
    assert 'git -C "$RUNNER_TEMP" clone --quiet --depth 1 --branch "$tag"' in paso
    # git corre fuera del repo: dentro, el encabezado del checkout se suma al
    # de la librería y GitHub responde 400 (primer deploy, 01-10-2026)
    comandos = "\n".join(l for l in paso.splitlines() if not l.strip().startswith("#"))
    assert re.findall(r"\bgit (?!-C \"\$RUNNER_TEMP\")\S+", comandos) == []
    assert len(re.findall(r'\bgit -C "\$RUNNER_TEMP"', comandos)) == 2
    assert 'export GIT_CEILING_DIRECTORIES="$(dirname "$RUNNER_TEMP")"' in paso
    # fuera del árbol del repo; a public/ va solo charting_library/
    assert 'DEST="$RUNNER_TEMP/tv"' in paso
    assert re.findall(r"cp -r (\S+) (\S+)", paso) == \
        [('"$DEST/charting_library"', "public/charting_library")]
    # el token nunca en la URL
    assert "x-access-token:%s" in paso and "@github.com" not in paso


def test_workflow_sigue_sin_la_libreria_y_avisa_despues_del_deploy():
    wf = _wf()
    paso = _paso(wf, "Librería TradingView")
    assert "set -e" not in paso and "continue-on-error" not in paso
    falla = re.search(r"fallar\(\) \{(.*?)\n          \}", paso, re.S).group(1)
    assert 'echo "libreria=falla" >> "$GITHUB_OUTPUT"' in falla
    assert "rm -rf" in falla and "public/charting_library" in falla
    assert "exit 0" in falla
    assert "libreria: ${{ steps.tv.outputs.libreria }}" in wf
    aviso = wf[wf.index("\n  aviso-libreria:"):]
    assert "needs: [build, deploy]" in aviso
    assert "if: ${{ !cancelled() && needs.build.outputs.libreria == 'falla' }}" in aviso
    assert 'echo "::error::No se pudo descargar la librería de TradingView"' in aviso
    assert aviso.rstrip().endswith("exit 1")


class _ServidorGit(http.server.BaseHTTPRequestHandler):
    """git smart-HTTP (git http-backend) que, como GitHub, responde 400 si
    llegan dos Authorization y 401 si falta o no es el esperado."""
    raiz = esperado = None
    pedidos = []

    def _servir(self):
        auths = self.headers.get_all("Authorization") or []
        self.pedidos.append(auths)
        if len(auths) > 1 or auths != [self.esperado]:
            self.send_response(400 if len(auths) > 1 else 401)
            if not auths:
                self.send_header("WWW-Authenticate", 'Basic realm="git"')
            self.end_headers()
            return
        ruta, _, qs = self.path.partition("?")
        cuerpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        env = dict(os.environ, GIT_PROJECT_ROOT=self.raiz, GIT_HTTP_EXPORT_ALL="1",
                   PATH_INFO=ruta, QUERY_STRING=qs, REQUEST_METHOD=self.command,
                   CONTENT_TYPE=self.headers.get("Content-Type", ""),
                   CONTENT_LENGTH=str(len(cuerpo)), REMOTE_ADDR="127.0.0.1")
        out = subprocess.run(["git", "http-backend"], input=cuerpo, env=env,
                             capture_output=True).stdout
        cab, _, resto = out.partition(b"\r\n\r\n")
        estado, campos = 200, []
        for linea in cab.decode().split("\r\n"):
            k, _, v = linea.partition(":")
            if k.lower() == "status":
                estado = int(v.split()[0])
            elif k:
                campos.append((k, v.strip()))
        self.send_response(estado)
        for k, v in campos:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resto)))
        self.end_headers()
        self.wfile.write(resto)

    do_GET = do_POST = _servir

    def log_message(self, *a):
        pass


def _correr_paso_libreria(tmp_path, token, tag=""):
    """El paso "Librería TradingView" tal cual, contra un repo git local con
    tags de versión, corriendo desde un workspace con el encabezado que deja
    actions/checkout (includeIf a un archivo de credenciales). Devuelve
    (salida del paso, $GITHUB_OUTPUT, workspace, Authorization por pedido)."""
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("sin git o bash")
    git = lambda *a, **k: subprocess.run(["git", *a], check=True, capture_output=True, **k)
    src = tmp_path / "src"
    (src / "charting_library" / "bundles").mkdir(parents=True)
    (src / "datafeeds").mkdir()
    (src / "datafeeds" / "udf.js").write_text("x")
    (src / "index.html").write_text("x")
    (src / "charting_library" / "bundles" / "a.js").write_text("x")
    lib = src / "charting_library" / "charting_library.standalone.js"
    git("init", "-q", str(src))
    ident = ["-c", "user.email=t@t", "-c", "user.name=t"]
    for version in ["9.0", "v31.2.0", "v32.2.0", "v32.3.0-beta"]:
        lib.write_text(f"// {version}")
        git("-C", str(src), "add", "-A")
        git("-C", str(src), *ident, "commit", "-qm", version)
        git("-C", str(src), "tag", version)
    raiz = tmp_path / "srv"
    git("clone", "-q", "--bare", str(src), str(raiz / "tradingview" / "charting_library.git"))

    esperado = "basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    manejador = type("H", (_ServidorGit,), {"raiz": str(raiz), "esperado": esperado, "pedidos": []})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"

    m = re.search(r"- name: Librería TradingView\n.*?run: \|\n(.*?)(?=\n      - name: )", _wf(), re.S)
    script = textwrap.dedent(m.group(1)).replace("https://github.com/", base)
    temp = tmp_path / "work" / "_temp"
    temp.mkdir(parents=True)
    ws = tmp_path / "work" / "repo" / "repo"
    git("init", "-q", str(ws))
    cred = temp / "git-credentials-checkout.config"
    cred.write_text(f'[http "{base}"]\n\textraheader = AUTHORIZATION: basic Z2l0aHViLXRva2Vu\n')
    git("-C", str(ws), "config", "--local", f"includeIf.gitdir:{ws}/.git.path", str(cred))
    salida = temp / "github_output"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "RUNNER_TEMP": str(temp),
           "GITHUB_OUTPUT": str(salida), "GITHUB_STEP_SUMMARY": str(temp / "resumen"),
           "TV_LIBRARY_TOKEN": token, "TV_LIBRARY_TAG": tag}
    try:
        r = subprocess.run(["bash", "-c", script], cwd=ws, env=env, capture_output=True,
                           text=True, timeout=120)
    finally:
        srv.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr   # el paso nunca corta el build
    return r.stdout + r.stderr, salida.read_text(), ws, manejador.pedidos


def test_paso_libreria_con_el_encabezado_del_checkout(tmp_path):
    log, out, ws, pedidos = _correr_paso_libreria(tmp_path, "tok-123")
    assert out == "libreria=ok\n", log
    assert "Librería TradingView v32.2.0 en public/charting_library/" in log
    # un solo Authorization por pedido: el de la librería
    assert pedidos and all(len(a) == 1 for a in pedidos), pedidos
    publicados = sorted(str(p.relative_to(ws)) for p in (ws / "public").rglob("*") if p.is_file())
    assert publicados == ["public/charting_library/bundles/a.js",
                          "public/charting_library/charting_library.standalone.js"]
    assert (ws / "public/charting_library/charting_library.standalone.js").read_text() == "// v32.2.0"
    assert sorted(os.listdir(tmp_path / "work" / "_temp")) == \
        ["git-credentials-checkout.config", "github_output", "resumen"]


def test_paso_libreria_tag_fijo_y_falla_sin_cortar_el_build(tmp_path):
    log, out, ws, _ = _correr_paso_libreria(tmp_path / "fijo", "tok-123", tag="v31.2.0")
    assert out == "libreria=ok\n", log
    assert (ws / "public/charting_library/charting_library.standalone.js").read_text() == "// v31.2.0"
    log, out, ws, _ = _correr_paso_libreria(tmp_path / "mal", "")
    assert out == "libreria=falla\n" and "falta el secreto TV_LIBRARY_TOKEN" in log
    assert not (ws / "public").exists()


def test_workflow_publica_la_pagina_de_prueba_y_el_datafeed():
    generar = _paso(_wf(), "Generar sitio")
    for archivo in ["prueba-graficos.html", "carestia-tv.js", "carestia-tv.css"]:
        assert f"cp {archivo} public/{archivo}" in generar
    # nunca se commitea nada desde el workflow
    assert not re.search(r"git (add|commit|push)", _wf())


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

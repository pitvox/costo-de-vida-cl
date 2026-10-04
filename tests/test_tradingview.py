"""TradingView paso A: librería, datafeed y página de prueba. Sin red: el
build corre en un directorio temporal con el indices.json sintético de
test_datos.py (el tamaño del real).

Verifica que el workflow descargue la librería solo al publicar (fuera del
árbol del repo, sin cortar el build si falla y con un job final que avisa),
que la librería nunca entre al repo, robots.txt, la página oculta
/prueba-graficos.html (noindex, fuera del menú y del sitemap, respaldo con
Lightweight Charts), la atribución a TradingView en el pie de las páginas con
gráficos, los textos del dueño y el datafeed (tests/feed_node.js, si hay
Node, con y sin datos/uf.json). Con CARESTIA_INDICES_REAL=ruta/a/indices.json,
el datafeed se prueba además con los datos reales (curl -O
https://carestia.cl/indices.json), y con CARESTIA_UF_REAL=ruta/a/uf.json (el
que escribe uf.py), también en UF."""
import base64
import datetime
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_datos import indices_realista  # noqa: E402

TV = "https://www.tradingview.com/"
NODE = shutil.which("node")


def uf_sintetica(fin="2026-11-02") -> dict:
    """datos/uf.json como lo escribe uf.py: la UF de cada lunes desde
    2007-12-31, con una UF inventada que sube de a poco."""
    t0 = datetime.date(2007, 12, 31)
    n = (datetime.date.fromisoformat(fin) - t0).days // 7 + 1
    return {"fuente": "prueba", "serie": "F073.UFF.PRE.Z.D", "generado": "2026-10-04",
            "t0": t0.isoformat(), "v": [round(19622.66 * 1.0007 ** i, 2) for i in range(n)]}


def _build(d, data, uf=None):
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if uf is not None:
        (d / "datos").mkdir(exist_ok=True)
        (d / "datos" / "uf.json").write_text(json.dumps(uf), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build_tv"), indices_realista())


@pytest.fixture(scope="module")
def sitio_uf(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build_tv_uf"), indices_realista(), uf_sintetica())


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
    # un tag estable fijo, que la variable del repo puede reemplazar; con los
    # dos vacíos, el tag vX.Y.Z más alto (sin -beta ni -rc)
    fijo = re.search(r"TV_LIBRARY_TAG: \$\{\{ vars\.TV_LIBRARY_TAG \|\| '([^']*)' \}\}", paso)
    assert fijo and re.fullmatch(r"v?[0-9]+(\.[0-9]+)*", fijo.group(1)), paso
    assert 'tag="$TV_LIBRARY_TAG"' in paso
    assert "git ls-remote --tags --refs" in paso
    assert r"sed -nE 's#.*refs/tags/(v?)([0-9]+(\.[0-9]+)*)$#\2 \1\2#p'" in paso
    assert "| sort -V | tail -n 1 | cut -d' ' -f2)" in paso
    # si GitHub no responde, git corta al minuto
    assert "export GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=60" in paso
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


# ---------- el paso, corriendo de verdad ----------
# Actions corre un paso con "shell: bash" así: con -e, además del
# "set -uo pipefail" del script. El paso tiene que terminar siempre en 0.
SHELL_ACTIONS = ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c"]
TOKEN = "tok-123"


class _ServidorGit(http.server.BaseHTTPRequestHandler):
    """git smart-HTTP (git http-backend) que, como GitHub, responde 400 ante
    dos Authorization y 401 si falta o no es el del token."""
    raiz = esperado = None
    pedidos = []

    def _servir(self):
        auths = self.headers.get_all("Authorization") or []
        self.pedidos.append(auths)
        if auths != [self.esperado]:
            self.send_response(400 if len(auths) > 1 else 401)
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


def _script_del_paso(base, cambios=()):
    m = re.search(r"\n      - name: Librería TradingView\n.*?run: \|\n(.*?)(?=\n      - name: )",
                  _wf(), re.S)
    assert m, "no está el paso Librería TradingView"
    script = textwrap.dedent(m.group(1)).replace("https://github.com/", base)
    for viejo, nuevo in cambios:
        assert viejo in script, viejo
        script = script.replace(viejo, nuevo)
    return script


def _correr(tmp_path, script, token, tag):
    """Corre el paso con el entorno de Actions: el workspace es un repo git
    (con el encabezado que dejaría un checkout con credenciales) y git debe
    trabajar desde RUNNER_TEMP. Devuelve (log, $GITHUB_OUTPUT, workspace)."""
    temp = tmp_path / "work" / "_temp"
    ws = tmp_path / "work" / "repo" / "repo"
    temp.mkdir(parents=True)
    ws.mkdir(parents=True)
    salida = temp / "github_output"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "RUNNER_TEMP": str(temp),
           "GITHUB_WORKSPACE": str(ws), "GITHUB_OUTPUT": str(salida),
           "GITHUB_STEP_SUMMARY": str(temp / "resumen"), "TV_LIBRARY_TOKEN": token,
           "TV_LIBRARY_TAG": tag}
    r = subprocess.run([*SHELL_ACTIONS, script], cwd=ws, env=env, capture_output=True,
                       text=True, timeout=120)
    # el paso nunca corta el build: siempre 0, con ok o falla
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout + r.stderr, salida.read_text(), ws


def _paso_libreria(tmp_path, token=TOKEN, tag="", tags=("9.0", "v31.2.0", "v32.2.0", "v32.3.0-beta")):
    """El paso tal cual contra un repo git local con 'tags' (cada uno con su
    charting_library.standalone.js) que solo acepta TOKEN. Devuelve
    (log, $GITHUB_OUTPUT, workspace, Authorization de cada pedido)."""
    if not shutil.which("git"):
        pytest.skip("sin git")
    # el git que arma el repo no lee la config de quien corre los tests
    env_git = dict(os.environ, HOME=str(tmp_path), GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_CONFIG_NOSYSTEM="1")

    def git(*a):
        r = subprocess.run(["git", *a], capture_output=True, text=True, env=env_git)
        assert r.returncode == 0, (a, r.stderr)
    src = tmp_path / "src"
    (src / "charting_library" / "bundles").mkdir(parents=True)
    (src / "datafeeds").mkdir()
    (src / "datafeeds" / "udf.js").write_text("x")
    (src / "index.html").write_text("x")
    (src / "charting_library" / "bundles" / "a.js").write_text("x")
    git("init", "-q", str(src))
    for version in tags:
        (src / "charting_library" / "charting_library.standalone.js").write_text(f"// {version}")
        git("-C", str(src), "add", "-A")
        git("-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-q", "--allow-empty", "-m", version)
        git("-C", str(src), "tag", version)
    raiz = tmp_path / "srv"
    git("clone", "-q", "--bare", str(src), str(raiz / "tradingview" / "charting_library.git"))
    esperado = "basic " + base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    manejador = type("H", (_ServidorGit,), {"raiz": str(raiz), "esperado": esperado, "pedidos": []})
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{srv.server_address[1]}/"
            log, out, ws = _correr(tmp_path, _script_del_paso(base), token, tag)
        finally:
            srv.shutdown()
    return log, out, ws, manejador.pedidos


def _publicados(ws):
    return sorted(str(p.relative_to(ws)) for p in (ws / "public").rglob("*") if p.is_file())


def test_paso_libreria_descarga_la_version_estable_mas_alta(tmp_path):
    log, out, ws, pedidos = _paso_libreria(tmp_path)
    assert out == "libreria=ok\n", log
    assert "Librería TradingView v32.2.0 en public/charting_library/" in log
    assert pedidos and all(len(a) == 1 for a in pedidos), pedidos
    # a public/ va solo charting_library/ (ni datafeeds/ ni los html de ejemplo)
    assert _publicados(ws) == ["public/charting_library/bundles/a.js",
                               "public/charting_library/charting_library.standalone.js"]
    assert sorted(os.listdir(tmp_path / "work" / "_temp")) == ["github_output", "resumen"]
    # con y sin v se compara el número: 33.0.0 le gana a v32.10.0
    log, out, ws, _ = _paso_libreria(tmp_path / "mezcla",
                                     tags=("v32.2.0", "33.0.0", "v32.10.0", "v34.0.0-rc1"))
    assert out == "libreria=ok\n", log
    assert (ws / "public/charting_library/charting_library.standalone.js").read_text() == "// 33.0.0"


def test_paso_libreria_tag_fijo(tmp_path):
    log, out, ws, _ = _paso_libreria(tmp_path, tag="v31.2.0")
    assert out == "libreria=ok\n", log
    assert (ws / "public/charting_library/charting_library.standalone.js").read_text() == "// v31.2.0"


@pytest.mark.parametrize("caso, kw, motivo", [
    ("sin-token", {"token": ""}, "falta el secreto TV_LIBRARY_TOKEN"),
    ("token-malo", {"token": "otro"}, "no se pudieron leer los tags del repo"),
    ("solo-betas", {"tags": ("v32.3.0-beta", "v33.0.0-rc1")}, "el repo no tiene tags de versión estable"),
    ("sin-tags", {"tags": ()}, "el repo no tiene tags de versión estable"),
    ("tag-inexistente", {"tag": "v99.0.0"}, "no se pudo clonar el tag v99.0.0"),
])
def test_paso_libreria_falla_sin_cortar_el_build(tmp_path, caso, kw, motivo):
    log, out, ws, _ = _paso_libreria(tmp_path, **kw)
    assert out == "libreria=falla\n" and motivo in log, log
    assert not (ws / "public" / "charting_library").exists()


def test_paso_libreria_corta_si_github_no_responde(tmp_path):
    """Un servidor que acepta la conexión y nunca contesta: git corta por el
    límite de velocidad (en el workflow, 60 s; aquí 2 s) y el paso avisa."""
    if not shutil.which("git"):
        pytest.skip("sin git")
    with socket.socket() as mudo:
        mudo.bind(("127.0.0.1", 0))
        mudo.listen(8)
        base = f"http://127.0.0.1:{mudo.getsockname()[1]}/"
        script = _script_del_paso(base, [("GIT_HTTP_LOW_SPEED_TIME=60", "GIT_HTTP_LOW_SPEED_TIME=2")])
        t0 = time.monotonic()
        log, out, ws = _correr(tmp_path, script, TOKEN, "")
    assert time.monotonic() - t0 < 60
    assert out == "libreria=falla\n" and "no se pudieron leer los tags del repo" in log, log


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


# ---------- paso B: los gráficos del sitio en Advanced Charts ----------
def _script(h):
    """El JS inline de la página (el último <script> sin src)."""
    return re.findall(r"<script>\n(.*?)</script>", h, re.S)[-1]


def test_graficos_carga_los_motores_sin_bloquear(sitio):
    h = _leer(sitio, "graficos.html")
    cab = h[:h.index("</head>")]
    assert re.search(r'<script defer src="/carestia-tv\.js\?v=[0-9a-f]{10}"></script>', cab)
    # Lightweight sigue (Arma tu canasta y el respaldo), sin bloquear el pintado
    assert ('<script defer src="https://unpkg.com/lightweight-charts@4.1.3/dist/'
            'lightweight-charts.standalone.production.js"></script>') in cab
    assert not re.search(r"<script src=", cab)
    assert "charting_library" not in cab


def test_graficos_indices_y_comparar_en_advanced_charts(sitio):
    js = _script(_leer(sitio, "graficos.html"))
    # la configuración común, un widget por modo, montado al estar a la vista
    assert js.count("TV.montar(") == 1
    assert "sitio: true" in js and "estilo: m === 'indices'" in js
    assert "if (modo === m) montarTV(m);" in js
    # las tabs cambian el símbolo del mismo widget; cada unidad es otro símbolo
    assert "const simboloIndice = code => code + SUF[unidad];" in js
    assert "const SUF = { real: '', epoca: '-epoca', uf: '-uf' };" in js
    assert "ponerSimbolo(tv.indices.w, simboloIndice(code))" in js
    # LÍNEA / VELAS cambia el tipo de gráfico
    assert "const c = w.activeChart(), tipo = linea ? 2 : 1;" in js
    # Comparar: comparación de la librería en escala porcentual, colores por
    # puesto, en la unidad elegida (al cambiarla, se rehacen las comparaciones)
    assert "const sim = k => PRODS[k].slug + SUF[unidad];" in js
    assert "if (keep.includes(k) && x.sim === sim(k)) return;" in js
    assert "{ source: 'close', symbol: s }," in js
    assert "c.createStudy('Compare', false, false," in js
    assert "{ 'plot.color': e.color, 'plot.linestyle': e.punteada ? 1 : 0, 'plot.linewidth': 2 }" in js
    assert "escala.setMode(2)" in js
    # Arma tu canasta sigue en Lightweight
    assert "cchart = LightweightCharts.createChart(el," in js
    # la caja con su tamaño final antes de crear el widget; sin ella, al respaldo
    montar = js[js.index("function montarTV(m)"):js.index("const simboloIndice")]
    assert montar.index("document.body.classList.add(e.clase);") < montar.index("TV.montar(")
    assert "document.body.classList.remove(e.clase);" in montar
    # la librería devuelve el símbolo en mayúsculas
    assert "const sinFuente = t => String(t || '').split(':').pop().toLowerCase();" in js
    # respaldo: el modo que no inicia dibuja con Lightweight
    assert "if (m === 'indices') { initChart(); pintarSerie(cur); }" in js
    assert "else { initPChart(); syncProductos(); }" in js


def test_graficos_controles_y_captura(sitio):
    h = _leer(sitio, "graficos.html")
    # la unidad: Pesos de hoy (por defecto) y Precio de la época; sin
    # datos/uf.json, sin UF
    assert ('<button class="vbtn ubtn active" type="button" data-unidad="real" '
            'aria-pressed="true">Pesos de hoy</button>') in h
    assert ('<button class="vbtn ubtn" type="button" data-unidad="epoca" '
            'aria-pressed="false">Precio de la época</button>') in h
    assert '<option value="epoca">Precio de la época</option>' in h
    assert 'data-unidad="uf"' not in h and '<option value="uf">' not in h
    # todos los gráficos parten en línea; las velas a un clic
    assert '<button class="vbtn active" id="v-linea">LÍNEA</button>' in h
    assert '<button class="vbtn" id="v-velas">VELAS</button>' in h
    assert "let cur = CODES[0], vista = 'linea', unidad = 'real';" in h
    # los controles van juntos y nunca quedan fuera de la vista: las ayudas
    # pasan a otra fila
    assert '<div class="cbar-ctrl">' in h
    assert ".cbar-right { margin-left:auto; display:flex; align-items:center; gap:8px 14px;\n    flex-wrap:wrap; justify-content:flex-end; }" in h
    for viejo in ["+ nominal", "NOMINAL", 'id="v-nominal"', 'id="leg-nom"', 'id="mleg-nom"']:
        assert viejo not in h, viejo
    assert '<div id="tvind" class="tvbox m-ind"></div>' in h
    assert '<div id="tvprod" class="tvbox m-prod"></div>' in h
    js = _script(h)
    # la captura de Advanced Charts es la del cliente; nunca la del servidor
    assert "TV.capturaCliente(w, tok)" in js
    assert not re.search(r"\bw\.takeScreenshot\(", js)
    # la captura dice la unidad y, en UF, la cifra en pesos de hoy debajo
    assert "const TITULO_UNIDAD = { epoca: ', PRECIO DE LA ÉPOCA', uf: ', EN UF' };" in js
    assert "titulo += TITULO_UNIDAD[unidad];" in js
    assert "compLineas.unshift(fmt(d.costo_real) + ' en pesos de hoy');" in js
    tvjs = _leer(sitio, "carestia-tv.js")
    assert "widget.takeClientScreenshot({" in tvjs
    assert "takeScreenshot()" not in tvjs and "snapshot_url:" not in tvjs


def test_graficos_y_ficha_con_uf(sitio_uf):
    """Con datos/uf.json, la opción UF aparece en /graficos.html, en las
    fichas y en el datafeed de la página de prueba."""
    for pagina in ["graficos.html", "productos/producto-000.html"]:
        h = _leer(sitio_uf, pagina)
        assert ('<button class="vbtn ubtn" type="button" data-unidad="uf" '
                'aria-pressed="false">UF</button>') in h, pagina
        assert '<option value="uf">UF</option>' in h, pagina
    app = json.loads(re.search(r"const DATA = (\{.*?\});\n", _leer(sitio_uf, "graficos.html"))
                     .group(1).replace("<\\/", "</"))
    assert app["uf"] is True
    assert "const UF = true;" in _leer(sitio_uf, "productos/producto-000.html")
    prueba = _leer(sitio_uf, "prueba-graficos.html")
    assert "uf: true });" in prueba
    assert "a precio de la época o en UF (por ejemplo, asado-epoca o asado-uf)" in prueba


def test_ficha_con_advanced_charts_despues_del_primer_pantallazo(sitio):
    h = _leer(sitio, "productos/producto-000.html")
    cab = h[:h.index("</head>")]
    # ningún motor de gráficos en el <head>: la cifra y el texto no esperan
    assert not re.search(r"lightweight-charts|charting_library|carestia-tv", cab)
    assert '<div id="grafico"><div class="nochart cargando">Cargando el gráfico...</div></div>' in h
    js = _script(h)
    assert "window.addEventListener('load', () => {" in js
    assert re.search(r"cargarScript\('/carestia-tv\.js\?v=[0-9a-f]{10}'\)", js)
    assert ("TV.montar({ contenedor: el, libreria: '/charting_library/', simbolo: SLUG + SUF[unidad],"
            in js)
    assert "sitio: true" in js
    # sus otras unidades, para superponer desde Comparar
    assert "comparar: unidadesHay().filter(u => u !== 'real')" in js
    assert ".map(u => ({ symbol: SLUG + SUF[u], title: NOMBRE + EN[u] })) });" in js
    assert "const EN = { epoca: ', precio de la época', uf: ', en UF' };" in js
    # el selector de unidad cambia el símbolo; en UF la cifra va en UF y
    # debajo, en pesos de hoy
    assert "Promise.resolve(c.setSymbol(SLUG + SUF[u])).catch(() => {});" in js
    assert "oprice.textContent = TV.textoUF(b[b.length - 1].close);" in js
    assert "opesos.textContent = PRECIO + ' en pesos de hoy';" in js
    assert '<div class="opesos" id="opesos" hidden></div>' in h
    assert "const UF = false;" in js
    assert "const SLUG = 'producto-000';" in js and 'const NOMBRE = "Producto 000";' in js
    # la serie de la página alimenta el datafeed (no se vuelve a pedir)
    assert "precargados: { ['productos/' + SLUG + '.json']: { t0: T0, v: V, min: MIN, max: MAX } }" in js
    # el rango semanal en la página y la referencia de las velas
    assert re.search(r"const MIN = \[[0-9null, ]+\];", js) and re.search(r"const MAX = \[[0-9null, ]+\];", js)
    assert ('<p class="ref-velas" id="ref-velas" hidden>Velas semanales. La mecha va del precio más bajo '
            'al más alto que ODEPA encontró entre los locales encuestados.</p>') in h
    # respaldo: Lightweight como siempre, en hueso y con fechas es-CL
    assert "}).then(w => {\n      widget = w;\n      el.dataset.motor = 'advanced';" in js
    assert "    }, () => { selector.limitar(unidadesHay()); lightweight(); });" in js
    # la referencia de las velas se muestra mientras estén a la vista
    assert "c.onChartTypeChanged().subscribe(null, ver);" in js
    assert "chart.addLineSeries({ color: tok('bone'), lineWidth: 2, priceLineVisible: false })" in js
    assert ("localization: { locale: 'es-CL', priceFormatter: v => unidad === 'uf' && TV ? "
            "TV.numUF(v) : fmt(v) }") in js


def test_configuracion_comun_en_una_funcion(sitio):
    tvjs = _leer(sitio, "carestia-tv.js")
    assert tvjs.count("function opcionesWidget(o)") == 1
    assert "widget = new window.TradingView.widget(opcionesWidget(o));" in tvjs
    # toda la historia al abrir y en cada cambio de símbolo
    assert "onSymbolChanged().subscribe(null, () => verTodo(widget, o.datafeed, caja));" in tvjs
    # con la caja oculta el rango espera a que vuelva a tener ancho
    assert "if (caja && !caja.clientWidth && typeof ResizeObserver === 'function') {" in tvjs
    # al cambiar de símbolo, el rango espera a que lleguen las barras
    assert "return datos.then(() => feed.barras(chart.symbol(), temp())).then(b => {" in tvjs
    # y en cada cambio de temporalidad, en la nueva
    assert "c.onIntervalChanged().subscribe(null, res => verTodo(widget, o.datafeed, caja, res));" in tvjs
    assert "const op = { applyDefaultRightMargin: true, rejectByTimeout: 3000 };" in tvjs
    assert "if (v && v.from > rango.from + 86400) return chart.setVisibleRange(rango, op);" in tvjs
    # v32 dibuja la línea con degradé si no se pide sólida: el color del sitio
    assert tvjs.count("'mainSeriesProperties.lineStyle.colorType': 'solid'") == 2
    assert "const MOVIL = '(max-width: 640px)';" in tvjs
    # las tres páginas con Advanced Charts usan la misma configuración
    for pagina in ["graficos.html", "productos/producto-000.html"]:
        assert "TV.montar(" in _leer(sitio, pagina), pagina
    assert "TV.opcionesWidget({" in _leer(sitio, "prueba-graficos.html")


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
    salida = _feed_node(sitio)
    assert "chequeos OK" in salida and "; sin UF" in salida


def test_datafeed_con_datos_sinteticos_en_uf(sitio_uf):
    salida = _feed_node(sitio_uf)
    assert "chequeos OK" in salida and "semanas de producto en UF (prueba" in salida


@pytest.mark.skipif(not os.environ.get("CARESTIA_INDICES_REAL"),
                    reason="sin CARESTIA_INDICES_REAL (indices.json real de carestia.cl)")
def test_datafeed_con_datos_reales(tmp_path):
    with open(os.environ["CARESTIA_INDICES_REAL"], encoding="utf-8") as fh:
        data = json.load(fh)
    uf = None
    if os.environ.get("CARESTIA_UF_REAL"):
        with open(os.environ["CARESTIA_UF_REAL"], encoding="utf-8") as fh:
            uf = json.load(fh)
    salida = _feed_node(_build(tmp_path, data, uf))
    print(salida)
    assert "chequeos OK" in salida

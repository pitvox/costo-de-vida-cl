"""Pruebas sin red de la prueba de lectura de supermercados
(analisis/supermercados/prueba_lectura.py). No tocan el sitio ni piden nada a
jumbo.cl ni a santaisabel.cl: revisan el lector de tarjetas contra los ejemplos
de claude/Prompt_prueba_supermercados.md, robots.txt, la detección de bloqueos,
la regla de qué deja salir el navegador y, con una sesión y un navegador
falsos, una corrida entera (tope de 32, pausas, robots.txt primero y que un
bloqueo frene al sitio)."""
import csv
import os
import re
import sys
import types

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "analisis", "supermercados"))
import prueba_lectura as pl  # noqa: E402
from test_texto import infracciones  # noqa: E402

PROMPT = os.path.join(RAIZ, "claude", "Prompt_prueba_supermercados.md")


def ejemplos_del_prompt() -> list:
    """Los bloques de texto de "Formato del texto de cada tarjeta", tal cual."""
    with open(PROMPT, encoding="utf-8") as fh:
        texto = fh.read()
    tramo = texto.split("Formato del texto de cada tarjeta", 1)[1].split("Con oferta aparece", 1)[0]
    return re.findall(r"```\n(.*?)```", tramo, re.S)


def una(texto: str) -> dict:
    tarjetas = pl.leer_tarjetas(texto)
    assert len(tarjetas) == 1, tarjetas
    return tarjetas[0]


# ---------- el lector de tarjetas ----------

def test_el_prompt_trae_los_dos_ejemplos():
    assert len(ejemplos_del_prompt()) == 2


def test_precio_simple():
    t = una(ejemplos_del_prompt()[0])
    assert (t["precio"], t["precio_unidad"], t["unidad"]) == (3890, 1945, "kg")
    assert (t["marca"], t["nombre"]) == ("Frutas y Verduras Propias", "Papa Malla 2 kg")
    assert t["precio_anterior"] is None and t["oferta"] == "" and t["presentacion"] is None


def test_precio_por_500_g():
    t = una(ejemplos_del_prompt()[1])
    assert (t["precio"], t["presentacion"]) == (1125, "x 500 g")
    assert (t["precio_unidad"], t["unidad"]) == (2250, "kg")
    assert (t["marca"], t["nombre"]) == ("Frutas y Verduras Propias", "Papa Granel")
    assert t["oferta"] == ""


# El prompt describe la oferta y la unidad "x un" sin copiar una tarjeta: estas
# dos se arman con su descripción y con cifras de su tabla (arroz de Santa
# Isabel en oferta, cebolla en malla de 3).
OFERTA = "Santa Ofertas\n$990\n$1.350\n$990 x kg\nCuisine & Co\nArroz Grado 2 Largo Delgado 1 kg"
POR_UNIDAD = "$1.850\n$617 x un\nFrutas y Verduras Propias\nCebolla Malla 3 un."


def test_oferta_con_dos_precios():
    t = una(OFERTA)
    assert (t["precio"], t["precio_anterior"], t["etiqueta"]) == (990, 1350, "Santa Ofertas")
    assert (t["precio_unidad"], t["unidad"]) == (990, "kg")
    assert (t["marca"], t["nombre"]) == ("Cuisine & Co", "Arroz Grado 2 Largo Delgado 1 kg")
    assert t["oferta"] == "Santa Ofertas, antes $1.350"


def test_unidad_x_un():
    t = una(POR_UNIDAD)
    assert (t["precio"], t["precio_unidad"], t["unidad"]) == (1850, 617, "un")
    assert t["nombre"] == "Cebolla Malla 3 un."


def test_etiqueta_con_precio_no_es_un_precio():
    t = una("Lleva 2 por $3.000\n$1.990\n$1.990 x un\nCuisine & Co\nAceite Vegetal 900 ml")
    assert t["precio"] == 1990 and t["precio_anterior"] is None
    assert t["oferta"] == "Lleva 2 por $3.000"


def pagina(n_tarjetas: int) -> str:
    """Un innerText de página: filtros (con precios sueltos) y n tarjetas."""
    filtros = "Filtros\nCategoría\nFrutas y Verduras (12)\nPrecio\n$0 a $5.000\nOrdenar por\nRelevancia"
    tarjetas = []
    for i in range(n_tarjetas):
        if i % 3 == 1:
            tarjetas.append(f"Oferta\n$1.{i}90\n$2.{i}90\n$1.{i}90 x kg\nMarca {i}\nProducto {i}")
        else:
            tarjetas.append(f"$3.{i}90\n$1.{i}45 x kg\nMarca {i}\nProducto {i}")
    return filtros + "\n" + "\nAgregar\n".join(tarjetas) + "\nAgregar\nVer más productos"


def test_pagina_con_filtros_y_tope_de_ocho():
    tarjetas = pl.leer_tarjetas(pagina(10))
    assert len(tarjetas) == 8
    assert [t["posicion"] for t in tarjetas] == list(range(1, 9))
    assert [t["nombre"] for t in tarjetas] == [f"Producto {i}" for i in range(8)]
    assert tarjetas[0]["precio"] == 3090 and tarjetas[0]["oferta"] == ""
    assert (tarjetas[1]["precio"], tarjetas[1]["precio_anterior"]) == (1190, 2190)
    assert tarjetas[1]["oferta"] == "Oferta, antes $2.190"


def test_sin_estilos_las_lineas_se_juntan_o_se_parten():
    # sin hojas de estilo (fase B) piezas que iban en líneas separadas quedan
    # juntas, y al revés: la tarjeta tiene que salir igual
    estilos = "Oferta\n$2.890\n$3.990\n$2.890 x kg\nMarca\nTrutro Entero Granel\nAgregar"
    juntas = "Oferta$2.890$3.990\n\n$2.890 x kg\n\nMarca\n\nTrutro Entero GranelAgregar"
    partidas = "Oferta\n$2.890\n$3.990\n$2.890\nx kg\nMarca\nTrutro Entero Granel\nAgregar"
    esperado = pl.leer_tarjetas(estilos)
    assert esperado[0]["precio"] == 2890 and esperado[0]["precio_anterior"] == 3990
    assert pl.leer_tarjetas(juntas) == esperado
    assert pl.leer_tarjetas(partidas) == esperado
    granel = pl.leer_tarjetas("$1.125x 500 g$2.250 x kg\nFrutas y Verduras Propias\nPapa Granel")
    assert (granel[0]["precio"], granel[0]["presentacion"], granel[0]["precio_unidad"]) == (1125, "x 500 g", 2250)


def test_sin_agregar_entre_tarjetas():
    texto = ("$3.890\n$1.945 x kg\nMarca A\nProducto A\n"
             "Oferta\n$990\n$1.350\n$990 x kg\nMarca B\nProducto B")
    a, b = pl.leer_tarjetas(texto)
    assert (a["marca"], a["nombre"]) == ("Marca A", "Producto A")
    assert (b["nombre"], b["etiqueta"], b["precio"]) == ("Producto B", "Oferta", 990)


def test_numeros():
    assert pl.a_numero("1.945") == 1945
    assert pl.a_numero("11.790") == 11790
    assert pl.a_numero("990") == 990
    assert pl.a_numero("2.111,5") == 2111.5
    assert pl.a_numero("1,945") == 1945
    assert pl.a_numero("1.000.000") == 1000000


def test_texto_de_html():
    html = ("<html><head><title>x</title></head><body><header>Menú</header><main>"
            "<div>Filtros</div><div><span>$3.890</span></div>"
            "<div><span>$1.945</span><!-- --> x <!-- -->kg</div>"
            "<p>Frutas y Verduras Propias</p><h2>Papa Malla 2 kg</h2><button>Agregar</button>"
            "<script>var p = '$9.999 x kg'</script><div hidden>oculto $1</div>"
            "<div style='display: none'>tampoco $2</div></main><footer>Pie</footer></body></html>")
    texto, hubo_main = pl.texto_de_html(html)
    assert hubo_main
    assert texto == "Filtros\n$3.890\n$1.945 x kg\nFrutas y Verduras Propias\nPapa Malla 2 kg\nAgregar"
    assert pl.leer_tarjetas(texto)[0]["nombre"] == "Papa Malla 2 kg"
    sin_main, hubo = pl.texto_de_html("<body><div>Hola</div></body>")
    assert (sin_main, hubo) == ("Hola", False)


def test_conteo_de_unidades_y_nombres_en_datos():
    html = ('<div>$1.945 x kg</div><div>$990<!-- --> x <!-- -->un</div><div>x lt</div>'
            '<script>{"productName":"Papa Granel","name":"Papas Fritas","nombre":"Tomate"}</script>')
    assert pl.contar_unidades(html) == {"kg": 1, "lt": 1, "un": 1}
    assert pl.nombres_en_datos(html, "papa") == ["Papa Granel", "Papas Fritas"]


# ---------- robots.txt ----------

# armados con lo que el prompt dice de cada robots.txt
ROBOTS_JUMBO = """User-agent: *
Disallow: /*?map=
Disallow: /*?PS=
Disallow: /*sc=
Disallow: /checkout
Disallow: /account
Sitemap: https://www.jumbo.cl/sitemap.xml
"""
ROBOTS_SANTA = """# Santa Isabel
User-agent: *
Allow: /
Crawl-delay: 1
Disallow: /api/
Disallow: /_next/
Disallow: /admin/
Disallow: /private/
"""


def test_robots_jumbo():
    r = pl.Robots(ROBOTS_JUMBO)
    assert all(r.permite(pl.ruta_de(pl.url_busqueda("https://www.jumbo.cl", t))) for t in pl.TERMINOS)
    assert not r.permite("/papa?map=ft")
    assert not r.permite("/busqueda?ft=papa&sc=1")
    assert not r.permite("/checkout/cart")
    assert r.crawl_delay is None


def test_robots_santa_isabel():
    r = pl.Robots(ROBOTS_SANTA)
    assert r.permite("/busqueda?ft=papa")
    assert not r.permite("/_next/static/chunks/main.js")
    assert not r.permite("/api/catalogo")
    assert r.crawl_delay == 1.0


def test_robots_reglas_rfc9309():
    r = pl.Robots("User-agent: otro\nDisallow: /\n\nUser-agent: *\nDisallow: /a\nAllow: /a/b\n"
                  "Disallow: /*.json$\nDisallow: /x*y\n")
    assert r.permite("/b") and not r.permite("/a/c") and r.permite("/a/b/c")
    assert not r.permite("/datos.json") and r.permite("/datos.json?x=1")
    assert not r.permite("/x123y")
    # a igual largo gana Allow; sin reglas, todo permitido
    assert pl.Robots("User-agent: *\nDisallow: /p\nAllow: /p\n").permite("/p")
    assert pl.Robots("").permite("/cualquiera")
    # un grupo que nombra a la prueba se suma al de "*"; no lo reemplaza
    propio = pl.Robots("User-agent: *\nDisallow: /busqueda\n\nUser-agent: CarestiaPrueba\nAllow: /\n")
    assert not propio.permite("/busqueda?ft=papa")
    # la ruta decodificada también cuenta
    assert not pl.Robots("User-agent: *\nDisallow: /busqueda?ft=a b\n").permite("/busqueda?ft=a%20b")


# ---------- bloqueos ----------

def test_bloqueos():
    assert pl.ver_bloqueo(403, {}, "", "", "", False) == "HTTP 403"
    assert pl.ver_bloqueo(429, {}, "", "", "", True) == "HTTP 429"
    assert pl.ver_bloqueo(200, {"CF-Mitigated": "challenge"}, "", "", "", False)
    assert pl.ver_bloqueo(200, {}, "<html>", "Un momento", "Just a moment...", False)
    assert pl.ver_bloqueo(200, {}, '<div id="px-captcha"></div>', "Press & Hold", "", False)
    assert pl.ver_bloqueo(503, {}, "<script>cf_chl_opt={}</script>", "", "", False)
    # una página normal con productos y un reCAPTCHA en el pie no está bloqueada
    assert pl.ver_bloqueo(200, {}, '<script src="recaptcha/api.js">', "captcha", "Jumbo", True) is None
    # sin productos ni marcas de desafío: sin precios, no bloqueado
    assert pl.ver_bloqueo(200, {}, "<main>Sin resultados</main>", "No encontramos productos",
                          "Búsqueda", False) is None


# ---------- qué deja salir el navegador de la fase B ----------

def evento(url, tipo="Document", marco="M", redireccion=None):
    ev = {"request": {"url": url}, "resourceType": tipo, "frameId": marco, "requestId": "1"}
    if redireccion:
        ev["redirectedRequestId"] = redireccion
    return ev


def test_politica_del_navegador():
    base = "https://www.jumbo.cl"
    robots = pl.Robots(ROBOTS_JUMBO)
    decidir = pl.NavegadorB._decidir
    estado = {"inicio": False, "saltos": [], "frenada": None, "extra": None}
    url = pl.url_busqueda(base, "papa")
    assert decidir(evento(url), "M", base, robots, estado) == "sale"           # la búsqueda
    for tipo in ("Stylesheet", "Script", "Image", "Font", "XHR", "Fetch", "Ping", "Other"):
        assert decidir(evento(base + "/estilo.css", tipo), "M", base, robots, estado) == "frena"
    assert decidir(evento("https://otro.cl/x", "Document", marco="F"), "M", base, robots, estado) == "frena"
    # redirección del servidor: dentro de /busqueda y permitida, sí; a ?map=, no
    assert decidir(evento(url + "&x=1", redireccion="r1"), "M", base, robots, estado) == "sale"
    assert decidir(evento(base + "/papa?map=ft", redireccion="r2"), "M", base, robots, estado) == "frena"
    assert "robots.txt" in estado["frenada"]
    # otra navegación (meta refresh, formulario): no sale; el navegador se queda donde está
    assert decidir(evento(base + "/busqueda?ft=otra"), "M", base, robots, estado) == "queda"
    assert estado["extra"] == base + "/busqueda?ft=otra"
    # la primera navegación tiene que ser una búsqueda del mismo sitio
    for malo in ("https://otro.cl/busqueda?ft=papa", base + "/papa?map=ft", base + "/api/x"):
        nuevo = {"inicio": False, "saltos": [], "frenada": None, "extra": None}
        assert decidir(evento(malo), "M", base, robots, nuevo) == "frena"


def test_no_seguir():
    base = "https://www.santaisabel.cl"
    robots = pl.Robots(ROBOTS_SANTA)
    assert pl.no_seguir(base + "/busqueda?ft=papa&page=1", robots, base, 0) is None
    assert "otro sitio" in pl.no_seguir("https://www.jumbo.cl/busqueda?ft=papa", robots, base, 0)
    assert "no lee" in pl.no_seguir(base + "/_next/data/x.json", robots, base, 0)
    assert "búsqueda" in pl.no_seguir(base + "/frutas/papa", robots, base, 0)
    assert "redirecciones" in pl.no_seguir(base + "/busqueda?ft=papa", robots, base, 2)


# ---------- reglas fijas de la prueba ----------

def test_reglas_fijas():
    assert pl.UA_SUFIJO == "CarestiaPrueba/0.1 (+https://carestia.cl; contacto@carestia.cl)"
    assert pl.TERMINOS == ["posta paleta", "trutro entero pollo", "arroz grado 2", "papa",
                           "tomate", "cebolla", "aceite vegetal", "marraqueta"]
    assert pl.TOPE_BUSQUEDAS == len(pl.TERMINOS) * len(pl.SITIOS) * 2 == 32
    assert pl.PAUSA_MINIMA == 3 and pl.PAUSA >= pl.PAUSA_MINIMA
    assert pl.url_busqueda("https://www.jumbo.cl", "posta paleta") == \
        "https://www.jumbo.cl/busqueda?ft=posta%20paleta"
    # nunca menos de 3 s con los sitios reales, ni menos que su Crawl-delay
    assert pl.pausa_del_sitio(0.5, "https://www.jumbo.cl", None) == 3.0
    assert pl.pausa_del_sitio(5.0, "https://www.santaisabel.cl", 7) == 7.0
    tope = pl.Tope()
    for _ in range(32):
        tope.tomar()
    with pytest.raises(RuntimeError):
        tope.tomar()


def test_ua_de_la_fase_a():
    pytest.importorskip("requests")
    s = pl.sesion_a()
    assert s.headers["User-Agent"].endswith(pl.UA_SUFIJO)
    assert s.trust_env is False


def test_workflow():
    with open(os.path.join(RAIZ, ".github", "workflows", "prueba_supermercados.yml"),
              encoding="utf-8") as fh:
        wf = fh.read()
    assert "permissions:\n  contents: read" in wf
    assert "contents: write" not in wf and "secrets." not in wf
    assert "retention-days: 3" in wf and "cat salida/resumen.md" in wf
    assert "schedule" not in wf and "pull_request" not in wf
    disparos = wf.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in disparos
    if "push:" in disparos:                 # solo mientras dura la prueba, y solo esta rama
        assert re.findall(r"^\s+- (\S+)$", disparos, re.M) == ["claude/prueba-supermercados"]


# ---------- una corrida entera, con sesión y navegador falsos ----------

class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        assert s > 0
        self.t += s


class Respuesta:
    def __init__(self, estado, cuerpo="", cabeceras=None):
        self.status_code = estado
        self.content = cuerpo.encode("utf-8")
        self.headers = {"content-type": "text/html; charset=utf-8", **(cabeceras or {})}
        self.history = []

    def close(self):
        pass


def html_busqueda(termino: str) -> str:
    return (f"<html><head><title>{termino}</title></head><body><main><div>Filtros</div>"
            f"<div>$1.990</div><div>$995 x kg</div><p>Marca</p><h2>{termino.title()} 1 kg</h2>"
            f"<button>Agregar</button></main></body></html>")


class Sesion:
    def __init__(self, reloj, log, respuesta):
        self.reloj, self.log, self.respuesta = reloj, log, respuesta
        self.headers = {"User-Agent": "python-requests/0 " + pl.UA_SUFIJO}

    def get(self, url, timeout=None, allow_redirects=True):
        self.log.append(("A", url, self.reloj.t))
        self.reloj.t += 0.4
        return self.respuesta(url)


class Navegador:
    """Reemplaza a NavegadorB: anota cada pedido y devuelve una página leída."""
    log, reloj, bloquear = None, None, ()

    def __init__(self, pw):
        self.ua = "Mozilla/5.0 HeadlessChrome/1 " + pl.UA_SUFIJO
        self.version = "1"

    def pedir(self, base, termino, robots):
        url = pl.url_busqueda(base, termino)
        assert robots.permite(pl.ruta_de(url))
        self.log.append(("B", url, self.reloj.t))
        self.reloj.t += 1.5
        if any(b in url for b in self.bloquear):
            return {"url": url, "estado": 403, "bytes": 10, "dur": 1.5, "resultado": "bloqueado",
                    "detalle": "HTTP 403", "tarjetas": [], "texto": "Access Denied",
                    "redirecciones": [], "subpedidos": {"salieron": 1, "frenados": {}}}
        texto = pl.texto_de_html(html_busqueda(termino))[0]
        return {"url": url, "estado": 200, "bytes": 900, "dur": 1.5, "resultado": "ok",
                "detalle": "con precios", "tarjetas": pl.leer_tarjetas(texto), "texto": texto,
                "redirecciones": [], "subpedidos": {"salieron": 1, "frenados": {"Stylesheet": 2}}}

    def cerrar(self):
        pass


@pytest.fixture
def corrida_falsa(monkeypatch, tmp_path):
    pytest.importorskip("requests")
    reloj = Reloj()
    monkeypatch.setattr(pl, "_reloj", reloj)
    monkeypatch.setattr(pl, "_dormir", reloj.dormir)
    log = []

    class SyncPW:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    falso = types.ModuleType("playwright.sync_api")
    falso.sync_playwright = SyncPW
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", falso)
    Navegador.log, Navegador.reloj = log, reloj
    monkeypatch.setattr(pl, "NavegadorB", Navegador)

    def correr(respuesta, bloquear_b=()):
        monkeypatch.setattr(pl, "sesion_a", lambda: Sesion(reloj, log, respuesta))
        Navegador.bloquear = bloquear_b
        salida = str(tmp_path / "salida")
        corrida = pl.correr(salida, dict(pl.SITIOS), pl.PAUSA)
        pl.escribir_salidas(salida, corrida)
        return corrida, log, salida

    return correr


def responder_normal(url):
    if url.endswith("/robots.txt"):
        return Respuesta(200, ROBOTS_SANTA if "santaisabel" in url else ROBOTS_JUMBO,
                         {"content-type": "text/plain"})
    termino = url.split("ft=", 1)[1].replace("%20", " ")
    return Respuesta(200, html_busqueda(termino))


def revisar_ritmo(log):
    """robots.txt antes que nada, uno a la vez y 5 s o más entre pedidos a un sitio."""
    for sitio in pl.SITIOS:
        propios = [(fase, url, t) for fase, url, t in log if sitio in url]
        assert propios[0][1].endswith("/robots.txt")
        assert sum(1 for _, u, _ in propios if u.endswith("/robots.txt")) == 1
        for (_, _, t1), (_, _, t2) in zip(propios, propios[1:]):
            # el pedido anterior dura 0,4 s (fase A) o 1,5 s (fase B)
            assert t2 - t1 >= pl.PAUSA + 0.4 - 1e-9
    tiempos = [t for _, _, t in log]
    assert tiempos == sorted(tiempos)


def test_corrida_completa(corrida_falsa):
    corrida, log, salida = corrida_falsa(responder_normal)
    busquedas = [x for x in log if "/busqueda" in x[1]]
    assert len(busquedas) == 32 == corrida["busquedas_pedidas"]
    assert {f for f, _, _ in busquedas} == {"A", "B"}
    revisar_ritmo(log)
    with open(os.path.join(salida, "resultado.csv"), encoding="utf-8") as fh:
        filas = list(csv.reader(fh))
    assert filas[0] == ["sitio", "fase", "término", "posición", "nombre", "marca", "precio",
                        "precio_unidad", "unidad", "oferta"]
    assert len(filas) == 1 + 32
    assert filas[1] == ["jumbo.cl", "A", "posta paleta", "1", "Posta Paleta 1 kg", "Marca",
                        "1990", "995", "kg", ""]
    with open(os.path.join(salida, "resumen.md"), encoding="utf-8") as fh:
        resumen = fh.read()
    assert "| jumbo.cl | A, pedido simple | 8 de 8 | 200 en las 8 | sí, en 8 de 8 | no |" in resumen
    assert "| santaisabel.cl | B, navegador sin interfaz | 8 de 8 | 200 en las 8 | sí, en 8 de 8 | no |" in resumen
    assert infracciones(resumen) == []
    assert len(os.listdir(os.path.join(salida, "crudo"))) == 32
    # releer desde crudo/ da lo mismo, sin pedir nada
    antes = len(log)
    pl.releer(salida)
    assert len(log) == antes
    with open(os.path.join(salida, "resultado.csv"), encoding="utf-8") as fh:
        assert list(csv.reader(fh)) == filas


def test_un_bloqueo_frena_al_sitio(corrida_falsa):
    def responder(url):
        if "santaisabel" in url and "ft=papa" in url:
            return Respuesta(403, "<html><title>Access Denied</title>Reference #18</html>",
                             {"server": "AkamaiGHost"})
        return responder_normal(url)

    corrida, log, salida = corrida_falsa(responder)
    santa = [x for x in log if "santaisabel" in x[1]]
    # robots.txt y las 4 primeras búsquedas de la fase A; la cuarta ("papa") bloqueó
    assert len(santa) == 1 + 4 and santa[-1][1].endswith("ft=papa")
    assert not any(f == "B" for f, _, _ in santa)
    assert len([x for x in log if "jumbo" in x[1] and "/busqueda" in x[1]]) == 16
    assert corrida["frenados"]["santaisabel.cl"]["resultado"] == "bloqueado"
    with open(os.path.join(salida, "resumen.md"), encoding="utf-8") as fh:
        resumen = fh.read()
    assert '| santaisabel.cl | A, pedido simple | 4 de 8 | 200 en 3, 403 en 1 | sí, en 3 de 4 |' \
        ' sí: HTTP 403 en "papa" |' in resumen
    assert "no se probó: el sitio quedó frenado en la fase A" in resumen
    assert "AkamaiGHost" in resumen
    assert infracciones(resumen) == []


def test_un_bloqueo_en_la_fase_b(corrida_falsa):
    corrida, log, _ = corrida_falsa(responder_normal, bloquear_b=("jumbo.cl/busqueda?ft=arroz",))
    jumbo_b = [u for f, u, _ in log if f == "B" and "jumbo" in u]
    assert len(jumbo_b) == 3 and jumbo_b[-1].endswith("ft=arroz%20grado%202")
    assert len([1 for f, u, _ in log if f == "B" and "santaisabel" in u]) == 8


def test_robots_que_no_responde_frena_al_sitio(corrida_falsa):
    def responder(url):
        if url == "https://www.jumbo.cl/robots.txt":
            return Respuesta(503, "caído")
        return responder_normal(url)

    corrida, log, _ = corrida_falsa(responder)
    assert [u for _, u, _ in log if "jumbo" in u] == ["https://www.jumbo.cl/robots.txt"]
    assert corrida["frenados"]["jumbo.cl"]["fase"] == "robots"


def test_fuera_de_actions_no_toca_a_los_supermercados(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    llamadas = []
    monkeypatch.setattr(pl, "correr", lambda *a, **k: llamadas.append(a))
    assert pl.main(["--salida", str(tmp_path)]) == 2
    assert pl.main(["--salida", str(tmp_path), "--base", "jumbo.cl=http://127.0.0.1:9"]) == 2
    assert llamadas == []

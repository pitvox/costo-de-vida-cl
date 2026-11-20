"""Pruebas sin red de la prueba de lectura de supermercados
(analisis/supermercados/prueba_lectura.py). No tocan el sitio ni piden nada a
jumbo.cl ni a santaisabel.cl: revisan el lector de tarjetas contra los ejemplos
de claude/Prompt_prueba_supermercados.md, robots.txt, la detección de bloqueos,
las redirecciones, la regla de qué deja salir el navegador y, con una sesión y
un navegador falsos, una corrida entera (tope de 32 con los saltos, pausas,
robots.txt primero, que un bloqueo frene al sitio y que un corte quede dicho)."""
import csv
import gzip
import json
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


def test_sin_estilos_la_unidad_pegada_a_lo_que_sigue():
    # el innerText real de Chromium con precio, precio por unidad, marca y
    # nombre como elementos en línea hermanos, sin hojas de estilo
    t = una("$3.890$1.945 x kgFrutas y Verduras PropiasPapa Malla 2 kgAgregar")
    assert (t["precio"], t["precio_anterior"], t["precio_unidad"], t["unidad"]) == (3890, None, 1945, "kg")
    aceite = una("$1.690\n$2.100\nx 900 ml$1.878 x lt\nCuisine & Co\nAceite Vegetal 900 ml\nAgregar")
    assert (aceite["precio"], aceite["precio_anterior"], aceite["presentacion"]) == (1690, 2100, "x 900 ml")
    assert (aceite["precio_unidad"], aceite["unidad"]) == (1878, "lt")
    granel = una("$1.125\nx 500 g$2.250 x kg\nFrutas y Verduras Propias\nPapa Granel")
    assert (granel["precio"], granel["presentacion"], granel["precio_unidad"]) == (1125, "x 500 g", 2250)
    # una palabra en mayúsculas pegada no es una unidad
    assert pl.piezas("$5.990 x LOMO") == [("precio", 5990), ("texto", "x LOMO")]


def test_texto_entre_los_precios_y_el_precio_por_unidad():
    casos = {
        "Santa Ofertas\n$990\nNormal: $1.350\n$990 x kg": (990, 1350),
        "Santa Ofertas\n$990\nPrecio normal\n$1.350\n$990 x kg": (990, 1350),
        "$990\n$1.350\nAhorra $360\n$990 x kg": (990, 1350),
        "$1.690\n-20%\n$2.100\n$1.878 x lt": (1690, 2100),
        "$1.690\n$2.100\n-20%\n$1.878 x lt": (1690, 2100),
        "$1.690\n$2.100\nOferta\n$1.878 x lt": (1690, 2100),
        "$990\n$990 x kg\nNormal: $1.350": (990, 1350),
    }
    for texto, esperado in casos.items():
        t = una(texto + "\nMarca\nProducto\nAgregar")
        assert (t["precio"], t["precio_anterior"]) == esperado, texto
        assert (t["marca"], t["nombre"]) == ("Marca", "Producto"), texto
    assert una("Santa Ofertas\n$990\nNormal: $1.350\n$990 x kg\nMarca\nArroz")["etiqueta"] == "Santa Ofertas"


def test_copias_ocultas_del_bloque_de_precios():
    t = una("Oferta\n$2.890\n$3.990\n$2.890 x kg\n$2.890 x kg\nMarca\nTrutro Entero Granel\nAgregar")
    assert (t["precio"], t["precio_anterior"], t["etiqueta"]) == (2890, 3990, "Oferta")
    assert t["nombre"] == "Trutro Entero Granel"
    # diez productos, cada uno con su bloque de precios repetido: las 8 primeras
    # tarjetas son 8 productos, no 4 productos y 4 copias sin nombre
    texto = "\n".join(f"$3.{i}90\n$1.{i}45 x kg\n$3.{i}90\n$1.{i}45 x kg\nMarca {i}\nProducto {i}\nAgregar"
                      for i in range(10))
    assert [t["nombre"] for t in pl.leer_tarjetas(texto)] == [f"Producto {i}" for i in range(8)]


def test_promocion_por_cantidad_no_es_precio_anterior():
    for texto in ("Lleva 2 por\n$3.000\n$1.990\n$2.211 x lt", "2x$5.000\n$1.990\n$2.211 x lt",
                  "Lleva 2x $3.000\n$1.990\n$2.211 x lt"):
        t = una(texto + "\nMarca\nAceite\nAgregar")
        assert (t["precio"], t["precio_anterior"]) == (1990, None), texto
        assert t["etiqueta"], texto


def test_precios_de_los_filtros_no_son_de_la_tarjeta():
    for filtro in ("Precio\n$0 - $5.000\n$5.000 - $20.000", "Precio\n$590\n$24.990"):
        t = pl.leer_tarjetas(filtro + "\n$3.890\n$1.945 x kg\nMarca\nPapa Malla 2 kg\nAgregar")[0]
        assert (t["precio"], t["precio_anterior"]) == (3890, None), filtro


def test_numero_que_no_se_lee_no_rompe_el_lector():
    assert pl.a_numero("1.945.50") is None
    t = una("Despacho $1.990.5\n$3.890\n$1.945 x kg\nMarca\nPapa\nAgregar")
    assert (t["precio"], t["precio_unidad"]) == (3890, 1945)


def test_categorias_de_los_filtros_no_son_etiqueta():
    # el texto real de santaisabel.cl en la corrida: antes de la primera tarjeta
    # va la tira de categorías ("Marcas Exclusivas" es una categoría, no una oferta)
    for tira in ("Chocolates, Galletas y SnacksLácteos, Huevos y CongeladosMarcas ExclusivasFrutas "
                 "y VerdurasProductos ImportadosMypes", "DespensaMarcas Exclusivas",
                 "Carnes y PescadosMarcas Exclusivas"):
        t = una(f"Aplicar\n{tira}\n{tira}\n$3.950\n$1.975 x kg\nFrutas y Verduras Propias\n"
                "Papa Malla 2 kg\nAgregar")
        assert (t["precio"], t["etiqueta"], t["oferta"]) == (3950, "", ""), tira
    # las etiquetas reales de la corrida siguen contando
    for etiqueta in ("Exclusivo online", "Exclusivo Jumbo", "20% dcto.", "Los Imbatibles", "Oferta"):
        t = una(f"Agregar\n{etiqueta}\n$2.890$3.990x 1 kg\n$2.890 x kg\nGranel\nTrutro Entero de Pollo kg\nAgregar")
        assert (t["precio"], t["precio_anterior"], t["presentacion"], t["etiqueta"]) == \
            (2890, 3990, "x 1 kg", etiqueta), etiqueta


def test_marca_y_nombre_sin_textos_de_estado():
    t = una("$3.890\n$1.945 x kg\nPapa Malla 2 kg\nAgotado\nAgregar")
    assert (t["marca"], t["nombre"]) == ("", "Papa Malla 2 kg")
    t = una("$990\n$990 x kg\nSanta Ofertas\nCuisine & Co\nArroz Grado 2\nAgregar")
    assert (t["marca"], t["nombre"], t["etiqueta"]) == ("Cuisine & Co", "Arroz Grado 2", "Santa Ofertas")
    t = una("$990\n$990 x kg\nPatrocinado\nCuisine & Co\nArroz Grado 2\nAgregar")
    assert (t["marca"], t["nombre"]) == ("Cuisine & Co", "Arroz Grado 2")


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


def test_texto_de_html_como_el_innertext():
    # los saltos del código fuente dentro de un elemento en línea son espacios,
    # y lo que el navegador no muestra no cuenta
    html = ("<main><span>Lleva 2 por\n    $3.000</span><div>$1.990</div><div>$2.211 x lt</div>"
            "<a>Aceite Vegetal\n   900 ml</a><dialog><div>$5.555 x kg</div></dialog>"
            "<details><summary>Más</summary><div>$7.777 x kg</div></details>"
            "<div style='visibility: hidden'>$8.888 x kg</div></main>")
    texto, _ = pl.texto_de_html(html)
    assert texto == "Lleva 2 por $3.000\n$1.990\n$2.211 x lt\nAceite Vegetal 900 ml"
    t = una(texto)
    assert (t["precio"], t["precio_anterior"], t["nombre"]) == (1990, None, "Aceite Vegetal 900 ml")
    # la grilla en un segmento de React (<div hidden id="S:0">), fuera de <main>
    react = ("<body><main><h1>Resultados</h1><template id='B:0'></template><div>Cargando...</div>"
             "</main><div hidden id='S:0'><div>$3.890</div><div>$1.945 x kg</div><div>Marca</div>"
             "<div>Papa Malla 2 kg</div><button>Agregar</button></div></body>")
    texto, hubo_main = pl.texto_de_html(react)
    assert hubo_main and una(texto)["precio"] == 3890


def test_conteo_de_unidades_y_nombres_en_datos():
    html = ('<div>$1.945 x kg</div><div>$990<!-- --> x <!-- -->un</div><div>x lt</div>'
            '<script>{"productName":"Papa Granel","name":"Papas Fritas","nombre":"Tomate"}</script>')
    assert pl.contar_unidades(html) == {"kg": 1, "lt": 1, "un": 1}
    assert pl.nombres_en_datos(html, "papa") == ["Papa Granel", "Papas Fritas"]
    # la carga de Next con App Router lleva el JSON con las comillas escapadas
    rsc = '<script>self.__next_f.push([1,"{\\"name\\":\\"Papa Granel\\",\\"price\\":1990}"])</script>'
    assert pl.nombres_en_datos(rsc, "papa") == ["Papa Granel"]


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
    # Crawl-delay no cierra la lista de User-agent (RFC 9309 2.2.4): "*" comparte
    # grupo con el Disallow que sigue
    r = pl.Robots("User-agent: *\nCrawl-delay: 1\n\nUser-agent: GPTBot\nDisallow: /\n")
    assert not r.permite("/busqueda?ft=papa") and r.crawl_delay == 1.0
    assert pl.Robots("User-agent: *\nAllow: /\nCrawl-delay: 1\nDisallow: /api/\n").permite("/busqueda?ft=a")
    # un Allow con caracteres reservados codificados no se decodifica (2.2.2)
    assert not pl.Robots("User-agent: *\nDisallow: /busqueda\nAllow: /busqueda%3Fft=\n").permite(
        "/busqueda?ft=papa")


# ---------- bloqueos ----------

def test_bloqueos():
    assert pl.ver_bloqueo(403, {}, "", "", "", False) == "HTTP 403"
    assert pl.ver_bloqueo(429, {}, "", "", "", True) == "HTTP 429"
    # cualquier 4xx que no sea 404 ni 410: 405 es el captcha de AWS WAF y 406
    # el bloqueo de Fastly
    for estado in (400, 405, 406, 451):
        assert pl.ver_bloqueo(estado, {}, "", "", "", False) == f"HTTP {estado}"
    assert pl.ver_bloqueo(404, {}, "<main>No existe</main>", "No existe", "Búsqueda", False) is None
    assert pl.ver_bloqueo(200, {"CF-Mitigated": "challenge"}, "", "", "", False)
    assert pl.ver_bloqueo(202, {"x-amzn-waf-action": "challenge"}, "", "", "", False)
    assert pl.ver_bloqueo(200, {"X-Vercel-Mitigated": "challenge"}, "", "", "", True)
    assert pl.ver_bloqueo(202, {}, "<html></html>", "", "", False)      # 2xx raro, sin precios
    assert pl.ver_bloqueo(200, {}, "<html>", "Un momento", "Just a moment...", False)
    assert pl.ver_bloqueo(200, {}, '<div id="px-captcha"></div>', "Press & Hold", "", False)
    assert pl.ver_bloqueo(503, {}, "<script>cf_chl_opt={}</script>", "", "", False)
    # una página normal con productos y un reCAPTCHA en el pie no está bloqueada
    assert pl.ver_bloqueo(200, {}, '<script src="recaptcha/api.js">', "captcha", "Jumbo", True) is None
    # sin productos ni marcas de desafío: sin precios, no bloqueado
    assert pl.ver_bloqueo(200, {}, "<main>Sin resultados</main>", "No encontramos productos",
                          "Búsqueda", False) is None


def test_interstitials_chicos_que_llegan_con_200():
    imperva = ('<html><head><script src="/_Incapsula_Resource?SWJIYLWA=719d34d31c8e3a6e">'
               '</script></head><body></body></html>')
    f5 = ("<html><head><title>Request Rejected</title></head><body>The requested URL was "
          "rejected. Please consult with your administrator.<br>Your support ID is: 123</body></html>")
    tspd = ('<html><head><script src="/TSPD/08a1?type=9"></script></head><body><noscript>Please '
            'enable JavaScript to view the page content.<br/>Your support ID is: 1</noscript></body></html>')
    cookie = '<html><head><meta http-equiv="refresh" content="0;url=/busqueda?ft=papa"></head></html>'
    for html in (imperva, f5, tspd, cookie):
        texto, hubo_main = pl.texto_de_html(html)
        assert pl.ver_bloqueo(200, {}, html, texto, pl.titulo_de_html(html), False, hubo_main), html


def test_pagina_normal_sin_resultados_no_es_un_desafio():
    # trae el script de detección de Cloudflare, Turnstile y un aviso de reCAPTCHA,
    # como cualquier página normal: sin precios leídos, igual no es un bloqueo
    html = ("<html><head><title>Búsqueda</title>"
            "<script src='/cdn-cgi/challenge-platform/h/b/scripts/jsd/abc/main.js'></script>"
            "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script></head>"
            "<body><main><p>No encontramos resultados</p><form>Este sitio está protegido por "
            "reCAPTCHA</form></main>" + "<div>relleno</div>" * 3000 + "</body></html>")
    texto, hubo_main = pl.texto_de_html(html)
    assert pl.ver_bloqueo(200, {}, html, texto, "Búsqueda", False, hubo_main) is None
    # una página con productos que el lector no armó tampoco: trae "x kg"
    assert pl.hay_precios_en([], "<div>$990 x kg</div>")


# ---------- redirecciones ----------

def test_clasificar_salto():
    base = "https://www.santaisabel.cl"
    robots = pl.Robots(ROBOTS_SANTA)
    url = pl.url_busqueda(base, "papa")

    def c(destino, hechos=0):
        return pl.clasificar_salto(destino, robots, base, [url], hechos)

    assert c(base + "/busqueda?ft=papa&page=1") == (None, None)
    assert c(url)[0] == "bloqueado"                             # vuelve a la misma URL
    assert c("https://validate.perfdrive.com/captcha?ssa=1")[0] == "bloqueado"
    assert c(base + "/_sec/cp_challenge/verify")[0] == "bloqueado"
    fuera = "redirección fuera de lo permitido"
    assert c("https://www.jumbo.cl/busqueda?ft=papa") == (fuera, "lleva a otro sitio (https://www.jumbo.cl)")
    assert c(base + "/_next/data/x.json")[0] == fuera
    assert c(base + "/frutas/papa")[0] == fuera
    assert c(base + "/busquedas-populares")[0] == fuera
    assert c(base + "/busqueda/%2e%2e/api/x")[0] == fuera
    assert c(base + "/busqueda?ft=papa&page=2", hechos=2)[0] == fuera
    jumbo = "https://www.jumbo.cl"
    assert pl.clasificar_salto(jumbo + "/busqueda?ft=papa&sc=1", pl.Robots(ROBOTS_JUMBO), jumbo, [], 0) \
        == ("redirección no seguida", "robots.txt bloquea el destino")
    assert "redirección fuera de lo permitido" in pl.DETIENEN
    assert "redirección no seguida" not in pl.DETIENEN


# ---------- qué deja salir el navegador de la fase B ----------

def evento(url, tipo="Document", marco="M", redireccion=None):
    ev = {"request": {"url": url}, "resourceType": tipo, "frameId": marco, "requestId": "1"}
    if redireccion:
        ev["redirectedRequestId"] = redireccion
    return ev


def estado_b():
    return {"inicio": False, "saltos": [], "pedidas": [], "frenada": None, "extra": None}


def test_politica_del_navegador():
    base = "https://www.jumbo.cl"
    robots = pl.Robots(ROBOTS_JUMBO)
    decidir = pl.NavegadorB._decidir
    estado = estado_b()
    url = pl.url_busqueda(base, "papa")
    assert decidir(evento(url), "M", base, robots, estado) == "sale"           # la búsqueda
    for tipo in ("Stylesheet", "Script", "Image", "Font", "XHR", "Fetch", "Ping", "Other"):
        assert decidir(evento(base + "/estilo.css", tipo), "M", base, robots, estado) == "frena"
    assert decidir(evento("https://otro.cl/x", "Document", marco="F"), "M", base, robots, estado) == "frena"
    # redirección del servidor dentro de /busqueda y permitida: sale después de la pausa
    assert decidir(evento(url + "&x=1", redireccion="r1"), "M", base, robots, estado) == "salto"
    # a un destino que robots.txt bloquea: no sale, y el sitio sigue
    assert decidir(evento(url + "&sc=1", redireccion="r2"), "M", base, robots, estado) == "frena"
    assert estado["frenada"][0] == "redirección no seguida" and "robots.txt" in estado["frenada"][1]
    # a un captcha: no sale, y queda como bloqueo
    captcha = estado_b()
    decidir(evento(url), "M", base, robots, captcha)
    assert decidir(evento("https://validate.perfdrive.com/c", redireccion="r3"), "M", base, robots,
                   captcha) == "frena"
    assert captcha["frenada"][0] == "bloqueado"
    # otra navegación (meta refresh, Critical-CH): no sale; el navegador se queda donde está
    assert decidir(evento(base + "/busqueda?ft=otra"), "M", base, robots, estado) == "queda"
    assert estado["extra"] == base + "/busqueda?ft=otra"
    # la primera navegación tiene que ser una búsqueda del mismo sitio
    for malo in ("https://otro.cl/busqueda?ft=papa", base + "/papa?map=ft", base + "/api/x",
                 base + "/busquedas?ft=papa"):
        assert decidir(evento(malo), "M", base, robots, estado_b()) == "frena"


def test_chromium_por_http11_y_sin_proxy():
    lanzado = {}

    class Pagina:
        def evaluate(self, js):
            return "Mozilla/5.0 HeadlessChrome/153.0.0.0 Safari/537.36"

    class Contexto:
        def new_page(self):
            return Pagina()

        def close(self):
            pass

    class Navegador:
        version = "153.0.0.0"

        def new_context(self, **k):
            return Contexto()

    class Chromium:
        def launch(self, **k):
            lanzado.update(k)
            return Navegador()

    nav = pl.NavegadorB(types.SimpleNamespace(chromium=Chromium()))
    assert lanzado["headless"] is True
    assert {"--disable-http2", "--disable-quic", "--no-proxy-server"} <= set(lanzado["args"])
    assert nav.ua.endswith("HeadlessChrome/153.0.0.0 Safari/537.36 " + pl.UA_SUFIJO)
    assert nav.opciones["java_script_enabled"] is False


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
        assert tope.queda()
        tope.tomar()
    assert not tope.queda()
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
    assert wf.count("retention-days: 3") == 2 and "cat salida/resumen.md" in wf
    assert "schedule" not in wf and "pull_request" not in wf
    # un Re-run no vuelve a pedir: otra corrida exige un push nuevo
    assert "if: github.run_attempt == '1'" in wf
    disparos = wf.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in disparos
    if "push:" in disparos:                 # solo mientras dura la prueba, y solo esta rama
        ramas = re.search(r"branches:\n((?:\s+- .+\n)+)", disparos).group(1)
        assert re.findall(r"- (\S+)", ramas) == ["claude/prueba-supermercados"]


# ---------- fase A con una sesión falsa ----------

class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        assert s > 0
        self.t += s


class Crudo:
    """Imita r.raw de urllib3: entrega el cuerpo en trozos, o gotea."""

    def __init__(self, cuerpo, reloj=None, goteo=0.0):
        self.cuerpo, self.pos, self.reloj, self.goteo = cuerpo, 0, reloj, goteo

    def read1(self, n, decode_content=True):
        if self.goteo:
            self.reloj.t += self.goteo
            return b"x"
        trozo = self.cuerpo[self.pos:self.pos + n]
        self.pos += len(trozo)
        return trozo


class Respuesta:
    def __init__(self, estado, cuerpo="", cabeceras=None, raw=None):
        self.status_code = estado
        self.content = cuerpo.encode("utf-8")
        self.headers = {"content-type": "text/html; charset=utf-8", **(cabeceras or {})}
        self.raw = raw or Crudo(self.content)

    def close(self):
        pass


class Sesion:
    def __init__(self, reloj, log, respuesta):
        self.reloj, self.log, self.respuesta = reloj, log, respuesta
        self.headers = {"User-Agent": "python-requests/0 " + pl.UA_SUFIJO}
        self.cerrada = 0

    def get(self, url, timeout=None, allow_redirects=True, stream=False):
        assert allow_redirects is False     # ninguna redirección se sigue sola
        self.log.append(("A", url, self.reloj.t))
        self.reloj.t += 0.4
        return self.respuesta(url)

    def close(self):
        self.cerrada += 1


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj()
    monkeypatch.setattr(pl, "_reloj", r)
    monkeypatch.setattr(pl, "_dormir", r.dormir)
    return r


def una_fase_a(reloj, respuesta, termino="papa", robots=ROBOTS_SANTA):
    pytest.importorskip("requests")
    log = []
    sesion = Sesion(reloj, log, respuesta)
    ritmo, tope = pl.Ritmo(), pl.Tope()
    ritmo.pausas["s"] = pl.PAUSA
    base = "https://www.santaisabel.cl"
    p = pl.fase_a(sesion, base, termino, pl.Robots(robots), ritmo, "s", tope)
    return p, log, sesion, tope


def test_fase_a_salto_dentro_de_la_busqueda_cuenta_y_espera(reloj):
    def responder(url):
        if url.endswith("ft=papa"):
            return Respuesta(301, "", {"location": "/busqueda?ft=papa&page=1"})
        return Respuesta(200, html_busqueda("papa"))

    p, log, _, tope = una_fase_a(reloj, responder)
    assert [u for _, u, _ in log] == ["https://www.santaisabel.cl/busqueda?ft=papa",
                                      "https://www.santaisabel.cl/busqueda?ft=papa&page=1"]
    assert log[1][2] - log[0][2] >= pl.PAUSA + 0.4 - 1e-9
    assert (p["resultado"], p["saltos_seguidos"], tope.usados) == ("ok", 1, 1)
    assert p["pausas_saltos"] == [pytest.approx(pl.PAUSA)]


def test_fase_a_redireccion_a_un_captcha_o_a_la_misma_url(reloj):
    for destino in ("https://validate.perfdrive.com/captcha?ref=1", "/busqueda?ft=papa"):
        p, log, _, tope = una_fase_a(reloj, lambda url: Respuesta(302, "", {"location": destino}))
        assert len(log) == 1 and tope.usados == 0
        assert p["resultado"] == "bloqueado" and p["resultado"] in pl.DETIENEN


def test_fase_a_ruta_con_puntos_no_sale(reloj):
    p, log, _, _ = una_fase_a(reloj, lambda url: Respuesta(
        302, "", {"location": "https://www.santaisabel.cl/busqueda/../api/x"}))
    assert len(log) == 1 and p["resultado"] == "redirección fuera de lo permitido"
    assert p["redirecciones"] == ["https://www.santaisabel.cl/api/x"]


def test_fase_a_revisa_el_estado_antes_de_leer(reloj, monkeypatch):
    def roto(texto, tope=8):
        raise ValueError("el lector se cayó")

    monkeypatch.setattr(pl, "leer_tarjetas", roto)
    p, _, _, _ = una_fase_a(reloj, lambda url: Respuesta(403, "Access Denied. Ref $1.234.56"))
    assert (p["resultado"], p["detalle"]) == ("bloqueado", "HTTP 403")
    p, _, _, _ = una_fase_a(reloj, lambda url: Respuesta(200, html_busqueda("papa")))
    assert p["resultado"] == "ok" and "leer las tarjetas" in p["avisos"][0]


def test_fase_a_respuesta_informativa_y_goteo(reloj):
    p, _, sesion, _ = una_fase_a(reloj, lambda url: Respuesta(103, "", {"link": "</a.css>; rel=preload"}))
    assert p["resultado"] == "sin página" and sesion.cerrada == 1
    p, _, _, _ = una_fase_a(reloj, lambda url: Respuesta(200, raw=Crudo(b"", reloj, goteo=1.0)))
    assert p["resultado"] == "sin respuesta" and "no terminó" in p["detalle"]


def bajar(reloj, respuesta):
    pytest.importorskip("requests")
    log = []
    ritmo = pl.Ritmo()
    ritmo.pausas["s"] = pl.PAUSA
    info, rob = pl.bajar_robots(Sesion(reloj, log, respuesta), "https://www.santaisabel.cl", ritmo, "s")
    return info, rob, log


def test_bajar_robots(reloj):
    # UTF-8 con BOM aunque el servidor diga ISO-8859-1: las reglas cuentan
    bom = "﻿User-agent: *\nDisallow: /busqueda\n"
    info, rob, _ = bajar(reloj, lambda url: Respuesta(200, bom, {"content-type": "text/plain; charset=ISO-8859-1"}))
    assert info["resultado"] == "ok" and not rob.permite("/busqueda?ft=papa")
    # 404: no hay robots.txt, no hay reglas
    info, rob, _ = bajar(reloj, lambda url: Respuesta(404, "<html>no existe</html>"))
    assert info["resultado"] == "ok" and rob.permite("/busqueda?ft=papa")
    # un HTML en vez del archivo, o un estado raro: el sitio no se prueba
    for r in (Respuesta(200, "<html><body><h1>Jumbo</h1>" + "x" * 30000 + "</body></html>"),
              Respuesta(405, "", {"x-amzn-waf-action": "captcha"}), Respuesta(204, "")):
        info, rob, _ = bajar(reloj, lambda url, r=r: r)
        assert rob is None and info["resultado"] in ("bloqueado", "no se pudo leer"), info
    # un robots.txt que prohíbe la ruta de un desafío no es un desafío
    info, rob, _ = bajar(reloj, lambda url: Respuesta(200, "User-agent: *\nDisallow: /_sec/cp_challenge/\n",
                                                      {"content-type": "text/plain"}))
    assert info["resultado"] == "ok" and rob is not None
    # redirecciones: dentro del sitio se siguen con pausa; a otro sitio o a /_next/, no
    def salta(url):
        if url.endswith("/r2/robots.txt"):
            return Respuesta(200, ROBOTS_SANTA, {"content-type": "text/plain"})
        return Respuesta(301, "", {"location": "/r2/robots.txt"})

    info, rob, log = bajar(reloj, salta)
    assert rob is not None and info["pedidos_http"] == 2 and log[1][2] - log[0][2] >= pl.PAUSA
    for destino in ("https://otro.cl/robots.txt", "/_next/static/robots.txt"):
        info, rob, log = bajar(reloj, lambda url, d=destino: Respuesta(302, "", {"location": d}))
        assert rob is None and len(log) == 1 and info["resultado"] == "no se pudo leer"


# ---------- una corrida entera, con sesión y navegador falsos ----------

def html_busqueda(termino: str) -> str:
    return (f"<html><head><title>{termino}</title><script>var clave = 'secreta';</script></head>"
            f"<body><main><div>Filtros</div><div>$1.990</div><div>$995 x kg</div><p>Marca</p>"
            f"<h2>{termino.title()} 1 kg</h2><button>Agregar</button></main></body></html>")


class Navegador:
    """Reemplaza a NavegadorB: anota cada pedido y devuelve una página leída."""
    log, reloj, bloquear, frenar, falla = None, None, (), (), None

    def __init__(self, pw):
        if Navegador.falla:
            raise Navegador.falla
        self.ua = "Mozilla/5.0 HeadlessChrome/1 " + pl.UA_SUFIJO
        self.version = "1"

    def pedir(self, base, termino, robots, ritmo=None, sitio=None, tope=None):
        url = pl.url_busqueda(base, termino)
        assert robots.permite(pl.ruta_de(url))
        self.log.append(("B", url, self.reloj.t))
        self.reloj.t += 1.5
        if any(b in url for b in self.bloquear):
            return {"url": url, "estado": 403, "bytes": 10, "dur": 1.5, "resultado": "bloqueado",
                    "detalle": "HTTP 403", "tarjetas": [], "texto": "Access Denied",
                    "redirecciones": [], "subpedidos": {"salieron": 1, "frenados": {}}}
        html = html_busqueda(termino)
        texto = pl.texto_de_html(html)[0]
        p = {"url": url, "estado": 200, "bytes": 900, "dur": 1.5, "resultado": "ok",
             "detalle": "con precios", "tarjetas": pl.leer_tarjetas(texto), "texto": texto,
             "html": html, "redirecciones": [], "saltos_seguidos": 0,
             "subpedidos": {"salieron": 1, "frenados": {"Stylesheet": 2}}}
        if any(b in url for b in self.frenar):
            p["frena_sitio"] = "llegó un 103 Early Hints (Link: </_next/a.css>)"
        return p

    def cerrar(self):
        pass


@pytest.fixture
def corrida_falsa(monkeypatch, tmp_path, reloj):
    pytest.importorskip("requests")
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

    def correr(respuesta, bloquear_b=(), frenar_b=(), saltar=(), falla_nav=None):
        monkeypatch.setattr(pl, "sesion_a", lambda: Sesion(reloj, log, respuesta))
        Navegador.bloquear, Navegador.frenar, Navegador.falla = bloquear_b, frenar_b, falla_nav
        salida = str(tmp_path / "salida")
        corrida = pl.correr(salida, dict(pl.SITIOS), pl.PAUSA, set(saltar))
        pl.escribir_salidas(salida, corrida)
        return corrida, log, salida

    return correr


def responder_normal(url):
    if url.endswith("/robots.txt"):
        return Respuesta(200, ROBOTS_SANTA if "santaisabel" in url else ROBOTS_JUMBO,
                         {"content-type": "text/plain"})
    termino = url.split("ft=", 1)[1].split("&")[0].replace("%20", " ")
    return Respuesta(200, html_busqueda(termino))


def revisar_ritmo(log):
    """robots.txt antes que nada, uno a la vez y 5 s o más entre pedidos a un sitio."""
    for sitio in pl.SITIOS:
        propios = [(fase, url, t) for fase, url, t in log if sitio in url]
        if not propios:
            continue
        assert propios[0][1].endswith("/robots.txt")
        for (_, _, t1), (_, _, t2) in zip(propios, propios[1:]):
            # el pedido anterior dura 0,4 s (fase A) o 1,5 s (fase B)
            assert t2 - t1 >= pl.PAUSA + 0.4 - 1e-9
    tiempos = [t for _, _, t in log]
    assert tiempos == sorted(tiempos)


def leer_resumen(salida):
    with open(os.path.join(salida, "resumen.md"), encoding="utf-8") as fh:
        resumen = fh.read()
    assert infracciones(resumen) == []
    return resumen


def test_corrida_completa(corrida_falsa):
    corrida, log, salida = corrida_falsa(responder_normal)
    busquedas = [x for x in log if "/busqueda" in x[1]]
    assert len(busquedas) == 32 == corrida["busquedas_pedidas"]
    assert {f for f, _, _ in busquedas} == {"A", "B"}
    assert corrida["terminada"] and "en_curso" not in corrida
    revisar_ritmo(log)
    with open(os.path.join(salida, "resultado.csv"), encoding="utf-8") as fh:
        filas = list(csv.reader(fh))
    assert filas[0] == ["sitio", "fase", "término", "posición", "nombre", "marca", "precio",
                        "precio_unidad", "unidad", "oferta"]
    assert len(filas) == 1 + 32
    assert filas[1] == ["jumbo.cl", "A", "posta paleta", "1", "Posta Paleta 1 kg", "Marca",
                        "1990", "995", "kg", ""]
    resumen = leer_resumen(salida)
    assert "| jumbo.cl | A, pedido simple | 8 de 8 | 200 en las 8 | sí, en 8 de 8 | no |" in resumen
    assert "| santaisabel.cl | B, navegador sin interfaz | 8 de 8 | 200 en las 8 | sí, en 8 de 8 | no |" in resumen
    assert "| santaisabel.cl | 200 | 1,0 s | 4 Disallow y 1 Allow para * | permitidas en las 8 |" in resumen
    assert "Pedidos de búsqueda: 32 de un tope de 32, uno a la vez, más 2 de robots.txt." in resumen
    assert "por HTTP/1.1" in resumen
    # crudo/: el texto de cada página y su HTML, sin el contenido de los scripts
    crudo = os.listdir(os.path.join(salida, "crudo"))
    assert sum(n.endswith(".txt") for n in crudo) == 32 == sum(n.endswith(".html.gz") for n in crudo)
    with gzip.open(os.path.join(salida, "crudo", "A_jumbo.cl_04_papa.html.gz"), "rt",
                   encoding="utf-8") as fh:
        guardado = fh.read()
    assert "<script></script>" in guardado and "secreta" not in guardado and "Papa 1 kg" in guardado
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
    resumen = leer_resumen(salida)
    assert '| santaisabel.cl | A, pedido simple | 4 de 8 | 200 en 3, 403 en 1 | sí, en 3 de 4 |' \
        ' sí: HTTP 403 en "papa" |' in resumen
    assert "| santaisabel.cl | B, navegador sin interfaz | 0 de 8 | no se pidió: el sitio quedó " \
        "frenado en la fase A | no | no se probó: el sitio quedó frenado en la fase A (bloqueado) |" in resumen
    assert "AkamaiGHost" in resumen


def test_un_bloqueo_en_la_fase_b(corrida_falsa):
    corrida, log, _ = corrida_falsa(responder_normal, bloquear_b=("jumbo.cl/busqueda?ft=arroz",))
    jumbo_b = [u for f, u, _ in log if f == "B" and "jumbo" in u]
    assert len(jumbo_b) == 3 and jumbo_b[-1].endswith("ft=arroz%20grado%202")
    assert len([1 for f, u, _ in log if f == "B" and "santaisabel" in u]) == 8


def test_un_103_en_la_fase_b_frena_al_sitio(corrida_falsa):
    corrida, log, salida = corrida_falsa(responder_normal, frenar_b=("jumbo.cl/busqueda?ft=trutro",))
    jumbo_b = [u for f, u, _ in log if f == "B" and "jumbo" in u]
    assert len(jumbo_b) == 2
    assert corrida["frenados"]["jumbo.cl"]["resultado"] == "frenado por la prueba"
    assert "la prueba frenó al sitio" in leer_resumen(salida)


def test_saltos_de_redireccion_cuentan_en_el_tope(corrida_falsa):
    def responder(url):
        if "jumbo" in url and url.endswith("ft=papa"):
            return Respuesta(301, "", {"location": url + "&page=1"})
        return responder_normal(url)

    corrida, log, salida = corrida_falsa(responder)
    busquedas = [x for x in log if "/busqueda" in x[1]]
    assert len(busquedas) == 32 == corrida["busquedas_pedidas"]       # nunca más de 32
    revisar_ritmo(log)
    ultima = [p for p in corrida["pedidos"] if p["fase"] == "B"][-1]
    assert (ultima["resultado"], ultima["detalle"]) == ("no se pidió", "se llegó al tope de 32 pedidos")
    resumen = leer_resumen(salida)
    assert ("Pedidos de búsqueda: 32 de un tope de 32, uno a la vez (1 de ellos, saltos de "
            "redirección dentro de /busqueda, cada uno con su pausa)") in resumen
    assert "redirigió a /busqueda?ft=papa&page=1; se siguieron 1" in resumen


def test_redireccion_a_un_captcha_o_a_otro_sitio_frena(corrida_falsa):
    def responder(url):
        if "santaisabel" in url and "ft=tomate" in url:
            return Respuesta(302, "", {"location": "https://validate.perfdrive.com/captcha?r=1"})
        if "jumbo" in url and "ft=cebolla" in url:
            return Respuesta(302, "", {"location": "https://www.otro.cl/busqueda?ft=cebolla"})
        return responder_normal(url)

    corrida, log, salida = corrida_falsa(responder)
    santa = [u for _, u, _ in log if "santaisabel" in u]
    assert santa[-1].endswith("ft=tomate") and len(santa) == 1 + 5
    jumbo = [u for _, u, _ in log if "jumbo" in u]
    assert jumbo[-1].endswith("ft=cebolla") and len(jumbo) == 1 + 6
    assert not any("perfdrive" in u or "otro.cl" in u for _, u, _ in log)
    resumen = leer_resumen(salida)
    assert 'sí: https://validate.perfdrive.com/captcha?r=1: redirige a una página de desafío en "tomate"' in resumen
    assert 'posible: redirección fuera de lo permitido en "cebolla"' in resumen


def test_robots_que_no_responde_o_no_se_puede_leer_frena_al_sitio(corrida_falsa):
    def responder(url):
        if url == "https://www.jumbo.cl/robots.txt":
            return Respuesta(503, "caído")
        if url == "https://www.santaisabel.cl/robots.txt":
            return Respuesta(200, "<html><body>Santa Isabel</body></html>" + " " * 30000)
        return responder_normal(url)

    corrida, log, salida = corrida_falsa(responder)
    assert [u for _, u, _ in log] == ["https://www.jumbo.cl/robots.txt",
                                      "https://www.santaisabel.cl/robots.txt"]
    assert corrida["frenados"]["jumbo.cl"]["fase"] == "robots"
    assert corrida["frenados"]["santaisabel.cl"]["resultado"] == "no se pudo leer"
    resumen = leer_resumen(salida)
    assert "| jumbo.cl | 503 | sin dato |" in resumen
    assert "no se pidió: sin robots.txt que se pudiera usar" in resumen


def test_robots_que_bloquea_un_termino(corrida_falsa):
    def responder(url):
        if url == "https://www.santaisabel.cl/robots.txt":
            return Respuesta(200, "User-agent: *\nDisallow: /busqueda?ft=papa\n", {"content-type": "text/plain"})
        return responder_normal(url)

    corrida, log, salida = corrida_falsa(responder)
    assert not any("santaisabel" in u and "ft=papa" in u for _, u, _ in log)
    assert "| 1 Disallow y 0 Allow para * | permitidas en 7 de 8 |" in leer_resumen(salida)


def test_chromium_que_no_parte_no_pide_nada(corrida_falsa):
    corrida, log, salida = corrida_falsa(responder_normal, falla_nav=RuntimeError("sin Chromium"))
    assert log == [] and corrida["busquedas_pedidas"] == 0
    resumen = leer_resumen(salida)
    assert "Chromium no partió, así que no se pidió nada" in resumen
    assert "| jumbo.cl | A, pedido simple | 0 de 8 | no se pidió: Chromium no partió |" in resumen


def test_saltar_un_sitio(corrida_falsa):
    corrida, log, salida = corrida_falsa(responder_normal, saltar={"jumbo.cl"})
    assert not any("jumbo" in u for _, u, _ in log)
    assert len([1 for _, u, _ in log if "santaisabel" in u and "/busqueda" in u]) == 16
    resumen = leer_resumen(salida)
    assert "| jumbo.cl | A, pedido simple | 0 de 8 | no se pidió: se saltó a pedido |" in resumen
    assert "Sin pedirles nada, a pedido: jumbo.cl." in resumen


def test_una_corrida_cortada_se_rehace_desde_crudo(monkeypatch, tmp_path, reloj):
    pytest.importorskip("requests")
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
    Navegador.log, Navegador.reloj, Navegador.falla = log, reloj, None
    monkeypatch.setattr(pl, "NavegadorB", Navegador)

    def responder(url):
        if "santaisabel" in url and "ft=papa" in url:
            raise KeyboardInterrupt         # un cancel o el límite de tiempo del job
        return responder_normal(url)

    monkeypatch.setattr(pl, "sesion_a", lambda: Sesion(reloj, log, responder))
    salida = str(tmp_path / "salida")
    with pytest.raises(KeyboardInterrupt):
        pl.correr(salida, dict(pl.SITIOS), pl.PAUSA)
    with open(os.path.join(salida, "corrida.json"), encoding="utf-8") as fh:
        guardada = json.load(fh)
    assert guardada["terminada"] is False and guardada["busquedas_pedidas"] == 8
    pl.releer(salida)                       # lo que hace el workflow si no hay resumen.md
    resumen = leer_resumen(salida)
    assert "La corrida se cortó antes de terminar" in resumen
    assert 'El pedido de "papa" a santaisabel.cl (fase A) salió a las' in resumen
    assert "Pedidos de búsqueda: 8 de un tope de 32" in resumen
    assert "no alcanzó a pedirse: la corrida se cortó" in resumen


def test_fuera_de_actions_no_toca_a_los_supermercados(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    llamadas = []
    monkeypatch.setattr(pl, "correr", lambda *a, **k: llamadas.append(a))
    assert pl.main(["--salida", str(tmp_path)]) == 2
    assert pl.main(["--salida", str(tmp_path), "--base", "jumbo.cl=http://127.0.0.1:9"]) == 2
    assert pl.main(["--salida", str(tmp_path), "--saltar", "jumbo.cl"]) == 2
    assert llamadas == []

"""
tarjetas.py - las og:image de 1200 x 630 que muestran WhatsApp y las redes
=========================================================================
build_site.py las genera en cada build: una por ficha de producto, una por
índice y una para la portada, en og/, más la genérica (og.png) y el ícono de
iOS (apple-touch-icon.png). Cada tarjeta lleva el nombre, el precio
de la semana, la frase de su veredicto ("Más caro que en 7 de los últimos 10
septiembres, aun descontando la inflación", o con menos de 5 años de ese mes
"Más caro que en 8 de cada 10 semanas desde 2008, descontada la inflación"),
la fecha de la semana y la marca. Las de producto y de índice llevan además,
a la derecha, el gráfico de su serie ajustada por inflación de los últimos
años, con el punto de esta semana (si la serie es muy corta, van sin él).

Aquí solo se dibuja: las frases y las cifras las arma build_site.py (ahí las
revisa la guardia de texto). Colores: los tokens de CSS_BASE, que build_site
pasa en 'tok'. Fuentes: las del sitio, en fuentes/ (IBM Plex y Space
Grotesk, licencia SIL Open Font License, ver fuentes/OFL-*.txt).

Requiere Pillow.
"""
import datetime
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

ANCHO, ALTO = 1200, 630
MARGEN = 64
# La marca: la Í de CARESTÍA lleva, en vez de la tilde, una línea de precio
# que sube. Sus puntos van en una caja de 52 por 30 y su trazo es 7. Respecto
# de la I, en em del wordmark: la caja mide 0.46 por 0.27 y su esquina de
# arriba a la izquierda va 0.07 a la izquierda de la I y 0.21 sobre el tope de
# su caja (la de line-height 1).
LINEA = ((4, 26), (18, 12), (28, 19), (48, 2))
LINEA_CAJA = (52, 30)
LINEA_TRAZO = 7
# dibujos a 8x que después se reducen: bordes suaves en el trazo y la barra
SUPER = 8
# La tarjeta con gráfico: el texto en una columna de COLUMNA px a la
# izquierda y el gráfico en la caja GRAFICO (x0, y0, x1, y1) a la derecha.
# Con menos de MIN_PUNTOS semanas con precio no hay gráfico. Entre dos semanas
# con precio separadas por más de HUECO_DIAS, la línea se corta. El gráfico
# se dibuja a GRAF_SUPER x (la capa es grande: 8x sería lento en un build
# de más de cien tarjetas).
COLUMNA = 500
GRAFICO = (624, 206, 1136, 486)
MIN_PUNTOS = 26
HUECO_DIAS = 63
GRAF_SUPER = 4
CARPETA_FUENTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuentes")
ARCHIVOS = {
    "display": "SpaceGrotesk-Bold.ttf",
    "sans": "IBMPlexSans-Regular.ttf",
    "sans-semi": "IBMPlexSans-SemiBold.ttf",
    "mono": "IBMPlexMono-Medium.ttf",
}
_cache = {}


def fuente(familia: str, tam: int) -> ImageFont.FreeTypeFont:
    clave = (familia, tam)
    if clave not in _cache:
        _cache[clave] = ImageFont.truetype(
            os.path.join(CARPETA_FUENTES, ARCHIVOS[familia]), tam)
    return _cache[clave]


def _rgb(hexa: str) -> tuple:
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


def _carpeta(ruta: str) -> None:
    """Crea la carpeta de 'ruta' si hace falta (og.png va en la raíz)."""
    if os.path.dirname(ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)


def trazo(d: ImageDraw.ImageDraw, pts, ancho: float, color) -> None:
    """Polilínea con extremos y uniones redondeados (los round de SVG): cada
    tramo es un trazo recto y cada punto, un círculo del ancho del trazo. La
    caja de ellipse incluye su último píxel: va uno menos para que el círculo
    mida lo mismo que el trazo."""
    r = ancho / 2
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=color, width=round(ancho))
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r - 1, y + r - 1], fill=color)


class Lienzo:
    def __init__(self, tok: dict):
        self.tok = {k: _rgb(v) for k, v in tok.items() if v.startswith("#")}
        self.img = Image.new("RGB", (ANCHO, ALTO), self.tok["bg"])
        self.d = ImageDraw.Draw(self.img)

    # ---- texto ----
    def ancho(self, texto: str, f, espacio: float = 0) -> float:
        if not espacio:
            return self.d.textlength(texto, font=f)
        return sum(self.d.textlength(c, font=f) for c in texto) + espacio * (len(texto) - 1)

    def texto(self, xy, texto: str, f, color: str, espacio: float = 0, ancla="ls"):
        """Texto con su línea base en y (ancla 'ls'); con 'espacio', letra a
        letra (el letter-spacing del sitio)."""
        x, y = xy
        if ancla[0] == "r":
            x -= self.ancho(texto, f, espacio)
            ancla = "l" + ancla[1]
        if not espacio:
            self.d.text((x, y), texto, font=f, fill=self.tok[color], anchor=ancla)
            return
        for c in texto:
            self.d.text((x, y), c, font=f, fill=self.tok[color], anchor=ancla)
            x += self.d.textlength(c, font=f) + espacio

    def lineas(self, texto: str, f, ancho_max: float) -> list:
        """Corta el texto en líneas que caben en ancho_max (por palabras)."""
        out, actual = [], ""
        for palabra in texto.split():
            prueba = f"{actual} {palabra}".strip()
            if actual and self.ancho(prueba, f) > ancho_max:
                out.append(actual)
                actual = palabra
            else:
                actual = prueba
        if actual:
            out.append(actual)
        return out

    def ajustar(self, texto: str, familia: str, tams, ancho_max: float, max_lineas: int):
        """La fuente más grande de 'tams' con la que el texto entra en
        max_lineas líneas; si ninguna alcanza, la más chica."""
        for tam in tams:
            f = fuente(familia, tam)
            ls = self.lineas(texto, f, ancho_max)
            if len(ls) <= max_lineas:
                return f, ls
        return f, ls[:max_lineas]

    # ---- piezas comunes ----
    def linea(self, x: float, y: float, escala: float, color: str = "ember"):
        """La línea de la marca con la esquina de arriba a la izquierda de su
        caja en (x, y) y 'escala' píxeles por unidad. Se dibuja a 8x en una
        capa del tamaño de la línea y se reduce: bordes suaves."""
        r = LINEA_TRAZO * escala / 2
        pts = [(x + px * escala, y + py * escala) for px, py in LINEA]
        izq = math.floor(min(p[0] for p in pts) - r) - 1
        arr = math.floor(min(p[1] for p in pts) - r) - 1
        ancho = math.ceil(max(p[0] for p in pts) + r) + 1 - izq
        alto = math.ceil(max(p[1] for p in pts) + r) + 1 - arr
        capa = Image.new("L", (ancho * SUPER, alto * SUPER), 0)
        trazo(ImageDraw.Draw(capa), [((px - izq) * SUPER, (py - arr) * SUPER) for px, py in pts],
              LINEA_TRAZO * escala * SUPER, 255)
        capa = capa.reduce(SUPER)
        self.img.paste(Image.new("RGB", capa.size, self.tok[color]), (izq, arr), capa)

    def marca(self, tam: int = 34, y: int = 92, x: float = MARGEN):
        """El wordmark CARESTÍA en hueso, con la línea de precio que sube en
        brasa en vez de la tilde de la Í (como el sitio y el favicon): la I va
        sin tilde y la línea, en su lugar (ver LINEA)."""
        f = fuente("display", tam)
        esp = tam * 0.06
        for c in "CARESTIA":
            self.d.text((x, y), c, font=f, fill=self.tok["bone"], anchor="ls")
            if c == "I":
                # tope de la caja de la I con line-height 1: el medio de la
                # fuente (ascendente más descendente) queda al medio de la caja
                asc, desc = f.getmetrics()
                tope = y - (asc - desc + tam) / 2
                # la caja de 0.46 por 0.27 em con la línea centrada adentro
                escala = 0.46 * tam / LINEA_CAJA[0]
                self.linea(x - 0.07 * tam,
                           tope - 0.21 * tam + (0.27 * tam - LINEA_CAJA[1] * escala) / 2, escala)
            x += self.d.textlength(c, font=f) + esp

    def fecha(self, texto: str, y: int = 92):
        self.texto((ANCHO - MARGEN, y), texto.upper(), fuente("mono", 20), "ash",
                   espacio=2.4, ancla="rs")

    def pie(self, fuente_txt: str, sitio: str):
        self.d.line([(MARGEN, 548), (ANCHO - MARGEN, 548)], fill=self.tok["line"], width=2)
        self.texto((MARGEN, 590), fuente_txt, fuente("sans", 22), "ash")
        self.texto((ANCHO - MARGEN, 590), sitio, fuente("display", 26), "bone", ancla="rs")

    def pildora(self, x: float, y_base: float, texto: str, color: str, tam: int = 22) -> float:
        """Píldora del veredicto (solo índices), con la línea base de su texto
        en y_base. Devuelve su ancho."""
        f = fuente("mono", tam)
        esp = tam * 0.08
        w = self.ancho(texto, f, esp) + 2 * tam * 0.8
        alto = tam * 1.7
        arriba = y_base - tam * 1.18
        self.d.rounded_rectangle([x, arriba, x + w, arriba + alto], radius=alto / 2,
                                 fill=self.tok[color])
        self.texto((x + tam * 0.8, y_base), texto, f, "bg", espacio=esp)
        return w

    def ancho_pildora(self, texto: str, tam: int = 22) -> float:
        """El ancho que tendrá la píldora, sin dibujarla."""
        return self.ancho(texto, fuente("mono", tam), tam * 0.08) + 2 * tam * 0.8

    def punto(self, x: float, y: float, r: float, color: str):
        """Un círculo de radio r con centro en (x, y), dibujado a 8x en una capa
        de su tamaño y reducido: bordes suaves."""
        izq, arr = math.floor(x - r) - 1, math.floor(y - r) - 1
        lado = math.ceil(2 * r) + 3
        capa = Image.new("L", (lado * SUPER, lado * SUPER), 0)
        cx, cy, rs = (x - izq) * SUPER, (y - arr) * SUPER, r * SUPER
        ImageDraw.Draw(capa).ellipse([cx - rs, cy - rs, cx + rs, cy + rs], fill=255)
        capa = capa.reduce(SUPER)
        self.img.paste(Image.new("RGB", capa.size, self.tok[color]), (izq, arr), capa)

    def grafico(self, puntos: list, leyenda: str = "", caja: tuple = GRAFICO):
        """El gráfico de la tarjeta, en 'caja': la serie de 'puntos' (pares
        [fecha ISO, valor], en orden) en brasa, como en el sitio, con un área
        suave debajo; una línea punteada a la altura de la última semana, para
        ver de un vistazo cuánto de la historia queda bajo el precio de hoy; y
        el punto de esa semana. Abajo, el eje con una marca por año y el
        primero y el último año; arriba, la leyenda. Sin escala de precios: el
        precio de la semana va en grande a la izquierda."""
        x0, y0, x1, y1 = caja
        ancho, alto = x1 - x0, y1 - y0
        fechas = [datetime.date.fromisoformat(f) for f, _v in puntos]
        vals = [float(v) for _f, v in puntos]
        dias = max((fechas[-1] - fechas[0]).days, 1)
        bajo, alto_v = min(vals), max(vals)
        if alto_v - bajo < 1e-9:
            bajo, alto_v = bajo - 1, alto_v + 1
        holgura = (alto_v - bajo) * 0.1
        bajo, alto_v = bajo - holgura, alto_v + holgura

        def px(f, v):
            return (x0 + (f - fechas[0]).days / dias * ancho,
                    y0 + (alto_v - v) / (alto_v - bajo) * alto)

        tramos, previa = [[]], None
        for f, v in zip(fechas, vals):
            if previa is not None and (f - previa).days > HUECO_DIAS:
                tramos.append([])
            tramos[-1].append(px(f, v))
            previa = f
        if leyenda:
            self.texto((x0, 178), leyenda.upper(), fuente("mono", 18), "ash", espacio=2.2)
        # el eje, una marca por cada 1 de enero y los años de los extremos
        self.d.line([(x0, y1), (x1, y1)], fill=self.tok["line"], width=2)
        for anio in range(fechas[0].year + 1, fechas[-1].year + 1):
            xm = round(px(datetime.date(anio, 1, 1), bajo)[0])
            self.d.line([(xm, y1), (xm, y1 + 8)], fill=self.tok["line"], width=2)
        f_anio = fuente("mono", 20)
        self.texto((x0, y1 + 36), str(fechas[0].year), f_anio, "ash")
        if fechas[-1].year != fechas[0].year:
            self.texto((x1, y1 + 36), str(fechas[-1].year), f_anio, "ash", ancla="rs")
        # el área y la línea, en capas a GRAF_SUPER x con un margen para los
        # bordes redondeados del trazo, reducidas y pegadas en brasa
        m, s = 16, GRAF_SUPER
        tam_capa = ((ancho + 2 * m) * s, (alto + 2 * m) * s)
        area, linea = Image.new("L", tam_capa, 0), Image.new("L", tam_capa, 0)
        d_area, d_linea = ImageDraw.Draw(area), ImageDraw.Draw(linea)
        piso = (alto + m) * s
        for tramo in tramos:
            pts = [((x - x0 + m) * s, (y - y0 + m) * s) for x, y in tramo]
            if len(pts) > 1:
                d_area.polygon(pts + [(pts[-1][0], piso), (pts[0][0], piso)], fill=255)
            trazo(d_linea, pts, 4 * s, 255)
        area, linea = area.reduce(s), linea.reduce(s)
        # el área se desvanece hacia abajo: un 32% de brasa arriba, nada en el eje
        degradado = Image.linear_gradient("L").rotate(180).resize(area.size)
        alfa = ImageChops.multiply(area, degradado.point(lambda a: round(a * 0.32)))
        brasa = Image.new("RGB", area.size, self.tok["ember"])
        self.img.paste(brasa, (x0 - m, y0 - m), alfa)
        # la punteada a la altura de esta semana, bajo la línea
        xu, yu = tramos[-1][-1]
        xp = x0
        while xp < x1:
            self.d.line([(xp, round(yu)), (min(xp + 10, x1), round(yu))],
                        fill=self.tok["dim"], width=2)
            xp += 18
        self.img.paste(brasa, (x0 - m, y0 - m), linea)
        # el punto de esta semana, con un anillo del fondo que lo separa
        self.punto(xu, yu, 13, "bg")
        self.punto(xu, yu, 8, "ember")

    def guardar(self, ruta: str):
        _carpeta(ruta)
        # compresión 6 sin optimize: la mitad del tiempo y casi el mismo peso
        self.img.save(ruta, "PNG", compress_level=6)


def ficha(ruta: str, tok: dict, *, antetitulo: str, nombre: str, precio: str,
          unidad: str, frase: str, fecha: str, fuente_txt: str, sitio: str,
          veredicto: str = None, color_veredicto: str = None, nota: str = None,
          serie: list = None, leyenda: str = "") -> None:
    """La tarjeta de un producto o de un índice: antetítulo, nombre, precio
    con su unidad (y, en los índices, la píldora del veredicto), la frase, la
    'nota' (índices: la regla de las dos semanas) y el pie con la fuente y la
    marca. Con 'serie' (pares [fecha ISO, valor] de la serie ajustada por
    inflación) y al menos MIN_PUNTOS semanas, el texto va en una columna a la
    izquierda y el gráfico a la derecha, con 'leyenda' encima; si no, el
    texto ocupa todo el ancho, como antes del gráfico."""
    c = Lienzo(tok)
    c.marca()
    c.fecha(fecha)
    texto = {"antetitulo": antetitulo, "nombre": nombre, "precio": precio,
             "unidad": unidad, "frase": frase, "veredicto": veredicto,
             "color_veredicto": color_veredicto, "nota": nota}
    if serie and len(serie) >= MIN_PUNTOS:
        # los tamaños más grandes con que la columna no toca el pie
        k = next((k for k in (1, 0.92, 0.85, 0.78) if _columna(c, texto, k) <= 528), 0.72)
        _columna(c, texto, k, dibujar=True)
        c.grafico(serie, leyenda)
    else:
        _ancho_completo(c, texto)
    c.pie(fuente_txt, sitio)
    c.guardar(ruta)


def _columna(c: Lienzo, t: dict, k: float, dibujar: bool = False) -> float:
    """El texto de la tarjeta con gráfico, en una columna de COLUMNA px: el
    antetítulo (con la letra que quepa en una línea), el nombre (en una línea
    o, si no cabe, en dos más chicas), el precio con la unidad y la píldora a
    su lado o, si no caben, debajo, la frase (hasta 3 líneas, o 4 más
    chicas) y la nota en gris. Los tamaños van por k (1, los más grandes).
    Devuelve la línea base de lo último; con dibujar=False solo mide."""
    x, y = MARGEN, 178
    ante = t["antetitulo"].upper()
    for tam in (20, 18, 16):
        f_ant = fuente("mono", tam)
        if c.ancho(ante, f_ant, tam * 0.14) <= COLUMNA:
            break
    if dibujar:
        c.texto((x, y), ante, f_ant, "ash", espacio=tam * 0.14)
    escala = lambda tams: tuple(round(s * k) for s in tams)  # noqa: E731
    f_nom, l_nom = c.ajustar(t["nombre"], "sans-semi", escala((56, 50, 44)), COLUMNA, 1)
    if len(c.lineas(t["nombre"], f_nom, COLUMNA)) > 1:
        f_nom, l_nom = c.ajustar(t["nombre"], "sans-semi", escala((46, 42, 38)), COLUMNA, 2)
    y += 18
    for linea in l_nom:
        y += int(f_nom.size * 1.12)
        if dibujar:
            c.texto((x, y), linea, f_nom, "bone")
    f_pre = fuente("display", round((104 if len(l_nom) == 1 else 88) * k))
    y += int(f_pre.size * 1.08)
    if dibujar:
        c.texto((x, y), t["precio"], f_pre, "bone")
    f_uni = fuente("sans", 28)
    piezas = []   # (ancho, separación antes, cómo dibujarla en (x, línea base))
    if t["unidad"]:
        piezas.append((c.ancho(t["unidad"], f_uni), 22,
                       lambda xp, yp: c.texto((xp, yp), t["unidad"], f_uni, "ash")))
    if t["veredicto"]:
        piezas.append((c.ancho_pildora(t["veredicto"]), 24,
                       lambda xp, yp: c.pildora(xp, yp - 4, t["veredicto"], t["color_veredicto"])))
    xp = x + c.ancho(t["precio"], f_pre)
    if xp + sum(a + sep for a, sep, _d in piezas) > x + COLUMNA:
        y, xp = y + 44, x - piezas[0][1] if piezas else x
    for a, sep, pieza in piezas:
        xp += sep
        if dibujar:
            pieza(xp, y)
        xp += a
    f_fra, l_fra = c.ajustar(t["frase"], "sans", escala((30, 28, 26)), COLUMNA, 3)
    if len(c.lineas(t["frase"], f_fra, COLUMNA)) > 3:
        f_fra, l_fra = c.ajustar(t["frase"], "sans", escala((24, 22)), COLUMNA, 4)
    y += round(26 * k)
    for linea in l_fra:
        y += int(f_fra.size * 1.3)
        if dibujar:
            c.texto((x, y), linea, f_fra, "bone")
    if t["nota"]:
        f_not, l_not = c.ajustar(t["nota"], "sans", escala((22, 20)), COLUMNA, 2)
        y += 6
        for linea in l_not:
            y += int(f_not.size * 1.4)
            if dibujar:
                c.texto((x, y), linea, f_not, "ash")
    return y


def _ancho_completo(c: Lienzo, t: dict) -> None:
    """El texto de la tarjeta sin gráfico, a todo el ancho: nombre (hasta dos
    líneas), precio con su unidad y la píldora, y la frase. Con el nombre en
    dos líneas, el precio y la frase se achican para no tocar el pie; con
    nota, la frase usa los tamaños chicos y la nota va debajo, en una línea."""
    antetitulo, nombre, precio, unidad = t["antetitulo"], t["nombre"], t["precio"], t["unidad"]
    frase, veredicto, color_veredicto, nota = (t["frase"], t["veredicto"],
                                               t["color_veredicto"], t["nota"])
    ancho = ANCHO - 2 * MARGEN
    c.texto((MARGEN, 178), antetitulo.upper(), fuente("mono", 20), "ash", espacio=2.8)
    f_nom, l_nom = c.ajustar(nombre, "sans-semi", (64, 56, 48), ancho, 2)
    dos = len(l_nom) > 1
    y = 178 + 18
    for linea in l_nom:
        y += int(f_nom.size * 1.12)
        c.texto((MARGEN, y), linea, f_nom, "bone")
    tam_precio = 84 if dos else 112
    f_pre = fuente("display", tam_precio)
    y += int(tam_precio * 1.08)
    c.texto((MARGEN, y), precio, f_pre, "bone")
    x = MARGEN + c.ancho(precio, f_pre) + 22
    f_uni = fuente("sans", 28)
    c.texto((x, y), unidad, f_uni, "ash")
    if veredicto:
        x += c.ancho(unidad, f_uni) + 24
        c.pildora(x, y - 4, veredicto, color_veredicto)
    # la frase en una línea si cabe con una fuente razonable; si no, en dos.
    # Nunca se corta: ajustar() solo trunca si ni la más chica alcanza
    chica = dos or bool(nota)
    una = (30, 28, 26, 24) if chica else (34, 32, 30)
    f_fra, l_fra = c.ajustar(frase, "sans", una, ancho, 1)
    if len(c.lineas(frase, f_fra, ancho)) > 1:
        f_fra, l_fra = c.ajustar(frase, "sans", (26, 24) if chica else (34, 30), ancho, 2)
    y += 30
    for linea in l_fra:
        y += int(f_fra.size * 1.3)
        c.texto((MARGEN, y), linea, f_fra, "bone")
    if nota:
        f_not, l_not = c.ajustar(nota, "sans", (24, 22, 20), ancho, 1)
        y += int(f_not.size * 1.5)
        c.texto((MARGEN, y), l_not[0], f_not, "ash")


def portada(ruta: str, tok: dict, *, indices: list, fecha: str,
            pie_txt: str, sitio: str) -> None:
    """La tarjeta de la portada: los 4 índices en una grilla de 2 x 2, cada
    uno con su nombre, su veredicto, su costo y su frase. 'indices' es una
    lista de dicts {nombre, veredicto, color, precio, frase}."""
    c = Lienzo(tok)
    c.marca()
    c.fecha(fecha)
    col = (ANCHO - 2 * MARGEN - 32) / 2
    alto = 186
    for i, d in enumerate(indices[:4]):
        x = MARGEN + (i % 2) * (col + 32)
        y0 = 136 + (i // 2) * (alto + 18)
        c.d.rounded_rectangle([x, y0, x + col, y0 + alto], radius=14,
                              fill=c.tok["panel"], outline=c.tok["line"], width=2)
        xi = x + 26
        f_n = fuente("mono", 20)
        c.texto((xi, y0 + 44), d["nombre"].upper(), f_n, "ash", espacio=2.4)
        c.pildora(xi + c.ancho(d["nombre"].upper(), f_n, 2.4) + 16, y0 + 44,
                  d["veredicto"], d["color"], tam=17)
        f_p = fuente("display", 54)
        c.texto((xi, y0 + 108), d["precio"], f_p, "bone")
        f_f, l_f = c.ajustar(d["frase"], "sans", (20, 19, 18), col - 52, 2)
        for k, linea in enumerate(l_f):
            c.texto((xi, y0 + 142 + k * int(f_f.size * 1.3)), linea, f_f, "bone")
    c.pie(pie_txt, sitio)
    c.guardar(ruta)


def generica(ruta: str, tok: dict, *, tagline: str, sitio: str) -> None:
    """og.png, la tarjeta de las páginas sin tarjeta propia: el wordmark
    grande, la línea del sitio y, abajo a la derecha, el sitio."""
    c = Lienzo(tok)
    c.marca(tam=160, y=337, x=MARGEN + 32)
    c.texto((MARGEN + 32, 407), tagline, fuente("mono", 28), "ash")
    c.texto((ANCHO - MARGEN, 590), sitio, fuente("display", 30), "dim", ancla="rs")
    c.guardar(ruta)


def icono(ruta: str, tok: dict, lado: int = 180) -> None:
    """apple-touch-icon.png: el símbolo del favicon (la I en hueso y la línea
    en brasa) sobre el fondo, a sangre: iOS redondea las esquinas. Es el SVG
    de viewBox -3.5 -5.5 70 70 con la barra en x=27 y=30 (10 por 24, radio 2)
    y la línea 17,25 25,17 31,21 46,8 de trazo 6, dibujado a 8x y reducido
    (como en trazo, la caja del rectángulo incluye su último píxel)."""
    k = lado * SUPER / 70

    def a(x, y):   # unidades del viewBox a píxeles
        return (x + 3.5) * k, (y + 5.5) * k

    img = Image.new("RGB", (lado * SUPER, lado * SUPER), _rgb(tok["bg"]))
    d = ImageDraw.Draw(img)
    (x0, y0), (x1, y1) = a(27, 30), a(37, 54)
    d.rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=2 * k, fill=_rgb(tok["bone"]))
    trazo(d, [a(17, 25), a(25, 17), a(31, 21), a(46, 8)], 6 * k, _rgb(tok["ember"]))
    _carpeta(ruta)
    img.reduce(SUPER).save(ruta, "PNG", optimize=True)

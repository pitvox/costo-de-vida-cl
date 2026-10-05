"""
tarjetas.py - las og:image de 1200 x 630 que muestran WhatsApp y las redes
=========================================================================
build_site.py las genera en cada build: una por ficha de producto, una por
índice y una para la portada, en og/. Cada tarjeta lleva el nombre, el precio
de la semana, la frase de su veredicto ("Más caro que en 7 de los últimos 10
septiembres, aun descontando la inflación", o con menos de 5 años de ese mes
"Más caro que en 8 de cada 10 semanas desde 2008, descontada la inflación"),
la fecha de la semana y la marca.

Aquí solo se dibuja: las frases y las cifras las arma build_site.py (ahí las
revisa la guardia de texto). Colores: los tokens de CSS_BASE, que build_site
pasa en 'tok'. Fuentes: las del sitio, en fuentes/ (IBM Plex y Space
Grotesk, licencia SIL Open Font License, ver fuentes/OFL-*.txt).

Requiere Pillow.
"""
import os

from PIL import Image, ImageDraw, ImageFont

ANCHO, ALTO = 1200, 630
MARGEN = 64
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
    def marca(self, tam: int = 34, y: int = 92):
        """El wordmark CARESTÍA en hueso, con el acento de la Í en brasa
        (como el ::after del sitio: la misma Í repintada y recortada a la
        altura de las mayúsculas)."""
        f = fuente("display", tam)
        esp = tam * 0.06
        x = MARGEN
        for c in "CARESTÍA":
            self.d.text((x, y), c, font=f, fill=self.tok["bone"], anchor="ls")
            if c == "Í":
                capa = Image.new("L", self.img.size, 0)
                ImageDraw.Draw(capa).text((x, y), c, font=f, fill=255, anchor="ls")
                tope = y + f.getbbox("I", anchor="ls")[1]
                capa.paste(0, (0, int(tope), ANCHO, ALTO))
                self.img.paste(Image.new("RGB", self.img.size, self.tok["ember"]), (0, 0), capa)
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

    def guardar(self, ruta: str):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        # compresión 6 sin optimize: la mitad del tiempo y casi el mismo peso
        self.img.save(ruta, "PNG", compress_level=6)


def ficha(ruta: str, tok: dict, *, antetitulo: str, nombre: str, precio: str,
          unidad: str, frase: str, fecha: str, fuente_txt: str, sitio: str,
          veredicto: str = None, color_veredicto: str = None) -> None:
    """La tarjeta de un producto o de un índice: antetítulo, nombre (hasta dos
    líneas), precio con su unidad (y, en los índices, la píldora del
    veredicto), la frase y el pie con la fuente y la marca. Con el nombre en
    dos líneas, el precio y la frase se achican para no tocar el pie."""
    c = Lienzo(tok)
    c.marca()
    c.fecha(fecha)
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
    una = (30, 28, 26, 24) if dos else (34, 32, 30)
    f_fra, l_fra = c.ajustar(frase, "sans", una, ancho, 1)
    if len(c.lineas(frase, f_fra, ancho)) > 1:
        f_fra, l_fra = c.ajustar(frase, "sans", (26, 24) if dos else (34, 30), ancho, 2)
    y += 30
    for linea in l_fra:
        y += int(f_fra.size * 1.3)
        c.texto((MARGEN, y), linea, f_fra, "bone")
    c.pie(fuente_txt, sitio)
    c.guardar(ruta)


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

"""
diseno/redes/generar.py - las piezas de redes de Carestía
=========================================================
No es parte del build del sitio: se corre a mano cuando cambian la marca o
la serie, desde la raíz del repo y con un indices.json al lado (el de
indices.py o el publicado, https://carestia.cl/indices.json):

  python diseno/redes/generar.py

Escribe en diseno/redes/:
- avatar.png, 800 x 800: el ícono en negativo, el mismo de
  apple-touch-icon.png (tarjetas.icono).
- portada-linkedin.png, 1128 x 191, y portada-linkedin@2x.png, al doble:
  fondo blanco con una regla inferior de 3px en tinta. Los 300 px de la
  izquierda quedan libres (LinkedIn pone ahí el avatar). Al centro, la
  frase en Archivo 800 y, debajo, las fuentes en el gris secundario. A la
  derecha, la línea del Índice Asado ajustado por inflación, con su
  leyenda y el sitio. Sin cifras.

Colores: los tokens de CSS_BASE, leídos de build_site.py (sin correr el
build). Fuente: Archivo, la de fuentes/ (ver tarjetas.py).
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
import tarjetas  # noqa: E402

CARPETA = os.path.join(RAIZ, "diseno", "redes")
FRASE = "Precios semanales de alimentos en Chile, descontada la inflación."
FUENTES = "Datos de ODEPA y del Banco Central, desde 2008."
LEYENDA = "Índice Asado"
SITIO = "carestia.cl"
ANCHO, ALTO = 1128, 191
LIBRE = 300          # la franja de la izquierda, bajo el avatar de LinkedIn


def tokens() -> dict:
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        fuente = fh.read()
    base = fuente[fuente.index('CSS_BASE = r"""'):]
    base = base[:base.index('"""', 20)]
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-f]{6})", base))


def serie_asado() -> list:
    with open(os.path.join(RAIZ, "indices.json"), encoding="utf-8") as fh:
        datos = json.load(fh)
    return [p["value"] for p in datos["indices"]["asado"]["real"] if p.get("value") is not None]


def portada(ruta: str, tok: dict, k: int) -> None:
    rgb = {n: tarjetas._rgb(v) for n, v in tok.items()}
    img = Image.new("RGB", (ANCHO * k, ALTO * k), rgb["bg"])
    d = ImageDraw.Draw(img)
    # la regla inferior de 3px en tinta
    d.rectangle([0, (ALTO - 3) * k, ANCHO * k, ALTO * k], fill=rgb["tinta"])
    # al centro: la frase en dos líneas y las fuentes debajo
    x0, ancho_txt = (LIBRE + 24) * k, 440 * k
    f_frase = tarjetas.fuente("display", 25 * k)
    lineas, actual = [], ""
    for palabra in FRASE.split():
        prueba = f"{actual} {palabra}".strip()
        if actual and d.textlength(prueba, font=f_frase) > ancho_txt:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    lineas.append(actual)
    y = 72 * k
    for linea in lineas:
        d.text((x0, y), linea, font=f_frase, fill=rgb["tinta"], anchor="ls")
        y += 31 * k
    d.text((x0, y + 4 * k), FUENTES, font=tarjetas.fuente("sans", 15 * k),
           fill=rgb["tinta2"], anchor="ls")
    # a la derecha: la línea del Índice Asado, con su leyenda y el sitio
    gx0, gx1, gy0, gy1 = 800 * k, (ANCHO - 32) * k, 62 * k, (ALTO - 34) * k
    f_ley = tarjetas.fuente("sans-semi", 13 * k)
    d.text((gx0, 44 * k), LEYENDA, font=f_ley, fill=rgb["tinta"], anchor="ls")
    d.text((gx1, 44 * k), SITIO, font=tarjetas.fuente("sans", 13 * k), fill=rgb["tinta2"],
           anchor="rs")
    vals = serie_asado()
    bajo, alto = min(vals), max(vals)
    s = 4   # la línea a 4x y reducida: bordes suaves
    capa = Image.new("L", ((gx1 - gx0) * s, (gy1 - gy0) * s), 0)
    pts = [(i / (len(vals) - 1) * (gx1 - gx0) * s,
            (alto - v) / (alto - bajo) * (gy1 - gy0) * s) for i, v in enumerate(vals)]
    tarjetas.trazo(ImageDraw.Draw(capa), pts, 2 * k * s, 255)
    capa = capa.reduce(s)
    img.paste(Image.new("RGB", capa.size, rgb["serie"]), (gx0, gy0), capa)
    img.save(ruta, "PNG", optimize=True)


def main() -> None:
    tok = tokens()
    tarjetas.icono(os.path.join(CARPETA, "avatar.png"), tok, lado=800)
    portada(os.path.join(CARPETA, "portada-linkedin.png"), tok, 1)
    portada(os.path.join(CARPETA, "portada-linkedin@2x.png"), tok, 2)
    print("diseno/redes: avatar.png, portada-linkedin.png y portada-linkedin@2x.png")


if __name__ == "__main__":
    main()

"""
imprimir.py - informe.md a informe.pdf, en una página carta
===========================================================
Último paso (ver README.md). Convierte informe.md a HTML con pandoc y lo
imprime a PDF con Chromium sin interfaz, con la tipografía del sitio
(fuentes/, licencia OFL). Revisa que el PDF quede en una sola página.

Uso: python imprimir.py   (necesita pandoc y Chromium; CHROMIUM fija la ruta)
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "fuentes")
CHROMIUM = os.environ.get("CHROMIUM") or next(
    (r for r in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                 shutil.which("chromium"), shutil.which("chromium-browser"),
                 shutil.which("google-chrome")) if r and os.path.exists(r)), None)
ESTILO = """
@font-face { font-family: "Plex"; src: url("file://%(f)s/IBMPlexSans-Regular.ttf"); }
@font-face { font-family: "Plex"; font-weight: 600 700;
             src: url("file://%(f)s/IBMPlexSans-SemiBold.ttf"); }
@page { size: Letter; margin: 1.1cm 1.2cm; }
body { font-family: "Plex", sans-serif; font-size: 8.2pt; line-height: 1.32; color: #111; }
h1 { font-size: 13.5pt; margin: 0 0 4pt; }
h2 { font-size: 10pt; margin: 5pt 0 1pt; }
p { margin: 2pt 0; }
ul { margin: 2pt 0; padding-left: 13pt; }
li { margin: 1pt 0; }
table { border-collapse: collapse; width: 100%%; font-size: 7.8pt; margin: 4pt 0; }
th, td { border-bottom: 0.5pt solid #ccc; padding: 0.6pt 4pt; text-align: left; }
th { font-weight: 600; }
td:nth-child(n+2) { white-space: nowrap; }
#lo-que-no-podemos-afirmar + ul { columns: 2; column-gap: 14pt; }
#lo-que-no-podemos-afirmar + ul li { break-inside: avoid; }
""" % {"f": FUENTES}


def paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def huella(ruta: str = None) -> str:
    """Los primeros 12 del sha256 de informe.md: van en el título del PDF,
    para que los tests sepan si el PDF salió de este informe."""
    with open(ruta or os.path.join(AQUI, "informe.md"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def imprimir(salida: str = None) -> str:
    if not CHROMIUM:
        sys.exit("imprimir.py: no encuentro Chromium (fija CHROMIUM con su ruta)")
    salida = salida or os.path.join(AQUI, "informe.pdf")
    with tempfile.TemporaryDirectory() as tmp:
        css = os.path.join(tmp, "informe.css")
        with open(css, "w", encoding="utf-8") as fh:
            fh.write(ESTILO)
        pagina = os.path.join(tmp, "informe.html")
        subprocess.run(["pandoc", os.path.join(AQUI, "informe.md"), "-s", "--metadata",
                        f"pagetitle=Carne de vacuno {huella()}", "-c", css, "-o", pagina],
                       check=True)
        subprocess.run([CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu",
                        "--allow-file-access-from-files", "--no-pdf-header-footer",
                        f"--print-to-pdf={salida}", f"file://{pagina}"],
                       check=True, capture_output=True)
    with open(salida, "rb") as fh:
        n = paginas(fh.read())
    if n != 1:
        sys.exit(f"imprimir.py: el informe ocupa {n} páginas; tiene que caber en una")
    return salida


if __name__ == "__main__":
    print(imprimir())

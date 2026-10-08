"""
graficar.py - gráfico de 1080 x 1080 de los cortes principales desde 2016
=========================================================================
Cuarto paso (ver README.md). Lee resultados/series_vacuno.json (lo escribe
vacuno.py) y dibuja grafico_vacuno.png: el precio por kilo ajustado por
inflación de cuatro cortes, como promedio de cada mes desde enero de 2016,
con un punto en el precio de esta semana.

Uso: python graficar.py   (después de vacuno.py; necesita matplotlib)
"""
import datetime
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
from vacuno import MESES, clp, fecha_larga, fechas, ultima  # noqa: E402

DESDE = datetime.date(2016, 1, 1)
# los cortes principales: los dos de la canasta del Índice Asado, el más caro
# de los de todos los días y el corte magro más común; en el orden de la paleta
CORTES = [("lomo_vetado", "Lomo vetado"), ("asado_de_tira", "Asado de tira"),
          ("posta_negra", "Posta negra"), ("asado_carnicero", "Asado carnicero")]
# paleta validada (dataviz, scripts/validate_palette.js en modo claro: pasa;
# el contraste bajo 3:1 de los dos últimos se cubre con etiquetas directas).
# El lomo vetado va en el magenta de Comparar (--cmp2 del sitio): la marca no
# usa azules. Queda a 14 o más (OKLab x100) de cada uno de los otros tres con
# visión normal y con protanopía, deuteranopía y tritanopía simuladas, y a
# 4,4:1 de la superficie
SUPERFICIE, TEXTO, TEXTO_2, MUTED, GRILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SERIES = ["#b04fb5", "#eb6834", "#1baf7a", "#eda100"]
LADO = 1080                                   # pixeles
TEXTOS = []                                   # todo el texto del gráfico (lo revisa el test)


def fuente(nombre: str, tam: float) -> font_manager.FontProperties:
    """La fuente del sitio (fuentes/, licencia OFL) por su archivo: la
    SemiBold y la Regular comparten nombre de familia."""
    return font_manager.FontProperties(fname=os.path.join(RAIZ, "fuentes", nombre), size=tam)


def sans(tam: float) -> font_manager.FontProperties:
    return fuente("IBMPlexSans-Regular.ttf", tam)


def negrita(tam: float) -> font_manager.FontProperties:
    return fuente("IBMPlexSans-SemiBold.ttf", tam)


def mensual(p: dict) -> tuple:
    """(fechas a mitad de mes, promedio de cada mes) desde DESDE, con las
    semanas asignadas al mes de su lunes, como en el sitio."""
    suma, n = {}, {}
    for f, x in zip(fechas(p), p["v"]):
        if x is None or f < DESDE:
            continue
        k = (f.year, f.month)
        suma[k] = suma.get(k, 0) + x
        n[k] = n.get(k, 0) + 1
    meses = sorted(suma)
    return ([datetime.date(a, m, 15) for a, m in meses], [suma[k] / n[k] for k in meses])


def miles(x: float) -> str:
    return "$" + f"{int(round(x)):,}".replace(",", ".")


def texto(fig_o_ax, *args, **kw):
    TEXTOS.append(args[2])
    return fig_o_ax.text(*args, **kw)


def graficar(series: dict, salida: str = None) -> str:
    TEXTOS.clear()
    prods = series["productos"]
    ipc = datetime.date.fromisoformat(series["ipc_mes"] + "-01")
    semana = max(fechas(p)[ultima(p["v"])] for p in prods.values())

    fig = plt.figure(figsize=(LADO / 100, LADO / 100), dpi=100, facecolor=SUPERFICIE)
    ax = fig.add_axes([0.12, 0.2, 0.585, 0.555])
    ax.set_facecolor(SUPERFICIE)

    texto(fig, 0.05, 0.955, "Carne de vacuno en Santiago", color=TEXTO,
          fontproperties=negrita(40), va="top")
    texto(fig, 0.05, 0.885, f"Precio por kilo ajustado por inflación, en pesos de "
          f"{MESES[ipc.month - 1]} de {ipc.year}", fontproperties=sans(22), color=TEXTO_2,
          va="top")
    texto(fig, 0.05, 0.84, "Línea: promedio de cada mes desde 2016.", fontproperties=sans(20),
          color=TEXTO_2, va="top")
    texto(fig, 0.05, 0.805, f"Punto: semana del {fecha_larga(semana)}.",
          fontproperties=sans(20), color=TEXTO_2, va="top")

    finales = []
    for (clave, nombre), color in zip(CORTES, SERIES):
        p = prods[clave]
        x, y = mensual(p)
        ax.plot(x, y, color=color, lw=2.4, solid_joinstyle="round", solid_capstyle="round",
                zorder=3)
        i = ultima(p["v"])
        f, v = fechas(p)[i], p["v"][i]
        # el punto de esta semana, con un anillo del color de la superficie
        ax.scatter([f], [v], s=150, color=color, edgecolor=SUPERFICIE, linewidth=2, zorder=5)
        finales.append((v, f, nombre, color))

    # etiquetas directas a la derecha: nombre y precio de esta semana, con
    # una línea guía al punto si hubo que separarlas
    ax.set_xlim(DESDE, datetime.date(2026, 12, 31))
    ymin, ymax = 6000, 19000
    ax.set_ylim(ymin, ymax)
    sep = (ymax - ymin) * 0.105
    pos = []
    for v, f, nombre, color in sorted(finales, reverse=True):
        y = v if not pos or pos[-1] - v >= sep else pos[-1] - sep
        pos.append(y)
        xl = datetime.date(2027, 2, 1)
        ax.annotate("", xy=(f, v), xytext=(xl, y), textcoords="data",
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=1, shrinkA=0, shrinkB=6),
                    annotation_clip=False)
        ax.plot([xl + datetime.timedelta(days=20), xl + datetime.timedelta(days=130)], [y, y],
                color=color, lw=5, solid_capstyle="round", clip_on=False)
        TEXTOS.extend([nombre, clp(v)])
        ax.text(xl + datetime.timedelta(days=165), y + sep * 0.22, nombre,
                fontproperties=sans(21), color=TEXTO, va="center", clip_on=False)
        ax.text(xl + datetime.timedelta(days=165), y - sep * 0.25, clp(v),
                fontproperties=negrita(21), color=TEXTO, va="center", clip_on=False)

    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(2000))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: miles(v)))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", color=GRILLA, lw=1)
    ax.tick_params(colors=MUTED, length=0, pad=8)
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_fontproperties(sans(19))
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_axisbelow(True)

    # ODEPA no releva carne de vacuno en ferias: carnicerías y supermercados
    # (desde 2020 también supermercados en línea)
    texto(fig, 0.05, 0.1, "Promedio de carnicerías y supermercados de Santiago que releva "
          "ODEPA.", fontproperties=sans(18), color=TEXTO_2, va="top")
    texto(fig, 0.05, 0.065, "Fuente: Carestía (carestia.cl), con datos de ODEPA (CC BY 4.0)",
          fontproperties=sans(18), color=TEXTO_2, va="top")
    texto(fig, 0.05, 0.03, "e IPC del Banco Central de Chile.", fontproperties=sans(18),
          color=TEXTO_2, va="top")

    salida = salida or os.path.join(AQUI, "grafico_vacuno.png")
    fig.savefig(salida, facecolor=SUPERFICIE, dpi=100)
    plt.close(fig)
    return salida


def cargar(ruta: str = None) -> dict:
    with open(ruta or os.path.join(AQUI, "resultados", "series_vacuno.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    print(graficar(cargar()))

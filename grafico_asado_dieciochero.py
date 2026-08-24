# -*- coding: utf-8 -*-
"""
grafico_asado_dieciochero.py — gráfico del Índice Asado, edición FP 2026
========================================================================
Baja indices.json del sitio DESPLEGADO (LOCKED #17: la cifra que se publica
es la que se lee del sitio vivo) y genera grafico_asado.png en paleta clara
para el factsheet dieciochero: fondo blanco, línea azul #0039A6, máximo
histórico marcado en rojo #D52B1E.
"""
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

URL = "https://carestia.cl/indices.json"

# Paleta edición dieciochera (solo esta pieza; la paleta del producto no cambia)
BG = "#ffffff"
INK = "#1a1a1a"
GRIS = "#8a8a8a"
AZUL = "#0039A6"
ROJO = "#D52B1E"
GRID = "#e6e6e6"

print("Bajando " + URL + " ...")
data = requests.get(URL, timeout=120).json()
serie = data["indices"]["asado"]["real"]
fechas = [datetime.strptime(p["time"], "%Y-%m-%d") for p in serie]
vals = [p["value"] for p in serie]

i_max = vals.index(max(vals))
f_max, v_max = fechas[i_max], vals[i_max]
f_ult, v_ult = fechas[-1], vals[-1]

def clp(x):
    return "$" + "{:,}".format(int(round(x))).replace(",", ".")

print("Máximo real histórico: " + clp(v_max) + " (" + f_max.strftime("%d-%m-%Y") + ")")
print("Última semana:         " + clp(v_ult) + " (" + f_ult.strftime("%d-%m-%Y") + ")")

fig, ax = plt.subplots(figsize=(12, 4.6), dpi=200)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

ax.plot(fechas, vals, color=AZUL, linewidth=1.6, zorder=3)

# Aire a la derecha: la etiqueta de "hoy" se rotula fuera de la serie, no
# encima. Sin este margen cae sobre la linea y queda ilegible.
ax.set_xlim(fechas[0], fechas[-1] + timedelta(days=220))

# máximo histórico
ax.scatter([f_max], [v_max], color=ROJO, s=30, zorder=4)
ax.annotate("máximo real histórico\n" + clp(v_max) + " · " + f_max.strftime("%b %Y"),
            xy=(f_max, v_max), xytext=(-10, 18), textcoords="offset points",
            ha="right", fontsize=8.5, color=INK, family="monospace",
            arrowprops=dict(arrowstyle="-", color=GRIS, lw=0.7))

# última semana
ax.scatter([f_ult], [v_ult], color=INK, s=30, zorder=4)
ax.annotate("hoy: " + clp(v_ult),
            xy=(f_ult, v_ult), xytext=(9, 0), textcoords="offset points",
            ha="left", va="center", fontsize=9, color=INK, family="monospace",
            weight="bold", zorder=5,
            bbox=dict(boxstyle="round,pad=0.2", facecolor=BG, edgecolor="none"))

ax.set_title("Índice Asado — asado para 4 personas, en pesos de hoy",
             color=INK, fontsize=11, family="monospace", loc="left", pad=12)

ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: clp(v)))
ax.xaxis.set_major_locator(mdates.YearLocator(2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.tick_params(colors=GRIS, labelsize=8.5)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_family("monospace")
    lbl.set_color(GRIS)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("bottom", "left"):
    ax.spines[side].set_color(GRID)
ax.grid(axis="y", color=GRID, linewidth=0.6)

fig.text(0.995, 0.015, "Datos: ODEPA (CC-BY) · deflactado por IPC BCCh · carestia.cl",
         ha="right", fontsize=7, color=GRIS, family="monospace")

plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig("grafico_asado.png", facecolor=BG, bbox_inches="tight")
print("Escrito grafico_asado.png")

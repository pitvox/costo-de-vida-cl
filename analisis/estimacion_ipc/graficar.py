"""
graficar.py - gráfico de la variación mensual estimada frente a la oficial
==========================================================================
Lee resultados/estimacion_mes_anterior.csv (la variante principal) y
escribe grafico_estimado_oficial.png para el informe.

Uso: python graficar.py   (después de estimar.py; necesita matplotlib)
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
# paleta validada (dataviz): superficie clara, dos series categóricas
SUPERFICIE, TEXTO, TEXTO_2, GRILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OFICIAL, ESTIMADA = "#2a78d6", "#eb6834"


def graficar(variante: str = "mes_anterior", salida: str = None) -> str:
    r = pd.read_csv(os.path.join(AQUI, "resultados", f"estimacion_{variante}.csv"))
    r = r.dropna(subset=["oficial"])
    x = pd.PeriodIndex(r["mes"], freq="M").to_timestamp()
    est = r["estimada"].round(1)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(10, 4.4), dpi=160)
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)
    ax.axhline(0, color=TEXTO_2, lw=0.8, zorder=1)
    cambio = pd.Timestamp("2024-01-01")
    ax.axvline(cambio, color=TEXTO_2, lw=0.8, ls=(0, (2, 3)), zorder=1)
    ax.text(cambio, 0.98, "  cambio de base del IPC", transform=ax.get_xaxis_transform(),
            color=TEXTO_2, fontsize=8.5, va="top")
    ax.plot(x, r["oficial"], color=OFICIAL, lw=2, label="Oficial (INE)", zorder=3)
    ax.plot(x, est, color=ESTIMADA, lw=2, label="Estimada con precios de ODEPA", zorder=2)
    # etiquetas directas al final de cada línea, separadas si quedan encima
    fin = {"oficial": r["oficial"].iloc[-1], "estimada": est.iloc[-1]}
    arriba = "oficial" if fin["oficial"] >= fin["estimada"] else "estimada"
    cerca = abs(fin["oficial"] - fin["estimada"]) < 0.3
    for texto, y in fin.items():
        dy = (6 if texto == arriba else -6) if cerca else 0
        ax.annotate(f"{texto} {y:+.1f}".replace(".", ",").replace("-", "−"), (x[-1], y),
                    xytext=(6, dy), textcoords="offset points", color=TEXTO, fontsize=8.5,
                    va="center")
    ax.set_ylabel("variación mensual (%)", color=TEXTO_2)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:.1f}".replace(".", ",").replace("-", "−")))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", color=GRILLA, lw=0.6)
    ax.tick_params(colors=TEXTO_2, length=0)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRILLA)
    ax.set_xlim(x[0] - pd.Timedelta(days=20), x[-1] + pd.Timedelta(days=150))
    ax.legend(loc="upper left", frameon=False, labelcolor=TEXTO, ncols=2,
              bbox_to_anchor=(0, 1.12))
    ax.set_title("IPC de alimentos y bebidas no alcohólicas, variación mensual",
                 loc="left", color=TEXTO, fontsize=11.5, pad=28)
    fig.tight_layout()
    salida = salida or os.path.join(AQUI, "grafico_estimado_oficial.png")
    fig.savefig(salida, facecolor=SUPERFICIE)
    plt.close(fig)
    return salida


if __name__ == "__main__":
    print(graficar())

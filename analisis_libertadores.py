"""
analisis_libertadores.py - ¿Se nota el cierre del Paso Los Libertadores en los precios?
=======================================================================================
Analisis one-off, NO toca el sitio ni el pipeline. Reutiliza las funciones de
indices.py (debe estar en la misma carpeta). Compara los precios semanales
deflactados de los productos mas expuestos al paso (carne importada, queso)
contra las dos ventanas de cierre prolongado:

  - 2023: ~23-06-2023 a ~21-07-2023 (ventana parcial 07-07 a 10-07)
          OJO: fecha de reapertura definitiva del segundo tramo NO confirmada
          al dia; verificar antes de publicar fechas exactas.
  - 2026: 14-07-2026 en adelante (cierre vigente, record historico)

Salida:
  1. libertadores.png  - grafico en paleta Carestia con ventanas sombreadas
  2. tabla en consola  - variacion % real de cada producto: 4 semanas previas
     al cierre vs semanas durante el cierre, para 2023 y 2026
  3. dispersion        - rango min-max entre puntos de venta (ancho de mecha)
     antes vs durante, por si el estres de abastecimiento abre la dispersion

Correr (mismo entorno donde corres indices.py):
  pip install matplotlib
  python analisis_libertadores.py

REGLAS DEL PROYECTO QUE APLICAN:
  - Ninguna cifra de esto se publica sin que salga de esta corrida real.
  - El post/nota describe lo que la serie muestra ("durante el cierre, X"),
    JAMAS atribuye causalidad ("el cierre causo X"). Hay dos shocks
    simultaneos en 2026 (paso + temporales) y no son separables.
  - Si el resultado es "no se nota", eso TAMBIEN es el hallazgo y se publica.
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# reutilizamos el pipeline existente
from indices import cargar_odepa, cargar_ipc, precio_semanal, unidad_modal, factor_precio

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
PRODUCTOS = [
    # (etiqueta, texto de busqueda ODEPA, unidad objetivo)
    ("Asado de tira",   "Asado de tira",   "kg"),
    ("Asado carnicero", "Asado Carnicero", "kg"),
    ("Queso Gauda",     "Queso Gauda",     "kg"),
]

VENTANAS = {
    # etiqueta: (inicio, fin, confirmada)
    "Cierre 2023": (pd.Timestamp("2023-06-23"), pd.Timestamp("2023-07-21"), False),
    "Cierre 2026": (pd.Timestamp("2026-07-14"), None, True),  # None = vigente
}

PRE_SEMANAS = 4   # ventana de comparacion previa al cierre

# paleta Carestia (LOCKED: sin celeste/azul)
BG, PANEL, BONE, ASH, BRASA = "#17120e", "#1e1813", "#e4dacc", "#8b8276", "#e8743b"
SOMBRA = "#8b8276"

# ----------------------------------------------------------------------------
def series_producto(df, ipc, texto, objetivo):
    """Precio semanal real (pesos de hoy) + rango min-max real por producto."""
    f, mismatch = factor_precio(unidad_modal(df, texto), objetivo)
    if mismatch:
        print(f"  [UNIDAD!] '{texto}': revisar unidad antes de usar este producto")
    prom = precio_semanal(df, texto, "Precio promedio") * f
    pmin = precio_semanal(df, texto, "Precio minimo") * f
    pmax = precio_semanal(df, texto, "Precio maximo") * f
    out = pd.DataFrame({"nom": prom, "min": pmin, "max": pmax}).resample("W-MON").mean()
    out = out.dropna(subset=["nom"])
    # deflactar a pesos de hoy (mismo metodo del pipeline: merge_asof backward)
    izq = out.reset_index().rename(columns={"index": "fecha"}).sort_values("fecha")
    der = ipc.rename("ipc").rename_axis("fecha").reset_index().sort_values("fecha")
    m = pd.merge_asof(izq, der, on="fecha", direction="backward").set_index("fecha")
    factor = m["ipc"].iloc[-1] / m["ipc"]
    m["real"] = m["nom"] * factor
    m["rmin"] = m["min"] * factor
    m["rmax"] = m["max"] * factor
    m["dispersion"] = m["rmax"] - m["rmin"]
    return m[["real", "rmin", "rmax", "dispersion"]]


def comparar_ventana(s, ini, fin):
    """Promedio real y dispersion: PRE_SEMANAS previas vs durante la ventana."""
    fin_ef = fin if fin is not None else s.index.max()
    pre = s.loc[(s.index >= ini - pd.Timedelta(weeks=PRE_SEMANAS)) & (s.index < ini)]
    dur = s.loc[(s.index >= ini) & (s.index <= fin_ef)]
    if pre.empty or dur.empty:
        return None
    return {
        "pre_real": pre["real"].mean(), "dur_real": dur["real"].mean(),
        "var_pct": (dur["real"].mean() / pre["real"].mean() - 1) * 100,
        "pre_disp": pre["dispersion"].mean(), "dur_disp": dur["dispersion"].mean(),
        "n_pre": len(pre), "n_dur": len(dur),
    }


def main():
    df = cargar_odepa()
    ipc = cargar_ipc()

    series = {}
    print("\n" + "=" * 72)
    for lab, texto, uni in PRODUCTOS:
        series[lab] = series_producto(df, ipc, texto, uni)
        print(f"{lab}: {len(series[lab])} semanas de datos")

    # ------------------------------ tabla ------------------------------
    for vlab, (ini, fin, confirmada) in VENTANAS.items():
        nota = "" if confirmada else "  [fechas 2023 por confirmar al dia]"
        print(f"\n--- {vlab}{nota} ---")
        print(f"{'Producto':<18}{'pre (4 sem)':>14}{'durante':>12}{'var %':>9}"
              f"{'disp pre':>11}{'disp dur':>11}")
        for lab in series:
            r = comparar_ventana(series[lab], ini, fin)
            if r is None:
                print(f"{lab:<18}{'sin datos suficientes':>30}")
                continue
            print(f"{lab:<18}{r['pre_real']:>13,.0f}{r['dur_real']:>12,.0f}"
                  f"{r['var_pct']:>+8.1f}%{r['pre_disp']:>11,.0f}{r['dur_disp']:>11,.0f}"
                  f"   (n={r['n_pre']}/{r['n_dur']})")
    print("=" * 72)
    print("Recordatorio: describir, no atribuir causalidad. Dos shocks en 2026.")

    # ------------------------------ grafico ------------------------------
    fig, axes = plt.subplots(len(PRODUCTOS), 1, figsize=(11, 3.2 * len(PRODUCTOS)),
                             sharex=False, facecolor=BG)
    if len(PRODUCTOS) == 1:
        axes = [axes]
    # solo desde 2022 para que las ventanas se lean
    desde = pd.Timestamp("2022-01-01")
    for ax, lab in zip(axes, series):
        s = series[lab].loc[series[lab].index >= desde]
        ax.set_facecolor(PANEL)
        ax.fill_between(s.index, s["rmin"], s["rmax"], color=ASH, alpha=0.25,
                        linewidth=0, label="Rango entre puntos de venta")
        ax.plot(s.index, s["real"], color=BRASA, linewidth=1.6,
                label="Precio real (pesos de hoy)")
        for vlab, (ini, fin, _) in VENTANAS.items():
            fin_ef = fin if fin is not None else s.index.max()
            ax.axvspan(ini, fin_ef, color=SOMBRA, alpha=0.28, label=vlab)
        ax.set_title(lab, color=BONE, fontsize=11, loc="left")
        ax.tick_params(colors=ASH, labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#3a332c")
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"${v:,.0f}".replace(",", ".")))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               labelcolor=BONE, fontsize=8)
    fig.suptitle("Precios reales vs cierres prolongados del Paso Los Libertadores\n"
                 "Fuente: ODEPA (CC-BY), deflactado por IPC · Region Metropolitana",
                 color=BONE, fontsize=11)
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig("libertadores.png", dpi=160, facecolor=BG)
    print("\nEscrito libertadores.png")


if __name__ == "__main__":
    main()

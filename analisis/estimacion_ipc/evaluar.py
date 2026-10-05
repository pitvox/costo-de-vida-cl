"""
evaluar.py - prueba fuera de muestra con la regla de preregistro.md
==================================================================
Desarrollo: enero 2019 a diciembre 2023 (ahí se estiman phi del AR(1) y el
peso w de la combinación). Prueba: enero 2024 a agosto 2026, sin tocar nada.

Productos y versiones, cada uno con 1, 2 y 3 semanas del mes (y el mes
completo como referencia):
- IPC V0: regla principal (lo que no tiene ODEPA, con su variación del mes
  anterior).
- IPC V1: lo que no tiene ODEPA, con un AR(1) (phi de desarrollo).
- IPC V2: lo que no tiene ODEPA, con su promedio de 12 meses.
- IPC V3: w * V0 + (1 - w) * promedio de 12 meses de Alimentos (w de
  desarrollo).
- Canasta anclada: valor oficial de m-1 más la variación ODEPA del mes.

Regla: error menor que el mejor comparador simple (ingenuo o promedio de 12
meses, el de menos error en el mismo período) con Diebold y Mariano p < 0,05,
y más aciertos de dirección que "siempre sube". Pasa un producto si cumple con
1, 2 y 3 semanas.

Uso: python evaluar.py                  (desarrollo y prueba)
     python evaluar.py --solo-desarrollo (no calcula nada de 2024 a 2026)
"""
import os
import sys

import numpy as np
import pandas as pd

import canasta
import estimar

AQUI = os.path.dirname(os.path.abspath(__file__))
RESULTADOS = os.path.join(AQUI, "resultados")
DESARROLLO = (pd.Period("2019-01", "M"), pd.Period("2023-12", "M"))
PRUEBA = (pd.Period("2024-01", "M"), None)
SEMANAS = (1, 2, 3, None)          # None = mes completo, solo como referencia
ALFA = 0.05
N_PRUEBAS = 15                      # 4 versiones del IPC y la canasta, por 3 semanas


def ventana(r: pd.DataFrame, periodo) -> pd.DataFrame:
    desde, hasta = periodo
    return r[(r["mes"] >= desde) & ((r["mes"] <= hasta) if hasta else True)]


def peso_combinacion(v0: pd.DataFrame) -> float:
    """w de la combinación: mínimos cuadrados de oficial - P12 sobre V0 - P12,
    sin constante, en el período de desarrollo, recortado entre 0 y 1."""
    d = ventana(v0, DESARROLLO).dropna(subset=["oficial"])
    x = d["estimada"] - d["promedio_12m"]
    y = d["oficial"] - d["promedio_12m"]
    return float(np.clip((x * y).sum() / (x * x).sum(), 0, 1))


def regla(r: pd.DataFrame) -> dict:
    """Aplica la regla a las filas de un período."""
    e = estimar.errores(r)
    eam = {"estimacion": e["error_est"].mean(), "ingenuo": e["error_ing"].mean(),
           "promedio_12m": e["error_p12"].mean()}
    mejor = "ingenuo" if eam["ingenuo"] <= eam["promedio_12m"] else "promedio_12m"
    col = {"ingenuo": "error_ing", "promedio_12m": "error_p12"}[mejor]
    p = estimar.diebold_mariano(e["error_est"], e[col])
    aciertos, sube = int(e["dir_est"].sum()), int(e["dir_sube"].sum())
    gana_error = bool(eam["estimacion"] < eam[mejor] and p < ALFA)
    gana_dir = aciertos > sube
    return {"meses": len(e), "eam_estimacion": eam["estimacion"],
            "eam_ingenuo": eam["ingenuo"], "eam_promedio_12m": eam["promedio_12m"],
            "mejor_comparador": mejor, "eam_mejor": eam[mejor], "p_dm": p,
            "gana_error": gana_error, "aciertos_dir": aciertos, "aciertos_siempre_sube": sube,
            "gana_direccion": gana_dir, "pasa": gana_error and gana_dir,
            "pasa_bonferroni": bool(gana_error and p < ALFA / N_PRUEBAS and gana_dir)}


def versiones(semanal: pd.DataFrame, phi: float):
    """{(producto, semanas): DataFrame mensual} y los pesos w de la combinación."""
    out, pesos = {}, {}
    for k in SEMANAS:
        v0 = estimar.estimar(semanal, "mes_anterior", semanas=k)
        pesos[k] = peso_combinacion(v0)
        out[("IPC V0 regla principal", k)] = v0
        out[("IPC V1 AR(1)", k)] = estimar.estimar(semanal, "ar1", semanas=k, phi=phi)
        out[("IPC V2 promedio de 12 meses", k)] = estimar.estimar(semanal, "12_meses", semanas=k)
        out[("IPC V3 combinación", k)] = v0.assign(
            estimada=pesos[k] * v0["estimada"] + (1 - pesos[k]) * v0["promedio_12m"])
        out[("Canasta anclada", k)] = canasta.anclada(semanal, k)
    return out, pesos


def nombre_semanas(k) -> str:
    return "mes completo" if k is None else f"{k} semana{'s' if k > 1 else ''}"


if __name__ == "__main__":
    solo_desarrollo = "--solo-desarrollo" in sys.argv
    semanal = pd.read_csv(os.path.join(AQUI, "datos", "odepa_semanal.csv"), parse_dates=["semana"])
    phi = estimar.estimar_phi(*DESARROLLO)
    out, pesos = versiones(semanal, phi)
    print(f"phi = {phi:.4f}; w = " + ", ".join(f"{nombre_semanas(k)} {w:.3f}"
                                              for k, w in pesos.items()))
    periodos = {"desarrollo": DESARROLLO} if solo_desarrollo else {"desarrollo": DESARROLLO,
                                                                    "prueba": PRUEBA}
    filas, mensual = [], []
    for (producto, k), r in out.items():
        for nombre, periodo in periodos.items():
            filas.append({"producto": producto, "semanas": nombre_semanas(k), "periodo": nombre,
                          **regla(ventana(r, periodo))})
        if not solo_desarrollo:
            mensual.append(r[["mes", "estimada", "oficial", "ingenuo", "promedio_12m"]]
                           .assign(producto=producto, semanas=nombre_semanas(k)))
    tabla = pd.DataFrame(filas)
    pd.set_option("display.width", 250)
    print(tabla.round(3).to_string(index=False))
    if solo_desarrollo:
        sys.exit(0)
    os.makedirs(RESULTADOS, exist_ok=True)
    tabla.round(4).to_csv(os.path.join(RESULTADOS, "evaluacion.csv"), index=False)
    pd.concat(mensual).assign(mes=lambda d: d["mes"].astype(str)).round(4).to_csv(
        os.path.join(RESULTADOS, "evaluacion_mensual.csv"), index=False)
    pd.DataFrame([{"parametro": "phi", "semanas": "todas", "valor": phi}]
                 + [{"parametro": "w", "semanas": nombre_semanas(k), "valor": w}
                    for k, w in pesos.items()]).round(4).to_csv(
        os.path.join(RESULTADOS, "evaluacion_parametros.csv"), index=False)
    prueba = tabla[(tabla["periodo"] == "prueba") & (tabla["semanas"] != "mes completo")]
    veredicto = prueba.groupby("producto")["pasa"].all()
    print("\n== pasa la regla con 1, 2 y 3 semanas (prueba 2024 a 2026) ==")
    print(veredicto.to_string())

"""
descargar.py - baja las fuentes del análisis a datos_crudos/
============================================================
Primer paso de la prueba hacia atrás (ver README.md). Baja solo lo que falta;
con --forzar vuelve a bajar todo.

- INE: series de tiempo y referenciales del IPC (bases 2018 y 2023) y la serie
  empalmada de analíticos, que trae "Alimentos". Licencia CC BY-SA 4.0.
- ODEPA: precios al consumidor 2008 a 2026, los mismos recursos que usa
  indices.py (datos.odepa.gob.cl). Licencia CC BY 4.0.
- Ministerio de Desarrollo Social y Familia: informes mensuales del valor de
  la Canasta Básica de Alimentos (2019 a 2026).

Uso: python descargar.py [--forzar]
"""
import os
import sys

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUDOS = os.path.join(AQUI, "datos_crudos")
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))
import indices  # noqa: E402

INE = "https://www.ine.gob.cl/docs/default-source/%C3%ADndice-de-precios-al-consumidor/cuadros-estadisticos/"
FUENTES = {
    "ine/ipc_base2018.csv":
        INE + "base-2018/series-de-tiempo/ipc-csv.csv?sfvrsn=e9985350_40&download=true",
    "ine/ipc_base2018_referencial.csv":
        INE + "base-2018/series-referenciales/ipc-base-2018-serie-referencial-csv.csv"
              "?sfvrsn=c646f4d2_2&download=true",
    "ine/ipc_base2023.csv":
        INE + "base-anual-2023_100/series-de-tiempo/ipc_base_20237baa955a44fe4eada201c196338fb3be.csv"
              "?sfvrsn=2a13310a_73&download=true",
    "ine/ipc_base2023_referencial.csv":
        INE + "base-anual-2023_100/series-referenciales/ipc_ref_base_20230bd18276c47b4ec68bda28582d82207d.csv"
              "?sfvrsn=93efbb69_6&download=true",
    "ine/analiticos_empalmados.csv":
        INE + "series-empalmadas-y-antecedentes-historicos/series-empalmadas-diciembre-2009-a-la-fecha/"
              "serie_anal%C3%ADticos_empalmados047c1ef98b0e463c8c5fa4a657efaa20.csv"
              "?sfvrsn=232a67f2_74&download=true",
}
FUENTES.update({f"odepa/{y}.csv": indices.URL.format(ds=indices.DATASET, rid=rid, y=y)
                for y, rid in sorted(indices.RESOURCES.items())})


def bajar(destino: str, url: str, forzar: bool = False) -> None:
    ruta = os.path.join(CRUDOS, destino)
    if os.path.exists(ruta) and os.path.getsize(ruta) > 0 and not forzar:
        return
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(ruta + ".tmp", "wb") as fh:
        fh.write(r.content)
    os.replace(ruta + ".tmp", ruta)
    print(f"  {destino}: {len(r.content) / 1e6:.1f} MB")


if __name__ == "__main__":
    forzar = "--forzar" in sys.argv
    for destino, url in FUENTES.items():
        bajar(destino, url, forzar)
    print(f"listo: {len(FUENTES)} archivos en {CRUDOS}")

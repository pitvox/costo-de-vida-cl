"""
descargar.py - baja las fuentes de la nota de vacuno a datos_crudos/
====================================================================
Primer paso (ver README.md). Baja solo lo que falta; con --forzar vuelve a
bajar todo. Lo del sitio (indices.json, catálogo, portada, fichas y series
de los cortes) se baja siempre junto, para que sea una sola foto del sitio
desplegado.

- carestia.cl: indices.json (de donde salen las cifras), datos/catalogo.json,
  la portada y, de cada corte de vacuno, su ficha (productos/{slug}.html) y
  su serie (datos/productos/{slug}.json).
- ODEPA: precios al consumidor 2008 a 2026, los mismos recursos que usa
  indices.py (datos.odepa.gob.cl). Licencia CC BY 4.0.
- Banco Central: dos cuadros públicos. La variación a 12 meses del IPC con
  el empalme del Banco Central (base 2023), la familia de la serie con que
  indices.py deflacta, y el índice con el empalme del INE (diciembre de 2009
  en adelante).
- INE: series de tiempo del IPC, bases 2018 y 2023. Licencia CC BY-SA 4.0.

Cada archivo queda anotado en datos_crudos/descarga.json con su URL, su hora
de descarga (UTC), su tamaño y su sha256.

Uso: python descargar.py [--forzar]
"""
import datetime
import hashlib
import json
import os
import sys

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
CRUDOS = os.path.join(AQUI, "datos_crudos")
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))
import indices  # noqa: E402

SITIO = "https://carestia.cl"
GRUPO = "Carne bovina"
BCCH = "https://si3.bcentral.cl/Siete/ES/Siete/Cuadro/CAP_PRECIOS/MN_CAP_PRECIOS/"
RANGO = "?cbFechaInicio=2007&cbFechaTermino=2026&cbFrecuencia=MONTHLY&cbCalculo=NONE&cbFechaBase="
INE = ("https://www.ine.gob.cl/docs/default-source/%C3%ADndice-de-precios-al-consumidor/"
       "cuadros-estadisticos/")
FUENTES = {
    # variación a 12 meses del empalme BCCh base 2023 (G073.IPC.V12.2023.M),
    # la misma familia que el índice con que deflacta indices.py
    # (G073.IPC.IND.2023.M, que solo sale por la API con usuario)
    "ipc/bcch_empalme_bcch_v12.html": BCCH + "PEM_VAR12_IPC_2023/638447991540869284" + RANGO,
    # índice empalmado por el INE (F074.IPC.IND.Z.EP23.C.M), diciembre de 2009
    # en adelante: otro método de empalme, para la robustez
    "ipc/bcch_empalme_ine.html": BCCH + "IPC_EMP_2023/638415285164039007" + RANGO,
    "ipc/ine_base2018.csv":
        INE + "base-2018/series-de-tiempo/ipc-csv.csv?sfvrsn=e9985350_40&download=true",
    "ipc/ine_base2023.csv":
        INE + "base-anual-2023_100/series-de-tiempo/ipc_base_20237baa955a44fe4eada201c196338fb3be.csv"
              "?sfvrsn=2a13310a_73&download=true",
}
FUENTES.update({f"odepa/{y}.csv": indices.URL.format(ds=indices.DATASET, rid=rid, y=y)
                for y, rid in sorted(indices.RESOURCES.items())})
REGISTRO = os.path.join(CRUDOS, "descarga.json")


def registro() -> dict:
    if os.path.exists(REGISTRO):
        with open(REGISTRO, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def bajar(destino: str, url: str, reg: dict, forzar: bool = False) -> bytes:
    ruta = os.path.join(CRUDOS, destino)
    if os.path.exists(ruta) and os.path.getsize(ruta) > 0 and not forzar:
        with open(ruta, "rb") as fh:
            return fh.read()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(ruta + ".tmp", "wb") as fh:
        fh.write(r.content)
    os.replace(ruta + ".tmp", ruta)
    reg[destino] = {"url": url, "utc": datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"), "bytes": len(r.content),
                    "sha256": hashlib.sha256(r.content).hexdigest()}
    print(f"  {destino}: {len(r.content) / 1e6:.2f} MB")
    return r.content


def bajar_sitio(reg: dict) -> None:
    """La foto del sitio: indices.json, catálogo, portada y, de cada corte
    de vacuno del catálogo, su ficha y su serie. Siempre completa."""
    bajar("sitio/indices.json", f"{SITIO}/indices.json", reg, True)
    cat = json.loads(bajar("sitio/catalogo.json", f"{SITIO}/datos/catalogo.json", reg, True))
    bajar("sitio/index.html", f"{SITIO}/", reg, True)
    for f in cat["productos"]:
        if f["grupo"] != GRUPO:
            continue
        bajar(f"sitio/fichas/{f['slug']}.html", f"{SITIO}/productos/{f['slug']}.html", reg, True)
        bajar(f"sitio/productos/{f['slug']}.json", f"{SITIO}/datos/productos/{f['slug']}.json",
              reg, True)


def main() -> None:
    forzar = "--forzar" in sys.argv
    reg = registro()
    sitio_completo = all(os.path.exists(os.path.join(CRUDOS, "sitio", a))
                         for a in ("indices.json", "catalogo.json", "index.html"))
    if forzar or not sitio_completo:
        bajar_sitio(reg)
    for destino, url in FUENTES.items():
        bajar(destino, url, reg, forzar)
    with open(REGISTRO, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=1)
    print(f"listo: {len(reg)} archivos en {CRUDOS}")


if __name__ == "__main__":
    main()

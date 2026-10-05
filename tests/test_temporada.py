"""Veredicto por temporada, sin red. El precio de esta semana, ajustado por
inflación, frente al promedio del mismo mes en cada uno de los 10 años
anteriores (los que tengan precio ese mes, si son al menos 5): CARO si es más
caro que en 7 o más de cada 10, BARATO si en 3 o menos y NORMAL entre medio;
el color de un índice cambia solo si la nueva zona se mantiene dos semanas
seguidas.

Verifica la regla en indices.py (ventana, escalado, empates, la regla de las
dos semanas y los huecos), su uso en resumen(), y en un build sintético: el
cálculo para un indices.json anterior a este cambio, el mes del último IPC,
las frases de los índices y de los productos (concordancia, meses en plural,
la frase contra toda la historia con menos de 5 años), las tarjetas de la
portada, /graficos.html, las páginas de los índices, las fichas y
resumen.json."""
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402
from indices import (BASKETS, comparar_temporada, resumen_temporada,  # noqa: E402
                     veredicto_temporada, zona_temporada)

D = datetime.date
SEMANA = datetime.timedelta(weeks=1)
FIN = D(2026, 9, 28)                   # lunes de la semana vigente (septiembre)


def lunes(desde: D, hasta: D) -> list:
    out, f = [], desde
    while f <= hasta:
        out.append(f)
        f += SEMANA
    return out


def por_anio(fechas, valor_2026, base=1000, paso=100):
    """Un valor fijo por año: 2016 vale base, cada año siguiente 'paso' más
    (los anteriores a 2016, menos que todos) y 2026 vale valor_2026 (un
    número o una lista para sus semanas, en orden)."""
    del_2026 = [f for f in fechas if f.year == 2026]
    v26 = valor_2026 if isinstance(valor_2026, list) else [valor_2026] * len(del_2026)
    assert len(v26) == len(del_2026)
    it = iter(v26)
    return [next(it) if f.year == 2026 else base + paso * (f.year - 2016) for f in fechas]


# ---------------- la regla ----------------
def test_compara_con_el_mismo_mes_de_los_10_anios_anteriores():
    fechas = lunes(D(2008, 1, 7), FIN)
    # cada septiembre vale lo que su año; el resto de los meses, muchísimo
    # (no entran en la comparación de una semana de septiembre)
    v = [1000 + 100 * (f.year - 2016) if f.month == 9 else 99999 for f in fechas]
    v[-1] = 2050
    t = comparar_temporada(fechas, v)
    # 2016 a 2025: 1.000 a 1.900. Bajo 2.050 quedan los 10; los de antes de
    # 2016 (más baratos) no cuentan
    assert t == {"mes": 9, "anios": 10, "debajo": 10, "encima": 0, "percentil": 100,
                 "zona": "CARO"}
    v[-1] = 1450
    assert comparar_temporada(fechas, v) == {"mes": 9, "anios": 10, "debajo": 5, "encima": 5,
                                             "percentil": 50, "zona": "NORMAL"}
    # las otras semanas de septiembre de 2026 no entran (solo años anteriores)
    for i in range(len(v) - 4, len(v) - 1):
        v[i] = 1
    assert comparar_temporada(fechas, v)["debajo"] == 5


def test_empate_no_cuenta_y_promedio_del_mes():
    fechas = lunes(D(2016, 1, 4), FIN)
    v = [1000 + 100 * (f.year - 2016) if f.month == 9 else None for f in fechas]
    # septiembre de 2020: el promedio de sus semanas (1.300 y 1.500 da 1.400)
    sep20 = [i for i, f in enumerate(fechas) if (f.year, f.month) == (2020, 9)]
    for k, i in enumerate(sep20):
        v[i] = 1300 if k % 2 == 0 else 1500
    prom = indices.promedios_mes(fechas, v)[(2020, 9)]
    v[-1] = prom
    t = comparar_temporada(fechas, v)
    assert t["anios"] == 10 and t["debajo"] + t["encima"] == 9      # 2020 empata
    assert t["debajo"] == 4 and t["encima"] == 5


def test_la_semana_va_al_mes_de_su_lunes():
    fechas = lunes(D(2015, 1, 5), D(2026, 8, 31))      # 31-08-2026: lunes de agosto
    v = [1000 if f.month == 8 else 5000 for f in fechas]
    v[-1] = 1001
    t = comparar_temporada(fechas, v)
    assert t["mes"] == 8 and t["debajo"] == 10


def test_con_menos_de_5_anios_del_mes_no_hay_temporada():
    fechas = lunes(D(2022, 1, 3), FIN)             # septiembres: 2022 a 2025
    v = por_anio(fechas, 2000)
    assert comparar_temporada(fechas, v) is None
    assert veredicto_temporada(fechas, v)["temporada"] is None
    assert veredicto_temporada(fechas, [None] * len(fechas)) is None
    fechas = lunes(D(2021, 9, 6), FIN)             # con 2021: 5 años
    t = comparar_temporada(fechas, por_anio(fechas, 2000))
    assert t["anios"] == 5 and t["zona"] == "CARO"
    # un año sin precio ese mes no cuenta: 4 de los 10
    fechas = lunes(D(2008, 1, 7), FIN)
    v = [None if f.month == 9 and 2016 <= f.year <= 2021 else 1000 for f in fechas]
    v[-1] = 2000
    assert comparar_temporada(fechas, v) is None
    # sin ningún valor
    assert comparar_temporada(fechas, [None] * len(fechas)) is None


@pytest.mark.parametrize("debajo, anios, zona", [
    (10, 10, "CARO"), (7, 10, "CARO"), (6, 10, "NORMAL"), (4, 10, "NORMAL"),
    (3, 10, "BARATO"), (0, 10, "BARATO"),
    # con menos años la cuenta se escala: 7 y 3 de cada 10
    (7, 9, "CARO"), (6, 9, "NORMAL"), (3, 9, "NORMAL"), (2, 9, "BARATO"),
    (5, 7, "CARO"), (4, 7, "NORMAL"), (3, 7, "NORMAL"), (2, 7, "BARATO"),
    (4, 6, "NORMAL"), (5, 6, "CARO"), (2, 6, "NORMAL"), (1, 6, "BARATO"),
    (4, 5, "CARO"), (3, 5, "NORMAL"), (2, 5, "NORMAL"), (1, 5, "BARATO"),
])
def test_zonas_escaladas(debajo, anios, zona):
    assert zona_temporada(debajo, anios) == zona


# ---------------- la regla de las dos semanas ----------------
CARO, NORMAL, BARATO = 1950, 1450, 1050     # frente a 1.000 ... 1.900


def serie_2026(zonas: list):
    """2016 a 2025 suben año a año (cada semana, CARO frente a los anteriores);
    en 2026, una semana por zona pedida, desde el 5 de enero."""
    fechas = lunes(D(2016, 1, 4), D(2026, 1, 5) + SEMANA * (len(zonas) - 1))
    return fechas, por_anio(fechas, zonas)


def test_el_color_cambia_solo_con_dos_semanas_seguidas():
    z = [CARO, CARO, NORMAL, CARO, NORMAL, NORMAL, BARATO, NORMAL, BARATO, BARATO]
    esperado = ["CARO", "CARO", "CARO", "CARO", "CARO", "NORMAL", "NORMAL", "NORMAL",
                "NORMAL", "BARATO"]
    crudo = ["CARO", "CARO", "NORMAL", "CARO", "NORMAL", "NORMAL", "BARATO", "NORMAL",
             "BARATO", "BARATO"]
    for k in range(1, len(z) + 1):
        fechas, v = serie_2026(z[:k])
        t = veredicto_temporada(fechas, v)
        assert t["veredicto"] == esperado[k - 1], k
        # la zona de esta semana, antes de la regla
        assert t["temporada"]["zona"] == crudo[k - 1], k


def test_un_hueco_no_cuenta_como_semana_seguida():
    fechas, v = serie_2026([CARO, NORMAL, NORMAL])
    # sin la semana del medio: la segunda NORMAL no sigue a la primera
    sin = [i for i in range(len(fechas)) if i != len(fechas) - 2]
    f2, v2 = [fechas[i] for i in sin], [v[i] for i in sin]
    assert veredicto_temporada(f2, v2)["veredicto"] == "CARO"
    # con la semana sin valor (null), igual
    v3 = list(v)
    v3[-2] = None
    assert veredicto_temporada(fechas, v3)["veredicto"] == "CARO"
    # NaN, como en una serie de pandas, tampoco es precio
    v3[-2] = float("nan")
    assert veredicto_temporada(fechas, v3)["veredicto"] == "CARO"
    assert veredicto_temporada(fechas, v)["veredicto"] == "NORMAL"


def test_semanas_sin_temporada_llevan_el_veredicto_de_toda_la_historia():
    """La fruta real no tiene 5 años de febrero a abril: en esas semanas la
    zona es la del percentil de toda la historia. Al volver la temporada, el
    color sigue la regla de las dos semanas desde ese veredicto, no desde uno
    de meses atrás."""
    fechas, v = [], []
    f = D(2016, 1, 4)
    while f <= D(2026, 6, 15):
        if f.year == 2026 or f.month >= 6:            # sin enero a mayo antes de 2026
            fechas.append(f)
            v.append(1000 + 100 * (f.year - 2016) if f.year < 2026 else
                     (5000 if f.month < 6 else NORMAL))
        f += SEMANA
    # mayo de 2026: sin temporada (ningún mayo antes); el precio más alto de la historia
    hasta_mayo = [i for i, x in enumerate(fechas) if x <= D(2026, 5, 25)]
    t = veredicto_temporada(fechas[:len(hasta_mayo)], v[:len(hasta_mayo)])
    assert t == {"veredicto": "CARO", "temporada": None}
    # 1 de junio: NORMAL frente a los junios, pero la semana anterior iba CARO
    k = len(hasta_mayo) + 1
    t = veredicto_temporada(fechas[:k], v[:k])
    assert (t["temporada"]["zona"], t["veredicto"]) == ("NORMAL", "CARO")
    # 8 de junio: dos semanas seguidas en NORMAL
    t = veredicto_temporada(fechas[:k + 1], v[:k + 1])
    assert (t["temporada"]["zona"], t["veredicto"]) == ("NORMAL", "NORMAL")
    assert indices.zona_historia(32) == "BARATO" and indices.zona_historia(65) == "NORMAL"
    assert indices.zona_historia(66) == "CARO"


def test_al_salir_de_la_temporada_el_color_tambien_espera_dos_semanas():
    """Al revés: de septiembre (con temporada, NORMAL) a octubre sin
    temporada (ningún octubre antes), con el precio más alto de la historia.
    La primera semana de octubre sigue NORMAL; la segunda pasa a CARO. En
    resumen_temporada la base es toda la historia y su zona, la que se pasa."""
    fechas = [f for f in lunes(D(2016, 1, 4), D(2026, 10, 12)) if f.year == 2026 or f.month < 10]
    v = [5000 if f.month == 10 else 1000 + 100 * (f.year - 2016) if f.year < 2026 else NORMAL
         for f in fechas]
    real = [{"time": f.isoformat(), "value": x} for f, x in zip(fechas, v)]
    t = veredicto_temporada(fechas[:-1], v[:-1])
    assert t == {"veredicto": "NORMAL", "temporada": None}
    assert veredicto_temporada(fechas, v) == {"veredicto": "CARO", "temporada": None}
    assert resumen_temporada(real[:-1], "CARO") == {
        "veredicto": "NORMAL", "base_veredicto": "toda la historia",
        "percentil_temporada": None, "anios_temporada": None, "temporada": None}
    assert resumen_temporada(real, "CARO")["veredicto"] == "CARO"
    # la zona de la última semana es la que se pasa (la de resumen, sin redondear)
    assert resumen_temporada(real, "NORMAL")["veredicto"] == "NORMAL"


def test_resumen_temporada():
    fechas, v = serie_2026([NORMAL, NORMAL, CARO])
    real = [{"time": f.isoformat(), "value": x} for f, x in zip(fechas, v)]
    r = resumen_temporada(real, "BARATO")
    assert r == {"veredicto": "NORMAL", "base_veredicto": "mismo mes, ultimos 10 anios",
                 "percentil_temporada": 100, "anios_temporada": 10,
                 "temporada": {"mes": 1, "anios": 10, "debajo": 10, "encima": 0,
                               "percentil": 100, "zona": "CARO"}}
    # sin temporada: la base es toda la historia (cuatro años: 2022 a 2025 y
    # las tres semanas de 2026). Las dos de 1.450 son las más baratas: BARATO
    # dos semanas seguidas; la última (1.950, la más cara) recién entra a CARO
    assert resumen_temporada(real[-200:], "CARO") == {
        "veredicto": "BARATO", "base_veredicto": "toda la historia",
        "percentil_temporada": None, "anios_temporada": None, "temporada": None}
    assert resumen_temporada([], "CARO")["veredicto"] == "CARO"


def test_resumen_de_indices_usa_la_temporada():
    """indices.resumen: el veredicto por temporada, sobre la serie publicada
    (enteros); el percentil sigue siendo el de toda la historia."""
    fechas = lunes(D(2014, 1, 6), FIN)
    v = por_anio(fechas, NORMAL)
    v[-1] = 1950.4                                    # esta semana, CARO (una sola)
    idx = pd.DatetimeIndex(fechas)
    out = pd.DataFrame({"nominal": v, "min_nom": v, "max_nom": v, "real": v,
                        "rmin": v, "rmax": v}, index=idx)
    r = indices.resumen(out, {"nombre": "Índice X", "subtitulo": "x"}, [])
    assert r["veredicto"] == "NORMAL" and r["color"] == indices.COLORES["NORMAL"]
    assert r["temporada"]["zona"] == "CARO" and r["percentil_temporada"] == 100
    assert r["base_veredicto"] == "mismo mes, ultimos 10 anios" and r["anios_temporada"] == 10
    # el percentil de toda la historia, como antes
    real = np.array(v, dtype=float)
    assert r["percentil"] == round(100.0 * (real <= real[-1]).mean())
    assert r == {**r, **resumen_temporada(r["real"], "CARO")}
    # el orden de siempre, con los campos nuevos tras el color
    claves = list(r)
    assert claves[claves.index("color") + 1:claves.index("n")] == [
        "base_veredicto", "percentil_temporada", "anios_temporada", "temporada"]


# ---------------- el sitio ----------------
def _serie_real(fechas, v, factor):
    return ([{"time": f.isoformat(), "value": x} for f, x in zip(fechas, v)],
            [{"time": f.isoformat(), "value": round(x * factor(f))} for f, x in zip(fechas, v)])


def sintetico() -> dict:
    """Un indices.json anterior a este cambio (sin el veredicto por temporada
    ni ipc_mes), con 4 índices: Asado CARO (más caro que los 10 septiembres),
    Ensalada NORMAL con esta semana en CARO (la primera), Fruta BARATO y
    Desayuno con 3 años (sin temporada). El precio de la época difiere del
    ajustado hasta julio de 2026: el último IPC es el de agosto."""
    def factor(f):
        return 1.0 if f >= D(2026, 8, 3) else 0.97
    fechas = lunes(D(2014, 1, 6), FIN)
    v26 = {"asado": 2000, "ensalada": NORMAL, "fruta": 900}
    out = {"generado": "2026-10-02", "indices": {}, "productos": {}, "descartes": []}
    for code, meta in BASKETS.items():
        if code == "desayuno":
            f = lunes(D(2023, 1, 2), FIN)
            v = [1000 + 10 * i for i in range(len(f))]
        else:
            f = fechas
            v = por_anio(f, v26[code])
            if code == "ensalada":
                v[-1] = 1750                          # más caro que 8 de los 10
        real, nominal = _serie_real(f, v, factor)
        out["indices"][code] = {
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"], "fecha": "28-09-2026",
            "costo_nominal": v[-1], "costo_real": v[-1], "percentil": 90, "zscore": 1.0,
            "vs_promedio": 12, "veredicto": "CARO", "color": "#e0552f", "n": len(real),
            "componentes": [{"label": lab, "qty": qty, "unidad": uni, "odepa_unit": "$/kg",
                             "factor": 1.0, "mismatch": False, "precio_ult": 1000, "aporte": 1000}
                            for (lab, _m, qty, uni) in meta["items"]],
            "estacionalidad": {"factores": {str(m): 1.0 for m in range(1, 13)},
                               "mes_barato": 1, "mes_caro": 2, "amplitud": 1},
            "velas": [], "nominal": nominal, "real": real,
        }

    def producto(label, grupo, valor_2026, desde=D(2014, 1, 6), hasta=FIN):
        f = lunes(desde, hasta)
        v = por_anio(f, valor_2026) if desde.year < 2026 else [valor_2026] * len(f)
        return {"label": label, "unidad": "kg", "grupo": grupo, "t0": desde.isoformat(), "v": v}
    p = out["productos"]
    p["palta"] = producto("Palta", "Frutas", 1950)
    p["lentejas"] = producto("Lentejas", "Abarrotes y otros", 950)
    p["porotos"] = producto("Porotos", "Abarrotes y otros", 1450)
    p["kiwi"] = producto("Kiwi", "Frutas", 1450, desde=D(2024, 1, 1))
    # sin precio esta semana: su último dato es de abril (22 semanas), del
    # 31 de agosto (4 semanas, lleva la frase de temporada) y del 24 de
    # agosto (5 semanas, ya no)
    p["chirimoya"] = producto("Chirimoya", "Frutas", 1950, hasta=D(2026, 4, 27))
    p["cereza"] = producto("Cereza", "Frutas", 1950, hasta=D(2026, 8, 31))
    p["uva"] = producto("Uva", "Frutas", 1450, hasta=D(2026, 8, 24))
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_temporada")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(sintetico(), ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8", CARESTIA_TARJETAS="0",
               CARESTIA_AHORA="2026-10-02T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d, r.stdout


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _epoca(d, valor, mes):
    """Un precio ajustado, a precio de la época de ese mes, con el factor del
    datafeed: nominal sobre real de los 4 índices, sumados en el mes."""
    data = json.loads(_leer(d, "indices.json"))
    nom = real = 0
    for ind in data["indices"].values():
        n = {p["time"]: p["value"] for p in ind["nominal"]}
        for p in ind["real"]:
            if p["time"].startswith(mes):
                nom, real = nom + n[p["time"]], real + p["value"]
    return "$" + f"{math.floor(valor * nom / real + 0.5):,}".replace(",", ".")


def _visible(h: str) -> str:
    h = re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", h).split())


def test_indices_json_anterior_se_completa_con_la_misma_regla(sitio):
    d, log = sitio
    assert ("AVISO: indices.json sin el veredicto por temporada (anterior a este cambio de "
            "indices.py); se calcula aquí para asado, ensalada, fruta, desayuno.") in log
    data = json.loads(_leer(d, "indices.json"))
    for code, ind in data["indices"].items():
        j = json.loads(_leer(d, f"datos/indices/{code}.json"))
        esperado = resumen_temporada(ind["real"], ind["veredicto"])
        assert {k: j[k] for k in esperado} == esperado, code
        assert j["color"] == indices.COLORES[esperado["veredicto"]], code
    asado = json.loads(_leer(d, "datos/indices/asado.json"))
    assert asado["veredicto"] == "CARO" and asado["temporada"]["debajo"] == 10
    ens = json.loads(_leer(d, "datos/indices/ensalada.json"))
    assert ens["veredicto"] == "NORMAL" and ens["temporada"]["zona"] == "CARO"
    assert json.loads(_leer(d, "datos/indices/fruta.json"))["veredicto"] == "BARATO"
    # Desayuno: 3 septiembres, sin temporada; queda el veredicto de antes
    des = json.loads(_leer(d, "datos/indices/desayuno.json"))
    assert des["veredicto"] == "CARO" and des["base_veredicto"] == "toda la historia"


def test_mes_del_ipc_deducido_de_los_indices(sitio):
    d, log = sitio
    assert "AVISO IPC: indices.json no trae ipc_mes; por los índices, el último IPC es el de 2026-08." in log
    assert "Precios ajustados en pesos de agosto de 2026" in log
    assert "Cada precio pasado, llevado a pesos de agosto de 2026 con el IPC." in _leer(d, "graficos.html")


def test_resumen_json_con_los_campos_nuevos(sitio):
    d, _ = sitio
    r = json.loads(_leer(d, "resumen.json"))
    asado = r["indices"]["asado"]
    assert list(asado) == ["nombre", "subtitulo", "costo_pesos_hoy", "veredicto", "percentil",
                           "vs_promedio_pct", "variacion_semanal_pct", "semanas_historia",
                           "percentil_temporada", "anios_temporada", "base_veredicto"]
    assert (asado["veredicto"], asado["percentil"], asado["percentil_temporada"],
            asado["anios_temporada"], asado["base_veredicto"]) == \
        ("CARO", 90, 100, 10, "mismo mes, ultimos 10 anios")
    ens = r["indices"]["ensalada"]
    assert (ens["veredicto"], ens["percentil_temporada"]) == ("NORMAL", 80)
    des = r["indices"]["desayuno"]
    assert (des["veredicto"], des["percentil_temporada"], des["anios_temporada"],
            des["base_veredicto"]) == ("CARO", None, None, "toda la historia")
    # validar.py arma lo mismo (y lo acepta)
    import validar
    data = json.loads(_leer(d, "indices.json"))
    for code, ind in data["indices"].items():
        ind.update(json.loads(_leer(d, f"datos/indices/{code}.json")))
    propio = validar.resumen_desde_indices(data)["indices"]
    assert propio == r["indices"]
    assert all(validar.chequear_base(c, n)[1] for c, n in propio.items())


FRASES = {
    "asado": "Más caro que en 10 de los últimos 10 septiembres, aun descontando la inflación.",
    # esta semana entra a CARO (la primera) y el color sigue NORMAL: la frase
    # sigue al color, con el N de esta semana
    "ensalada": "Dentro de lo normal para septiembre: más caro que en 8 de los últimos 10.",
    "fruta": "Más barato que en 10 de los últimos 10 septiembres, aun descontando la inflación.",
}


def test_tarjetas_de_la_portada(sitio):
    d, _ = sitio
    h = _leer(d, "index.html")
    tarjetas = dict(re.findall(r'<a class="icard" href="/graficos.html#(\w+)">(.*?)</a>', h, re.S))
    for code, frase in FRASES.items():
        assert f'<p class="ic-fr">{frase}</p>' in tarjetas[code], code
        assert '<div class="zonas" aria-hidden="true">' in tarjetas[code], code
    assert 'style="left:100%"' in tarjetas["asado"] and 'style="left:0%"' in tarjetas["fruta"]
    assert 'style="left:80%"' in tarjetas["ensalada"]
    # el color, con la regla de las dos semanas
    assert 'style="background:var(--ambar)">NORMAL<' in tarjetas["ensalada"]
    assert 'style="background:var(--verde)">BARATO<' in tarjetas["fruta"]
    # sin temporada: la frase y las zonas de toda la historia
    assert '<div class="zonas historia" aria-hidden="true">' in tarjetas["desayuno"]
    assert "de cada 10 semanas desde 2023, descontada la inflación.</p>" in tarjetas["desayuno"]
    # el percentil de toda la historia, como dato secundario
    for code in BASKETS:
        assert "<span>percentil 90 en su historia</span>" in tarjetas[code], code
    # las zonas: 30, 40 y 30 por temporada; 33, 33 y 34 en la historia
    assert ".zonas .z { flex:32 1 0; }" in h and ".zonas .z2 { flex-grow:36;" in h
    assert ".zonas.historia .z { flex-grow:33; }" in h


def test_graficos_y_paginas_de_los_indices(sitio):
    d, _ = sitio
    app = json.loads(re.search(r"const DATA = (\{.*?\});\n", _leer(d, "graficos.html"))
                     .group(1).replace("<\\/", "</"))
    for code, frase in FRASES.items():
        assert app["indices"][code]["frase"] == frase, code
        h = _leer(d, f"indices/{code}.html")
        assert frase in h, code
        assert re.search(r'<meta name="description" content="[^"]*' + re.escape(frase), h), code
    assert app["indices"]["asado"]["historia"] == (
        "Percentil 90 de 665 semanas en su historia, +12% sobre su promedio histórico, "
        "ajustado por inflación, en pesos de agosto de 2026.")
    assert "document.getElementById('opct').textContent = d.frase;" in _leer(d, "graficos.html")
    # el número grande sin etiqueta de ajuste
    asado = _leer(d, "indices/asado.html")
    assert '<span class="ind-precio">$2.000</span><span class="ind-pill"' in asado
    assert "pesos de hoy" not in asado


def test_fichas_frase_principal_y_percentil_secundario(sitio):
    d, _ = sitio
    palta = _leer(d, "productos/palta.html")
    assert '<p class="pct">Más cara que en 10 de los últimos 10 septiembres, aun descontando la inflación.</p>' in palta
    # "ajustada": concuerda con el producto (la palta)
    assert re.search(r'<p class="pct2">Frente a toda su historia, está más cara que en el \d+% de '
                     r'las semanas desde 2014, ajustada por inflación, en pesos de agosto de 2026\.</p>',
                     palta)
    # sin píldora: el semáforo es de los índices
    assert "ic-pill" not in palta and "badge" not in palta.split("</style>")[1]
    assert '<div class="miga">Precio de esta semana en Santiago</div>' in palta
    assert '<div class="ouni">por kilo</div>' in palta
    assert ('<p class="pct">Más baratas que en 10 de los últimos 10 septiembres, aun '
            'descontando la inflación.</p>') in _leer(d, "productos/lentejas.html")
    assert ('<p class="pct">Dentro de lo normal para septiembre: más caros que en 5 de los '
            'últimos 10.</p>') in _leer(d, "productos/porotos.html")
    # menos de 5 años del mes: la frase de antes, contra toda la historia
    kiwi = _leer(d, "productos/kiwi.html")
    assert re.search(r'<p class="pct">Hoy está más barato que en el \d+% de las semanas desde '
                     r'2024, ajustado por inflación, en pesos de agosto de 2026\.</p>', kiwi)
    assert 'class="pct2"' not in kiwi
    # sin precio esta semana: sin número grande (es siempre el de esta
    # semana), el último dato a precio de la época y su semana
    ch = _leer(d, "productos/chirimoya.html")
    ultimo = f"Sin precio de ODEPA esta semana. Último dato: {_epoca(d, 1950, '2026-04')}, semana del 27-04-2026."
    assert f'<p class="pct">{ultimo}</p>' in ch
    assert '<div class="miga">Último precio publicado en Santiago</div>' in ch
    assert 'class="orow"' not in ch and 'class="oprice"' not in ch
    assert re.search(r'<p class="pct2">Frente a toda su historia, estaba más cara que', ch)
    assert re.search(r'<meta name="description" content="' + re.escape(ultimo) + ' Precio por kilo', ch)
    assert "Hoy" not in _visible(ch.split("<main>")[1].split('<div class="unidad"')[0])
    # con 4 semanas o menos, más la frase de temporada (agosto: el mes de ese dato)
    assert ('<p class="pct">Sin precio de ODEPA esta semana. Último dato: $1.950, semana del '
            '31-08-2026. Más cara que en 10 de los últimos 10 agostos, aun descontando la '
            'inflación.</p>') in _leer(d, "productos/cereza.html")
    assert ('<p class="pct">Sin precio de ODEPA esta semana. Último dato: $1.450, semana del '
            '24-08-2026.</p>') in _leer(d, "productos/uva.html")


def test_tarjetas_og_con_la_frase(sitio):
    d, _ = sitio
    palta = _leer(d, "productos/palta.html")
    assert ('content="Palta: $1.950 por kilo, semana del 28-09-2026. Más cara que en 10 de los '
            'últimos 10 septiembres, aun descontando la inflación."') in palta
    ens = _leer(d, "indices/ensalada.html")
    assert ('content="Índice Ensalada: $1.750, NORMAL, semana del 28-09-2026. Dentro de lo normal '
            'para septiembre: más caro que en 8 de los últimos 10."') in ens
    # con menos de 5 años de ese mes, la frase contra toda la historia
    assert re.search(r'content="Kiwi: \$1\.450 por kilo, semana del 28-09-2026\. Más barato que '
                     r'en \d+ de cada 10 semanas desde 2024, descontada la inflación\."',
                     _leer(d, "productos/kiwi.html"))
    # sin precio esta semana: el último dato a precio de la época y, si es
    # reciente, la frase de temporada; si no, que no hay precio esta semana
    assert (f'content="Chirimoya: {_epoca(d, 1950, "2026-04")} por kilo, semana del 27-04-2026. '
            'Sin precio de ODEPA esta semana."') in _leer(d, "productos/chirimoya.html")
    assert ('content="Cereza: $1.950 por kilo, semana del 31-08-2026. Más cara que en 10 de los '
            'últimos 10 agostos, aun descontando la inflación."') in _leer(d, "productos/cereza.html")
    assert ('content="Uva: $1.450 por kilo, semana del 24-08-2026. Sin precio de ODEPA esta '
            'semana."') in _leer(d, "productos/uva.html")


def test_sin_pesos_de_hoy(sitio):
    """"Pesos de hoy" ya no se dice en ninguna página: ajustado por inflación,
    en pesos del mes del último IPC. Acerca y términos (textos del dueño)
    dicen "ajustados por inflación"."""
    d, _ = sitio
    con = []
    for raiz, _dirs, archivos in os.walk(d):
        for a in archivos:
            if a.endswith((".html", ".js")):
                ruta = os.path.join(raiz, a)
                with open(ruta, encoding="utf-8") as fh:
                    texto = fh.read()
                if "pesos de hoy" in (_visible(texto) if a.endswith(".html") else texto):
                    con.append(os.path.relpath(ruta, d))
    assert con == [], con
    assert ("las series de más de cien productos de la Región Metropolitana, todos ajustados por inflación, para que cualquiera pueda ver si algo está caro o barato respecto de su propia historia. ") \
        in _visible(_leer(d, "acerca.html"))
    assert "expresados" not in _visible(_leer(d, "acerca.html"))
    terminos = _visible(_leer(d, "terminos.html"))
    assert "Última actualización: 5 de octubre de 2026" in terminos
    assert "de la Región Metropolitana, ajustados por inflación y elaborados sobre datos públicos." in terminos
    assert "sus valores históricos ajustados por inflación cambian" in terminos

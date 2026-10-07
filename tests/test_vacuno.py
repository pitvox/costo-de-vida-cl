"""Pruebas sin red de la nota de vacuno (analisis/vacuno/). No tocan el sitio:
revisan las reglas de las cifras con series sintéticas, que el informe, la
tabla y resumen.json salgan de las series guardadas en
resultados/series_vacuno.json, y que el informe y el gráfico respeten las
reglas de texto de CLAUDE.md."""
import ast
import csv
import datetime
import importlib.util
import json
import os
import re
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALISIS = os.path.join(RAIZ, "analisis", "vacuno")
sys.path.insert(0, ANALISIS)
import vacuno  # noqa: E402
from test_texto import infracciones  # noqa: E402

LUNES = datetime.date(2014, 1, 6)


def serie(valores, t0=LUNES):
    return {"label": "Corte", "unidad": "kg", "grupo": "Carne bovina",
            "t0": t0.isoformat(), "v": list(valores)}


def semanas(desde, hasta):
    """Los lunes de desde a hasta, los dos incluidos."""
    return [desde + datetime.timedelta(weeks=j) for j in range((hasta - desde).days // 7 + 1)]


def resultado(nombre):
    return os.path.join(ANALISIS, "resultados", nombre)


# ---------- las reglas ----------
def test_historia_cuenta_como_la_ficha_y_el_catalogo():
    h = vacuno.historia([10, 20, 20, None, 30, 20], 5)
    # 5 semanas con precio: una más barata, una más cara, tres iguales
    assert (h["n"], h["debajo"], h["encima"]) == (5, 1, 1)
    assert h["ficha"] == 20 and h["catalogo"] == 80


def test_el_5_por_ciento_mas_caro_sin_redondear():
    # 95 de 100 semanas más baratas: entra
    assert vacuno.en_top(vacuno.historia(list(range(1, 96)) + [200] * 4 + [100], 99))
    # 947 de 1000 (94,7%) redondea a 95 en la ficha, pero queda fuera
    h = vacuno.historia(list(range(1, 948)) + [5000] * 52 + [1000], 999)
    assert h["ficha"] == 95 and not vacuno.en_top(h)


def test_maximo_de_10_anios_con_margen_de_1_por_ciento():
    n = 11 * 52 + 1
    base = [100.0] * n
    p = serie(base[:-1] + [100.5])
    m = vacuno.maximo(vacuno.fechas(p), p["v"], n - 1)
    assert m["cubre"] and m["es_maximo"] and not m["se_afirma"]   # 0,5%: no se afirma
    p = serie(base[:-1] + [101.2])
    m = vacuno.maximo(vacuno.fechas(p), p["v"], n - 1)
    assert m["se_afirma"] and m["margen_pct"] == pytest.approx(1.2)
    # exactamente 1% no basta: tiene que ser más de 1%
    p = serie(base[:-1] + [101.0])
    assert not vacuno.maximo(vacuno.fechas(p), p["v"], n - 1)["se_afirma"]


def test_maximo_solo_mira_los_10_anios_anteriores():
    # un precio más alto hace 11 años no cuenta para "en al menos 10 años",
    # pero sí para toda la serie
    n = 11 * 52 + 1
    v = [150.0] + [100.0] * (n - 2) + [105.0]
    p = serie(v)
    m = vacuno.maximo(vacuno.fechas(p), v, n - 1)
    assert m["se_afirma"] and m["margen_total_pct"] < 0
    assert m["ultima_igual_o_mayor"] == LUNES


def test_sin_10_anios_de_serie_no_hay_maximo_de_10_anios():
    v = [100.0] * (5 * 52) + [120.0]
    p = serie(v)
    m = vacuno.maximo(vacuno.fechas(p), v, len(v) - 1)
    assert not m["cubre"] and not m["es_maximo"] and not m["se_afirma"]


def test_la_semana_de_hace_10_anios_entra_en_la_ventana():
    # la última semana es la del lunes 2026-09-28: el 28-09-2016 cae en la
    # semana del lunes 2016-09-26, que entra; una semana más caro ahí lo impide
    fs = semanas(datetime.date(2015, 12, 14), datetime.date(2026, 9, 28))
    i = len(fs) - 1
    j = fs.index(datetime.date(2016, 9, 26))
    v = [100.0] * len(fs)
    v[i], v[j] = 110.0, 120.0
    assert not vacuno.maximo(fs, v, i)["es_maximo"]
    v[j], v[j - 1] = 100.0, 120.0       # la semana anterior ya no entra
    assert vacuno.maximo(fs, v, i)["se_afirma"]


def test_una_serie_que_parte_despues_del_dia_de_hace_10_anios_no_cubre():
    # parte el lunes siguiente al 28-09-2016: le falta una semana
    fs = semanas(datetime.date(2016, 10, 3), datetime.date(2026, 9, 28))
    v = [100.0] * (len(fs) - 1) + [150.0]
    m = vacuno.maximo(fs, v, len(fs) - 1)
    assert not m["cubre"] and not m["se_afirma"]
    fs = semanas(datetime.date(2016, 9, 26), datetime.date(2026, 9, 28))
    v = [100.0] * (len(fs) - 1) + [150.0]
    assert vacuno.maximo(fs, v, len(fs) - 1)["se_afirma"]


def test_propio_sin_rango_es_semana_arrastrada():
    p = {"v": [10, 10, None], "min": [9, None, None], "max": [11, None, None]}
    assert vacuno.propio(p, 0) and not vacuno.propio(p, 1) and not vacuno.propio(p, 2)
    assert vacuno.propio({"v": [10], "min": [], "max": []}, 0)   # sin rango en el archivo


def test_maximo_mensual_promedia_el_mes_contra_los_120_anteriores():
    t0 = datetime.date(2016, 1, 4)
    fs = [t0 + datetime.timedelta(weeks=j) for j in range(560)]
    v = [100.0] * 560
    i = 559
    mes = (fs[i].year, fs[i].month)
    for j in range(560):
        if (fs[j].year, fs[j].month) == mes:
            v[j] = 102.0                    # todo el mes 2% más caro
    m = vacuno.maximo_mensual(fs, v, i)
    assert m["se_afirma"] and m["margen_pct"] == pytest.approx(2.0)


def test_variacion_anual_contra_52_semanas_y_sin_precio_es_none():
    v = [100.0] + [None] * 51 + [106.3]
    assert vacuno.variacion_anual(v, 52) == pytest.approx(6.3)
    assert vacuno.variacion_anual([None] + [1.0] * 52, 52) is None


def test_formato_de_cifras():
    assert vacuno.clp(12922) == "$12.922"
    assert vacuno.pct(6.3) == "+6,3%" and vacuno.pct(-3.66) == "-3,7%"
    assert vacuno.fecha_larga(datetime.date(2026, 9, 28)) == "28 de septiembre de 2026"


# ---------- las cifras guardadas ----------
@pytest.fixture(scope="module")
def guardado():
    if not os.path.exists(resultado("series_vacuno.json")):
        pytest.skip("todavía no hay resultados")
    with open(resultado("series_vacuno.json"), encoding="utf-8") as fh:
        series = json.load(fh)
    with open(resultado("resumen.json"), encoding="utf-8") as fh:
        resumen = json.load(fh)
    return vacuno.desde_series(series), series, resumen


def test_resumen_sale_de_las_series_guardadas(guardado):
    prods, series, resumen = guardado
    assert series["sha256"] == resumen["sha256"]
    nuevo = vacuno.resumen(series, series["sha256"], prods)
    assert json.loads(json.dumps(nuevo, default=str)) == resumen


def test_las_tres_cifras_de_la_nota(guardado):
    _, _, r = guardado
    assert (r["A"]["top5"], r["A"]["de"]) == (20, 24)
    assert r["B"]["se_afirman"] == []
    assert (r["C"]["precio"], r["C"]["variacion_anual"]) == (12922, 6.3)
    assert r["C"]["anio_antes_propio"]                     # un precio de ODEPA, no arrastrado


def test_cortes_csv_sale_de_las_series_guardadas(guardado):
    prods, _, _ = guardado
    with open(resultado("cortes.csv"), encoding="utf-8") as fh:
        filas = {f["clave"]: f for f in csv.DictReader(fh)}
    assert set(filas) == set(prods)
    for k, p in prods.items():
        esperado = {c: str(x) for c, x in vacuno.fila(k, p, vacuno.cifras(p)).items()}
        assert filas[k] == esperado, k


# ---------- el informe ----------
def informe() -> str:
    ruta = os.path.join(ANALISIS, "informe.md")
    if not os.path.exists(ruta):
        pytest.skip("todavía no hay informe")
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def test_tabla_del_informe_es_la_de_cortes_csv():
    with open(resultado("cortes.csv"), encoding="utf-8") as fh:
        filas = {f["corte"].lower(): f for f in csv.DictReader(fh)}
    tabla = [[c.strip() for c in linea.strip("|").split("|")]
             for linea in informe().splitlines()
             if linea.startswith("| ") and not linea.startswith("| Corte")]
    assert len(tabla) == len(filas) == 24
    for corte, precio, hist, sept, anual, maximo in tabla:
        f = filas[corte.lower()]
        semana = datetime.date.fromisoformat(f["semana_max_10_anios"])
        # el 100% de la ficha, marcado cuando es redondeo
        marca = "*" if f["ficha_pct"] == "100" and float(f["pct_mas_barato"]) < 100 else ""
        assert precio == vacuno.clp(int(f["precio"])), corte
        assert hist == f"{f['ficha_pct']}%{marca} (desde {f['desde'][:4]})", corte
        assert sept == f["debajo_mes"], corte
        assert anual == vacuno.pct(float(f["variacion_anual"])), corte
        assert maximo == f"{vacuno.clp(int(f['max_10_anios']))} ({semana:%d-%m-%Y})", corte


def test_informe_dice_las_tres_cifras():
    t = informe()
    assert "**20 de los 24 cortes están en el 5% más caro de su historia**" in t
    assert "**Ninguno está esta semana en su precio real más alto en al menos 10 años**" in t
    assert "$12.922 el kilo, +6,3% sobre la semana del 29 de septiembre de 2025" in t


def test_informe_cita_las_comparaciones_de_verificacion_csv():
    with open(resultado("verificacion.csv"), encoding="utf-8") as fh:
        filas = [f for f in csv.DictReader(fh) if f["ok"] != ""]
    assert filas and all(f["ok"] == "1" for f in filas)
    assert f"{len(filas)} comparaciones" in informe()


def test_vacuno_no_se_releva_en_ferias():
    # ODEPA releva carne de vacuno en carnicerías y supermercados, no en ferias
    assert "feria" not in informe().lower().replace("no hay ferias", "")
    assert not [s for s in _strings_graficar() if "feria" in s.lower()]


def test_informe_trae_lo_que_no_podemos_afirmar():
    t = informe()
    seccion = t.split("## Lo que no podemos afirmar", 1)[1]
    for tema in ("**Causas.**", "**Proyecciones.**", "**Récord.**", "**Todo Chile, ni un local.**"):
        assert tema in seccion, tema


def test_informe_pdf_de_una_pagina_y_al_dia():
    ruta = os.path.join(ANALISIS, "informe.pdf")
    if not os.path.exists(ruta):
        pytest.skip("todavía no hay PDF")
    spec = importlib.util.spec_from_file_location("vacuno_imprimir",
                                                  os.path.join(ANALISIS, "imprimir.py"))
    imprimir = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imprimir)
    with open(ruta, "rb") as fh:
        pdf = fh.read()
    assert imprimir.paginas(pdf) == 1
    # el título del PDF lleva la huella del informe.md del que salió
    assert imprimir.huella().encode() in pdf, "informe.pdf no salió de este informe.md"


def test_informe_sin_rayas_ni_muletillas():
    assert infracciones(informe()) == []


def test_informe_meses_en_minuscula_dentro_de_la_frase():
    t = informe()
    meses = "|".join(m.capitalize() for m in vacuno.MESES)
    # un mes con mayúscula solo al comienzo de una línea, de una oración o
    # de una celda
    malos = [m.group(0) for m in re.finditer(rf"\b({meses})\b", t)
             if not re.search(r"(^|\n|[.|*#]\s*)$", t[:m.start()])]
    assert malos == []
    assert not re.search(r"\b(Ene|Feb|Abr|Ago|Sept?|Dic)\.?\s*\d", informe())


# ---------- el gráfico ----------
def _strings_graficar() -> list:
    """Los strings de graficar.py que llegan al gráfico (sin docstrings)."""
    with open(os.path.join(ANALISIS, "graficar.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    fuera = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef)) and nodo.body:
            primero = nodo.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                fuera.add(id(primero.value))
    return [n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in fuera]


def test_textos_del_grafico_sin_rayas_ni_muletillas():
    assert [s for s in _strings_graficar() if infracciones(s)] == []


def test_grafico_de_1080_por_1080():
    ruta = os.path.join(ANALISIS, "grafico_vacuno.png")
    if not os.path.exists(ruta):
        pytest.skip("todavía no hay gráfico")
    from PIL import Image
    with Image.open(ruta) as im:
        assert im.size == (1080, 1080)


def test_grafico_dibujado_respeta_las_reglas(tmp_path, guardado):
    pytest.importorskip("matplotlib")
    # por ruta y con nombre propio: analisis/estimacion_ipc también tiene un
    # graficar.py y el orden de sys.path depende del orden de los tests
    spec = importlib.util.spec_from_file_location("vacuno_graficar",
                                                  os.path.join(ANALISIS, "graficar.py"))
    graficar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graficar)
    _, series, _ = guardado
    salida = graficar.graficar(series, str(tmp_path / "g.png"))
    from PIL import Image
    with Image.open(salida) as im:
        assert im.size == (1080, 1080)
    assert graficar.TEXTOS and [s for s in graficar.TEXTOS if infracciones(s)] == []
    assert "Punto: semana del 28 de septiembre de 2026." in " ".join(graficar.TEXTOS)

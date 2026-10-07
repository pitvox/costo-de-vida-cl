"""Pruebas sin red de la nota de vacuno (analisis/vacuno/). No tocan el sitio:
revisan las reglas de las cifras con series sintéticas, que el informe, la
tabla y resumen.json salgan de las series guardadas en
resultados/series_vacuno.json, y que el informe y el gráfico respeten las
reglas de texto de CLAUDE.md."""
import ast
import csv
import datetime
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


def resultado(nombre):
    return os.path.join(ANALISIS, "resultados", nombre)


# ---------- las reglas ----------
def test_historia_cuenta_como_la_ficha_y_el_catalogo():
    h = vacuno.historia([10, 20, 20, None, 30, 20], 5)
    # 5 semanas con precio: una más barata, una más cara, tres iguales
    assert (h["n"], h["debajo"], h["encima"]) == (5, 1, 1)
    assert h["ficha"] == 20 and h["catalogo"] == 80


def test_el_5_por_ciento_mas_caro_sin_redondear():
    # 95 de 100 semanas más baratas: entra; 94 de 100 (redondea igual a 94): no
    assert vacuno.en_top(vacuno.historia(list(range(1, 96)) + [200] * 4 + [100], 99))
    h = vacuno.historia(list(range(1, 95)) + [200] * 5 + [100], 99)
    assert h["pct_debajo"] == 94 and not vacuno.en_top(h)


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
        mes = datetime.date.fromisoformat(f["semana_max_10_anios"])
        assert precio == vacuno.clp(int(f["precio"])), corte
        assert hist == f"{f['ficha_pct']}% (desde {f['desde'][:4]})", corte
        assert sept == f["debajo_mes"], corte
        assert anual == vacuno.pct(float(f["variacion_anual"])), corte
        assert maximo == (f"{vacuno.clp(int(f['max_10_anios']))} "
                          f"({vacuno.MESES[mes.month - 1]} de {mes.year})"), corte


def test_informe_dice_las_tres_cifras():
    t = informe()
    assert "**20 de los 24 cortes están en el 5% más caro de su historia**" in t
    assert "**Ninguno está esta semana en su precio real más alto en al menos 10 años.**" in t
    assert "$12.922 el kilo esta semana, +6,3% sobre la semana del 29 de septiembre de 2025" in t


def test_informe_trae_lo_que_no_podemos_afirmar():
    t = informe()
    seccion = t.split("## Lo que no podemos afirmar", 1)[1]
    for tema in ("Por qué subió", "Qué va a pasar", "máximo o récord", "todo Chile"):
        assert tema in seccion, tema


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
    import graficar
    _, series, _ = guardado
    salida = graficar.graficar(series, str(tmp_path / "g.png"))
    from PIL import Image
    with Image.open(salida) as im:
        assert im.size == (1080, 1080)
    assert graficar.TEXTOS and [s for s in graficar.TEXTOS if infracciones(s)] == []
    assert "Punto: semana del 28 de septiembre de 2026." in " ".join(graficar.TEXTOS)

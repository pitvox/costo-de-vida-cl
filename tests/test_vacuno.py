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


def cargar_modulo(nombre):
    """Un script de analisis/vacuno por su ruta y con nombre propio: otros
    análisis tienen scripts con el mismo nombre (graficar.py) y el orden de
    sys.path depende del orden de los tests."""
    spec = importlib.util.spec_from_file_location(f"vacuno_{nombre}",
                                                  os.path.join(ANALISIS, f"{nombre}.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


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
    # 947 de 1000 (94,7%): fuera, y la ficha dice 94 (trunca)
    h = vacuno.historia(list(range(1, 948)) + [5000] * 52 + [1000], 999)
    assert h["ficha"] == 94 and not vacuno.en_top(h)


def test_ficha_y_catalogo_truncan_como_el_sitio():
    serie = list(range(1, 1001))
    h = vacuno.historia(serie, 996)                      # 996 de 1000
    assert (h["ficha"], h["catalogo"]) == (99, 99)       # antes, 100 y 100
    h = vacuno.historia(serie, 999)                      # el más alto
    assert (h["ficha"], h["catalogo"]) == (100, 100)
    h = vacuno.historia(serie + [1000], 1000)            # igual al más alto
    assert (h["ficha"], h["catalogo"]) == (99, 100)


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


def test_maximo_mensual_ventana_de_120_meses_y_margen():
    fs = semanas(datetime.date(2014, 1, 6), datetime.date(2026, 9, 28))
    i = len(fs) - 1

    def con(ahora, meses=None):
        """Serie plana en 100, el mes de la última semana en 'ahora' y los
        meses pedidos {(año, mes): precio}."""
        meses = meses or {}
        return [ahora if (f.year, f.month) == (2026, 9) else meses.get((f.year, f.month), 100)
                for f in fs]
    # septiembre de 2016 (120 meses antes) entra y bloquea; agosto de 2016, no
    assert not vacuno.maximo_mensual(fs, con(102, {(2016, 9): 103}), i)["se_afirma"]
    assert vacuno.maximo_mensual(fs, con(102, {(2016, 8): 103}), i)["se_afirma"]
    # exactamente 1% sobre el mes más caro no basta; un poco más, sí
    assert not vacuno.maximo_mensual(fs, con(101), i)["se_afirma"]
    assert vacuno.maximo_mensual(fs, con(101.01), i)["se_afirma"]


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
    assert r["ipc_mes"] == "2026-09"                       # con el IPC de septiembre
    assert (r["A"]["top5"], r["A"]["de"]) == (18, 24)
    assert r["B"]["se_afirman"] == []
    assert (r["C"]["precio"], r["C"]["variacion_anual"]) == (12922, 5.9)
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
        assert precio == vacuno.clp(int(f["precio"])), corte
        assert hist == f"{f['ficha_pct']}% (desde {f['desde'][:4]})", corte
        # truncado, como el sitio: ningún corte está en su máximo
        assert int(f["ficha_pct"]) == int(float(f["pct_mas_barato"])) < 100, corte
        assert sept == f["debajo_mes"], corte
        assert anual == vacuno.pct(float(f["variacion_anual"])), corte
        assert maximo == f"{vacuno.clp(int(f['max_10_anios']))} ({semana:%d-%m-%Y})", corte


def test_informe_dice_las_tres_cifras():
    t = informe()
    assert "**18 de los 24 cortes están en el 5% más caro de su historia**" in t
    assert "**Ninguno está esta semana en su precio real más alto en al menos 10 años**" in t
    assert "$12.922 el kilo, +5,9% sobre la semana del 29 de septiembre de 2025" in t


def test_informe_dice_que_reemplaza_a_la_nota_del_7_de_octubre(guardado):
    # la nota del 7 de octubre (pesos de agosto) daba 20 de 24 y +6,3%; los
    # precios de la semana son los mismos, cambia solo el IPC
    _, _, r = guardado
    t = informe()
    assert "en pesos de septiembre (IPC de 0,4%, publicado hoy por el INE)" in t
    assert (f"Reemplaza a la del 7 de octubre, en pesos de agosto: con los mismos precios, "
            f"los cortes en el 5% más caro bajan de 20 a {r['A']['top5']} "
            f"(salen el ganso y la posta negra) y el asado de tira, de +6,3% a "
            f"{vacuno.pct(r['C']['variacion_anual'])}.") in t
    assert "Ganso" not in r["A"]["cortes"] and "Posta Negra" not in r["A"]["cortes"]
    assert r["C"]["precio"] == 12922                       # el de la nota del 7 de octubre


def _robustez() -> dict:
    with open(resultado("robustez.csv"), encoding="utf-8") as fh:
        return {f["escenario"]: f for f in csv.DictReader(fh)}


def _miles(xs: list) -> str:
    """'20, 11, 22 y 20'."""
    xs = [str(x) for x in xs]
    return ", ".join(xs[:-1]) + " y " + xs[-1]


def test_informe_cita_el_contexto_que_calcula_vacuno(guardado):
    _, _, r = guardado
    t, c = informe(), r["contexto"]
    assert f"en septiembre el conteo fue {_miles([s['top5'] for s in c['top5_por_semana']])}" in t
    assert f"{c['bajaron_esta_semana']} de los 24 bajaron esta semana" in t
    assert c["todos_con_una_semana_mas_cara_este_anio"]
    assert "Todos tuvieron una semana más cara en 2026" in t
    nombres = [n.split(" (")[0].lower() for n in c["a_menos_de_1_de_su_maximo"]]
    assert len(nombres) == 3
    assert ("tres quedan a menos de 1%: "
            + ", ".join(nombres[:-1]) + " y " + nombres[-1]) in t
    justo = c["mismo_mes_entra_mas_justo"]
    assert f" {justo['corte'].lower()} entra por {justo['margen_pct']:.2f}%".replace(".", ",") in t
    assert (f"septiembre sobre septiembre, "
            f"{vacuno.pct(c['asado_de_tira_mes_sobre_mes_del_anio_anterior_pct'])}") in t


def test_informe_cita_lo_que_verificar_calcula_del_asado_de_tira():
    ruta = resultado("asado_de_tira.json")
    if not os.path.exists(ruta):
        pytest.skip("todavía no hay verificación")
    with open(ruta, encoding="utf-8") as fh:
        a = json.load(fh)
    t = informe()
    assert f"({len(a['filas'])} promedios de ODEPA por sector y tipo de local)" in t
    comunes = a["filas_en_las_dos"]
    assert len(comunes) == 4 and all(x.endswith("Carnicería") for x in comunes)
    assert f"Con las mismas 4 carnicerías es {vacuno.pct(a['variacion_anual_en_las_dos_pct'])}" in t
    assert a["semana_del_maximo"][5:7] == "03" and len(a["sobre_todas_las_carnicerias"]) == 2
    assert all("Supermercado" in x for x in a["sobre_todas_las_carnicerias"])
    assert "Su máximo de marzo lo empujaron dos supermercados" in t


def test_informe_cita_la_robustez_de_robustez_csv():
    r, t = _robustez(), informe()
    a = {k: int(f["A_top5"]) for k, f in r.items()}
    bases = a["IPC del INE por bases desde 2019, empalme del INE antes"]
    sin_linea = a["ODEPA sin los supermercados en línea (desde 2020)"]
    assert bases == sin_linea
    assert (f"Con el IPC del INE por bases (el sitio usa el empalme del Banco Central) "
            f"o sin los supermercados en línea (desde 2020) son {bases}; "
            f"con el empalme del INE, {a['empalme del INE desde diciembre de 2009']}.") in t
    # con el IPC de septiembre publicado no quedan escenarios de IPC por venir
    assert not [k for k in r if k.startswith("IPC de septiembre de")]
    assert "IPC de septiembre de" not in t
    # B: ninguno, ni con la regla del 1% ni sin ella, en todos los escenarios
    assert all(f["B_se_afirman"] == "ninguno" for f in r.values())
    assert all(f["B_maximo_sin_margen"] == "ninguno" for f in r.values())
    assert "con otros deflactores y sin la limpieza del sitio" in t
    sitio = r["las series del sitio (empalme BCCh, indices.py)"]["B_con_el_promedio_del_mes"]
    m = re.match(r"Punta de Ganso \(\+([\d,]+)% sobre", sitio)
    assert m and f"la punta de ganso queda {m.group(1)}% sobre su mes más caro" in t


def test_informe_cita_los_porcentajes_al_borde(guardado):
    prods, _, _ = guardado
    t = informe()
    pct = {p["label"]: vacuno.historia(p["v"], vacuno.ultima(p["v"])) for p in prods.values()}
    borde = sorted((h["pct_debajo"], c) for c, h in pct.items() if 95 <= h["pct_debajo"] < 96)
    assert [c for _, c in borde] == ["Asiento", "Palanca", "Plateada", "Lomo Vetado"]
    citados = [f"{c.lower()} ({x:.1f}%)".replace(".", ",") for x, c in borde]
    assert (", ".join(citados[:-1]) + " y " + citados[-1]).capitalize() in t
    # truncado como el sitio: ya no hay 100% de redondeo que aclarar
    assert not [c for c, h in pct.items() if h["ficha"] == 100]
    assert "Redondeo de" not in t


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
    imprimir = cargar_modulo("imprimir")
    with open(ruta, "rb") as fh:
        assert imprimir.paginas(fh.read()) == 1
    # imprimir.py anota de qué informe.md salió el PDF
    with open(resultado("informe_pdf.json"), encoding="utf-8") as fh:
        anotado = json.load(fh)
    assert anotado["informe.md"] == imprimir.sha256(os.path.join(ANALISIS, "informe.md")), \
        "informe.pdf no salió de este informe.md: correr imprimir.py"
    assert anotado["informe.pdf"] == imprimir.sha256(ruta)


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


# ---------- verificar.py, sin red ----------
@pytest.fixture(scope="module")
def verificar():
    return cargar_modulo("verificar")


def test_reescalar_sin_escalon_antes_del_primer_mes(verificar):
    p = serie([100.0] * 10, datetime.date(2009, 10, 5))
    fsitio = {m: 1.0 for m in ("2009-10", "2009-11", "2009-12")}
    nuevo = {"2009-12": 1.1}                 # el otro deflactor parte en diciembre
    v = verificar.reescalar(p, fsitio, nuevo)
    assert v == pytest.approx([110.0] * 10)  # octubre y noviembre, encadenados


def test_alinear_con_t0_distintos(verificar):
    p = serie([1, 2, 3, 4], datetime.date(2020, 1, 13))
    q = {"t0": "2020-01-06", "v": [0, 10, 20, 30]}
    assert verificar.alinear(q, p) == [10, 20, 30, None]


def test_descartes_cuentan_solo_si_dan_vuelta_un_maximo(verificar):
    n = 11 * 52 + 1
    p = serie([100.0] * (n - 1) + [103.0])
    fs = vacuno.fechas(p)
    data = {"descartes": [{"slug": "corte", "semana": fs[-5].isoformat(), "precio": 102.5}]}
    fsitio = {f.strftime("%Y-%m"): 1.0 for f in fs}
    verificar.FILAS.clear()
    verificar.probar_descartes(data, {"corte": p}, fsitio)
    fila = verificar.FILAS[-1]
    assert fila["ok"] == 0                   # 102,5 queda a menos de 1% de 103
    verificar.FILAS.clear()
    data["descartes"][0]["precio"] = 101.0
    verificar.probar_descartes(data, {"corte": p}, fsitio)
    assert verificar.FILAS[-1]["ok"] == 1
    verificar.FILAS.clear()
    p = serie([100.0] * n)                   # sin máximo: la fila es informativa
    verificar.probar_descartes(data, {"corte": p}, fsitio)
    assert verificar.FILAS[-1]["ok"] == ""
    verificar.FILAS.clear()


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
    graficar = cargar_modulo("graficar")
    _, series, _ = guardado
    salida = graficar.graficar(series, str(tmp_path / "g.png"))
    from PIL import Image
    with Image.open(salida) as im:
        assert im.size == (1080, 1080)
    assert graficar.TEXTOS and [s for s in graficar.TEXTOS if infracciones(s)] == []
    assert "Punto: semana del 28 de septiembre de 2026." in " ".join(graficar.TEXTOS)

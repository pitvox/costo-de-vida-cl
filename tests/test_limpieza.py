"""Tests sintéticos de indices.limpiar_semanal (limpieza de las series de
producto). Sin red: solo series armadas a mano."""
import ast
import os
import sys

import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402


def semanal(valores, inicio="2026-01-05"):
    """Serie W-MON con NaN en los None, como la deja resample().mean()."""
    idx = pd.date_range(inicio, periods=len(valores), freq="W-MON")
    return pd.Series([np.nan if v is None else float(v) for v in valores], index=idx)


def test_valor_aislado_a_un_centesimo_se_descarta():
    vals = [3000, 3050, 2980, 3020, 3010, 2990, 3040, 3000, 30, 3010, 3000]
    s = semanal(vals)
    limpia, desc, _anual = indices.limpiar_semanal(s)
    assert len(desc) == 1
    semana, precio, mediana = desc[0]
    assert semana == s.index[8] and precio == 30 and mediana == 3005
    assert np.isnan(limpia.iloc[8])
    # el resto queda intacto
    assert limpia.drop(s.index[8]).equals(s.drop(s.index[8]))
    # y el pipeline de emitir() completa esa semana con el ffill
    assert limpia.ffill(limit=4).iloc[8] == 3000


def test_cambio_de_nivel_persistente_x10_se_acepta_en_max_5_semanas():
    """La regla es ±5x: un cambio de nivel tiene que salir de esa banda para
    que se descarte algo. Con x10 (ODEPA pasa de un envase a otro) se
    descartan las primeras semanas y desde la quinta el nivel nuevo ya pesa
    en la mediana de los crudos y se acepta."""
    vals = [1000] * 10 + [10000] * 10
    s = semanal(vals)
    limpia, desc, _anual = indices.limpiar_semanal(s)
    descartadas = [f for f, _p, _m in desc]
    assert descartadas == list(s.index[10:14])       # 4 semanas
    assert limpia.iloc[14:].notna().all()             # la 5ª ya entra
    assert (limpia.iloc[14:] == 10000).all()


def test_cambio_de_nivel_x4_esta_dentro_de_la_banda_y_no_se_descarta():
    s = semanal([1000] * 10 + [4000] * 10)
    limpia, desc, _anual = indices.limpiar_semanal(s)
    assert desc == [] and limpia.equals(s)


def test_regreso_de_temporada_a_su_nivel_no_se_descarta():
    # 20 semanas de temporada a $1.000, 30 semanas sin dato, regresa a $1.300:
    # la ventana de 8 semanas está vacía y la mediana de sus últimas 52
    # semanas con dato ($1.000) lo deja dentro de la banda
    vals = [1000] * 20 + [None] * 30 + [1300, 1350, 1250, 1300]
    s = semanal(vals)
    limpia, desc, anual = indices.limpiar_semanal(s)
    assert desc == [] and anual == []
    assert limpia.equals(s)


def test_regreso_de_temporada_a_9_veces_se_descarta_hasta_llenar_la_ventana():
    """Con la ventana de 8 semanas escasa juzga la mediana de las últimas 52
    semanas con dato: un regreso a 9 veces su nivel se descarta mientras la
    ventana tenga menos de 3 valores; con 3, manda la ventana y el nivel nuevo
    se acepta, como un cambio de nivel persistente."""
    vals = [1000] * 20 + [None] * 30 + [9000, 9100, 200, 9000]
    s = semanal(vals)
    limpia, desc, anual = indices.limpiar_semanal(s)
    assert desc == []
    assert [(f, p, m) for f, p, m in anual] == [(s.index[50], 9000, 1000),
                                               (s.index[51], 9100, 1000)]
    # $200 es justo un quinto de $1.000: queda; la última ya la juzga la ventana
    assert np.isnan(limpia.iloc[50]) and np.isnan(limpia.iloc[51])
    assert limpia.iloc[52] == 200 and limpia.iloc[53] == 9000


def test_con_menos_de_3_semanas_con_dato_no_se_juzga():
    # 2 valores previos en total: ni la ventana de 8 ni la de 52 juzgan
    s2 = semanal([1000, 1000, None, None, None, None, None, None, 100000])
    limpia, desc, anual = indices.limpiar_semanal(s2)
    assert desc == [] and anual == [] and limpia.equals(s2)


def test_poroto_manteca_a_3_pesos_con_huecos_se_descarta():
    """El caso que motivó el segundo control: pocas semanas con dato y muy
    separadas, así que la ventana de 8 semanas no tiene con qué comparar."""
    vals = [3100] + [None] * 10 + [3000] + [None] * 20 + [3200] + [None] * 5 \
        + [3100] + [None] * 10 + [3]
    s = semanal(vals)
    limpia, desc, anual = indices.limpiar_semanal(s)
    assert desc == []
    assert anual == [(s.index[-1], 3.0, 3100.0)]
    assert np.isnan(limpia.iloc[-1])
    assert limpia.dropna().tolist() == [3100, 3000, 3200, 3100]


def test_la_mediana_anual_usa_las_ultimas_52_semanas_con_dato():
    # 60 semanas a $1.000, 52 a $10.000 (cambio de nivel ya aceptado), 10
    # sin dato y regresa a $9.500: la mediana de las últimas 52 con dato es
    # $10.000 y no la de toda la historia
    vals = [1000] * 60 + [10000] * 52 + [None] * 10 + [9500]
    s = semanal(vals)
    _limpia, _desc, anual = indices.limpiar_semanal(s)
    assert anual == []


def test_con_ventana_de_8_suficiente_no_juzga_la_anual():
    # serie densa: manda la ventana de 8 semanas aunque la anual diría otra cosa
    vals = [1000] * 60 + [6000] * 8 + [6000]
    s = semanal(vals)
    _limpia, _desc, anual = indices.limpiar_semanal(s)
    assert anual == []


def test_pocos_puntos_descarta_las_semanas_con_menos_de_3():
    s = semanal([1000, 1010, 990, 1000, None])
    pts = pd.Series([5, 3, 2, 1, 0], index=s.index, dtype=float)
    malo, fuera = indices.pocos_puntos(s, pts)
    assert malo.tolist() == [False, False, True, True, False]
    assert fuera == [(s.index[2], 990.0, 2), (s.index[3], 1000.0, 1)]
    # sin conteo (formato sin sector ni tipo de punto) no se aplica
    malo, fuera = indices.pocos_puntos(s, None)
    assert not malo.any() and fuera == []


def test_volatilidad_normal_60pct_no_se_descarta():
    rng = np.random.default_rng(0)
    vals = 2000 * (1 + rng.uniform(-0.6, 0.6, size=300))
    vals[::7] = 2000 * 1.6
    vals[3::11] = 2000 * 0.4
    s = semanal(list(vals))
    limpia, desc, _anual = indices.limpiar_semanal(s)
    assert desc == []
    assert limpia.equals(s)


def test_series_productos_registra_descartes_nominales():
    fechas = pd.date_range("2026-01-05", periods=12, freq="W-MON")
    precios = [3000.0] * 12
    precios[9] = 3.0                                  # el "poroto a $3"
    df = pd.DataFrame({"ProductoBase": "Poroto manteca", "Precio promedio": precios,
                       "Unidad": "$/kilo", "Grupo": "Legumbres", "fecha": fechas})
    ipc = pd.Series([100.0, 110.0], index=pd.to_datetime(["2025-12-01", "2026-03-01"]))
    descartes = []
    out = indices.series_productos(df, ipc, descartes)
    assert descartes == [{"slug": "poroto_manteca", "semana": "2026-03-09",
                          "precio": 3.0, "mediana": 3000.0}]
    v = out["poroto_manteca"]["v"]
    assert None not in v and min(v) >= 3000          # la semana quedó con el ffill
    # sin la lista, la firma de siempre (informe.py) sigue funcionando
    assert indices.series_productos(df, ipc) == out


def test_series_productos_emite_la_mecha_alineada_con_v():
    """min y max (la mecha de las velas): promedio semanal del mínimo y del
    máximo de ODEPA, deflactados igual que v, alineados con v. Sin rango en
    la semana descartada ni en las que completa el ffill."""
    fechas = list(pd.date_range("2026-01-05", periods=12, freq="W-MON"))
    precios = [3000.0] * 12
    precios[9] = 3.0                                  # semana descartada
    fechas[5] = fechas[4]                             # semana 5 sin dato: ffill
    df = pd.DataFrame({"ProductoBase": "Poroto manteca", "Precio promedio": precios,
                       "Precio minimo": [p * 0.8 for p in precios],
                       "Precio maximo": [p * 1.5 for p in precios],
                       "Unidad": "$/kilo", "Grupo": "Legumbres", "fecha": fechas})
    ipc = pd.Series([100.0, 110.0], index=pd.to_datetime(["2025-12-01", "2026-03-01"]))
    p = indices.series_productos(df, ipc)["poroto_manteca"]
    assert len(p["min"]) == len(p["max"]) == len(p["v"]) == 12
    # semanas con dato: rango deflactado como v (enero y febrero x 1,1)
    assert (p["min"][0], p["v"][0], p["max"][0]) == (2640, 3300, 4950)
    assert (p["min"][10], p["v"][10], p["max"][10]) == (2400, 3000, 4500)
    # semana sin dato (ffill) y semana descartada: v completado, sin rango
    for i in (5, 9):
        assert p["v"][i] is not None and p["min"][i] is None and p["max"][i] is None
    # nunca una mecha que no contenga el promedio
    for lo, v, hi in zip(p["min"], p["v"], p["max"]):
        assert lo is None or lo <= v <= hi


def _filas_por_punto(producto, semanas, puntos, precio=3000.0):
    """Filas ODEPA de un producto: en la semana i, una fila por cada uno de
    sus puntos[i] puntos de monitoreo (sector y tipo de punto)."""
    filas = []
    for f, n in zip(semanas, puntos):
        for k in range(n):
            filas.append({"ProductoBase": producto, "Precio promedio": precio,
                          "Unidad": "$/kilo", "Grupo": "Legumbres", "fecha": f,
                          "Punto": f"Sector {k} | Feria libre"})
    return filas


def test_series_productos_aplica_el_minimo_de_puntos():
    semanas = pd.date_range("2026-01-05", periods=12, freq="W-MON")
    filas = _filas_por_punto("Lenteja", semanas, [4, 4, 4, 4, 4, 2, 4, 4, 4, 4, 4, 1])
    # un producto encuestado solo en 2 puntos (mayoristas) todas las semanas
    filas += _filas_por_punto("Poroto coscorrón", semanas, [2] * 12)
    # y una fila repetida en el mismo punto no cuenta como otro punto
    filas += _filas_por_punto("Lenteja", semanas[3:4], [1])
    df = pd.DataFrame(filas)
    ipc = pd.Series([100.0], index=pd.to_datetime(["2025-12-01"]))
    descartes, anuales, puntos = [], [], []
    out = indices.series_productos(df, ipc, descartes, anuales, puntos)
    assert descartes == [] and anuales == []
    lenteja = [d for d in puntos if d["slug"] == "lenteja"]
    assert lenteja == [{"slug": "lenteja", "semana": "2026-02-09", "precio": 3000.0, "puntos": 2},
                       {"slug": "lenteja", "semana": "2026-03-23", "precio": 3000.0, "puntos": 1}]
    # las semanas descartadas se completan con el ffill, sin rango
    p = out["lenteja"]
    assert len(p["v"]) == 12 and None not in p["v"]
    assert p["min"][5] is None and p["min"][11] is None and p["min"][4] == 3000
    # sin ninguna semana publicable, el producto no entra, pero se informa
    assert "poroto_coscorron" not in out
    assert len([d for d in puntos if d["slug"] == "poroto_coscorron"]) == 12


def test_series_productos_sin_punto_no_aplica_el_minimo():
    semanas = pd.date_range("2026-01-05", periods=6, freq="W-MON")
    df = pd.DataFrame(_filas_por_punto("Lenteja", semanas, [1] * 6))
    df["Punto"] = ""
    ipc = pd.Series([100.0], index=pd.to_datetime(["2025-12-01"]))
    puntos = []
    out = indices.series_productos(df, ipc, puntos=puntos)
    assert puntos == [] and len(out["lenteja"]["v"]) == 6


def _llamadas(fn_nombre):
    src = open(os.path.join(RAIZ, "indices.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == fn_nombre)
    return {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(fn) if isinstance(n, ast.Call)}


def test_los_indices_no_pasan_por_la_limpieza():
    for fn in ("calcular", "_serie_canasta", "precio_semanal", "resumen", "main"):
        assert "limpiar_semanal" not in _llamadas(fn), fn
    assert "limpiar_semanal" in _llamadas("series_productos")
    for fn in ("calcular", "_serie_canasta", "precio_semanal", "resumen"):
        assert "pocos_puntos" not in _llamadas(fn), fn
    assert "pocos_puntos" in _llamadas("series_productos")

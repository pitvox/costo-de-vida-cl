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
    limpia, desc = indices.limpiar_semanal(s)
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
    limpia, desc = indices.limpiar_semanal(s)
    descartadas = [f for f, _p, _m in desc]
    assert descartadas == list(s.index[10:14])       # 4 semanas
    assert limpia.iloc[14:].notna().all()             # la 5ª ya entra
    assert (limpia.iloc[14:] == 10000).all()


def test_cambio_de_nivel_x4_esta_dentro_de_la_banda_y_no_se_descarta():
    s = semanal([1000] * 10 + [4000] * 10)
    limpia, desc = indices.limpiar_semanal(s)
    assert desc == [] and limpia.equals(s)


def test_regreso_de_temporada_con_ventana_escasa_no_se_juzga():
    # 20 semanas de temporada a $1.000, 30 semanas sin dato, regresa a $9.000:
    # la ventana de 8 semanas anteriores tiene 0 valores -> no se juzga
    vals = [1000] * 20 + [None] * 30 + [9000, 9100, 200, 9000]
    s = semanal(vals)
    limpia, desc = indices.limpiar_semanal(s)
    assert desc == []
    assert limpia.equals(s)
    # con solo 2 valores previos en la ventana tampoco se juzga
    s2 = semanal([1000, 1000, None, None, None, None, None, None, 100000])
    assert indices.limpiar_semanal(s2)[1] == []


def test_volatilidad_normal_60pct_no_se_descarta():
    rng = np.random.default_rng(0)
    vals = 2000 * (1 + rng.uniform(-0.6, 0.6, size=300))
    vals[::7] = 2000 * 1.6
    vals[3::11] = 2000 * 0.4
    s = semanal(list(vals))
    limpia, desc = indices.limpiar_semanal(s)
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

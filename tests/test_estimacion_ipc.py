"""Pruebas sin red del análisis de analisis/estimacion_ipc/ (prueba hacia atrás
del IPC de alimentos). No tocan el sitio: revisan que la estimación no use
información posterior a la publicación del IPC, las cuentas del relativo de
precios y los reemplazos, y que informe.md respete las reglas de texto."""
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALISIS = os.path.join(RAIZ, "analisis", "estimacion_ipc")
sys.path.insert(0, ANALISIS)
import estimar  # noqa: E402
import odepa_mensual  # noqa: E402


def semanal(filas):
    """odepa_semanal sintético: (clave, unidad, lunes, precio)."""
    return pd.DataFrame([{"clave": c, "serie": f"{c} | {u}", "producto": c, "unidad": u,
                          "base": "kg", "contenido": 1.0, "semana": pd.Timestamp(s),
                          "precio": p, "puntos": 5} for c, u, s, p in filas])


def test_corte_deja_fuera_lo_publicado_desde_el_dia_del_ipc():
    # IPC de marzo publicado el 8 de abril: la semana del lunes 30 de marzo
    # sale el viernes 3 de abril y entra; con 11 días de atraso ya no entra.
    s = semanal([("papa", "$/kilo", "2026-03-02", 100.0),
                 ("papa", "$/kilo", "2026-03-30", 200.0)])
    corte = {pd.Period("2026-03", "M"): pd.Timestamp("2026-04-08")}
    con = odepa_mensual.precios_mensuales(s, corte)
    assert con["precio"].iloc[0] == 150.0 and con["semanas"].iloc[0] == 2
    sin = odepa_mensual.precios_mensuales(s, corte, atraso=11)
    assert sin["precio"].iloc[0] == 100.0 and sin["semanas"].iloc[0] == 1
    # publicada el mismo día del IPC: no entra (el IPC sale a las 8:00)
    corte_justo = {pd.Period("2026-03", "M"): pd.Timestamp("2026-04-03")}
    assert odepa_mensual.precios_mensuales(s, corte_justo)["semanas"].iloc[0] == 1


def test_jevons_en_dos_niveles():
    # producto a con dos unidades (sube 10% y 21%), producto b sube 0%:
    # a = raíz(1,1 x 1,21) = 1,1533; el producto del IPC = raíz(1,1533 x 1)
    meses = pd.PeriodIndex(["2026-01", "2026-02"], freq="M")
    precios = pd.DataFrame({"a | kilo": [100, 110], "a | unidad": [100, 121],
                            "b | kilo": [50, 50], "c | kilo": [10, np.nan]}, index=meses)
    series = {"a": ["a | kilo", "a | unidad"], "b": ["b | kilo"], "c": ["c | kilo"]}
    r, n = estimar.jevons(precios, precios, series, ["a", "b", "c"], meses[1])
    assert n == 2  # c no tiene precio en febrero
    assert r == pytest.approx(np.sqrt(np.sqrt(1.1 * 1.21)))


def test_jevons_toma_p_anterior_y_p_actual_de_tablas_distintas():
    meses = pd.PeriodIndex(["2026-01", "2026-02"], freq="M")
    anterior = pd.DataFrame({"a | kilo": [100.0, 130.0]}, index=meses)
    actual = pd.DataFrame({"a | kilo": [90.0, 120.0]}, index=meses)
    r, _ = estimar.jevons(anterior, actual, {"a": ["a | kilo"]}, ["a"], meses[1])
    assert r == pytest.approx(1.2)


def test_reemplazos_con_la_historia_oficial():
    idx = pd.period_range("2025-01", "2026-03", freq="M")
    serie = pd.Series(100 * 1.01 ** np.arange(len(idx)), index=idx)
    m = pd.Period("2026-03", "M")
    assert estimar.relativo_propio(serie, m, "mes_anterior") == pytest.approx(1.01)
    assert estimar.relativo_propio(serie, m, "12_meses") == pytest.approx(1.01)
    var = pd.Series(1.0, index=idx)
    assert estimar.relativo_agregado(var, m, "mes_anterior") == pytest.approx(1.01)
    assert estimar.relativo_agregado(var, m, "12_meses") == pytest.approx(1.01)


def test_contenido_reconoce_mililitros():
    assert odepa_mensual.contenido("$/botella 900 ml") == ("l", 0.9)
    assert odepa_mensual.contenido("$/bolsa 800 grs") == ("kg", 0.8)
    assert odepa_mensual.contenido("$/kilo (en saco de 25 kilos)") is None


def test_metricas_redondean_y_cuentan_la_direccion():
    r = pd.DataFrame({"mes": pd.PeriodIndex(["2026-01", "2026-02", "2026-03"], freq="M"),
                      "estimada": [0.04, -0.26, 0.5], "oficial": [0.0, -0.3, 0.4],
                      "ingenuo": [0.2, 0.0, -0.3], "promedio_12m": [0.3, 0.3, 0.3]})
    t = estimar.metricas(r).loc["total"]
    # estimada redondeada: 0,0 / -0,3 / 0,5 -> errores 0 / 0 / 0,1
    assert t["eam_estimacion"] == pytest.approx(0.1 / 3)
    assert t["acierto_dir_estimacion"] == pytest.approx(100)
    assert t["acierto_dir_ingenuo"] == pytest.approx(0)


def test_calendario_cubre_todos_los_meses_de_la_prueba():
    cal = pd.read_csv(os.path.join(ANALISIS, "calendario_ipc.csv"))
    meses = set(cal["mes_referencia"])
    assert {str(m) for m in pd.period_range("2018-12", "2026-08", freq="M")} <= meses
    fechas = pd.to_datetime(cal["fecha_publicacion"])
    ref = pd.PeriodIndex(cal["mes_referencia"], freq="M")
    assert (fechas.dt.to_period("M") == ref + 1).all()  # sale el mes siguiente


def test_informe_sin_rayas_ni_muletillas():
    ruta = os.path.join(ANALISIS, "informe.md")
    if not os.path.exists(ruta):
        pytest.skip("todavía no hay informe")
    texto = open(ruta, encoding="utf-8").read()
    for patron in ("—", "–", r"\bvs\b", "inédit", "al descuento", "sin precedentes"):
        assert not re.search(patron, texto, re.I), patron


def test_redondeo_mitad_hacia_arriba_sin_ruido_de_coma_flotante():
    assert list(estimar.redondear([1.3499999999999999, 0.25, -0.25, 0.04])) == [1.4, 0.3, -0.3, 0.0]


def test_t_de_student_dos_colas():
    assert estimar.p_t_dos_colas(2.0, 10) == pytest.approx(0.07339, abs=1e-5)
    assert estimar.p_t_dos_colas(1.96, 10 ** 6) == pytest.approx(0.05, abs=1e-4)


def test_criterio_acepta_exactamente_dos_de_cada_tres():
    meses = pd.period_range("2025-01", periods=12, freq="M")
    oficial = [0.5] * 12
    estimada = [0.5] * 8 + [-0.5] * 4   # 8 de 12 aciertos
    r = pd.DataFrame({"mes": meses, "estimada": estimada, "oficial": oficial,
                      "ingenuo": [0.0] * 12, "promedio_12m": [0.5] * 12})
    assert "2 de cada 3 meses: sí (8 de 12)" in estimar.criterio(r)


def test_ar1_alrededor_del_promedio_de_12_meses():
    idx = pd.period_range("2025-01", "2026-02", freq="M")
    x = np.log1p(np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 0], dtype=float) / 100)
    serie = pd.Series(100 * np.exp(np.cumsum(x)), index=idx)
    m = pd.Period("2026-03", "M")
    previos = x[-12:]
    mu = previos.mean()
    esperado = np.exp(mu + 0.5 * (x[-1] - mu))
    assert estimar.relativo_propio(serie, m, "ar1", phi=0.5) == pytest.approx(esperado)
    # phi = 0 es el promedio de 12 meses (geométrico)
    assert estimar.relativo_propio(serie, m, "ar1", phi=0.0) == pytest.approx(
        estimar.relativo_propio(serie, m, "12_meses"))


def test_peso_de_la_combinacion_solo_con_desarrollo_y_recortado():
    import evaluar
    meses = pd.period_range("2019-01", "2024-12", freq="M")
    n = len(meses)
    rng = np.random.default_rng(0)
    p12 = np.full(n, 0.5)
    est = p12 + rng.normal(0, 1, n)
    oficial = p12 + 0.3 * (est - p12)
    # en la prueba la relación es otra: no debe influir en w
    oficial[meses >= pd.Period("2024-01", "M")] = 9.0
    v0 = pd.DataFrame({"mes": meses, "estimada": est, "oficial": oficial, "promedio_12m": p12})
    assert evaluar.peso_combinacion(v0) == pytest.approx(0.3)
    assert evaluar.peso_combinacion(v0.assign(oficial=p12 - 2 * (est - p12))) == 0.0


def test_regla_usa_el_mejor_comparador_y_siempre_sube():
    import evaluar
    meses = pd.period_range("2024-01", periods=12, freq="M")
    oficial = np.array([0.5, 0.3, -0.2, 0.8, 0.1, 0.4, 0.6, -0.1, 0.2, 0.9, 0.3, 0.5])
    r = pd.DataFrame({"mes": meses, "oficial": oficial, "estimada": oficial,
                      "ingenuo": np.roll(oficial, 1), "promedio_12m": np.full(12, 0.3)})
    res = evaluar.regla(r)
    assert res["mejor_comparador"] == "promedio_12m"
    assert res["eam_estimacion"] == 0 and res["gana_error"] and res["pasa"]
    assert res["aciertos_siempre_sube"] == 10 and res["aciertos_dir"] == 12
    # misma precisión que "siempre sube" en dirección: no pasa
    r2 = r.assign(estimada=np.where(oficial > 0, oficial, 0.3))
    assert not evaluar.regla(r2)["gana_direccion"]

"""Tests sintéticos de validar.py. No tocan la red: requests.get está
reemplazado por un fake en todos los tests (y un get no mockeado revienta)."""
import ast
import copy
import datetime
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import validar  # noqa: E402

SEMANA_ANT = "2026-09-14"
SEMANA_NUEVA = "2026-09-21"
N_ANT = {"asado": 800, "ensalada": 900, "fruta": 700, "desayuno": 600}
COSTO = {"asado": 52000, "ensalada": 8000, "fruta": 12000, "desayuno": 15000}


def _semanas(fin: str, n: int) -> list:
    f = datetime.date.fromisoformat(fin)
    return [(f - datetime.timedelta(weeks=n - 1 - i)).isoformat() for i in range(n)]


def indices_nuevo(n_extra=1, productos=120):
    """indices.json sintético con la forma que escribe indices.py."""
    out = {"generado": "2026-09-26", "indices": {}, "productos": {}}
    for code in validar.INDICES:
        n = N_ANT[code] + n_extra
        costo = COSTO[code]
        fechas = _semanas(SEMANA_NUEVA, n)
        real = [{"time": t, "value": costo} for t in fechas]
        real[-2]["value"] = round(costo / 1.02)      # +2% semanal
        comp = [{"label": f"{code}_{i}", "qty": 1, "unidad": "kg",
                 "odepa_unit": "$/kg", "factor": 1.0, "mismatch": False,
                 "precio_ult": costo // 4, "aporte": costo // 4} for i in range(4)]
        out["indices"][code] = {
            "nombre": f"Índice {code.title()}", "subtitulo": "x",
            "fecha": "21-09-2026", "costo_nominal": costo, "costo_real": costo,
            "percentil": 50, "zscore": 0.1, "vs_promedio": 2, "veredicto": "NORMAL",
            "color": "#e0a83c", "n": n, "componentes": comp,
            "estacionalidad": {}, "velas": [], "nominal": real, "real": real,
        }
    for i in range(productos):
        out["productos"][f"prod_{i:03d}"] = {"label": f"P{i}", "unidad": "kg",
                                            "grupo": "Otros", "t0": SEMANA_NUEVA,
                                            "v": [1000]}
    return out


def resumen_desplegado():
    return {
        "generado": "2026-09-19", "semana": SEMANA_ANT, "fuente": "Carestía",
        "indices": {code: {"nombre": f"Índice {code.title()}", "subtitulo": "x",
                           "costo_pesos_hoy": COSTO[code], "veredicto": "NORMAL",
                           "percentil": 50, "vs_promedio_pct": 2,
                           "variacion_semanal_pct": 1.0,
                           "semanas_historia": N_ANT[code]}
                    for code in validar.INDICES},
    }


class Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Directorio de trabajo aislado + red falsa. Devuelve un dict mutable:
    'indices' (lo que escribió indices.py), 'resumen' / 'indices_remoto'
    (lo desplegado; None = inalcanzable)."""
    monkeypatch.chdir(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("PRODUCTOS_ESPERADOS", raising=False)
    estado = {"indices": indices_nuevo(), "resumen": resumen_desplegado(),
              "indices_remoto": indices_nuevo(productos=120), "urls": []}

    def fake_get(url, **_kw):
        estado["urls"].append(url)
        payload = estado["resumen"] if url.endswith("resumen.json") \
            else estado["indices_remoto"]
        if payload is None:
            raise validar.requests.ConnectionError("sin red (test)")
        return Resp(payload)

    monkeypatch.setattr(validar.requests, "get", fake_get)

    def correr():
        (tmp_path / "indices.json").write_text(
            json.dumps(estado["indices"], ensure_ascii=False), encoding="utf-8")
        code = validar.main()
        return code, summary.read_text(encoding="utf-8")

    estado["correr"] = correr
    return estado


def test_conteo_mas_uno_y_variacion_chica_pasa(entorno, capsys):
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert "PASA" in summary and validar.KO not in summary
    out = capsys.readouterr().out
    assert "OK asado: $52.000 | p50 | NORMAL | 800→801" in out
    assert out.count("OK ") == 4
    # la tabla trae los 4 índices
    for c in validar.INDICES:
        assert f"| {c} |" in summary


def test_conteo_mas_cinco_en_una_semana_falla(entorno):
    entorno["indices"] = indices_nuevo(n_extra=5)
    code, summary = entorno["correr"]()
    assert code == 1
    assert "FALLA" in summary and "800→805" in summary


def test_misma_semana_con_conteo_igual_pasa_y_distinto_falla(entorno):
    entorno["indices"] = indices_nuevo(n_extra=0)
    entorno["resumen"]["semana"] = SEMANA_NUEVA
    assert entorno["correr"]()[0] == 0
    entorno["indices"] = indices_nuevo(n_extra=1)
    assert entorno["correr"]()[0] == 1


def test_variacion_semanal_60_falla(entorno):
    real = entorno["indices"]["indices"]["fruta"]["real"]
    real[-2]["value"] = round(real[-1]["value"] / 1.6)   # +60%
    code, summary = entorno["correr"]()
    assert code == 1
    assert "fruta: variación semanal" in summary and "60.0%" in summary


def test_componentes_suman_3pct_menos_falla(entorno):
    d = entorno["indices"]["indices"]["asado"]
    d["costo_nominal"] = round(sum(c["aporte"] for c in d["componentes"]) / 0.97)
    code, summary = entorno["correr"]()
    assert code == 1
    assert "asado: Σ aportes = costo_nominal" in summary


def test_mismatch_de_unidad_falla(entorno):
    entorno["indices"]["indices"]["desayuno"]["componentes"][0]["mismatch"] = True
    assert entorno["correr"]()[0] == 1


def test_119_productos_falla_y_lista_slugs(entorno):
    entorno["indices"] = indices_nuevo(productos=119)
    code, summary = entorno["correr"]()
    assert code == 1
    assert "119 series, esperadas 120" in summary
    assert "desaparecieron [prod_119]" in summary


def test_productos_esperados_por_env(entorno, monkeypatch):
    monkeypatch.setenv("PRODUCTOS_ESPERADOS", "119")
    entorno["indices"] = indices_nuevo(productos=119)
    assert entorno["correr"]()[0] == 0


def test_snapshot_inalcanzable_falla(entorno):
    entorno["resumen"] = None
    code, summary = entorno["correr"]()
    assert code == 1
    assert "no pude leer el snapshot anterior; no valido contra nada" in summary
    # intentó ambos orígenes, en orden
    assert entorno["urls"] == list(validar.URLS_RESUMEN)


def test_respaldo_github_io_si_carestia_falla(entorno, monkeypatch):
    llamadas = []

    def get(url, **_kw):
        llamadas.append(url)
        if "carestia.cl" in url:
            raise validar.requests.ConnectionError("caído")
        return Resp(resumen_desplegado())

    monkeypatch.setattr(validar.requests, "get", get)
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert validar.URLS_RESUMEN[1] in summary


def test_resumen_igual_al_de_build_site():
    """validar.resumen_desde_indices debe calcular lo mismo que
    build_site.generar_resumen (que es quien escribe resumen.json)."""
    src = open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "generar_resumen")
    data = indices_nuevo()
    data["indices"]["fruta"]["real"] = data["indices"]["fruta"]["real"][:-1]
    escrito = {}

    class FakeFile:
        def __init__(self):
            self.buf = []

        def write(self, s):
            self.buf.append(s)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            escrito["json"] = json.loads("".join(self.buf))

    g = {"DATA": copy.deepcopy(data), "datetime": datetime, "json": json,
         "open": lambda *a, **k: FakeFile()}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "build_site.py", "exec"), g)
    g["generar_resumen"]()
    esperado = escrito["json"]
    propio = validar.resumen_desde_indices(data)
    assert propio["semana"] == esperado["semana"]
    assert propio["indices"] == esperado["indices"]


# ---------------- Limpieza de productos (clave "descartes") ----------------
def _descartes(n, semana=SEMANA_NUEVA, slug="prod_000"):
    return [{"slug": slug, "semana": semana, "precio": 3.0, "mediana": 3000.0}] * n


def test_sin_clave_descartes_pasa(entorno):
    assert "descartes" not in entorno["indices"]
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert "## Limpieza de productos" in summary
    assert "no trae la clave `descartes`" in summary


def test_pocos_descartes_no_fallan_y_se_informan(entorno):
    # 120 productos x 200 semanas = 24.000 semanas-producto con dato
    for p in entorno["indices"]["productos"].values():
        p["t0"] = _semanas(SEMANA_NUEVA, 200)[0]
        p["v"] = [1000] * 200
    entorno["indices"]["descartes"] = (
        [{"slug": "poroto_manteca", "semana": "2026-06-29", "precio": 3.0,
          "mediana": 2950.0}]
        + _descartes(1, slug="prod_001")
        + [d for k in range(3) for d in _descartes(
            1, (datetime.date.fromisoformat(SEMANA_NUEVA)
                - datetime.timedelta(weeks=k)).isoformat(), "prod_002")])
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert "5 semanas descartadas" in summary and "de 24000 semanas-producto" in summary
    assert f"Última semana ({SEMANA_NUEVA}):** 2 descarte(s)" in summary
    assert "posible cambio de unidad o de producto en ODEPA: revisar" in summary
    assert "- prod_002" in summary and "- prod_001" not in summary
    assert "| poroto_manteca | 2026-06-29 | 3.0 | 2950.0 |" in summary


def test_descartes_sobre_el_medio_por_ciento_fallan(entorno):
    for p in entorno["indices"]["productos"].values():
        p["t0"] = _semanas(SEMANA_NUEVA, 200)[0]
        p["v"] = [1000] * 200
    entorno["indices"]["descartes"] = _descartes(121)     # 121/24.000 = 0,504%
    code, summary = entorno["correr"]()
    assert code == 1
    assert "limpieza de productos: descartes ≤ 0,5%" in summary
    assert "borrando de más" in summary
    entorno["indices"]["descartes"] = _descartes(120)     # justo 0,5%: pasa
    assert entorno["correr"]()[0] == 0


# ---------------- Controles nuevos: mediana anual y puntos de venta ----------------
def _con_200_semanas(entorno):
    for p in entorno["indices"]["productos"].values():
        p["t0"] = _semanas(SEMANA_NUEVA, 200)[0]
        p["v"] = [1000] * 200


def test_controles_nuevos_se_informan_y_nunca_fallan(entorno):
    _con_200_semanas(entorno)
    entorno["indices"]["descartes"] = []
    entorno["indices"]["descartes_anuales"] = [
        {"slug": "poroto_manteca", "semana": "2026-06-29", "precio": 3.0, "mediana": 2225.0}]
    # muchos más que el 0,5% de las semanas-producto: igual no falla
    entorno["indices"]["descartes_puntos"] = (
        [{"slug": "prod_001", "semana": SEMANA_NUEVA, "precio": 900.0, "puntos": 2}]
        + [{"slug": "poroto_coscorron", "semana": s, "precio": 2500.0, "puntos": 2}
           for s in _semanas(SEMANA_NUEVA, 600)])
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert "### Mediana de las últimas 52 semanas con dato" in summary
    assert "| poroto_manteca | 2026-06-29 | 3.0 | 2225.0 |" in summary
    assert "### Menos de 3 puntos de venta" in summary
    assert "**601 semanas descartadas**" in summary
    assert "Solo se informa: no hace fallar el build." in summary
    assert f"Última semana ({SEMANA_NUEVA}):** 2 descarte(s)" in summary
    assert "| prod_001 | " + SEMANA_NUEVA + " | 900.0 | 2 |" in summary
    # los que se quedan sin ninguna semana se nombran
    assert "**Sin ninguna semana publicable** (no están en el catálogo):" in summary
    assert "- poroto_coscorron" in summary and "- poroto_manteca" in summary
    assert "- prod_001" not in summary
    assert "| poroto_coscorron | 600 |" in summary


def test_sin_claves_de_los_controles_nuevos_lo_dice(entorno):
    entorno["indices"]["descartes"] = []
    code, summary = entorno["correr"]()
    assert code == 0, summary
    assert "no trae la clave `descartes_anuales`" in summary
    assert "no trae la clave `descartes_puntos`" in summary

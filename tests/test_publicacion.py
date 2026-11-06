"""Tests de publicacion.py, sin red: la referencia publicada es un dict y la
descarga, un get falso. Usa el indices.json sintético de test_validar."""
import ast
import datetime
import json
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import publicacion  # noqa: E402
import validar  # noqa: E402
from test_validar import N_ANT, SEMANA_NUEVA, indices_nuevo, resumen_desplegado  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=-3))
LUNES = datetime.date(2026, 11, 2)      # la semana que ODEPA publica el viernes 6


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Una descarga no reemplazada revienta en vez de salir a la red."""
    def urlopen(*a, **k):
        raise AssertionError("test con red")
    monkeypatch.setattr(publicacion.urllib.request, "urlopen", urlopen)


def _chile(s):
    return datetime.datetime.fromisoformat(s).replace(tzinfo=TZ)


# ---------- constantes compartidas ----------
def test_mismas_urls_que_validar():
    assert publicacion.URLS_RESUMEN == validar.URLS_RESUMEN
    assert publicacion.INDICES == validar.INDICES


def test_misma_hora_de_odepa_que_build_site():
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    for n in arbol.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "elts", None) \
                and n.targets[0].elts[0].id == "ODEPA_DIA":
            assert ast.literal_eval(n.value) == (publicacion.ODEPA_DIA, publicacion.ODEPA_HORA)
            break
    else:
        pytest.fail("build_site.py sin ODEPA_DIA, ODEPA_HORA")


def test_semana_esperada_igual_que_build_site():
    from test_credibilidad import _funciones_del_aviso
    g = _funciones_del_aviso()
    inicio = _chile("2026-10-29T00:00")
    for h in range(0, 24 * 10, 1):
        f = inicio + datetime.timedelta(hours=h)
        assert publicacion.semana_esperada(f) == g["semana_esperada"](f), f


# ---------- semanas ----------
@pytest.mark.parametrize("ahora,objetivo", [
    ("2026-11-06T09:00", LUNES),                     # viernes, antes de ODEPA
    ("2026-11-06T12:30", LUNES),
    ("2026-11-06T19:13", LUNES),
    ("2026-11-07T09:23", LUNES),                     # sábado
    ("2026-11-08T22:00", LUNES),                     # domingo
    ("2026-11-09T10:00", LUNES),                     # lunes siguiente
    ("2026-11-12T23:59", LUNES),                     # jueves
    ("2026-11-13T00:01", LUNES + datetime.timedelta(weeks=1)),
])
def test_semana_objetivo(ahora, objetivo):
    assert publicacion.semana_objetivo(_chile(ahora)) == objetivo


# ---------- job revisar ----------
def _ref(semana):
    return {"semana": semana, "indices": {}}


def test_revisar_semana_ya_publicada_no_arma():
    for ahora in ["2026-11-06T12:30", "2026-11-06T19:13", "2026-11-07T11:41"]:
        construir, motivo = publicacion.revisar("schedule", _chile(ahora),
                                                _ref("2026-11-02"), "u", [])
        assert construir is False, ahora
        assert "ya está publicada" in motivo


def test_revisar_semana_pendiente_arma():
    for ahora in ["2026-11-06T12:30", "2026-11-06T19:13", "2026-11-07T11:41"]:
        construir, _ = publicacion.revisar("schedule", _chile(ahora), _ref("2026-10-26"), "u", [])
        assert construir is True, ahora


def test_revisar_a_mano_siempre_arma():
    construir, _ = publicacion.revisar("workflow_dispatch", _chile("2026-11-04T10:00"),
                                       _ref("2026-11-02"), "u", [])
    assert construir is True


def test_revisar_sin_referencia_o_ilegible_arma():
    assert publicacion.revisar("schedule", _chile("2026-11-06T12:30"), None, None, ["x"])[0]
    assert publicacion.revisar("schedule", _chile("2026-11-06T12:30"),
                               _ref("ayer"), "u", [])[0]


def test_leer_referencia_usa_el_respaldo():
    llamadas = []

    def get(url):
        llamadas.append(url)
        if "carestia.cl" in url:
            raise OSError("caído")
        return {"semana": "2026-11-02", "indices": {}}
    data, url, errores = publicacion.leer_referencia(get=get)
    assert url == publicacion.URLS_RESUMEN[1] and data["semana"] == "2026-11-02"
    assert len(errores) == 1 and llamadas == list(publicacion.URLS_RESUMEN)
    assert publicacion.leer_referencia(get=lambda u: {"x": 1})[0] is None


# ---------- paso de conteos ----------
# SEMANA_ANT 2026-09-14, SEMANA_NUEVA 2026-09-21: el viernes de SEMANA_NUEVA es el 25
VIERNES_TARDE = _chile("2026-09-25T18:00")
VIERNES_TEMPRANO = _chile("2026-09-25T12:30")


def test_semana_nueva_con_conteos_mas_1_pasa():
    r = publicacion.chequear_conteos(indices_nuevo(1), resumen_desplegado(), VIERNES_TARDE)
    assert r["ok"] and r["semanas"] == 1 and not r["errores"] and r["aviso"] is None
    assert [(c, a, n) for c, a, n, _e, _ok in r["filas"]] == \
        [(c, N_ANT[c], N_ANT[c] + 1) for c in validar.INDICES]


def test_conteo_que_no_es_la_referencia_mas_1_falla():
    data = indices_nuevo(1)
    data["indices"]["fruta"]["n"] += 1          # +2 en fruta, con la semana +1
    r = publicacion.chequear_conteos(data, resumen_desplegado(), VIERNES_TARDE)
    assert not r["ok"]
    assert r["errores"] == [f"fruta: {N_ANT['fruta'] + 2} semanas de historia, esperadas "
                            f"{N_ANT['fruta'] + 1} (la referencia, {N_ANT['fruta']}, más 1)"]
    data = indices_nuevo(1)
    data["indices"]["asado"]["n"] -= 1          # +0 en asado
    assert not publicacion.chequear_conteos(data, resumen_desplegado(), VIERNES_TARDE)["ok"]


def test_falta_un_indice_en_la_referencia_falla():
    ref = resumen_desplegado()
    del ref["indices"]["desayuno"]
    r = publicacion.chequear_conteos(indices_nuevo(1), ref, VIERNES_TARDE)
    assert not r["ok"] and any(e.startswith("desayuno:") for e in r["errores"])


def _misma_semana():
    """indices.json con la misma semana que la referencia y sus mismos conteos."""
    data = indices_nuevo(1)
    for d in data["indices"].values():
        d["real"] = d["real"][:-1]
        d["n"] -= 1
    return data


def test_misma_semana_antes_de_que_odepa_publique_pasa_sin_aviso():
    r = publicacion.chequear_conteos(_misma_semana(), resumen_desplegado(), VIERNES_TEMPRANO)
    assert r["ok"] and r["semanas"] == 0 and r["aviso"] is None
    assert any("todavía no publica" in a for a in r["avisos"])


def test_misma_semana_despues_de_las_17_publica_y_avisa():
    for ahora in [VIERNES_TARDE, _chile("2026-09-26T09:23")]:
        r = publicacion.chequear_conteos(_misma_semana(), resumen_desplegado(), ahora)
        assert r["ok"] and r["aviso"] == "odepa", ahora


def test_misma_semana_a_mitad_de_semana_pasa_sin_avisos():
    """Una corrida a mano un miércoles, con la semana del lunes anterior ya
    publicada."""
    ref = resumen_desplegado()
    ref["semana"] = SEMANA_NUEVA
    ref["indices"] = {c: dict(v, semanas_historia=N_ANT[c] + 1) for c, v in ref["indices"].items()}
    r = publicacion.chequear_conteos(indices_nuevo(1), ref, _chile("2026-09-30T10:00"))
    assert r["ok"] and r["semanas"] == 0 and r["aviso"] is None and not r["avisos"]


def test_misma_semana_con_un_conteo_distinto_falla():
    data = _misma_semana()
    data["indices"]["ensalada"]["n"] += 1
    r = publicacion.chequear_conteos(data, resumen_desplegado(), VIERNES_TEMPRANO)
    assert not r["ok"] and r["errores"][0].startswith("ensalada:")


def test_dos_semanas_de_salto_falla_salvo_aceptar_salto():
    ref = resumen_desplegado()
    ref["semana"] = "2026-09-07"
    ref["indices"] = {c: dict(v, semanas_historia=N_ANT[c] - 1) for c, v in ref["indices"].items()}
    r = publicacion.chequear_conteos(indices_nuevo(1), ref, VIERNES_TARDE)
    assert not r["ok"] and "aceptar_salto" in r["errores"][0]
    r = publicacion.chequear_conteos(indices_nuevo(1), ref, VIERNES_TARDE, aceptar_salto=True)
    assert r["ok"] and r["semanas"] == 2


def test_semana_hacia_atras_o_fuera_de_lunes_falla():
    for semana in ["2026-09-28", "2026-09-17"]:
        ref = resumen_desplegado()
        ref["semana"] = semana
        r = publicacion.chequear_conteos(indices_nuevo(1), ref, VIERNES_TARDE)
        assert not r["ok"] and "salto de" in r["errores"][0], semana


# ---------- de punta a punta, como en el workflow ----------
def _correr(tmp_path, comando, env_extra, ref):
    """Corre publicacion.py en un subproceso con la descarga reemplazada."""
    (tmp_path / "indices.json").write_text(json.dumps(indices_nuevo(1)), encoding="utf-8")
    salida, summary = tmp_path / "out", tmp_path / "summary"
    salida.write_text(""), summary.write_text("")
    script = (f"import sys, json; sys.path.insert(0, {RAIZ!r}); import publicacion\n"
              f"publicacion._get_json = lambda url: json.loads({json.dumps(json.dumps(ref))})\n"
              f"sys.exit(publicacion.main_{comando}())\n")
    env = dict(os.environ, GITHUB_OUTPUT=str(salida), GITHUB_STEP_SUMMARY=str(summary),
               **env_extra)
    p = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    return p, salida.read_text(), summary.read_text()


def test_main_revisar_escribe_construir(tmp_path):
    p, out, summary = _correr(tmp_path, "revisar",
                              {"GITHUB_EVENT_NAME": "schedule",
                               "CARESTIA_AHORA": "2026-09-25T12:30"},
                              dict(resumen_desplegado(), semana=SEMANA_NUEVA))
    assert p.returncode == 0 and out == "construir=false\n"
    assert "Nada que hacer" in summary
    p, out, _ = _correr(tmp_path, "revisar", {"GITHUB_EVENT_NAME": "schedule",
                                              "CARESTIA_AHORA": "2026-09-25T12:30"},
                        resumen_desplegado())
    assert p.returncode == 0 and out == "construir=true\n"


def test_main_conteos_pasa_y_falla_con_ruido(tmp_path):
    p, out, summary = _correr(tmp_path, "conteos", {"CARESTIA_AHORA": "2026-09-25T18:00"},
                              resumen_desplegado())
    assert p.returncode == 0, p.stdout + p.stderr
    assert out == "" and "**PASA.**" in summary
    malo = resumen_desplegado()
    malo["indices"]["asado"]["semanas_historia"] -= 1
    p, out, summary = _correr(tmp_path, "conteos", {"CARESTIA_AHORA": "2026-09-25T18:00"}, malo)
    assert p.returncode == 1
    assert "::error::Conteos: asado:" in p.stdout
    assert "FALLA" in summary
    # misma semana después de las 17:00: pasa con aviso=odepa
    ref = dict(resumen_desplegado(), semana=SEMANA_NUEVA)
    ref["indices"] = {c: dict(v, semanas_historia=N_ANT[c] + 1)
                      for c, v in ref["indices"].items()}
    p, out, _ = _correr(tmp_path, "conteos", {"CARESTIA_AHORA": "2026-10-02T18:00"}, ref)
    assert p.returncode == 0 and out == "aviso=odepa\n"
    assert "::warning::ODEPA no publicó" in p.stdout

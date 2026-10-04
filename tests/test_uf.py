"""Tests sintéticos de uf.py. No tocan la red ni esperan: requests.get está
reemplazado por un fake en todos los tests (y un pedido no previsto revienta)
y uf.dormir solo anota las esperas."""
import datetime
import json
import os
import sys
from urllib.parse import parse_qs, quote, quote_plus, urlsplit
from zoneinfo import ZoneInfo

import pytest
import requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import uf  # noqa: E402

D = datetime.date
SANTIAGO = ZoneInfo("America/Santiago")
INICIO = D(2007, 12, 31)
HOY = D(2026, 10, 4)                 # domingo: el lunes de la semana es el 28-09-2026
LUNES_HOY = D(2026, 9, 28)
PUBLICADO = D(2026, 10, 9)           # la UF se publica hasta el 9 del mes siguiente
N_REQ = (LUNES_HOY - INICIO).days // 7 + 1
USUARIO, CLAVE = "usuario.secreto@ejemplo.cl", "cl@ve&Secreta#1 x"


def uf_dia(d: D) -> float:
    return round(19622.66 * 1.0001 ** (d - INICIO).days, 2)


def lunes(i: int) -> D:
    return INICIO + datetime.timedelta(weeks=i)


def diarios(hasta=PUBLICADO, sin=(), mas=0.0, desde=INICIO) -> dict:
    out, d = {}, desde
    while d <= hasta:
        if d not in sin:
            out[d] = round(uf_dia(d) + mas, 2)
        d += datetime.timedelta(days=1)
    return out


def es_cl(x: float) -> str:
    entero, dec = f"{x:.2f}".split(".")
    grupos = []
    while entero:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    return ".".join(grupos) + "," + dec


# ---------------- Fakes ----------------
class Resp:
    def __init__(self, data=None, texto=None, status=200):
        self._data = data
        self.text = texto if texto is not None else json.dumps(data)
        self.status_code = status

    def json(self):
        if self._data is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._data


def resp_bcch(dias: dict, extra=()) -> Resp:
    obs = [{"indexDateString": d.strftime("%d-%m-%Y"), "value": f"{v:.2f}", "statusCode": "OK"}
           for d, v in sorted(dias.items())]
    return Resp({"Codigo": 0, "Descripcion": "Success",
                 "Series": {"descripEsp": "Unidad de fomento (UF)",
                            "seriesId": "F073.UFF.PRE.Z.D", "Obs": obs + list(extra)},
                 "SeriesInfos": []})


def fecha_utc(d: D, hora=None) -> str:
    """Medianoche chilena en UTC, como la da mindicador (hora fija si se pide)."""
    if hora:
        return f"{d.isoformat()}T{hora}:00:00.000Z"
    t = datetime.datetime(d.year, d.month, d.day, tzinfo=SANTIAGO)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def resp_mind(dias: dict, anio: int, hora=None) -> Resp:
    serie = [{"fecha": fecha_utc(d, hora), "valor": v}
             for d, v in sorted(dias.items(), reverse=True) if d.year == anio]
    return Resp({"version": "1.7.0", "autor": "mindicador.cl", "codigo": "uf",
                 "nombre": "Unidad de fomento (UF)", "unidad_medida": "Pesos", "serie": serie})


class Red:
    """requests.get falso: rutea por host y anota cada URL pedida."""

    def __init__(self, bcch=None, mind=None):
        self.urls, self.bcch, self.mind = [], bcch, mind

    def get(self, url, timeout=None, **kw):
        assert timeout, "todo pedido lleva timeout"
        self.urls.append(url)
        if url.startswith("https://si3.bcentral.cl/"):
            assert self.bcch, "no se esperaba un pedido al Banco Central"
            return self.bcch(url)
        if url.startswith("https://mindicador.cl/api/uf/"):
            assert self.mind, "no se esperaba un pedido a mindicador"
            return self.mind(int(url.rsplit("/", 1)[1]))
        raise AssertionError(f"pedido inesperado: {url}")

    def a(self, host):
        return [u for u in self.urls if host in u]


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BCCH_USER", USUARIO)
    monkeypatch.setenv("BCCH_PASS", CLAVE)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    esperas = []
    monkeypatch.setattr(uf, "dormir", esperas.append)

    def sin_red(*a, **k):
        raise AssertionError("test sin red: requests.get no está reemplazado")
    monkeypatch.setattr(uf.requests, "get", sin_red)
    return esperas


def instalar(monkeypatch, red: Red) -> Red:
    monkeypatch.setattr(uf.requests, "get", red.get)
    return red


def leer_uf() -> dict:
    with open(os.path.join("datos", "uf.json"), encoding="utf-8") as fh:
        return json.load(fh)


def stale():
    os.makedirs("datos", exist_ok=True)
    with open(os.path.join("datos", "uf.json"), "w", encoding="utf-8") as fh:
        fh.write('{"t0":"2007-12-31","v":[1]}')


def es_falla_suave(capsys, retorno):
    assert retorno == 0
    assert not os.path.exists(os.path.join("datos", "uf.json"))
    assert not os.path.exists(os.path.join("datos", "uf.json.tmp"))
    out = capsys.readouterr().out
    avisos = [x for x in out.splitlines() if x.startswith("::warning::")]
    assert len(avisos) == 1, out
    assert "sin la opción UF" in avisos[0]
    return avisos[0]


# ---------------- Fechas ----------------
def test_lunes_requeridos():
    req = uf.lunes_requeridos(HOY)
    assert req[0] == INICIO and req[-1] == LUNES_HOY and len(req) == N_REQ
    assert all(d.weekday() == 0 for d in req)
    assert uf.lunes_requeridos(LUNES_HOY)[-1] == LUNES_HOY      # el lunes mismo cuenta
    assert uf.lunes_requeridos(D(2026, 9, 27))[-1] == D(2026, 9, 21)


def test_anios_mindicador():
    assert uf.anios_mindicador(HOY) == list(range(2007, 2027))
    assert uf.anios_mindicador(D(2026, 12, 21)) == list(range(2007, 2028))
    # sin nada del Banco Central faltan todos los lunes: el orden no cambia
    assert uf.anios_mindicador(HOY, uf.lunes_requeridos(HOY)) == list(range(2007, 2027))
    dic = D(2026, 12, 21)
    assert uf.anios_mindicador(dic, uf.lunes_requeridos(dic)) == list(range(2007, 2028))


def test_anios_mindicador_primero_los_que_faltan():
    otros = [a for a in range(2007, 2027) if a not in (2015, 2026)]
    assert uf.anios_mindicador(HOY, [LUNES_HOY, D(2015, 6, 1)]) == [2015, 2026] + otros
    # en diciembre, el año siguiente (solo lunes ya publicados) también va antes
    dic = D(2026, 12, 21)
    assert uf.anios_mindicador(dic, [dic]) == [2026, 2027] + list(range(2007, 2026))


@pytest.mark.parametrize("texto, fecha", [
    ("2026-10-04T03:00:00.000Z", D(2026, 10, 4)),    # verano, UTC-3
    ("2026-07-01T04:00:00.000Z", D(2026, 7, 1)),     # invierno, UTC-4
    ("2026-07-01T03:00:00.000Z", D(2026, 7, 1)),     # 23:00 del día anterior en Chile
    ("2026-01-15T04:00:00.000Z", D(2026, 1, 15)),    # 01:00 en Chile
    ("2026-09-06T04:00:00.000Z", D(2026, 9, 6)),     # día del cambio de hora
    ("2026-04-05T03:00:00.000Z", D(2026, 4, 5)),     # día del cambio de hora
    ("2008-01-02T03:00:00.000Z", D(2008, 1, 2)),
])
def test_fecha_mindicador(texto, fecha):
    assert uf.fecha_mindicador(texto) == fecha


def test_pesos():
    assert uf.pesos(39485.65) == "39.485,65"
    assert uf.pesos(19622.6) == "19.622,60"
    assert uf.pesos(1234567.891) == "1.234.567,89"


# ---------------- 1. Banco Central OK ----------------
def test_bcch_ok(monkeypatch, capsys, entorno, tmp_path):
    resumen = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumen))
    dias = diarios()
    ruido = [{"indexDateString": "11-10-2026", "value": "NaN", "statusCode": "ND"},
             {"indexDateString": "12-10-2026", "value": "NaN", "statusCode": "OK"},
             {"indexDateString": "19-10-2026", "value": f"{uf_dia(D(2026, 10, 19)):.2f}",
              "statusCode": "OK"}]
    red = instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(dias, ruido)))
    stale()

    assert uf.main(HOY) == 0

    out = leer_uf()
    assert list(out) == ["fuente", "serie", "generado", "t0", "v"]
    assert out["fuente"] == "Banco Central de Chile"
    assert out["serie"] == "F073.UFF.PRE.Z.D"
    assert out["generado"] == "2026-10-04" and out["t0"] == "2007-12-31"
    # todos los lunes hasta el 28-09-2026, más el 05-10-2026 (ya publicado);
    # el 12-10-2026 viene NaN y ahí corta, aunque el 19-10-2026 tenga valor
    assert len(out["v"]) == N_REQ + 1
    assert out["v"] == [uf_dia(lunes(i)) for i in range(N_REQ + 1)]
    assert lunes(len(out["v"]) - 1) == D(2026, 10, 5)
    # JSON compacto
    with open(os.path.join("datos", "uf.json"), encoding="utf-8") as fh:
        crudo = fh.read()
    assert crudo.startswith('{"fuente":"Banco Central de Chile","serie":"F073.UFF.PRE.Z.D",'
                            '"generado":"2026-10-04","t0":"2007-12-31","v":[19622.66,')
    assert " " not in crudo.replace("Banco Central de Chile", "")
    # un solo pedido, al Banco Central, con la serie y el rango correctos
    assert red.a("mindicador") == [] and len(red.a("si3.bcentral.cl")) == 1
    q = parse_qs(urlsplit(red.urls[0]).query)
    assert q["timeseries"] == ["F073.UFF.PRE.Z.D"] and q["function"] == ["GetSeries"]
    assert q["firstdate"] == ["2007-12-31"] and q["lastdate"] == ["2026-11-18"]
    assert q["user"] == [USUARIO] and q["pass"] == [CLAVE]
    assert entorno == []
    # resumen en consola y en el workflow
    salida = capsys.readouterr().out
    linea = f"UF del lunes 28-09-2026: {es_cl(uf_dia(LUNES_HOY))}"
    assert linea in salida
    assert "Banco Central de Chile" in salida and f"{N_REQ + 1} semanas" in salida
    assert "31-12-2007" in salida and "05-10-2026" in salida
    assert "::warning::" not in salida
    assert linea in resumen.read_text(encoding="utf-8")


def test_leer_bcch_descarta_status_no_ok():
    data = {"Codigo": 0, "Series": {"Obs": [
        {"indexDateString": "05-01-2026", "value": "39000.00", "statusCode": "ND"},
        {"indexDateString": "06-01-2026", "value": "39001.00", "statusCode": "OK"}]}}
    assert uf._leer_bcch(data) == {D(2026, 1, 6): 39001.0}


def test_lunes_sin_status_ok_lo_llena_mindicador(monkeypatch):
    """Un lunes obligatorio que el Banco Central trae sin statusCode OK no se
    usa, aunque traiga un número: falta, y lo llena mindicador."""
    hueco = lunes(200)
    nd = [{"indexDateString": uf.ddmmaaaa(hueco), "value": f"{uf_dia(hueco) + 5:.2f}",
           "statusCode": "ND"}]
    bcch = diarios(sin={hueco})
    mind = diarios(mas=1.0)
    red = instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(bcch, nd),
                                    mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    out = leer_uf()
    assert out["fuente"] == "Banco Central de Chile y mindicador.cl"
    assert out["v"][200] == mind[hueco]
    assert out["v"][199] == bcch[lunes(199)] and out["v"][201] == bcch[lunes(201)]
    assert red.a("/api/uf/" + str(hueco.year))


def test_formato_es_cl_en_resumen(monkeypatch, capsys):
    dias = diarios()
    dias[LUNES_HOY] = 39485.65
    dias[LUNES_HOY - datetime.timedelta(weeks=1)] = 39400.00
    dias[LUNES_HOY + datetime.timedelta(weeks=1)] = 39500.00
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(dias)))
    assert uf.main(HOY) == 0
    assert "UF del lunes 28-09-2026: 39.485,65" in capsys.readouterr().out


# ---------------- 2. Banco Central con error -> mindicador ----------------
def test_bcch_error_usa_mindicador(monkeypatch, entorno):
    error = Resp({"Codigo": -5, "Descripcion": "Invalid username or password",
                  "Series": {"descripEsp": None, "seriesId": None, "Obs": None},
                  "SeriesInfos": []})
    mind = diarios(mas=1.0)
    red = instalar(monkeypatch, Red(bcch=lambda url: error,
                                    mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    out = leer_uf()
    assert out["fuente"] == "mindicador.cl"
    assert out["v"] == [mind[lunes(i)] for i in range(N_REQ + 1)]
    assert len(red.a("si3.bcentral.cl")) == 1          # un error declarado no se reintenta
    assert sorted(int(u.rsplit("/", 1)[1]) for u in red.a("mindicador")) == list(range(2007, 2027))
    assert entorno == []


# ---------------- 3. Fusión ----------------
def test_fusion_bcch_manda(monkeypatch, capsys):
    faltan = {lunes(100), lunes(500), LUNES_HOY}
    bcch = diarios(sin=faltan)
    mind = diarios(mas=1.0)
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(bcch),
                              mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    out = leer_uf()
    assert out["fuente"] == "Banco Central de Chile y mindicador.cl"
    for i, x in enumerate(out["v"]):
        d = lunes(i)
        assert x == (mind[d] if d in faltan else bcch[d]), d
    assert "faltan 3 lunes" in capsys.readouterr().out


def test_fusion_unidad():
    diarios_, de_mind = uf.fusionar({D(2026, 1, 5): 1.0, D(2026, 1, 6): 2.0},
                                    {D(2026, 1, 6): 9.0, D(2026, 1, 7): 3.0})
    assert diarios_ == {D(2026, 1, 5): 1.0, D(2026, 1, 6): 2.0, D(2026, 1, 7): 3.0}
    assert de_mind == {D(2026, 1, 7)}
    assert uf.nombre_fuente([D(2026, 1, 5)], de_mind) == "Banco Central de Chile"
    assert uf.nombre_fuente([D(2026, 1, 7)], de_mind) == "mindicador.cl"
    assert uf.nombre_fuente([D(2026, 1, 5), D(2026, 1, 7)], de_mind) == \
        "Banco Central de Chile y mindicador.cl"


def test_anio_fallido_de_mindicador_no_importa_si_no_hace_falta(monkeypatch, capsys):
    bcch = diarios(sin={LUNES_HOY})
    mind = diarios(mas=1.0)

    def mindicador(anio):
        if anio == 2010:
            raise requests.ConnectionError("mindicador caído")
        return resp_mind(mind, anio)
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(bcch), mind=mindicador))
    assert uf.main(HOY) == 0
    out = leer_uf()
    assert out["fuente"] == "Banco Central de Chile y mindicador.cl"
    assert out["v"][N_REQ - 1] == mind[LUNES_HOY]
    assert "mindicador 2010 falló" in capsys.readouterr().out


def test_mindicador_caido_a_medias(monkeypatch, capsys):
    """Al Banco Central le falta solo el lunes de esta semana y mindicador no
    responde en 2008 ni de 2010 a 2012. Un año suelto no corta; tres seguidos
    sí, pero 2026 (el año que hacía falta) se pidió primero: hay UF."""
    bcch = diarios(sin={LUNES_HOY})
    mind = diarios(mas=1.0)
    caidos = {2008, 2010, 2011, 2012}

    def mindicador(anio):
        if anio in caidos:
            raise requests.ConnectionError("mindicador caído")
        return resp_mind(mind, anio)
    red = instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(bcch), mind=mindicador))
    stale()
    assert uf.main(HOY) == 0
    out = leer_uf()
    assert out["fuente"] == "Banco Central de Chile y mindicador.cl"
    assert out["v"][N_REQ - 1] == mind[LUNES_HOY]
    assert out["v"] == [mind[lunes(i)] if i == N_REQ - 1 else bcch[lunes(i)]
                        for i in range(N_REQ + 1)]
    pedidos = list(dict.fromkeys(int(u.rsplit("/", 1)[1]) for u in red.a("mindicador")))
    assert pedidos == [2026] + list(range(2007, 2013))
    salida = capsys.readouterr().out
    assert "3 años seguidos sin respuesta" in salida and "::warning::" not in salida


def test_mindicador_corta_en_un_anio_necesario(monkeypatch, capsys):
    """Si el corte llega mientras se piden los años necesarios, ya falló uno
    de ellos: falla suave, sin pedir el resto."""
    faltan = {lunes(100), lunes(300), lunes(500), LUNES_HOY}
    bcch = diarios(sin=faltan)

    def mindicador(anio):
        raise requests.ConnectionError("mindicador caído")
    red = instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(bcch), mind=mindicador))
    stale()
    aviso = es_falla_suave(capsys, uf.main(HOY))
    pedidos = list(dict.fromkeys(int(u.rsplit("/", 1)[1]) for u in red.a("mindicador")))
    assert pedidos == sorted({d.year for d in faltan})[:3]
    assert "faltan 4 lunes" in aviso


# ---------------- 4. Sin credenciales ----------------
@pytest.mark.parametrize("vacia", ["BCCH_USER", "BCCH_PASS"])
def test_sin_credenciales(monkeypatch, capsys, vacia):
    monkeypatch.setenv(vacia, "")
    mind = diarios()
    red = instalar(monkeypatch, Red(mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    assert red.a("bcentral") == []
    assert leer_uf()["fuente"] == "mindicador.cl"
    assert leer_uf()["v"] == [uf_dia(lunes(i)) for i in range(N_REQ + 1)]
    assert "sin credenciales BCCh" in capsys.readouterr().out


def test_anio_vacio_es_respuesta_valida(monkeypatch, entorno):
    """En diciembre se pide el año siguiente; si aún no tiene datos, la lista
    vacía es una respuesta válida y no se reintenta."""
    monkeypatch.delenv("BCCH_USER")
    hoy = D(2026, 12, 21)
    mind = diarios(hasta=D(2026, 12, 31))
    red = instalar(monkeypatch, Red(mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(hoy) == 0
    assert len(red.a("/api/uf/2027")) == 1 and entorno == []
    out = leer_uf()
    assert lunes(len(out["v"]) - 1) == D(2026, 12, 28)


# ---------------- 5. Fechas de mindicador en la serie ----------------
@pytest.mark.parametrize("hora", [None, "03", "04"])
def test_mindicador_fechas_en_la_serie(monkeypatch, hora):
    monkeypatch.delenv("BCCH_PASS")
    mind = diarios()
    instalar(monkeypatch, Red(mind=lambda anio: resp_mind(mind, anio, hora)))
    assert uf.main(HOY) == 0
    assert leer_uf()["v"] == [uf_dia(lunes(i)) for i in range(N_REQ + 1)]


# ---------------- 6. Las dos fuentes fallan ----------------
def test_ambas_fallan(monkeypatch, capsys, entorno, tmp_path):
    resumen = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumen))

    def bcch(url):
        raise requests.ConnectionError("Max retries exceeded")

    def mind(anio):
        raise requests.Timeout("Read timed out")
    red = instalar(monkeypatch, Red(bcch=bcch, mind=mind))
    stale()
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert "ninguna fuente respondió" in aviso
    assert len(red.a("bcentral")) == 3                  # 3 intentos por pedido
    # mindicador: tras 3 años seguidos sin respuesta no se piden los demás
    assert sorted(set(red.a("mindicador"))) == [f"https://mindicador.cl/api/uf/{a}"
                                                for a in (2007, 2008, 2009)]
    assert len(red.a("mindicador")) == 3 * 3
    assert entorno == [2, 4] * 4                        # esperas de 2 y 4 s
    assert "sin la opción UF" in resumen.read_text(encoding="utf-8")


def test_error_inesperado_es_falla_suave(monkeypatch, capsys):
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(diarios())))

    def revienta(*a, **k):
        raise RuntimeError("algo raro")
    monkeypatch.setattr(uf, "semanas", revienta)
    stale()
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert "RuntimeError: algo raro" in aviso


def test_json_inesperado(monkeypatch, capsys):
    """Respuestas que no son JSON, o JSON sin la forma esperada."""
    instalar(monkeypatch, Red(bcch=lambda url: Resp(texto="<html>502 Bad Gateway</html>", status=502),
                              mind=lambda anio: Resp([1, 2])))
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert "ninguna fuente respondió" in aviso and "502" in aviso


# ---------------- 7. Lunes sin valor en ninguna fuente ----------------
def test_lunes_faltante_en_ambas(monkeypatch, capsys):
    hueco = D(2015, 6, 1)
    assert hueco.weekday() == 0
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(diarios(sin={hueco})),
                              mind=lambda anio: resp_mind(diarios(sin={hueco}), anio)))
    stale()
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert "faltan 1 lunes (01-06-2015)" in aviso


def test_lunes_actual_faltante(monkeypatch, capsys):
    """Si ninguna fuente tiene aún el lunes de la semana en curso, no hay UF."""
    dias = diarios(hasta=LUNES_HOY - datetime.timedelta(days=1))
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(dias),
                              mind=lambda anio: resp_mind(dias, anio)))
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert "28-09-2026" in aviso


# ---------------- 8. Valores imposibles ----------------
@pytest.mark.parametrize("valor, texto", [
    (lambda x: x * 1.03, "saltos de 2% o más"),
    (lambda x: 0.0, "fuera de rango"),
    (lambda x: 150000.0, "fuera de rango"),
])
def test_valor_imposible(monkeypatch, capsys, valor, texto):
    dias = diarios()
    malo = lunes(300)
    dias[malo] = round(valor(dias[malo]), 2)
    instalar(monkeypatch, Red(bcch=lambda url: resp_bcch(dias)))
    stale()
    aviso = es_falla_suave(capsys, uf.main(HOY))
    assert texto in aviso and uf.ddmmaaaa(malo) in aviso


def test_validar_unidad():
    v = [uf_dia(lunes(i)) for i in range(N_REQ)]
    assert uf.validar(INICIO, v, HOY) == []
    assert uf.validar(INICIO, v + [v[-1] * 1.019], HOY) == []
    assert "saltos" in uf.validar(INICIO, v + [v[-1] * 1.021], HOY)[0]
    assert "saltos" in uf.validar(INICIO, v + [v[-1] * 0.97], HOY)[0]
    assert "faltan 1 lunes" in uf.validar(INICIO, v[:-1], HOY)[0]
    assert "fuera de rango" in uf.validar(INICIO, v[:-1] + [float("nan")], HOY)[0]


# ---------------- 9. Credenciales ----------------
def _sin_credenciales(texto: str):
    for s in (USUARIO, CLAVE, quote(USUARIO, safe=""), quote(CLAVE, safe=""),
              quote_plus(USUARIO), quote_plus(CLAVE), "Secreta", "usuario.secreto"):
        assert s not in texto, s


def test_credenciales_nunca_se_imprimen(monkeypatch, capsys, tmp_path):
    resumen = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumen))

    def bcch(url):
        ruta = url.split("si3.bcentral.cl", 1)[1]
        raise requests.ConnectionError(
            f"HTTPSConnectionPool(host='si3.bcentral.cl', port=443): Max retries exceeded "
            f"with url: {ruta} (Caused by NameResolutionError) [{USUARIO} {CLAVE}]")

    def mind(anio):
        raise requests.ConnectionError(f"sin red para {anio}")
    instalar(monkeypatch, Red(bcch=bcch, mind=mind))
    stale()
    assert uf.main(HOY) == 0
    assert not os.path.exists(os.path.join("datos", "uf.json"))
    cap = capsys.readouterr()
    assert "::warning::" in cap.out
    _sin_credenciales(cap.out + cap.err)
    _sin_credenciales(resumen.read_text(encoding="utf-8"))
    assert "user=***" in cap.out and "pass=***" in cap.out


@pytest.mark.parametrize("respuesta", [
    lambda url: Resp(texto=f"<html>Error en {url} para {USUARIO}</html>", status=500),
    lambda url: Resp({"Codigo": -5, "Descripcion": f"Usuario {USUARIO} clave {CLAVE} invalidos",
                      "Series": {"Obs": None}}),
])
def test_credenciales_en_respuesta_del_bcch(monkeypatch, capsys, respuesta):
    mind = diarios()
    instalar(monkeypatch, Red(bcch=respuesta, mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    cap = capsys.readouterr()
    _sin_credenciales(cap.out + cap.err)
    assert "***" in cap.out
    assert leer_uf()["fuente"] == "mindicador.cl"


@pytest.mark.parametrize("secreto", [USUARIO, CLAVE])
@pytest.mark.parametrize("inicio", [190, 194])
def test_credenciales_en_el_corte_del_cuerpo(monkeypatch, capsys, secreto, inicio):
    """El cuerpo que no es JSON se muestra cortado a 200 caracteres. Se limpia
    antes de cortar: un secreto partido por el corte no deja ver su comienzo."""
    cuerpo = "x" * (inicio - 1) + " " + secreto + " ok"
    assert cuerpo.index(secreto) == inicio < 200 < inicio + len(secreto)
    mind = diarios()
    instalar(monkeypatch, Red(bcch=lambda url: Resp(texto=cuerpo, status=500),
                              mind=lambda anio: resp_mind(mind, anio)))
    assert uf.main(HOY) == 0
    cap = capsys.readouterr()
    salida = cap.out + cap.err
    _sin_credenciales(salida)
    for n in range(4, len(secreto) + 1):
        assert secreto[:n] not in salida, secreto[:n]
    assert "***" in salida and leer_uf()["fuente"] == "mindicador.cl"


def test_texto_ajeno_no_arma_comandos_del_workflow(monkeypatch, capsys):
    """Un salto de línea en la Descripcion del Banco Central o en un error de
    red no puede dejar una línea que empiece con "::" (GitHub Actions la toma
    como comando): cada mensaje se imprime en una sola línea."""
    error = Resp({"Codigo": -1, "Series": {"Obs": None},
                  "Descripcion": "Error interno\n::error title=x::inyectado\r\n"
                                 "::add-mask::algo\n::stop-commands::fin"})

    def mind(anio):
        raise requests.ConnectionError("caído\n  ::error::desde mindicador")
    instalar(monkeypatch, Red(bcch=lambda url: error, mind=mind))
    stale()
    assert uf.main(HOY) == 0
    assert not os.path.exists(os.path.join("datos", "uf.json"))
    out = capsys.readouterr().out
    comandos = [x for x in out.splitlines() if x.lstrip().startswith("::")]
    assert len(comandos) == 1 and comandos[0].startswith("::warning::"), out
    assert "inyectado" in comandos[0] and "stop-commands" in comandos[0]
    assert "desde mindicador" in out and "\r" not in out


def test_limpiar():
    url = ("https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?user=otro&pass=x%20y"
           "&firstdate=2007-12-31")
    assert uf.limpiar(url).endswith("?user=***&pass=***&firstdate=2007-12-31")
    _sin_credenciales(uf.limpiar(f"{USUARIO} {quote_plus(CLAVE)} {quote(CLAVE, safe='')}"))
    # clave cruda tras "pass=": el "&" de la clave no deja una cola a la vista
    _sin_credenciales(uf.limpiar(f"eco user={USUARIO}&pass={CLAVE}&firstdate=x"))
    _sin_credenciales(uf.limpiar(f"eco pass={CLAVE} fin"))
    # la clave lleva un espacio: con un salto de línea en su lugar también se tapa
    _sin_credenciales(uf.limpiar("eco " + CLAVE.replace(" ", "\n") + " fin"))
    # siempre una sola línea
    assert uf.limpiar("a\nb\r\n  c ::x\t d") == "a b c ::x d"


# ---------------- 10. Reintentos ----------------
def test_reintentos(monkeypatch, entorno):
    dias = diarios()
    intentos = []

    def bcch(url):
        intentos.append(url)
        if len(intentos) == 1:
            raise requests.ConnectionError("se cortó")
        if len(intentos) == 2:
            return Resp(texto="<html>503</html>", status=503)
        return resp_bcch(dias)
    red = instalar(monkeypatch, Red(bcch=bcch))
    assert uf.main(HOY) == 0
    assert len(intentos) == 3 and entorno == [2, 4]
    assert red.a("mindicador") == []
    assert leer_uf()["fuente"] == "Banco Central de Chile"


def test_reintentos_mindicador(monkeypatch, entorno):
    monkeypatch.delenv("BCCH_USER")
    mind = diarios()
    fallas = {2012: 2}

    def mindicador(anio):
        if fallas.get(anio, 0) > 0:
            fallas[anio] -= 1
            raise requests.Timeout("Read timed out")
        return resp_mind(mind, anio)
    red = instalar(monkeypatch, Red(mind=mindicador))
    assert uf.main(HOY) == 0
    assert len(red.a("/api/uf/2012")) == 3 and entorno == [2, 4]
    assert leer_uf()["v"] == [uf_dia(lunes(i)) for i in range(N_REQ + 1)]

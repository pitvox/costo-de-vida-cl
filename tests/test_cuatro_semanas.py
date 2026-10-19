"""El cambio de 4 semanas al lado de cada variación semanal. Sin red:
build_site.py corre en un directorio temporal con un indices.json sintético
de valores controlados.

Es el promedio de las últimas 4 semanas con precio contra el promedio de las
4 anteriores, sobre las mismas series de indices.json (real de los índices,
v de los productos, ajustadas por inflación): las semanas sin precio no
cuentan y con menos de 8 semanas con precio no va. Verifica la cinta, las
tarjetas de "Índices Carestía", la tabla de la portada, la ficha de cada
producto y la cifra del índice en /graficos.html, y que resumen.json no
cambie."""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from indices import BASKETS  # noqa: E402

FIN = datetime.date(2026, 9, 21)   # lunes de la semana vigente
CODES = list(BASKETS)              # asado, ensalada, fruta, desayuno


def _indice(code: str, valores: list, saltos: dict = None) -> dict:
    """Un índice con 'valores' semanales que terminan en FIN; 'saltos' {i: n}
    deja n semanas sin dato antes del valor i (indices.json no trae esos
    puntos)."""
    saltos = saltos or {}
    semanas, t = [], FIN
    for i in range(len(valores) - 1, -1, -1):
        semanas.append(t)
        t -= datetime.timedelta(weeks=1 + saltos.get(i, 0))
    real = [{"time": f.isoformat(), "value": v}
            for f, v in zip(reversed(semanas), valores)]
    meta = BASKETS[code]
    return {
        "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
        "fecha": FIN.strftime("%d-%m-%Y"), "costo_nominal": valores[-1],
        "costo_real": valores[-1], "percentil": 50, "zscore": 0.0, "vs_promedio": 0,
        "veredicto": "NORMAL", "color": "#e0a83c",
        "base_veredicto": "toda la historia", "percentil_temporada": None,
        "anios_temporada": None, "temporada": None, "n": len(real),
        "componentes": [{"label": lab, "qty": qty, "unidad": uni, "odepa_unit": "$/kg",
                         "factor": 1.0, "mismatch": False, "precio_ult": 1000,
                         "aporte": 1000} for (lab, _m, qty, uni) in meta["items"]],
        "estacionalidad": {"factores": {str(m): 1.0 for m in range(1, 13)},
                           "mes_barato": 1, "mes_caro": 2, "amplitud": 1},
        "velas": [], "nominal": real, "real": real,
    }


def _producto(label: str, v: list) -> dict:
    t0 = FIN - datetime.timedelta(weeks=len(v) - 1)
    return {"label": label, "unidad": "kg", "grupo": "Hortalizas",
            "t0": t0.isoformat(), "v": v}


def sintetico() -> dict:
    out = {"generado": "2026-09-26", "ipc_mes": "2026-08", "indices": {},
           "productos": {}, "descartes": []}
    # asado: 4 semanas en 10.000 y 4 en 12.000 (+20%), con 2 semanas sin dato
    # en medio que no cuentan; esta semana igual que la anterior
    out["indices"]["asado"] = _indice("asado", [10000] * 56 + [12000] * 4, {57: 2})
    # ensalada: 6 semanas, sin el cambio de 4 semanas
    out["indices"]["ensalada"] = _indice("ensalada", [8000, 8100, 8200, 8300, 8400, 8500])
    # fruta: de 10.000 a 9.000 (-10%)
    out["indices"]["fruta"] = _indice("fruta", [10000] * 56 + [9000] * 4)
    # desayuno: plano
    out["indices"]["desayuno"] = _indice("desayuno", [9000] * 60)
    p = out["productos"]
    # con semanas sin precio entre medio: las últimas 8 con precio son
    # 4 en 1.000 y 4 en 2.000 (+100%)
    p["huecos"] = _producto("Huecos", [1000] * 20 + [1000, None, 1000, 1000, None, None,
                                                      1000, 2000, None, 2000, 2000, 2000])
    # 6 semanas con precio: sin el cambio de 4 semanas
    p["corto"] = _producto("Corto", [None] * 20 + [500] * 6)
    # de 3.000 a 2.000 (-33,3%)
    p["baja"] = _producto("Baja", [3000] * 20 + [2000] * 4)
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_cuatro_semanas")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    (d / "indices.json").write_text(json.dumps(sintetico()), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8",
               CARESTIA_TARJETAS="0", CARESTIA_AHORA="2026-09-25T15:00")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d


def _leer(d, ruta):
    return (d / ruta).read_text(encoding="utf-8")


def _inline(d) -> dict:
    h = _leer(d, "graficos.html")
    m = re.search(r"const DATA = (\{.*?\});\n", h)
    return json.loads(m.group(1).replace("<\\/", "</"))


# ---------- la cuenta ----------
def _cuenta():
    """variacion_4_semanas de build_site.py (con su constante), sin correr el
    build."""
    import ast
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    piezas = [n for n in arbol.body
              if (isinstance(n, ast.FunctionDef) and n.name == "variacion_4_semanas")
              or (isinstance(n, ast.Assign) and
                  [getattr(t, "id", None) for t in n.targets] == ["SEMANAS_BLOQUE"])]
    ns = {}
    exec(compile(ast.Module(body=piezas, type_ignores=[]), "build_site.py", "exec"), ns)
    return ns["variacion_4_semanas"]


def test_cuenta_con_las_ultimas_8_semanas_con_precio():
    f = _cuenta()
    assert f([100] * 4 + [110] * 4) == pytest.approx(10.0)
    # solo cuentan las últimas 8
    assert f([5000, 1] + [100] * 4 + [110] * 4) == pytest.approx(10.0)
    # las semanas sin precio no cuentan
    assert f([None, 100, None, 100, 100, None, None, 100, 110, 110, None, 110, 110]) == \
        pytest.approx(10.0)
    assert f([100] * 8) == 0
    # sin 8 semanas con precio, o sin precio en las 4 anteriores, no hay cambio
    assert f([100] * 7) is None and f([None] * 3 + [100] * 7) is None and f([]) is None
    assert f([0] * 4 + [100] * 4) is None


def test_cuenta_en_el_resumen_de_los_indices(sitio):
    """Promedio de las últimas 4 semanas con precio contra el de las 4
    anteriores, sin redondear, como la variación semanal."""
    r = _inline(sitio)["indices"]
    assert r["asado"]["delta4"] == pytest.approx(20.0)
    assert r["asado"]["delta"] == 0
    assert r["ensalada"]["delta4"] is None and r["ensalada"]["delta"] is not None
    assert r["fruta"]["delta4"] == pytest.approx(-10.0)
    assert r["desayuno"]["delta4"] == 0


def test_resumen_json_no_cambia(sitio):
    """resumen.json no lleva el cambio de 4 semanas: lo calcula el sitio."""
    resumen = json.loads(_leer(sitio, "resumen.json"))
    for code in CODES:
        assert set(resumen["indices"][code]) == {
            "nombre", "subtitulo", "costo_pesos_hoy", "veredicto", "percentil",
            "vs_promedio_pct", "variacion_semanal_pct", "semanas_historia",
            "percentil_temporada", "anios_temporada", "base_veredicto"}, code


# ---------- portada ----------
def _titem(h, code):
    return re.search(rf'<a class="titem" href="/graficos.html#{code}">(.*?)</a>', h).group(1)


def test_cinta_con_la_semana_y_las_4_semanas(sitio):
    h = _leer(sitio, "index.html")
    asado = _titem(h, "asado")
    assert asado.endswith(
        '<span class="tv"><span class="td"><i class="f">=</i>0,0%</span> <small>sem.</small></span>'
        '<span class="tv"><span class="td"><i class="f">▲</i><span class="v-sube">20,0%</span>'
        '</span> <small>4 semanas</small></span>')
    assert ('<span class="td"><i class="f">▼</i><span class="v-baja">10,0%</span></span> '
            '<small>4 semanas</small>') in _titem(h, "fruta")
    # sin 8 semanas con precio no va (ni un "·" con su etiqueta)
    ensalada = _titem(h, "ensalada")
    assert "<small>sem.</small>" in ensalada and "4 semanas" not in ensalada
    # la segunda vuelta, igual y oculta
    assert h.count("<small>4 semanas</small></span></a>") == 2 * 3


def _tarjeta(h, code):
    return re.search(rf'<a class="icard" href="/graficos.html#{code}">(.*?)</a>', h, re.S).group(1)


def test_tarjetas_con_la_semana_y_las_4_semanas(sitio):
    h = _leer(sitio, "index.html")
    asado = _tarjeta(h, "asado")
    assert ('<div class="ic-pie"><span><i class="f">=</i> 0,0% esta semana</span>'
            '<span><i class="f">▲</i> <span class="v-sube">20,0%</span> 4 semanas</span>'
            '<span>percentil 50 en su historia</span>') in asado
    # en el celular, una sola línea con cada variación y su etiqueta
    assert ('<div class="ic-m"><span class="nw"><i class="f">=</i> 0,0% esta semana</span>, '
            '<span class="nw"><i class="f">▲</i> <span class="v-sube">20,0%</span> 4 semanas</span>, '
            'percentil 50 en su historia</div>') in asado
    assert '<span><i class="f">▼</i> <span class="v-baja">10,0%</span> 4 semanas</span>' in _tarjeta(h, "fruta")
    ensalada = _tarjeta(h, "ensalada")
    assert "esta semana" in ensalada and "4 semanas" not in ensalada


def _fila(h, slug):
    return re.search(rf'<a class="fila" href="/productos/{slug}.html"([^>]*)>(.*?)</a>', h)


def test_tabla_con_la_columna_de_4_semanas(sitio):
    h = _leer(sitio, "index.html")
    # la columna va al lado de "1 semana" y se ordena como las demás
    cabecera = re.findall(r'data-k="(\w)" aria-pressed="\w+">([^<]+) <span', h)
    assert cabecera[2:4] == [("w", "1 semana"), ("m", "4 semanas")]
    assert "m: -1" in h and "m: '4 semanas'" in h
    huecos = _fila(h, "huecos")
    assert 'data-w="0.0" data-m="100.0"' in huecos.group(1)
    assert ('<span class="c-v c-w"><i class="f">=</i> 0,0%</span>'
            '<span class="c-v c-m"><i class="f">▲</i> <span class="v-sube">100,0%</span></span>'
            ) in huecos.group(2)
    baja = _fila(h, "baja")
    assert 'data-m="-33.3"' in baja.group(1)
    assert '<span class="c-v c-m"><i class="f">▼</i> <span class="v-baja">33,3%</span></span>' in baja.group(2)
    # sin 8 semanas con precio: el marcador de dato faltante, sin data-m
    # (al ordenar va al final) y, en el celular, la celda no se muestra
    corto = _fila(h, "corto")
    assert "data-m=" not in corto.group(1)
    assert '<span class="c-v c-m">·</span>' in corto.group(2)
    assert ".fila:not([data-m]) .c-m { display:none; }" in h
    # en el celular no hay cabecera: la etiqueta la pone el CSS, una vez
    assert '.c-m::after { content:" 4 semanas";' in h
    assert not any("4 semanas" in f for f in re.findall(r'<a class="fila".*?</a>', h))


# ---------- ficha ----------
def _orow(d, slug):
    m = re.search(r'<div class="orow">\n(.*?)\n    </div>', _leer(d, f"productos/{slug}.html"), re.S)
    return m.group(1)


def test_ficha_con_la_semana_y_las_4_semanas(sitio):
    assert _orow(sitio, "huecos").endswith(
        '<div class="odelta"><i class="f">▲</i>0,0% <small>sem.</small></div>\n'
        '      <div class="odelta"><i class="f">▲</i><span class="v-sube">100,0%</span> '
        '<small>4 semanas</small></div>')
    assert ('<div class="odelta"><i class="f">▼</i><span class="v-baja">33,3%</span> '
            '<small>4 semanas</small></div>') in _orow(sitio, "baja")
    corto = _orow(sitio, "corto")
    assert "<small>sem.</small>" in corto and "4 semanas" not in corto


# ---------- /graficos.html ----------
def test_graficos_con_la_semana_y_las_4_semanas(sitio):
    g = _leer(sitio, "graficos.html")
    # la cifra del índice: el bloque de 4 semanas al lado del semanal, oculto
    # sin dato
    assert ('<div class="odelta"><span id="odelta"></span> <small>sem.</small></div>\n'
            '          <div class="odelta" id="odelta4-caja"><span id="odelta4"></span> '
            '<small>4 semanas</small></div>') in g
    assert "const cuatroSemanas = d => d.delta4;" in g
    assert "document.getElementById('odelta4').innerHTML = fmtDelta(d4);" in g
    assert "document.getElementById('odelta4-caja').hidden = d4 == null;" in g
    # la cinta: las dos cifras con su etiqueta; sin dato, solo la semanal
    assert "'</span> <small>sem.</small></span>' + (d4 == null ? '' :" in g
    assert "'<span class=\"tv\"><span class=\"td\">' + fmtDelta(d4) +" in g
    assert "'</span> <small>4 semanas</small></span>');" in g


def test_sin_senal_ni_puntos_sueltos(sitio):
    """Reglas de texto del pedido: la etiqueta es "4 semanas", sin "señal" y
    sin un "·" de dato faltante con su etiqueta al lado."""
    for ruta in ["index.html", "graficos.html", "productos/huecos.html",
                 "productos/corto.html"]:
        h = _leer(sitio, ruta)
        assert "señal" not in h.lower(), ruta
        assert not re.search(r"·\s*(?:</span>\s*)?<small>", h), ruta

"""Datos a demanda, tokens y tipografía del sitio. Sin red: build_site.py corre
en un directorio temporal con un indices.json sintético del tamaño del real
(4 índices semanales desde 2008 con velas completas y 125 productos).

Verifica que /graficos.html (la app que antes era la portada) lleve inline
solo el primer pantallazo, que la portada y /graficos.html queden bajo 200 KB,
que datos/ reproduzca indices.json sin pérdida, el formato de
datos/catalogo.json, que el workflow publique datos/ y graficos.html y que
todas las páginas compartan los mismos tokens y la misma llamada a Google
Fonts."""
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

FIN = datetime.date(2026, 9, 21)   # lunes
LIMITE_PORTADA = 200_000           # bytes, sin comprimir


def _semanas(ini: datetime.date) -> list:
    n = (FIN - ini).days // 7 + 1
    return [(ini + datetime.timedelta(weeks=i)).isoformat() for i in range(n)]


def indices_realista() -> dict:
    out = {"generado": "2026-09-26", "indices": {}, "productos": {}, "descartes": []}
    inicios = [datetime.date(2008, 1, 7), datetime.date(2008, 1, 7),
               datetime.date(2009, 3, 2), datetime.date(2012, 6, 4)]
    for k, (code, meta) in enumerate(BASKETS.items()):
        fechas = _semanas(inicios[k])
        real, nominal, velas = [], [], []
        for i, t in enumerate(fechas):
            if code == "fruta" and 300 <= i < 306:       # hueco de 6 semanas
                continue
            v = 30000 + 13 * i + 997 * ((i * 7 + k) % 23)
            real.append({"time": t, "value": v})
            nominal.append({"time": t, "value": v * 6 // 10})
            op = real[-2]["value"] if len(real) > 1 else v
            velas.append({"time": t, "open": op, "high": max(op, v) + 1234,
                          "low": min(op, v) - 987, "close": v})
        out["indices"][code] = {
            "nombre": meta["nombre"], "subtitulo": meta["subtitulo"],
            "fecha": "21-09-2026", "costo_nominal": nominal[-1]["value"],
            "costo_real": real[-1]["value"], "percentil": 71, "zscore": 0.4,
            "vs_promedio": 12, "veredicto": "CARO", "color": "#e0552f",
            "n": len(real),
            "componentes": [{"label": lab, "qty": qty, "unidad": uni,
                             "odepa_unit": "$/kg", "factor": 1.0, "mismatch": False,
                             "precio_ult": 5000, "aporte": 5000}
                            for (lab, _m, qty, uni) in meta["items"]],
            "estacionalidad": {"factores": {str(m): 1 + (m % 5 - 2) / 100
                                            for m in range(1, 13)},
                               "mes_barato": 3, "mes_caro": 9, "amplitud": 4},
            "velas": velas, "nominal": nominal, "real": real,
        }
    grupos = ["Carne de Vacuno", "Frutas", "Hortalizas", "Lácteos - Huevos - Margarinas"]
    for i in range(125):
        ini = datetime.date(2008, 1, 7) + datetime.timedelta(weeks=(i % 5) * 40)
        v = [10000 + 37 * j + 211 * (i % 9) for j in range(len(_semanas(ini)))]
        if i % 4 == 1:                                   # estacional
            v = [None if 20 <= j % 52 < 34 else x for j, x in enumerate(v)]
            v[-1] = 12345
        out["productos"][f"producto_{i:03d}"] = {
            "label": f"Producto {i:03d}", "unidad": ["kg", "un", "l"][i % 3],
            "grupo": grupos[i % 4], "t0": ini.isoformat(), "v": v}
    return out


@pytest.fixture(scope="module")
def sitio(tmp_path_factory):
    d = tmp_path_factory.mktemp("build_datos")
    shutil.copytree(os.path.join(RAIZ, "textos"), d / "textos")
    data = indices_realista()
    (d / "indices.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=RAIZ, PYTHONIOENCODING="utf-8")
    env.pop("CARESTIA_BORRADOR", None)
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "build_site.py")],
                       cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d, data


def _json(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def _inline(d) -> dict:
    h = (d / "graficos.html").read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\n", h)
    return json.loads(m.group(1).replace("<\\/", "</"))


def expandir(c: dict) -> dict:
    """La misma expansión que hace la portada en el navegador."""
    base = datetime.date.fromisoformat(c["t0"])
    t = [(base + datetime.timedelta(weeks=i)).isoformat()
         for i in range(max(len(c["real"]), len(c["nominal"]), len(c["velas"])))]
    return {
        "real": [{"time": t[i], "value": v} for i, v in enumerate(c["real"]) if v is not None],
        "nominal": [{"time": t[i], "value": v} for i, v in enumerate(c["nominal"]) if v is not None],
        "velas": [{"time": t[i], "open": x[0], "high": x[1], "low": x[2], "close": x[3]}
                  for i, x in enumerate(c["velas"]) if x is not None],
    }


# ---------- portada y /graficos.html livianos ----------
def test_portada_y_graficos_bajo_200_kb_con_datos_del_tamano_real(sitio):
    d, _data = sitio
    # el sintético pesa lo que el real: sin partir los datos, no cabrían
    assert os.path.getsize(d / "indices.json") > 1_000_000
    assert os.path.getsize(d / "index.html") < LIMITE_PORTADA
    assert os.path.getsize(d / "graficos.html") < LIMITE_PORTADA


def test_portada_sin_datos_inline_ni_motor_de_graficos(sitio):
    d, _data = sitio
    h = (d / "index.html").read_text(encoding="utf-8")
    assert "const DATA" not in h
    assert "lightweight-charts" not in h
    # las 125 filas van en el HTML estático (todas con precio esta semana)
    assert h.count('<a class="fila" href="/productos/') == 125


def test_graficos_lleva_inline_solo_el_primer_pantallazo(sitio):
    d, data = sitio
    inline = _inline(d)
    codes = list(data["indices"])
    assert list(inline["indices"]) == codes
    assert list(inline["series"]) == [codes[0]]        # solo el índice inicial
    for code, r in inline["indices"].items():
        assert not {"real", "nominal", "velas"} & set(r)
        real = data["indices"][code]["real"]
        assert r["delta"] == (real[-1]["value"] / real[-2]["value"] - 1) * 100
        assert r["costo_real"] == data["indices"][code]["costo_real"]
    # productos sin series, con la clave de los links de canasta
    assert set(inline["productos"]) == set(data["productos"])
    for p in inline["productos"].values():
        assert set(p) == {"label", "grupo", "unidad", "slug"}
    assert inline["rango"] == [2008, 2026]
    assert "descartes" not in inline


def test_serie_inline_identica_a_indices_json(sitio):
    d, data = sitio
    code = next(iter(data["indices"]))
    assert expandir(_inline(d)["series"][code]) == \
        {k: data["indices"][code][k] for k in ("real", "nominal", "velas")}


# ---------- datos/ ----------
def test_datos_indices_reproducen_indices_json(sitio):
    d, data = sitio
    for code, ind in data["indices"].items():
        j = _json(d / "datos" / "indices" / f"{code}.json")
        assert expandir(j["serie"]) == {k: ind[k] for k in ("real", "nominal", "velas")}
        sin_series = {k: v for k, v in ind.items() if k not in ("real", "nominal", "velas")}
        assert {k: v for k, v in j.items() if k != "serie"} == sin_series
    # la fruta tiene un hueco de 6 semanas: viaja como null y no se pierde
    assert _json(d / "datos" / "indices" / "fruta.json")["serie"]["real"][300:306] == [None] * 6


def test_datos_productos_uno_por_producto_con_el_slug_de_su_ficha(sitio):
    d, data = sitio
    inline = _inline(d)
    archivos = os.listdir(d / "datos" / "productos")
    assert len(archivos) == len(data["productos"])
    for clave, p in data["productos"].items():
        slug = inline["productos"][clave]["slug"]
        assert _json(d / "datos" / "productos" / f"{slug}.json") == p
        assert (d / "productos" / f"{slug}.html").exists()


def test_catalogo(sitio):
    d, data = sitio
    cat = _json(d / "datos" / "catalogo.json")
    assert cat["semana"] == FIN.isoformat()
    assert len(cat["productos"]) == len(data["productos"])
    campos = {"slug", "clave", "nombre", "grupo", "unidad", "semana", "precio_pesos_hoy",
              "variacion_1s_pct", "variacion_13s_pct", "variacion_52s_pct",
              "percentil", "ultimas_52"}
    for f in cat["productos"]:
        assert set(f) == campos
        assert len(f["ultimas_52"]) <= 52 and f["ultimas_52"][-1] == f["precio_pesos_hoy"]
    f = next(x for x in cat["productos"] if x["clave"] == "producto_000")
    v = data["productos"]["producto_000"]["v"]
    assert f["nombre"] == "Producto 000" and f["grupo"] == "Carne de Vacuno"
    assert f["precio_pesos_hoy"] == v[-1] and f["ultimas_52"] == v[-52:]
    assert f["variacion_1s_pct"] == round((v[-1] / v[-2] - 1) * 100, 1)
    assert f["variacion_13s_pct"] == round((v[-1] / v[-14] - 1) * 100, 1)
    assert f["variacion_52s_pct"] == round((v[-1] / v[-53] - 1) * 100, 1)
    assert f["percentil"] == 100                         # serie creciente
    # grupo con el nombre para mostrar; estacional: null donde no hubo precio
    lac = next(x for x in cat["productos"] if x["clave"] == "producto_003")
    assert lac["grupo"] == "Lácteos, huevos y margarinas"
    est = next(x for x in cat["productos"] if x["clave"] == "producto_001")
    assert None in est["ultimas_52"]


def test_workflow_publica_datos():
    with open(os.path.join(RAIZ, ".github", "workflows", "actualizar.yml"),
              encoding="utf-8") as fh:
        wf = fh.read()
    assert "cp -r datos public/datos" in wf
    assert "cp indices.json public/indices.json" in wf   # se sigue publicando
    assert "cp graficos.html public/graficos.html" in wf


# ---------- tokens y tipografía ----------
def _paginas(d):
    return [d / "index.html", d / "graficos.html", d / "productos" / "producto-000.html",
            d / "productos" / "index.html", d / "metodologia.html", d / "404.html"]


def test_una_sola_llamada_a_google_fonts_igual_en_todas_las_paginas(sitio):
    d, _data = sitio
    urls = set()
    for p in _paginas(d):
        h = p.read_text(encoding="utf-8")
        encontradas = re.findall(r'https://fonts\.googleapis\.com/css2\?[^"]+', h)
        assert len(encontradas) == 1, p
        urls.add(encontradas[0])
    assert urls == {"https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600"
                    "&family=IBM+Plex+Sans:wght@400;500;600"
                    "&family=Space+Grotesk:wght@700&display=swap"}


def test_tokens_en_un_solo_lugar_y_brasa_solo_en_su_token(sitio):
    d, _data = sitio
    for p in _paginas(d):
        h = p.read_text(encoding="utf-8")
        assert h.count(":root {") == 1, p
        for token in ["--bg:#0f0f0e", "--panel:#171716", "--line:#2b2a27",
                      "--bone:#e4dacc", "--ash:#a39e95", "--dim:#86817a",
                      "--ember:#e8743b", "--verde:#5bbf7a", "--ambar:#e0a83c",
                      "--rojo:#e0552f"]:
            assert token in h, (p, token)
        # la brasa se escribe una sola vez (su token); el resto la usa por var()
        assert h.count("#e8743b") == 1, p
        # ni la paleta anterior ni los azules de Comparar
        for viejo in ["#17120e", "#8b8276", "#5a5348", "#1f1913", "#6ea8dc",
                      "#58c5c0", "#9a8ec4", "#8f9bb3", '"IBM Plex Mono",monospace']:
            assert viejo not in h, (p, viejo)


def test_comparar_cuatro_tonos_por_orden_de_seleccion_y_locale(sitio):
    d, _data = sitio
    h = (d / "graficos.html").read_text(encoding="utf-8")
    assert "--cmp1:#f28cc0; --cmp2:#b04fb5; --cmp3:#f4f1ea; --cmp4:#f2d74e;" in h
    assert "--cmp5" not in h
    for viejo in ["#717c16", "#b897f0", "#d1e25a", "#9977e4"]:   # paleta de 8 anterior
        assert viejo not in h
    # estilo por puesto de selección (no por posición en el catálogo) y
    # repetición punteada del 5º al 8º
    assert "PKEYS.indexOf(k) % PALETTE.length" not in h
    assert "LightweightCharts.LineStyle.Dotted" in h
    assert "const PMAX = PALETTE.length * 2;" in h
    # fechas de los gráficos en es-CL, en la portada y en las fichas
    assert "localization: Object.assign({ locale: 'es-CL' }" in h
    ficha = (d / "productos" / "producto-000.html").read_text(encoding="utf-8")
    assert "locale: 'es-CL'" in ficha

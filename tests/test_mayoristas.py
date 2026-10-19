"""mayoristas.py sin red: las unidades y sus kilos, la semana W-MON y los slugs
iguales a los de indices.py, la limpieza, la tabla de equivalencias y la
salida completa sobre tests/muestra_mayoristas.csv, 31 filas reales de los CSV
de ODEPA (precios mayoristas, CC BY 4.0): tomate en dos semanas y una fila de
otra región, palta que ya viene por kilo, arándano en canastillos de 125
gramos, lechuga solo por unidades, cebolla en malla y en paquete, betarraga
por unidad, una naranja de 2012 con el precio de un bins rotulado por kilo y
un ají de 2025 con precio cero.

También fija que nada se publica todavía: ni build_site.py ni los workflows
usan mayoristas.py y datos/mayoristas.json no entra al repo (el deploy copia
datos/ entero). Cuando el dueño decida publicarlo, esta guardia se cambia."""
import glob
import json
import os
import sys

import pandas as pd
import pytest
import requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402
import mayoristas as M  # noqa: E402

MUESTRA = os.path.join(RAIZ, "tests", "muestra_mayoristas.csv")
URL_CSV = ("https://datos.odepa.gob.cl/dataset/x/resource/y/download/"
           "precio_mayorista_fruta-hortaliza_{}.csv")


def _muestra() -> bytes:
    with open(MUESTRA, "rb") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def filas():
    return M.leer_csv(_muestra())


@pytest.fixture(scope="module")
def salida(filas):
    return M.armar(filas, min_semanas=1)


# ---------------- Unidades ----------------
@pytest.mark.parametrize("unidad, kg", [
    ("$/kilo", 1.0),
    ("$/kilo (en caja de 17 kilos)", 1.0),      # ya viene por kilo: no es 17
    ("$/kilo (en bins de 450 kilos)", 1.0),
    ("$/kilo (volumen en unidades)", 1.0),
    ("$/kilo (en caja de 8 kilos )", 1.0),
    ("$/kg caja 18 Kgs. Importado", 1.0),
    ("$/envase 1 kilo", 1.0),
    ("$/malla 18 kilos", 18.0),
    ("$/caja 18 kilos granel", 18.0),
    ("$/bandeja 6 kilos empredada", 6.0),        # así viene escrito en ODEPA
    ("$/bins (400 kilos)", 400.0),
    ("$/saco 25 kilos", 25.0),
    ("$/cuna 10 kilos", 10.0),
    ("$/quintal de 25 kilos", 25.0),
    ("$/bandeja 4,5 kilos", 4.5),
    ("$/bandeja 12 canastillos 125 gramos", 1.5),
    ("$/bandeja 12 canastillos 170 gramos", 2.04),
    ("$/caja 15 unidades", None),
    ("$/caja 36 atados", None),
    ("$/docena de atados", None),
    ("$/docena de matas", None),
    ("$/unidad", None),
    ("$/cien", None),
    ("$/mil (volumen en unidades)", None),
    ("$/paquete", None),
    ("$/paquete 20 unidades (volumen en unidades)", None),
    ("$/atado 1 a 1,5 kilos", None),             # un rango no es un factor
    ("$/atado 1,5 a 2 kilos", None),
    ("$/caja 0 kilos", None),
    ("", None),
    (None, None),
])
def test_kilos_de_la_unidad(unidad, kg):
    assert M.kilos(unidad) == kg


# ---------------- Semanas ----------------
def test_semana_va_de_lunes_a_domingo_rotulada_con_su_lunes():
    dias = pd.Series(pd.date_range("2026-10-12", "2026-10-18"))   # lunes a domingo
    assert (M.lunes(dias) == pd.Timestamp("2026-10-12")).all()
    assert M.lunes(pd.Series([pd.Timestamp("2026-10-19")])).iloc[0] == pd.Timestamp("2026-10-19")


def test_semana_es_la_de_indices():
    """indices.py rotula la semana de ODEPA consumidor con su "Fecha inicio",
    un lunes, y la agrupa con resample("W-MON"): el lunes queda con su misma
    etiqueta. mayoristas.lunes da esa etiqueta a todos los días de la semana."""
    inicio = pd.Series(pd.to_datetime(["2025-12-29", "2026-01-05", "2026-10-12"]))
    de_indices = pd.Series(1.0, index=inicio).resample("W-MON").mean().dropna().index
    assert list(M.lunes(inicio)) == list(de_indices)
    jueves = inicio + pd.Timedelta(days=3)
    assert list(M.lunes(jueves)) == list(de_indices)
    grilla = pd.date_range("1994-01-03", "2026-12-28", freq="W-MON")
    assert set(M.lunes(pd.Series(pd.date_range("1994-01-03", "2026-12-31")))) <= set(grilla)


# ---------------- Slugs y equivalencias ----------------
def test_slug_igual_al_de_indices():
    nombres = list(M.EQUIVALENCIAS) + ["Betarraga", "Ají", "Bruselas (repollito)",
                                       "Fruto del paraíso", "Pera asiática"]
    for n in nombres:
        assert M.slug(n) == indices._slug(n), n


def test_equivalencias_de_las_canastas():
    """Los productos de las canastas tienen en indices.json el slug de su
    etiqueta de BASKETS (Pepino ensalada es "pepino")."""
    etiquetas = {lab for meta in indices.BASKETS.values() for (lab, *_r) in meta["items"]}
    canastas = {"Tomate": "Tomate", "Cebolla": "Cebolla", "Palta": "Palta", "Limón": "Limón",
                "Lechuga": "Lechuga", "Pepino ensalada": "Pepino", "Pimiento": "Pimiento",
                "Manzana": "Manzana", "Plátano": "Plátano", "Naranja": "Naranja",
                "Pera": "Pera", "Mandarina": "Mandarina"}
    for odepa, etiqueta in canastas.items():
        assert etiqueta in etiquetas
        assert M.EQUIVALENCIAS[odepa] == indices._slug(etiqueta), odepa
    # el resto del catálogo de indices.py lleva el slug de su nombre de ODEPA
    for odepa, s in M.EQUIVALENCIAS.items():
        if odepa not in canastas:
            assert s == indices._slug(odepa), odepa


def test_equivalencias_sin_repetir():
    assert len(set(M.EQUIVALENCIAS.values())) == len(M.EQUIVALENCIAS)


# ---------------- Lectura ----------------
def test_leer_csv_solo_santiago(filas):
    assert len(filas) == 30                          # la de Valparaíso queda fuera
    assert set(filas["mercado"].astype(str)) == {
        "Mercado Mayorista Lo Valledor de Santiago", "Vega Central Mapocho de Santiago"}
    palta = filas[filas["producto"] == "Palta"]
    assert sorted(palta["kilos"]) == [1.0, 1.0, 1.0, 10.0]
    assert filas[filas["producto"] == "Lechuga"]["kilos"].isna().all()
    assert (filas["semana"].dt.dayofweek == 0).all()


def test_leer_csv_exige_las_columnas():
    with pytest.raises(ValueError, match="Precio promedio"):
        M.leer_csv('"Fecha","ID region","Mercado","Subsector","Producto",'
                   '"Unidad de comercializacion"\n'.encode("utf-8"))


def test_numero_con_coma_decimal():
    s = M._numero(pd.Series(["17666,6666", "1.234,5", "250", "", "abc"]))
    assert s.iloc[0] == pytest.approx(17666.6666)
    assert s.iloc[1] == pytest.approx(1234.5)
    assert s.iloc[2] == 250
    assert s.iloc[3:].isna().all()


# ---------------- Limpieza ----------------
def _filas(*grupos):
    """[(lunes, [precios por kilo])] -> filas como las de leer_csv."""
    out = []
    for semana, precios in grupos:
        for p in precios:
            out.append({"producto": "Papa", "semana": pd.Timestamp(semana), "precio_kg": p})
    return pd.DataFrame(out)


def test_banda_con_la_semana_propia():
    df = _filas(("2026-10-12", [100, 110, 90, 105, 1000, 10, 25]))
    fuera = M.fuera_de_banda(df)
    assert list(df.loc[fuera, "precio_kg"]) == [1000, 10]   # 25 está dentro: 100/5 = 20


def test_banda_no_castiga_una_caida_rapida():
    """Con ventana hacia atrás, una semana entera a 20 tras semanas a 150 quedaría
    bajo la banda. Con 3 filas o más manda la semana propia."""
    df = _filas(("2026-09-28", [150, 150, 150]), ("2026-10-05", [150, 150, 150]),
                ("2026-10-12", [20, 22, 25]))
    assert not M.fuera_de_banda(df).any()


def test_banda_semana_flaca_usa_la_ventana():
    df = _filas(("2026-08-17", [100, 100]), ("2026-10-05", [100]), ("2026-10-12", [900, 100]))
    fuera = M.fuera_de_banda(df)
    # 2026-10-12: 2 filas propias; la ventana (esa semana y las 8 anteriores)
    # trae 5, mediana 100: el 900 queda fuera
    assert list(df.loc[fuera, "precio_kg"]) == [900]


def test_banda_sin_filas_suficientes_no_juzga():
    df = _filas(("2026-01-05", [100]), ("2026-10-12", [5000, 100]))
    assert not M.fuera_de_banda(df).any()


# ---------------- Salida ----------------
def test_productos_de_la_muestra(salida):
    p = salida["productos"]
    assert sorted(p) == ["aji", "arandano_(blue)", "cebolla", "naranja", "palta", "tomate"]
    assert p["tomate"]["semanas"] == [
        {"semana": "2026-10-05", "precio_kg": round(77900 / 18 / 3, 2), "obs": 3},
        {"semana": "2026-10-12", "precio_kg": round((102000 / 18 + 1350) / 5, 2), "obs": 5},
    ]
    assert p["tomate"]["en_indices"] and p["tomate"]["producto_odepa"] == "Tomate"
    assert p["tomate"]["subsector"] == "Hortalizas y tubérculos"
    # por kilo, no dividido por 17; la bandeja de 10 kilos sí se divide
    assert p["palta"]["semanas"] == [{"semana": "2026-10-12", "precio_kg": 2600.0, "obs": 4}]
    # 12 canastillos de 125 gramos = 1,5 kilos; el jueves 1 de octubre es de la semana del 28
    assert p["arandano_(blue)"]["semanas"] == [
        {"semana": "2026-09-28", "precio_kg": 10000.0, "obs": 1},
        {"semana": "2026-10-12", "precio_kg": 9750.0, "obs": 2},
    ]
    assert p["cebolla"]["semanas"] == [
        {"semana": "2026-10-12", "precio_kg": round(41000 / 17 / 3, 2), "obs": 3}]
    assert p["cebolla"]["filas_sin_factor"] == {"$/paquete 20 unidades (volumen en unidades)": 1}
    assert p["cebolla"]["filas_descartadas"] == 0


def test_descartes_de_la_muestra(salida):
    p = salida["productos"]
    # el bins rotulado por kilo (58.500 el "kilo") sale; quedan los 4 bins normales
    naranja = (35000 + 41142.8570 + 35000 + 39999.9999) / 400 / 4
    assert p["naranja"]["semanas"] == [{"semana": "2012-07-30", "precio_kg": round(naranja, 2), "obs": 4}]
    assert p["naranja"]["filas_descartadas"] == 1
    # el precio cero sale; el ají no está en indices.json y lleva su propio slug
    assert p["aji"]["semanas"] == [
        {"semana": "2024-12-30", "precio_kg": round((28000 / 25 + 16466.6666 / 15) / 2, 2), "obs": 2}]
    assert p["aji"]["filas_descartadas"] == 1
    assert p["aji"]["en_indices"] is False


def test_fuera_de_la_muestra(salida):
    fuera = {x["producto_odepa"]: x for x in salida["fuera"]}
    assert sorted(fuera) == ["Betarraga", "Lechuga"]
    assert fuera["Lechuga"] == {
        "producto_odepa": "Lechuga", "slug": "lechuga", "en_indices": True,
        "motivo": "ninguna de sus unidades declara kilos: no hay factor oficial",
        "unidades": {"$/caja 15 unidades": 1, "$/caja 18 unidades": 1}}
    assert fuera["Betarraga"]["slug"] == "betarraga"
    assert fuera["Betarraga"]["en_indices"] is False


def test_minimo_de_semanas(filas):
    s = M.armar(filas)
    assert s["productos"] == {}
    motivos = {x["producto_odepa"]: x["motivo"] for x in s["fuera"]}
    assert motivos["Tomate"] == "2 semanas con precio por kilo (el mínimo es 52)"
    assert motivos["Palta"] == "1 semana con precio por kilo (el mínimo es 52)"
    assert motivos["Lechuga"] == "ninguna de sus unidades declara kilos: no hay factor oficial"


def test_revisar_indices(tmp_path, salida):
    ruta = tmp_path / "indices.json"
    assert M.revisar_indices(salida, str(ruta)) == []           # sin indices.json, nada
    slugs = set(M.EQUIVALENCIAS.values()) - {"tuna"} | {"aji"}
    ruta.write_text(json.dumps({"productos": {s: {} for s in slugs}}), encoding="utf-8")
    avisos = M.revisar_indices(salida, str(ruta))
    assert any("Tuna -> tuna" in a for a in avisos)
    assert any(a.startswith("Ají: su slug aji") for a in avisos)
    assert len(avisos) == 2


# ---------------- Descarga ----------------
def _listado(anios, extra=()):
    recursos = [{"format": "CSV", "url": URL_CSV.format(a), "size": len(_muestra()),
                 "name": f"Precios mayoristas de fruta y hortaliza año {a}"} for a in anios]
    return {"success": True, "result": {"resources": recursos + list(extra)}}


def test_recursos():
    r = M.recursos(_listado([2026, 2024, 2025], [{"format": "PDF", "url": "x.pdf", "name": "2023"}]))
    assert [a for a, _u, _s in r] == [2024, 2025, 2026]
    with pytest.raises(ValueError, match="faltan los años"):
        M.recursos(_listado([2023, 2026]))
    with pytest.raises(ValueError, match="dos CSV"):
        M.recursos(_listado([2025, 2025]))
    with pytest.raises(ValueError, match="sin éxito"):
        M.recursos({"success": False, "error": "x"})
    with pytest.raises(ValueError, match="no trae CSV"):
        M.recursos(_listado([]))


def test_reintentos(monkeypatch):
    llamadas, esperas = [], []

    def falla(url, params=None, timeout=None):
        llamadas.append(url)
        raise requests.ConnectionError("reset")
    monkeypatch.setattr(M.requests, "get", falla)
    monkeypatch.setattr(M, "dormir", esperas.append)
    with pytest.raises(requests.ConnectionError):
        M._bajar("https://x")
    assert len(llamadas) == M.REINTENTOS
    assert esperas == [2, 4, 8]


def _sin_red(monkeypatch, anios):
    pedidos = []

    def bajar(url, params=None):
        pedidos.append(url)
        if url == M.API:
            assert params == {"id": M.DATASET}
            return json.dumps(_listado(anios)).encode("utf-8")
        return _muestra()
    monkeypatch.setattr(M, "_bajar", bajar)
    monkeypatch.setattr(M, "MIN_SEMANAS", 1)
    return pedidos


def test_main_sin_red(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _sin_red(monkeypatch, [2026])
    assert M.main([]) == 0
    with open(tmp_path / "datos" / "mayoristas.json", encoding="utf-8") as fh:
        datos = json.load(fh)
    assert datos["licencia"] == "CC BY 4.0"
    assert datos["fuente"].startswith("ODEPA")
    assert datos["url"] == "https://datos.odepa.gob.cl/dataset/precios-mayoristas-de-frutas-y-hortalizas"
    assert datos["ultimo_dia"] == "2026-10-15"
    assert datos["mercados"][0] == {"mercado": "Mercado Mayorista Lo Valledor de Santiago",
                                    "desde": "2012-07-30", "hasta": "2026-10-15"}
    assert sorted(datos["productos"]) == ["aji", "arandano_(blue)", "cebolla", "naranja",
                                          "palta", "tomate"]
    out = capsys.readouterr().out
    assert "FUERA Lechuga" in out and "6 productos, 2 fuera" in out
    # el texto de la salida sigue las reglas de CLAUDE.md
    texto = json.dumps(datos, ensure_ascii=False)
    for prohibido in ("—", "–", " · ", " vs "):
        assert prohibido not in texto


def test_cache_reusa_los_anios_cerrados(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pedidos = _sin_red(monkeypatch, [2025, 2026])
    M.main(["--cache", str(tmp_path / "csv"), "--salida", str(tmp_path / "a.json")])
    assert len([p for p in pedidos if p != M.API]) == 2
    del pedidos[:]
    M.main(["--cache", str(tmp_path / "csv"), "--salida", str(tmp_path / "b.json")])
    # 2025 sale de la caché; el año en curso se baja siempre
    assert [p for p in pedidos if p != M.API] == [URL_CSV.format(2026)]
    # con otro tamaño en el portal, 2025 se vuelve a bajar
    (tmp_path / "csv" / os.path.basename(URL_CSV.format(2025))).write_bytes(b"corto")
    del pedidos[:]
    M.main(["--cache", str(tmp_path / "csv"), "--salida", str(tmp_path / "c.json")])
    assert [p for p in pedidos if p != M.API] == [URL_CSV.format(2025), URL_CSV.format(2026)]


# ---------------- Nada se publica todavía ----------------
def test_no_se_publica():
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        assert "mayoristas" not in fh.read()
    for ruta in glob.glob(os.path.join(RAIZ, ".github", "workflows", "*.yml")):
        with open(ruta, encoding="utf-8") as fh:
            assert "mayoristas" not in fh.read(), ruta
    with open(os.path.join(RAIZ, ".gitignore"), encoding="utf-8") as fh:
        assert "datos/mayoristas.json" in fh.read().split()

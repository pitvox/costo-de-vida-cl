"""mayoristas.py sin red: lo que mide cada unidad de comercialización, la
semana W-MON y los slugs iguales a los de indices.py, la limpieza, el precio
ponderado por volumen y el simple, las series por unidad, la tabla de
equivalencias y la salida completa sobre tests/muestra_mayoristas.csv, 38 filas
reales de los CSV de ODEPA (precios mayoristas, CC BY 4.0): tomate en dos
semanas y una fila de otra región, palta que ya viene por kilo, arándano en
canastillos de 125 gramos, lechuga en cajas de 15 y 18 unidades y por cien (en
2011), cebolla en malla y en paquete de 20 unidades, betarraga por unidad, una
naranja de 2012 con el precio de un bins rotulado por kilo, un ají de 2025 con
precio cero, zapallo por kilo con el volumen en piezas, repollo por unidad y
apio por docena de matas.

También fija que nada se publica todavía: ni build_site.py ni los workflows
usan mayoristas.py, y datos/mayoristas.json y la caché de CSV no entran al
repo (el deploy copia datos/ entero). Cuando el dueño decida publicarlo, esta
guardia se cambia."""
import glob
import hashlib
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


def _semana(semana, precio, simple, obs, volumen):
    return {"semana": semana, "precio": None if precio is None else round(precio, 2),
            "precio_simple": round(simple, 2), "obs": obs,
            "volumen": None if volumen is None else round(volumen)}


# ---------------- Unidades ----------------
@pytest.mark.parametrize("unidad, esperado", [
    # por kilo: (base, kilos que cubre el precio, kilos por unidad de Volumen)
    ("$/kilo", ("kg", 1.0, 1.0)),
    ("$/kilo (en caja de 17 kilos)", ("kg", 1.0, 17.0)),   # precio por kilo, volumen en cajas
    ("$/kilo (en bins de 450 kilos)", ("kg", 1.0, 450.0)),
    ("$/kilo (en caja de 8 kilos )", ("kg", 1.0, 8.0)),
    ("$/kilo (en caja de 20 kilos) importada", ("kg", 1.0, 20.0)),
    ("$/kg caja 18 Kgs. Importado", ("kg", 1.0, 18.0)),
    ("$/kilo (volumen en unidades)", ("kg", 1.0, None)),   # el volumen cuenta piezas
    # un texto por kilo que no se entiende deja el volumen sin escala, no lo inventa
    ("$/kilo (en caja de 8 a 10 kilos)", ("kg", 1.0, None)),
    ("$/kilo (en caja de 18 kg)", ("kg", 1.0, None)),
    ("$/kilo (volumen en cajas)", ("kg", 1.0, None)),
    ("$/envase 1 kilo", ("kg", 1.0, 1.0)),
    ("$/malla 18 kilos", ("kg", 18.0, 18.0)),
    ("$/caja 18 kilos granel", ("kg", 18.0, 18.0)),
    ("$/bandeja 6 kilos empredada", ("kg", 6.0, 6.0)),     # así viene escrito en ODEPA
    ("$/bins (400 kilos)", ("kg", 400.0, 400.0)),
    ("$/saco 25 kilos", ("kg", 25.0, 25.0)),
    ("$/cuna 10 kilos", ("kg", 10.0, 10.0)),
    ("$/quintal de 25 kilos", ("kg", 25.0, 25.0)),
    ("$/bandeja 4,5 kilos", ("kg", 4.5, 4.5)),
    ("$/bandeja 12 canastillos 125 gramos", ("kg", 1.5, 1.5)),
    ("$/bandeja 12 canastillos 170 gramos", ("kg", 2.04, 2.04)),
    # por cantidad: (base, unidades que cubre el precio, unidades por unidad de Volumen)
    ("$/unidad", ("un", 1.0, 1.0)),
    ("$/caja 15 unidades", ("un", 15.0, 15.0)),            # el volumen cuenta cajas
    ("$/malla 60 unidades", ("un", 60.0, 60.0)),
    ("$/trenza 50 unidades", ("un", 50.0, 50.0)),
    ("$/paquete 20 unidades (volumen en unidades)", ("un", 20.0, 1.0)),
    ("$/cien", ("un", 100.0, 1.0)),                         # el volumen cuenta unidades
    ("$/cien (a granel)", ("un", 100.0, 1.0)),
    ("$/cien unidades (volumen en unidades)", ("un", 100.0, 1.0)),
    ("$/mil (volumen en unidades)", ("un", 1000.0, 1.0)),
    ("$/cien en rama (volumen en unidades)", ("un", 100.0, 1.0)),   # cebolla con hoja
    ("$/mil en rama", ("un", 1000.0, 1.0)),                          # ajo con tallo
    ("$/cien matas", ("un", 100.0, 1.0)),
    ("$/docena", ("un", 12.0, 12.0)),                                # el volumen cuenta docenas
    ("$/docena de matas", ("un", 12.0, 12.0)),                       # apio: una mata, una planta
    ("$/media docena de matas", ("un", 6.0, 6.0)),                   # apio en Coquimbo desde 2025
    ("$/media docena", ("un", 6.0, 6.0)),
    # sin cantidad declarada
    ("$/caja 36 atados", None),
    ("$/docena de atados", None),
    ("$/media docena de atados", None),
    ("$/paquete", None),
    ("$/docena de paquetes", None),
    ("$/caja 20 docenas", None),
    ("$/atado 1 a 1,5 kilos", None),             # un rango no es un factor
    ("$/atado 1,5 a 2 kilos", None),
    ("$/caja 0 kilos", None),
    ("$/caja 0 unidades", None),
    ("", None),
    (None, None),
])
def test_medida_de_la_unidad(unidad, esperado):
    assert M.medida(unidad) == esperado


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
    etiqueta de BASKETS (Pepino ensalada es "pepino"), y los que la canasta
    cuenta por unidad van en POR_UNIDAD."""
    items = {lab: uni for meta in indices.BASKETS.values() for (lab, _m, _q, uni) in meta["items"]}
    canastas = {"Tomate": "Tomate", "Cebolla": "Cebolla", "Palta": "Palta", "Limón": "Limón",
                "Lechuga": "Lechuga", "Pepino ensalada": "Pepino", "Pimiento": "Pimiento",
                "Manzana": "Manzana", "Plátano": "Plátano", "Naranja": "Naranja",
                "Pera": "Pera", "Mandarina": "Mandarina"}
    for odepa, etiqueta in canastas.items():
        assert etiqueta in items
        assert M.EQUIVALENCIAS[odepa] == indices._slug(etiqueta), odepa
        assert (items[etiqueta] == "un") == (M.EQUIVALENCIAS[odepa] in M.POR_UNIDAD), odepa
    # el resto del catálogo de indices.py lleva el slug de su nombre de ODEPA
    for odepa, s in M.EQUIVALENCIAS.items():
        if odepa not in canastas:
            assert s == indices._slug(odepa), odepa


def test_equivalencias_sin_repetir():
    assert len(set(M.EQUIVALENCIAS.values())) == len(M.EQUIVALENCIAS)
    assert M.POR_UNIDAD <= set(M.EQUIVALENCIAS.values())


# ---------------- Lectura ----------------
def test_leer_csv_solo_santiago(filas):
    assert len(filas) == 37                          # la de Valparaíso queda fuera
    assert set(filas["mercado"].astype(str)) == {
        "Mercado Mayorista Lo Valledor de Santiago", "Vega Central Mapocho de Santiago",
        "Vega poniente de Santiago"}
    palta = filas[filas["producto"] == "Palta"]
    assert sorted(zip(palta["por_precio"], palta["por_volumen"], palta["volumen_base"])) == [
        (1.0, 17.0, 2040.0), (1.0, 17.0, 2550.0), (1.0, 17.0, 2550.0), (10.0, 10.0, 1200.0)]
    lechuga = filas[filas["producto"] == "Lechuga"]
    assert set(lechuga["base"]) == {"un"}
    assert set(filas[filas["producto"] == "Apio"]["base"]) == {"un"}
    assert filas[filas["producto"] == "Betarraga"]["base"].iloc[0] == "un"   # sin serie: no es POR_UNIDAD
    assert (filas["semana"].dt.dayofweek == 0).all()


def test_leer_csv_exige_las_columnas():
    with pytest.raises(ValueError, match="Volumen, Precio promedio"):
        M.leer_csv('"Fecha","ID region","Mercado","Subsector","Producto",'
                   '"Unidad de comercializacion"\n'.encode("utf-8"))


def test_numero_con_coma_decimal():
    s = M._numero(pd.Series(["17666,6666", "1.234,5", "250", "", "abc"]))
    assert s.iloc[0] == pytest.approx(17666.6666)
    assert s.iloc[1] == pytest.approx(1234.5)
    assert s.iloc[2] == 250
    assert s.iloc[3:].isna().all()


# ---------------- Limpieza ----------------
def _filas(*grupos, base="kg"):
    """[(lunes, [precios por kilo])] -> filas como las de leer_csv."""
    out = []
    for semana, precios in grupos:
        for p in precios:
            out.append({"producto": "Papa", "base": base, "semana": pd.Timestamp(semana),
                        "precio_base": p})
    return pd.DataFrame(out)


def test_banda_con_la_semana_propia():
    df = _filas(("2026-10-12", [100, 110, 90, 105, 1000, 10, 25]))
    fuera = M.fuera_de_banda(df)
    assert list(df.loc[fuera, "precio_base"]) == [1000, 10]   # 25 está dentro: 100/5 = 20


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
    assert list(df.loc[fuera, "precio_base"]) == [900]


def test_banda_sin_filas_suficientes_no_juzga():
    df = _filas(("2026-01-05", [100]), ("2026-10-12", [5000, 100]))
    assert not M.fuera_de_banda(df).any()


def test_banda_separa_kilo_y_unidad():
    """El precio por unidad no se juzga contra el precio por kilo del mismo producto."""
    df = pd.concat([_filas(("2026-10-12", [1000, 1000, 1000])),
                    _filas(("2026-10-12", [50, 50, 50]), base="un")], ignore_index=True)
    assert not M.fuera_de_banda(df).any()


# ---------------- Ponderación ----------------
def test_semanal_pondera_por_lo_transado():
    ok = pd.DataFrame({"semana": pd.Timestamp("2026-10-12"),
                       "precio_base": [100.0, 200.0, 400.0], "volumen_base": [300.0, 100.0, 100.0]})
    s = M.semanal(ok).iloc[0]
    assert s["precio"] == pytest.approx((100 * 300 + 200 * 100 + 400 * 100) / 500)
    assert s["simple"] == pytest.approx(700 / 3)
    assert s["obs"] == 3 and s["volumen"] == 500


@pytest.mark.parametrize("volumen", [float("nan"), 0.0])
def test_semanal_no_pondera_una_semana_a_medias(volumen):
    """Si una fila no tiene volumen (o trae 0), ponderar el resto daría otro
    precio: esa semana queda solo con el promedio simple."""
    ok = pd.DataFrame({"semana": [pd.Timestamp("2026-10-05")] * 2 + [pd.Timestamp("2026-10-12")] * 2,
                       "precio_base": [100.0, 300.0, 100.0, 200.0],
                       "volumen_base": [100.0, 100.0, 300.0, volumen]})
    s = M.semanal(ok)
    assert s["precio"].iloc[0] == 200.0 and s["volumen"].iloc[0] == 200
    assert pd.isna(s["precio"].iloc[1]) and pd.isna(s["volumen"].iloc[1])
    assert s["simple"].iloc[1] == 150.0 and s["obs"].iloc[1] == 2


def _lotes(volumenes, mercado="Lo Valledor", unidad="$/caja 18 kilos", base="kg"):
    """[(lunes, volumen)] -> filas ok con volumen en kilos."""
    return pd.DataFrame({"producto": "Tuna", "unidad": unidad, "base": base, "mercado": mercado,
                         "semana": [pd.Timestamp(f) for f, _v in volumenes],
                         "precio_base": 100.0, "volumen_base": [v for _f, v in volumenes]})


def test_volumen_dudoso_saca_del_ponderado_un_digito_de_mas():
    """Una fila con 400 veces el volumen de su temporada no se lleva la semana:
    sale del ponderado y del volumen, pero sigue en el promedio simple."""
    ok = _lotes([("2012-07-30", 40 * 18), ("2012-08-06", 48 * 18), ("2012-08-06", 50 * 18),
                 ("2012-08-06", 19000 * 18), ("2012-08-13", 45 * 18)])
    ok.loc[1:3, "precio_base"] = [600.0, 620.0, 800.0]
    dudoso = M.volumen_dudoso(ok)
    assert list(dudoso) == [False, False, False, True, False]
    s = M.semanal(ok, dudoso).loc[pd.Timestamp("2012-08-06")]
    assert s["precio"] == pytest.approx((600 * 48 + 620 * 50) / 98)
    assert s["volumen"] == 98 * 18
    assert s["simple"] == pytest.approx(2020 / 3) and s["obs"] == 3


def test_volumen_dudoso_no_castiga_el_pico_de_la_cosecha():
    """El percentil 75 es de la temporada (4 semanas antes y después), no del
    año: un pico de cosecha de 30 veces el volumen de invierno no es un error.
    Con una ventana de todo el año, el percentil 75 sería el del invierno y la
    cosecha quedaría dudosa."""
    invierno = [(f"2012-0{m}-{d:02d}", 10.0) for m in (5, 6) for d in (1, 4, 7, 10, 13, 16)]
    cosecha = [("2012-12-03", 300.0), ("2012-12-10", 320.0), ("2012-12-17", 310.0)]
    assert not M.volumen_dudoso(_lotes(invierno + cosecha)).any()


def test_volumen_dudoso_separa_mercado_y_base():
    """Otro mercado y la serie por unidad tienen su propio percentil 75: un lote
    de 18.000 de la Vega o por unidad no se juzga contra los de 300 de Lo
    Valledor por kilo (si se juntaran, caerían como dudosos)."""
    lv = _lotes([("2012-12-03", 300.0 + i) for i in range(7)])
    otro = _lotes([("2012-12-03", 18000.0)], mercado="Vega Central")
    por_unidad = _lotes([("2012-12-03", 18000.0)], unidad="$/caja 30 unidades", base="un")
    assert not M.volumen_dudoso(pd.concat([lv, otro, por_unidad], ignore_index=True)).any()


def test_volumen_dudoso_no_castiga_la_calidad_principal():
    """Con 7 lotes chicos de las calidades bajas y 3 grandes de la Primera, los
    grandes pasan de 20 veces la mediana, pero no del percentil 75: no son
    errores. Una semana cuya única fila es dudosa queda sin ponderado."""
    ok = _lotes([("2008-11-10", 10.0)] * 7 + [("2008-11-10", 250.0)] * 3)
    assert not M.volumen_dudoso(ok).any()
    sola = _lotes([("2008-11-03", 10.0)] * 4 + [("2008-11-10", 5000.0)])
    dudoso = M.volumen_dudoso(sola)
    assert list(dudoso) == [False] * 4 + [True]
    s = M.semanal(sola, dudoso).loc[pd.Timestamp("2008-11-10")]
    assert pd.isna(s["precio"]) and pd.isna(s["volumen"]) and s["obs"] == 1


def test_volumen_incierto_del_choclo():
    """Las mallas de choclo de Lo Valledor de mayo de 2013 a diciembre de 2014
    traen el volumen en otra escala: quedan sin volumen (su semana, sin
    ponderado). Las de la Vega y las de otras fechas no cambian."""
    cab = ('"Fecha","ID region","Region","Mercado","Subsector","Producto","Variedad / Tipo",'
           '"Calidad","Unidad de comercializacion","Origen","Volumen","Precio minimo",'
           '"Precio maximo","Precio promedio"\n')
    fila = ('"{f}","13","Región Metropolitana de Santiago","{m}","Hortalizas y tubérculos",'
            '"Choclo","Dulce","Primera","$/malla 70 unidades","Región Metropolitana","{v}",'
            '"17500,0000","17500,0000","17500,0000"\n')
    lv, vega = "Mercado Mayorista Lo Valledor de Santiago", "Vega Central Mapocho de Santiago"
    csv = cab + "".join(fila.format(f=f, m=m, v=v) for f, m, v in [
        ("2013-09-02", lv, 12000), ("2013-09-03", vega, 80), ("2015-01-05", lv, 400)])
    filas = M.leer_csv(csv.encode("utf-8"))
    assert filas["volumen_base"].isna().tolist() == [True, False, False]
    assert filas["precio_base"].tolist() == [250.0, 250.0, 250.0]
    s = M.semanal(filas)
    assert pd.isna(s.loc[pd.Timestamp("2013-09-02"), "precio"])
    assert s.loc[pd.Timestamp("2013-09-02"), "simple"] == 250.0
    assert s.loc[pd.Timestamp("2015-01-05"), "precio"] == 250.0


def test_volumen_dudoso_compara_en_kilos_entre_envases():
    """Palta "en bins de 450 kilos" con 1.000 bins (450.000 kilos) en una semana
    de cajas de 17 kilos de unos 5.000 kilos por fila: cuenta cajas, no bins."""
    cajas = _lotes([("2010-08-30", 300 * 17.0), ("2010-08-30", 280 * 17.0), ("2010-08-23", 310 * 17.0)],
                   unidad="$/kilo (en caja de 17 kilos)")
    bins = _lotes([("2010-08-30", 1000 * 450.0), ("2010-08-30", 12 * 450.0)],
                  unidad="$/kilo (en bins de 450 kilos)")
    ok = pd.concat([cajas, bins], ignore_index=True)
    assert list(M.volumen_dudoso(ok)) == [False, False, False, True, False]


# ---------------- Salida ----------------
def test_series_por_kilo_de_la_muestra(salida):
    p = salida["productos"]
    assert sorted(p) == ["aji", "apio", "arandano_(blue)", "cebolla", "lechuga", "naranja",
                         "palta", "repollo", "tomate", "zapallo"]
    assert p["tomate"]["kg"]["semanas"] == [
        _semana("2026-10-05", (27000 * 550 + 25400 * 1000 + 25500 * 430) / (18 * 1980),
                77900 / 18 / 3, 3, 18 * 1980),
        _semana("2026-10-12",
                (28500 * 160 + 26500 * 340 + 24500 * 250 + 22500 * 70 + 27000 * 300)
                / (18 * 820 + 20 * 300),
                (102000 / 18 + 1350) / 5, 5, 18 * 820 + 20 * 300),
    ]
    t = p["tomate"]
    assert t["en_indices"] and t["producto_odepa"] == "Tomate" and t["unidad_indices"] == "kg"
    assert t["subsector"] == "Hortalizas y tubérculos" and "un" not in t
    # por kilo, no dividido por 17, y el volumen en cajas de 17 kilos; la
    # bandeja de 10 kilos sí se divide
    assert p["palta"]["kg"]["semanas"] == [_semana(
        "2026-10-12", (2500 * 2550 * 2 + 2200 * 2040 + 3200 * 1200) / (2550 * 2 + 2040 + 1200),
        2600.0, 4, 2550 * 2 + 2040 + 1200)]
    # 12 canastillos de 125 gramos = 1,5 kilos; el jueves 1 de octubre es de la semana del 28
    assert p["arandano_(blue)"]["kg"]["semanas"] == [
        _semana("2026-09-28", 10000.0, 10000.0, 1, 180),
        _semana("2026-10-12", (10000 * 300 + 9500 * 320) / 620, 9750.0, 2, 620),
    ]
    # zapallo: precio por kilo con el volumen en piezas; solo promedio simple
    z = p["zapallo"]["kg"]
    assert z["semanas"] == [_semana("2026-10-12", None, (1150 + 1760) / 2, 2, None)]
    assert z["filas_sin_volumen"] == 2


def test_series_por_unidad_de_la_muestra(salida):
    p = salida["productos"]
    # cebolla: por kilo (malla de 17 kilos) y por unidad (paquete de 20, volumen en unidades)
    c = p["cebolla"]
    assert c["unidad_indices"] == "un" and c["filas_sin_factor"] == {}
    assert c["kg"]["semanas"] == [_semana(
        "2026-10-12", (14000 * 2500 * 2 + 13000 * 1200) / (17 * 6200), 41000 / 17 / 3, 3, 17 * 6200)]
    assert c["un"]["semanas"] == [_semana("2026-10-12", 255.0, 255.0, 1, 10400)]
    # lechuga: cajas de 15 y 18 (el volumen cuenta cajas) y cien en 2011 (cuenta unidades)
    assert "kg" not in p["lechuga"]
    assert p["lechuga"]["un"]["semanas"] == [
        _semana("2011-06-06", (42999.46 * 96 + 35833.28 * 3.5) / 9950,
                (429.9946 + 358.3328) / 2, 2, 9950),
        _semana("2026-10-12", (8500 * 124 + 7000 * 52) / (15 * 124 + 18 * 52),
                (8500 / 15 + 7000 / 18) / 2, 2, 15 * 124 + 18 * 52),
    ]
    assert p["repollo"]["un"]["semanas"] == [
        _semana("2026-10-12", (1700 * 1060 + 1800 * 700) / 1760, 1750.0, 2, 1760)]
    # apio: docena de matas, una mata es una planta; el volumen cuenta docenas
    assert p["apio"]["un"]["semanas"] == [_semana("2026-10-12", 9500 / 12, 9500 / 12, 1, 520 * 12)]


def test_descartes_de_la_muestra(salida):
    p = salida["productos"]
    # el bins rotulado por kilo (58.500 el "kilo") sale; quedan los 4 bins normales
    bins = [(35000, 26), (41142.8570, 42), (35000, 30), (39999.9999, 18)]
    assert p["naranja"]["kg"]["semanas"] == [_semana(
        "2012-07-30", sum(pr * v for pr, v in bins) / (400 * 116),
        sum(pr for pr, _v in bins) / 400 / 4, 4, 400 * 116)]
    assert p["naranja"]["kg"]["filas_descartadas"] == 1
    # el precio cero sale; el ají no está en indices.json y lleva su propio slug
    assert p["aji"]["kg"]["semanas"] == [_semana(
        "2024-12-30", (28000 * 60 + 16466.6666 * 150) / (25 * 60 + 15 * 150),
        (28000 / 25 + 16466.6666 / 15) / 2, 2, 25 * 60 + 15 * 150)]
    assert p["aji"]["kg"]["filas_descartadas"] == 1
    assert p["aji"]["en_indices"] is False and p["aji"]["unidad_indices"] is None


def test_fuera_de_la_muestra(salida):
    fuera = {(x["producto_odepa"], x["serie"]): x for x in salida["fuera"]}
    assert sorted(fuera) == [("Apio", "kg"), ("Betarraga", "kg"), ("Lechuga", "kg"),
                             ("Repollo", "kg")]
    assert fuera[("Lechuga", "kg")] == {
        "producto_odepa": "Lechuga", "slug": "lechuga", "en_indices": True, "serie": "kg",
        "motivo": "ninguna de sus unidades declara kilos: no hay factor oficial",
        "unidades": {"$/caja 15 unidades": 1, "$/caja 18 unidades": 1, "$/cien": 2}}
    # betarraga va por unidad, pero indices.json no la lleva: no tiene serie por unidad
    assert fuera[("Betarraga", "kg")]["slug"] == "betarraga"
    assert fuera[("Betarraga", "kg")]["en_indices"] is False
    assert ("Betarraga", "un") not in fuera


def test_producto_por_unidad_sin_filas_por_unidad():
    """Un producto de POR_UNIDAD que en Santiago solo trae unidades por kilo
    (el pimiento desde 2011) no tiene serie por unidad: va a fuera con su motivo."""
    csv = ('"Fecha","ID region","Region","Mercado","Subsector","Producto","Variedad / Tipo",'
           '"Calidad","Unidad de comercializacion","Origen","Volumen","Precio minimo",'
           '"Precio maximo","Precio promedio"\n'
           '"2026-10-13","13","Región Metropolitana de Santiago","Vega Central Mapocho de Santiago",'
           '"Hortalizas y tubérculos","Pimiento","Zafiro rojo","Primera","$/caja 15 kilos",'
           '"Región de Arica y Parinacota","100","15000,0000","15000,0000","15000,0000"\n')
    s = M.armar(M.leer_csv(csv.encode("utf-8")), min_semanas=1)
    assert s["productos"]["pimiento"]["kg"]["semanas"][0]["precio"] == 1000.0
    assert "un" not in s["productos"]["pimiento"]
    fuera = {(x["producto_odepa"], x["serie"]): x for x in s["fuera"]}
    motivo = fuera[("Pimiento", "un")]["motivo"]
    assert motivo == "ninguna de sus unidades declara cuántas unidades trae: no hay factor oficial"
    for prohibido in ("—", "–", " · ", " vs "):
        assert prohibido not in motivo


def test_minimo_de_semanas(filas):
    s = M.armar(filas)
    assert s["productos"] == {}
    motivos = {(x["producto_odepa"], x["serie"]): x["motivo"] for x in s["fuera"]}
    assert motivos[("Tomate", "kg")] == "2 semanas con precio por kilo (el mínimo es 52)"
    assert motivos[("Palta", "kg")] == "1 semana con precio por kilo (el mínimo es 52)"
    assert motivos[("Cebolla", "un")] == "1 semana con precio por unidad (el mínimo es 52)"
    assert motivos[("Lechuga", "kg")] == "ninguna de sus unidades declara kilos: no hay factor oficial"


def test_revisar_indices(tmp_path, salida):
    ruta = tmp_path / "indices.json"
    assert M.revisar_indices(salida, str(ruta)) == []           # sin indices.json, nada
    prods = {s: {"unidad": "un" if s in M.POR_UNIDAD else "kg"} for s in M.EQUIVALENCIAS.values()}
    ruta.write_text(json.dumps({"productos": prods}), encoding="utf-8")
    assert M.revisar_indices(salida, str(ruta)) == []
    del prods["tuna"]
    prods["aji"] = {"unidad": "kg"}
    prods["palta"]["unidad"] = "un"
    ruta.write_text(json.dumps({"productos": prods}), encoding="utf-8")
    avisos = M.revisar_indices(salida, str(ruta))
    assert "EQUIVALENCIAS: Tuna -> tuna no está en " + str(ruta) in avisos
    assert "POR_UNIDAD: palta va en " + str(ruta) + " por un" in avisos
    assert any(a.startswith("Ají: su slug aji") for a in avisos)
    assert len(avisos) == 3


# ---------------- Descarga ----------------
def _listado(anios, extra=(), contenido=None, size=True, md5=True):
    contenido = _muestra() if contenido is None else contenido
    recursos = [{"format": "CSV", "url": URL_CSV.format(a),
                 "size": len(contenido) if size else None,
                 "hash": hashlib.md5(contenido).hexdigest() if md5 else "",
                 "name": f"Precios mayoristas de fruta y hortaliza año {a}"} for a in anios]
    return {"success": True, "result": {"resources": recursos + list(extra)}}


def test_recursos():
    r = M.recursos(_listado([2026, 2024, 2025], [{"format": "PDF", "url": "x.pdf", "name": "2023"}]))
    assert [a for a, _u, _s, _h in r] == [2024, 2025, 2026]
    assert r[0][3] == hashlib.md5(_muestra()).hexdigest()
    assert M.recursos(_listado([2026], md5=False))[0][2:] == (len(_muestra()), None)
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


def _sin_red(monkeypatch, anios, **listado):
    pedidos = []

    def bajar(url, params=None):
        pedidos.append(url)
        if url == M.API:
            assert params == {"id": M.DATASET}
            return json.dumps(_listado(anios, **listado)).encode("utf-8")
        return _muestra()
    monkeypatch.setattr(M, "_bajar", bajar)
    monkeypatch.setattr(M, "MIN_SEMANAS", 1)
    return pedidos


def test_vigente():
    c = b"precio,1"
    md5 = hashlib.md5(c).hexdigest()
    assert M.vigente(c, len(c), md5)
    assert not M.vigente(b"precio,2", len(c), md5)     # mismo tamaño, otro md5: ODEPA lo corrigió
    assert M.vigente(c, len(c), None)                  # sin md5, vale el tamaño
    assert not M.vigente(c + b"\n", len(c), None)
    assert not M.vigente(c, None, None)                # sin nada que comparar, se baja


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
                                    "desde": "2011-06-06", "hasta": "2026-10-15"}
    assert sorted(datos["productos"]) == ["aji", "apio", "arandano_(blue)", "cebolla", "lechuga",
                                          "naranja", "palta", "repollo", "tomate", "zapallo"]
    out = capsys.readouterr().out
    assert "FUERA Apio (kg)" in out and "10 productos, 4 series fuera" in out
    # el texto de la salida sigue las reglas de CLAUDE.md
    texto = json.dumps(datos, ensure_ascii=False)
    for prohibido in ("—", "–", " · ", " vs "):
        assert prohibido not in texto


def test_descarga_incremental(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    pedidos = _sin_red(monkeypatch, [2025, 2026])
    cache = tmp_path / ".cache" / "mayoristas"
    ambos = [URL_CSV.format(2025), URL_CSV.format(2026)]

    def csv_bajados():
        out = [p for p in pedidos if p != M.API]
        del pedidos[:]
        return out
    M.main(["--salida", "a.json"])
    assert csv_bajados() == ambos
    assert sorted(os.listdir(cache)) == sorted(os.path.basename(u) for u in ambos)
    # la segunda vez, 2025 sale de la caché y el año en curso se baja siempre
    M.main(["--salida", "b.json"])
    assert csv_bajados() == [URL_CSV.format(2026)]
    assert "1 año de la caché" in capsys.readouterr().out
    # --completo baja todo de nuevo
    M.main(["--completo", "--salida", "c.json"])
    assert csv_bajados() == ambos
    # si el guardado no es el que publica el portal (otro md5, aunque tenga
    # el mismo tamaño), ODEPA lo cambió: 2025 se vuelve a bajar
    guardado = cache / os.path.basename(URL_CSV.format(2025))
    guardado.write_bytes(_muestra().replace(b"Primera", b"Segunda", 1))
    assert guardado.stat().st_size == len(_muestra())
    capsys.readouterr()
    M.main(["--salida", "d.json"])
    assert csv_bajados() == ambos
    assert "2025: el archivo guardado no es el que publica el portal" in capsys.readouterr().out
    assert guardado.read_bytes() == _muestra()
    assert not list(cache.glob("*.tmp"))
    # --cache cambia la carpeta
    M.main(["--cache", "otra", "--salida", "e.json"])
    assert csv_bajados() == ambos
    assert (tmp_path / "otra" / os.path.basename(URL_CSV.format(2025))).exists()


def test_descarga_sin_size_ni_md5_baja_todo(tmp_path, monkeypatch):
    """Si el portal no informa tamaño ni md5 no hay cómo saber si el guardado
    sigue vigente: se baja de nuevo."""
    monkeypatch.chdir(tmp_path)
    pedidos = _sin_red(monkeypatch, [2025, 2026], size=False, md5=False)
    M.main(["--salida", "a.json"])
    del pedidos[:]
    M.main(["--salida", "b.json"])
    assert [p for p in pedidos if p != M.API] == [URL_CSV.format(2025), URL_CSV.format(2026)]


# ---------------- Nada se publica todavía ----------------
def test_no_se_publica():
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        assert "mayoristas" not in fh.read()
    for ruta in glob.glob(os.path.join(RAIZ, ".github", "workflows", "*.yml")):
        with open(ruta, encoding="utf-8") as fh:
            assert "mayoristas" not in fh.read(), ruta
    with open(os.path.join(RAIZ, ".gitignore"), encoding="utf-8") as fh:
        ignorados = fh.read().split()
    assert "datos/mayoristas.json" in ignorados and ".cache/" in ignorados

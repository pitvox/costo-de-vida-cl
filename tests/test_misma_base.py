"""Tests sintéticos de indices.misma_base: un producto que ODEPA informa en
dos bases a la vez (la cebolla, desde 2014, por unidad en las ferias y por
kilo en los supermercados) se calcula solo con las filas de la base de su
unidad modal, en los índices y en el catálogo. Sin red."""
import os
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402

SEMANAS = pd.date_range("2026-08-03", periods=6, freq="W-MON")
IPC = pd.Series([100.0], index=pd.to_datetime(["2026-07-01"]))


def _fila(producto, unidad, precio, fecha, punto, grupo="Hortalizas"):
    return {"ProductoBase": producto, "Unidad": unidad, "Precio promedio": precio,
            "Precio minimo": precio * 0.8, "Precio maximo": precio * 1.2,
            "Grupo": grupo, "fecha": fecha, "Punto": punto}


def cebolla(semanas=SEMANAS, ferias=4, supers=3):
    """Cada semana, 'ferias' ferias venden la cebolla a $300 la unidad y
    'supers' supermercados a $1.600 el kilo, como en ODEPA desde 2014."""
    filas = []
    for f in semanas:
        filas += [_fila("Cebolla", "$/unidad", 300.0, f, f"Sector {k} | Feria libre")
                  for k in range(ferias)]
        filas += [_fila("Cebolla", "$/kilo", 1600.0, f, f"Sector {k} | Supermercado")
                  for k in range(supers)]
    return filas


def test_deja_solo_las_filas_de_la_base_modal():
    df = pd.DataFrame([
        _fila("Cebolla", "$/unidad", 300.0, SEMANAS[0], "Norte | Feria libre"),
        _fila("Cebolla", "$/kilo", 1600.0, SEMANAS[0], "Norte | Supermercado"),
    ])
    sub = indices.misma_base(df, "$/unidad")
    assert sub["Unidad"].tolist() == ["$/unidad"]
    # y al revés, en un producto que va por kilo (la zanahoria hasta 2014)
    assert indices.misma_base(df, "$/kilo")["Unidad"].tolist() == ["$/kilo"]


def test_no_saca_lo_que_no_reconoce_ni_otros_envases_de_la_misma_base():
    unidades = ["$/litro", "$/botella 900 ml", "", None, "$/bandeja 12 unidades"]
    df = pd.DataFrame({"Unidad": unidades, "Precio promedio": [1.0] * 5})
    # '$/botella 900 ml' no se lee con certeza y una fila sin unidad no dice
    # su base: se quedan, como antes
    assert len(indices.misma_base(df, "$/litro")) == 4
    huevos = pd.DataFrame({"Unidad": ["$/bandeja 12 unidades", "$/bandeja 30 unidades"],
                           "Precio promedio": [3200.0, 5750.0]})
    # mismo 'un', distinto contenido: no es asunto de misma_base
    assert len(indices.misma_base(huevos, "$/bandeja 12 unidades")) == 2


def test_sin_columna_unidad_o_sin_modal_no_filtra():
    df = pd.DataFrame({"Precio promedio": [1.0, 2.0]})
    assert indices.misma_base(df, "$/unidad") is df
    df = pd.DataFrame({"Unidad": ["$/kilo", "$/unidad"], "Precio promedio": [1.0, 2.0]})
    assert indices.misma_base(df, "") is df


def test_precio_semanal_no_promedia_kilos_con_unidades():
    df = pd.DataFrame(cebolla())
    for col, esperado in (("Precio promedio", 300.0), ("Precio minimo", 240.0),
                          ("Precio maximo", 360.0)):
        s = indices.precio_semanal(df, "Cebolla", col)
        assert s.round(6).tolist() == [esperado] * len(SEMANAS), col


def test_el_indice_cuenta_una_cebolla_por_unidad():
    df = pd.DataFrame(cebolla())
    m, comp = indices.calcular(df, IPC, [("Cebolla", "Cebolla", 1, "un")])
    assert m["nominal"].tolist() == [300.0] * len(SEMANAS)
    # la mecha de las velas tampoco mezcla el kilo
    assert m["min_nom"].round(6).tolist() == [240.0] * len(SEMANAS)
    assert m["max_nom"].round(6).tolist() == [360.0] * len(SEMANAS)
    (c,) = comp
    assert (c["odepa_unit"], c["mismatch"], c["precio_ult"], c["aporte"]) == \
        ("$/unidad", False, 300, 300)


def test_el_indice_sigue_con_las_semanas_que_solo_traen_kilo():
    """Una semana sin ninguna fila por unidad queda sin dato y el ffill del
    índice la completa, como cualquier semana sin dato: la historia no pierde
    semanas (validar.py exige que semanas_historia avance justo)."""
    filas = cebolla()
    filas = [f for f in filas if not (f["fecha"] == SEMANAS[3] and f["Unidad"] == "$/unidad")]
    m, _ = indices.calcular(pd.DataFrame(filas), IPC, [("Cebolla", "Cebolla", 1, "un")])
    assert len(m) == len(SEMANAS)
    assert m["nominal"].tolist() == [300.0] * len(SEMANAS)


def test_el_catalogo_publica_la_cebolla_por_unidad():
    df = pd.DataFrame(cebolla())
    out = indices.series_productos(df, IPC)
    p = out["cebolla"]
    assert p["unidad"] == "un"
    assert p["v"] == [300] * len(SEMANAS)
    assert p["min"] == [240] * len(SEMANAS) and p["max"] == [360] * len(SEMANAS)
    # las filas por kilo no arman otro producto en la segunda pasada
    assert len(out) == 1


def test_los_supermercados_por_kilo_no_cuentan_para_el_minimo_de_puntos():
    # 2 ferias por unidad (encuestadas dos veces, así la unidad sigue siendo
    # la modal) y 3 supermercados por kilo: 5 puntos, pero solo 2 venden la
    # cebolla en la unidad publicada
    filas = cebolla(ferias=2, supers=3)
    filas += [f for f in filas if f["Unidad"] == "$/unidad"]
    df = pd.DataFrame(filas)
    assert indices.unidad_modal(df, "Cebolla") == "$/unidad"
    puntos = []
    out = indices.series_productos(df, IPC, puntos=puntos)
    assert "cebolla" not in out
    assert {d["puntos"] for d in puntos if d["slug"] == "cebolla"} == {2}


def test_el_resto_del_catalogo_usa_la_misma_regla():
    """La zanahoria fue por unidad hasta 2014 y por kilo después; su modal es
    el kilo. Las filas por unidad no entran a su serie por kilo."""
    filas = []
    for f in SEMANAS:
        filas += [_fila("Zanahoria", "$/kilo", 900.0, f, f"Sector {k} | Feria libre")
                  for k in range(4)]
        filas += [_fila("Zanahoria", "$/unidad", 70.0, f, f"Sector {k} | Supermercado")
                  for k in range(3)]
    p = indices.series_productos(pd.DataFrame(filas), IPC)["zanahoria"]
    assert p["unidad"] == "kg" and p["v"] == [900] * len(SEMANAS)

"""Cada producto usa solo las filas de ODEPA de la unidad que declara, sin
red. ODEPA cotiza algunos productos en dos unidades a la vez: la cebolla en
$/unidad (ferias) y en $/kilo (supermercados) desde octubre de 2014, los
huevos en bandeja de 12 y de 30 desde mayo de 2020, la zanahoria en $/unidad
hasta 2014 y el aceite en $/botella 900 ml desde julio de 2023. Promediar esas
filas mezclaba precios de cantidades distintas; estos tests fallan si un
índice o un producto del catálogo vuelve a mezclarlas.

La regla: si la unidad declara el volumen o el peso exacto del envase, la
fila entra convertida con ese número (la botella de 900 ml, por litro
dividido por 0,9); si no, queda fuera. Un número de piezas no es peso ni
volumen: la bandeja de 30 huevos no se lleva a la de 12.

Las unidades son las 18 que traen los CSV de precios al consumidor de ODEPA
2008 a 2026 en la Región Metropolitana."""
import ast
import os
import sys

import pandas as pd
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402

# las unidades de ODEPA y lo que mide su precio, (base, contenido): con la
# misma medida se promedian tal cual; con la misma base de peso o volumen, la
# fila se convierte; entre bases distintas o entre conteos distintos, no
POR_KILO = ["$/kilo", "$/envase 1 kilo", "$/bolsa 1 kilo", "$/kilo (en envase de 1 kilo)",
            "$/kilo (en saco de 5 kilos)", "$/kilo (en saco de 25 kilos)",
            "$/kilo (en saco de 50 kilos)"]
POR_LITRO = ["$/litro", "$/Caja de 1 Litro"]
MEDIDAS = {
    **{u: ("kg", 1.0) for u in POR_KILO}, **{u: ("l", 1.0) for u in POR_LITRO},
    "$/unidad": ("un", 1.0), "$/bandeja 12 unidades": ("un", 12.0),
    "$/bandeja 30 unidades": ("un", 30.0), "$/bolsa 800 grs": ("kg", 0.8),
    "$/envase 400 gramos": ("kg", 0.4), "$/pote 500 gramos": ("kg", 0.5),
    "$/pan de 250 gramos": ("kg", 0.25), "$/envase 125 gramos": ("kg", 0.125),
    "$/botella 900 ml": ("l", 0.9),
}
UNIDADES = list(MEDIDAS)

SEMANAS = pd.date_range("2025-01-06", periods=20, freq="W-MON")
IPC = pd.Series([100.0], index=pd.to_datetime(["2024-12-01"]))
# la unidad que declara cada producto es la modal: la suya va en más puntos
FERIAS = ("Oriente | Feria libre", "Centro | Feria libre", "Sur | Feria libre",
          "Norte | Feria libre")
SUPER = ("Oriente | Supermercado", "Centro | Supermercado", "Sur | Supermercado")


def filas(producto, unidad, precio, semanas=SEMANAS, puntos=FERIAS, grupo="Hortalizas"):
    """Filas ODEPA de un producto: en cada semana, una por punto de monitoreo."""
    return [{"ProductoBase": producto, "Unidad": unidad, "Grupo": grupo, "fecha": f,
             "Punto": p, "Precio promedio": float(precio),
             "Precio minimo": precio * 0.8, "Precio maximo": precio * 1.2}
            for f in semanas for p in puntos]


def test_medida_de_cada_unidad():
    assert len(UNIDADES) == 18
    for u, (base, contenido) in MEDIDAS.items():
        m = indices._medida(u)
        assert m is not None and m[0] == base and m[1] == pytest.approx(contenido), u


def test_entran_las_que_miden_lo_mismo_y_los_envases_de_peso_o_volumen():
    for declarada in UNIDADES:
        # la declarada es la modal: 3 filas suyas y 1 de cada una de las
        # otras, todas a $1.000 por su envase (mínimo $800, máximo $1.200)
        sub = pd.DataFrame([{"Unidad": u, "Precio promedio": 1000.0,
                             "Precio minimo": 800.0, "Precio maximo": 1200.0}
                            for u in [declarada] * 3 + [u for u in UNIDADES if u != declarada]])
        base, contenido = MEDIDAS[declarada]
        esperado = {u: 1000.0 * contenido / c for u, (b, c) in MEDIDAS.items()
                    if (b, c) == (base, contenido) or (b == base and b in ("kg", "l"))}
        out = indices.de_su_unidad(sub)
        assert sorted(set(out["Unidad"])) == sorted(esperado), declarada
        for _, r in out.iterrows():
            f = esperado[r["Unidad"]] / 1000.0
            assert (r["Precio promedio"], r["Precio minimo"], r["Precio maximo"]) == \
                pytest.approx((1000.0 * f, 800.0 * f, 1200.0 * f)), (declarada, r["Unidad"])


def test_botella_de_900_ml_entra_por_litro():
    """El aceite en "$/botella 900 ml" entra al precio por litro dividido por
    0,9, con su mínimo y su máximo, y sin tocar las filas que recibe."""
    rs = filas("Aceite maravilla", "$/litro", 2000, SEMANAS[:14], grupo="Abarrotes y otros")
    rs += filas("Aceite maravilla", "$/botella 900 ml", 2700, SEMANAS[12:], puntos=SUPER,
                grupo="Abarrotes y otros")
    df = pd.DataFrame(rs)
    copia = df.copy()
    # semanas 12 y 13: 4 filas por litro a $2.000 y 3 botellas a $2.700 ($3.000 el litro)
    esperado = [2000.0] * 12 + [(4 * 2000 + 3 * 3000) / 7] * 2 + [3000.0] * 6
    for col, k in (("Precio promedio", 1.0), ("Precio minimo", 0.8), ("Precio maximo", 1.2)):
        s = indices.precio_semanal(df, "Aceite maravilla", col)
        assert list(s.index) == list(SEMANAS)
        assert list(s) == pytest.approx([x * k for x in esperado]), col
    pd.testing.assert_frame_equal(df, copia)
    # el factor de la canasta es el de la unidad que declara, el litro
    assert indices.factor_precio(indices.unidad_modal(df, "Aceite maravilla"), "l") == (1.0, False)


def test_sin_unidad_entran_todas_las_filas():
    sub = pd.DataFrame({"Unidad": [""] * 4, "Precio promedio": [1.0, 2.0, 3.0, 4.0]})
    assert indices.de_su_unidad(sub).equals(sub)
    assert indices.de_su_unidad(sub.drop(columns="Unidad")).equals(sub.drop(columns="Unidad"))


# unidad y precio ODEPA de cada producto de las canastas en los datos sintéticos
CANASTA = {
    "Asado de tira": ("$/kilo", 13000), "Asado Carnicero": ("$/kilo", 10000),
    "Tomate": ("$/kilo", 1500), "Cebolla": ("$/unidad", 300), "Palta": ("$/kilo", 4000),
    "Limón": ("$/kilo", 1200), "Lechuga": ("$/unidad", 1000),
    "Pepino ensalada": ("$/unidad", 600), "Pimiento": ("$/unidad", 900),
    "Marraqueta": ("$/kilo", 2200), "Mantequilla": ("$/pan de 250 gramos", 1500),
    "Queso Gauda": ("$/envase 1 kilo", 11000),
    "Huevo color grande (primera)": ("$/bandeja 12 unidades", 3600),
    "Leche Fluida Entera": ("$/Caja de 1 Litro", 1100),
}
# la otra unidad que ODEPA trae a la vez, en otros puntos de venta
OTRA = {"Cebolla": ("$/kilo", 1000),
        "Huevo color grande (primera)": ("$/bandeja 30 unidades", 7500)}


def canasta(con_otra: bool) -> pd.DataFrame:
    rs = []
    for producto, (unidad, precio) in CANASTA.items():
        rs += filas(producto, unidad, precio)
        if con_otra and producto in OTRA:
            rs += filas(producto, *OTRA[producto], puntos=SUPER)
    return pd.DataFrame(rs)


@pytest.mark.parametrize("code, item, precio", [
    ("asado", "Cebolla", 300), ("ensalada", "Cebolla", 300),
    ("desayuno", "Huevos", 300),                   # bandeja de 12 a $3.600
])
def test_indice_no_mezcla_unidades(code, item, precio):
    items = indices.BASKETS[code]["items"]
    m, comp = indices.calcular(canasta(True), IPC, items)
    solo, comp_solo = indices.calcular(canasta(False), IPC, items)
    # la otra unidad no cambia nada: ni la serie (semanas, promedio, mínimo y
    # máximo) ni el desglose
    pd.testing.assert_frame_equal(m, solo)
    assert comp == comp_solo
    c = next(c for c in comp if c["label"] == item)
    assert c["precio_ult"] == precio and not c["mismatch"]
    assert len(m) == len(SEMANAS)
    assert m["nominal"].iloc[-1] == sum(x["aporte"] for x in comp)


def test_catalogo_no_mezcla_unidades(capsys):
    rs = canasta(True).to_dict("records")
    # zanahoria: en $/unidad hasta 2014 y en $/kilo después
    rs += filas("Zanahoria", "$/unidad", 70, SEMANAS[:8])
    rs += filas("Zanahoria", "$/kilo", 800, SEMANAS[6:], puntos=SUPER)
    # aceite: en $/litro y desde julio de 2023 en $/botella 900 ml
    rs += filas("Aceite maravilla", "$/litro", 2000, SEMANAS[:14], grupo="Abarrotes y otros")
    rs += filas("Aceite maravilla", "$/botella 900 ml", 2600, SEMANAS[14:],
                grupo="Abarrotes y otros")
    # lentejas: a granel y en saco, las dos por kilo: siguen promediándose
    rs += filas("Lentejas 6 mm", "$/kilo", 2000, grupo="Legumbres")
    rs += filas("Lentejas 6 mm", "$/kilo (en saco de 25 kilos)", 1500, puntos=SUPER,
                grupo="Legumbres")
    out = indices.series_productos(pd.DataFrame(rs), IPC)
    n = len(SEMANAS)
    assert out["cebolla"]["unidad"] == "un"
    assert out["cebolla"]["v"] == [300] * n
    assert out["cebolla"]["min"] == [240] * n and out["cebolla"]["max"] == [360] * n
    assert out["huevos"]["v"] == [300] * n
    assert out["zanahoria"]["unidad"] == "kg"
    assert out["zanahoria"]["t0"] == SEMANAS[6].strftime("%Y-%m-%d")
    assert out["zanahoria"]["v"] == [800] * (n - 6)
    # la botella de 900 ml entra por litro: $2.600 / 0,9 = $2.889, con su
    # mínimo ($2.080 / 0,9) y su máximo ($3.120 / 0,9)
    assert out["aceite_maravilla"]["unidad"] == "l"
    assert out["aceite_maravilla"]["t0"] == SEMANAS[0].strftime("%Y-%m-%d")
    assert out["aceite_maravilla"]["v"] == [2000] * 14 + [2889] * 6
    assert out["aceite_maravilla"]["min"] == [1600] * 14 + [2311] * 6
    assert out["aceite_maravilla"]["max"] == [2400] * 14 + [3467] * 6
    assert out["lentejas_6_mm"]["v"] == [round((4 * 2000 + 3 * 1500) / 7)] * n
    log = capsys.readouterr().out
    assert "OTRA UNIDAD (no entra): cebolla: 60 filas en $/kilo, 2025-01-06 a 2025-05-19" in log
    assert ("OTRA UNIDAD (no entra): huevos: 60 filas en $/bandeja 30 unidades, "
            "2025-01-06 a 2025-05-19") in log
    assert ("OTRA UNIDAD (no entra): zanahoria: 32 filas en $/unidad, "
            "2025-01-06 a 2025-02-24") in log
    assert "OTRA UNIDAD (no entra): aceite_maravilla" not in log
    assert ("OTRO ENVASE (entra convertido, precio x 1.111): aceite_maravilla: 24 filas en "
            "$/botella 900 ml, 2025-04-14 a 2025-05-19") in log
    assert "lentejas" not in log


def _llamadas(fn_nombre):
    src = open(os.path.join(RAIZ, "indices.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == fn_nombre)
    return {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(fn) if isinstance(n, ast.Call)}


def test_todo_precio_de_producto_pasa_por_de_su_unidad():
    """Los índices leen los precios solo con precio_semanal y el catálogo con
    series_productos: las dos filtran con de_su_unidad."""
    assert "de_su_unidad" in _llamadas("precio_semanal")
    assert "de_su_unidad" in _llamadas("series_productos")
    for fn in ("calcular", "_serie_canasta"):
        assert "precio_semanal" in _llamadas(fn), fn

"""Cada producto usa solo las filas de ODEPA de la unidad que declara, sin
red. ODEPA cotiza algunos productos en dos unidades a la vez: la cebolla en
$/unidad (ferias) y en $/kilo (supermercados) desde octubre de 2014, los
huevos en bandeja de 12 y de 30 desde mayo de 2020, la zanahoria en $/unidad
hasta 2014 y el aceite en $/botella 900 ml desde julio de 2023. Promediar esas
filas mezclaba precios de cantidades distintas; estos tests fallan si un
índice o un producto del catálogo vuelve a mezclarlas.

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

# las unidades de ODEPA, agrupadas por lo que mide su precio: dentro de un
# grupo se pueden promediar, entre grupos no
POR_KILO = ["$/kilo", "$/envase 1 kilo", "$/bolsa 1 kilo", "$/kilo (en envase de 1 kilo)",
            "$/kilo (en saco de 5 kilos)", "$/kilo (en saco de 25 kilos)",
            "$/kilo (en saco de 50 kilos)"]
POR_LITRO = ["$/litro", "$/Caja de 1 Litro"]
GRUPOS = [POR_KILO, POR_LITRO, ["$/unidad"], ["$/bandeja 12 unidades"],
          ["$/bandeja 30 unidades"], ["$/bolsa 800 grs"], ["$/envase 400 gramos"],
          ["$/pote 500 gramos"], ["$/pan de 250 gramos"], ["$/envase 125 gramos"],
          ["$/botella 900 ml"]]
UNIDADES = [u for g in GRUPOS for u in g]

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


def test_entran_solo_las_unidades_que_miden_lo_mismo():
    assert len(UNIDADES) == len(set(UNIDADES)) == 18
    for declarada in UNIDADES:
        # la declarada es la modal: 3 filas suyas y 1 de cada una de las otras
        sub = pd.DataFrame([{"Unidad": declarada}] * 3
                           + [{"Unidad": u} for u in UNIDADES if u != declarada])
        grupo = next(g for g in GRUPOS if declarada in g)
        assert sorted(set(indices.de_su_unidad(sub)["Unidad"])) == sorted(grupo), declarada


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
    # sin convertir la botella: la serie termina en la última semana en litros
    assert out["aceite_maravilla"]["unidad"] == "l"
    assert out["aceite_maravilla"]["v"] == [2000] * 14
    assert out["lentejas_6_mm"]["v"] == [round((4 * 2000 + 3 * 1500) / 7)] * n
    log = capsys.readouterr().out
    assert "OTRA UNIDAD (no entra): cebolla: 60 filas en $/kilo, 2025-01-06 a 2025-05-19" in log
    assert ("OTRA UNIDAD (no entra): huevos: 60 filas en $/bandeja 30 unidades, "
            "2025-01-06 a 2025-05-19") in log
    assert ("OTRA UNIDAD (no entra): zanahoria: 32 filas en $/unidad, "
            "2025-01-06 a 2025-02-24") in log
    assert ("OTRA UNIDAD (no entra): aceite_maravilla: 24 filas en $/botella 900 ml, "
            "2025-04-14 a 2025-05-19") in log
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

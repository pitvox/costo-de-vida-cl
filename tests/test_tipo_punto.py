"""Precio por tipo de punto (regla del 12-11-2026), sin red.

El precio semanal de un producto se calcula dentro de cada tipo de punto
estable (feria libre, supermercado, carnicería...) y luego como promedio
simple entre ellos, para que un cambio en la mezcla de puntos de ODEPA no se
lea como alza o baja. Tipos estables: con precio en al menos 80% de las
semanas del producto antes del 1 de marzo de 2013 y en al menos 80% desde
esa fecha (o de todas, si el producto parte después). Un tipo estable sin
precio usa su último precio hasta 4 semanas; más allá, el promedio va con
los que tienen precio."""
import ast
import os
import sys

import numpy as np
import pandas as pd
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import indices  # noqa: E402

IPC = pd.Series([100.0], index=pd.to_datetime(["2009-12-01"]))
SEMANAS = pd.date_range("2010-01-04", "2016-12-26", freq="W-MON")
FERIAS = [f"{s} | Feria libre" for s in ("Norte", "Sur", "Oriente")]


def fila(producto, unidad, fecha, punto, precio):
    return {"ProductoBase": producto, "Unidad": unidad, "Grupo": "Prueba", "fecha": fecha,
            "Punto": punto, "Precio promedio": float(precio),
            "Precio minimo": precio * 0.8, "Precio maximo": precio * 1.2}


def mezcla(producto="Manzana", unidad="$/kilo", base=1000.0, semanas=SEMANAS):
    """Antes del corte, 3 ferias y 1 supermercado; desde el corte, 3 ferias y
    4 supermercados; desde 2015, además un supermercado en línea. Cada tipo
    con su precio fijo: feria base, supermercado 1,3 veces, en línea 1,6."""
    rs = []
    for f in semanas:
        sup = ["Centro | Supermercado"]
        if f >= indices.CORTE_MUESTRA:
            sup += [f"{s} | Supermercado" for s in ("Norte", "Sur", "Oriente")]
        for p in FERIAS:
            rs.append(fila(producto, unidad, f, p, base))
        for p in sup:
            rs.append(fila(producto, unidad, f, p, base * 1.3))
        if f >= pd.Timestamp("2015-01-05"):
            rs.append(fila(producto, unidad, f, "Oriente | Supermercado en Línea", base * 1.6))
    return rs


def anterior(sub, col="Precio promedio"):
    """La serie de antes: promedio simple de las filas por fecha y luego por
    semana W-MON."""
    return sub.groupby("fecha")[col].mean().resample("W-MON").mean().dropna()


# ---------------- 1. un cambio de mezcla conocido deja la serie plana ----------------
def test_cambio_de_mezcla_deja_la_serie_plana():
    df = pd.DataFrame(mezcla())
    assert indices.tipos_estables(indices.por_tipo(df)) == ["Feria libre", "Supermercado"]
    for col, k in (("Precio promedio", 1.0), ("Precio minimo", 0.8), ("Precio maximo", 1.2)):
        s = indices.precio_semanal(df, "Manzana", col)
        assert list(s.index) == list(SEMANAS)
        assert s.to_numpy() == pytest.approx([1000 * k * (1 + 1.3) / 2] * len(SEMANAS)), col
    # la serie de antes sí se movía con la mezcla: 1 de 4 filas en supermercado
    # antes del corte, 4 de 7 después y además la en línea desde 2015
    viejo = anterior(df)
    assert viejo["2012-12-31"] == pytest.approx((3 + 1.3) * 1000 / 4)
    assert viejo["2013-03-04"] == pytest.approx((3 + 4 * 1.3) * 1000 / 7)
    assert viejo["2015-01-05"] > viejo["2013-03-04"]


def test_canasta_y_catalogo_usan_el_precio_por_tipo():
    """Los 5 productos de la canasta de fruta con el mismo cambio de mezcla:
    el índice (promedio, mínimo y máximo) y el catálogo quedan planos."""
    items = indices.BASKETS["fruta"]["items"]
    nombres = {"Manzana": "Manzana", "tano": "Plátano", "Naranja": "Naranja",
               "Pera": "Pera", "Mandarina": "Mandarina"}
    rs = []
    for (_lab, match, _qty, _uni) in items:
        rs += mezcla(nombres[match])
    df = pd.DataFrame(rs)
    m, comp = indices.calcular(df, IPC, items)
    total = sum(qty for (_l, _m, qty, _u) in items) * 1000 * 2.3 / 2
    assert m["nominal"].to_numpy() == pytest.approx([total] * len(SEMANAS))
    assert m["min_nom"].to_numpy() == pytest.approx([total * 0.8] * len(SEMANAS))
    assert m["max_nom"].to_numpy() == pytest.approx([total * 1.2] * len(SEMANAS))
    assert all(c["precio_ult"] == 1150 for c in comp)
    out = indices.series_productos(df, IPC)
    assert set(out) == {"manzana", "platano", "naranja", "pera", "mandarina"}
    for p in out.values():
        assert p["v"] == [1150] * len(SEMANAS)
        assert p["min"] == [920] * len(SEMANAS) and p["max"] == [1380] * len(SEMANAS)


# ---------------- 2. un tipo que desaparece a mitad del período ----------------
def test_tipo_que_desaparece_queda_fuera():
    """Como la cebolla: el supermercado la cotiza por unidad hasta octubre de
    2014 y por kilo después (de_su_unidad deja fuera esas filas). El
    supermercado no es estable y la serie es la de la feria en todo el
    período, también antes de 2014."""
    rs = []
    for f in SEMANAS:
        for p in FERIAS:
            rs.append(fila("Cebolla", "$/unidad", f, p, 300))
        if f < pd.Timestamp("2014-10-06"):
            rs.append(fila("Cebolla", "$/unidad", f, "Centro | Supermercado", 450))
        else:
            rs.append(fila("Cebolla", "$/kilo", f, "Centro | Supermercado", 1000))
    df = pd.DataFrame(rs)
    sub = indices.de_su_unidad(df)
    assert indices.tipos_estables(indices.por_tipo(sub)) == ["Feria libre"]
    s = indices.precio_semanal(df, "Cebolla")
    assert list(s.index) == list(SEMANAS) and (s == 300).all()
    m, comp = indices.calcular(pd.DataFrame(rs), IPC, [("Cebolla", "Cebolla", 1, "un")])
    assert (m["nominal"] == 300).all()
    assert indices.series_productos(df, IPC)["cebolla"]["v"] == [300] * len(SEMANAS)


# ---------------- 3. huecos de 3 y de 6 semanas en un tipo estable ----------------
def test_huecos_de_3_y_6_semanas():
    """Feria a $1.000 fija y supermercado a $2.000 + $10 por semana. En un
    hueco de 3 semanas el supermercado usa su último precio; en uno de 6, las
    4 primeras con su último precio y las 2 últimas solo la feria."""
    corto, largo = list(SEMANAS[300:303]), list(SEMANAS[320:326])
    rs = []
    for i, f in enumerate(SEMANAS):
        for p in FERIAS:
            rs.append(fila("Palta", "$/kilo", f, p, 1000))
        if f not in corto and f not in largo:
            rs.append(fila("Palta", "$/kilo", f, "Centro | Supermercado", 2000 + 10 * i))
    df = pd.DataFrame(rs)
    assert indices.tipos_estables(indices.por_tipo(df)) == ["Feria libre", "Supermercado"]
    s = indices.precio_semanal(df, "Palta")
    assert list(s.index) == list(SEMANAS)
    ultimo_corto, ultimo_largo = 2000 + 10 * 299, 2000 + 10 * 319
    assert s[corto].to_numpy() == pytest.approx([(1000 + ultimo_corto) / 2] * 3)
    assert s[largo[:4]].to_numpy() == pytest.approx([(1000 + ultimo_largo) / 2] * 4)
    assert s[largo[4:]].to_numpy() == pytest.approx([1000.0] * 2)
    # después del hueco vuelve el precio propio
    assert s[SEMANAS[326]] == pytest.approx((1000 + 2000 + 10 * 326) / 2)
    # los pesos de cada tipo: mitad y mitad, salvo las 2 semanas sin supermercado
    _serie, pesos = indices.combinar_tipos(indices.por_tipo(df), ["Feria libre",
                                                                  "Supermercado"])
    assert (pesos.loc[largo[4:], "Feria libre"] == 1.0).all()
    assert (pesos.drop(largo[4:])["Supermercado"] == 0.5).all()


def test_semana_sin_ningun_tipo_estable_queda_sin_precio():
    """Una semana con filas solo de un tipo que no es estable (o sin filas)
    queda sin precio, como hoy; el arrastre de 4 semanas de un tipo no crea
    semanas que no tienen precio propio de ningún tipo estable."""
    rs = []
    for f in SEMANAS[:30]:
        for p in FERIAS:
            if f != SEMANAS[10]:
                rs.append(fila("Pera", "$/kilo", f, p, 1000))
    rs.append(fila("Pera", "$/kilo", SEMANAS[10], "Oriente | Supermercado en Línea", 5000))
    s = indices.precio_semanal(pd.DataFrame(rs), "Pera")
    assert SEMANAS[10] not in s.index and len(s) == 29 and (s == 1000).all()


# ---------------- 4. un producto sin tipo de punto se comporta como hoy ----------------
@pytest.mark.parametrize("sin_columna", [False, True])
def test_sin_tipo_de_punto_como_hoy(sin_columna):
    """Varias filas por fecha y dos fechas en algunas semanas: el promedio de
    las filas por fecha y luego por semana, igual que antes."""
    rng = np.random.default_rng(7)
    rs = []
    for i, f in enumerate(SEMANAS[:60]):
        if i % 9 == 5:
            continue                                   # semanas sin filas
        fechas = [f - pd.Timedelta(days=3), f] if i % 4 == 0 else [f]
        for d in fechas:
            for _ in range(int(rng.integers(1, 5))):
                rs.append(fila("Lenteja", "$/kilo", d, "", float(rng.integers(900, 1500))))
    df = pd.DataFrame(rs)
    if sin_columna:
        df = df.drop(columns="Punto")
    for col in ("Precio promedio", "Precio minimo", "Precio maximo"):
        pd.testing.assert_series_equal(indices.precio_semanal(df, "Lenteja", col),
                                       anterior(df, col), check_names=False, check_freq=False)
    assert set(indices.tipo_punto(df)) == {indices.SIN_TIPO}


# ---------------- 5. un producto que parte después del corte ----------------
def test_producto_que_parte_despues_del_corte():
    """Desde 2016: feria en todas sus semanas, supermercado en el 80% justo,
    carnicería en el 79% y en línea en la mitad. Son estables los que tienen
    precio en al menos 80% de todas sus semanas."""
    semanas = pd.date_range("2016-01-04", periods=100, freq="W-MON")
    rs = []
    for i, f in enumerate(semanas):
        rs.append(fila("Huevo color", "$/bandeja 12 unidades", f, "Norte | Feria libre", 3000))
        if i % 5 != 4:                                              # 80 de 100
            rs.append(fila("Huevo color", "$/bandeja 12 unidades", f, "Sur | Supermercado", 3600))
        if i >= 21:                                                 # 79 de 100
            rs.append(fila("Huevo color", "$/bandeja 12 unidades", f, "Sur | Carnicería", 9000))
        if i % 2:
            rs.append(fila("Huevo color", "$/bandeja 12 unidades", f,
                           "Sur | Supermercado en Línea", 9000))
    df = pd.DataFrame(rs)
    assert indices.tipos_estables(indices.por_tipo(df)) == ["Feria libre", "Supermercado"]
    s = indices.precio_semanal(df, "Huevo color")
    assert s.to_numpy() == pytest.approx([3300.0] * 100)


def test_estable_antes_y_desde_el_corte():
    """Con semanas a los dos lados del corte, el tipo tiene que llegar al 80%
    en los dos: un tipo que cubre casi todo el período antes pero poco
    después no entra, aunque en el total pase del 80%."""
    rs = []
    for i, f in enumerate(SEMANAS):
        rs.append(fila("Tomate", "$/kilo", f, "Norte | Feria libre", 1000))
        if f < indices.CORTE_MUESTRA or i % 4 == 0:
            rs.append(fila("Tomate", "$/kilo", f, "Sur | Supermercado", 2000))
    df = pd.DataFrame(rs)
    hay = indices.por_tipo(df).notna().mean()
    assert hay["Supermercado"] > 0.5
    assert indices.tipos_estables(indices.por_tipo(df)) == ["Feria libre"]


def test_ningun_tipo_cumple_entra_el_de_mas_semanas():
    """Si ningún tipo llega al 80%, el tipo con más semanas con precio."""
    semanas = pd.date_range("2016-01-04", periods=20, freq="W-MON")
    rs = [fila("Pepino", "$/unidad", f, "Norte | Feria libre", 400) for f in semanas[:12]]
    rs += [fila("Pepino", "$/unidad", f, "Sur | Supermercado", 600) for f in semanas[9:]]
    df = pd.DataFrame(rs)
    assert indices.tipos_estables(indices.por_tipo(df)) == ["Feria libre"]
    s = indices.precio_semanal(df, "Pepino")
    assert list(s.index) == list(semanas[:12]) and (s == 400).all()
    # empate: el primero por nombre
    rs = [fila("Pepino", "$/unidad", f, "Sur | Supermercado", 600) for f in semanas[:10]]
    rs += [fila("Pepino", "$/unidad", f, "Norte | Feria libre", 400) for f in semanas[10:]]
    assert indices.tipos_estables(indices.por_tipo(pd.DataFrame(rs))) == ["Feria libre"]


# ---------------- una sola función, en indices.py ----------------
def _definidas(archivo):
    src = open(os.path.join(RAIZ, archivo), encoding="utf-8").read()
    return {n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}, src


def test_diagnostico_importa_la_regla_de_indices():
    """diagnostico_composicion.py usa la regla de indices.py, no una copia."""
    definidas, src = _definidas("diagnostico_composicion.py")
    importadas = set()
    for n in ast.parse(src).body:
        if isinstance(n, ast.ImportFrom) and n.module == "indices":
            importadas |= {a.name for a in n.names}
    regla = {"tipo_punto", "por_tipo", "tipos_estables", "combinar_tipos", "precio_semanal"}
    assert regla <= importadas
    assert not (regla & definidas)
    assert "estratificada" not in definidas and "tipos_comunes" not in definidas

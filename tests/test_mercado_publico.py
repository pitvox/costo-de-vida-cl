"""mercado_publico.py sin red: filtros de la línea de orden de compra, producto
por categoría y texto, preparaciones que no entran, macrozona, limpieza por
mediana, agregación con mínimos de líneas, compradores y proveedores, y que
ninguna salida trae códigos de comprador o proveedor. También fija que el
piloto no se publica: build_site.py no lo usa y la salida no puede ir a datos/."""
import csv
import datetime
import io
import os
import sys
import zipfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import mercado_publico as MP  # noqa: E402

ENC = ["ID", "Codigo", "Estado", "RegionUnidadCompra", "CodigoOrganismoPublico",
       "CodigoProveedor", "NombreProveedor", "codigoProductoONU", "NombreroductoGenerico",
       "EspecificacionComprador", "EspecificacionProveedor", "cantidad", "UnidadMedida",
       "monedaItem", "precioNeto"]


def fila(estado="Aceptada", region="Región Metropolitana de Santiago", org="O1",
         prov="P1", onu="50401500", gen="Verduras frescas", esp="papa blanca",
         unidad="kilogramo", moneda="CLP", precio="1100"):
    return ["1", "OC-1", estado, region, org, prov, "Proveedor de prueba", onu, gen,
            esp, "NA", "10", unidad, moneda, precio]


def test_filtros_y_producto():
    filas = [ENC,
             fila(),                                            # entra: papa RM
             fila(estado="Enviada a proveedor"),                # estado fuera
             fila(estado="Recepción Conforme", precio="1.200,5"),  # con tilde y decimal
             fila(moneda="USD"),                                # moneda fuera
             fila(unidad="Unidad"),                             # no es por kilo
             fila(onu="44121600"),                              # no es alimento
             fila(precio="0"),                                  # precio cero
             fila(gen="Carne de ave o carne fresca", esp="pollo asado entero"),  # preparación
             fila(gen="Carne de ave o carne fresca", esp="asado de tira; corte\nvacuno"),
             fila(gen="Fruta fresca", esp="papayas"),           # no calza con nada
             fila(gen="Pan fresco", esp="Pan Marraqueta", region="Región de Ñuble"),
             ["corta"]]                                         # fila incompleta
    ls = MP.lineas(filas, "2026-10")
    assert [(l["producto"], l["zona"], l["precio"]) for l in ls] == [
        ("papa", "RM", 1100.0), ("papa", "RM", 1200.5), ("vacuno", "RM", 1100.0),
        ("pan", "Sur", 1100.0)]


def test_falta_columna():
    with pytest.raises(ValueError, match="faltan columnas"):
        MP.lineas([ENC[:-1], fila()[:-1]], "2026-10")


def test_leer_zip_cp1252_comillas_y_saltos(tmp_path):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
    w.writerow(ENC)
    w.writerow(fila(esp='tomate "larga vida";\n10 kilos', gen="Verduras frescas",
                    region="Región de Tarapacá  "))
    ruta = tmp_path / "2026-10.zip"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("2026-10.csv", buf.getvalue().encode("cp1252"))
    ls = MP.leer_zip(str(ruta), "2026-10")
    assert [(l["producto"], l["zona"]) for l in ls] == [("tomate", "Norte")]


def test_limpieza_por_mediana():
    ls = [{"mes": "2026-10", "producto": "papa", "zona": "RM", "precio": p,
           "organismo": "O", "proveedor": "P"} for p in (1000, 1100, 1200, 90, 9000)]
    quedan, descartadas = MP.limpiar(ls)
    assert sorted(l["precio"] for l in quedan) == [1000, 1100, 1200]
    assert descartadas == 2


def test_agregar_minimos_y_sin_codigos():
    ls = [{"mes": "2026-10", "producto": "pollo", "zona": "RM" if k < 30 else "Sur",
           "precio": 4000 + k, "organismo": f"O{k % 6}", "proveedor": f"P{k % 5}"}
          for k in range(36)]
    out = {(r["zona"]): r for r in MP.agregar(ls)}
    assert set(out) == {"Nacional", "RM", "Sur"}
    assert out["Nacional"]["lineas"] == 36 and out["Nacional"]["utilizable"] == "si"
    assert out["RM"]["lineas"] == 30 and out["RM"]["compradores"] == 6
    assert out["RM"]["proveedores"] == 5 and out["RM"]["utilizable"] == "si"
    assert out["Sur"]["lineas"] == 6 and out["Sur"]["utilizable"] == "no"
    assert out["Nacional"]["p25"] <= out["Nacional"]["mediana"] <= out["Nacional"]["p75"]
    for r in out.values():
        assert set(r) == set(MP.CAMPOS)
        assert not any(isinstance(v, str) and v.startswith(("O", "P")) and v[1:].isdigit()
                       for v in r.values())


def test_meses_no_incluye_el_mes_en_curso():
    hoy = datetime.date.today()
    ms = MP.meses(anio=hoy.year)
    assert len(ms) == hoy.month - 1 and all(a == hoy.year for a, _ in ms)
    assert MP.meses(anio=2015) == [(2015, m) for m in range(1, 13)]
    assert MP.meses(mes="2026-10") == [(2026, 10)]


def test_no_se_publica():
    with open(os.path.join(RAIZ, "build_site.py"), encoding="utf-8") as fh:
        assert "mercado_publico" not in fh.read()
    with pytest.raises(SystemExit):
        MP.main(["--mes", "2026-10", "--salida", os.path.join("datos", "x.csv")])

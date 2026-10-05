"""
armar_mapa.py - escribe mapa_productos.csv desde el borrador de abajo
====================================================================
El mapa liga cada producto del IPC (división 01, bases 2018 y 2023) con los
productos de ODEPA que lo representan. Se escribe por glosa del INE y el
código y la ponderación salen de los cuadros del INE, así que no se tipean
a mano. Lo que no aparece aquí queda sin cubrir.

Uso: python armar_mapa.py   (necesita datos_crudos/, ver descargar.py)
"""
import os

import pandas as pd

import ine

AQUI = os.path.dirname(os.path.abspath(__file__))

VACUNO = ["Abastero", "Asado Carnicero", "Asado de tira", "Asiento", "Choclillo",
          "Estomaguillo (Tapabarriga)", "Filete", "Ganso", "Huachalomo", "Lomo Liso",
          "Lomo Vetado", "Malaya", "Osobuco", "Palanca", "Plateada", "Pollo Ganso",
          "Posta Negra", "Posta Paleta", "Posta Rosada", "Punta de Ganso", "Punta paleta",
          "Punta picana", "Sobrecostilla", "Tapapecho"]
POLLO = ["Pollo Entero", "Pollo Pechuga", "Pollo Pechuga Deshuesada", "Pollo Trutro Entero"]
CERDO = ["Cerdo Costillar", "Cerdo Lomo", "Cerdo Pulpa c/hueso", "Cerdo Pulpa s/hueso",
         "Chuleta (Parrillera)", "Chuleta (centro)"]
PAVO = ["Pavo Osobuco", "Pavo Pechuga s/hueso", "Pavo Trutro Ala", "Pavo Trutro Corto"]
PAN = ["Marraqueta", "Hallulla corriente", "Hallulla especial", "Hallulla integral", "Pan amasado"]
ARROZ = ["Arroz grano ancho grado 1", "Arroz grano ancho grado 2",
         "Arroz grano largo delgado grado 2"]
HARINA = ["Harina con polvos de hornear", "Harina sin polvos de hornear"]
LEGUMBRES = ["Arvejas verdes partidas", "Garbanzos sin piel", "Lentejas 6 mm",
             "Poroto Hallado", "Poroto Negro", "Poroto Tórtola"]
FRUTAS_ESTACION = ["Arándano (blue)", "Cereza", "Chirimoya", "Ciruela", "Damasco", "Durazno",
                   "Frambuesa", "Frutilla", "Kiwi", "Mandarina", "Mango", "Melón", "Nectarín",
                   "Sandia", "Tuna", "Uva"]
VERDURAS_ESTACION = ["Alcachofa", "Apio", "Arveja Verde", "Brócoli", "Choclo", "Coliflor",
                     "Espárragos", "Haba", "Pepino ensalada", "Poroto granado", "Poroto verde",
                     "Repollo"]

# glosa del INE -> productos ODEPA (base 2023)
BASE_2023 = {
    "ARROZ": ARROZ,
    "HARINA DE TRIGO": HARINA,
    "PAN": PAN,
    "PASTAS": ["Spaghetti N°5"],
    "CARNE DE VACUNO": VACUNO,
    "CARNE DE POLLO": POLLO,
    "CARNE DE CERDO": CERDO,
    "CARNE DE PAVO": PAVO,
    "LECHE LÍQUIDA": ["Leche Fluida Entera", "Leche Fluida Descremada"],
    "LECHE EN POLVO": ["Leche en Polvo Entera", "Leche en Polvo Descremada"],
    "QUESOS": ["Queso Chanco", "Queso Gauda", "Queso Mantecoso"],
    "YOGURES Y PRODUCTOS SIMILARES": ["Yoghurt", "Yoghurt (vainilla ó frutilla)"],
    "HUEVOS": ["Huevo blanco grande (primera)", "Huevo color grande (primera)"],
    "ACEITE VEGETAL Y DE MARAVILLA": ["Aceite vegetal", "Aceite maravilla"],
    "ACEITE DE OLIVA": ["Aceite de oliva"],
    "MANTEQUILLA": ["Mantequilla con sal"],
    "MARGARINA": ["Margarina"],
    "PALTAS": ["Palta"],
    "FRUTAS DE ESTACIÓN": FRUTAS_ESTACION,
    "PLÁTANOS": ["Plátano"],
    "LIMONES": ["Limón"],
    "NARANJAS": ["Naranja"],
    "MANZANAS": ["Manzana"],
    "PERAS": ["Pera"],
    "VERDURAS DE ESTACIÓN": VERDURAS_ESTACION + ["Espinaca"],
    "TOMATES": ["Tomate"],
    "LECHUGAS": ["Lechuga"],
    "CEBOLLAS Y CEBOLLINES": ["Cebolla"],
    "ZAPALLOS": ["Zapallo"],
    "ZANAHORIAS": ["Zanahoria"],
    "PIMIENTOS MORRONES": ["Pimiento"],
    "ZAPALLOS ITALIANOS": ["Zapallo italiano"],
    "PAPAS": ["Papa"],
    "LEGUMBRES SECAS": LEGUMBRES,
    "AZÚCAR": ["Azúcar"],
}

# base 2018: misma correspondencia con las glosas de esa canasta (limón y
# palta van en hortalizas; acelga y espinaca es un producto aparte)
BASE_2018 = {
    "ARROZ": ARROZ,
    "HARINA": HARINA,
    "PAN": PAN,
    "PASTAS": ["Spaghetti N°5"],
    "CARNE DE VACUNO": VACUNO,
    "CARNE DE CERDO": CERDO,
    "CARNE DE PAVO": PAVO,
    "CARNE DE POLLO": POLLO,
    "LECHE EN POLVO": ["Leche en Polvo Entera", "Leche en Polvo Descremada"],
    "LECHE LÍQUIDA": ["Leche Fluida Entera", "Leche Fluida Descremada"],
    "YOGHURT": ["Yoghurt", "Yoghurt (vainilla ó frutilla)"],
    "QUESO": ["Queso Chanco", "Queso Gauda", "Queso Mantecoso"],
    "HUEVOS": ["Huevo blanco grande (primera)", "Huevo color grande (primera)"],
    "MANTEQUILLA": ["Mantequilla con sal"],
    "MARGARINA": ["Margarina"],
    "ACEITE VEGETAL": ["Aceite vegetal", "Aceite maravilla"],
    "MANZANA": ["Manzana"],
    "NARANJA": ["Naranja"],
    "PERA": ["Pera"],
    "PLÁTANO": ["Plátano"],
    "FRUTAS DE ESTACIÓN": FRUTAS_ESTACION,
    "ACELGA Y ESPINACA": ["Espinaca"],
    "CEBOLLA Y CEBOLLÍN": ["Cebolla"],
    "LECHUGA": ["Lechuga"],
    "LIMÓN": ["Limón"],
    "PALTA": ["Palta"],
    "PIMENTÓN Y PIMIENTO": ["Pimiento"],
    "TOMATE": ["Tomate"],
    "ZANAHORIA": ["Zanahoria"],
    "ZAPALLO": ["Zapallo"],
    "ZAPALLO ITALIANO": ["Zapallo italiano"],
    "VERDURAS DE ESTACIÓN": VERDURAS_ESTACION,
    "LEGUMBRES": LEGUMBRES,
    "PAPA": ["Papa"],
    "AZÚCAR": ["Azúcar"],
}


def armar() -> pd.DataFrame:
    filas = []
    for base, borrador in ((2018, BASE_2018), (2023, BASE_2023)):
        p = ine.productos(base).groupby("codigo")[["glosa", "ponderacion"]].first().reset_index()
        glosas = set(p["glosa"])
        faltan = sorted(set(borrador) - glosas)
        if faltan:
            raise SystemExit(f"glosas que no están en la base {base}: {faltan}")
        for _, r in p.iterrows():
            odepa = borrador.get(r["glosa"], [])
            filas.append({"base": base, "codigo": r["codigo"], "producto_ipc": r["glosa"],
                          "ponderacion": r["ponderacion"], "odepa": " | ".join(odepa)})
    return pd.DataFrame(filas)


if __name__ == "__main__":
    mapa = armar()
    ruta = os.path.join(AQUI, "mapa_productos.csv")
    mapa.to_csv(ruta, index=False)
    for base, g in mapa.groupby("base"):
        cub = g[g["odepa"] != ""]
        print(f"base {base}: {len(cub)} de {len(g)} productos con ODEPA, "
              f"{cub['ponderacion'].sum() / g['ponderacion'].sum() * 100:.1f}% del peso de alimentos")

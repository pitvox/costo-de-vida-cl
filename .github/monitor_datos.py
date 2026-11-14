"""TEMPORAL: datos para el monitor de minuta privado. No publica nada.

Modo "sitio": baja de carestia.cl las series de los insumos del almuerzo de
casino. Modo "salida": arma series mensuales (consumidor real, mayorista
nominal y el deflactor real/nominal de los índices) y las imprime en el log.
"""
import collections
import datetime
import json
import sys
import urllib.request

CLAVES = ["posta_paleta", "pollo_trutro_entero", "arroz_grano_largo_delgado_grado_2",
          "papa", "tomate", "cebolla", "aceite_vegetal", "marraqueta"]
SITIO = "https://carestia.cl"
DESDE = "2013-01"


def bajar(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": "carestia-monitor"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def candidatos(clave, cat):
    c = [clave.replace("_", "-"), clave]

    def walk(o):
        if isinstance(o, dict):
            if clave in [v for v in o.values() if isinstance(v, str)]:
                for f in ("slug", "s", "ficha", "url", "j"):
                    v = o.get(f)
                    if isinstance(v, str):
                        c.append(v.rsplit("/", 1)[-1].replace(".html", "").replace(".json", ""))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cat)
    vistos = []
    for x in c:
        if x and x not in vistos:
            vistos.append(x)
    return vistos


def semanas(t0, v):
    base = datetime.date.fromisoformat(t0)
    for i, x in enumerate(v):
        if x is not None:
            yield (base + datetime.timedelta(weeks=i)).isoformat(), x


def mensual(pares):
    s, n = collections.defaultdict(float), collections.defaultdict(int)
    for f, x in pares:
        m = f[:7]
        if m >= DESDE:
            s[m] += x
            n[m] += 1
    return {m: round(s[m] / n[m], 1) for m in sorted(s)}


def sitio():
    cat = json.load(open("catalogo.json", encoding="utf-8"))
    print("catalogo:", type(cat).__name__, list(cat)[:6] if isinstance(cat, dict) else len(cat))
    out = {}
    for clave in CLAVES:
        for slug in candidatos(clave, cat):
            try:
                p = bajar(f"{SITIO}/datos/productos/{slug}.json")
            except Exception as e:
                print("  no", clave, slug, e)
                continue
            print("  ok", clave, slug, "campos:", sorted(p)[:12])
            out[clave] = p
            break
        else:
            print("FALTA", clave)
    json.dump(out, open("/tmp/productos.json", "w"))


def salida():
    ind = json.load(open("indices.json", encoding="utf-8"))
    fac = collections.defaultdict(list)
    for r in ind["indices"].values():
        nom = {p["time"]: p["value"] for p in r.get("nominal", [])}
        for p in r.get("real", []):
            if nom.get(p["time"]):
                fac[p["time"][:7]].append(p["value"] / nom[p["time"]])
    defl = {m: round(sum(v) / len(v), 5) for m, v in sorted(fac.items()) if m >= DESDE}
    cons = {}
    for clave, p in json.load(open("/tmp/productos.json")).items():
        pares = list(semanas(p["t0"], p["v"]))
        cons[clave] = {"u": p.get("u"), "mensual": mensual(pares),
                       "ultima": list(pares[-1]) if pares else None}
    mm, ultimo = {}, None
    try:
        may = json.load(open("datos/mayoristas.json", encoding="utf-8"))
        ultimo = may.get("ultimo_dia")
        for slug in ("papa", "tomate", "cebolla"):
            d = may["productos"].get(slug, {})
            for unidad in ("kg", "un"):
                if unidad not in d:
                    continue
                sem = [(s["semana"], s["precio"] if s.get("precio") is not None else s.get("precio_simple"))
                       for s in d[unidad]["semanas"]]
                sem = [(f, x) for f, x in sem if x is not None]
                mm[f"{slug}_{unidad}"] = {"mensual": mensual(sem), "ultima": list(sem[-1]) if sem else None}
    except Exception as e:
        print("mayoristas: error", e)
    try:
        r = bajar("https://datos.odepa.gob.cl/api/3/action/package_show?id=precios-mayoristas-de-frutas-y-hortalizas")
        notas = (r.get("result") or {}).get("notes", "")[:1500]
    except Exception as e:
        notas = f"error: {e}"
    datos = {"ipc_mes": ind.get("ipc_mes"), "generado": ind.get("generado"), "deflactor": defl,
             "consumidor": cons, "mayorista": mm, "mayorista_ultimo_dia": ultimo,
             "notas_mayorista": notas}
    print("=== DATOS MONITOR ===")
    print(json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
    print("=== FIN DATOS ===")


if __name__ == "__main__":
    {"sitio": sitio, "salida": salida}[sys.argv[1]]()

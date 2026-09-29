"""
validar.py — compuerta pre-deploy.

Corre DESPUÉS de indices.py y ANTES de build_site.py. Compara lo recién
calculado contra el resumen.json que está publicado y termina con exit 1
(el workflow falla, no hay deploy, GitHub avisa por correo) si algo no cuadra.

resumen.json lo escribe build_site.py, que todavía no corrió en este punto del
workflow. Por eso el resumen "nuevo" se arma aquí desde indices.json con la
misma receta de build_site.generar_resumen (tests/test_validar.py verifica que
ambas coincidan campo a campo). No toca la metodología: solo lee.

Chequeos:
  a. snapshot desplegado legible (carestia.cl, respaldo pitvox.github.io);
  b. por índice: semanas_historia avanza exactamente lo que avanzó "semana";
     |variacion_semanal_pct| <= 40; costo_pesos_hoy > 0; percentil 0..100;
     veredicto en {BARATO, NORMAL, CARO};
  c. por índice: suma de aportes = costo_nominal (±1%) y ningún mismatch;
  d. catálogo: len(indices.json["productos"]) == PRODUCTOS_ESPERADOS (125).

Siempre escribe un resumen en $GITHUB_STEP_SUMMARY (o stdout si no existe).
Solo usa json/requests (+ stdlib).
"""
import datetime
import json
import os
import sys

import requests

INDICES = ("asado", "ensalada", "fruta", "desayuno")
VEREDICTOS = {"BARATO", "NORMAL", "CARO"}
URLS_RESUMEN = ("https://carestia.cl/resumen.json",
                "https://pitvox.github.io/costo-de-vida-cl/resumen.json")
URLS_INDICES = ("https://carestia.cl/indices.json",
                "https://pitvox.github.io/costo-de-vida-cl/indices.json")
MAX_VARIACION_PCT = 40
TOLERANCIA_APORTES = 0.01
TIMEOUT = 30

OK, KO = "✓", "✗"


class SinReferencia(Exception):
    pass


def clp(x) -> str:
    return "$" + f"{int(round(x)):,}".replace(",", ".")


# ---------------- Entrada ----------------
def resumen_desde_indices(data: dict) -> dict:
    """Misma receta que build_site.generar_resumen (solo los campos que se
    validan): variación semanal de las dos últimas semanas de la serie real,
    'semana' = la última fecha más reciente entre los índices."""
    indices, semana = {}, None
    for code, d in data["indices"].items():
        real = d.get("real") or []
        variacion = None
        if len(real) >= 2 and real[-2]["value"]:
            variacion = round((real[-1]["value"] / real[-2]["value"] - 1) * 100, 1)
        if real and (semana is None or real[-1]["time"] > semana):
            semana = real[-1]["time"]
        indices[code] = {
            "nombre": d["nombre"],
            "subtitulo": d["subtitulo"],
            "costo_pesos_hoy": d["costo_real"],
            "veredicto": d["veredicto"],
            "percentil": d["percentil"],
            "vs_promedio_pct": d["vs_promedio"],
            "variacion_semanal_pct": variacion,
            "semanas_historia": d["n"],
        }
    return {"semana": semana, "indices": indices}


def descargar_json(urls, validar_forma):
    """Primer JSON válido de la lista de URLs. Devuelve (data, url, errores)."""
    errores = []
    for url in urls:
        try:
            r = requests.get(url, timeout=TIMEOUT,
                             headers={"Cache-Control": "no-cache"})
            r.raise_for_status()
            data = r.json()
            validar_forma(data)
            return data, url, errores
        except Exception as e:   # red, HTTP, JSON o forma inesperada
            errores.append(f"{url}: {type(e).__name__}: {e}")
    return None, None, errores


def _forma_resumen(data):
    if not isinstance(data, dict) or "semana" not in data \
            or not isinstance(data.get("indices"), dict):
        raise ValueError("no tiene 'semana' e 'indices'")


def _forma_indices(data):
    if not isinstance(data, dict) or not isinstance(data.get("productos"), dict):
        raise ValueError("no tiene 'productos'")


def descargar_snapshot() -> tuple:
    data, url, errores = descargar_json(URLS_RESUMEN, _forma_resumen)
    if data is None:
        raise SinReferencia(
            "no pude leer el snapshot anterior; no valido contra nada. "
            + " | ".join(errores))
    return data, url


# ---------------- Chequeos ----------------
def _fecha(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def chequear_indice(code, nuevo, ant, semana_nueva, semana_ant) -> list:
    """Lista de (chequeo, ok, detalle) para un índice del resumen."""
    out = []
    n_new, n_old = nuevo.get("semanas_historia"), ant.get("semanas_historia")
    try:
        dias = (_fecha(semana_nueva) - _fecha(semana_ant)).days
    except (TypeError, ValueError) as e:
        out.append((f"{code}: semanas_historia", False, f"'semana' ilegible: {e}"))
        dias = None
    if dias is not None:
        if dias < 0 or dias % 7:
            out.append((f"{code}: semanas_historia", False,
                        f"semana {semana_ant} → {semana_nueva}: salto de {dias} días"))
        else:
            esperado = dias // 7
            ok = isinstance(n_new, int) and isinstance(n_old, int) \
                and n_new - n_old == esperado
            out.append((f"{code}: semanas_historia", ok,
                        f"{n_old}→{n_new} (esperado +{esperado}; "
                        f"semana {semana_ant} → {semana_nueva})"))

    var = nuevo.get("variacion_semanal_pct")
    ok = isinstance(var, (int, float)) and abs(var) <= MAX_VARIACION_PCT
    out.append((f"{code}: variación semanal", ok,
                f"{var}% (límite ±{MAX_VARIACION_PCT}%)"))

    costo = nuevo.get("costo_pesos_hoy")
    out.append((f"{code}: costo_pesos_hoy > 0",
                isinstance(costo, (int, float)) and costo > 0, f"{costo}"))
    pct = nuevo.get("percentil")
    out.append((f"{code}: percentil 0..100",
                isinstance(pct, (int, float)) and 0 <= pct <= 100, f"{pct}"))
    ver = nuevo.get("veredicto")
    out.append((f"{code}: veredicto", ver in VEREDICTOS, f"{ver}"))
    return out


def chequear_componentes(code, d) -> list:
    out = []
    comp = d.get("componentes") or []
    malos = [c.get("label") for c in comp if c.get("mismatch") is True]
    out.append((f"{code}: sin mismatch de unidades", not malos,
                "ninguno" if not malos else "mismatch en: " + ", ".join(map(str, malos))))
    sin_aporte = [c.get("label") for c in comp if c.get("aporte") is None]
    nominal = d.get("costo_nominal")
    if not comp or sin_aporte or not isinstance(nominal, (int, float)) or nominal <= 0:
        det = ("sin componentes" if not comp else
               f"aporte s/d en: {', '.join(map(str, sin_aporte))}" if sin_aporte else
               f"costo_nominal inválido: {nominal}")
        out.append((f"{code}: Σ aportes = costo_nominal", False, det))
        return out
    suma = sum(c["aporte"] for c in comp)
    desvio = (suma - nominal) / nominal
    out.append((f"{code}: Σ aportes = costo_nominal",
                abs(desvio) <= TOLERANCIA_APORTES,
                f"{clp(suma)} vs {clp(nominal)} ({desvio * 100:+.2f}%, "
                f"tolerancia ±{TOLERANCIA_APORTES * 100:g}%)"))
    return out


def chequear_catalogo(productos: dict, esperados: int) -> tuple:
    n = len(productos)
    if n == esperados:
        return (f"catálogo de productos", True, f"{n} series (esperadas {esperados})")
    det = f"{n} series, esperadas {esperados}"
    ref, url, errores = descargar_json(URLS_INDICES, _forma_indices)
    if ref is None:
        det += ". No pude bajar el indices.json desplegado para listar los slugs: " \
               + " | ".join(errores)
    else:
        nuevos = sorted(set(productos) - set(ref["productos"]))
        idos = sorted(set(ref["productos"]) - set(productos))
        det += (f". Contra {url}: aparecieron [{', '.join(nuevos) or '—'}]; "
                f"desaparecieron [{', '.join(idos) or '—'}]")
    return ("catálogo de productos", False, det)


# ---------------- Salida ----------------
def escribir_summary(texto: str) -> None:
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    else:
        print(texto)


def armar_summary(filas, chequeos, url_ref, error=None) -> str:
    fallas = sum(1 for _c, ok, _d in chequeos if not ok) + (1 if error else 0)
    estado = f"{OK} PASA — se publica" if not fallas else \
        f"{KO} FALLA — build abortado, no se publica ({fallas} chequeo(s) en falla)"
    lineas = ["## Validación contra sitio desplegado", "", f"**{estado}**", ""]
    if url_ref:
        lineas += [f"Referencia: `{url_ref}`", ""]
    if error:
        lineas += [f"{KO} {error}", ""]
    if filas:
        lineas += ["| Índice | Precio (pesos de hoy) | Percentil | Veredicto "
                   "| Semanas anterior → nueva | Variación semanal |",
                   "|---|---:|---:|---|---:|---:|"]
        for f in filas:
            lineas.append(f"| {f['code']} | {f['precio']} | {f['percentil']} | "
                          f"{f['veredicto']} | {f['n_ant']} → {f['n_new']} | {f['var']} |")
        lineas.append("")
    if chequeos:
        lineas += ["| Estado | Chequeo | Detalle |", "|:-:|---|---|"]
        for c, ok, d in chequeos:
            lineas.append(f"| {OK if ok else KO} | {c} | {str(d).replace('|', '/')} |")
    return "\n".join(lineas)


def main() -> int:
    esperados = int(os.environ.get("PRODUCTOS_ESPERADOS", "125"))
    chequeos, filas, url_ref = [], [], None
    try:
        with open("indices.json", encoding="utf-8") as fh:
            data = json.load(fh)
        nuevo = resumen_desde_indices(data)
        ant, url_ref = descargar_snapshot()
    except SinReferencia as e:
        escribir_summary(armar_summary([], [], None, error=str(e)))
        print(f"FALLA: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        msg = f"no pude cargar el resultado nuevo (indices.json): {type(e).__name__}: {e}"
        escribir_summary(armar_summary([], [], None, error=msg))
        print(f"FALLA: {msg}", file=sys.stderr)
        return 1

    for code in INDICES:
        n = nuevo["indices"].get(code)
        a = ant["indices"].get(code)
        if n is None or a is None:
            chequeos.append((f"{code}: presente", False,
                             f"falta en {'el nuevo' if n is None else 'el desplegado'}"))
            continue
        chequeos += chequear_indice(code, n, a, nuevo["semana"], ant.get("semana"))
        chequeos += chequear_componentes(code, data["indices"][code])
        var = n.get("variacion_semanal_pct")
        costo = n.get("costo_pesos_hoy")
        filas.append({
            "code": code,
            "precio": clp(costo) if isinstance(costo, (int, float)) else costo,
            "percentil": n.get("percentil"), "veredicto": n.get("veredicto"),
            "n_ant": a.get("semanas_historia"), "n_new": n.get("semanas_historia"),
            "var": f"{var:+.1f}%" if isinstance(var, (int, float)) else var,
        })
    chequeos.append(chequear_catalogo(data.get("productos") or {}, esperados))

    escribir_summary(armar_summary(filas, chequeos, url_ref))
    fallas = [(c, d) for c, ok, d in chequeos if not ok]
    if fallas:
        for c, d in fallas:
            print(f"FALLA {c}: {d}", file=sys.stderr)
        return 1
    for f in filas:
        print(f"OK {f['code']}: {f['precio']} | p{f['percentil']} | "
              f"{f['veredicto']} | {f['n_ant']}→{f['n_new']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

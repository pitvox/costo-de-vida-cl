"""
publicacion.py: lo que decide, en cada corrida de actualizar.yml, si se arma
el sitio y si lo armado cuadra con lo publicado. No toca indices.py, validar.py,
la metodología ni los datos: solo lee el resumen.json publicado y el
indices.json recién calculado.

  python publicacion.py revisar
      Job "revisar", antes de todo. En una corrida programada, si la semana
      que ODEPA publica este viernes ya está en el resumen.json publicado,
      escribe construir=false y el workflow no arma ni publica nada (sale en
      verde). Así cada horario de respaldo se puede repetir sin efecto. Una
      corrida a mano siempre arma. Si no puede leer lo publicado, arma
      igual: validar.py falla después, con su detalle.

  python publicacion.py conteos
      Job "build", después de indices.py y antes de validar.py. Compara la
      semana y los conteos (semanas_historia de cada índice) contra el
      resumen.json publicado, la referencia:
        - semana nueva (7 días después): los 4 conteos tienen que ser los de
          la referencia más 1;
        - misma semana (ODEPA todavía no publica o es una corrida a mano a
          mitad de semana): los 4 conteos, iguales a los de la referencia;
        - cualquier otro salto falla. Si se perdió una semana entera, se
          corre a mano con aceptar_salto y entonces cada conteo tiene que
          avanzar exactamente las semanas que avanzó la semana.
      Si algo no cuadra termina con exit 1: el build se corta, no hay deploy
      y GitHub manda el correo. Si cuadra pero ODEPA no publicó la semana
      que ya debía estar (la misma regla del aviso "Sin datos nuevos" de
      build_site.py), escribe aviso=odepa: el sitio se publica con ese aviso
      y el job aviso-odepa deja el run en rojo.

Solo usa la biblioteca estándar: el job revisar corre con el Python del
runner, sin instalar nada. CARESTIA_AHORA (aaaa-mm-ddThh:mm, hora de Chile)
fija la hora, como en build_site.py: solo tests.
"""
import datetime
import json
import os
import sys
import urllib.request

INDICES = ("asado", "ensalada", "fruta", "desayuno")
# las de validar.py (tests/test_publicacion.py verifica que coincidan)
URLS_RESUMEN = ("https://carestia.cl/resumen.json",
                "https://pitvox.github.io/costo-de-vida-cl/resumen.json")
# los de build_site.py (tests/test_publicacion.py verifica que coincidan)
ODEPA_DIA, ODEPA_HORA = 4, 17          # viernes, 17:00
TIMEOUT = 30


# ---------------- Hora y semanas ----------------
def ahora_chile() -> datetime.datetime:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Santiago")
    except Exception:   # sin base de zonas horarias: hora de verano de Chile
        tz = datetime.timezone(datetime.timedelta(hours=-3))
    fijo = os.environ.get("CARESTIA_AHORA")
    if fijo:
        f = datetime.datetime.fromisoformat(fijo)
        return f.replace(tzinfo=tz) if f.tzinfo is None else f.astimezone(tz)
    return datetime.datetime.now(tz)


def _ultimo_viernes(hoy: datetime.date) -> datetime.date:
    return hoy - datetime.timedelta(days=(hoy.weekday() - ODEPA_DIA) % 7)


def semana_objetivo(ahora: datetime.datetime) -> datetime.date:
    """El lunes de la semana que ODEPA publica el último viernes (hoy, si es
    viernes, a cualquier hora): la que buscan las corridas del viernes y del
    sábado."""
    return _ultimo_viernes(ahora.date()) - datetime.timedelta(days=ODEPA_DIA)


def semana_esperada(ahora: datetime.datetime) -> datetime.date:
    """La misma regla de build_site.semana_esperada: el lunes de la última
    semana que ODEPA ya publicó a esta hora (el viernes, recién desde las
    17:00 de Chile)."""
    hoy = ahora.date()
    viernes = _ultimo_viernes(hoy)
    if viernes == hoy and ahora.hour < ODEPA_HORA:
        viernes -= datetime.timedelta(weeks=1)
    return viernes - datetime.timedelta(days=ODEPA_DIA)


def _fecha(s) -> datetime.date:
    return datetime.date.fromisoformat(str(s))


# ---------------- Entrada ----------------
def _get_json(url: str):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                               "User-Agent": "carestia-publicacion"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def leer_referencia(urls=URLS_RESUMEN, get=None):
    """El primer resumen.json publicado con 'semana' e 'indices'. Devuelve
    (resumen, url, errores); sin ninguno legible, (None, None, errores)."""
    get = get or _get_json
    errores = []
    for url in urls:
        try:
            data = get(url)
            if not isinstance(data, dict) or "semana" not in data \
                    or not isinstance(data.get("indices"), dict):
                raise ValueError("no tiene 'semana' e 'indices'")
            return data, url, errores
        except Exception as e:   # red, HTTP, JSON o forma inesperada
            errores.append(f"{url}: {type(e).__name__}: {e}")
    return None, None, errores


def resumen_nuevo(data: dict) -> tuple:
    """(semana, {índice: semanas_historia}) del indices.json recién
    calculado, con la receta de validar.resumen_desde_indices: la semana es
    la última fecha más reciente entre los índices y el conteo es "n"."""
    semana, conteos = None, {}
    for code, d in (data.get("indices") or {}).items():
        real = d.get("real") or []
        if real and (semana is None or real[-1]["time"] > semana):
            semana = real[-1]["time"]
        conteos[code] = d.get("n")
    return semana, conteos


# ---------------- Decisiones ----------------
def revisar(evento: str, ahora: datetime.datetime, ref, url, errores) -> tuple:
    """(construir, motivo) para el job revisar."""
    objetivo = semana_objetivo(ahora)
    if evento != "schedule":
        return True, f"Corrida {evento or 'sin evento'}: se arma siempre."
    if ref is None:
        return True, ("No pude leer el resumen.json publicado; se arma igual y "
                      "validar.py dice por qué. " + " | ".join(errores))
    try:
        publicada = _fecha(ref.get("semana"))
    except ValueError:
        return True, f"La semana publicada es ilegible ({ref.get('semana')!r}); se arma igual."
    if publicada >= objetivo:
        return False, (f"La semana del {objetivo} ya está publicada ({url}: semana "
                       f"{publicada}). No se arma ni se publica nada.")
    return True, (f"Falta la semana del {objetivo} ({url}: semana {publicada}). "
                  f"Se arma el sitio.")


def chequear_conteos(data: dict, ref: dict, ahora: datetime.datetime,
                     aceptar_salto: bool = False) -> dict:
    """Compara la semana y los conteos nuevos con la referencia publicada.
    Devuelve {"ok", "aviso", "errores", "avisos", "filas", "semana",
    "semana_ref", "semanas"}."""
    out = {"ok": False, "aviso": None, "errores": [], "avisos": [], "filas": [],
           "semana": None, "semana_ref": ref.get("semana"), "semanas": None}
    semana, conteos = resumen_nuevo(data)
    out["semana"] = semana
    try:
        nueva, anterior = _fecha(semana), _fecha(ref.get("semana"))
    except ValueError as e:
        out["errores"].append(f"semana ilegible (nueva {semana!r}, publicada "
                              f"{ref.get('semana')!r}): {e}")
        return out
    dias = (nueva - anterior).days
    if dias < 0 or dias % 7:
        out["errores"].append(f"la semana pasa de {anterior} a {nueva}: un salto de "
                              f"{dias} días")
        return out
    k = dias // 7
    out["semanas"] = k
    if k > 1 and not aceptar_salto:
        out["errores"].append(
            f"la semana avanza {k} semanas ({anterior} a {nueva}) y cada corrida "
            f"publica una. Si se perdió una semana entera, correr a mano con "
            f"aceptar_salto")
    for code in INDICES:
        a = (ref["indices"].get(code) or {}).get("semanas_historia")
        n = conteos.get(code)
        esperado = a + k if isinstance(a, int) and not isinstance(a, bool) else None
        ok = esperado is not None and isinstance(n, int) and not isinstance(n, bool) \
            and n == esperado
        out["filas"].append((code, a, n, esperado, ok))
        if not ok:
            out["errores"].append(f"{code}: {n} semanas de historia, esperadas "
                                  f"{esperado} (la referencia, {a}, más {k})")
    if out["errores"]:
        return out
    out["ok"] = True
    if nueva < semana_esperada(ahora):
        out["aviso"] = "odepa"
        out["avisos"].append(
            f"ODEPA no publicó la semana del {semana_esperada(ahora)}: el sitio se "
            f"publica con el aviso \"Sin datos nuevos\" y el run queda en rojo")
    elif nueva < semana_objetivo(ahora):
        out["avisos"].append(
            f"ODEPA todavía no publica la semana del {semana_objetivo(ahora)}: se "
            f"publica lo mismo y la próxima corrida vuelve a intentar")
    return out


# ---------------- Salida ----------------
def _anotar(nivel: str, texto: str) -> None:
    print(f"::{nivel}::{texto}")


def _summary(lineas) -> None:
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    texto = "\n".join(lineas) + "\n"
    if ruta:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(texto)
    else:
        print(texto)


def _output(clave: str, valor: str) -> None:
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(f"{clave}={valor}\n")
    print(f"{clave}={valor}")


def main_revisar() -> int:
    ahora = ahora_chile()
    evento = os.environ.get("GITHUB_EVENT_NAME", "")
    ref, url, errores = (None, None, []) if evento != "schedule" else leer_referencia()
    construir, motivo = revisar(evento, ahora, ref, url, errores)
    _output("construir", "true" if construir else "false")
    _anotar("notice", motivo)
    _summary(["## Semana publicada", "", f"{ahora:%Y-%m-%d %H:%M} hora de Chile.", "",
              f"**{'Se arma el sitio' if construir else 'Nada que hacer'}.** {motivo}"])
    return 0


def main_conteos() -> int:
    ahora = ahora_chile()
    aceptar_salto = os.environ.get("ACEPTAR_SALTO", "").strip().lower() == "true"
    try:
        with open("indices.json", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        msg = f"no pude leer indices.json: {type(e).__name__}: {e}"
        _anotar("error", f"Conteos: {msg}")
        _summary(["## Conteos contra la referencia", "", f"**FALLA.** {msg}"])
        return 1
    ref, url, errores = leer_referencia()
    if ref is None:
        msg = "no pude leer el resumen.json publicado: " + " | ".join(errores)
        _anotar("error", f"Conteos: {msg}")
        _summary(["## Conteos contra la referencia", "", f"**FALLA.** {msg}"])
        return 1
    r = chequear_conteos(data, ref, ahora, aceptar_salto)
    lineas = ["## Conteos contra la referencia", "",
              f"Referencia: `{url}`, semana {r['semana_ref']}. Semana nueva: {r['semana']}"
              + (f" ({r['semanas']} semana(s) más)." if r["semanas"] is not None else "."),
              ""]
    if r["filas"]:
        lineas += ["| Índice | Referencia | Esperado | Nuevo | Estado |", "|---|---:|---:|---:|:-:|"]
        lineas += [f"| {c} | {a} | {e} | {n} | {'✓' if ok else '✗'} |"
                   for c, a, n, e, ok in r["filas"]]
        lineas.append("")
    if r["ok"]:
        lineas.append("**PASA.**" + "".join(f" {a}." for a in r["avisos"]))
    else:
        lineas.append("**FALLA: build cortado, no se publica.**")
        lineas += [f"- {e}" for e in r["errores"]]
    _summary(lineas)
    for e in r["errores"]:
        _anotar("error", f"Conteos: {e}")
    for a in r["avisos"]:
        _anotar("warning", a)
    if not r["ok"]:
        return 1
    if r["aviso"]:
        _output("aviso", r["aviso"])
    print(f"OK conteos: semana {r['semana_ref']} a {r['semana']}, "
          + ", ".join(f"{c} {a} a {n}" for c, a, n, _e, _ok in r["filas"]))
    return 0


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "revisar":
        sys.exit(main_revisar())
    if comando == "conteos":
        sys.exit(main_conteos())
    print("uso: python publicacion.py revisar|conteos", file=sys.stderr)
    sys.exit(2)

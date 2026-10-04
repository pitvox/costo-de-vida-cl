"""
uf.py: valor de la UF de cada semana, para la opción "UF" de los gráficos.

Corre aparte de indices.py (no lo importa ni lo toca). Pide la serie diaria de
la UF al Banco Central de Chile (F073.UFF.PRE.Z.D) con los secretos BCCH_USER
y BCCH_PASS; mindicador.cl queda de respaldo y solo llena las fechas que al
Banco Central le falten, igual que con el IPC en indices.py.

Escribe datos/uf.json con la UF de cada lunes (las series semanales del sitio
se rotulan con su lunes), compacto como las series de productos:

  {"fuente": "Banco Central de Chile", "serie": "F073.UFF.PRE.Z.D",
   "generado": "2026-10-04", "t0": "2007-12-31", "v": [19622.66, ...]}

v[i] es la UF del lunes t0 + 7*i. Son obligatorios todos los lunes desde
2007-12-31 hasta el de la semana en curso (hora de Chile). Después siguen los
lunes que ya tengan valor publicado (la UF se publica hasta el día 9 del mes
siguiente), y la serie corta en el primero que falte.

Nunca hace fallar el build. Si no hay UF (ninguna fuente respondió, o la serie
no pasó la validación), deja un ::warning:: en el log, borra un datos/uf.json
viejo si lo hubiera y termina con código 0: el sitio se publica sin la opción
UF. Las credenciales nunca se imprimen: todo mensaje de error pasa por limpiar().

Solo usa requests (+ stdlib).

Correr:
  pip install requests
  python uf.py
"""
import datetime
import json
import math
import os
import re
import sys
import time
from urllib.parse import quote, quote_plus, urlencode
from zoneinfo import ZoneInfo

import requests

INICIO = datetime.date(2007, 12, 31)   # lunes: cubre todas las semanas desde 2008
SERIE_BCCH = "F073.UFF.PRE.Z.D"
URL_BCCH = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
URL_MINDICADOR = "https://mindicador.cl/api/uf/{anio}"
ARCHIVO = os.path.join("datos", "uf.json")
DIAS_ADELANTE = 45          # la UF se publica hasta el día 9 del mes siguiente
REINTENTOS = 3
TIMEOUT = 30
MINDICADOR_CAIDO = 3        # años seguidos sin respuesta: no se sigue pidiendo
UF_MIN, UF_MAX = 10000, 100000
SALTO_MAX = 0.02            # cambio máximo entre dos lunes seguidos
try:
    SANTIAGO = ZoneInfo("America/Santiago")
except Exception:  # noqa
    # sin base de zonas horarias: Chile continental en invierno (el desfase de
    # una hora lo absorben las 12 horas de fecha_mindicador)
    SANTIAGO = datetime.timezone(datetime.timedelta(hours=-4))

FUENTE_BCCH = "Banco Central de Chile"
FUENTE_MINDICADOR = "mindicador.cl"
FUENTE_AMBAS = "Banco Central de Chile y mindicador.cl"

dormir = time.sleep         # los tests lo reemplazan para no esperar


class FalloFuente(Exception):
    """Una fuente no entregó la UF. El mensaje ya viene sin credenciales."""


# ---------------- Credenciales ----------------
def _credenciales() -> tuple:
    return os.environ.get("BCCH_USER", ""), os.environ.get("BCCH_PASS", "")


def limpiar(texto) -> str:
    """Saca las credenciales de un texto antes de mostrarlo y lo deja en una
    sola línea. Las excepciones de requests traen la URL completa, con user y
    pass en la consulta. Y un salto de línea en un texto ajeno (la Descripcion
    del Banco Central, un mensaje de error) podría empezar una línea con "::",
    que GitHub Actions toma como comando del workflow."""
    formas = set()
    for secreto in _credenciales():
        for s in (secreto, secreto.strip(), " ".join(secreto.split())):
            if s:
                formas |= {s, quote(s, safe=""), quote_plus(s)}
    formas = sorted(formas, key=len, reverse=True)

    def tapar(t):
        for forma in formas:
            t = t.replace(forma, "***")
        return t
    # primero los secretos enteros: si el regex corta antes una clave cruda
    # (por ejemplo en un "&"), lo que queda ya no coincide y se imprimiría
    texto = tapar(str(texto))
    texto = re.sub(r"(?i)\b(user|pass)=[^&\s'\"]*", r"\1=***", texto)
    # una sola línea; se tapa de nuevo por si un secreto con espacios venía
    # con otro espacio en blanco (un salto de línea, por ejemplo)
    return tapar(" ".join(texto.split()))


# ---------------- Fechas ----------------
def hoy_chile() -> datetime.date:
    return datetime.datetime.now(SANTIAGO).date()


def lunes_de(d: datetime.date) -> datetime.date:
    return d - datetime.timedelta(days=d.weekday())


def lunes_requeridos(hoy: datetime.date) -> list:
    """Todos los lunes desde INICIO hasta el de la semana de hoy."""
    fin, lunes, out = lunes_de(hoy), INICIO, []
    while lunes <= fin:
        out.append(lunes)
        lunes += datetime.timedelta(weeks=1)
    return out


def anios_mindicador(hoy: datetime.date, faltan=()) -> list:
    """Años a pedir a mindicador: desde el de INICIO hasta el actual, y el
    siguiente en diciembre (los lunes de enero ya pueden tener UF).

    Con faltan (los lunes obligatorios que no trajo el Banco Central) van
    primero los años de esos lunes y los posteriores a la semana en curso, y
    después el resto. Así el corte de uf_mindicador por servicio caído solo
    llega a saltarse un año necesario cuando otro año necesario ya falló, es
    decir, cuando la serie ya no sale."""
    fin = hoy.year + 1 if hoy.month == 12 else hoy.year
    anios = list(range(INICIO.year, fin + 1))
    if not faltan:
        return anios
    primero = {f.year for f in faltan} | {a for a in anios if a > lunes_de(hoy).year}
    return sorted(primero & set(anios)) + [a for a in anios if a not in primero]


def fecha_mindicador(texto: str) -> datetime.date:
    """mindicador da la medianoche chilena expresada en UTC: 03:00Z en verano,
    04:00Z en invierno. Se pasa a hora de Chile y se suman 12 horas antes de
    tomar la fecha, así que tanto las 00:00 como las 23:00 del día anterior
    (horario de verano mal aplicado) caen en el día correcto."""
    t = datetime.datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return (t.astimezone(SANTIAGO) + datetime.timedelta(hours=12)).date()


def ddmmaaaa(d: datetime.date) -> str:
    return d.strftime("%d-%m-%Y")


def pesos(x: float) -> str:
    """39485.65 -> "39.485,65" (formato chileno)."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _numero(x):
    """float finito o None (BCCh manda los valores como texto, y "NaN" sin dato)."""
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------- Fuentes ----------------
def _pedir(url: str, nombre: str, leer):
    """GET con hasta REINTENTOS intentos (esperas de 2 y 4 s) ante errores de
    red o de formato. leer(data) interpreta el JSON: si lanza FalloFuente (por
    ejemplo, un error declarado por la API) no se reintenta."""
    for intento in range(1, REINTENTOS + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            try:
                data = r.json()
            except ValueError:
                # se limpia antes de cortar: cortado, un secreto a medias ya no se tapa
                texto = limpiar(r.text)[:200]
                raise ValueError(f"respuesta {r.status_code} que no es JSON: {texto}") from None
            if not isinstance(data, dict):
                raise ValueError(f"respuesta {r.status_code} con un JSON inesperado")
            return leer(data)
        except (requests.RequestException, ValueError) as e:
            error = limpiar(f"{type(e).__name__}: {e}")
            if intento == REINTENTOS:
                raise FalloFuente(error) from None
            espera = 2 ** intento
            print(f"  [{nombre}: {error}; reintento {intento + 1} de {REINTENTOS} en {espera} s]")
            dormir(espera)


def _leer_bcch(data: dict) -> dict:
    # Con error (ej: Codigo -5) Series.Obs viene null: se mira Codigo primero.
    if data.get("Codigo") != 0:
        raise FalloFuente(limpiar(f"error {data.get('Codigo')}: {data.get('Descripcion')}"))
    obs = (data.get("Series") or {}).get("Obs") or []
    if not obs:
        raise FalloFuente("Codigo 0 pero sin observaciones")
    diarios = {}
    for o in obs:
        if not isinstance(o, dict) or o.get("statusCode") != "OK":
            continue
        v = _numero(o.get("value"))
        try:
            f = datetime.datetime.strptime(str(o.get("indexDateString")), "%d-%m-%Y").date()
        except ValueError:
            continue
        if v is not None:
            diarios[f] = v
    if not diarios:
        raise FalloFuente("ninguna observación válida tras filtrar statusCode y value")
    return diarios


def uf_bcch(desde: datetime.date, hasta: datetime.date) -> dict:
    """UF diaria del Banco Central: {fecha: valor}. Lanza FalloFuente si no hay."""
    usuario, clave = _credenciales()
    url = URL_BCCH + "?" + urlencode({
        "user": usuario, "pass": clave,
        "firstdate": desde.isoformat(), "lastdate": hasta.isoformat(),
        "timeseries": SERIE_BCCH, "function": "GetSeries"})
    diarios = _pedir(url, "BCCh", _leer_bcch)
    print(f"  [BCCh: {len(diarios)} días, {ddmmaaaa(min(diarios))} a {ddmmaaaa(max(diarios))}]")
    return diarios


def _leer_mindicador(data: dict) -> dict:
    serie = data.get("serie")
    if not isinstance(serie, list):
        raise ValueError("respuesta sin la lista 'serie'")
    diarios = {}
    for o in serie:     # una lista vacía es válida: el año aún no tiene datos
        if not isinstance(o, dict):
            continue
        v = _numero(o.get("valor"))
        try:
            f = fecha_mindicador(str(o.get("fecha")))
        except ValueError:
            continue
        if v is not None:
            diarios[f] = v
    return diarios


def uf_mindicador(anios) -> dict:
    """UF diaria de mindicador, un pedido por año, en el orden recibido (ver
    anios_mindicador): {fecha: valor}. Un año que falla se avisa y se sigue con
    los demás (validar decide si faltó algo). Con MINDICADOR_CAIDO años
    seguidos sin respuesta deja de pedir, para no alargar el build con un
    servicio caído. Lanza FalloFuente si no hay datos."""
    anios, diarios, fallidos, seguidos = list(anios), {}, [], 0
    for k, anio in enumerate(anios):
        try:
            datos = _pedir(URL_MINDICADOR.format(anio=anio), f"mindicador {anio}", _leer_mindicador)
        except FalloFuente as e:
            print(f"  [mindicador {anio} falló: {limpiar(e)}]")
            fallidos.append(anio)
            seguidos += 1
            resto = anios[k + 1:]
            if seguidos >= MINDICADOR_CAIDO and resto:
                print(f"  [mindicador: {seguidos} años seguidos sin respuesta; "
                      f"no pido los {len(resto)} años que quedan]")
                fallidos += resto
                break
            continue
        seguidos = 0
        diarios.update(datos)
    if not diarios:
        raise FalloFuente("sin respuesta" if fallidos else "sin datos")
    if fallidos:
        print(f"  [mindicador: sin datos de {', '.join(map(str, fallidos))}]")
    print(f"  [mindicador: {len(diarios)} días, {ddmmaaaa(min(diarios))} a {ddmmaaaa(max(diarios))}]")
    return diarios


# ---------------- Serie semanal ----------------
def fusionar(bcch: dict, mind: dict) -> tuple:
    """Manda el Banco Central; mindicador solo llena las fechas que no trae.
    Devuelve (diarios, fechas que vinieron de mindicador)."""
    diarios, de_mindicador = dict(bcch), set()
    for f, v in mind.items():
        if f not in diarios:
            diarios[f] = v
            de_mindicador.add(f)
    return diarios, de_mindicador


def semanas(diarios: dict, hoy: datetime.date) -> tuple:
    """(t0, v): la UF de cada lunes seguido desde INICIO, redondeada a 2
    decimales. Un lunes obligatorio sin valor queda en None (validar lo
    rechaza). Después del lunes de hoy sigue mientras haya valor."""
    requeridos = lunes_requeridos(hoy)
    v = [round(diarios[f], 2) if f in diarios else None for f in requeridos]
    lunes = requeridos[-1] + datetime.timedelta(weeks=1)
    while lunes in diarios:
        v.append(round(diarios[lunes], 2))
        lunes += datetime.timedelta(weeks=1)
    return INICIO, v


def _lista(fechas: list, n: int = 5) -> str:
    txt = ", ".join(ddmmaaaa(f) for f in fechas[:n])
    return txt + (f" y {len(fechas) - n} más" if len(fechas) > n else "")


def validar(t0: datetime.date, v: list, hoy: datetime.date) -> list:
    """Problemas de la serie (lista vacía si está bien): todo lunes obligatorio
    con valor, cada valor finito entre UF_MIN y UF_MAX, y menos de SALTO_MAX
    de cambio entre dos lunes seguidos."""
    def lunes(i):
        return t0 + datetime.timedelta(weeks=i)

    def bueno(x):
        n = _numero(x)
        return n is not None and UF_MIN < n < UF_MAX

    problemas = []
    n = len(lunes_requeridos(hoy))
    faltan = [lunes(i) for i in range(n) if i >= len(v) or v[i] is None]
    if faltan:
        problemas.append(f"faltan {len(faltan)} lunes ({_lista(faltan)})")
    raros = [i for i, x in enumerate(v) if x is not None and not bueno(x)]
    if raros:
        problemas.append("valores fuera de rango: " + ", ".join(
            f"{v[i]} el lunes {ddmmaaaa(lunes(i))}" for i in raros[:5]))
    saltos = [i for i in range(1, len(v))
              if bueno(v[i - 1]) and bueno(v[i]) and abs(v[i] / v[i - 1] - 1) >= SALTO_MAX]
    if saltos:
        problemas.append("saltos de 2% o más: " + ", ".join(
            f"{(v[i] / v[i - 1] - 1) * 100:+.1f}% el lunes {ddmmaaaa(lunes(i))}" for i in saltos[:5]))
    return problemas


def nombre_fuente(lunes: list, de_mindicador: set) -> str:
    """Fuente según de dónde salió el valor de cada lunes publicado."""
    n = sum(1 for f in lunes if f in de_mindicador)
    if n == 0:
        return FUENTE_BCCH
    return FUENTE_MINDICADOR if n == len(lunes) else FUENTE_AMBAS


# ---------------- Salida ----------------
def escribir(t0: datetime.date, v: list, fuente: str, hoy: datetime.date, ruta: str = ARCHIVO) -> None:
    datos = {"fuente": fuente, "serie": SERIE_BCCH, "generado": hoy.isoformat(),
             "t0": t0.isoformat(), "v": v}
    carpeta = os.path.dirname(ruta)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)


def escribir_summary(lineas: list) -> None:
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ruta:
        return
    try:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write("## UF\n\n" + "\n".join(f"- {x}" for x in lineas) + "\n")
    except OSError as e:
        print(f"  [no se pudo escribir el resumen del workflow: {limpiar(e)}]")


def falla_suave(motivo: str, ruta: str = ARCHIVO) -> int:
    """Sin UF el build sigue: aviso en el log, fuera el uf.json viejo, código 0."""
    motivo = limpiar(motivo)
    borrado = ""
    for archivo in (ruta, ruta + ".tmp"):
        try:
            if os.path.exists(archivo):
                os.remove(archivo)
                if archivo == ruta:
                    borrado = f" Se borró el {ruta} anterior."
        except OSError as e:
            borrado += f" No se pudo borrar {archivo}: {limpiar(e)}."
    aviso = (f"No se pudo obtener la UF; el sitio se publica sin la opción UF. "
             f"Motivo: {motivo}.{borrado}")
    print(f"::warning::{aviso}")
    escribir_summary([aviso])
    return 0


def _correr(hoy: datetime.date) -> int:
    requeridos = lunes_requeridos(hoy)
    motivos, bcch, mind = [], {}, {}
    usuario, clave = _credenciales()
    if usuario.strip() and clave.strip():
        print("UF: Banco Central de Chile (oficial)...")
        try:
            bcch = uf_bcch(INICIO, hoy + datetime.timedelta(days=DIAS_ADELANTE))
        except Exception as e:  # noqa
            motivos.append(f"Banco Central: {limpiar(e)}")
            print(f"  [BCCh falló: {limpiar(e)}; sigo con mindicador]")
    else:
        motivos.append("Banco Central: faltan BCCH_USER o BCCH_PASS")
        print("UF: sin credenciales BCCh (BCCH_USER y BCCH_PASS), parto de mindicador.")

    faltan = [f for f in requeridos if f not in bcch]
    if faltan:
        if bcch:
            print(f"UF: al Banco Central le faltan {len(faltan)} lunes; los pido a mindicador...")
        else:
            print("UF: mindicador...")
        try:
            mind = uf_mindicador(anios_mindicador(hoy, faltan))
        except Exception as e:  # noqa
            motivos.append(f"mindicador: {limpiar(e)}")
            print(f"  [mindicador falló: {limpiar(e)}]")
    if not bcch and not mind:
        return falla_suave("ninguna fuente respondió (" + "; ".join(motivos) + ")")

    diarios, de_mindicador = fusionar(bcch, mind)
    t0, v = semanas(diarios, hoy)
    problemas = validar(t0, v, hoy)
    if problemas:
        extra = f" (además, {'; '.join(motivos)})" if motivos else ""
        return falla_suave("la serie no pasó la validación: " + "; ".join(problemas) + extra)

    lunes = [t0 + datetime.timedelta(weeks=i) for i in range(len(v))]
    fuente = nombre_fuente(lunes, de_mindicador)
    escribir(t0, v, fuente, hoy)
    actual = requeridos[-1]
    lineas = [f"Fuente: {fuente}",
              f"{len(v)} semanas, del lunes {ddmmaaaa(lunes[0])} al lunes {ddmmaaaa(lunes[-1])}",
              f"UF del lunes {ddmmaaaa(actual)}: {pesos(v[len(requeridos) - 1])}"]
    print(f"UF OK, escrito {ARCHIVO}")
    for x in lineas:
        print(f"  {x}")
    escribir_summary(lineas)
    return 0


def main(hoy: datetime.date = None) -> int:
    """Siempre devuelve 0: sin UF el sitio se publica igual, sin esa opción."""
    try:
        return _correr(hoy or hoy_chile())
    except Exception as e:  # noqa
        # cualquier imprevisto es falla suave
        return falla_suave(f"error inesperado ({type(e).__name__}: {e})")


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)     # pase lo que pase, el build sigue

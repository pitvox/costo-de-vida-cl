"""
build_site.py - genera el sitio Carestía
========================================
Lee 'indices.json' (lo produce indices.py) y escribe dos páginas principales:

- index.html, la portada en formato tabla: cinta de índices, las 4 tarjetas
  de "Índices Carestía" (el único lugar del semáforo), lo que más se movió
  esta semana y la tabla de productos, todo en HTML estático (cada fila es un
  link a su ficha); el JS solo ordena y filtra. Los links viejos de la app
  que entraban por la portada (#comparar, #canasta=..., un índice) se
  redirigen a /graficos.html con el mismo hash.
- graficos.html, la app de gráficos: cinta ticker y una sola superficie; el
  hero es el único lienzo de gráfico y las tabs lo cambian de MODO en el
  lugar (índices con veredicto y línea/velas, Comparar productos en
  spaghetti, Arma tu canasta), con una franja de contexto que acompaña a
  cada modo. #asado, #ensalada, #fruta y #desayuno abren ese índice.

Identidad (tokens en CSS_BASE, iguales en todas las páginas): base neutra
con texto hueso; la brasa #e8743b solo vive en la í del wordmark y en la
línea de los índices oficiales; hueso es el color de las canastas de
usuario. El verde/ámbar/rojo del semáforo queda reservado a los 4 índices
(veredicto, zonas del percentil de sus tarjetas y velas); los productos van
sin semáforo. IBM Plex Sans para la interfaz y el texto, IBM Plex Mono para
etiquetas cortas en mayúsculas y Space Grotesk para el wordmark, los títulos
de sección de la portada y las cifras grandes.

/graficos.html trae inline solo el primer pantallazo; las series completas
van a datos/ y se piden a demanda (ver generar_datos). La portada no lleva
datos inline: sus cifras salen de datos/catalogo.json en el build.

También escribe una ficha por producto (productos/{slug}.html), el listado
/productos/, /metodologia.html, las páginas institucionales y legales (con
los textos literales de textos/), robots.txt, sitemap.xml y resumen.json.
Todas las páginas comparten la navegación del encabezado y el pie.

TradingView Advanced Charts (paso A): carestia-tv.js (el datafeed sobre
datos/), carestia-tv.css (el tema para el iframe de la librería) y la página
oculta /prueba-graficos.html. La librería no está en este repo: el workflow
la descarga al publicar (ver generar_tradingview).

Correr:
  python indices.py
  python build_site.py
  python -m http.server   (y abrir http://localhost:8000: /graficos.html
                           pide datos/ por fetch, que no corre con file://)
"""

import datetime
import hashlib
import html
import json
import math
import os
import re
import unicodedata

# las cantidades de /metodologia.html salen del mismo diccionario que usa el
# cálculo (nunca escritas a mano)
from indices import BASKETS

with open("indices.json", encoding="utf-8") as fh:
    DATA = json.load(fh)

GRAFICOS_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gráficos de los índices del costo de vida en Chile | Carestía</title>
<meta name="description" content="Gráficos semanales de los índices Carestía en pesos de hoy, con velas y estacionalidad. Compara productos y arma tu propia canasta con datos públicos de ODEPA.">
<link rel="canonical" href="https://carestia.cl/graficos.html">
<meta property="og:title" content="Gráficos de los índices del costo de vida en Chile | Carestía">
<meta property="og:description" content="Los índices Carestía en pesos de hoy desde 2008, para comparar productos y armar tu propia canasta. Datos públicos de ODEPA, actualizados cada viernes.">
<meta property="og:image" content="https://carestia.cl/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
__ICONO__
__FUENTES__
<!-- índices y Comparar van en Advanced Charts (carestia-tv.js monta la
     librería al cargar la página); Lightweight dibuja Arma tu canasta y el
     respaldo -->
<script defer src="/__TV_JS__?v=__VER_TV__"></script>
<script defer src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__

__CSS_CABECERA__
  /* ---- tabs de índice ---- */
  /* min-height = pill (34px) + padding: las tabs las construye JS y sin
     reserva la fila nacía vacía y empujaba todo al poblarse (CLS) */
  .tabs { display:flex; gap:8px; padding:12px clamp(16px,3vw,32px);
    min-height:59px; border-bottom:1px solid var(--line);
    overflow-x:auto; overflow-y:hidden;
    scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .tabs::-webkit-scrollbar { display:none; }
  /* afordancia: las pills inactivas se leen como botón (fondo panel, borde
     de línea, texto hueso) y el hover/focus responde con borde hueso */
  .tab { flex:none; font:600 13px var(--sans); letter-spacing:.01em;
    padding:8px 16px; min-height:34px; cursor:pointer; white-space:nowrap;
    background:var(--panel); border:1px solid var(--line); border-radius:999px;
    color:var(--bone);
    transition:background-color .15s ease, border-color .15s ease, color .15s ease; }
  .tab:not(.active):hover, .tab:not(.active):focus-visible {
    background:var(--hover); border-color:var(--bone); }
  .tab.active { background:var(--bone); border-color:var(--bone); color:var(--bg); }
  /* punto de 6px: marca las tabs de herramienta (Comparar productos /
     Arma tu canasta); toma el color del texto de la pill */
  .tab .tdot { display:inline-block; width:6px; height:6px; border-radius:50%;
    background:currentColor; margin-right:8px; vertical-align:middle; }
  /* separador fino entre los índices y las pills de herramientas */
  .tab-sep { flex:none; width:1px; align-self:stretch; background:var(--line);
    margin:0 4px; }
  /* móvil: sin scroll horizontal; las pills envuelven en dos filas completas
     (índices arriba, herramientas abajo) y el separador se vuelve un filete
     horizontal que fuerza el salto de fila. flex-basis 0 en las pills: cada
     fila se reparte el ancho y NUNCA nace una tercera fila; en pantallas muy
     angostas el texto elipsa en vez de reflowar. min-height =
     12+34+8+1+8+34+12 más el borde inferior: la reserva exacta de las dos
     filas antes de que JS las pueble (CLS). El punto brasa de las
     herramientas queda intacto */
  @media (max-width:640px) {
    .tabs { flex-wrap:wrap; overflow-x:visible; min-height:110px; }
    .tab { flex:1 1 0; min-width:0; overflow:hidden; text-overflow:ellipsis;
      text-align:center; padding:8px 6px; font-size:12px; letter-spacing:0; }
    .tab .tdot { margin-right:6px; }
    .tab-sep { flex-basis:100%; width:auto; height:1px; align-self:auto;
      margin:0; }
  }

  /* el pulso del veredicto usa su propio color del semáforo */
  @keyframes car-pulse {
    0%,100% { box-shadow:0 0 0 0 color-mix(in srgb, var(--verdict) 55%, transparent); }
    50% { box-shadow:0 0 14px 3px color-mix(in srgb, var(--verdict) 25%, transparent); }
  }
  @media (prefers-reduced-motion: reduce) {
    * { animation:none !important; }
  }

  /* ---- hero: un solo lienzo con modos ---- */
  /* cada pieza marcada m-ind / m-prod / m-can pertenece a un modo; el modo
     activo vive en body[data-modo] y el resto se apaga sin perder su display */
  body:not([data-modo="indices"])   .m-ind  { display:none !important; }
  body:not([data-modo="productos"]) .m-prod { display:none !important; }
  body:not([data-modo="canasta"])   .m-can  { display:none !important; }
  /* la unidad vale para los índices y Comparar: fuera solo en la canasta */
  body[data-modo="canasta"] .m-uni { display:none !important; }
  #vista { opacity:1; transition:opacity .18s ease; }
  /* la barra de controles (~52px) y la línea de la unidad bajo ella
     (--utxt: 27px en una línea, 43px en dos en el celular; en Arma tu
     canasta no está) salen del calc para que hero+barra sigan encuadrando
     la pantalla sin scroll */
  body { --utxt:var(--utxt-medido, 27px); }
  @media (max-width:759px) { body { --utxt:var(--utxt-medido, 43px); } }
  body[data-modo="canasta"] { --utxt:0px; }
  /* altura reservada por CSS antes de que Lightweight Charts monte, y en
     svh donde exista: 100vh cambia con la barra del navegador móvil y ese
     reflow se atribuía a los contenedores de chart (CLS) */
  .hero-wrap { position:relative; height:calc(100vh - 318px - var(--utxt)); min-height:320px;
    background:var(--bg); }
  @supports (height:100svh) {
    .hero-wrap { height:calc(100svh - 318px - var(--utxt)); } }
  /* sobre 640px la fila de navegación del sitio (33px, en el encabezado)
     también sale del calc: 272+33 y 368+33 */
  @media (min-width:760px) {
    .hero-wrap { height:calc(100vh - 305px - var(--utxt)); min-height:420px; }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 305px - var(--utxt)); } } }
  /* móvil: la franja bajo el lienzo (66px, ver .mstrip) y, bajo 641px, la
     segunda fila de tabs (+50px) salen del encuadre para que hero + barras
     sigan cerrando la pantalla sin scroll donde el alto alcance */
  @media (max-width:759px) {
    .hero-wrap { height:calc(100vh - 401px - var(--utxt)); }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 401px - var(--utxt)); } } }
  @media (max-width:640px) {
    .hero-wrap { height:calc(100vh - 419px - var(--utxt)); }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 419px - var(--utxt)); } } }
  @media (max-width:759px) { .overlay .oname, .overlay .cstats, .overlay .caviso,
    .overlay .can-reg { max-width:calc(100vw - 160px); }
    body.tv-ind .overlay.m-ind .oname { max-width:none; } }
  #chart, #pchart, #cchart { position:absolute; inset:0; }
  /* ---- Advanced Charts (índices y Comparar) ---- */
  /* la librería trae su barra arriba y su leyenda: el texto del índice sale
     del lienzo a una franja propia sobre el gráfico, en una fila que se
     envuelve, y el widget ocupa el resto del alto reservado */
  .tvbox { display:none; }
  body.tv-ind .hero-wrap, body.tv-prod .hero-wrap { display:flex; flex-direction:column; }
  body.tv-ind #tvind, body.tv-prod #tvprod { display:block; position:relative;
    flex:1 1 auto; min-height:0; }
  body.tv-ind #chart, body.tv-prod #pchart { display:none; }
  body.tv-ind .overlay.m-ind, body.tv-prod .overlay.m-prod { position:static;
    max-width:none; display:flex; flex-wrap:wrap; align-items:baseline;
    gap:4px 16px; padding:10px clamp(16px,3vw,32px) 9px;
    border-bottom:1px solid var(--line); }
  body.tv-ind .overlay.m-ind .orow, body.tv-ind .overlay.m-ind .overd,
  body.tv-ind .overlay.m-ind .ovs, body.tv-prod .overlay.m-prod .onote { margin-top:0; }
  body.tv-ind .overlay.m-ind .oprice { font-size:clamp(24px,3.4vw,38px); }
  body.tv-ind .overlay.m-ind .oname #osub { display:inline; margin-left:6px; }
  .overlay { position:absolute; left:clamp(12px,2.5vw,32px); top:clamp(12px,2.5vw,26px);
    pointer-events:none; z-index:5; max-width:88%; }
  .overlay .oname { font:500 clamp(10px,1.4vw,12px) var(--mono);
    letter-spacing:.16em; color:var(--ash); text-transform:uppercase; }
  .overlay .oname span { color:var(--dim); text-transform:none; }
  /* el nombre del índice es una etiqueta corta: mono y en mayúsculas, como
     en el ticker; el subtítulo y el rango de años van en texto normal */
  .overlay .oname #oname { text-transform:uppercase; }
  .overlay .oname #osub, .overlay .oname #prod-rango {
    font:400 clamp(11px,1.4vw,13px) var(--sans); letter-spacing:0; }
  .overlay .oname #osub { display:block; margin-top:3px; }
  .orow { display:flex; align-items:baseline; gap:clamp(8px,1.5vw,16px);
    margin-top:4px; flex-wrap:wrap; }
  .oprice { font:700 clamp(34px,6vw,68px)/1 var(--display);
    letter-spacing:-.01em; color:var(--bone); }
  /* en UF, la cifra grande va en UF y debajo, más chica, en pesos de hoy */
  .ocifra { display:flex; flex-direction:column; }
  .opesos { font:400 clamp(11px,1.3vw,13px) var(--sans); color:var(--ash);
    margin-top:6px; }
  .odelta { font:600 clamp(13px,1.6vw,18px) var(--sans); color:var(--ash); }
  .odelta small { font:400 12px var(--sans); color:var(--dim); }
  .overd { display:flex; align-items:center; gap:12px; margin-top:12px; flex-wrap:wrap; }
  .badge { font:600 clamp(11px,1.4vw,13px) var(--mono); letter-spacing:.14em;
    padding:5px 12px; background:var(--verdict); color:var(--bg);
    animation:car-pulse 2.4s ease-in-out infinite; }
  .opct, .ovs { font:400 clamp(11px,1.3vw,13px) var(--sans); color:var(--ash); }
  .ovs { margin-top:8px; }
  .onote { display:inline-block; font:500 12px var(--sans); color:var(--ash);
    border:1px solid var(--line); padding:4px 10px; background:var(--panel);
    margin-top:8px; }
  /* ---- barra de controles: fuera del lienzo, sobre el gráfico ---- */
  /* los controles ya no flotan sobre el chart; viven en una fila propia,
     alineados a la derecha, con scroll horizontal si no caben (móvil) */
  .cbar { display:flex; flex-wrap:wrap; align-items:center; gap:8px 14px;
    min-height:50px; padding:7px clamp(16px,3vw,32px);
    border-bottom:1px solid var(--line);
    overflow-x:auto; overflow-y:hidden; scrollbar-width:none;
    -webkit-overflow-scrolling:touch; }
  .cbar::-webkit-scrollbar { display:none; }
  /* los controles van juntos y nunca quedan fuera de la vista: si las
     ayudas (zoom, velas) no caben a su lado, pasan a una fila arriba de
     ellos, y si ni así caben junto a la unidad, bajan a otra fila */
  .cbar-right { margin-left:auto; display:flex; align-items:center; gap:8px 14px;
    flex-wrap:wrap; justify-content:flex-end; }
  .cbar-right > * { flex:none; }
  .cbar-ctrl { display:flex; align-items:center; gap:14px; }
  /* ---- unidad: pesos de hoy, precio de la época o UF ---- */
  /* tres botones o, si no caben en la fila de controles, el desplegable
     (JS_UNIDAD prueba la fila sin envolver: .midiendo). Bajo la barra, la
     línea de la unidad elegida, que reemplaza a la leyenda de las series */
  .unidad { flex:none; }
  .vtoggle .ubtn { font:500 13px var(--sans); letter-spacing:0; }
  .usel { display:none; font:500 13px var(--sans); color:var(--bone);
    background:var(--bg); border:1px solid var(--line); border-radius:0;
    min-height:34px; padding:0 6px; color-scheme:dark; cursor:pointer; }
  .unidad.compacta .ubtns { display:none; }
  .unidad.compacta .usel { display:block; }
  .midiendo { flex-wrap:nowrap !important; }
  .midiendo .cbar-right { justify-content:flex-start; }
  .urow { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between;
    gap:4px 24px; padding:0 clamp(16px,3vw,32px) 9px; border-bottom:1px solid var(--line); }
  .utxt { flex:1 1 320px; font:400 11px/1.5 var(--sans); color:var(--ash); text-wrap:pretty; }
  /* la leyenda de la línea del índice: las tres unidades, la elegida a la
     vista y las otras atenuadas; en escritorio junto a la línea de la
     unidad, en el celular en la franja bajo el lienzo */
  .legend { display:none; gap:14px; font:400 11px/1.5 var(--sans); color:var(--ash);
    white-space:nowrap; }
  @media (min-width:900px) { .legend { display:flex; } }
  .legend .sw, .mstrip .sw { display:inline-block; width:16px; height:0; margin-right:6px;
    vertical-align:middle; border-top:2px solid var(--ember); }
  /* con la unidad a la vista, su línea va pegada a la barra */
  body:not([data-modo="canasta"]) .cbar { border-bottom:none; padding-bottom:6px; }
  .vtoggle { display:flex; border:1px solid var(--line); background:var(--bg); }
  /* LÍNEA / VELAS son etiquetas cortas en mayúsculas (mono); los botones
     de texto normal (captura PNG) van en la tipografía de la
     interfaz */
  .vbtn { font:600 11px var(--mono); letter-spacing:.1em; padding:8px 14px;
    border:none; cursor:pointer; background:transparent; color:var(--ash); min-height:34px;
    white-space:nowrap; }
  .vbtn + .vbtn { border-left:1px solid var(--line); }
  .vbtn.active { background:var(--bone); color:var(--bg); }
  .nomtoggle { border:1px solid var(--line); background:var(--bg);
    font:500 13px var(--sans); letter-spacing:0; }
  /* celular: la unidad (en el desplegable si los botones no caben),
     LÍNEA / VELAS y la captura van en la fila con botones más justos */
  @media (max-width:640px) {
    .cbar, .cbar-right, .cbar-ctrl { gap:8px 6px; }
    .cbar .vbtn { padding:8px 7px; letter-spacing:.06em; }
    .cbar .nomtoggle { font-size:12px; }
    .cbar .vtoggle .ubtn { letter-spacing:0; padding:8px 10px; }
    .usel { font-size:11px; padding:0 2px; }
  }
  @media (max-width:380px) { .cbar, .urow { padding-left:10px; padding-right:10px; }
    .cbar, .cbar-right, .cbar-ctrl { gap:6px; }
    .cbar .vbtn { padding:8px 6px; } }
  /* referencia de velas y pista de zoom: texto de ayuda dentro de la barra;
     bajo 760px se omiten para no alargar la fila de controles en móvil, y la
     pista de zoom espera a 960px para que en tablets la fila siga siendo una */
  .ref { display:none; max-width:300px; text-wrap:balance;
    font:400 11px/1.5 var(--sans); color:var(--dim); }
  .zoomhint { display:none; max-width:280px; text-wrap:balance;
    font:400 11px/1.5 var(--sans); color:var(--ash); }
  @media (min-width:760px) { .ref { display:block; } }
  @media (min-width:960px) { .zoomhint { display:block; } }
  /* ---- franja móvil bajo el lienzo: leyenda compacta + pista táctil ---- */
  /* bajo 760px ni la leyenda de escritorio (≥900px) ni la pista de zoom de
     la barra existen: esta franja trae ambas en versión corta, fuera del
     lienzo para no taparlo. Primera línea: las tres unidades (la elegida a
     la vista); segunda línea: la pista de gestos. En productos/canasta la
     leyenda (m-ind) se apaga y el min-height mantiene la franja estable;
     altura fija reservada desde el primer paint (CLS) */
  .mstrip { display:none; }
  @media (max-width:759px) {
    .mstrip { display:flex; flex-wrap:wrap; align-content:flex-start;
      align-items:center; gap:4px 14px; min-height:66px;
      padding:7px clamp(16px,3vw,32px);
      font:400 11px/16px var(--sans); color:var(--ash); }
    .mstrip .mleg { white-space:nowrap; }
    .mstrip .mhint { flex-basis:100%; color:var(--dim); text-wrap:balance; }
  }
  .tooltip { position:absolute; display:none; z-index:7; pointer-events:none;
    background:var(--panel); border:1px solid var(--line); padding:8px 12px; white-space:nowrap; }
  .tooltip .tt-d { font:500 11px var(--sans); color:var(--ash); }
  .tooltip .tt-r { font:600 15px var(--sans); color:var(--bone); margin-top:2px; }
  .tooltip .tt-r small { font:400 11px var(--sans); color:var(--ash); }
  .tooltip .tt-n { font:400 12px var(--sans); color:var(--ash); }

  /* ---- franja de contexto ---- */
  /* min-height en las cajas que puebla JS (barras, chips, selector): la
     estructura bajo el hero queda reservada y ni la carga inicial ni el
     cambio de modo desplazan el footer (CLS de #vista) */
  .contexto { display:grid; grid-template-columns:1fr; border-top:1px solid var(--line); }
  @media (min-width:900px) { .contexto { grid-template-columns:480px 1fr; } }
  .ctx-box { padding:clamp(16px,3vw,24px) clamp(16px,3vw,32px); min-height:190px; }
  @media (min-width:900px) { .ctx-box + .ctx-box { border-left:1px solid var(--line); } }
  @media (max-width:899px) { .ctx-box + .ctx-box { border-top:1px solid var(--line); } }
  .ctx-h { font:600 11px var(--mono); letter-spacing:.16em; color:var(--ash); }
  .ctx-h span { font:400 12px var(--sans); color:var(--dim); letter-spacing:0; }
  .bars { display:flex; align-items:flex-end; gap:6px; height:76px; margin-top:16px; }
  .bars .mcol { flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; }
  .bars .bar { width:100%; min-height:3px; background:var(--ash); }
  .bars .ml { font:400 10px var(--sans); color:var(--dim); }
  .frase { font:400 14px/1.55 var(--sans); color:var(--bone); margin-top:16px;
    text-wrap:pretty; }
  .frase b { font-weight:600; color:var(--bone); }
  .comp { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
  .comp .chip { display:flex; align-items:baseline; gap:10px; border:1px solid var(--line);
    padding:9px 14px; background:var(--panel); font:400 13px var(--sans);
    color:var(--bone); }
  .comp .chip b { font-weight:600; }

  /* ---- franja de contexto: productos y canasta ---- */
  .ctx-solo { border-top:1px solid var(--line); min-height:190px;
    padding:clamp(16px,3vw,24px) clamp(16px,3vw,32px) clamp(20px,3vw,28px); }
  /* selector de catálogo: búsqueda + grupos ODEPA colapsables */
  .psearch { width:100%; font:400 14px var(--sans); color:var(--bone);
    background:var(--panel); border:1px solid var(--line); padding:10px 14px;
    margin-bottom:10px; border-radius:0; outline:none; -webkit-appearance:none; }
  .psearch::placeholder { color:var(--dim); }
  .psearch:focus { border-color:var(--dim); }
  .pgroup { border-top:1px solid var(--line); }
  .pg-head { display:flex; align-items:center; gap:8px; width:100%; text-align:left;
    font:600 11px var(--mono); letter-spacing:.14em; color:var(--ash);
    text-transform:uppercase; background:none; border:none; padding:11px 2px;
    min-height:38px; cursor:pointer; }
  .pg-head:hover { color:var(--bone); }
  .pg-n { color:var(--dim); letter-spacing:.04em; }
  .pg-chev { color:var(--dim); transition:transform .15s ease; }
  .pgroup.abierto .pg-chev { transform:rotate(90deg); }
  .pg-body { padding:2px 0 14px; }
  /* colapso con más especificidad que el display:flex de .pchips (el cuerpo
     lleva ambas clases); buscando: los grupos con resultados se abren solos
     y al borrar la búsqueda vuelve el colapso que dejó el usuario */
  .pgroup:not(.abierto):not(.buscando) .pg-body { display:none; }
  .pchips { display:flex; flex-wrap:wrap; gap:8px; }
  .pchip { display:flex; align-items:center; gap:8px; font:500 13px var(--sans);
    padding:7px 12px; min-height:34px; cursor:pointer; background:transparent;
    border:1px solid var(--line); color:var(--ash); }
  .pchip .dot { width:8px; height:8px; border-radius:50%; background:var(--dim); flex:none; }
  .pchip.active { background:var(--panel); color:var(--bone); }
  .can-reg { font:400 12px/1.6 var(--sans); color:var(--ash); margin-top:10px; }
  /* acción principal de la vista: pill como los tabs, en hueso para que
     se lea como botón protagonista */
  .ccopy { font:600 13px var(--sans); padding:8px 16px;
    min-height:34px; cursor:pointer; background:transparent; border:1px solid var(--bone);
    border-radius:999px; color:var(--bone); white-space:nowrap; }
  .ccopy:hover { background:var(--hover); }
  .ccopy.copiado { background:var(--bone); border-color:var(--bone); color:var(--bg); }
  .can-acciones { display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; }
  .citems { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
  .citem { display:flex; flex-direction:column; gap:6px; border:1px solid var(--line);
    background:var(--panel); padding:10px 14px; max-width:100%; }
  .ci-top { display:flex; align-items:center; justify-content:space-between;
    gap:8px 14px; flex-wrap:wrap; }
  .ci-label { font:500 14px var(--sans); color:var(--bone); }
  .ci-step { display:flex; align-items:stretch; border:1px solid var(--line); background:var(--bg); }
  .ci-btn { font:600 16px var(--sans); width:38px; min-height:34px; cursor:pointer;
    background:transparent; border:none; color:var(--bone); }
  .ci-btn:hover { background:var(--hover); }
  .ci-q { font:500 13px var(--sans);
    color:var(--bone); min-width:66px; display:flex; align-items:center;
    justify-content:center; padding:0 6px; border-left:1px solid var(--line);
    border-right:1px solid var(--line); }
  .ci-eq { font:400 12px var(--sans); color:var(--ash); }
  .cstats { font:400 13px/1.5 var(--sans); color:var(--ash); margin-top:8px;
    text-wrap:pretty; }
  .ctemporada { margin-top:2px; }
  .caviso { font:400 12px/1.5 var(--sans); color:var(--ash); margin-top:4px; }

  /* ---- footer: el pie común del sitio (CSS_SITIO, más abajo) ---- */

  .nochart { display:flex; align-items:center; justify-content:center; height:100%;
    color:var(--ash); font-size:13px; padding:20px; text-align:center; }
  /* estado de carga del lienzo: centrado, sin tapar el overlay; el botón
     de reintentar aparece solo si el pedido falló */
  .carga { position:absolute; inset:0; z-index:6; display:flex;
    flex-direction:column; align-items:center; justify-content:center; gap:10px;
    padding:20px; text-align:center; pointer-events:none;
    font:400 12px/1.5 var(--sans); color:var(--ash); }
  .carga[hidden] { display:none; }
  .carga:not(.error) #carga-txt { animation:car-carga 1.2s ease-in-out infinite alternate; }
  .carga:not(.error) button { display:none; }
  .carga button { pointer-events:auto; }
  @keyframes car-carga { from { opacity:.45; } to { opacity:1; } }
__CSS_SITIO__
</style>
</head>
<body data-modo="indices">

  <div class="ticker">
    <div class="tag">ÍNDICES</div>
    <div class="ticker-scroll"><div class="ticker-track" id="ticker-track"></div></div>
  </div>

  <header>
    <div class="brand">
      <!-- un único span envuelve el texto: con flex, los nodos sueltos se
           vuelven flex items y innerText/copy-paste los separa con saltos
           de línea; así el wordmark es UN run inline: "CARESTÍA" -->
      <a class="wordmark" href="https://carestia.cl/"><span>CAREST<span class="i">Í</span>A</span></a>
      <div class="tagline">Índices del costo de vida en Chile</div>
    </div>
    <div class="semana">Semana del <span id="fecha"></span>. <span>Se actualiza los viernes.</span></div>
    __NAV__
  </header>

  <nav class="tabs" id="tabs" aria-label="Índices y herramientas"></nav>

  <div class="cbar" id="cbar">
    <div class="unidad m-uni" id="unidad" data-fila="cbar">
      __SELECTOR_UNIDAD__
    </div>
    <div class="cbar-right">
      <span class="zoomhint">Para acercar, arrastra el eje de los años o el de los precios. En el celular, usa dos dedos.</span>
      <span class="ref m-ind" id="ref-velas"></span>
      <div class="cbar-ctrl">
        <div class="vtoggle m-ind">
          <button class="vbtn active" id="v-linea">LÍNEA</button>
          <button class="vbtn" id="v-velas">VELAS</button>
        </div>
        <button class="vbtn nomtoggle" id="shot">captura PNG</button>
      </div>
    </div>
  </div>
  <div class="urow m-uni">
    <p class="utxt" id="utxt">__UNIDAD_REAL__</p>
    <div class="legend m-ind" id="leyenda">
      __LEYENDA__
    </div>
  </div>

  <div id="vista">
    <section class="hero-wrap" id="hero">
      <div id="chart" class="m-ind"></div>
      <div id="pchart" class="m-prod"></div>
      <div id="cchart" class="m-can"></div>
      <div class="overlay m-ind">
        <div class="oname"><span id="oname"></span> <span id="osub"></span></div>
        <div class="orow">
          <div class="ocifra">
            <div class="oprice" id="oprice"></div>
            <div class="opesos" id="opesos" hidden></div>
          </div>
          <div class="odelta"><span id="odelta"></span> <small>sem.</small></div>
        </div>
        <div class="overd">
          <span class="badge" id="obadge"></span>
          <span class="opct" id="opct"></span>
        </div>
        <div class="ovs" id="ovs"></div>
      </div>
      <div class="overlay m-prod">
        <div class="oname">COMPARAR PRODUCTOS <span id="prod-rango"></span></div>
        <div class="onote" id="onote">Cambio del precio real, en porcentaje</div>
      </div>
      <div class="overlay m-can">
        <div class="oname">ARMA TU CANASTA <span>Y COMPÁRTELA</span></div>
        <div class="orow"><div class="oprice" id="ccosto"></div></div>
        <div class="cstats" id="cstats"></div>
        <div class="cstats ctemporada" id="ctemporada"></div>
        <div class="caviso" id="caviso"></div>
        <div class="can-reg">Esta canasta la armaste tú con datos de ODEPA. No es un índice de Carestía.</div>
      </div>
      <div id="tvind" class="tvbox m-ind"></div>
      <div id="tvprod" class="tvbox m-prod"></div>
      <div class="carga" id="carga" role="status" hidden>
        <span id="carga-txt"></span>
        <button class="vbtn nomtoggle" id="carga-reintentar">Reintentar</button>
      </div>
      <div class="tooltip" id="tooltip">
        <div class="tt-d" id="tt-d"></div>
        <div class="tt-r"><span id="tt-r"></span> <small id="tt-u">pesos de hoy</small></div>
        <div class="tt-n" id="tt-n"></div>
      </div>
    </section>

    <!-- franja móvil (<760px): leyenda compacta del modo índices y pista de
         gestos táctiles del lienzo; en desktop no existe -->
    <div class="mstrip">
      __LEYENDA_MOVIL__
      <span class="mhint">Desliza hacia los lados para moverte. Usa dos dedos para acercar.</span>
    </div>

    <section class="contexto m-ind">
      <div class="ctx-box">
        <div class="ctx-h">ESTACIONALIDAD</div>
        <div class="bars" id="season-bars"></div>
        <div class="frase" id="season-frase"></div>
      </div>
      <div class="ctx-box">
        <div class="ctx-h">COMPONENTES DE LA CANASTA <span>(aporte de cada uno al total)</span></div>
        <div class="comp" id="comp"></div>
      </div>
    </section>

    <section class="ctx-solo m-prod" aria-label="Selección de productos">
      <input class="psearch" id="psearch" type="search" placeholder="busca un producto..." autocomplete="off">
      <div id="pgroups"></div>
    </section>

    <section class="ctx-solo m-can" aria-label="Arma tu canasta">
      <input class="psearch" id="csearch" type="search" placeholder="busca un producto..." autocomplete="off">
      <div id="cgroups"></div>
      <div class="citems" id="citems"></div>
      <div class="can-acciones">
        <button class="ccopy" id="ccopy">copiar link de esta canasta</button>
      </div>
    </section>
  </div>

__PIE__

<script>
  // inline viene solo el primer pantallazo: el resumen de los 4 índices, la
  // serie del primero y la lista de productos sin series. El resto se pide
  // a datos/ al necesitarlo (ver "datos a demanda")
  const DATA = __DATA__;
  const INDICES = DATA.indices;
  const CODES = Object.keys(INDICES);
  const PRODS = DATA.productos || {};

  /* ---------- datos a demanda ---------- */
  // las series llegan compactas: t0 (lunes de la primera semana) y un valor
  // por semana, null donde no hubo dato; se expanden una sola vez
  const DIA = 864e5;
  const semanas = t0 => {
    const base = Date.parse(t0 + 'T00:00:00Z');
    return i => new Date(base + i * 7 * DIA).toISOString().slice(0, 10);
  };
  function expandirIndice(d, s) {
    const t = semanas(s.t0);
    const puntos = arr => arr.reduce((out, v, i) => {
      if (v != null) out.push({ time: t(i), value: v });
      return out;
    }, []);
    d.nominal = puntos(s.nominal);
    d.velas = s.velas.reduce((out, x, i) => {
      if (x) out.push({ time: t(i), open: x[0], high: x[1], low: x[2], close: x[3] });
      return out;
    }, []);
    d.real = puntos(s.real);   // al final: d.real marca el índice como cargado
  }
  // un producto se expande a dos series: real = solo semanas con dato (en la
  // canasta un null cuenta como "sin dato" para la intersección estricta) y
  // gaps = serie completa con puntos whitespace, para que el spaghetti dibuje
  // cortes donde no hubo precio (estacionales)
  function expandirProducto(p, s) {
    const t = semanas(s.t0);
    const real = [], gaps = [];
    s.v.forEach((v, i) => {
      const time = t(i);
      if (v == null) { gaps.push({ time }); return; }
      real.push({ time, value: v });
      gaps.push({ time, value: v });
    });
    p.gaps = gaps;
    p.real = real;
  }
  Object.keys(DATA.series || {}).forEach(c => expandirIndice(INDICES[c], DATA.series[c]));

  // un pedido por archivo; si falla no queda guardado y se puede reintentar.
  // La versión en la URL evita mezclar archivos de dos builds en la caché
  const pedidos = new Map();
  const errores = new Set();
  function pedirJSON(ruta) {
    if (!pedidos.has(ruta)) {
      const p = fetch('datos/' + ruta + '?v=' + DATA.ver).then(r => {
        if (!r.ok) throw new Error(ruta + ': ' + r.status);
        return r.json();
      });
      p.catch(() => pedidos.delete(ruta));
      pedidos.set(ruta, p);
    }
    return pedidos.get(ruta);
  }
  function cargar(clave, ruta, listo, expandir) {
    if (listo()) return Promise.resolve();
    errores.delete(clave);
    return pedirJSON(ruta).then(j => { if (!listo()) expandir(j); },
      e => { errores.add(clave); throw e; });
  }
  const cargarIndice = code => cargar('i:' + code, 'indices/' + code + '.json',
    () => !!INDICES[code].real, j => expandirIndice(INDICES[code], j.serie));
  const cargarProducto = k => cargar('p:' + k, 'productos/' + PRODS[k].slug + '.json',
    () => !!PRODS[k].real, j => expandirProducto(PRODS[k], j));
  // #asado, #ensalada, #fruta, #desayuno abren ese índice (las tarjetas y la
  // cinta de la portada llevan aquí); su serie se pide de inmediato, sin
  // esperar a que cargue la página
  const indiceDelHash = () => {
    const c = location.hash.slice(1);
    return CODES.indexOf(c) !== -1 ? c : null;
  };
  if (indiceDelHash()) cargarIndice(indiceDelHash()).catch(() => {});
  // pide los productos que falten y llama a 'luego' cuando llegaron todos
  function pedirProductos(keys, luego) {
    const faltan = keys.filter(k => PRODS[k] && !PRODS[k].real);
    if (!faltan.length) return;
    Promise.all(faltan.map(cargarProducto)).then(luego, () => {}).finally(pintarCarga);
    pintarCarga();
  }
  const fmt = v => '$' + Math.round(v).toLocaleString('es-CL');
__JS_UNIDAD__
  const MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  // dentro de una frase, el mes con su nombre completo; las abreviaturas
  // quedan solo como etiquetas de las barras
  const MESES_LARGO = ['','enero','febrero','marzo','abril','mayo','junio','julio',
    'agosto','septiembre','octubre','noviembre','diciembre'];
  // nombres de los grupos ODEPA, solo al mostrarlos (las claves no cambian)
  const GRUPO_TXT = __GRUPOS__;
  const grupoTxt = g => GRUPO_TXT[g] || g;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // los colores de los gráficos y de la captura salen de los tokens de :root
  const VARS = getComputedStyle(document.documentElement);
  const tok = n => VARS.getPropertyValue('--' + n).trim();
  const COL = {};
  ['bg', 'bone', 'ash', 'dim', 'line', 'grid', 'ember', 'cruz', 'verde', 'rojo', 'sans']
    .forEach(n => { COL[n] = tok(n); });
  // opciones comunes de los tres lienzos: la rueda acerca y mueve el
  // gráfico, como en Advanced Charts; el deslizamiento vertical en táctil
  // queda para la página y dos dedos acercan. El crosshair va en hueso tenue
  function opcionesChart(extra) {
    extra = extra || {};
    return Object.assign({
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: COL.ash,
        fontFamily: COL.sans },
      grid: { vertLines: { color: COL.grid }, horzLines: { color: COL.grid } },
      rightPriceScale: { borderColor: COL.line },
      timeScale: { borderColor: COL.line },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: true, vertTouchDrag: false,
        horzTouchDrag: true, pressedMouseMove: true },
      crosshair: { mode: 0,
        vertLine: { color: COL.cruz, labelBackgroundColor: COL.line },
        horzLine: { color: COL.cruz, labelBackgroundColor: COL.line } },
    }, extra, {
      // fechas del eje y del crosshair siempre en castellano de Chile, sin
      // depender del idioma del navegador
      localization: Object.assign({ locale: 'es-CL' }, extra.localization),
    });
  }

  /* ---------- motor: Advanced Charts, con respaldo en Lightweight ---------- */
  // índices y Comparar van en Advanced Charts, un widget para cada uno que se
  // monta la primera vez que su modo está a la vista; Arma tu canasta sigue
  // en Lightweight. Si la librería no está o un widget no inicia en 8
  // segundos, ese modo dibuja con Lightweight como siempre
  const LIBRERIA = '/charting_library/';
  const TV_CSS = '/__TV_CSS__?v=__VER_CSS__';
  let TV = null, feed = null;
  const tv = { indices: { estado: 'nada', caja: 'tvind', clase: 'tv-ind', dato: 'motorIndices' },
               productos: { estado: 'nada', caja: 'tvprod', clase: 'tv-prod', dato: 'motorProductos' } };
  const tvListo = m => tv[m].estado === 'listo';
  const usaLW = m => tv[m].estado === 'falla';
  // la librería devuelve el símbolo en mayúsculas y a veces con la fuente
  const sinFuente = t => String(t || '').split(':').pop().toLowerCase();
  // en el load: carestia-tv.js y Lightweight llegan con defer
  function prepararTV() {
    TV = window.CarestiaTV || null;
    if (!TV) {
      ['indices', 'productos'].forEach(m => { tv[m].estado = 'falla'; document.body.dataset[tv[m].dato] = 'lightweight'; });
      return;
    }
    // el índice que viene inline y los productos de la página no se piden
    const precargados = {};
    Object.keys(DATA.series || {}).forEach(c => {
      precargados['indices/' + c + '.json'] = { serie: DATA.series[c] };
    });
    feed = TV.crearDatafeed({ base: '/datos/', ver: DATA.ver, precargados, uf: DATA.uf,
      // los mismos pedidos de la página: un archivo de datos/ se baja una vez
      pedir: pedirJSON,
      indices: CODES.map(c => ({ codigo: c, nombre: INDICES[c].nombre })),
      productos: Object.keys(PRODS).map(k => ({ slug: PRODS[k].slug, nombre: PRODS[k].label,
        unidad: PRODS[k].unidad, grupo: PRODS[k].grupo })) });
    TV.cargarLibreria(LIBRERIA).catch(() => {});   // empieza a bajar de inmediato
  }
  function montarTV(m) {
    const e = tv[m];
    if (!TV || e.estado !== 'nada') return;
    e.estado = 'cargando';
    document.body.dataset[e.dato] = 'cargando';
    // la caja a la vista y con su tamaño final desde antes de crear el
    // widget: oculta, la librería mide cero y el rango inicial no queda
    document.body.classList.add(e.clase);
    pintarCarga();
    const caja = document.getElementById(e.caja);
    const primero = m === 'productos' ? elegidosEnOrden()[0] || Object.keys(PRODS)[0] : null;
    TV.montar({ contenedor: caja, libreria: LIBRERIA, datafeed: feed, tok, sitio: true,
      css: location.origin + TV_CSS,
      simbolo: m === 'indices' ? simboloIndice(cur) : PRODS[primero].slug + SUF[unidad],
      // Comparar pone sus propios colores
      estilo: m === 'indices' })
      .then(w => {
        e.w = w;
        e.estado = 'listo';
        document.body.dataset[e.dato] = 'advanced';
        if (m === 'indices') {
          // si la persona cambia el tipo desde la barra de la librería, los
          // botones LÍNEA / VELAS la siguen
          w.activeChart().onChartTypeChanged().subscribe(null, t => {
            if (t === 1 || t === 2) vista = t === 2 ? 'linea' : 'velas';
            aplicarVista();   // otro tipo (área, barras...): ningún botón activo
          });
          // la referencia de las velas cambia con la temporalidad
          w.activeChart().onIntervalChanged().subscribe(null, () => setTimeout(() => aplicarVista(), 0));
          pintarSerie(cur);
          // lo que se haya elegido con los botones mientras la librería cargaba
          aplicarVista(true);
        } else syncProductos();
        pintarCarga();
      }, () => {
        e.estado = 'falla';
        caja.remove();
        document.body.classList.remove(e.clase);
        document.body.dataset[e.dato] = 'lightweight';
        if (m === 'indices') { initChart(); pintarSerie(cur); }
        else { initPChart(); syncProductos(); }
        pintarCarga();
      });
  }
  const simboloIndice = code => code + SUF[unidad];
  function ponerSimbolo(w, sim) {
    const c = w.activeChart();
    if (sinFuente(c.symbol()) === sim) return Promise.resolve();
    return Promise.resolve(c.setSymbol(sim)).catch(() => {});
  }

  // todos los gráficos parten en línea y en pesos de hoy; las velas (las de
  // ODEPA, del más bajo al más alto) quedan a un clic
  let cur = CODES[0], vista = 'linea', unidad = 'real';
  let chart, sLinea, sCandle, pchart;
  let mapaUnidad = new Map(), mapaReal = new Map(), mapaEpoca = new Map();
  // en Lightweight, la unidad de lo que está dibujado (cambia al llegar sus
  // semanas, no al elegirla)
  let unidadLW = 'real';
  const dia = ms => new Date(ms).toISOString().slice(0, 10);
  const SEMANA_MS = 7 * DIA;
  // en Comparar, el cambio del precio en la unidad elegida
  const ONOTE = { real: 'Cambio del precio real, en porcentaje',
    epoca: 'Cambio del precio de la época, en porcentaje',
    uf: 'Cambio del precio en UF, en porcentaje' };

  // variación de las dos últimas semanas: viene calculada en el resumen,
  // así el ticker no necesita las series
  const deltaSemanal = d => d.delta;
  // C1: flechas en ceniza, nunca verde/rojo
  function fmtDelta(x) {
    if (x == null) return '·';
    return (x < 0 ? '▼' : '▲') + Math.abs(x).toFixed(1).replace('.', ',') + '%';
  }
  const tstr = t => typeof t === 'string' ? t :
    t.year + '-' + String(t.month).padStart(2, '0') + '-' + String(t.day).padStart(2, '0');
  const ddmmyyyy = t => t.split('-').reverse().join('-');

  /* ---------- ticker ---------- */
  const track = document.getElementById('ticker-track');
  function buildTicker() {
    track.innerHTML = '';
    for (let rep = 0; rep < 2; rep++) {
      CODES.forEach(code => {
        const d = INDICES[code];
        const b = document.createElement('button');
        b.className = 'titem';
        b.setAttribute('aria-label', d.nombre);
        const nombre = d.nombre.replace(/^Índice /i, '').toUpperCase();
        b.innerHTML = '<span class="tn">' + nombre + '</span>' +
          '<span class="tp">' + fmt(d.costo_real) + '</span>' +
          '<span class="td">' + fmtDelta(deltaSemanal(d)) + '</span>';
        b.onclick = () => render(code);
        track.appendChild(b);
      });
    }
  }

  const tscroll = document.querySelector('.ticker-scroll');
  tscroll.addEventListener('touchstart',
    () => tscroll.classList.add('tocado'), { passive: true });
  ['touchend', 'touchcancel'].forEach(ev => tscroll.addEventListener(ev,
    () => tscroll.classList.remove('tocado'), { passive: true }));

  /* ---------- tabs: índices + modos del lienzo ---------- */
  const tabsEl = document.getElementById('tabs');
  function buildTabs() {
    tabsEl.innerHTML = '';
    CODES.forEach(code => {
      const b = document.createElement('button');
      b.className = 'tab';
      b.dataset.code = code;
      b.textContent = INDICES[code].nombre.replace(/^Índice /i, '');
      b.onclick = () => render(code);
      // con el puntero encima ya se pide la serie: al hacer clic suele estar
      b.addEventListener('pointerenter', () => cargarIndice(code).catch(() => {}));
      tabsEl.appendChild(b);
    });
    if (!Object.keys(PRODS).length) return;   // sin productos no hay más modos
    // pills de modo: no son índices, van tras un separador fino
    const sep = document.createElement('span');
    sep.className = 'tab-sep';
    tabsEl.appendChild(sep);
    [['productos', 'Comparar productos'], ['canasta', 'Arma tu canasta']].forEach(([m, label]) => {
      const p = document.createElement('button');
      p.className = 'tab';
      p.dataset.modo = m;
      p.innerHTML = '<span class="tdot" aria-hidden="true"></span>' + label;
      p.onclick = () => setModo(m);
      tabsEl.appendChild(p);
    });
  }
  // modo: qué herramienta ocupa el lienzo del hero; las tabs lo cambian
  // EN EL LUGAR, sin scroll
  let modo = 'indices';
  function syncTabs() {
    tabsEl.querySelectorAll('.tab').forEach(b =>
      b.classList.toggle('active', modo === 'indices' ?
        b.dataset.code === cur : b.dataset.modo === modo));
  }
  // el gráfico Lightweight del modo (null si el modo va en Advanced Charts)
  function chartActivo() {
    return modo === 'productos' ? pchart : modo === 'canasta' ? cchart : chart;
  }
  // el widget de Advanced Charts del modo, si está listo
  const widgetActivo = () => (modo === 'indices' || modo === 'productos') && tvListo(modo) ?
    tv[modo].w : null;
  // navegación del sitio: en /graficos.html, Índices / Comparar / Arma tu
  // canasta del encabezado cambian el modo EN EL LUGAR, igual que las tabs
  // (sin recargar y aunque el hash ya sea el mismo); sin JS, o sin
  // productos, siguen siendo links normales a los deep links
  function syncNav() {
    document.querySelectorAll('.sitenav a[data-modo]').forEach(a => {
      if (a.dataset.modo === modo) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }
  document.querySelectorAll('.sitenav a[data-modo]').forEach(a => {
    a.addEventListener('click', e => {
      const m = a.dataset.modo;
      if (m !== 'indices' && !Object.keys(PRODS).length) return;
      e.preventDefault();
      if (m === 'indices') { if (modo !== 'indices') render(cur); }
      else setModo(m);
      const menu = a.closest('details');
      if (menu) menu.open = false;
    });
  });
  function setModo(m) {
    const cambio = modo !== m;
    modo = m;
    document.body.dataset.modo = m;
    syncTabs();
    syncNav();
    pintarCarga();
    // la fila de controles cambia con el modo: ¿caben los tres botones?
    selector.medir();
    // el widget del modo se monta la primera vez que está a la vista; después
    // de los deep links del load (que pueden cambiar el modo de entrada)
    if ((m === 'indices' || m === 'productos') && tv[m].estado === 'nada') {
      setTimeout(() => { if (modo === m) montarTV(m); }, 0);
    }
    if (!cambio) return;
    // los productos de Comparar y de la canasta se piden al entrar al modo
    if (m === 'productos') syncProductos();
    else if (m === 'canasta') syncCanasta();
    // el chart recién mostrado estuvo en display:none: esperar a que el
    // ResizeObserver de autoSize le dé tamaño y recién ahí re-encuadrar,
    // recuperando la autoescala si el usuario arrastró el eje de precios
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const ch = chartActivo();
      if (!ch) return;
      ch.priceScale('right').applyOptions({ autoScale: true });
      ch.timeScale().fitContent();
    }));
  }

  /* ---------- hero chart (respaldo con Lightweight) ---------- */
  // una línea y unas velas con las semanas de la unidad elegida
  function initChart() {
    const el = document.getElementById('chart');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos (revisa la conexión).</div>';
      return;
    }
    // el eje en pesos o, en UF, con sus decimales (los de la unidad dibujada)
    chart = LightweightCharts.createChart(el, opcionesChart({ localization: {
      priceFormatter: v => unidadLW === 'uf' && TV ? TV.numUF(v) : fmt(v) } }));
    // la línea de los índices oficiales: el único lugar de la brasa en los gráficos
    sLinea = chart.addLineSeries({ color: COL.ember, lineWidth: 2, priceLineVisible: false });
    // C2: convención estándar de trading, verde sube y rojo baja
    sCandle = chart.addCandlestickSeries({
      upColor: COL.verde, downColor: COL.rojo, borderVisible: false,
      wickUpColor: COL.verde, wickDownColor: COL.rojo, visible: false });
    chart.subscribeCrosshairMove(onCrosshair);
  }

  // la semana bajo el cursor: su valor en la unidad elegida y, abajo, en
  // pesos de hoy (o a precio de la época, si la unidad es pesos de hoy)
  const UNIDAD_TT = { real: 'pesos de hoy', epoca: 'precio de la época', uf: '' };
  const tooltip = document.getElementById('tooltip');
  function onCrosshair(param) {
    const el = document.getElementById('chart');
    if (!param.time || !param.point || param.point.x < 0) {
      tooltip.style.display = 'none';
      return;
    }
    const t = tstr(param.time);
    const uv = mapaUnidad.get(t);
    if (uv == null) { tooltip.style.display = 'none'; return; }
    const u = unidadLW, otra = u === 'real' ? mapaEpoca.get(t) : mapaReal.get(t);
    document.getElementById('tt-d').textContent = ddmmyyyy(t);
    document.getElementById('tt-r').textContent = u === 'uf' ? TV.textoUF(uv) : fmt(uv);
    document.getElementById('tt-u').textContent = UNIDAD_TT[u];
    document.getElementById('tt-n').textContent = (otra != null ? fmt(otra) : '·') +
      (u === 'real' ? ' precio de la época' : ' pesos de hoy');
    tooltip.style.display = 'block';
    const w = tooltip.offsetWidth, cw = el.clientWidth;
    let x = param.point.x + 14;
    if (x + w > cw - 8) x = param.point.x - w - 14;
    tooltip.style.left = Math.max(8, x) + 'px';
    tooltip.style.top = Math.min(param.point.y + 14, el.clientHeight - 80) + 'px';
  }

  // la referencia de las velas: en semanas, la frase completa; en las
  // temporalidades largas cada vela junta varias semanas y queda la mecha
  const REF_VELAS = 'Velas semanales. La mecha va del precio más bajo al más alto que ODEPA encontró entre los locales encuestados.';
  function refVelas(w) {
    const p = w && TV ? TV.temporalidad(w.activeChart().resolution()) : null;
    return !p || p.nombre === TV.RESOLUCION ? REF_VELAS : REF_VELAS.replace('Velas semanales. ', '');
  }
  // LÍNEA / VELAS. En Advanced Charts los botones del sitio ('forzar')
  // cambian el tipo de gráfico; si no, se respeta el que tenga, también uno
  // elegido en la barra de la librería (área, barras...), y los botones solo
  // lo reflejan. En Lightweight muestra la línea o las velas de la unidad
  function aplicarVista(forzar) {
    const linea = vista === 'linea', w = tvListo('indices') ? tv.indices.w : null;
    if (w) {
      const c = w.activeChart(), pedido = linea ? 2 : 1;
      if (forzar && c.chartType() !== pedido) Promise.resolve(c.setChartType(pedido)).catch(() => {});
      const tipo = forzar ? pedido : c.chartType();
      document.getElementById('v-linea').classList.toggle('active', tipo === 2);
      document.getElementById('v-velas').classList.toggle('active', tipo === 1);
      document.getElementById('ref-velas').textContent = tipo === 1 ? refVelas(w) : '';
      return;
    }
    document.getElementById('v-linea').classList.toggle('active', linea);
    document.getElementById('v-velas').classList.toggle('active', !linea);
    document.getElementById('ref-velas').textContent = linea ? '' : refVelas(w);
    if (!chart) return;
    sLinea.applyOptions({ visible: linea });
    sCandle.applyOptions({ visible: !linea });
    chart.timeScale().fitContent();
  }
  document.getElementById('v-linea').onclick = () => { vista = 'linea'; aplicarVista(true); };
  document.getElementById('v-velas').onclick = () => { vista = 'velas'; aplicarVista(true); };

  /* ---------- unidad: pesos de hoy, precio de la época o UF ---------- */
  // vale para los índices y para Comparar. En Advanced Charts cada unidad
  // es otro símbolo; en Lightweight, otras semanas para la línea y las velas.
  // Sin carestia-tv.js (que calcula la época y la UF) solo hay pesos de hoy
  const unidadesHay = () => !feed ? ['real'] : DATA.uf ? ['real', 'epoca', 'uf'] : ['real', 'epoca'];
  // la leyenda de la línea del índice (escritorio y franja del celular): las
  // unidades que hay, la elegida a la vista y las otras atenuadas
  function pintarLeyenda() {
    const hay = unidadesHay();
    document.querySelectorAll('[data-leyenda]').forEach(e => {
      e.hidden = hay.indexOf(e.dataset.leyenda) === -1;
      e.style.opacity = e.dataset.leyenda === unidad ? '' : '.35';
    });
  }
  function ponerUnidad(u) {
    if (unidadesHay().indexOf(u) === -1) u = 'real';
    unidad = u;
    selector.poner(u);
    pintarLeyenda();
    document.getElementById('onote').textContent = ONOTE[u];
    pintarCifra();
    pintarSerie(cur);
    syncProductos();
  }
  const selector = selectorUnidad(ponerUnidad);
  // la línea de la unidad ocupa una, dos o tres líneas según el ancho y la
  // unidad: su alto medido (--utxt-medido) sale del alto del lienzo, para
  // que hero y barras sigan cerrando la pantalla; antes de medir, el CSS
  if (typeof ResizeObserver === 'function') {
    const urow = document.querySelector('.urow');
    new ResizeObserver(() => {
      if (urow.offsetHeight) document.body.style.setProperty('--utxt-medido', urow.offsetHeight + 'px');
    }).observe(urow);
  }

  /* ---------- count-up del precio (~600ms) ---------- */
  // cifraGen corta una animación en curso cuando otra cifra la reemplaza
  let lastPrice = 0, cifraGen = 0;
  function countUp(el, to) {
    const gen = ++cifraGen;
    if (reduced) { el.textContent = fmt(to); lastPrice = to; return; }
    const from = lastPrice, t0 = performance.now();
    (function step(t) {
      if (gen !== cifraGen) return;
      const p = Math.min(1, (t - t0) / 600);
      const e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step); else lastPrice = to;
    })(t0);
  }

  /* ---------- estacionalidad ---------- */
  function renderEstacional(d) {
    const e = d.estacionalidad || {};
    const frase = document.getElementById('season-frase');
    const cont = document.getElementById('season-bars');
    cont.innerHTML = '';
    if (!e.factores) { frase.textContent = ''; return; }
    const nombre = d.nombre.replace(/^Índice /i, '').toLowerCase();
    const fem = /a$/.test(nombre);   // la ensalada, la fruta / el asado, el desayuno
    frase.innerHTML = (fem ? 'La ' : 'El ') + nombre + ' suele estar más ' +
      (fem ? 'barata' : 'barato') + ' en <b>' + MESES_LARGO[e.mes_barato] +
      '</b> y más ' + (fem ? 'cara' : 'caro') + ' en <b>' + MESES_LARGO[e.mes_caro] +
      '</b>. La diferencia entre esos meses es de ' + e.amplitud + '%.';
    const vals = Object.values(e.factores);
    const maxDev = Math.max(...vals.map(v => Math.abs(v - 1))) || 0.01;
    for (let m = 1; m <= 12; m++) {
      const f = e.factores[m] != null ? e.factores[m] : 1;
      const dev = f - 1;
      const col = document.createElement('div'); col.className = 'mcol';
      const bar = document.createElement('div'); bar.className = 'bar';
      bar.style.height = (6 + Math.abs(dev) / maxDev * 50) + 'px';
      bar.style.background = dev >= 0 ? COL.bone : COL.dim;
      bar.title = MESES[m] + ': ' + (dev >= 0 ? '+' : '') + Math.round(dev * 100) + '%';
      const lab = document.createElement('div'); lab.className = 'ml';
      lab.textContent = MESES[m];
      if (m === e.mes_caro || m === e.mes_barato) lab.style.color = COL.bone;
      col.appendChild(bar); col.appendChild(lab); cont.appendChild(col);
    }
  }

  /* ---------- render de un índice ---------- */
  // el último cierre de un índice en una unidad: la cifra en UF y el
  // encabezado de la captura
  function ultimoCierre(code, u) {
    if (feed) return feed.barras(code + SUF[u]).then(b => b && b.length ? b[b.length - 1].close : null);
    return Promise.resolve(u === 'real' ? INDICES[code].costo_real : null);
  }
  // la cifra grande: en pesos de hoy (también con el precio de la época, que
  // en la última semana es el mismo) o, en UF, la del índice en UF y debajo,
  // más chica, la de pesos de hoy
  function pintarCifra() {
    const code = cur, d = INDICES[code];
    const oprice = document.getElementById('oprice'), opesos = document.getElementById('opesos');
    // primero la de pesos de hoy del índice elegido (la que queda si la UF
    // no llega); en UF se reemplaza al llegar
    opesos.hidden = true;
    countUp(oprice, d.costo_real);
    if (unidad !== 'uf') return;
    ultimoCierre(code, 'uf').then(x => {
      if (cur !== code || unidad !== 'uf' || x == null) return;
      cifraGen++;   // la cifra en pesos que venía animándose ya no va
      oprice.textContent = TV.textoUF(x);
      opesos.textContent = fmt(d.costo_real) + ' en pesos de hoy';
      opesos.hidden = false;
    }, () => {});
  }
  const fmtQty = q => String(q).replace('.', ',');
  function aplicar(code) {
    const d = INDICES[code];
    document.documentElement.style.setProperty('--verdict', d.color);
    document.getElementById('fecha').textContent = d.fecha;
    document.getElementById('oname').textContent = d.nombre.replace(/^Índice /i, '');
    document.getElementById('osub').textContent = d.subtitulo;
    pintarCifra();
    document.getElementById('odelta').textContent = fmtDelta(deltaSemanal(d));
    document.getElementById('obadge').textContent = d.veredicto;
    document.getElementById('obadge').style.background = d.color;
    document.getElementById('opct').textContent =
      'percentil ' + d.percentil + ' de ' + d.n + ' semanas';
    document.getElementById('ovs').textContent =
      (d.vs_promedio >= 0 ? '+' : '') + d.vs_promedio +
      (d.vs_promedio >= 0 ? '% sobre' : '% bajo') +
      ' su promedio histórico, en pesos de hoy';
    pintarSerie(code);
    renderEstacional(d);
    const comp = document.getElementById('comp');
    comp.innerHTML = '';
    (d.componentes || []).forEach(c => {
      if (c.aporte == null) return;
      const chip = document.createElement('div'); chip.className = 'chip';
      chip.innerHTML = c.label + ' (' + fmtQty(c.qty) + ' ' + c.unidad + '): <b>' +
        fmt(c.aporte) + '</b>';
      comp.appendChild(chip);
    });
  }

  // la serie del índice: si aún no llega, el lienzo queda vacío con su
  // estado de carga y se dibuja al llegar (si el índice sigue elegido)
  function pintarSerie(code) {
    if (!usaLW('indices')) {
      // Advanced Charts: el mismo widget, con el símbolo del índice
      if (tvListo('indices')) { ponerSimbolo(tv.indices.w, simboloIndice(code)); aplicarVista(); }
      pintarCarga();
      return;
    }
    const d = INDICES[code];
    if (!d.real) {
      mapaUnidad = new Map(); mapaReal = new Map(); mapaEpoca = new Map();
      tooltip.style.display = 'none';
      if (chart) { sLinea.setData([]); sCandle.setData([]); }
      cargarIndice(code).then(() => { if (cur === code) pintarSerie(code); }, () => {})
        .finally(pintarCarga);
      pintarCarga();
      return;
    }
    mapaReal = new Map(d.real.map(p => [p.time, p.value]));
    mapaEpoca = new Map(d.nominal.map(p => [p.time, p.value]));
    const u = unidad;
    semanasLW(code, u).then(([linea, velas]) => {
      if (cur !== code || unidad !== u || !chart) return;
      unidadLW = u;
      mapaUnidad = new Map(linea.map(p => [p.time, p.value]));
      // si el usuario arrastró el eje de precios, autoScale quedó apagado
      // y la serie nueva caería fuera del encuadre
      chart.priceScale('right').applyOptions({ autoScale: true });
      const formato = u === 'uf' ? { type: 'price', precision: 4, minMove: 0.0001 } :
        { type: 'price', precision: 0, minMove: 1 };
      sLinea.applyOptions({ priceFormat: formato });
      sCandle.applyOptions({ priceFormat: formato });
      sLinea.setData(linea);
      sCandle.setData(velas);
      aplicarVista();
    }, () => {
      // sin las semanas de esa unidad, el selector vuelve a la dibujada
      if (cur === code && unidad === u && u !== unidadLW) ponerUnidad(unidadLW);
    });
    pintarCarga();
  }
  // la línea y las velas del índice en una unidad, con la fecha como texto:
  // pesos de hoy desde su serie; precio de la época y UF, del datafeed
  function semanasLW(code, u) {
    const d = INDICES[code];
    if (u === 'real' || !feed) return Promise.resolve([d.real, d.velas || []]);
    return feed.barras(code + SUF[u]).then(b => {
      const velas = (b || []).map(x => Object.assign({}, x, { time: dia(x.time) }));
      return [velas.map(x => ({ time: x.time, value: x.close })), velas];
    });
  }

  /* ---------- estado de carga del lienzo ---------- */
  // mientras falte alguna serie del modo activo, "Cargando datos..." sobre
  // el lienzo; si un pedido falló, el aviso con un botón para reintentar
  const cargaEl = document.getElementById('carga');
  function faltantes() {
    if ((modo === 'indices' || modo === 'productos') && !usaLW(modo)) {
      return tvListo(modo) ? [] : ['tv'];
    }
    if (modo === 'indices') return INDICES[cur].real ? [] : ['i:' + cur];
    const keys = modo === 'productos' ? [...psel] : [...canasta.keys()];
    return keys.filter(k => PRODS[k] && !PRODS[k].real).map(k => 'p:' + k);
  }
  function pintarCarga() {
    const faltan = faltantes();
    const fallo = faltan.some(c => errores.has(c));
    cargaEl.hidden = !faltan.length;
    cargaEl.classList.toggle('error', fallo);
    document.getElementById('carga-txt').textContent = fallo ?
      'No se pudieron cargar los datos.' : 'Cargando datos...';
  }
  document.getElementById('carga-reintentar').onclick = () => {
    if (modo === 'indices') pintarSerie(cur);
    else if (modo === 'productos') syncProductos();
    else syncCanasta();
  };

  const vistaEl = document.getElementById('vista');
  function render(code, primera) {
    cur = code;
    setModo('indices');   // elegir un índice también fija el modo del lienzo
    if (primera || reduced) { aplicar(code); return; }
    vistaEl.style.opacity = 0;                       // crossfade al cambiar índice
    setTimeout(() => { aplicar(code); vistaEl.style.opacity = 1; }, 180);
  }

  /* ---------- vista Productos ---------- */
  // C3: cuatro tonos propios (tokens --cmp1 a --cmp4); del 5º al 8º
  // producto se repiten con línea punteada. El estilo va por orden de
  // selección: cada producto toma el primer puesto libre y lo conserva
  // mientras siga elegido, así dos productos nunca comparten estilo y los
  // que ya están no cambian de color. Máximo 8 a la vez
  const PALETTE = [1, 2, 3, 4].map(i => tok('cmp' + i));
  const PMAX = PALETTE.length * 2;
  const PKEYS = Object.keys(PRODS);
  const puestos = new Map();          // clave -> puesto 0..7
  const estiloDe = k => {
    const i = puestos.get(k);
    return { color: PALETTE[i % PALETTE.length], punteada: i >= PALETTE.length };
  };

  /* ---------- selector de catálogo: búsqueda + grupos colapsables ---------- */
  const sinTildes = s =>
    s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  // los productos de las canastas oficiales van primero dentro de su grupo
  const OFICIALES = new Set();
  CODES.forEach(c => (INDICES[c].componentes || []).forEach(x =>
    OFICIALES.add(sinTildes(x.label).trim().replace(/ /g, '_'))));
  const GRUPOS = [...new Set(PKEYS.map(k => PRODS[k].grupo || 'Otros'))];
  const esMovil = window.matchMedia('(max-width:759px)').matches;

  function buildSelector(idCaja, idBusca, hacerChip) {
    const caja = document.getElementById(idCaja);
    caja.innerHTML = '';
    const grupos = [];
    GRUPOS.forEach((g, gi) => {
      const keys = PKEYS.filter(k => (PRODS[k].grupo || 'Otros') === g)
        .sort((a, b) => (OFICIALES.has(b) ? 1 : 0) - (OFICIALES.has(a) ? 1 : 0));
      if (!keys.length) return;
      const box = document.createElement('div'); box.className = 'pgroup';
      const head = document.createElement('button'); head.className = 'pg-head';
      head.innerHTML = '<span class="pg-chev" aria-hidden="true">▸</span>' + grupoTxt(g) +
        ' <span class="pg-n">(' + keys.length + ')</span>';
      const body = document.createElement('div'); body.className = 'pg-body pchips';
      const chips = keys.map(k => {
        const b = hacerChip(k);
        b.dataset.buscar = sinTildes(PRODS[k].label);
        body.appendChild(b);
        return b;
      });
      // colapsados por defecto en móvil; en desktop abren los 2 primeros
      let abierto = !esMovil && gi < 2;
      box.classList.toggle('abierto', abierto);
      head.onclick = () => {
        abierto = !abierto;
        box.classList.toggle('abierto', abierto);
      };
      box.appendChild(head); box.appendChild(body); caja.appendChild(box);
      grupos.push({ box, chips });
    });
    const input = document.getElementById(idBusca);
    input.oninput = () => {
      const q = sinTildes(input.value.trim());
      grupos.forEach(gr => {
        let vivos = 0;
        gr.chips.forEach(ch => {
          const ok = !q || ch.dataset.buscar.indexOf(q) !== -1;
          ch.style.display = ok ? '' : 'none';
          if (ok) vivos++;
        });
        gr.box.classList.toggle('buscando', !!q);
        gr.box.style.display = (q && !vivos) ? 'none' : '';
      });
    };
  }
  const psel = new Set();
  function elegir(k) {
    const usados = new Set(puestos.values());
    let i = 0;
    while (usados.has(i)) i++;
    puestos.set(k, i);
    psel.add(k);
  }
  function soltar(k) { psel.delete(k); puestos.delete(k); }
  ['asado_de_tira', 'palta', 'huevo_color'].forEach(w => {
    if (PRODS[w]) { elegir(w); return; }
    const alt = PKEYS.find(k => k.indexOf(w.split('_')[0]) === 0);
    if (alt) elegir(alt);
  });
  const ppaints = [];
  const pseries = new Map();

  function initPChart() {
    const el = document.getElementById('pchart');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos.</div>';
      return;
    }
    // misma política de gestos que el hero; modo percentage: rebase
    // automático a la ventana visible
    pchart = LightweightCharts.createChart(el, opcionesChart({
      rightPriceScale: { mode: LightweightCharts.PriceScaleMode.Percentage,
        borderColor: COL.line },
    }));
  }

  // los elegidos en el orden de sus puestos (color 1, color 2, ...)
  const elegidosEnOrden = () => [...psel].filter(k => PRODS[k])
    .sort((a, b) => puestos.get(a) - puestos.get(b));

  // Comparar en Advanced Charts: el primer elegido es la serie principal y el
  // resto va con la comparación de la librería, en escala porcentual, con los
  // colores de cada puesto (del 5º al 8º, punteados), todos en la unidad
  // elegida. Los cambios van en fila para que dos clics rápidos no se crucen
  const comparados = new Map();       // clave -> { id del estudio Compare, símbolo }
  let filaComparar = Promise.resolve();
  function compararTV() {
    filaComparar = filaComparar.then(compararAhora, compararAhora);
    return filaComparar;
  }
  async function compararAhora() {
    const w = tv.productos.w, c = w.activeChart(), serie = c.getSeries();
    const elegidos = elegidosEnOrden();
    // el símbolo de un producto en la unidad elegida
    const sim = k => PRODS[k].slug + SUF[unidad];
    // fuera los que ya no están y los que quedaron en otra unidad
    const quitar = keep => [...comparados].forEach(([k, x]) => {
      if (keep.includes(k) && x.sim === sim(k)) return;
      try { c.removeEntity(x.id); } catch (e) {}
      comparados.delete(k);
    });
    if (!elegidos.length) { quitar([]); serie.setVisible(false); return; }
    const [primero, ...resto] = elegidos;
    quitar(resto);
    if (sinFuente(c.symbol()) !== sim(primero)) {
      await Promise.resolve(c.setSymbol(sim(primero))).catch(() => {});
    }
    serie.setVisible(true);
    const e0 = estiloDe(primero);
    w.applyOverrides({ 'mainSeriesProperties.lineStyle.colorType': 'solid',
      'mainSeriesProperties.lineStyle.color': e0.color,
      'mainSeriesProperties.lineStyle.linestyle': e0.punteada ? 1 : 0,
      'mainSeriesProperties.lineStyle.linewidth': 2 });
    if (c.chartType() !== 2) await Promise.resolve(c.setChartType(2)).catch(() => {});
    for (const k of resto) {
      if (comparados.has(k)) continue;
      const e = estiloDe(k);
      try {
        const s = sim(k);
        const id = await c.createStudy('Compare', false, false,
          { source: 'close', symbol: s },
          { 'plot.color': e.color, 'plot.linestyle': e.punteada ? 1 : 0, 'plot.linewidth': 2 });
        if (id) comparados.set(k, { id, sim: s });
      } catch (err) {}
    }
    // cambio del precio en porcentaje, como siempre en Comparar
    const escala = c.getPanes()[0].getMainSourcePriceScale();
    if (escala && escala.getMode() !== 2) escala.setMode(2);
  }

  function syncProductos() {
    if (!usaLW('productos')) {
      if (tvListo('productos')) compararTV().then(pintarCarga);
      pintarCarga();
      return;
    }
    if (!pchart) return;
    // las series que falten se piden solo con Comparar a la vista; al
    // llegar todas, vuelve a sincronizar
    if (modo === 'productos') pedirProductos([...psel], syncProductos);
    PKEYS.forEach(k => {
      const on = psel.has(k);
      if (on && !PRODS[k].real) return;   // aún no llega: se agrega al llegar
      const x = pseries.get(k);
      if (on && (!x || x.unidad !== unidad)) {
        let s = x && x.s;
        if (!s) {
          const e = estiloDe(k);
          s = pchart.addLineSeries({ color: e.color, lineWidth: 2,
            lineStyle: e.punteada ? LightweightCharts.LineStyle.Dotted
              : LightweightCharts.LineStyle.Solid,
            priceLineVisible: false, lastValueVisible: false });
        }
        // unidad: la pedida; dibujada: la de las semanas que ya tiene
        const u = unidad, dibujada = x ? x.dibujada : null;
        pseries.set(k, { s, unidad: u, dibujada });
        puntosProducto(k, u).then(datos => {
          const y = pseries.get(k);
          if (!y || y.s !== s || y.unidad !== u) return;
          y.dibujada = u;
          s.setData(datos);   // con huecos donde no hubo precio
          pchart.timeScale().fitContent();
        }, () => {
          // sin las semanas de esa unidad: la serie sigue en la que tenía y el
          // selector vuelve a ella (pesos de hoy, si recién se agregó)
          const y = pseries.get(k);
          if (!y || y.s !== s || y.unidad !== u) return;
          y.unidad = y.dibujada;
          if (unidad === u) ponerUnidad(y.dibujada || 'real');
        });
      } else if (!on && x) {
        pchart.removeSeries(x.s);
        pseries.delete(k);
      }
    });
    pchart.priceScale('right').applyOptions({ autoScale: true });
    pchart.timeScale().fitContent();
    pintarCarga();
  }

  // un producto en Lightweight, en la unidad elegida y con huecos donde no
  // hubo precio: pesos de hoy desde la página; época y UF, del datafeed
  function puntosProducto(k, u) {
    if (u === 'real' || !feed) return Promise.resolve(PRODS[k].gaps);
    return feed.barras(PRODS[k].slug + SUF[u]).then(b => {
      const out = [];
      (b || []).forEach((x, i) => {
        if (i) for (let t = b[i - 1].time + SEMANA_MS; t < x.time; t += SEMANA_MS) out.push({ time: dia(t) });
        out.push({ time: dia(x.time), value: x.close });
      });
      return out;
    });
  }

  function buildProductos() {
    if (!PKEYS.length) return;   // sin productos el modo no existe (ni su pill)
    // primer y último año con dato del catálogo, calculados en el build
    if (DATA.rango) document.getElementById('prod-rango').textContent =
      '(' + DATA.rango[0] + ' a ' + DATA.rango[1] + ')';
    buildSelector('pgroups', 'psearch', k => {
      const b = document.createElement('button');
      b.className = 'pchip' + (psel.has(k) ? ' active' : '');
      b.innerHTML = '<span class="dot"></span>' + PRODS[k].label;
      const dot = b.querySelector('.dot');
      // el chip muestra el estilo de su línea: punto lleno si es continua,
      // anillo y borde de guiones si es punteada
      const paint = () => {
        const on = psel.has(k);
        const e = on ? estiloDe(k) : null;
        b.classList.toggle('active', on);
        dot.style.background = !on ? 'var(--dim)' : e.punteada ? 'transparent' : e.color;
        dot.style.boxShadow = on && e.punteada ? 'inset 0 0 0 2px ' + e.color : '';
        b.style.borderColor = on ? e.color : 'var(--line)';
        b.style.borderStyle = on && e.punteada ? 'dashed' : '';
        b.style.opacity = (!on && psel.size >= PMAX) ? '.4' : '';
      };
      ppaints.push(paint);
      paint();
      b.onclick = () => {
        if (psel.has(k)) soltar(k);
        else {
          if (psel.size >= PMAX) return;   // máximo 8: nunca dos iguales
          elegir(k);
        }
        ppaints.forEach(f => f()); syncProductos();
      };
      return b;
    });
  }

  /* ---------- vista Tu canasta ---------- */
  // constructor libre sobre las series de PRODS; el semáforo CARO/NORMAL/
  // BARATO queda reservado a los índices oficiales y aquí no se usa
  const QDEF  = { kg: 0.5, un: 1, l: 1 };
  const QSTEP = { kg: 0.1, un: 1, l: 0.1 };
  const QMIN  = { kg: 0.1, un: 1, l: 0.1 };
  const EQUIV = { marraqueta: '0,1 kg ≈ 1 marraqueta',
                  palta: '0,25 kg ≈ 1 palta mediana',
                  limon: '0,1 kg ≈ 1 limón' };
  const CMAX = 8;
  const canasta = new Map();          // slug -> cantidad
  const cpaints = [];
  let cchart, cserie;
  const redondear = q => Math.round(q * 10) / 10;
  const fmtCant = (q, uni) => (uni === 'un' ? String(Math.round(q)) :
    q.toFixed(1).replace(/\.0$/, '').replace('.', ',')) + ' ' + uni;

  function hashCanasta() {
    if (!canasta.size) return '';
    return '#canasta=' + [...canasta.entries()]
      .map(([k, q]) => k + ':' + redondear(q)).join(',');
  }
  function guardarHash() {
    history.replaceState(null, '', location.pathname + location.search + hashCanasta());
  }
  // el hash comparte la canasta y tiene prioridad sobre la precarga
  function leerHash() {
    const m = location.hash.match(/canasta=([^&]*)/);
    if (!m) return false;
    decodeURIComponent(m[1]).split(',').forEach(par => {
      const [k, qs] = par.split(':');
      if (!PRODS[k] || canasta.has(k) || canasta.size >= CMAX) return;
      const uni = PRODS[k].unidad;
      let q = parseFloat(qs);
      if (!isFinite(q) || q <= 0) q = QDEF[uni];
      canasta.set(k, Math.max(QMIN[uni], uni === 'un' ? Math.round(q) : redondear(q)));
    });
    return true;
  }

  // integridad Laspeyres: la serie compuesta existe SOLO en las semanas
  // donde TODOS los productos elegidos tienen dato (intersección estricta,
  // como el min_count del pipeline); un producto de historia corta trunca
  function calcularCanasta() {
    const keys = [...canasta.keys()].filter(k => PRODS[k] && PRODS[k].real.length);
    if (!keys.length) return { serie: [], truncada: false, limitante: null };
    const mapas = keys.map(k => new Map(PRODS[k].real.map(p => [p.time, p.value])));
    const serie = [];
    PRODS[keys[0]].real.forEach(p => {
      let suma = 0;
      for (let i = 0; i < keys.length; i++) {
        const v = mapas[i].get(p.time);
        if (v == null) return;
        suma += canasta.get(keys[i]) * v;
      }
      serie.push({ time: p.time, value: suma });
    });
    let limitante = keys[0], tarde = PRODS[keys[0]].real[0].time, temprano = tarde;
    keys.forEach(k => {
      const t0 = PRODS[k].real[0].time;
      if (t0 > tarde) { tarde = t0; limitante = k; }
      if (t0 < temprano) temprano = t0;
    });
    return { serie, truncada: tarde > temprano, limitante };
  }

  function initCChart() {
    const el = document.getElementById('cchart');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos.</div>';
      return;
    }
    // mismos gestos del hero (rueda y swipe vertical scrollean la página,
    // zoom en ejes y pinch) pero la línea va en HUESO: la brasa queda para
    // los índices oficiales; las canastas de usuario se dibujan en hueso
    cchart = LightweightCharts.createChart(el,
      opcionesChart({ localization: { priceFormatter: fmt } }));
    // el label de precio del eje toma el color de la serie: acompaña
    cserie = cchart.addLineSeries({ color: COL.bone, lineWidth: 2, priceLineVisible: false });
  }

  function renderCItems() {
    const cont = document.getElementById('citems');
    cont.innerHTML = '';
    canasta.forEach((q, k) => {
      const p = PRODS[k];
      if (!p) return;
      const it = document.createElement('div'); it.className = 'citem';
      const top = document.createElement('div'); top.className = 'ci-top';
      const lab = document.createElement('span'); lab.className = 'ci-label';
      lab.textContent = p.label;
      const st = document.createElement('div'); st.className = 'ci-step';
      const menos = document.createElement('button'); menos.className = 'ci-btn';
      menos.textContent = '-'; menos.setAttribute('aria-label', 'menos ' + p.label);
      const val = document.createElement('span'); val.className = 'ci-q';
      val.textContent = fmtCant(q, p.unidad);
      const mas = document.createElement('button'); mas.className = 'ci-btn';
      mas.textContent = '+'; mas.setAttribute('aria-label', 'más ' + p.label);
      const setQ = nq => { canasta.set(k, nq); val.textContent = fmtCant(nq, p.unidad);
        guardarHash(); syncCanasta(); };
      menos.onclick = () => {
        const nq = Math.max(QMIN[p.unidad], redondear(canasta.get(k) - QSTEP[p.unidad]));
        if (nq !== canasta.get(k)) setQ(nq);
      };
      mas.onclick = () => setQ(redondear(canasta.get(k) + QSTEP[p.unidad]));
      st.appendChild(menos); st.appendChild(val); st.appendChild(mas);
      top.appendChild(lab); top.appendChild(st);
      it.appendChild(top);
      if (p.unidad === 'kg' && EQUIV[k]) {   // ayuda doméstica solo donde existe
        const eq = document.createElement('div'); eq.className = 'ci-eq';
        eq.textContent = EQUIV[k];
        it.appendChild(eq);
      }
      cont.appendChild(it);
    });
  }

  // semana ISO (1..53) de una fecha 'YYYY-MM-DD', en UTC para no depender
  // del huso del visitante
  function semanaISO(t) {
    const d = new Date(t + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
    const j4 = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
    return 1 + Math.round(((d - j4) / 864e5 - 3 + ((j4.getUTCDay() + 6) % 7)) / 7);
  }
  // distancia circular mod 52: diciembre y enero son épocas vecinas
  const distSem = (a, b) => {
    const d = Math.abs(a - b) % 52;
    return Math.min(d, 52 - d);
  };

  function syncCanasta() {
    // la intersección necesita todas las series: si falta alguna, se pide
    // (solo con la canasta a la vista) y el cálculo espera a que lleguen
    const faltan = [...canasta.keys()].some(k => PRODS[k] && !PRODS[k].real);
    if (faltan) {
      if (modo === 'canasta') pedirProductos([...canasta.keys()], syncCanasta);
      pintarCarga();
      return;
    }
    const r = calcularCanasta();
    const costo = document.getElementById('ccosto');
    const stats = document.getElementById('cstats');
    const temporada = document.getElementById('ctemporada');
    const aviso = document.getElementById('caviso');
    if (!r.serie.length) {
      costo.textContent = '';
      stats.textContent = canasta.size ?
        'sin semanas en común entre los productos elegidos' :
        'elige productos para armar tu canasta';
      temporada.textContent = '';
      aviso.textContent = '';
    } else {
      const vals = r.serie.map(p => p.value);
      const ult = vals[vals.length - 1], n = vals.length;
      costo.textContent = fmt(ult);
      const pct = Math.round(100 * vals.filter(v => v <= ult).length / n);
      const prom = vals.reduce((a, b) => a + b, 0) / n;
      const vsp = Math.round((ult / prom - 1) * 100);
      stats.textContent = 'percentil ' + pct + ' de ' + n +
        ' semanas de esta canasta (' + (vsp >= 0 ? '+' : '') + vsp +
        (vsp >= 0 ? '% sobre' : '% bajo') + ' su promedio histórico)';
      // percentil de TEMPORADA: la semana actual solo contra las semanas
      // históricas de su misma época (semana ISO a ±6, circular); con menos
      // de 30 comparables el percentil es ruido y la línea se omite
      const wAct = semanaISO(r.serie[n - 1].time);
      const comp = [];
      let desde = '';
      for (let i = 0; i < n - 1; i++) {
        if (distSem(semanaISO(r.serie[i].time), wAct) <= 6) {
          if (!comp.length) desde = r.serie[i].time.slice(0, 4);
          comp.push(vals[i]);
        }
      }
      if (comp.length < 30) temporada.textContent = '';
      else {
        const nc = comp.length;
        const ord = comp.slice().sort((a, b) => a - b);
        const med = (ord[(nc - 1) >> 1] + ord[nc >> 1]) / 2;
        const pca = Math.round(100 * comp.filter(v => v < ult).length / nc);
        temporada.textContent = 'en esta época del año: ' + (ult < med ?
          'más barata que el ' + (100 - pca) + '%' :
          'más cara que el ' + pca + '%') +
          ' de las semanas comparables (' + nc + ' desde ' + desde + ')';
      }
      aviso.textContent = r.truncada ? 'tu canasta tiene datos desde ' +
        r.serie[0].time.slice(0, 4) + ' (limitada por ' +
        PRODS[r.limitante].label + ')' : '';
    }
    if (cchart) {
      // recuperar la autoescala si el usuario arrastró el eje de precios
      cchart.priceScale('right').applyOptions({ autoScale: true });
      cserie.setData(r.serie);
      cchart.timeScale().fitContent();
    }
    pintarCarga();
  }

  function buildCanasta() {
    if (!PKEYS.length) return;   // sin productos el modo no existe (ni su pill)
    if (!leerHash()) {   // precarga primera visita: un pan con palta generoso
      if (PRODS.marraqueta) canasta.set('marraqueta', 0.1);
      if (PRODS.palta) canasta.set('palta', 0.1);
    }
    buildSelector('cgroups', 'csearch', k => {
      const b = document.createElement('button');
      b.className = 'pchip';
      b.innerHTML = '<span class="dot"></span>' + PRODS[k].label;
      const dot = b.querySelector('.dot');
      const paint = () => {
        const on = canasta.has(k);
        b.classList.toggle('active', on);
        // la canasta de usuario va en hueso, como su línea
        dot.style.background = on ? 'var(--bone)' : 'var(--dim)';
        b.style.borderColor = on ? 'var(--bone)' : 'var(--line)';
        b.style.opacity = (!on && canasta.size >= CMAX) ? '.4' : '';
      };
      cpaints.push(paint);
      b.onclick = () => {
        if (canasta.has(k)) canasta.delete(k);
        else {
          if (canasta.size >= CMAX) return;   // máximo 8 productos simultáneos
          canasta.set(k, QDEF[PRODS[k].unidad]);
        }
        cpaints.forEach(f => f());
        renderCItems(); guardarHash(); syncCanasta();
      };
      return b;
    });
    cpaints.forEach(f => f());
    initCChart();
    renderCItems();
    syncCanasta();
    const btn = document.getElementById('ccopy');
    btn.onclick = () => {
      guardarHash();
      const url = location.href;
      const listo = () => {
        btn.textContent = 'copiado';
        btn.classList.add('copiado');
        setTimeout(() => { btn.textContent = 'copiar link de esta canasta';
          btn.classList.remove('copiado'); }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(listo, listo);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch (e) {}
        ta.remove(); listo();
      }
    };
  }

  /* ---------- captura PNG compartible (estilo TradingView) ---------- */
  const TITULO_UNIDAD = { epoca: ', PRECIO DE LA ÉPOCA', uf: ', EN UF' };
  // la marca va en tres segmentos medidos para pintar SOLO la í en brasa,
  // en la tipografía del wordmark
  function marcaDeAgua(ctx, xDer, yBase, size) {
    ctx.font = '700 ' + size + 'px "Space Grotesk", sans-serif';
    ctx.textBaseline = 'alphabetic';
    const seg = ['carest', 'í', 'a.cl'];
    const w = seg.map(s => ctx.measureText(s).width);
    let x = xDer - (w[0] + w[1] + w[2]);
    ctx.globalAlpha = 0.4; ctx.fillStyle = COL.bone;  ctx.fillText(seg[0], x, yBase);
    ctx.globalAlpha = 1;   ctx.fillStyle = COL.ember; ctx.fillText(seg[1], x + w[0], yBase);
    ctx.globalAlpha = 0.4; ctx.fillStyle = COL.bone;  ctx.fillText(seg[2], x + w[0] + w[1], yBase);
    ctx.globalAlpha = 1;
  }

  // las series del modo activo: si alguna aún viene en camino, la captura
  // la espera (y se omite si el pedido falla)
  function datosDelModo() {
    if (modo === 'indices') return cargarIndice(cur);
    const keys = modo === 'productos' ? [...psel] : [...canasta.keys()];
    return Promise.all(keys.filter(k => PRODS[k]).map(cargarProducto));
  }

  async function capturarPNG() {
    // Advanced Charts: su captura del lado del cliente (nunca la del servidor
    // de TradingView); Lightweight: la suya, como siempre
    const w = widgetActivo(), ch = w ? null : chartActivo();
    if (!w && !ch) return;
    if (!w) {
      try { await datosDelModo(); } catch (e) { pintarCarga(); return; }
      // dos cuadros: el lienzo alcanza a dibujar lo que acaba de llegar
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    }
    // el canvas no dispara la carga perezosa de webfonts: si un peso aún
    // no se usó en el DOM, fillText caería a la fuente del sistema.
    // Cargar explícitamente cada peso que dibuja el snapshot (título,
    // costo, fecha y marca de agua) antes de componer
    try {
      await Promise.all([
        document.fonts.load('400 16px "IBM Plex Sans"'),
        document.fonts.load('500 16px "IBM Plex Mono"'),
        document.fonts.load('700 16px "Space Grotesk"'),
      ]);
      await document.fonts.ready;
    } catch (e) {}
    const shot = w ? await TV.capturaCliente(w, tok).catch(() => null) : ch.takeScreenshot();
    if (!shot || !shot.width) return;
    // lienzo de salida legible para compartir: nunca menos de 1200px de
    // ancho; takeScreenshot ya viene a devicePixelRatio y si aun así es
    // chico (móvil a DPR bajo) se escala el canvas
    const W = Math.max(1200, Math.round(shot.width));
    const pad = Math.round(W * 0.04);
    const chartW = W - pad * 2;
    const chartH = Math.round(shot.height * chartW / shot.width);
    // bajo el costo, la composición: en canasta "{label} {cantidad} {unidad}"
    // en una línea o dos si no cabe; en productos, los elegidos por orden de
    // puesto, cada uno con la muestra de su línea (color y trazo del
    // gráfico). El encabezado crece lo que ellas ocupen
    const compSize = Math.round(W * 0.013), compAlto = Math.round(compSize * 1.5);
    const compLineas = [], prodLineas = [];
    const muestra = Math.round(compSize * 1.8), hueco = Math.round(compSize * 0.5),
      entre = Math.round(compSize * 1.4);
    const mctx = document.createElement('canvas').getContext('2d');
    mctx.font = '400 ' + compSize + 'px "IBM Plex Sans", sans-serif';
    let partes = [];
    if (modo === 'canasta' && canasta.size) {
      partes = [...canasta.entries()].filter(([k]) => PRODS[k])
        .map(([k, q]) => PRODS[k].label + ' ' + fmtCant(q, PRODS[k].unidad));
    } else if (modo === 'productos') {
      let fila = [], ancho = 0;
      // en el orden de sus puestos: color 1, color 2, ... como en el gráfico
      [...psel].filter(k => PRODS[k]).sort((a, b) => puestos.get(a) - puestos.get(b)).forEach(k => {
        const it = Object.assign({ texto: PRODS[k].label }, estiloDe(k));
        const w = muestra + hueco + mctx.measureText(it.texto).width;
        if (fila.length && ancho + entre + w > chartW) { prodLineas.push(fila); fila = []; ancho = 0; }
        ancho += (fila.length ? entre : 0) + w;
        fila.push(it);
      });
      if (fila.length) prodLineas.push(fila);
    }
    if (partes.length) {
      let linea = '';
      partes.forEach(p => {
        const cand = linea ? linea + ', ' + p : p;
        if (!linea || mctx.measureText(cand).width <= chartW) linea = cand;
        else { compLineas.push(linea); linea = p; }
      });
      if (linea) compLineas.push(linea);
      if (compLineas.length > 2) {   // nunca más de dos: recorte con …
        let l2 = compLineas.slice(1).join(', ');
        while (l2 && mctx.measureText(l2 + ' …').width > chartW) l2 = l2.slice(0, -1);
        compLineas.length = 1;
        compLineas.push(l2 + ' …');
      }
    }
    // contexto arriba a la izquierda: qué es, cuánto vale, de cuándo;
    // productos no tiene un costo único y lleva su etiqueta en vez del monto.
    // Un índice fuera de pesos de hoy dice su unidad y, en UF, debajo va la
    // cifra en pesos de hoy
    let titulo, precio,
      precioFont = '700 ' + Math.round(W * 0.037) + 'px "Space Grotesk", sans-serif';
    if (modo === 'canasta') {
      titulo = 'TU CANASTA';
      precio = document.getElementById('ccosto').textContent || '·';
    } else if (modo === 'productos') {
      titulo = 'PRODUCTOS';
      precio = ONOTE[unidad];
      precioFont = '400 ' + Math.round(W * 0.02) + 'px "IBM Plex Sans", sans-serif';
    } else {
      const d = INDICES[cur];
      titulo = d.nombre.replace(/^Índice /i, '').toUpperCase();
      precio = fmt(d.costo_real);
      if (unidad !== 'real') {
        titulo += TITULO_UNIDAD[unidad];
        const x = await ultimoCierre(cur, unidad).catch(() => null);
        if (x != null) precio = unidad === 'uf' ? TV.textoUF(x) : fmt(x);
        if (x != null && unidad === 'uf') compLineas.unshift(fmt(d.costo_real) + ' en pesos de hoy');
      }
    }
    const compH = (compLineas.length + prodLineas.length) * compAlto;
    const headH = Math.round(W * 0.13) + compH, footH = Math.round(W * 0.07);
    const H = headH + chartH + footH;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, W, H);
    const fecha = document.getElementById('fecha').textContent;
    ctx.textBaseline = 'top';
    ctx.fillStyle = COL.ash;
    ctx.font = '500 ' + Math.round(W * 0.014) + 'px "IBM Plex Mono", monospace';
    ctx.fillText(titulo, pad, Math.round(W * 0.028));
    ctx.fillStyle = COL.bone;
    ctx.font = precioFont;
    ctx.fillText(precio, pad, Math.round(W * 0.05));
    ctx.fillStyle = COL.ash;
    ctx.font = '400 ' + compSize + 'px "IBM Plex Sans", sans-serif';
    compLineas.forEach((l, i) =>
      ctx.fillText(l, pad, Math.round(W * 0.098) + i * compAlto));
    const grosor = Math.max(2, Math.round(compSize * 0.16));
    prodLineas.forEach((fila, i) => {
      const y = Math.round(W * 0.098) + i * compAlto;
      let x = pad;
      fila.forEach(it => {
        ctx.save();
        ctx.strokeStyle = it.color;
        ctx.lineWidth = grosor;
        ctx.setLineDash(it.punteada ? [grosor, grosor * 1.5] : []);
        ctx.beginPath();
        ctx.moveTo(x, y + compSize * 0.6);
        ctx.lineTo(x + muestra, y + compSize * 0.6);
        ctx.stroke();
        ctx.restore();
        ctx.fillText(it.texto, x + muestra + hueco, y);
        x += muestra + hueco + ctx.measureText(it.texto).width + entre;
      });
    });
    ctx.font = '400 ' + Math.round(W * 0.012) + 'px "IBM Plex Sans", sans-serif';
    ctx.fillText('semana del ' + fecha, pad, Math.round(W * 0.098) + compH);
    ctx.drawImage(shot, pad, headH, chartW, chartH);
    marcaDeAgua(ctx, W - pad, H - Math.round(footH * 0.35), Math.round(W * 0.02));
    const nombre = 'carestia_' + (modo === 'indices' ? simboloIndice(cur) : modo) + '_' +
      new Date().toISOString().slice(0, 10) + '.png';
    cv.toBlob(async blob => {
      if (!blob) return;
      // en móvil el share sheet nativo (ideal para WhatsApp); si no está
      // disponible o el archivo no se puede compartir, descarga directa
      const file = new File([blob], nombre, { type: 'image/png' });
      if (matchMedia('(pointer:coarse)').matches &&
          navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file] }); return; }
        catch (e) { if (e.name === 'AbortError') return; }
      }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = nombre;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }, 'image/png');
  }
  document.getElementById('shot').onclick = () => capturarPNG();

  // deep link: el modo ES la pantalla, sin scroll. #productos y #canasta
  // abren su modo directo; #canasta=... además aterriza con la canasta armada
  function modoDelHash() {
    if (/^#canasta(=|$)/.test(location.hash)) return 'canasta';
    // #comparar es alias de #productos (label visible "Comparar productos");
    // ambos siguen funcionando para no romper links compartidos
    if (location.hash === '#productos' || location.hash === '#comparar') return 'productos';
    return null;
  }
  function activarDeepLink() {
    const m = modoDelHash();
    if (m) setModo(m);
  }
  // y si el hash cambia con la página ya abierta (otro link compartido),
  // rearmar la canasta desde cero y cambiar de modo; guardarHash usa
  // replaceState, así que los cambios propios no disparan este evento
  window.addEventListener('hashchange', () => {
    const code = indiceDelHash();
    if (code) { render(code); return; }
    const m = modoDelHash();
    if (!m) return;
    if (/canasta=/.test(location.hash)) {
      canasta.clear();
      leerHash();
      cpaints.forEach(f => f());
      renderCItems();
      syncCanasta();
    }
    setModo(m);
  });

  window.addEventListener('load', () => {
    prepararTV();
    selector.limitar(unidadesHay());
    pintarLeyenda();
    buildTicker();
    buildTabs();
    // sin carestia-tv.js, Lightweight desde el principio, como antes
    if (usaLW('indices')) initChart();
    render(indiceDelHash() || CODES[0], true);
    aplicarVista();   // botones y referencia de velas antes de que llegue el gráfico
    if (usaLW('productos')) initPChart();
    buildProductos();
    syncProductos();
    buildCanasta();
    activarDeepLink();
  });
</script>
</body>
</html>
"""

# ---------------- Portada (formato tabla) ----------------
# Índices arriba, lo que más se movió esta semana y la tabla de productos.
# Todo va en el HTML estático (las filas son <a href> a cada ficha: se leen
# sin JS y las indexan los buscadores); el JS solo ordena, filtra por grupo
# y cambia las pestañas de "Esta semana" en móvil. Sin Lightweight Charts ni
# datos inline: los gráficos viven en /graficos.html.
PORTADA_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>
  // los links de la app (un índice, Comparar, Arma tu canasta y las canastas
  // compartidas) apuntaban a la portada: siguen funcionando, ahora en
  // /graficos.html con el mismo hash. Va primero para no pintar la portada
  (function () {
    function mudar() {
      if (/^#(?:__HASHES__)$/.test(location.hash))
        location.replace('graficos.html' + location.search + location.hash);
    }
    mudar();
    window.addEventListener('hashchange', mudar);
    document.documentElement.className = 'js';
  })();
</script>
<title>Carestía: índices del costo de vida en Chile</title>
<meta name="description" content="Índices del costo de vida en Chile: asado, desayuno, ensalada y fruta en pesos de hoy, con datos públicos de ODEPA desde 2008. Actualizado cada viernes.">
<link rel="canonical" href="https://carestia.cl/">
<meta property="og:title" content="Carestía: índices del costo de vida en Chile">
<meta property="og:description" content="Cuánto cuesta la vida cotidiana en Chile, en pesos de hoy. Índices propios sobre datos públicos de ODEPA, actualizados cada viernes.">
<meta property="og:image" content="https://carestia.cl/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
__ICONO__
__FUENTES__
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__
__CSS_CABECERA__
  main { display:flex; flex-direction:column; gap:clamp(28px,4vw,48px);
    padding:clamp(16px,3vw,40px) clamp(16px,3vw,32px) clamp(32px,4vw,56px); }
  .vh { position:absolute; width:1px; height:1px; overflow:hidden;
    clip-path:inset(50%); white-space:nowrap; }
  .bloque { display:flex; flex-direction:column; gap:16px; }
  .bloque h2 { font:700 26px/1.15 var(--display); letter-spacing:-.01em; }
  .bloque h2.chico { font-size:22px; }
  .sec-head { display:flex; align-items:flex-end; justify-content:space-between;
    flex-wrap:wrap; gap:12px 24px; }
  .sec-tit { display:flex; flex-direction:column; gap:6px; }
  .sec-tit p { font:400 14px/1.5 var(--sans); color:var(--ash); max-width:72ch;
    text-wrap:pretty; }
  .sec-link { font:400 14px var(--sans); color:var(--ash);
    text-decoration:underline; text-decoration-color:var(--dim);
    text-underline-offset:3px; }
  .sec-link:hover, .sec-link:focus-visible { color:var(--bone);
    text-decoration-color:var(--bone); }
  /* flechas siempre neutras: el color no dice si algo subió o bajó */
  .f { font-style:normal; color:var(--dim); }
  /* la cinta queda quieta para quien pidió menos movimiento, como en
     /graficos.html */
  @media (prefers-reduced-motion: reduce) {
    * { animation:none !important; }
  }

  /* ---- Índices Carestía: el semáforo vive solo aquí ---- */
  .icards { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }
  .icard { display:flex; flex-direction:column; gap:14px; padding:20px;
    background:var(--panel); border:1px solid var(--line); border-radius:14px;
    color:var(--bone); text-decoration:none;
    transition:border-color .15s ease, background-color .15s ease; }
  .icard:hover, .icard:focus-visible { border-color:var(--bone); background:var(--hover); }
  .ic-top { display:flex; flex-wrap:wrap; justify-content:space-between;
    align-items:center; gap:6px 8px; }
  .ic-ey { font:500 11px var(--mono); letter-spacing:.14em; color:var(--ash); }
  .ic-pill { font:500 11px var(--mono); letter-spacing:.08em; padding:3px 9px;
    border-radius:999px; color:var(--bg); }
  .ic-mid { display:flex; flex-direction:column; gap:4px; }
  .ic-sub { font:400 13px var(--sans); color:var(--ash); }
  .ic-precio { font:700 38px/1.05 var(--display); letter-spacing:-.02em; }
  .ic-ph { font:400 12px var(--sans); color:var(--dim); }
  .ic-niv { display:flex; flex-direction:column; gap:7px; }
  .ic-nl { display:flex; justify-content:space-between; gap:8px;
    font:400 12px var(--sans); }
  .ic-nl span:first-child { color:var(--ash); }
  /* las tres zonas del percentil (0 a 33, 33 a 66, 66 a 100) y la marca */
  .zonas { position:relative; height:8px; display:flex; gap:2px; }
  .zonas .z { flex:33 1 0; }
  .zonas .z1 { background:color-mix(in srgb, var(--verde) 28%, transparent);
    border-radius:4px 0 0 4px; }
  .zonas .z2 { background:color-mix(in srgb, var(--ambar) 28%, transparent); }
  .zonas .z3 { flex-grow:34; border-radius:0 4px 4px 0;
    background:color-mix(in srgb, var(--rojo) 28%, transparent); }
  .zonas .marca { position:absolute; top:-4px; width:3px; height:16px;
    margin-left:-1px; background:var(--bone); border-radius:2px; }
  .ic-pie { display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px 8px;
    font:400 12px/1.5 var(--sans); color:var(--ash);
    border-top:1px solid var(--line); padding-top:12px; }
  /* las 4 tarjetas miden lo mismo: si el pie no cabe en una línea, va en dos
     en todas, no solo en las de cifras más largas */
  .icard { container-type:inline-size; }
  @container (max-width:264px) { .ic-pie { flex-direction:column; } }
  .ic-m { display:none; }

  /* ---- Esta semana ---- */
  .sem-tabs { display:none; }
  .sem-listas { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
  .sem-l { background:var(--panel); border:1px solid var(--line);
    border-radius:14px; overflow:hidden; }
  .sem-h { display:flex; flex-direction:column; gap:3px; padding:16px 18px 12px; }
  .sem-h h3 { font:600 15px var(--sans); }
  .sem-h span { font:400 12px var(--sans); color:var(--dim); }
  .sem-l ul { list-style:none; }
  .sem-l a { display:flex; justify-content:space-between; align-items:center;
    gap:12px; min-height:44px; padding:8px 18px; border-top:1px solid var(--hover);
    color:var(--bone); text-decoration:none; }
  .sem-l a:hover, .sem-l a:focus-visible { background:var(--hover); }
  .sem-l .vacio { padding:12px 18px; border-top:1px solid var(--hover);
    font:400 13px var(--sans); color:var(--ash); }
  .sn { display:flex; flex-wrap:wrap; align-items:baseline; gap:0 8px; min-width:0; }
  .sn b { font:500 14px var(--sans); }
  .sn small { font:400 12px var(--sans); color:var(--dim); }
  .sv { display:flex; align-items:baseline; gap:6px; font:400 14px var(--sans);
    white-space:nowrap; }
  .sv .f { font-size:11px; }

  /* ---- Productos ---- */
  .orden { display:flex; align-items:center; gap:10px; font:400 13px var(--sans);
    color:var(--ash); }
  .orden select { height:36px; padding:0 10px; background:var(--panel);
    color:var(--bone); border:1px solid var(--line); border-radius:9px;
    font:400 13px var(--sans); }
  .chips { display:flex; flex-wrap:wrap; gap:8px; }
  .chips button { min-height:36px; padding:0 14px; border-radius:999px;
    cursor:pointer; font:500 13px var(--sans); background:transparent;
    color:var(--ash); border:1px solid var(--line); }
  .chips button:hover, .chips button:focus-visible { color:var(--bone);
    border-color:var(--bone); }
  .chips button[aria-pressed="true"] { background:var(--bone); color:var(--bg);
    border-color:var(--bone); }
  /* sin JS no hay orden ni filtro: las filas igual quedan en el HTML */
  html:not(.js) .orden, html:not(.js) .chips { display:none; }
  .tabla { background:var(--panel); border:1px solid var(--line);
    border-radius:14px; overflow:hidden; }
  .thead, .fila { display:grid; align-items:center; gap:12px; padding:0 16px;
    grid-template-columns:minmax(0,2.4fr) minmax(0,1.1fr) minmax(0,.9fr)
      minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.7fr) 124px 24px; }
  .thead { border-bottom:1px solid var(--line); }
  .thead > * { display:flex; justify-content:flex-end; align-items:center; gap:4px;
    min-height:40px; padding:0; background:none; border:0; text-align:right;
    font:500 12px var(--sans); color:var(--dim); }
  .thead > :first-child { justify-content:flex-start; text-align:left; }
  .thead button { cursor:pointer; }
  .thead button:hover, .thead button:focus-visible,
  .thead button[aria-pressed="true"] { color:var(--bone); }
  .fila { min-height:60px; padding-top:8px; padding-bottom:8px;
    border-bottom:1px solid var(--hover); color:var(--bone); text-decoration:none; }
  .fila:last-child { border-bottom:0; }
  .fila[hidden] { display:none; }
  .fila:hover, .fila:focus-visible { background:var(--hover); }
  /* la flecha de la fila: abre la ficha */
  .fila::after { content:""; justify-self:end; width:7px; height:7px;
    margin-right:5px; border-top:2px solid var(--dim); border-right:2px solid var(--dim);
    transform:rotate(45deg); }
  .c-n { display:flex; flex-direction:column; gap:2px; min-width:0; }
  .nm { font:500 15px/1.3 var(--sans); }
  .mt { font:400 12px/1.4 var(--sans); color:var(--dim); }
  .mp { display:none; }
  .c-p { text-align:right; font:500 15px var(--sans); }
  .c-p small { display:block; font:400 11px var(--sans); color:var(--dim); }
  .c-v { text-align:right; font:400 14px var(--sans); white-space:nowrap; }
  .c-v .f { font-size:10px; }
  /* percentil en su historia: barra neutra, sin semáforo */
  .c-c { display:flex; align-items:center; justify-content:flex-end; gap:10px; }
  .bar { position:relative; flex:none; width:96px; height:4px;
    background:var(--line); border-radius:2px; }
  .bar span { position:absolute; left:0; top:0; bottom:0; background:var(--ash);
    border-radius:2px; }
  .cn { width:28px; text-align:right; font:400 13px var(--sans); }
  .sp { justify-self:end; width:112px; height:28px; overflow:visible; }
  .sp path { fill:none; stroke:var(--bone); stroke-width:1.5; stroke-linejoin:round;
    stroke-linecap:round; vector-effect:non-scaling-stroke; }
  .ver-todos { align-self:center; display:flex; align-items:center;
    justify-content:center; min-height:44px; padding:0 20px;
    border:1px solid var(--line); border-radius:10px;
    font:500 14px var(--sans); color:var(--bone); text-decoration:none; }
  .ver-todos:hover, .ver-todos:focus-visible { border-color:var(--bone);
    background:var(--hover); }

  /* ---- escritorio angosto: 2 índices por fila, la tabla sin "3 meses" ---- */
  @media (max-width:1099px) {
    .icards { grid-template-columns:repeat(2,minmax(0,1fr)); }
  }
  @media (max-width:1023px) {
    .thead, .fila { grid-template-columns:minmax(0,2.4fr) minmax(0,1.1fr)
      minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.3fr) 96px 16px; }
    .c-t { display:none; }
    .bar { width:56px; }
    .sp { width:96px; }
  }

  /* ---- móvil ---- */
  @media (max-width:760px) {
    /* Esta semana: una tarjeta con tres pestañas (sin JS, las tres listas
       una bajo otra) */
    .sem { background:var(--panel); border:1px solid var(--line);
      border-radius:12px; overflow:hidden; }
    .sem-listas { display:block; }
    .sem-l { background:none; border:0; border-radius:0; }
    .sem-l + .sem-l { border-top:1px solid var(--line); }
    .js .sem-tabs { display:flex; gap:4px; padding:6px;
      border-bottom:1px solid var(--hover); }
    .sem-tabs button { flex:1 1 0; min-width:0; min-height:40px; border:0;
      border-radius:8px; cursor:pointer; font:500 14px var(--sans);
      background:transparent; color:var(--ash); }
    .sem-tabs button[aria-pressed="true"] { background:var(--line); color:var(--bone); }
    .js .sem-l:not(.on) { display:none; }
    .js .sem-l + .sem-l { border-top:0; }
    .js .sem-h { position:absolute; width:1px; height:1px; padding:0;
      overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
    .sem-l a { min-height:48px; padding:8px 14px; border-top:0;
      border-bottom:1px solid var(--hover); }
    .sem-l a .sn b, .sem-l a .sv { font-size:15px; }

    /* Productos: lista con nombre, unidad y percentil, sparkline, precio y
       cambio semanal; el selector de orden baja bajo los grupos */
    .prod-head { display:contents; }
    .prod-head .sec-tit { order:0; }
    .chips { order:1; }
    .orden { order:2; width:100%; }
    .orden select { flex:1; min-width:0; height:44px; }
    .tabla { order:3; background:none; border:0; border-radius:0; overflow:visible; }
    .ver-todos { order:4; align-self:stretch; min-height:48px; }
    .thead { display:none; }
    .fila { grid-template-columns:minmax(0,1fr) 64px 92px; grid-template-rows:auto auto;
      gap:3px 12px; min-height:66px; padding:10px 0;
      border-bottom:1px solid var(--hover); }
    .fila:last-child { border-bottom:1px solid var(--hover); }
    .fila:hover, .fila:focus-visible { background:none; }
    .fila::after { display:none; }
    .c-n { grid-column:1; grid-row:1 / 3; gap:3px; }
    .sp { grid-column:2; grid-row:1 / 3; width:64px; height:24px; }
    .c-p { grid-column:3; grid-row:1; align-self:end; }
    .c-w { grid-column:3; grid-row:2; align-self:start; font-size:12px; }
    .c-t, .c-y, .c-c, .mg { display:none; }
    .mp { display:inline; }
    .sec-tit p .d-only { display:none; }
  }
  @media (max-width:640px) {
    .bloque { gap:12px; }
    .bloque h2 { font-size:22px; }
    .bloque h2.chico { font-size:20px; }
    .sec-tit p { font-size:13px; }
    .ind-head .sec-tit p, .ind-head .sec-link { display:none; }
    /* Índices: 2 por fila, tarjeta compacta */
    .icards { gap:10px; }
    .icard { gap:8px; padding:14px; border-radius:12px; }
    .ic-ind, .ic-sub, .ic-ph, .ic-nl, .ic-pie { display:none; }
    .ic-ey { font-size:10px; letter-spacing:.12em; }
    .ic-pill { font-size:10px; letter-spacing:.06em; padding:2px 7px; }
    .ic-precio { font-size:24px; line-height:1.1; }
    .zonas { height:6px; }
    .zonas .marca { top:-3px; height:12px; }
    .ic-m { display:block; font:400 11px/1.4 var(--sans); color:var(--ash); }
  }
__CSS_SITIO__
</style>
</head>
<body>

  <div class="ticker">
    <div class="tag">ÍNDICES</div>
    <div class="ticker-scroll"><div class="ticker-track">
__CINTA__
    </div></div>
  </div>

  <header>
    <div class="brand">
      <!-- un único span envuelve el texto: innerText y copy-paste leen
           "CARESTÍA" en un solo run -->
      <div class="wordmark"><span>CAREST<span class="i">Í</span>A</span></div>
      <div class="tagline">Índices del costo de vida en Chile</div>
    </div>
    <div class="semana">Semana del <span class="nw">__FECHA__</span>. <span>Se actualiza los viernes.</span></div>
    __NAV__
  </header>

  <main>
    <h1 class="vh">Carestía: el costo de vida en Chile, en pesos de hoy</h1>

    <section class="bloque" aria-labelledby="h-indices">
      <div class="sec-head ind-head">
        <div class="sec-tit">
          <h2 id="h-indices">Índices Carestía</h2>
          <p>Canastas fijas en pesos de hoy. El color dice si están caras o baratas respecto de su propia historia.</p>
        </div>
        <a class="sec-link" href="/metodologia.html">Cómo se calculan</a>
      </div>
      <div class="icards">
__TARJETAS__
      </div>
    </section>

    <section class="bloque" aria-labelledby="h-semana">
      <h2 class="chico" id="h-semana">Esta semana</h2>
      <div class="sem" id="sem">
        <div class="sem-tabs" role="group" aria-label="Listas de esta semana">
          <button type="button" aria-pressed="true" aria-controls="sem-sub">Subieron</button>
          <button type="button" aria-pressed="false" aria-controls="sem-baj">Bajaron</button>
          <button type="button" aria-pressed="false" aria-controls="sem-car">Más caros</button>
        </div>
        <div class="sem-listas">
__LISTAS__
        </div>
      </div>
    </section>

    <section class="bloque" aria-labelledby="h-productos">
      <div class="sec-head prod-head">
        <div class="sec-tit">
          <h2 id="h-productos">Productos</h2>
          <p>Precios al consumidor ODEPA, Región Metropolitana, en pesos de hoy.<span class="d-only"> Cada fila abre su gráfico.</span></p>
        </div>
        <label class="orden">Ordenar por
          <select id="orden">
            <option value="n:1">Alfabético</option>
            <option value="w:-1">Más subió esta semana</option>
            <option value="w:1">Más bajó esta semana</option>
            <option value="c:-1">Más caro frente a su historia</option>
            <option value="y:-1">Mayor alza en un año</option>
            <option value="" hidden></option>
          </select>
        </label>
      </div>
      <div class="chips" role="group" aria-label="Filtrar por grupo">
__CHIPS__
      </div>
      <div class="tabla">
        <div class="thead">
          <button type="button" data-k="n" aria-pressed="true">Producto <span aria-hidden="true">▾</span></button>
          <button type="button" data-k="p" aria-pressed="false">Precio hoy <span aria-hidden="true"></span></button>
          <button type="button" data-k="w" aria-pressed="false">1 semana <span aria-hidden="true"></span></button>
          <button type="button" class="c-t" data-k="t" aria-pressed="false">3 meses <span aria-hidden="true"></span></button>
          <button type="button" data-k="y" aria-pressed="false">1 año <span aria-hidden="true"></span></button>
          <button type="button" data-k="c" aria-pressed="false">Percentil en su historia <span aria-hidden="true"></span></button>
          <span>Último año</span>
          <span></span>
        </div>
        <div id="filas">
__FILAS__
        </div>
      </div>
      <a class="ver-todos" href="/productos/">Ver todos los productos</a>
    </section>
  </main>

__PIE__

<script>
  // cinta: en táctil se pausa mientras el dedo está encima
  const tscroll = document.querySelector('.ticker-scroll');
  tscroll.addEventListener('touchstart',
    () => tscroll.classList.add('tocado'), { passive: true });
  ['touchend', 'touchcancel'].forEach(ev => tscroll.addEventListener(ev,
    () => tscroll.classList.remove('tocado'), { passive: true }));

  // Esta semana, en móvil: una tarjeta con tres pestañas
  const semTabs = [...document.querySelectorAll('.sem-tabs button')];
  semTabs.forEach(b => b.addEventListener('click', () => semTabs.forEach(t => {
    const on = t === b;
    t.setAttribute('aria-pressed', on);
    document.getElementById(t.getAttribute('aria-controls')).classList.toggle('on', on);
  })));

  // Productos: las filas ya vienen en el HTML, en orden alfabético; aquí solo
  // se reordenan (encabezados y selector) y se ocultan las de otros grupos.
  // Los valores van en data-*: p precio, w 1 semana, t 3 meses, y 1 año,
  // c percentil y g el grupo; sin el atributo, la fila no tiene ese dato y
  // va al final
  const cont = document.getElementById('filas');
  const filas = [...cont.children];
  const POS = new Map(filas.map((f, i) => [f, i]));
  // sentido de partida de cada columna: A a Z, y de mayor a menor en cifras
  const DEF = { n: 1, p: -1, w: -1, t: -1, y: -1, c: -1 };
  const NOMBRE = { n: 'Producto', p: 'Precio hoy', w: '1 semana', t: '3 meses',
    y: '1 año', c: 'Percentil en su historia' };
  const heads = [...document.querySelectorAll('.thead button')];
  const sel = document.getElementById('orden');
  const libre = sel.querySelector('option[hidden]');
  const chips = [...document.querySelectorAll('.chips button')];
  let clave = 'n', dir = 1, grupo = '';
  const valor = (f, k) => {
    if (k === 'n') return POS.get(f);
    const v = f.getAttribute('data-' + k);
    return v === null ? null : +v;
  };
  function comparar(a, b, k, d) {
    const x = valor(a, k), y = valor(b, k);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    return (x - y) * d;
  }
  function pintar() {
    // empates de percentil: primero el que más subió en un año, como en
    // "Más caros respecto de su historia"
    const orden = filas.slice().sort((a, b) => comparar(a, b, clave, dir) ||
      (clave === 'c' ? comparar(a, b, 'y', -1) : 0) || POS.get(a) - POS.get(b));
    orden.forEach(f => {
      f.hidden = grupo !== '' && f.dataset.g !== grupo;
      cont.appendChild(f);
    });
    heads.forEach(h => {
      const on = h.dataset.k === clave;
      h.setAttribute('aria-pressed', on);
      h.lastElementChild.textContent = on ? (dir === DEF[clave] ? '▾' : '▴') : '';
    });
    const v = clave + ':' + dir;
    if ([...sel.options].some(o => o.value === v)) { sel.value = v; return; }
    libre.textContent = NOMBRE[clave] + (clave === 'n' ?
      (dir === 1 ? ', de la A a la Z' : ', de la Z a la A') :
      (dir === -1 ? ', de mayor a menor' : ', de menor a mayor'));
    sel.value = '';
  }
  heads.forEach(h => h.addEventListener('click', () => {
    const k = h.dataset.k;
    dir = k === clave ? -dir : DEF[k];
    clave = k;
    pintar();
  }));
  sel.addEventListener('change', () => {
    if (!sel.value) return;
    const [k, d] = sel.value.split(':');
    clave = k; dir = +d;
    pintar();
  });
  chips.forEach(c => c.addEventListener('click', () => {
    grupo = c.dataset.g;
    chips.forEach(x => x.setAttribute('aria-pressed', x === c));
    pintar();
  }));
</script>
</body>
</html>
"""

# la librería de TradingView se publica en /charting_library/ (la inyecta el
# workflow al publicar) y no tiene nada que indexar
ROBOTS = """User-agent: *
Allow: /
Disallow: /charting_library/

Sitemap: https://carestia.cl/sitemap.xml
"""

# ---------------- Navegación y pie comunes (todas las páginas) ----------------
# Portada, fichas y páginas del sitio llevan la misma navegación en el
# encabezado y cierran con el mismo pie. URLs absolutas al dominio canónico,
# como el resto de los links del sitio (el 404 se sirve en cualquier ruta).
# Desktop: los links van en una fila propia bajo la marca. Móvil (≤640px): se
# pliegan en un <details> "Menú" que ocupa la fila del wordmark: sin scroll
# horizontal, sin JS y sin sumar filas al encabezado de la portada.
SITIO = "https://carestia.cl"
NAV = [   # (clave, texto, href, modo de /graficos.html que abre en el lugar)
    ("indices", "Índices", f"{SITIO}/graficos.html", "indices"),
    ("productos", "Productos", f"{SITIO}/productos/", None),
    # deep links de /graficos.html (#comparar = alias de #productos)
    ("comparar", "Comparar", f"{SITIO}/graficos.html#comparar", "productos"),
    ("canasta", "Arma tu canasta", f"{SITIO}/graficos.html#canasta", "canasta"),
    ("metodologia", "Metodología", f"{SITIO}/metodologia.html", None),
    ("acerca", "Acerca de", f"{SITIO}/acerca.html", None),
]
PIE_LINKS = [
    ("metodologia", "Metodología", f"{SITIO}/metodologia.html"),
    ("acerca", "Acerca de", f"{SITIO}/acerca.html"),
    ("contacto", "Contacto", f"{SITIO}/contacto.html"),
    ("terminos", "Términos de uso", f"{SITIO}/terminos.html"),
    ("privacidad", "Privacidad", f"{SITIO}/privacidad.html"),
    ("datos", "Datos abiertos (resumen.json)", f"{SITIO}/resumen.json"),
]
# atribución ODEPA CC-BY y deslinde: el mismo texto que ya tenía el pie de la
# portada, ahora en el pie de todas las páginas
PIE_ATTR = ('Fuente: precios al consumidor de ODEPA (<a href="https://datos.odepa.gob.cl">'
            'datos.odepa.gob.cl</a>, licencia CC-BY), deflactados con el IPC. Cada precio es el '
            'promedio de los puntos que ODEPA encuesta cada semana en la Región '
            'Metropolitana: ferias libres, supermercados y carnicerías. Por eso suele '
            'ser menor que el precio de supermercado. Canastas fijas; precios '
            'normalizados a kilo, unidad o litro según el envase que cotiza ODEPA.')
PIE_DISC = ('Información de consumo con fines analíticos. No constituye asesoría '
            'ni recomendación de inversión.')

# ---------------- Identidad común: fuentes, tokens y base ----------------
# Una sola llamada a Google Fonts, igual en todas las páginas, con los pesos
# que se usan: IBM Plex Sans para la interfaz y el texto, IBM Plex Mono solo
# para etiquetas cortas en mayúsculas y Space Grotesk solo para el wordmark,
# los títulos de sección de la portada y las cifras grandes.
FUENTES = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">"""

# Favicon: la í del wordmark (tallo hueso, acento brasa) sobre el fondo.
ICONO = ("<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
         "viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%230f0f0e'/%3E"
         "%3Crect x='28.5' y='28' width='7' height='24' rx='2' fill='%23e4dacc'/%3E"
         "%3Cpath d='M29.5 22L39 13.5' stroke='%23e8743b' stroke-width='7' "
         "stroke-linecap='round' fill='none'/%3E%3C/svg%3E\">")

# Los tokens de color y de familia viven SOLO aquí (cada página los recibe en
# su :root); los gráficos y la captura PNG los leen con getComputedStyle.
CSS_BASE = r"""
  /* fallbacks métricos: Arial ajustada a las métricas de cada webfont para
     que el swap no reacomode el wordmark, las cifras ni el texto (CLS) */
  @font-face { font-family:"Space Grotesk Fallback"; src:local("Arial");
    size-adjust:101.7%; ascent-override:96.9%; descent-override:29.2%;
    line-gap-override:0%; }
  @font-face { font-family:"IBM Plex Sans Fallback"; src:local("Arial");
    size-adjust:99.5%; ascent-override:103%; descent-override:27.6%;
    line-gap-override:0%; }
  :root {
    /* base neutra. Sobre --bg, hueso 13,9:1, secundario 7,2:1 y
       terciario 5,0:1 (AA); sobre --panel, 13,0, 6,7 y 4,6 */
    --bg:#0f0f0e; --panel:#171716; --line:#2b2a27;
    --bone:#e4dacc; --ash:#a39e95; --dim:#86817a;
    /* derivados de la base: hover de los controles y grilla de gráficos */
    --hover:#201f1d; --grid:#1c1c1a;
    /* brasa: solo la í del wordmark y la línea de los índices oficiales */
    --ember:#e8743b;
    /* semáforo: solo el veredicto y las velas de los 4 índices */
    --verde:#5bbf7a; --ambar:#e0a83c; --rojo:#e0552f; --verdict:var(--rojo);
    /* Comparar productos: cuatro tonos muy distintos, sin azules ni
       violetas azulados, sin verde, naranjo ni rojo (rosa, magenta, blanco
       cálido y amarillo); del 5º al 8º producto se repiten punteados. Los
       tres primeros, los que Comparar muestra al entrar, quedan a 18 o más
       entre sí (OKLab x100) aun con daltonismo simulado */
    --cmp1:#f28cc0; --cmp2:#b04fb5; --cmp3:#f4f1ea; --cmp4:#f2d74e;
    /* crosshair de los gráficos: hueso tenue */
    --cruz:rgba(228,218,204,.35);
    --sans:"IBM Plex Sans","IBM Plex Sans Fallback",system-ui,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,monospace;
    --display:"Space Grotesk","Space Grotesk Fallback",sans-serif;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--bone); font-family:var(--sans);
    font-variant-numeric:tabular-nums; min-height:100vh; }
  button, input { font-family:inherit; }
"""

# Cinta de índices y encabezado con el wordmark grande: los comparten la
# portada y /graficos.html (la portada arma la cinta en el HTML, con links
# a cada índice; en /graficos.html la arma el JS, con botones).
CSS_CABECERA = r"""  /* ---- ticker ---- */
  .ticker { position:sticky; top:0; z-index:50; display:flex; align-items:stretch;
    background:var(--bg); border-bottom:1px solid var(--line); min-height:44px; }
  .ticker .tag { display:none; align-items:center; padding:0 18px;
    border-right:1px solid var(--line); font:600 10px var(--mono);
    letter-spacing:.18em; color:var(--ash); white-space:nowrap; }
  .ticker-scroll { flex:1; overflow-x:auto; overflow-y:hidden;
    scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .ticker-scroll::-webkit-scrollbar { display:none; }
  .ticker-track { display:flex; width:max-content; min-height:44px;
    animation:car-marquee 60s linear infinite; }
  /* pausa al foco y, en táctil, mientras el dedo esté sobre el ticker
     (.tocado la pone touchstart y la saca touchend); pausado, el scroll
     manual sigue disponible. El hover pausa solo donde existe hover real:
     en táctil queda pegado tras el toque y no reanudaría nunca */
  .ticker-scroll:focus-within .ticker-track,
  .ticker-scroll.tocado .ticker-track { animation-play-state:paused; }
  @media (hover:hover) {
    .ticker-scroll:hover .ticker-track { animation-play-state:paused; }
  }
  .titem { display:flex; align-items:center; gap:10px; padding:0 22px; cursor:pointer;
    white-space:nowrap; border-right:1px solid var(--grid); background:none; border-top:0;
    border-bottom:0; border-left:0; min-height:44px; }
  .titem:hover { background:var(--hover); }
  .titem .tn { font:600 11px var(--mono); letter-spacing:.1em; color:var(--bone); }
  .titem .tp { font:500 13px var(--sans); color:var(--bone); }
  .titem .td { font:500 12px var(--sans); color:var(--ash); } /* deltas SIEMPRE en secundario */
  @media (min-width:760px) {
    .ticker .tag { display:flex; }
    .ticker-scroll { overflow-x:hidden; }
  }
  @keyframes car-marquee { from{transform:translateX(0)} to{transform:translateX(-50%)} }

  /* ---- header ---- */
  header { display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 18px;
    justify-content:space-between; padding:16px clamp(16px,3vw,32px) 12px;
    border-bottom:1px solid var(--line); }
  .brand { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 18px; }
  /* line-height y alto explícitos: el alto del wordmark depende solo del
     font-size, no de la métrica de la fuente que esté cargada (CLS) */
  .wordmark { font:700 clamp(20px,4vw,26px)/1.15 var(--display);
    letter-spacing:.06em; color:var(--bone); display:flex; align-items:baseline;
    height:1.15em; }
  /* í-brasa: el texto real del nodo lleva la Í única (innerText, copy-paste
     y lectores de pantalla leen CARESTÍA); el adorno es un ::after
     decorativo que repinta la misma Í en brasa y el clip-path deja visible
     solo el acento, tapando el de hueso que queda debajo (mismo glifo,
     misma posición: solape exacto). Al cuerpo del header (20-26px) la
     tilde va siempre plana, sin glow: a ese tamaño el halo es más grande
     que el acento y lo vuelve una mancha. El 86% está calibrado al pixel
     en Chromium a 20 y 26px: menos corta el tallo, más corta el acento.
     El box del span no cambia (la altura la fija line-height, no el
     glifo): el fix de CLS del wordmark queda intacto */
  .wordmark .i { position:relative; display:inline-block; }
  .wordmark .i::after { content:"Í"; content:"Í" / ""; position:absolute;
    left:0; top:0; pointer-events:none;
    color:var(--ember); clip-path:inset(0 0 86% 0); }
  /* line-height fijo en el texto del encabezado: su alto no cambia con la
     tipografía y el encuadre del lienzo (calc más abajo) sigue exacto */
  .tagline { font:400 13px/15.6px var(--sans); color:var(--ash); }
  .semana { font:500 12px/14.3px var(--sans); color:var(--ash); }
  .semana span { color:var(--dim); }
  a.wordmark, a.titem { text-decoration:none; }
"""

CSS_SITIO = r"""
  /* ---- navegación del sitio (común a todas las páginas) ---- */
  .sitenav { flex-basis:100%; }
  .sitenav ul { list-style:none; }
  .snav-links { display:flex; flex-wrap:wrap; gap:0 22px; }
  .snav-links a, .snav-panel a { font:500 11px var(--mono);
    letter-spacing:.08em; text-transform:uppercase; text-decoration:none; }
  .snav-links a { display:inline-block; padding:6px 0 5px; color:var(--ash);
    border-bottom:1px solid transparent; }
  .snav-links a:hover, .snav-links a:focus-visible { color:var(--bone);
    border-bottom-color:var(--dim); }
  .snav-links a[aria-current] { color:var(--bone); border-bottom-color:var(--bone); }
  /* móvil: el <summary> mide 34px de alto (área táctil de las pills) pero
     el margen negativo deja su caja en 22px, el alto de la fila del
     wordmark: el encabezado no crece */
  .snav-menu { display:none; position:relative; }
  .snav-menu > summary { display:flex; align-items:center; gap:8px;
    min-height:34px; margin:-6px 0; padding:0 14px; cursor:pointer;
    list-style:none; -webkit-user-select:none; user-select:none;
    font:600 11px var(--mono); letter-spacing:.1em;
    text-transform:uppercase; color:var(--bone); background:var(--panel);
    border:1px solid var(--line); border-radius:999px; }
  .snav-menu > summary::-webkit-details-marker { display:none; }
  .snav-menu > summary::after { content:"▾"; content:"▾" / ""; color:var(--ash); }
  .snav-menu[open] > summary { border-color:var(--bone); }
  .snav-panel { position:absolute; right:0; top:calc(100% + 12px); z-index:60;
    min-width:230px; max-width:calc(100vw - 32px); padding:4px 0;
    background:var(--panel); border:1px solid var(--line);
    box-shadow:0 14px 34px rgba(0,0,0,.55); }
  .snav-panel li + li { border-top:1px solid var(--line); }
  .snav-panel a { display:flex; align-items:center; min-height:44px;
    padding:0 18px; font-size:12px; color:var(--bone); }
  .snav-panel a:hover, .snav-panel a:focus-visible { background:var(--hover); }
  .snav-panel a[aria-current] { box-shadow:inset 3px 0 0 var(--bone); }
  @media (max-width:640px) {
    header { display:grid; grid-template-columns:minmax(0,1fr) auto;
      align-items:center; column-gap:12px; row-gap:6px; }
    header .brand { display:contents; }
    header .wordmark { grid-column:1; grid-row:1; }
    header .sitenav { grid-column:2; grid-row:1; }
    header .tagline, header .semana { grid-column:1 / -1; }
    header .semana { margin-top:2px; }
    .snav-links { display:none; }
    .snav-menu { display:block; }
  }

  /* ---- pie común ---- */
  /* todo el texto del pie cumple AA sobre --bg: secundario 7,2:1 y
     hueso 13,9:1 */
  .sitefoot { border-top:1px solid var(--line); background:var(--bg);
    padding:18px clamp(16px,3vw,32px) 24px; display:flex;
    flex-direction:column; gap:8px; }
  .sitefoot p { font:400 12px/1.6 var(--sans); color:var(--ash);
    text-wrap:pretty; }
  .sitefoot a { color:var(--bone); text-decoration:underline;
    text-decoration-color:var(--dim); text-underline-offset:3px; }
  .sitefoot a:hover, .sitefoot a:focus-visible { text-decoration-color:var(--bone); }
  .pie-links { display:flex; flex-wrap:wrap; gap:0 20px; list-style:none; }
  .pie-links a { display:inline-block; padding:6px 0;
    font:500 13px var(--sans); }
  .pie-links a[aria-current] { text-decoration-color:var(--bone); }
  /* RUT y fechas (78.521.796-9, 22-07-2026) no se cortan en el guion */
  .nw { white-space:nowrap; }
"""

# menú móvil: se cierra al tocar fuera o con Escape (sin JS abre y cierra
# igual con su propio botón)
JS_MENU = """<script>
  (function () {
    var m = document.querySelector('.snav-menu');
    if (!m) return;
    document.addEventListener('click', function (e) {
      if (m.open && !m.contains(e.target)) m.open = false;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && m.open) {
        m.open = false;
        m.querySelector('summary').focus();
      }
    });
  })();
</script>"""


def nav_sitio(actual: str = "", exacto: bool = True) -> str:
    """Navegación del encabezado. 'actual' marca la sección con aria-current
    ('page' en esa misma página; 'true' dentro de ella, como una ficha bajo
    Productos). El mismo <ul> va dos veces: en el <details> (móvil) y en
    línea (desktop); cada breakpoint muestra solo uno."""
    items = []
    for clave, texto, href, modo in NAV:
        attrs = f' data-modo="{modo}"' if modo else ""
        if clave == actual:
            attrs += f' aria-current="{"page" if exacto else "true"}"'
        items.append(f'<li><a href="{href}"{attrs}>{html.escape(texto)}</a></li>')
    lis = "\n        ".join(items)
    return (f'<nav class="sitenav" aria-label="Secciones del sitio">\n'
            f'      <details class="snav-menu">\n'
            f'        <summary>Menú</summary>\n'
            f'        <ul class="snav-panel">\n        {lis}\n        </ul>\n'
            f'      </details>\n'
            f'      <ul class="snav-links">\n        {lis}\n      </ul>\n'
            f'    </nav>')


def pie_sitio(actual: str = "", graficos: bool = False) -> str:
    """Pie común: links institucionales y legales, atribución ODEPA CC-BY,
    deslinde, razón social y el aviso de atribución de Lightweight Charts
    tal cual su NOTICE, con link directo a tradingview.com (sin rel). En las
    páginas con gráficos ('graficos'), además la atribución de Advanced
    Charts: "Gráficos de TradingView", también con link sin rel."""
    items = []
    for clave, texto, href in PIE_LINKS:
        cur = ' aria-current="page"' if clave == actual else ""
        items.append(f'<li><a href="{href}"{cur}>{html.escape(texto)}</a></li>')
    links = "\n      ".join(items)
    return (f'  <footer class="sitefoot">\n'
            f'    <nav aria-label="Información del sitio"><ul class="pie-links">\n'
            f'      {links}\n'
            f'    </ul></nav>\n'
            f'    <p class="pie-attr">{PIE_ATTR}</p>\n'
            f'    <p class="pie-disc">{PIE_DISC}</p>\n'
            # el RUT no se corta en el guion
            f'    <p class="pie-legal">© 2026 Carestía SpA, '
            f'<span class="nw">RUT 78.521.796-9</span>. '
            f'Contacto: <a href="mailto:pedro@carestia.cl">pedro@carestia.cl</a></p>\n'
            + (f'    <p class="pie-tv"><a href="https://www.tradingview.com/">'
               f'Gráficos de TradingView</a></p>\n' if graficos else '') +
            f'    <p class="pie-tv"><a href="https://www.tradingview.com/">'
            f'TradingView Lightweight Charts™. Copyright (c) 2023 TradingView, Inc.'
            f'</a></p>\n'
            f'  </footer>\n'
            f'{JS_MENU}')

# ---------------- Páginas estáticas por producto (SEO) ----------------
# Una página liviana por producto del catálogo, generada en el build con los
# datos de ESE producto inline (nunca el catálogo completo). Versión reducida
# de la estética del sitio: carbón/hueso/ceniza/brasa, wordmark chico con la
# tilde, sin ticker. La serie va compacta (t0 + enteros semanales) y se
# expande en el navegador igual que en el index.
PRODUCT_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="https://carestia.cl/productos/__SLUG__.html">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:image" content="https://carestia.cl/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
__ICONO__
__FUENTES__
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__
  header { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px;
    padding:14px clamp(16px,3vw,32px); border-bottom:1px solid var(--line);
    min-height:51px; }
  .wordmark { font:700 20px/1.1 var(--display); letter-spacing:.06em;
    color:var(--bone); text-decoration:none; display:inline-flex;
    align-items:baseline; height:22px; overflow:hidden; }
  /* í-brasa: misma construcción del index; el texto del nodo lleva la Í
     única y el ::after decorativo repinta el acento en brasa (clip-path) */
  .wordmark .i { position:relative; display:inline-block; }
  .wordmark .i::after { content:"Í"; content:"Í" / ""; position:absolute;
    left:0; top:0; pointer-events:none;
    color:var(--ember); clip-path:inset(0 0 86% 0); }
  .tagline { font:400 12px/14.3px var(--sans); color:var(--ash); }
  /* el gráfico usa el ancho de la página, como en /graficos.html, y el texto
     se alinea con él (y con la marca y el pie) a la izquierda, en un ancho
     de lectura */
  main { margin:0 auto;
    padding:clamp(20px,4vw,36px) clamp(16px,3vw,32px) clamp(28px,4vw,44px); }
  main > * { max-width:916px; }
  .miga { font:500 10px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  h1 { font:600 clamp(26px,5vw,40px)/1.15 var(--sans);
    letter-spacing:-.005em; margin-top:6px; }
  .orow { display:flex; align-items:baseline; gap:clamp(10px,2vw,18px);
    flex-wrap:wrap; margin-top:14px; min-height:52px; }
  .oprice { font:700 clamp(38px,7vw,64px)/1 var(--display);
    letter-spacing:-.01em; color:var(--bone); }
  /* en UF, la cifra grande va en UF y debajo, más chica, en pesos de hoy */
  .ocifra { display:flex; flex-direction:column; }
  .opesos { font:400 13px var(--sans); color:var(--ash); margin-top:6px; }
  .ouni { font:400 13px var(--sans); color:var(--ash); }
  .odelta { font:600 15px var(--sans); color:var(--ash); } /* deltas SIEMPRE en secundario */
  .odelta small { font:400 12px var(--sans); color:var(--dim); }
  .pct { font:400 15px/1.6 var(--sans); color:var(--bone);
    margin-top:12px; text-wrap:pretty; }
  /* altura reservada por CSS ANTES de que Lightweight Charts monte: la
     página no salta al renderizar (svh: estable frente a la barra móvil) */
  /* la unidad del gráfico: pesos de hoy, precio de la época o UF, en tres
     botones o, si no caben, en un desplegable (JS_UNIDAD), y su línea */
  .unidad { margin-top:18px; }
  .vtoggle { display:inline-flex; border:1px solid var(--line); background:var(--bg); }
  .vbtn { font:500 13px var(--sans); padding:8px 14px; border:none; cursor:pointer;
    background:transparent; color:var(--ash); min-height:34px; white-space:nowrap; }
  .vbtn + .vbtn { border-left:1px solid var(--line); }
  .vbtn.active { background:var(--bone); color:var(--bg); }
  .usel { display:none; font:500 13px var(--sans); color:var(--bone);
    background:var(--bg); border:1px solid var(--line); border-radius:0;
    min-height:34px; padding:0 6px; color-scheme:dark; cursor:pointer; }
  .unidad.compacta .ubtns { display:none; }
  .unidad.compacta .usel { display:block; }
  .utxt { font:400 12px/1.5 var(--sans); color:var(--ash); margin-top:8px;
    text-wrap:pretty; }
  #grafico { position:relative; max-width:none; height:clamp(320px,66vh,820px);
    height:clamp(320px,66svh,820px); margin-top:16px; }
  .fecha { font:500 12px var(--sans); color:var(--ash); margin-top:14px; }
  .ref-velas { font:400 12px/1.5 var(--sans); color:var(--dim); margin-top:10px; }
  /* otros productos del grupo: interlinking sobrio al pie, misma paleta
     del sitio (panel/línea/hueso, hover con borde hueso como .links) */
  .otros { margin-top:26px; }
  .otros-h { font:600 11px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  .otros-links { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
  .otros-links a { font:500 13px var(--sans); padding:9px 14px;
    min-height:34px; display:inline-flex; align-items:center;
    text-decoration:none; border:1px solid var(--line); color:var(--bone);
    background:var(--panel); }
  .otros-links a:hover { border-color:var(--bone); background:var(--hover); }
  .metodo { font:400 12px/1.6 var(--sans); color:var(--ash);
    margin-top:18px; text-wrap:pretty; }
  .disc { font:400 12px/1.6 var(--sans); color:var(--dim);
    margin-top:6px; }
  .links { display:flex; gap:12px; flex-wrap:wrap; margin-top:24px; }
  .links a { font:600 13px var(--sans);
    padding:9px 16px; min-height:34px; display:inline-flex; align-items:center;
    text-decoration:none; border:1px solid var(--line); color:var(--bone);
    background:var(--panel); border-radius:999px; }
  .links a:hover { border-color:var(--bone); background:var(--hover); }
  .nochart { display:flex; align-items:center; justify-content:center;
    height:100%; color:var(--ash); font-size:13px; padding:20px; text-align:center; }
  /* el gráfico llega después del primer pantallazo: mientras, un aviso tenue
     en el alto ya reservado */
  #grafico .cargando { color:var(--dim); }
__CSS_SITIO__
</style>
</head>
<body>

  <header>
    <!-- span único: un solo flex item para que innerText no parta el texto -->
    <a class="wordmark" href="https://carestia.cl/"><span>CAREST<span class="i">Í</span>A</span></a>
    <span class="tagline">Índices del costo de vida en Chile</span>
    __NAV__
  </header>

  <main>
    <div class="miga" id="miga">Precio real en Chile, en pesos de hoy</div>
    <h1>__LABEL__</h1>
    <div class="orow">
      <div class="ocifra">
        <div class="oprice" id="oprice">__PRECIO__</div>
        <div class="opesos" id="opesos" hidden></div>
      </div>
      <div class="ouni" id="ouni">por __UNI_TXT__, en pesos de hoy</div>
      <div class="odelta">__DELTA__ <small>sem.</small></div>
    </div>
    <p class="pct">__PCT_LINEA__</p>
    <div class="unidad" id="unidad">
      __SELECTOR_UNIDAD__
      <p class="utxt" id="utxt">__UNIDAD_REAL__</p>
    </div>
    <div id="grafico"><div class="nochart cargando">Cargando el gráfico...</div></div>
    <p class="ref-velas" id="ref-velas" hidden>Velas semanales. La mecha va del precio más bajo al más alto que ODEPA encontró entre los locales encuestados.</p>
    <div class="fecha">Semana del __FECHA__. Serie desde __ANIO__. Se actualiza los viernes.</div>
    __OTROS__
    <p class="metodo">Cada punto es el promedio de los puntos que ODEPA encuesta
      cada semana en la Región Metropolitana: ferias libres, supermercados y
      carnicerías, deflactado por IPC a pesos de hoy. Fuente: precios al
      consumidor ODEPA (datos.odepa.gob.cl, CC-BY). Actualizado cada viernes.</p>
    <p class="disc">Información de consumo con fines analíticos. No constituye
      asesoría ni recomendación de inversión.</p>
    <nav class="links">
      <a href="https://carestia.cl/">← todos los índices</a>
      <a href="https://carestia.cl/graficos.html#canasta=__CANASTA__">ármalo en una canasta →</a>
    </nav>
  </main>

__PIE__

<script>
  // serie compacta del producto: t0 + valores semanales consecutivos, null en
  // semanas sin dato (estacionales), y el rango de cada semana (la mecha de
  // las velas). La cifra y el texto ya están en el HTML: el gráfico se arma
  // después del primer pantallazo, en Advanced Charts (en línea, en hueso;
  // las velas a un clic) o, si la librería no está o no inicia en 8
  // segundos, en Lightweight como siempre. En los dos, la unidad del selector
  const T0 = '__T0__';
  const V = __V__;
  const MIN = __MIN__;
  const MAX = __MAX__;
  const SLUG = '__SLUG__';
  const NOMBRE = __NOMBRE__;
  const UNIDAD = '__UNIDAD__';
  const UNI_TXT = '__UNI_TXT__';
  const INDICES = __INDICES__;
  // el build trae datos/uf.json: hay opción UF
  const UF = __UF__;
  const LIGHTWEIGHT = 'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js';
  const fmt = v => '$' + Math.round(v).toLocaleString('es-CL');
  // colores desde los tokens de :root
  const vars = getComputedStyle(document.documentElement);
  const tok = n => vars.getPropertyValue('--' + n).trim();
  const el = document.getElementById('grafico');
  function cargarScript(src) {
    return new Promise((ok, mal) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = ok;
      s.onerror = mal;
      document.head.appendChild(s);
    });
  }
__JS_UNIDAD__
  // la unidad: en Advanced Charts es otro símbolo; en Lightweight, otra
  // serie. Sin carestia-tv.js (que calcula la época y la UF), pesos de hoy
  // (unidadLW: la que está dibujada en Lightweight, que cambia al llegar)
  let TV = null, feed = null, widget = null, lw = null, unidad = 'real', unidadLW = 'real';
  const unidadesHay = () => !feed ? ['real'] : UF ? ['real', 'epoca', 'uf'] : ['real', 'epoca'];
  const oprice = document.getElementById('oprice'), opesos = document.getElementById('opesos');
  const ouni = document.getElementById('ouni'), miga = document.getElementById('miga');
  const PRECIO = oprice.textContent, OUNI = ouni.textContent, MIGA = miga.textContent;
  function ponerUnidad(u) {
    if (unidadesHay().indexOf(u) === -1) u = 'real';
    unidad = u;
    selector.poner(u);
    pintarCifra();
    if (widget) {
      const c = widget.activeChart();
      if (c.symbol().split(':').pop().toLowerCase() !== SLUG + SUF[u]) {
        Promise.resolve(c.setSymbol(SLUG + SUF[u])).catch(() => {});
      }
    } else if (lw) lw(u);
  }
  const selector = selectorUnidad(ponerUnidad);
  // la cifra grande: en UF, la del producto en UF (el último cierre de su
  // serie) y debajo, más chica, en pesos de hoy. Con el precio de la época
  // queda la de pesos de hoy: en la última semana es la misma
  function pintarCifra() {
    if (unidad !== 'uf' || !feed) {
      oprice.textContent = PRECIO;
      ouni.textContent = OUNI;
      miga.textContent = MIGA;
      opesos.hidden = true;
      return;
    }
    feed.barras(SLUG + SUF.uf).then(b => {
      if (unidad !== 'uf' || !b || !b.length) return;
      oprice.textContent = TV.textoUF(b[b.length - 1].close);
      ouni.textContent = 'por ' + UNI_TXT;
      // el antetítulo deja de decir "en pesos de hoy": la cifra va en UF
      miga.textContent = MIGA.replace(/, en pesos de hoy$/, '');
      opesos.textContent = PRECIO + ' en pesos de hoy';
      opesos.hidden = false;
    }, () => {});
  }

  function lightweight() {
    el.dataset.motor = 'lightweight';
    cargarScript(LIGHTWEIGHT).then(() => {
      if (!window.LightweightCharts) throw new Error('sin motor');
      el.innerHTML = '';
      const DIA = 864e5, base = Date.parse(T0 + 'T00:00:00Z');
      const dia = ms => new Date(ms).toISOString().slice(0, 10);
      const serie = V.map((v, i) => {
        const time = dia(base + i * 7 * DIA);
        return v == null ? { time } : { time, value: v };
      });
      const chart = LightweightCharts.createChart(el, {
        autoSize: true,
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: tok('ash'),
          fontFamily: tok('sans') },
        grid: { vertLines: { color: tok('grid') }, horzLines: { color: tok('grid') } },
        rightPriceScale: { borderColor: tok('line') },
        timeScale: { borderColor: tok('line') },
        // fechas en castellano de Chile, como en la portada; la UF con decimales
        localization: { locale: 'es-CL', priceFormatter: v => unidadLW === 'uf' && TV ? TV.numUF(v) : fmt(v) },
        // misma política de gestos del sitio: la rueda acerca y mueve el
        // gráfico; el swipe vertical en táctil queda para la página
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
        handleScroll: { mouseWheel: true, vertTouchDrag: false,
          horzTouchDrag: true, pressedMouseMove: true },
        crosshair: { mode: 0,
          vertLine: { color: tok('cruz'), labelBackgroundColor: tok('line') },
          horzLine: { color: tok('cruz'), labelBackgroundColor: tok('line') } },
      });
      // un producto no es un índice oficial: su línea va en hueso (la brasa
      // queda para los índices)
      const linea = chart.addLineSeries({ color: tok('bone'), lineWidth: 2, priceLineVisible: false });
      linea.setData(serie);
      chart.timeScale().fitContent();
      // otra unidad: las semanas del datafeed, con huecos donde no hubo precio
      lw = u => {
        const datos = u === 'real' || !feed ? Promise.resolve(serie) :
          feed.barras(SLUG + SUF[u]).then(b => {
            const out = [];
            (b || []).forEach((x, i) => {
              if (i) for (let t = b[i - 1].time + 7 * DIA; t < x.time; t += 7 * DIA) out.push({ time: dia(t) });
              out.push({ time: dia(x.time), value: x.close });
            });
            return out;
          });
        datos.then(d => {
          if (unidad !== u) return;
          unidadLW = u;
          linea.applyOptions({ priceFormat: u === 'uf' ? { type: 'price', precision: 4, minMove: 0.0001 } :
            { type: 'price', precision: 0, minMove: 1 } });
          linea.setData(d);
          chart.timeScale().fitContent();
        }, () => { if (unidad === u && u !== unidadLW) ponerUnidad(unidadLW); });
      };
      if (unidad !== 'real') lw(unidad);
    }).catch(() => {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos (revisa la conexión).</div>';
    });
  }

  window.addEventListener('load', () => {
    cargarScript('/__TV_JS__?v=__VER_TV__').then(() => {
      TV = window.CarestiaTV;
      if (!TV) throw new Error('sin carestia-tv.js');
      // la serie ya viene en la página: el datafeed no la vuelve a pedir
      feed = TV.crearDatafeed({ base: '/datos/', ver: '__VER__', indices: INDICES, uf: UF,
        productos: [{ slug: SLUG, nombre: NOMBRE, unidad: UNIDAD }],
        precargados: { ['productos/' + SLUG + '.json']: { t0: T0, v: V, min: MIN, max: MAX } } });
      selector.limitar(unidadesHay());
      el.innerHTML = '';
      const EN = { real: ', en pesos de hoy', epoca: ', precio de la época', uf: ', en UF' };
      return TV.montar({ contenedor: el, libreria: '/charting_library/', simbolo: SLUG + SUF[unidad],
        datafeed: feed, tok, sitio: true, css: location.origin + '/__TV_CSS__?v=__VER_CSS__',
        // sus unidades, listas para superponer desde Comparar (la lista no
        // cambia después: van todas, sea cual sea la del selector)
        comparar: unidadesHay().map(u => ({ symbol: SLUG + SUF[u], title: NOMBRE + EN[u] })) });
    }).then(w => {
      widget = w;
      el.dataset.motor = 'advanced';
      // la referencia de las velas, mientras estén a la vista: en semanas, la
      // frase completa; en temporalidades largas cada vela junta semanas
      const ref = document.getElementById('ref-velas'), REF = ref.textContent;
      const c = w.activeChart();
      const ver = t => {
        ref.hidden = t !== 1;
        const p = TV.temporalidad(c.resolution());
        ref.textContent = p && p.nombre !== TV.RESOLUCION ? REF.replace('Velas semanales. ', '') : REF;
      };
      ver(c.chartType());
      c.onChartTypeChanged().subscribe(null, ver);
      c.onIntervalChanged().subscribe(null, () => setTimeout(() => ver(c.chartType()), 0));
      // la unidad elegida mientras el gráfico cargaba
      ponerUnidad(unidad);
    }, () => { selector.limitar(unidadesHay()); lightweight(); });
  });
</script>
</body>
</html>
"""

UNI_TXT = {"kg": "kilo", "un": "unidad", "l": "litro"}

# Nombre con que se muestran los grupos ODEPA. Solo el texto visible: los
# datos, las claves y los anclas (slug_url del nombre original) no cambian.
GRUPO_TXT = {
    "Carne de Cerdo - Ave - Cordero": "Carne de cerdo, ave y cordero",
    "Lácteos - Huevos - Margarinas": "Lácteos, huevos y margarinas",
}


def grupo_txt(g: str) -> str:
    return GRUPO_TXT.get(g, g)
QDEF = {"kg": "0.5", "un": "1", "l": "1"}   # cantidad por defecto del link de canasta


def slug_url(label: str) -> str:
    """Slug ESTABLE para la URL pública: minúsculas, sin tildes, espacios a
    guiones; solo [a-z0-9-]. Función pura del label: mismo label → mismo slug
    en todos los builds."""
    s = unicodedata.normalize("NFKD", label)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", "-", s.lower().strip())
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def fmt_clp(x: float) -> str:
    return "$" + f"{int(round(x)):,}".replace(",", ".")


def fmt_delta(vals: list) -> str:
    if len(vals) < 2 or not vals[-2]:
        return "·"
    d = (vals[-1] / vals[-2] - 1) * 100
    return ("▼" if d < 0 else "▲") + f"{abs(d):.1f}".replace(".", ",") + "%"


def es_femenino(label: str) -> bool:
    """Concordancia por la primera palabra del label (la palta / el asado)."""
    return label.split()[0].lower().endswith("a")


def seccion_otros(slug: str, grupo: str, rueda: list, labels: dict) -> str:
    """Sección "Otros productos de {grupo}" con enlaces a los 4 SIGUIENTES
    slugs en la rueda alfabética del grupo (circular). Selección DETERMINISTA:
    función pura del catálogo, el mismo set de productos produce los mismos
    enlaces en todos los builds (crawl estable, nunca aleatoria). Con menos
    de 2 productos en el grupo no hay sección."""
    i = rueda.index(slug)
    vecinos = [rueda[(i + j) % len(rueda)] for j in range(1, len(rueda))][:4]
    if not vecinos:
        return ""
    enlaces = "\n      ".join(
        f'<a href="https://carestia.cl/productos/{v}.html">'
        f'{html.escape(labels[v])}</a>' for v in vecinos)
    return (f'<section class="otros" aria-label="Otros productos de '
            f'{html.escape(grupo_txt(grupo), quote=True)}">\n'
            f'      <h2 class="otros-h">Otros productos de '
            f'{html.escape(grupo_txt(grupo))}</h2>\n'
            f'      <nav class="otros-links">\n'
            f'      {enlaces}\n'
            f'      </nav>\n'
            f'    </section>')


def fin_serie(p: dict) -> datetime.date:
    """Semana del último valor publicado de una serie compacta (t0 + v)."""
    return (datetime.date.fromisoformat(p["t0"]) +
            datetime.timedelta(weeks=len(p["v"]) - 1))


def semana_vigente(prods) -> datetime.date:
    """La semana más reciente del catálogo: la vara con que se decide si el
    precio de un producto es "de hoy" o de una semana anterior."""
    return max((fin_serie(p) for p in prods if any(v is not None for v in p["v"])),
               default=None)


# sobre este umbral el producto va a "Sin datos hace más de un año"
SEMANAS_SIN_DATOS = 52


def sin_datos_hace_un_anio(fin: datetime.date, semana: datetime.date) -> bool:
    return semana is not None and (semana - fin).days > SEMANAS_SIN_DATOS * 7


# ---------------- Datos a demanda (datos/) ----------------
# /graficos.html lleva inline solo el primer pantallazo: el resumen de los 4
# índices, la serie del índice que se muestra al cargar y la lista de
# productos sin series (los selectores y los links de canasta la necesitan
# de entrada). El resto se pide al necesitarlo:
#   datos/indices/{codigo}.json   el índice completo, con su serie
#   datos/productos/{slug}.json   la serie de un producto (Comparar y canasta)
#   datos/catalogo.json           resumen liviano por producto
# indices.json se sigue generando y publicando igual. Las series de índice
# van compactas, como las de producto: t0 (lunes de la primera semana) y un
# valor por semana consecutiva, null donde no hay dato; las velas como
# [open, high, low, close]. El build verifica que se expanden sin pérdida.
DATOS = "datos"
SERIES_INDICE = ("real", "nominal", "velas")
RESUMEN_INDICE = ("nombre", "subtitulo", "fecha", "costo_real", "veredicto",
                  "color", "percentil", "n", "vs_promedio")


def _json(obj) -> str:
    """JSON compacto, con tildes literales."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def expandir_indice(c: dict) -> dict:
    """Inversa de compactar_indice; la portada hace lo mismo en el navegador."""
    if not c["t0"]:
        return {k: [] for k in SERIES_INDICE}
    base = datetime.date.fromisoformat(c["t0"])

    def t(i):
        return (base + datetime.timedelta(weeks=i)).isoformat()
    return {
        "real": [{"time": t(i), "value": v}
                 for i, v in enumerate(c["real"]) if v is not None],
        "nominal": [{"time": t(i), "value": v}
                    for i, v in enumerate(c["nominal"]) if v is not None],
        "velas": [{"time": t(i), "open": x[0], "high": x[1], "low": x[2], "close": x[3]}
                  for i, x in enumerate(c["velas"]) if x is not None],
    }


def compactar_indice(code: str, d: dict) -> dict:
    """real, nominal y velas de un índice en forma compacta. Si la serie no
    cae en la grilla semanal o no vuelve idéntica al expandirla, el build se
    detiene: nunca se publica una serie distinta de la de indices.json."""
    tiempos = [p["time"] for k in SERIES_INDICE for p in d.get(k) or []]
    if not tiempos:
        return {"t0": None, **{k: [] for k in SERIES_INDICE}}
    base = datetime.date.fromisoformat(min(tiempos))

    def arreglo(puntos, valor):
        out = []
        for p in puntos:
            dias = (datetime.date.fromisoformat(p["time"]) - base).days
            if dias % 7:
                raise SystemExit(f"build_site.py: {code}: {p['time']} no cae en "
                                 f"la grilla semanal que parte el {base}.")
            i = dias // 7
            out.extend([None] * (i + 1 - len(out)))
            out[i] = valor(p)
        return out
    c = {"t0": base.isoformat(),
         "real": arreglo(d.get("real") or [], lambda p: p["value"]),
         "nominal": arreglo(d.get("nominal") or [], lambda p: p["value"]),
         "velas": arreglo(d.get("velas") or [],
                          lambda p: [p["open"], p["high"], p["low"], p["close"]])}
    if expandir_indice(c) != {k: d.get(k) or [] for k in SERIES_INDICE}:
        raise SystemExit(f"build_site.py: {code}: la serie compacta no reproduce "
                         f"la de indices.json.")
    return c


def resumen_indice(d: dict) -> dict:
    """Lo que /graficos.html (y la cinta y las tarjetas de la portada)
    muestra de un índice sin su serie: el overlay, el ticker, la
    estacionalidad y los componentes. La variación semanal es la
    misma cuenta que hacía el navegador con las dos últimas semanas, sin
    redondear, para que la cifra mostrada no cambie."""
    r = {k: d[k] for k in RESUMEN_INDICE}
    real = d.get("real") or []
    r["delta"] = ((real[-1]["value"] / real[-2]["value"] - 1) * 100
                  if len(real) >= 2 and real[-2]["value"] else None)
    r["estacionalidad"] = d.get("estacionalidad") or {}
    r["componentes"] = [{k: c.get(k) for k in ("label", "qty", "unidad", "aporte")}
                        for c in d.get("componentes") or []]
    return r


def slugs_de_datos(prods: dict, fichas: dict) -> dict:
    """{clave: slug} para datos/productos/{slug}.json. Es el slug de la ficha
    (productos/{slug}.html) cuando la hay; si no (label sin slug o colisión),
    uno derivado que no pisa ninguno. La clave sigue siendo la de indices.json:
    es la que usan los links de canasta ya compartidos."""
    out = {clave: slug for slug, (clave, _label) in fichas.items()}
    usados = set(out.values()) | {"index"}
    for clave in sorted(prods):
        if clave in out:
            continue
        base = slug_url(prods[clave]["label"]) or "producto"
        slug, n = base, 2
        while slug in usados:
            slug, n = f"{base}-{n}", n + 1
        usados.add(slug)
        out[clave] = slug
    return out


def generar_catalogo(prods: dict, slugs: dict) -> dict:
    """datos/catalogo.json: una fila liviana por producto con datos, en el
    orden de /productos/ (grupo A-Z, "Otros" al final, y nombre). Variaciones
    en pesos de hoy contra 1, 13 y 52 semanas antes (null si esa semana no
    tiene dato); percentil como el de los índices (semanas con precio menor
    o igual al último); las últimas 52 semanas del calendario, con null donde
    no hubo precio."""
    filas = []
    for clave, p in prods.items():
        v = p["v"]
        con_dato = [i for i, x in enumerate(v) if x is not None]
        if not con_dato:
            continue
        i = con_dato[-1]
        ult = v[i]

        def variacion(k, i=i, ult=ult, v=v):
            j = i - k
            return round((ult / v[j] - 1) * 100, 1) if j >= 0 and v[j] else None
        vals = [v[j] for j in con_dato]
        grupo = p.get("grupo") or "Otros"
        semana = (datetime.date.fromisoformat(p["t0"]) +
                  datetime.timedelta(weeks=i)).isoformat()
        filas.append(((grupo == "Otros", _orden(grupo), _orden(p["label"])), {
            "slug": slugs[clave],
            "clave": clave,
            "nombre": p["label"],
            "grupo": grupo_txt(grupo),
            "unidad": p["unidad"],
            "semana": semana,
            "precio_pesos_hoy": ult,
            "variacion_1s_pct": variacion(1),
            "variacion_13s_pct": variacion(13),
            "variacion_52s_pct": variacion(52),
            "percentil": round(100 * sum(1 for x in vals if x <= ult) / len(vals)),
            "ultimas_52": [None if x is None else int(round(x))
                           for x in v[max(0, i - 51):i + 1]],
        }))
    filas.sort(key=lambda f: f[0])
    productos = [f[1] for f in filas]
    return {"semana": max((f["semana"] for f in productos), default=None),
            "productos": productos}


def rango_productos(prods: dict) -> list:
    """[primer año, último año] con dato en todo el catálogo (Comparar)."""
    anios = []
    for p in prods.values():
        con_dato = [i for i, x in enumerate(p["v"]) if x is not None]
        if con_dato:
            t0 = datetime.date.fromisoformat(p["t0"])
            anios += [(t0 + datetime.timedelta(weeks=con_dato[0])).year,
                      (t0 + datetime.timedelta(weeks=con_dato[-1])).year]
    return [min(anios), max(anios)] if anios else None


def escribir_json(ruta: str, obj) -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(_json(obj))


# ---------------- UF y unidades de los gráficos ----------------
# Los gráficos se ven en pesos de hoy (por defecto), a precio de la época o en
# UF. La UF de cada semana es su precio de la época dividido por la UF del
# lunes en que empieza: el datafeed la calcula con datos/uf.json, que escribe
# uf.py (aparte de indices.py) con la UF de cada lunes. Si falta o no cubre
# todas las semanas de las series, el sitio sale sin la opción UF y el build
# lo avisa.
UF_JSON = os.path.join(DATOS, "uf.json")
UNIDADES = ("real", "epoca", "uf")
UNIDAD_NOMBRE = {"real": "Pesos de hoy", "epoca": "Precio de la época", "uf": "UF"}
# la línea bajo el selector: textos del dueño, literales
UNIDAD_TXT = {
    "real": "Cada precio pasado, llevado a pesos de hoy con la inflación. "
            "Sirve para comparar años distintos.",
    "epoca": "Lo que costaba en su momento, tal como salía en la boleta.",
    "uf": "Cada precio dividido por el valor de la UF de esa semana. Como la UF "
          "sube con la inflación, también sirve para comparar años distintos.",
}


def semanas_de_las_series() -> tuple:
    """(primer lunes, último lunes) con dato entre índices y productos."""
    fechas = []
    for d in DATA["indices"].values():
        for k in SERIES_INDICE:
            fechas += [p["time"] for p in d.get(k) or []]
    for p in DATA.get("productos", {}).values():
        con_dato = [i for i, x in enumerate(p["v"]) if x is not None]
        if con_dato:
            t0 = datetime.date.fromisoformat(p["t0"])
            fechas += [(t0 + datetime.timedelta(weeks=i)).isoformat()
                       for i in (con_dato[0], con_dato[-1])]
    if not fechas:
        return None, None
    return (datetime.date.fromisoformat(min(fechas)),
            datetime.date.fromisoformat(max(fechas)))


def _no_es_json(constante):
    raise ValueError(f"{constante} no es JSON")


def cargar_uf():
    """datos/uf.json si existe, el navegador lo puede leer y trae la UF
    (positiva) de cada uno de sus lunes, desde la primera hasta la última
    semana de las series; si no, None y un aviso. Nunca corta el build."""
    def aviso(motivo):
        print(f"AVISO UF: {motivo}. El sitio sale sin la opción UF.")
        return None
    try:
        with open(UF_JSON, encoding="utf-8") as fh:
            # estricto: NaN e Infinity no son JSON y el navegador no los lee
            uf = json.load(fh, parse_constant=_no_es_json)
        t0 = datetime.date.fromisoformat(uf["t0"])
        v = uf["v"]
        # t0 aaaa-mm-dd, como lo lee el datafeed (Date.parse no lee otras
        # formas ISO que Python sí acepta, como 20071231 o 2008-W01-1)
        if (uf["t0"] != t0.isoformat() or t0.weekday() != 0 or not isinstance(v, list)
                or not v):
            return aviso(f"{UF_JSON} no viene por semanas desde un lunes")
        # se escribe como lo hará el build (la versión de datos/ lo incluye)
        _json(uf).encode("utf-8")
        ini, fin = semanas_de_las_series()
        if ini is None:
            return aviso("no hay series")
        i, j = (ini - t0).days // 7, (fin - t0).days // 7
        if i < 0 or j >= len(v):
            ult = t0 + datetime.timedelta(weeks=len(v) - 1)
            return aviso(f"{UF_JSON} va de {t0} a {ult} y las series, de {ini} a {fin}")
        malas = [t0 + datetime.timedelta(weeks=k) for k, x in enumerate(v)
                 if isinstance(x, bool) or not isinstance(x, (int, float))
                 or not math.isfinite(x) or not x > 0]
        if malas:
            return aviso(f"{UF_JSON} no trae la UF de {len(malas)} lunes (el primero, {malas[0]})")
        print(f"UF: {UF_JSON}, {uf.get('fuente', 'sin fuente')}, de {t0} a "
              f"{t0 + datetime.timedelta(weeks=len(v) - 1)}; la del lunes {fin}: {v[j]}")
        return uf
    except FileNotFoundError:
        return aviso(f"no está {UF_JSON} (uf.py no corrió o no obtuvo la UF)")
    except Exception as e:  # noqa: un uf.json roto nunca corta el build
        return aviso(f"{UF_JSON} no se puede leer ({type(e).__name__}: {str(e)[:120]})")


def selector_unidad(con_uf: bool) -> str:
    """Pesos de hoy, Precio de la época y UF: tres botones o, si no caben en
    su fila, un desplegable (lo decide JS_UNIDAD). Sin datos/uf.json, sin UF."""
    unidades = [u for u in UNIDADES if con_uf or u != "uf"]
    botones = "\n        ".join(
        f'<button class="vbtn ubtn{" active" if u == "real" else ""}" type="button" '
        f'data-unidad="{u}" aria-pressed="{"true" if u == "real" else "false"}">'
        f'{UNIDAD_NOMBRE[u]}</button>' for u in unidades)
    opciones = "\n        ".join(
        f'<option value="{u}">{UNIDAD_NOMBRE[u]}</option>' for u in unidades)
    return (f'<div class="vtoggle ubtns" role="group" aria-label="Unidad">\n'
            f'        {botones}\n      </div>\n'
            f'      <select class="usel" aria-label="Unidad">\n'
            f'        {opciones}\n      </select>')


def leyenda_unidad(con_uf: bool, clase: str) -> str:
    """La leyenda de la línea del índice en /graficos.html: las unidades, con
    la de pesos de hoy a la vista y las otras atenuadas (pintarLeyenda las
    sigue al elegir)."""
    clase = f' class="{clase}"' if clase else ""
    tenue = ' style="opacity:.35"'
    return "\n      ".join(
        f'<span{clase} data-leyenda="{u}"{"" if u == "real" else tenue}>'
        f'<span class="sw"></span>{UNIDAD_NOMBRE[u]}</span>'
        for u in UNIDADES if con_uf or u != "uf")


# el selector de unidad en el navegador, igual en /graficos.html y las fichas.
# Prueba con los botones y, si la fila se desborda, pasa al desplegable
JS_UNIDAD = r"""  /* ---------- selector de unidad ---------- */
  // Pesos de hoy, Precio de la época o UF: tres botones o, si no caben en su
  // fila, un desplegable; bajo el selector, la línea de la unidad elegida
  const UNIDAD_TXT = __UNIDAD_TXT__;
  const SUF = { real: '', epoca: '-epoca', uf: '-uf' };
  function selectorUnidad(alElegir) {
    const caja = document.getElementById('unidad');
    const fila = document.getElementById(caja.dataset.fila) || caja;
    const botones = [...caja.querySelectorAll('.ubtn')];
    const lista = caja.querySelector('.usel');
    const linea = document.getElementById('utxt');
    // se mide la fila sin envolver (.midiendo): si los botones no caben en
    // ella junto a lo demás, va el desplegable
    function medir() {
      caja.classList.remove('compacta');
      fila.classList.add('midiendo');
      const desborda = fila.scrollWidth > fila.clientWidth + 1;
      fila.classList.remove('midiendo');
      if (desborda) caja.classList.add('compacta');
    }
    function poner(u) {
      botones.forEach(b => {
        const on = b.dataset.unidad === u;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      lista.value = u;
      linea.textContent = UNIDAD_TXT[u];
    }
    botones.forEach(b => { b.onclick = () => alElegir(b.dataset.unidad); });
    lista.onchange = () => alElegir(lista.value);
    medir();
    addEventListener('resize', medir);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(medir);
    return {
      poner, medir,
      // solo las unidades que hay; con una sola no hay selector
      limitar(unidades) {
        botones.forEach(b => { b.hidden = unidades.indexOf(b.dataset.unidad) === -1; });
        [...lista.options].forEach(o => { o.disabled = o.hidden = unidades.indexOf(o.value) === -1; });
        caja.hidden = unidades.length < 2;
        medir();
      },
    };
  }
"""


def generar_datos(slugs: dict, catalogo: dict, uf: dict = None) -> dict:
    """Escribe datos/ y devuelve lo que va inline en /graficos.html. 'uf' es
    datos/uf.json ya validado (cargar_uf), o None si el sitio sale sin UF."""
    indices = DATA["indices"]
    prods = DATA.get("productos", {})
    series = {code: compactar_indice(code, d) for code, d in indices.items()}
    for code, d in indices.items():
        completo = {k: v for k, v in d.items() if k not in SERIES_INDICE}
        completo["serie"] = series[code]
        escribir_json(os.path.join(DATOS, "indices", f"{code}.json"), completo)
    for clave, p in prods.items():
        escribir_json(os.path.join(DATOS, "productos", f"{slugs[clave]}.json"), p)
    escribir_json(os.path.join(DATOS, "catalogo.json"), catalogo)
    primero = next(iter(indices))
    return {
        "indices": {code: resumen_indice(d) for code, d in indices.items()},
        "series": {primero: series[primero]},
        "productos": {clave: {"label": p["label"], "grupo": p.get("grupo") or "Otros",
                              "unidad": p["unidad"], "slug": slugs[clave]}
                      for clave, p in prods.items()},
        "rango": rango_productos(prods),
        # versión de los datos: los pedidos a datos/ la llevan en la URL para
        # que el navegador no mezcle archivos de dos builds distintos (con la
        # UF, también la de datos/uf.json)
        "ver": hashlib.sha1((_json(DATA) + (_json(uf) if uf else "")).encode("utf-8"))
                      .hexdigest()[:10],
        # datos/uf.json cubre todas las semanas: la opción UF existe
        "uf": bool(uf),
    }


def pagina_producto(key: str, p: dict, slug: str, otros_html: str = "",
                    semana: datetime.date = None) -> str:
    """Renderiza la página estática de UN producto con sus datos inline.
    'semana' es la semana vigente del catálogo: si el último dato del
    producto es de otra semana (mismo criterio que el "precio de la semana
    del…" de /productos/), ni el texto ni la descripción dicen "Hoy"."""
    vals = [v for v in p["v"] if v is not None]
    ult = vals[-1]
    n = len(vals)
    anio = p["t0"][:4]
    fecha_fin = fin_serie(p)
    antiguo = semana is not None and fecha_fin != semana
    fecha_txt = fecha_fin.strftime("%d-%m-%Y")
    fem = es_femenino(p["label"])
    art, de = ("la", "de la") if fem else ("el", "del")
    label_frase = p["label"][0].lower() + p["label"][1:]
    uni_txt = UNI_TXT.get(p["unidad"], p["unidad"])
    precio = fmt_clp(ult)

    # percentil sobre la serie real completa: en qué fracción de las semanas
    # el precio fue menor (más caro) o mayor (más barato) que el de hoy
    pct_caro = round(100 * sum(1 for v in vals if v < ult) / n)
    pct_barato = round(100 * sum(1 for v in vals if v > ult) / n)
    if antiguo:
        cuando, esta = "En esa semana", "estaba"
    else:
        cuando, esta = "Hoy", "está"
    if pct_caro >= pct_barato:
        adj = "cara" if fem else "caro"
        pct_linea = (f"{cuando} {esta} más {adj} que en el {pct_caro}% de las "
                     f"semanas desde {anio}, en pesos de hoy.")
    else:
        adj = "barata" if fem else "barato"
        pct_linea = (f"{cuando} {esta} más {adj} que en el {pct_barato}% de las "
                     f"semanas desde {anio}, en pesos de hoy.")

    title = f"Precio {de} {label_frase} en Chile: histórico desde {anio} | Carestía"
    if antiguo:
        ultimo = f"Último precio publicado por ODEPA (semana del {fecha_txt})"
        pct_linea = f"{ultimo}. {pct_linea}"
        desc = (f"{ultimo}: {precio} por {uni_txt} {de} {label_frase} en Chile "
                f"(promedio de ferias, supermercados y carnicerías de la RM, "
                f"en pesos de hoy). Serie semanal desde {anio} con datos ODEPA.")
    else:
        desc = (f"Hoy {art} {label_frase} cuesta {precio} por {uni_txt} en Chile "
                f"(promedio de ferias, supermercados y carnicerías de la RM, "
                f"en pesos de hoy). Serie semanal desde {anio} con datos ODEPA, "
                f"actualizada cada viernes.")

    out = PRODUCT_HTML
    for token, valor in [
        ("__TITLE__", html.escape(title, quote=True)),
        ("__DESC__", html.escape(desc, quote=True)),
        ("__SLUG__", slug),
        ("__LABEL__", html.escape(p["label"])),
        ("__PRECIO__", precio),
        ("__UNI_TXT__", uni_txt),
        ("__DELTA__", fmt_delta(vals)),
        ("__PCT_LINEA__", html.escape(pct_linea)),
        ("__FECHA__", fecha_txt),
        ("__ANIO__", anio),
        ("__CANASTA__", f"{key}:{QDEF.get(p['unidad'], '1')}"),
        ("__T0__", p["t0"]),
        ("__V__", json.dumps(p["v"])),
        # el rango semanal (mecha de las velas); vacío si indices.json no lo trae
        ("__MIN__", json.dumps(p.get("min") or [])),
        ("__MAX__", json.dumps(p.get("max") or [])),
        # Advanced Charts: el datafeed, sus versiones y lo que la ficha ya sabe
        ("__NOMBRE__", json.dumps(p["label"], ensure_ascii=False).replace("</", "<\\/")),
        ("__UNIDAD__", p["unidad"]),
        ("__INDICES__", indices_tv()),
        ("__TV_JS__", TV_JS),
        ("__VER_TV__", _ver(FEED_JS)),
        ("__TV_CSS__", TV_CSS),
        ("__VER_CSS__", _ver(tv_css())),
        ("__VER__", APP["ver"]),
        # la unidad: el selector, su línea y su JS; UF solo con datos/uf.json
        ("__UF__", "true" if APP["uf"] else "false"),
        ("__SELECTOR_UNIDAD__", selector_unidad(APP["uf"])),
        ("__UNIDAD_REAL__", UNIDAD_TXT["real"]),
        ("__JS_UNIDAD__", JS_UNIDAD),
        ("__UNIDAD_TXT__", _json(UNIDAD_TXT)),
        # HTML ya renderizado (seccion_otros escapa labels y grupo), no
        # se vuelve a escapar aquí
        ("__OTROS__", otros_html),
        # identidad, navegación y pie comunes; la ficha vive bajo /productos/
        ("__ICONO__", ICONO),
        ("__FUENTES__", FUENTES),
        ("__CSS_BASE__", CSS_BASE),
        ("__CSS_SITIO__", CSS_SITIO),
        ("__NAV__", nav_sitio("productos", exacto=False)),
        ("__PIE__", pie_sitio(graficos=True)),
    ]:
        out = out.replace(token, valor)
    return out


def asignar_fichas(prods: dict) -> dict:
    """Las fichas a publicar, {slug: (clave, label)} (para las fichas, el
    sitemap, /productos/ y los nombres de datos/productos/). Detecta
    colisiones de slug: son URLs públicas indexables y dos labels no pueden
    compartir una."""
    slugs = {}
    for key in sorted(prods):
        p = prods[key]
        if not any(v is not None for v in p["v"]):
            continue
        slug = slug_url(p["label"])
        # "index" es productos/index.html, el listado de fichas
        if not slug or slug == "index":
            print(f"AVISO: label sin slug utilizable, se omite: {p['label']!r}")
            continue
        if slug in slugs:
            # la URL pública ya publicada no se pisa: el label que llegó
            # después (orden estable por clave) queda fuera y se reporta
            print(f"COLISIÓN de slug '{slug}': {slugs[slug][1]!r} vs "
                  f"{p['label']!r}; se omite el segundo.")
            continue
        slugs[slug] = (key, p["label"])
    return slugs


def generar_productos(slugs: dict) -> None:
    """Escribe productos/{slug}.html por cada ficha de asignar_fichas."""
    prods = DATA.get("productos", {})
    # interlinking: rueda alfabética de slugs por grupo ODEPA (determinista)
    por_grupo = {}
    for slug, (key, _label) in slugs.items():
        g = prods[key].get("grupo") or "Otros"
        por_grupo.setdefault(g, []).append(slug)
    for lst in por_grupo.values():
        lst.sort()
    labels = {s: lab for s, (_k, lab) in slugs.items()}
    semana = semana_vigente(prods[k] for k, _l in slugs.values())
    os.makedirs("productos", exist_ok=True)
    for slug, (key, _label) in slugs.items():
        grupo = prods[key].get("grupo") or "Otros"
        otros = seccion_otros(slug, grupo, por_grupo[grupo], labels)
        with open(os.path.join("productos", f"{slug}.html"), "w",
                  encoding="utf-8") as fh:
            fh.write(pagina_producto(key, prods[key], slug, otros, semana))


# ---------------- Advanced Charts (TradingView) ----------------
# La librería no vive en este repo (licencia): el workflow la clona del repo
# privado al publicar y la deja en /charting_library/. Aquí va lo propio:
#   carestia-tv.js         el datafeed (API de datafeed de la librería) sobre
#                          los archivos de datos/, más el guardado en el
#                          navegador y los formatos de precio y fecha
#   carestia-tv.css        el tema del sitio para el iframe de la librería
#   prueba-graficos.html   página oculta de prueba (noindex, fuera del menú y
#                          del sitemap); si la librería no está o no inicia en
#                          8 segundos, dibuja con Lightweight Charts
# Símbolos: los 4 índices y los productos del catálogo, cada uno en pesos de
# hoy, a precio de la época ("{slug}-epoca") y en UF ("{slug}-uf", solo si el
# build tiene datos/uf.json); el ticker es el slug (el código del índice o el
# de la ficha del producto). Semanales (1W) y las temporalidades que el
# datafeed arma juntando semanas (2W, 1M, 3M, 6M y 12M); en CLP sin decimales
# (la UF con decimales) y en America/Santiago.
TV_JS = "carestia-tv.js"
TV_CSS = "carestia-tv.css"
TV_PRUEBA = "prueba-graficos.html"
FEED_JS = r"""/* Carestía: datafeed de Advanced Charts sobre los archivos de datos/.
   Lo genera build_site.py; lo usan las páginas con gráficos. */
(function (raiz) {
  'use strict';

  // la temporalidad por defecto: las semanas, como vienen en datos/
  const RESOLUCION = '1W';
  // las que se pueden elegir: el datafeed arma las de más de una semana
  // juntando semanas (ver agrupar)
  const RESOLUCIONES = ['1W', '2W', '1M', '3M', '6M', '12M'];
  const ZONA = 'America/Santiago';
  const FUENTE = 'Carestía';
  const DIA = 864e5;
  const SEMANA = 7 * DIA;
  const UNIDAD = { kg: 'kilo', un: 'unidad', l: 'litro' };
  const TIPO = { indice: 'index', producto: 'commodity' };
  // cada serie en tres unidades: pesos de hoy (el ticker solo), precio de la
  // época y UF. Los nombres llevan la unidad: el largo (pantallas anchas y
  // búsqueda) y el corto (la leyenda en el celular)
  const UNIDADES = ['real', 'epoca', 'uf'];
  const SUFIJO = { real: '', epoca: '-epoca', uf: '-uf' };
  const EN_LARGO = { real: ', en pesos de hoy', epoca: ', precio de la época', uf: ', en UF' };
  const EN_CORTO = { real: '', epoca: ', precio de la época', uf: ', en UF' };

  const sinTildes = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

  const conPuntos = s => s.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  // precios en pesos, sin decimales y con punto de miles: 26467 -> "26.467"
  function miles(x) {
    const r = Math.round(x);
    return (r < 0 ? '-' : '') + conPuntos(String(Math.abs(r)));
  }
  // UF con coma decimal: 2 decimales desde 1 UF y 4 bajo 1 UF ("2 sobre 1
  // UF y 4 bajo 1 UF"). Los decimales salen de la cifra ya redondeada:
  // 0,99996 es 1,00
  function numUF(x) {
    const a = Math.abs(x);
    let t = a.toFixed(a >= 1 ? 2 : 4);
    if (a < 1 && Number(t) >= 1) t = a.toFixed(2);
    const [e, d] = t.split('.');
    return (x < 0 && Number(t) ? '-' : '') + conPuntos(e) + ',' + d;
  }
  const textoUF = x => numUF(x) + ' UF';
  // fechas dd-mm-aaaa; las barras semanales llegan a las 00:00 UTC del lunes
  function fecha(d) {
    const dos = n => String(n).padStart(2, '0');
    return dos(d.getUTCDate()) + '-' + dos(d.getUTCMonth() + 1) + '-' + d.getUTCFullYear();
  }

  // series compactas de datos/ (t0, el lunes de la primera semana, y un valor
  // por semana consecutiva, null donde no hubo dato) a barras de la librería:
  // time en milisegundos UTC del lunes, como pide la API para barras semanales
  const tiempos = t0 => {
    const base = Date.parse(t0 + 'T00:00:00Z');
    return i => base + i * SEMANA;
  };
  const mesDe = ms => new Date(ms).toISOString().slice(0, 7);

  // índice en pesos de hoy: las velas de indices.py (apertura = cierre
  // anterior, mecha = mínimo y máximo entre puntos de venta, cierre = promedio)
  function barrasIndice(s) {
    const t = tiempos(s.t0), out = [];
    s.real.forEach((c, i) => {
      if (c == null) return;
      const v = s.velas && s.velas[i];
      if (v) out.push({ time: t(i), open: v[0], high: v[1], low: v[2], close: v[3] });
      else {
        const o = out.length ? out[out.length - 1].close : c;
        out.push({ time: t(i), open: o, high: Math.max(o, c), low: Math.min(o, c), close: c });
      }
    });
    return out;
  }
  // índice a precio de la época: la misma vela en pesos de cada semana. El
  // cierre es el nominal publicado y la apertura el cierre anterior; la mecha
  // se lleva a pesos de esa semana con el mismo factor del IPC que usó
  // indices.py (nominal / real de la semana)
  function barrasIndiceEpoca(s) {
    const t = tiempos(s.t0), out = [];
    s.nominal.forEach((c, i) => {
      if (c == null) return;
      const o = out.length ? out[out.length - 1].close : c;
      const v = s.velas && s.velas[i], r = s.real[i];
      const k = v && r ? c / r : null;
      out.push({ time: t(i), open: o, close: c,
        high: Math.max(o, c, k ? Math.round(v[1] * k) : c),
        low: Math.min(o, c, k ? Math.round(v[2] * k) : c) });
    });
    return out;
  }
  // producto: velas como las de los índices: el cuerpo va del cierre de la semana
  // anterior con dato al de esta; la mecha, del precio más bajo al más alto
  // que ODEPA encontró entre los locales (min y max de indices.py). Sin
  // rango esa semana, la vela va sin mecha
  function barrasProducto(p, factor) {
    const t = tiempos(p.t0), out = [];
    const rango = (a, i, f) => a && a[i] != null ? Math.round(a[i] * f) : null;
    p.v.forEach((x, i) => {
      if (x == null) return;
      const ms = t(i);
      let f = 1;
      if (factor) {
        f = factor.get(mesDe(ms));
        if (f == null) return;   // mes sin factor: esa semana no tiene precio de la época
      }
      const c = factor ? Math.round(x * f) : x;
      const o = out.length ? out[out.length - 1].close : c;
      const lo = rango(p.min, i, f), hi = rango(p.max, i, f);
      out.push({ time: ms, open: o, high: Math.max(o, c, hi == null ? c : hi),
        low: Math.min(o, c, lo == null ? c : lo), close: c });
    });
    return out;
  }
  // factor de pesos de hoy a pesos de cada mes: indices.py deflacta con el IPC
  // del mes (el mismo para índices y productos), así que el cociente entre el
  // nominal y el real publicados de los índices lo devuelve. Se suman los
  // cuatro índices de cada mes para que el redondeo a pesos no pese
  function factorMensual(series) {
    const nom = new Map(), real = new Map();
    series.forEach(s => {
      const t = tiempos(s.t0);
      s.real.forEach((r, i) => {
        const n = s.nominal[i];
        if (r == null || n == null) return;
        const m = mesDe(t(i));
        nom.set(m, (nom.get(m) || 0) + n);
        real.set(m, (real.get(m) || 0) + r);
      });
    });
    const out = new Map();
    real.forEach((r, m) => { if (r) out.set(m, nom.get(m) / r); });
    return out;
  }
  // la UF de cada lunes, de datos/uf.json (t0 y un valor por semana)
  function ufSemanal(j) {
    const t = tiempos(j.t0), out = new Map();
    (j.v || []).forEach((x, i) => { if (x > 0) out.set(t(i), x); });
    return out;
  }
  // en UF: cada vela a precio de la época dividida por la UF del lunes de su
  // semana, el día en que empieza. La apertura es el cierre anterior en UF,
  // como en pesos; sin UF ese lunes, la semana queda sin barra
  function enUF(barras, uf) {
    const out = [];
    barras.forEach(b => {
      const u = uf.get(b.time);
      if (!u) return;
      const c = b.close / u;
      const o = out.length ? out[out.length - 1].close : c;
      out.push({ time: b.time, open: o, high: Math.max(o, c, b.high / u),
        low: Math.min(o, c, b.low / u), close: c });
    });
    return out;
  }

  // ---------- temporalidades ----------
  // 1S son las semanas de datos/. 2S, 1M, 3M, 6M y 12M juntan semanas: la
  // apertura es la de la primera semana del período, el cierre el de la
  // última y el máximo y el mínimo, los extremos del período. Cada semana va
  // al período del lunes en que empieza. Los períodos se anclan como los
  // cuenta la librería (Resolution, "Bar alignment"): la cuenta parte de
  // nuevo cada año; los meses, desde enero (3M en enero, abril, julio y
  // octubre; 6M en enero y julio; 12M el 1 de enero) y las semanas, desde el
  // primer lunes del año (la primera semana completa), así que el último
  // período de 2S de un año de 53 lunes trae una sola semana. La barra lleva
  // la fecha en que empieza su período, a las 00:00 UTC
  function temporalidad(res) {
    const m = /^(\d*)([WM])$/.exec(String(res || ''));
    if (!m) return null;
    const n = Number(m[1] || 1), nombre = n + m[2];
    return RESOLUCIONES.indexOf(nombre) === -1 ? null : { n, mes: m[2] === 'M', nombre };
  }
  const primerLunes = y => {
    const e = Date.UTC(y, 0, 1);
    return e + ((8 - new Date(e).getUTCDay()) % 7) * DIA;
  };
  function inicioPeriodo(ms, p) {
    const d = new Date(ms), y = d.getUTCFullYear();
    if (p.mes) {
      const m = d.getUTCMonth();
      return Date.UTC(y, m - m % p.n, 1);
    }
    // los días antes del primer lunes van al último período del año anterior
    const a = ms >= primerLunes(y) ? primerLunes(y) : primerLunes(y - 1);
    return a + Math.floor((ms - a) / (p.n * SEMANA)) * p.n * SEMANA;
  }
  function agrupar(semanas, p) {
    const out = [];
    semanas.forEach(b => {
      const t = inicioPeriodo(b.time, p), u = out[out.length - 1];
      if (u && u.time === t) {
        u.high = Math.max(u.high, b.high);
        u.low = Math.min(u.low, b.low);
        u.close = b.close;
      } else out.push({ time: t, open: b.open, high: b.high, low: b.low, close: b.close });
    });
    return out;
  }

  // opciones: { base: '/datos/', ver, indices: [{ codigo, nombre }], pedir,
  //   productos: [{ slug, nombre, unidad }], precargados: { ruta: json }, uf }
  // 'pedir(ruta)' devuelve una promesa con el JSON de datos/{ruta}; por
  // defecto, fetch con la versión del build en la URL. 'productos' son los
  // que la página ya conoce (la ficha, el suyo): se resuelven sin esperar el
  // catálogo. 'precargados' son archivos de datos/ que la página trae inline.
  // 'uf': el build trae datos/uf.json; sin él no hay símbolos en UF
  function crearDatafeed(opciones) {
    const base = opciones.base || '/datos/';
    const ver = opciones.ver ? '?v=' + encodeURIComponent(opciones.ver) : '';
    const precargados = opciones.precargados || {};
    const traer = opciones.pedir || (ruta => fetch(base + ruta + ver).then(r => {
      if (!r.ok) throw new Error(ruta + ': ' + r.status);
      return r.json();
    }));
    const pedir = ruta => ruta in precargados ? Promise.resolve(precargados[ruta]) : traer(ruta);
    const memo = new Map();
    const una = (clave, f) => {
      if (!memo.has(clave)) {
        const p = f();
        p.catch(() => memo.delete(clave));   // un pedido fallido se puede repetir
        memo.set(clave, p);
      }
      return memo.get(clave);
    };
    const indices = opciones.indices || [];
    const unidades = opciones.uf ? UNIDADES : UNIDADES.filter(u => u !== 'uf');

    // símbolos: cada serie en pesos de hoy, a precio de la época y en UF. El
    // ticker es el slug (el código del índice o el de la ficha del producto)
    // más el sufijo de la unidad, sin paréntesis ni dos puntos. Cada uno con
    // un nombre corto (la leyenda en el celular) y uno largo (la leyenda en
    // pantallas anchas y la búsqueda)
    const simbolos = new Map();
    function agregar(s) {
      unidades.forEach(unidad => {
        const ticker = s.ticker + SUFIJO[unidad];
        if (simbolos.has(ticker)) return;   // nunca dos símbolos con un ticker
        const desc = s.nombre + EN_LARGO[unidad];
        const corto = s.corto + EN_CORTO[unidad];
        simbolos.set(ticker, Object.assign({}, s, { ticker, base: s.ticker, unidad, desc, corto,
          etiqueta: s.corto, buscar: sinTildes(ticker + ' ' + desc + ' ' + s.nombre) }));
      });
    }
    const agregarProducto = p => agregar({ ticker: p.slug, clase: 'producto', corto: p.nombre,
      nombre: p.nombre + ' por ' + (UNIDAD[p.unidad] || p.unidad), grupo: p.grupo,
      ruta: 'productos/' + p.slug + '.json' });
    indices.forEach(d => agregar({ ticker: d.codigo, clase: 'indice', nombre: d.nombre,
      corto: d.nombre.replace(/^Índice /, ''), ruta: 'indices/' + d.codigo + '.json' }));
    (opciones.productos || []).forEach(agregarProducto);
    const listo = pedir('catalogo.json').then(cat => {
      (cat.productos || []).forEach(agregarProducto);
    }).catch(() => {});   // sin catálogo quedan los índices

    const simbolo = nombre => {
      // por si llega con prefijo de fuente ("Carestía:asado") o en mayúsculas;
      // "-nominal" era el sufijo del precio de la época
      const t = String(nombre || '').split(':').pop().trim().toLowerCase()
        .replace(/-nominal$/, SUFIJO.epoca);
      // los que la página ya conoce no esperan el catálogo
      return simbolos.has(t) ? Promise.resolve(simbolos.get(t)) :
        listo.then(() => simbolos.get(t) || null);
    };
    const factor = () => una('factor', () =>
      Promise.all(indices.map(d => pedir('indices/' + d.codigo + '.json')))
        .then(js => factorMensual(js.map(j => j.serie))));
    const uf = () => una('uf', () => pedir('uf.json').then(ufSemanal));
    // las semanas de un símbolo, completas y en orden
    function semanas(s) {
      if (s.unidad === 'uf') {
        return Promise.all([barras(s.base + SUFIJO.epoca), uf()]).then(([b, u]) => enUF(b || [], u));
      }
      return pedir(s.ruta).then(j => {
        if (s.clase === 'indice') return s.unidad === 'epoca' ? barrasIndiceEpoca(j.serie) : barrasIndice(j.serie);
        return s.unidad === 'epoca' ? factor().then(f => barrasProducto(j, f)) : barrasProducto(j, null);
      });
    }
    // las barras de un símbolo en una temporalidad (1W si no se dice),
    // completas y en orden; null si el símbolo o la temporalidad no existen.
    // Las semanas ya llegadas quedan también a mano, sin promesa (ver rango)
    const llegadas = new Map();
    function barras(nombre, res) {
      const p = temporalidad(res || RESOLUCION);
      return simbolo(nombre).then(s => {
        if (!s || !p) return null;
        const sem = una('b:' + s.ticker, () => semanas(s).then(b => { llegadas.set(s.ticker, b); return b; }));
        if (p.nombre === RESOLUCION) return sem;
        return una('b:' + s.ticker + ':' + p.nombre, () => sem.then(b => agrupar(b, p)));
      });
    }
    // toda la historia de un símbolo en una temporalidad, en segundos, de
    // inmediato: del período de la primera semana al de la última. null si
    // sus semanas aún no llegan
    function rango(nombre, res) {
      const t = String(nombre || '').split(':').pop().trim().toLowerCase()
        .replace(/-nominal$/, SUFIJO.epoca);
      const b = llegadas.get(t), p = temporalidad(res || RESOLUCION);
      if (!b || !b.length || !p) return null;
      return { from: inicioPeriodo(b[0].time, p) / 1000, to: inicioPeriodo(b[b.length - 1].time, p) / 1000 };
    }

    function info(s) {
      const enUF = s.unidad === 'uf';
      return {
        // el nombre que la librería muestra en Comparar (leyenda y eje): el
        // del producto o del índice, sin la unidad (Comparar ya la dice). Los
        // pedidos y c.symbol() usan el ticker, con la unidad
        name: s.etiqueta,
        ticker: s.ticker,
        description: s.corto,
        long_description: s.desc,
        type: TIPO[s.clase],
        session: '24x7',
        timezone: ZONA,
        exchange: FUENTE,
        listed_exchange: FUENTE,
        format: 'price',
        minmov: 1,
        // pesos sin decimales; la UF con hasta 4 (ver numUF)
        pricescale: enUF ? 10000 : 1,
        has_intraday: false,
        has_daily: false,
        // las semanas vienen hechas y el resto lo arma el datafeed
        has_weekly_and_monthly: true,
        weekly_multipliers: ['1', '2'],
        monthly_multipliers: ['1', '3', '6', '12'],
        supported_resolutions: RESOLUCIONES,
        // índices y productos traen velas (los productos, con el rango de
        // ODEPA cuando indices.json lo trae)
        visible_plots_set: 'ohlc',
        data_status: 'endofday',
        currency_code: enUF ? 'UF' : 'CLP',
        volume_precision: 0,
      };
    }

    // la API pide todos los callbacks en otra macrotarea
    const despues = f => setTimeout(f, 0);
    return {
      // la configuración no depende del catálogo: no lo espera
      onReady(cb) {
        despues(() => cb({
          supported_resolutions: RESOLUCIONES,
          exchanges: [],
          symbols_types: [
            { name: 'Todos', value: '' },
            { name: 'Índices', value: TIPO.indice },
            { name: 'Productos', value: TIPO.producto },
          ],
          supports_marks: false,
          supports_timescale_marks: false,
          supports_time: false,
        }));
      },
      // búsqueda solo entre los símbolos de Carestía: todas las palabras
      // escritas, sin tildes ni mayúsculas, en el ticker o el nombre
      searchSymbols(texto, _fuente, tipo, cb) {
        listo.then(() => {
          const palabras = sinTildes(texto || '').split(/\s+/).filter(Boolean);
          const out = [];
          simbolos.forEach(s => {
            if (tipo && TIPO[s.clase] !== tipo) return;
            if (!palabras.every(w => s.buscar.indexOf(w) !== -1)) return;
            out.push({ symbol: s.ticker, ticker: s.ticker, description: s.desc,
              exchange: FUENTE, type: TIPO[s.clase] });
          });
          despues(() => cb(out));
        });
      },
      resolveSymbol(nombre, alResolver, alFallar) {
        simbolo(nombre).then(s => despues(() => {
          if (s) alResolver(info(s));
          else alFallar('unknown_symbol');
        }));
      },
      // historia en la temporalidad pedida; countBack manda sobre from (la
      // API lo pide así): si en [from, to) hay menos barras, se devuelven las
      // anteriores a to
      getBars(symbolInfo, resolucion, periodo, alResultado, alFallar) {
        if (!temporalidad(resolucion)) {
          despues(() => alResultado([], { noData: true }));
          return;
        }
        barras(symbolInfo.ticker || symbolInfo.name, resolucion).then(todas => {
          if (!todas) { despues(() => alFallar('unknown_symbol')); return; }
          const desde = periodo.from * 1000, hasta = periodo.to * 1000;
          let fin = 0;
          while (fin < todas.length && todas[fin].time < hasta) fin++;
          let ini = fin;
          while (ini > 0 && todas[ini - 1].time >= desde) ini--;
          if (periodo.countBack && fin - ini < periodo.countBack) {
            ini = Math.max(0, fin - periodo.countBack);
          }
          // sin countBack y sin barras en el tramo: las anteriores (la API
          // pide al menos dos), para que el pedido siguiente siga hacia atrás;
          // noData solo cuando no queda historia
          if (ini === fin && fin > 0) ini = Math.max(0, fin - 2);
          // copias: la librería puede modificar las barras que recibe
          const out = todas.slice(ini, fin).map(b => Object.assign({}, b));
          despues(() => alResultado(out, { noData: !out.length }));
        }, e => despues(() => alFallar(String(e && e.message || e))));
      },
      // datos semanales publicados los viernes: sin tiempo real
      subscribeBars() {},
      unsubscribeBars() {},
      // para el respaldo con Lightweight Charts, el rango al cambiar de
      // temporalidad y las pruebas
      barras,
      rango,
      simbolo,
      lista: () => listo.then(() => [...simbolos.values()].map(s =>
        ({ ticker: s.ticker, descripcion: s.desc, corto: s.corto, clase: s.clase,
          unidad: s.unidad }))),
      info: nombre => simbolo(nombre).then(s => s && info(s)),
    };
  }

  // ---------- guardado en el navegador ----------
  // save_load_adapter sobre localStorage: los gráficos guardados (con sus
  // dibujos) y las plantillas quedan en el navegador de cada persona; nada
  // va a servidores de TradingView ni de Carestía
  function almacenLocal(prefijo) {
    const leer = (k, def) => {
      try { const v = localStorage.getItem(prefijo + k); return v ? JSON.parse(v) : def; }
      catch (e) { return def; }
    };
    const escribir = (k, v) => {
      try { localStorage.setItem(prefijo + k, JSON.stringify(v)); return Promise.resolve(); }
      catch (e) { return Promise.reject(new Error('No hay espacio en el navegador')); }
    };
    const ya = v => Promise.resolve(v);
    const graficos = () => leer('graficos', []);
    // reemplaza (o quita, sin 'agregar') la entrada con ese nombre
    const porNombre = (k, nombre, agregar) => {
      const lista = leer(k, []).filter(x => x.name !== nombre);
      if (agregar) lista.push(agregar);
      return escribir(k, lista);
    };
    const contenido = (k, nombre) => {
      const x = leer(k, []).find(t => t.name === nombre);
      return x ? ya(x.content) : Promise.reject(new Error('No existe'));
    };
    return {
      getAllCharts: () => ya(graficos().map(g => ({ id: g.id, name: g.name,
        symbol: g.symbol, resolution: g.resolution, timestamp: g.timestamp }))),
      removeChart: id => escribir('graficos', graficos().filter(g => g.id !== id)),
      saveChart: d => {
        const lista = graficos();
        const id = d.id != null ? d.id : 'g' + Date.now().toString(36);
        const g = { id, name: d.name, symbol: d.symbol, resolution: d.resolution,
          content: d.content, timestamp: Math.floor(Date.now() / 1000) };
        const i = lista.findIndex(x => x.id === id);
        if (i === -1) lista.push(g); else lista[i] = g;
        return escribir('graficos', lista).then(() => id);
      },
      getChartContent: id => {
        const g = graficos().find(x => x.id === id);
        return g ? ya(g.content) : Promise.reject(new Error('No existe'));
      },
      getAllStudyTemplates: () => ya(leer('indicadores', []).map(t => ({ name: t.name }))),
      removeStudyTemplate: t => porNombre('indicadores', t.name),
      saveStudyTemplate: t => porNombre('indicadores', t.name, { name: t.name, content: t.content }),
      getStudyTemplateContent: t => contenido('indicadores', t.name),
      getDrawingTemplates: herramienta => ya(Object.keys(leer('dibujos', {})[herramienta] || {})),
      loadDrawingTemplate: (herramienta, nombre) => {
        const x = (leer('dibujos', {})[herramienta] || {})[nombre];
        return x != null ? ya(x) : Promise.reject(new Error('No existe'));
      },
      removeDrawingTemplate: (herramienta, nombre) => {
        const todo = leer('dibujos', {});
        if (todo[herramienta]) delete todo[herramienta][nombre];
        return escribir('dibujos', todo);
      },
      saveDrawingTemplate: (herramienta, nombre, texto) => {
        const todo = leer('dibujos', {});
        (todo[herramienta] = todo[herramienta] || {})[nombre] = texto;
        return escribir('dibujos', todo);
      },
      getAllChartTemplates: () => ya(leer('temas', []).map(t => t.name)),
      getChartTemplateContent: nombre => contenido('temas', nombre).then(content => ({ content })),
      saveChartTemplate: (nombre, tema) => porNombre('temas', nombre, { name: nombre, content: tema }),
      removeChartTemplate: nombre => porNombre('temas', nombre),
      // solo se usan con saveload_separate_drawings_storage (apagado): los
      // dibujos viajan dentro de cada gráfico guardado
      saveLineToolsAndGroups: () => ya(),
      loadLineToolsAndGroups: () => ya(null),
    };
  }

  // ---------- el widget ----------
  // formatos: precios en pesos con punto de miles, en UF con coma decimal
  // (sin la sigla: la escala ya dice UF) y fechas dd-mm-aaaa
  const esUF = info => !!info && (info.currency_code === 'UF' || /-uf$/.test(info.ticker || info.name || ''));
  function formateadores() {
    const formato = f => ({ format: (x, o) => {
      const signo = (o === true || (o && o.signPositive)) && x > 0 ? '+' : '';
      return signo + f(x);
    } });
    const pesos = formato(miles), enUF = formato(numUF);
    return {
      priceFormatterFactory: info => esUF(info) ? enUF : pesos,
      dateFormatter: {
        format: fecha,
        formatLocal: d => fecha(new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))),
        // lo que se escribe en "Ir a": dd-mm-aaaa a aaaa-mm-dd
        parse: t => {
          const m = /^\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$/.exec(t);
          return m ? m[3] + '-' + m[2].padStart(2, '0') + '-' + m[1].padStart(2, '0') : t;
        },
      },
    };
  }

  // colores de la librería con los tokens del sitio: velas verde y rojo; la
  // línea en brasa para los índices oficiales y en hueso para los productos.
  // Todos los gráficos parten en línea; las velas quedan a un clic
  function overrides(tok) {
    const verde = tok('verde'), rojo = tok('rojo');
    const o = {
      'paneProperties.backgroundType': 'solid',
      'paneProperties.background': tok('bg'),
      'paneProperties.vertGridProperties.color': tok('grid'),
      'paneProperties.horzGridProperties.color': tok('grid'),
      'paneProperties.crossHairProperties.color': tok('dim'),
      'paneProperties.separatorColor': tok('line'),
      'scalesProperties.textColor': tok('ash'),
      'scalesProperties.lineColor': tok('line'),
      'mainSeriesProperties.style': 2,
      // v32 dibuja la línea con degradé si no se pide un color sólido
      'mainSeriesProperties.lineStyle.colorType': 'solid',
      'mainSeriesProperties.lineStyle.color': tok('ember'),
      'mainSeriesProperties.lineStyle.linewidth': 2,
    };
    ['candleStyle', 'hollowCandleStyle', 'haStyle'].forEach(e => {
      o['mainSeriesProperties.' + e + '.upColor'] = verde;
      o['mainSeriesProperties.' + e + '.downColor'] = rojo;
      o['mainSeriesProperties.' + e + '.borderUpColor'] = verde;
      o['mainSeriesProperties.' + e + '.borderDownColor'] = rojo;
      o['mainSeriesProperties.' + e + '.wickUpColor'] = verde;
      o['mainSeriesProperties.' + e + '.wickDownColor'] = rojo;
    });
    o['mainSeriesProperties.barStyle.upColor'] = verde;
    o['mainSeriesProperties.barStyle.downColor'] = rojo;
    return o;
  }
  const colorLinea = (tok, indice) => {
    const c = tok(indice ? 'ember' : 'bone');
    return { 'mainSeriesProperties.lineStyle.colorType': 'solid', 'mainSeriesProperties.lineStyle.color': c };
  };

  // pantallas de celular: hasta 640px, como el menú del sitio
  const MOVIL = '(max-width: 640px)';
  const esMovil = () => typeof matchMedia === 'function' && matchMedia(MOVIL).matches;
  // en el celular la barra de arriba deja solo las temporalidades, comparar,
  // indicadores, tipo de gráfico y pantalla completa (más el dibujo, en su
  // propia barra): sin lo que no cabe
  const FAVORITAS_MOVIL = ['1W', '1M', '12M'];
  const SOLO_ESCRITORIO = ['header_symbol_search', 'header_settings',
    'header_undo_redo', 'header_quick_search', 'header_screenshot', 'header_saveload'];
  // páginas del sitio: el símbolo lo eligen las pestañas y los selectores de
  // la página (sin buscador de la librería ni guardar y cargar gráficos).
  // Gestos: la rueda acerca y mueve el gráfico; en táctil el deslizamiento
  // vertical mueve la página, hacia los lados mueve el gráfico y dos dedos
  // acercan
  const FUERA_DEL_SITIO = ['header_symbol_search', 'symbol_search_hot_key', 'header_saveload',
    'vert_touch_drag_scroll'];

  // la configuración común de todas las páginas.
  // o: { contenedor, libreria, simbolo, datafeed, tok, css, movil, sitio,
  //      comparar: [{ symbol, title }] }
  function opcionesWidget(o) {
    const movil = o.movil != null ? o.movil : esMovil();
    const fuera = new Set([...(movil ? SOLO_ESCRITORIO : []), ...(o.sitio ? FUERA_DEL_SITIO : [])]);
    const ov = overrides(o.tok);
    // la leyenda: en el celular el nombre corto, sin intervalo ni fuente, para
    // que no se corte; en pantallas anchas el nombre largo
    ov['mainSeriesProperties.statusViewStyle.symbolTextSource'] = movil ? 'description' : 'long-description';
    ov['mainSeriesProperties.statusViewStyle.showInterval'] = !movil;
    ov['mainSeriesProperties.statusViewStyle.showExchange'] = !movil;
    const opciones = {
      container: o.contenedor,
      library_path: o.libreria,
      datafeed: o.datafeed,
      symbol: o.simbolo,
      interval: RESOLUCION,
      timezone: ZONA,
      locale: 'es',
      theme: 'dark',
      autosize: true,
      custom_css_url: o.css,
      custom_font_family: "'IBM Plex Sans', system-ui, sans-serif",
      loading_screen: { backgroundColor: o.tok('bg'), foregroundColor: o.tok('ember') },
      toolbar_bg: o.tok('panel'),
      overrides: ov,
      custom_formatters: formateadores(),
      numeric_formatting: { decimal_sign: ',', grouping_separator: '.' },
      // guardar y cargar gráficos, plantillas y dibujos: en el navegador
      save_load_adapter: almacenLocal('carestia-tv:'),
      // a un clic en la barra: las temporalidades (en el celular 1S, 1M y 12M;
      // las seis no dejan lugar a la línea y las velas), la línea y las velas
      favorites: { intervals: movil ? FAVORITAS_MOVIL : RESOLUCIONES, chartTypes: ['Line', 'Candles'] },
      // toda la historia cabe aun a 390px de ancho
      time_scale: { min_bar_spacing: 0.1 },
      // plazos de la barra inferior, todos semanales (los de fábrica piden
      // resoluciones de minutos o días, que estos datos no tienen)
      time_frames: [
        { text: '6m', resolution: RESOLUCION, description: '6 meses', title: '6M' },
        { text: '1y', resolution: RESOLUCION, description: '1 año', title: '1A' },
        { text: '3y', resolution: RESOLUCION, description: '3 años', title: '3A' },
        { text: '5y', resolution: RESOLUCION, description: '5 años', title: '5A' },
        { text: '10y', resolution: RESOLUCION, description: '10 años', title: '10A' },
        { text: '20y', resolution: RESOLUCION, description: 'Toda la serie', title: 'Todo' },
      ],
      // las funciones de fábrica quedan activas (dibujo, indicadores, comparar,
      // tipos de gráfico, captura para descargar o copiar), más las plantillas
      // de indicadores y sin el ancho mínimo del gráfico (a 390px desbordaría
      // la página), salvo lo que no va en el celular o en las páginas del
      // sitio. No se configura nada que guarde fuera del navegador: ni
      // charts_storage_url ni snapshot_url
      enabled_features: ['study_templates', 'no_min_chart_width'],
      disabled_features: [...fuera],
    };
    // la página de prueba guarda sola en el navegador y abre lo último guardado
    if (!o.sitio) Object.assign(opciones, { auto_save_delay: 5, load_last_chart: true });
    // símbolos a mano en Comparar de la librería (la ficha: sus otras unidades)
    if (o.comparar) opciones.compare_symbols = o.comparar;
    return opciones;
  }

  // con el gráfico listo: estilo según el símbolo (la línea en brasa para los
  // índices y en hueso para los productos) y guardado automático en el
  // navegador
  function alistarWidget(widget, feed, tok) {
    estiloPorSimbolo(widget, feed, tok);
    widget.subscribe('onAutoSaveNeeded', () => {
      Promise.resolve(widget.saveChartToServer({ defaultChartName: 'Mi gráfico' }))
        .catch(() => {});
    });
  }
  function estiloPorSimbolo(widget, feed, tok) {
    const chart = widget.activeChart();
    // el color de la línea por clase; el tipo de gráfico no se toca: índices
    // y productos parten en la línea de 'overrides' (o lo guardado) y queda
    // el que elija la persona
    const estilo = () => feed.simbolo(chart.symbol()).then(s => {
      if (!s) return;
      widget.applyOverrides(colorLinea(tok, s.clase === 'indice'));
    });
    estilo();
    chart.onSymbolChanged().subscribe(null, estilo);
  }
  // la librería quedó lista (chartReady desde v32; onChartReady antes)
  const listoWidget = w => w.chartReady ? w.chartReady() : new Promise(r => w.onChartReady(r));

  // toda la historia de la serie a la vista, en la temporalidad del gráfico.
  // Con la caja oculta (display:none, otro modo a la vista) la librería mide
  // cero y el rango no queda: se aplica cuando la caja vuelve a tener ancho
  const esperandoAncho = new WeakSet();
  function verTodo(widget, feed, caja, res) {
    if (caja && !caja.clientWidth && typeof ResizeObserver === 'function') {
      if (esperandoAncho.has(widget)) return Promise.resolve();
      esperandoAncho.add(widget);
      const ro = new ResizeObserver(() => {
        if (!caja.clientWidth) return;
        ro.disconnect();
        esperandoAncho.delete(widget);
        // la librería toma el ancho nuevo en su propio cuadro
        setTimeout(() => verTodo(widget, feed, caja, res), 100);
      });
      ro.observe(caja);
      return Promise.resolve();
    }
    const chart = widget.activeChart();
    // al cambiar de símbolo el aviso llega antes que las barras (sin datos,
    // setVisibleRange falla): primero se espera a que el gráfico los tenga
    const datos = typeof chart.dataReady === 'function' ? Promise.resolve(chart.dataReady()) : Promise.resolve();
    // la temporalidad: la que llega con el aviso de cambio o la del gráfico
    const temp = () => res || (typeof chart.resolution === 'function' ? chart.resolution() : RESOLUCION);
    return datos.then(() => feed.barras(chart.symbol(), temp())).then(b => {
      if (!b || !b.length) return;
      const rango = { from: b[0].time / 1000, to: b[b.length - 1].time / 1000 };
      // la librería no garantiza que setVisibleRange termine: con plazo. El
      // margen de la derecha (unas diez barras) solo en semanas: en 12M
      // serían diez años vacíos
      const p = temporalidad(temp());
      const op = { applyDefaultRightMargin: !p || p.nombre === RESOLUCION, rejectByTimeout: 3000 };
      return Promise.resolve(chart.setVisibleRange(rango, op)).then(() => {
        // la historia más antigua llega mientras se aplica el rango y, con
        // semanas sin dato, puede quedar corto por la izquierda: una vez
        // más, ya con todo cargado
        const v = typeof chart.getVisibleRange === 'function' ? chart.getVisibleRange() : null;
        if (v && v.from > rango.from + 86400) return chart.setVisibleRange(rango, op);
      });
    }).catch(() => {});
  }

  // la librería se pide una sola vez por página
  let libreria = null;
  function cargarLibreria(ruta) {
    if (!libreria) {
      libreria = new Promise((ok, mal) => {
        const lista = () => typeof window.TradingView === 'object' && window.TradingView &&
          typeof window.TradingView.widget === 'function';
        if (lista()) return ok();
        const s = document.createElement('script');
        s.src = ruta + 'charting_library.standalone.js';
        s.onload = () => (lista() ? ok() : mal('falta'));
        s.onerror = () => mal('falta');
        document.head.appendChild(s);
      });
    }
    return libreria;
  }

  // monta Advanced Charts con la configuración común. Resuelve con el widget
  // listo, con toda la historia a la vista (también en cada cambio de
  // símbolo o de temporalidad); rechaza con 'falta' (la librería no está), 'tarde' (no inició
  // en 'espera' ms) o 'error', y entonces la página dibuja con Lightweight.
  // o: lo de opcionesWidget, más { espera = 8000, estilo = true (velas o
  // línea y color según el símbolo; Comparar maneja los suyos) }
  const ESPERA = 8000;
  function montar(o) {
    return new Promise((ok, mal) => {
      let widget = null, hecho = false;
      const reloj = setTimeout(() => fin('tarde'), o.espera || ESPERA);
      function fin(motivo) {
        if (hecho) return;
        hecho = true;
        clearTimeout(reloj);
        if (!motivo) { ok(widget); return; }
        if (widget) { try { widget.remove(); } catch (e) {} }
        mal(motivo);
      }
      cargarLibreria(o.libreria).then(() => {
        if (hecho) return;
        try { widget = new window.TradingView.widget(opcionesWidget(o)); }
        catch (e) { fin('error'); return; }
        listoWidget(widget).then(() => {
          if (hecho) return;
          if (o.estilo !== false) estiloPorSimbolo(widget, o.datafeed, o.tok);
          const caja = typeof o.contenedor === 'string' ? document.getElementById(o.contenedor) : o.contenedor;
          const c = widget.activeChart();
          c.onSymbolChanged().subscribe(null, () => verTodo(widget, o.datafeed, caja));
          // al cambiar de temporalidad la librería deja el ancho de las barras
          // y la historia quedaba apretada a un lado: el rango completo va en
          // el mismo aviso, como pide su documentación (timeframe). Si el
          // cambio ya trae su rango (los plazos de la barra de abajo), queda
          if (typeof c.onIntervalChanged === 'function') {
            c.onIntervalChanged().subscribe(null, (res, cambio) => {
              const r = o.datafeed.rango && o.datafeed.rango(c.symbol(), res);
              if (r && cambio && !cambio.timeframe) {
                cambio.timeframe = { type: 'time-range', from: r.from, to: r.to };
              }
            });
          }
          // el rango no frena el arranque: el widget ya inició
          verTodo(widget, o.datafeed, caja);
          fin();
        }, () => fin('error'));
      }, motivo => fin(motivo || 'falta'));
    });
  }

  // captura del gráfico del lado del cliente (nunca la del servidor de
  // TradingView): un canvas para componer la imagen compartible
  function capturaCliente(widget, tok) {
    return widget.takeClientScreenshot({ backgroundColor: tok('bg'), borderColor: tok('line'),
      font: "'IBM Plex Sans', system-ui, sans-serif", fontSize: 12, legendMode: 'horizontal',
      hideResolution: true });
  }

  const api = { crearDatafeed, miles, numUF, textoUF, fecha, almacenLocal, formateadores,
    overrides, opcionesWidget, alistarWidget, listoWidget, montar, verTodo, cargarLibreria,
    capturaCliente, colorLinea, temporalidad, MOVIL, RESOLUCION, RESOLUCIONES, SUFIJO, ZONA };
  raiz.CarestiaTV = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
"""


PRUEBA_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gráficos de prueba | Carestía</title>
<meta name="description" content="Página de prueba de los gráficos de Carestía.">
<meta name="robots" content="noindex, nofollow">
__ICONO__
__FUENTES__
<script src="/__TV_JS__?v=__VER_JS__"></script>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__
  /* encabezado: el mismo de las páginas del sitio */
  header { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px;
    padding:14px clamp(16px,3vw,32px); border-bottom:1px solid var(--line);
    min-height:51px; }
  .wordmark { font:700 20px/1.1 var(--display); letter-spacing:.06em;
    color:var(--bone); text-decoration:none; display:inline-flex;
    align-items:baseline; height:22px; overflow:hidden; }
  .wordmark .i { position:relative; display:inline-block; }
  .wordmark .i::after { content:"Í"; content:"Í" / ""; position:absolute;
    left:0; top:0; pointer-events:none;
    color:var(--ember); clip-path:inset(0 0 86% 0); }
  .tagline { font:400 12px/14.3px var(--sans); color:var(--ash); }
  main { max-width:1280px; margin:0 auto;
    padding:clamp(20px,3vw,32px) clamp(16px,3vw,32px) clamp(28px,4vw,44px); }
  .miga { font:500 10px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  h1 { font:600 clamp(24px,4vw,34px)/1.15 var(--sans);
    letter-spacing:-.005em; margin-top:6px; text-wrap:balance; }
  .intro { font:400 14px/1.6 var(--sans); color:var(--bone); margin-top:10px;
    max-width:76ch; text-wrap:pretty; }
  /* el lienzo: alto reservado antes de que monte cualquiera de los dos
     motores (CLS); en svh, estable frente a la barra del navegador móvil.
     Deja aire arriba y abajo para mover la página con el dedo fuera del
     gráfico */
  .marco { position:relative; margin-top:18px; border:1px solid var(--line);
    background:var(--bg); height:clamp(380px,calc(100vh - 230px),820px);
    height:clamp(380px,calc(100svh - 230px),820px); overflow:hidden; }
  #tv, #lw { position:absolute; inset:0; }
  /* respaldo con Lightweight Charts: los controles van sobre el lienzo, en
     una fila propia que no se desborda en móvil */
  .lw-barra { display:none; flex-wrap:wrap; align-items:center; gap:10px;
    margin-top:18px; }
  body[data-motor="lightweight"] .lw-barra { display:flex; }
  body[data-motor="lightweight"] .marco { margin-top:10px; }
  .vtoggle { display:flex; border:1px solid var(--line); background:var(--bg); }
  .vbtn { font:600 11px var(--mono); letter-spacing:.1em; padding:8px 14px;
    border:none; cursor:pointer; background:transparent; color:var(--ash);
    min-height:34px; }
  .vbtn + .vbtn { border-left:1px solid var(--line); }
  .vbtn.active { background:var(--bone); color:var(--bg); }
  .nomtoggle { border:1px solid var(--line); background:var(--bg);
    font:500 13px var(--sans); letter-spacing:0; }
  .lw-ref { font:400 11px/1.5 var(--sans); color:var(--dim); max-width:46ch; }
  .carga { position:absolute; inset:0; display:flex; align-items:center;
    justify-content:center; padding:20px; text-align:center;
    font:400 12px/1.5 var(--sans); color:var(--ash); pointer-events:none; }
  .carga[hidden] { display:none; }
  .nochart { display:flex; align-items:center; justify-content:center;
    height:100%; color:var(--ash); font-size:13px; padding:20px; text-align:center; }
  .motor { font:400 12px/1.6 var(--sans); color:var(--ash); margin-top:12px;
    text-wrap:pretty; }
  /* pista de gestos: solo en pantallas táctiles angostas */
  .gestos { display:none; font:400 12px/1.6 var(--sans); color:var(--dim);
    margin-top:4px; }
  @media (max-width:759px) { .gestos { display:block; } }
__CSS_SITIO__
</style>
</head>
<body data-motor="cargando">

  <header>
    <!-- span único: un solo flex item para que innerText no parta el texto -->
    <a class="wordmark" href="https://carestia.cl/"><span>CAREST<span class="i">Í</span>A</span></a>
    <span class="tagline">Índices del costo de vida en Chile</span>
    __NAV__
  </header>

  <main>
    <div class="miga">Página de prueba</div>
    <h1>Gráficos de prueba</h1>
    <p class="intro">El Índice Asado en la librería Advanced Charts de TradingView. Con el buscador de símbolos abres los otros índices y los __N_PRODUCTOS__ productos, __UNIDADES_PRUEBA__, y con Comparar los superpones.</p>
    <div class="lw-barra" aria-label="Vista del gráfico de respaldo">
      <div class="vtoggle">
        <button class="vbtn active" id="lw-linea">LÍNEA</button>
        <button class="vbtn" id="lw-velas">VELAS</button>
      </div>
      <button class="vbtn nomtoggle" id="lw-nominal">+ precio de la época</button>
      <span class="lw-ref" id="lw-ref"></span>
    </div>
    <div class="marco" id="marco">
      <div id="tv"></div>
      <div id="lw" hidden></div>
      <div class="carga" id="carga" role="status">Cargando el gráfico...</div>
    </div>
    <p class="motor" id="motor" role="status"></p>
    <p class="gestos" id="gestos"></p>
  </main>

__PIE__

<script>
(function () {
  'use strict';
  // índices (código y nombre) y versión de datos/, del build
  const INDICES = __INDICES__;
  const VER = '__VER__';
  const SIMBOLO = '__SIMBOLO__';
  const ESPERA = 8000;   // ms para que Advanced Charts quede lista
  const LIBRERIA = '/charting_library/';
  const LIGHTWEIGHT = 'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js';
  const TEXTO = {
    advanced: 'Gráfico con la librería Advanced Charts de TradingView.',
    falta: 'Gráfico de respaldo con Lightweight Charts: la librería Advanced Charts no está disponible en este sitio.',
    tarde: 'Gráfico de respaldo con Lightweight Charts: la librería Advanced Charts no inició en 8 segundos.',
    error: 'Gráfico de respaldo con Lightweight Charts: la librería Advanced Charts no pudo iniciar.',
    sin: 'No se pudo cargar el motor de gráficos (revisa la conexión).',
    gestosTv: 'Usa un dedo para moverte y dos para acercar.',
    gestosLw: 'Desliza hacia los lados para moverte. Usa dos dedos para acercar.',
    velas: 'Velas semanales. La mecha va del precio más bajo al más alto que ODEPA encontró entre los locales encuestados.',
  };
  const $ = id => document.getElementById(id);
  const TV = window.CarestiaTV;
  // los colores salen de los tokens de :root
  const VARS = getComputedStyle(document.documentElement);
  const tok = n => VARS.getPropertyValue('--' + n).trim();

  let resuelto = false, widget = null;
  function usar(motor, texto, gestos) {
    resuelto = true;
    clearTimeout(reloj);
    document.body.dataset.motor = motor;
    $('carga').hidden = true;
    $('motor').textContent = texto;
    $('gestos').textContent = gestos || '';
  }
  const reloj = setTimeout(() => respaldo('tarde'), ESPERA);
  function cargarScript(src) {
    return new Promise((ok, mal) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = ok;
      s.onerror = mal;
      document.head.appendChild(s);
    });
  }
  if (!TV) { usar('ninguno', TEXTO.sin); return; }
  const feed = TV.crearDatafeed({ base: '/datos/', ver: VER, indices: INDICES, uf: __UF__ });

  /* ---------- Advanced Charts ---------- */
  cargarScript(LIBRERIA + 'charting_library.standalone.js').then(iniciar, () => respaldo('falta'));

  function iniciar() {
    if (resuelto) return;
    if (!window.TradingView || typeof TradingView.widget !== 'function') { respaldo('falta'); return; }
    try {
      widget = new TradingView.widget(TV.opcionesWidget({
        contenedor: $('tv'), libreria: LIBRERIA, simbolo: SIMBOLO, datafeed: feed,
        tok, css: location.origin + '/__TV_CSS__?v=__VER_CSS__',
      }));
    } catch (e) {
      respaldo('error');
      return;
    }
    const w = widget;
    TV.listoWidget(w).then(() => {
      if (resuelto || w !== widget) return;   // ya se dibujó el respaldo
      usar('advanced', TEXTO.advanced, TEXTO.gestosTv);
      TV.alistarWidget(w, feed, tok);
    }, () => respaldo('error'));
  }

  /* ---------- respaldo: Lightweight Charts, como en /graficos.html ---------- */
  function respaldo(motivo) {
    if (resuelto) return;
    if (widget) { try { widget.remove(); } catch (e) {} widget = null; }
    $('tv').remove();
    usar('lightweight', TEXTO[motivo], TEXTO.gestosLw);
    const dia = ms => new Date(ms).toISOString().slice(0, 10);
    Promise.all([cargarScript(LIGHTWEIGHT), feed.barras(SIMBOLO), feed.barras(SIMBOLO + '-epoca')])
      .then(([, real, epoca]) => {
        if (!window.LightweightCharts || !real) throw new Error('sin motor');
        const lw = $('lw');
        lw.hidden = false;
        const fmt = v => '$' + TV.miles(v);
        const chart = LightweightCharts.createChart(lw, {
          autoSize: true,
          layout: { background: { type: 'solid', color: 'transparent' }, textColor: tok('ash'),
            fontFamily: tok('sans') },
          grid: { vertLines: { color: tok('grid') }, horzLines: { color: tok('grid') } },
          rightPriceScale: { borderColor: tok('line') },
          timeScale: { borderColor: tok('line') },
          // misma política de gestos del sitio: la rueda y el deslizamiento
          // vertical quedan para la página; zoom en los ejes y con dos dedos
          handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
          handleScroll: { mouseWheel: false, vertTouchDrag: false,
            horzTouchDrag: true, pressedMouseMove: true },
          crosshair: { mode: 0,
            vertLine: { color: tok('cruz'), labelBackgroundColor: tok('line') },
            horzLine: { color: tok('cruz'), labelBackgroundColor: tok('line') } },
          localization: { locale: 'es-CL', priceFormatter: fmt },
        });
        const sNom = chart.addLineSeries({ color: tok('ash'), lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false, visible: false });
        // la línea de los índices oficiales, en brasa
        const sReal = chart.addLineSeries({ color: tok('ember'), lineWidth: 2,
          priceLineVisible: false });
        const sVelas = chart.addCandlestickSeries({ upColor: tok('verde'),
          downColor: tok('rojo'), borderVisible: false, wickUpColor: tok('verde'),
          wickDownColor: tok('rojo'), visible: false });
        sNom.setData((epoca || []).map(b => ({ time: dia(b.time), value: b.close })));
        sReal.setData(real.map(b => ({ time: dia(b.time), value: b.close })));
        sVelas.setData(real.map(b => ({ time: dia(b.time), open: b.open, high: b.high,
          low: b.low, close: b.close })));
        let vista = 'linea', nom = false;
        const aplicar = () => {
          const linea = vista === 'linea';
          sReal.applyOptions({ visible: linea });
          sNom.applyOptions({ visible: linea && nom });
          sVelas.applyOptions({ visible: !linea });
          $('lw-linea').classList.toggle('active', linea);
          $('lw-velas').classList.toggle('active', !linea);
          $('lw-nominal').classList.toggle('active', nom);
          $('lw-nominal').style.visibility = linea ? 'visible' : 'hidden';
          $('lw-ref').textContent = linea ? '' : TEXTO.velas;
          chart.timeScale().fitContent();
        };
        $('lw-linea').onclick = () => { vista = 'linea'; aplicar(); };
        $('lw-velas').onclick = () => { vista = 'velas'; aplicar(); };
        $('lw-nominal').onclick = () => { nom = !nom; aplicar(); };
        aplicar();
      })
      .catch(() => {
        $('lw').hidden = false;
        $('lw').innerHTML = '<div class="nochart">' + TEXTO.sin + '</div>';
        $('motor').textContent = TEXTO.sin;
      });
  }
})();
</script>
</body>
</html>
"""


# variables de color de la interfaz de la librería (toolbars, menús y
# diálogos) para el tema oscuro, con los tokens del sitio
TV_COLORES = """.theme-dark:root {{
  --tv-color-platform-background: {bg};
  --tv-color-pane-background: {bg};
  --tv-color-toolbar-button-background-hover: {hover};
  --tv-color-toolbar-button-background-expanded: {hover};
  --tv-color-toolbar-button-background-active: {hover};
  --tv-color-toolbar-button-background-active-hover: {hover};
  --tv-color-toolbar-button-text: {ash};
  --tv-color-toolbar-button-text-hover: {bone};
  --tv-color-toolbar-button-text-active: {bone};
  --tv-color-toolbar-button-text-active-hover: {bone};
  --tv-color-item-active-text: {bone};
  --tv-color-toolbar-toggle-button-background-active: {line};
  --tv-color-toolbar-toggle-button-background-active-hover: {line};
  --tv-color-toolbar-divider-background: {line};
  --tv-color-toolbar-save-layout-loader: {dim};
  --tv-color-popup-background: {panel};
  --tv-color-popup-element-text: {bone};
  --tv-color-popup-element-text-hover: {bone};
  --tv-color-popup-element-background-hover: {hover};
  --tv-color-popup-element-divider-background: {line};
  --tv-color-popup-element-secondary-text: {ash};
  --tv-color-popup-element-hint-text: {dim};
  --tv-color-popup-element-text-active: {bone};
  --tv-color-popup-element-background-active: {line};
  --tv-color-popup-element-toolbox-text: {ash};
  --tv-color-popup-element-toolbox-text-hover: {bone};
  --tv-color-popup-element-toolbox-text-active-hover: {bone};
  --tv-color-popup-element-toolbox-background-hover: {hover};
  --tv-color-popup-element-toolbox-background-active-hover: {hover};
}}
"""


def tokens_css() -> dict:
    """Los tokens de color de CSS_BASE ({nombre: valor}): el tema del iframe
    de la librería sale de los mismos valores que el resto del sitio."""
    return dict(re.findall(r"--([a-z0-9]+):(#[0-9a-f]{6}|rgba\([^)]*\))", CSS_BASE))


def tv_css() -> str:
    """carestia-tv.css: el tema del sitio dentro del iframe de Advanced Charts
    (custom_css_url). Plex Sans con la misma llamada a Google Fonts del sitio
    (el iframe es otro documento: no hereda las fuentes de la página) y los
    colores de la interfaz de la librería con los tokens."""
    t = tokens_css()
    fuentes = re.search(r'https://fonts\.googleapis\.com/css2\?[^"]+', FUENTES).group(0)
    colores = TV_COLORES.format(**t)
    return (f'/* Tema de Carestía para Advanced Charts: tokens de build_site.py */\n'
            f'@import url("{fuentes}");\n'
            f'{colores}'
            # menús y diálogos en Plex Sans (el lienzo la toma de
            # custom_font_family)
            f'html, body {{ font-family: {t_sans()}; }}\n')


def t_sans() -> str:
    """La familia --sans de CSS_BASE."""
    return re.search(r"--sans:([^;]+);", CSS_BASE).group(1)


def indices_tv() -> str:
    """Los 4 índices para el datafeed (código y nombre), en JSON para el JS."""
    return _json([{"codigo": c, "nombre": d["nombre"]}
                  for c, d in DATA["indices"].items()]).replace("</", "<\\/")


def _ver(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:10]


def generar_tradingview(app: dict, catalogo: dict) -> None:
    """carestia-tv.js, carestia-tv.css y /prueba-graficos.html."""
    css = tv_css()
    for archivo, texto in [(TV_JS, FEED_JS), (TV_CSS, css)]:
        with open(archivo, "w", encoding="utf-8") as fh:
            fh.write(texto)
    simbolo = "asado" if "asado" in DATA["indices"] else next(iter(DATA["indices"]))
    out = PRUEBA_HTML
    for token, valor in [
        ("__TV_JS__", TV_JS),
        ("__VER_JS__", _ver(FEED_JS)),
        ("__TV_CSS__", TV_CSS),
        ("__VER_CSS__", _ver(css)),
        ("__ICONO__", ICONO),
        ("__FUENTES__", FUENTES),
        ("__CSS_BASE__", CSS_BASE),
        ("__CSS_SITIO__", CSS_SITIO),
        ("__NAV__", nav_sitio()),
        ("__PIE__", pie_sitio(graficos=True)),
        ("__N_PRODUCTOS__", str(len(catalogo["productos"]))),
        ("__SIMBOLO__", simbolo),
        ("__VER__", app["ver"]),
        # "</" escapado: un nombre nunca puede cerrar el <script>
        ("__INDICES__", indices_tv()),
        ("__UF__", "true" if app["uf"] else "false"),
        ("__UNIDADES_PRUEBA__",
         "en pesos de hoy, a precio de la época o en UF (por ejemplo, asado-epoca o asado-uf)"
         if app["uf"] else
         "en pesos de hoy o a precio de la época (por ejemplo, asado-epoca)"),
    ]:
        out = out.replace(token, valor)
    with open(TV_PRUEBA, "w", encoding="utf-8") as fh:
        fh.write(out)


# ---------------- Páginas del sitio ----------------
# /productos/, /metodologia.html y las páginas institucionales y legales.
# Misma <head> que las fichas (canonical, og, favicon, fuentes y beacon de
# Cloudflare), sin Lightweight Charts porque no tienen gráfico, y la
# navegación y el pie comunes. HTML estático: se leen sin JS.
PAGINA_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
__HEAD_URL__
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:image" content="https://carestia.cl/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
__ICONO__
__FUENTES__
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__
  /* encabezado: el mismo de las fichas */
  header { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px;
    padding:14px clamp(16px,3vw,32px); border-bottom:1px solid var(--line);
    min-height:51px; }
  .wordmark { font:700 20px/1.1 var(--display); letter-spacing:.06em;
    color:var(--bone); text-decoration:none; display:inline-flex;
    align-items:baseline; height:22px; overflow:hidden; }
  .wordmark .i { position:relative; display:inline-block; }
  .wordmark .i::after { content:"Í"; content:"Í" / ""; position:absolute;
    left:0; top:0; pointer-events:none;
    color:var(--ember); clip-path:inset(0 0 86% 0); }
  .tagline { font:400 12px/14.3px var(--sans); color:var(--ash); }
  main { max-width:980px; margin:0 auto;
    padding:clamp(20px,4vw,36px) clamp(16px,3vw,32px) clamp(28px,4vw,44px); }
  .miga { font:500 10px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  h1 { font:600 clamp(26px,5vw,40px)/1.15 var(--sans);
    letter-spacing:-.005em; margin-top:6px; text-wrap:balance; }

  /* ---- textos: metodología, institucionales y legales ---- */
  .doc { max-width:760px; }
  .doc > h1:first-child { margin-top:0; }
  .doc h2 { font:600 11px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; margin-top:40px; }
  .doc h3 { font:600 16px var(--sans); color:var(--bone); }
  .doc h3 span { font-weight:400; color:var(--ash); }
  .doc p, .doc li { font:400 15px/1.7 var(--sans);
    color:var(--bone); max-width:70ch; text-wrap:pretty; }
  .doc p { margin-top:14px; }
  .doc ul { margin-top:12px; padding-left:18px; }
  .doc li + li { margin-top:8px; }
  .doc li::marker { color:var(--ash); }
  .doc strong { font-weight:600; }
  .doc code { font:inherit; font-size:.95em; background:var(--panel);
    border:1px solid var(--line); padding:0 5px;
    -webkit-box-decoration-break:clone; box-decoration-break:clone; }
  .doc a { color:var(--bone); text-decoration:underline;
    text-decoration-color:var(--dim); text-underline-offset:3px; }
  .doc a:hover, .doc a:focus-visible { text-decoration-color:var(--bone); }
  .doc .meta { font-size:13px; color:var(--ash); }
  .doc .sub { padding-left:3ch; }   /* sub-cláusulas: 4.1., 4.2., ... */
  .doc .pendiente { border:1px dashed var(--dim); padding:12px 16px;
    color:var(--ash); }
  /* las canastas: cantidades leídas de BASKETS (indices.py) */
  .canastas { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
    gap:26px 32px; margin-top:18px; }
  .canastas .csub { font:400 13px/1.5 var(--sans); color:var(--ash);
    margin-top:4px; }
  .canastas ul { list-style:none; margin-top:10px; padding-left:0; }
  .canastas li { font:400 14px/1.5 var(--sans); padding:7px 0;
    border-bottom:1px solid var(--line); }
  .canastas li + li { margin-top:0; }

  /* ---- /productos/: listado estático de fichas ---- */
  .intro { font:400 15px/1.7 var(--sans); color:var(--bone);
    margin-top:14px; max-width:70ch; text-wrap:pretty; }
  .grupos { display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; list-style:none; }
  .grupos a { display:inline-flex; align-items:center; gap:8px; min-height:34px;
    padding:7px 12px; font:500 13px var(--sans);
    text-decoration:none; color:var(--bone); background:var(--panel);
    border:1px solid var(--line); }
  .grupos a span { color:var(--ash); }
  .grupos a:hover, .grupos a:focus-visible { border-color:var(--bone); background:var(--hover); }
  .pgrupo { margin-top:36px; scroll-margin-top:12px; }
  .pgrupo h2 { font:600 11px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  .pgrupo h2 span { letter-spacing:.04em; }
  .plista { list-style:none; margin-top:10px; display:grid;
    grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); column-gap:32px; }
  .plista a { display:flex; align-items:baseline; justify-content:space-between;
    gap:14px; min-height:44px; padding:11px 0; text-decoration:none;
    color:var(--bone); border-bottom:1px solid var(--line); }
  .plista a:hover .pn, .plista a:focus-visible .pn { text-decoration:underline;
    text-decoration-color:var(--bone); text-underline-offset:3px; }
  .pn { font:500 14px/1.4 var(--sans); }
  .pf { display:block; font:400 12px var(--sans); color:var(--ash);
    margin-top:2px; }
  .pp { font:600 14px var(--sans);
    white-space:nowrap; text-align:right; }
  .pp small { font:400 12px var(--sans); color:var(--ash); }
__CSS_SITIO__
</style>
</head>
<body>

  <header>
    <!-- span único: un solo flex item para que innerText no parta el texto -->
    <a class="wordmark" href="https://carestia.cl/"><span>CAREST<span class="i">Í</span>A</span></a>
    <span class="tagline">Índices del costo de vida en Chile</span>
    __NAV__
  </header>

  <main class="__CLASE__">
__MAIN__
  </main>

__PIE__
</body>
</html>
"""


def escribir_pagina(archivo: str, url: str, titulo: str, desc: str, cuerpo: str,
                    actual: str = "", clase: str = "doc") -> None:
    """Escribe una página del sitio. url=None: no indexable (el 404), sin
    canonical y con noindex."""
    if url:
        head_url = f'<link rel="canonical" href="{url}">'
    else:
        head_url = '<meta name="robots" content="noindex">'
    out = PAGINA_HTML
    for token, valor in [
        ("__TITLE__", html.escape(titulo, quote=True)),
        ("__DESC__", html.escape(desc, quote=True)),
        ("__HEAD_URL__", head_url),
        ("__ICONO__", ICONO),
        ("__FUENTES__", FUENTES),
        ("__CSS_BASE__", CSS_BASE),
        ("__CSS_SITIO__", CSS_SITIO),
        ("__NAV__", nav_sitio(actual)),
        ("__PIE__", pie_sitio(actual)),
        ("__CLASE__", clase),
        ("__MAIN__", cuerpo),   # al final: HTML ya renderizado
    ]:
        out = out.replace(token, valor)
    carpeta = os.path.dirname(archivo)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as fh:
        fh.write(out)


def _orden(s: str) -> str:
    """Clave de orden alfabético en castellano, sin tildes ni mayúsculas."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def generar_indice_productos(fichas: dict) -> None:
    """productos/index.html: las fichas publicadas agrupadas por grupo ODEPA
    (A-Z, "Otros" al final), cada una con su precio de hoy en pesos de hoy y
    un <a href> a su ficha. Sin semáforo: está reservado a los 4 índices.
    Si la última semana con dato de un producto no es la más reciente del
    catálogo (estacionales), se dice de cuándo es el precio. Los productos
    cuyo último dato tiene más de 52 semanas van al final, en su propia
    sección "Sin datos hace más de un año", con su último dato y su fecha."""
    prods = DATA.get("productos", {})
    filas = []
    for slug, (key, label) in fichas.items():
        p = prods[key]
        ult = [v for v in p["v"] if v is not None][-1]
        filas.append((p.get("grupo") or "Otros", label, slug, ult,
                      UNI_TXT.get(p["unidad"], p["unidad"]), fin_serie(p)))
    semana = max((f[5] for f in filas), default=None)
    grupos, sin_datos = {}, []
    for f in filas:
        if sin_datos_hace_un_anio(f[5], semana):
            sin_datos.append(f)
        else:
            grupos.setdefault(f[0], []).append(f)
    orden = sorted(grupos, key=lambda g: (g == "Otros", _orden(g)))

    def item(label, slug, ult, uni, fin):
        viejo = (f'<span class="pf">precio de la semana del '
                 f'{fin.strftime("%d-%m-%Y")}</span>' if fin != semana else "")
        return (f'<li><a href="{SITIO}/productos/{slug}.html">'
                f'<span class="pn">{html.escape(label)}{viejo}</span>'
                f'<span class="pp">{fmt_clp(ult)} <small>por {uni}</small></span>'
                f'</a></li>')

    ID_SIN_DATOS = "sin-datos"
    chips = [(slug_url(g), g, len(grupos[g])) for g in orden]
    if sin_datos:
        chips.append((ID_SIN_DATOS, "Sin datos hace más de un año", len(sin_datos)))
    indice = "\n        ".join(
        f'<li><a href="#{ancla}">{html.escape(grupo_txt(g))} '
        f'<span>{k}</span></a></li>' for ancla, g, k in chips)
    secciones = []
    for g in orden:
        lis = "\n        ".join(
            item(*f[1:]) for f in sorted(grupos[g], key=lambda f: _orden(f[1])))
        secciones.append(
            f'    <section class="pgrupo" id="{slug_url(g)}">\n'
            f'      <h2>{html.escape(grupo_txt(g))} <span>({len(grupos[g])})</span></h2>\n'
            f'      <ul class="plista">\n        {lis}\n      </ul>\n'
            f'    </section>')
    if sin_datos:
        lis = "\n        ".join(
            item(*f[1:]) for f in sorted(sin_datos, key=lambda f: _orden(f[1])))
        secciones.append(
            f'    <section class="pgrupo" id="{ID_SIN_DATOS}">\n'
            f'      <h2>Sin datos hace más de un año <span>({len(sin_datos)})</span></h2>\n'
            f'      <p class="intro">ODEPA no ha publicado precios de estos productos '
            f'en los últimos 12 meses. Se muestran con su último dato y su fecha.</p>\n'
            f'      <ul class="plista">\n        {lis}\n      </ul>\n'
            f'    </section>')
    n = len(filas)
    fecha = semana.strftime("%d-%m-%Y") if semana else "·"
    cuerpo = (
        f'    <div class="miga">Catálogo en pesos de hoy</div>\n'
        f'    <h1>Productos</h1>\n'
        f'    <p class="intro">Precios de {n} productos en la Región '
        f'Metropolitana, en pesos de hoy: el promedio de los puntos que ODEPA '
        f'encuesta cada semana (ferias libres, supermercados y carnicerías). '
        f'Semana del {fecha}. Cada producto enlaza a su serie semanal.</p>\n'
        f'    <nav aria-label="Grupos de productos"><ul class="grupos">\n'
        f'        {indice}\n'
        f'    </ul></nav>\n' + "\n".join(secciones))
    escribir_pagina(
        os.path.join("productos", "index.html"), f"{SITIO}/productos/",
        f"Precios de {n} alimentos en Chile, en pesos de hoy | Carestía",
        f"Precios de {n} alimentos en la Región Metropolitana, en pesos "
        f"de hoy, agrupados por tipo y con la serie semanal de cada uno. Datos "
        f"ODEPA, actualizado cada viernes.",
        cuerpo, actual="productos", clase="catalogo")


# ---------------- Portada ----------------
# La tabla muestra los productos con precio en las últimas 4 semanas; las
# listas de "Esta semana", solo los que tienen precio en la semana vigente.
# Todo sale de datos/catalogo.json (el mismo cálculo) y cada fila lleva a la
# ficha del producto.
SEMANAS_TABLA = 4
TOP_SEMANA = 5
# el semáforo de cada veredicto, por su token (solo en los 4 índices)
SEMAFORO = {"BARATO": "var(--verde)", "NORMAL": "var(--ambar)", "CARO": "var(--rojo)"}


def cambio(x, sep: str = " ") -> str:
    """Variación con flecha neutra: ▲ sube, ▼ baja, = si redondea a 0,0.
    Sin dato, el marcador "·"."""
    if x is None:
        return "·"
    r = round(x, 1)
    f = "=" if r == 0 else ("▲" if r > 0 else "▼")
    num = f"{abs(r):.1f}".replace(".", ",")
    return f'<i class="f">{f}</i>{sep}{num}%'


def sparkline(vals: list) -> str:
    """Path SVG del último año (52 semanas, la más reciente a la derecha) en
    un viewBox 0 0 51 100 que se estira al tamaño de cada pantalla; donde no
    hubo precio la línea se corta. Enteros y lineto implícitos: pocos bytes
    por fila."""
    nums = [v for v in vals if v is not None]
    if len(nums) < 2:
        return ""
    lo, hi = min(nums), max(nums)
    desde = 52 - len(vals)
    trazos, trazo = [], []
    for i, v in enumerate(vals):
        if v is None:
            if trazo:
                trazos.append(trazo)
            trazo = []
            continue
        y = 50 if hi == lo else round(96 - (v - lo) / (hi - lo) * 92)
        trazo.append(f"{desde + i} {y}")
    if trazo:
        trazos.append(trazo)
    d = "".join("M" + " ".join(t) + ("h0" if len(t) == 1 else "") for t in trazos)
    return (f'<svg class="sp" viewBox="0 0 51 100" preserveAspectRatio="none" '
            f'aria-hidden="true"><path d="{d}"/></svg>')


def html_cinta(indices: dict) -> str:
    """La cinta de índices, dos veces seguidas para el desplazamiento continuo
    (la segunda copia queda fuera del orden de tabulación y de los lectores
    de pantalla). Cada índice abre su gráfico."""
    items = []
    for code, d in indices.items():
        r = resumen_indice(d)
        items.append(
            f'<a class="titem" href="/graficos.html#{code}"__OCULTA__>'
            f'<span class="tn">{html.escape(d["nombre"].replace("Índice ", "").upper())}</span>'
            f'<span class="tp">{fmt_clp(d["costo_real"])}</span>'
            f'<span class="td">{cambio(r["delta"], "")}</span></a>')
    return "\n".join(["      " + i.replace("__OCULTA__", "") for i in items] +
                     ["      " + i.replace("__OCULTA__", ' aria-hidden="true" tabindex="-1"')
                      for i in items])


def html_tarjetas(indices: dict) -> str:
    """Las 4 tarjetas de "Índices Carestía": veredicto con su color del
    semáforo, costo en pesos de hoy, percentil sobre las tres zonas, cambio
    semanal y distancia a su promedio. Cada una abre /graficos.html#codigo."""
    out = []
    for code, d in indices.items():
        r = resumen_indice(d)
        corto = html.escape(d["nombre"].replace("Índice ", "").upper())
        color = SEMAFORO.get(d["veredicto"], html.escape(d["color"]))
        pct = d["percentil"]
        vs = d["vs_promedio"]
        vs_txt = f"+{vs}% sobre" if vs >= 0 else f"{vs}% bajo"
        # sin la semana anterior no hay cambio que mostrar
        semana = (f'{cambio(r["delta"])} esta semana' if r["delta"] is not None
                  else "sin la semana anterior")
        semana_m = (f'{cambio(r["delta"])} (p{pct})' if r["delta"] is not None
                    else f"percentil {pct}")
        out.append(
            f'        <a class="icard" href="/graficos.html#{code}">\n'
            f'          <div class="ic-top"><span class="ic-ey"><span class="ic-ind">ÍNDICE </span>{corto}</span>'
            f'<span class="ic-pill" style="background:{color}">{html.escape(d["veredicto"])}</span></div>\n'
            f'          <div class="ic-mid"><span class="ic-sub">{html.escape(d["subtitulo"])}</span>'
            f'<span class="ic-precio">{fmt_clp(d["costo_real"])}</span>'
            f'<span class="ic-ph">en pesos de hoy</span></div>\n'
            f'          <div class="ic-niv"><div class="ic-nl"><span>Nivel frente a su historia</span>'
            f'<span>percentil {pct}</span></div>'
            f'<div class="zonas" aria-hidden="true"><span class="z z1"></span><span class="z z2"></span>'
            f'<span class="z z3"></span><span class="marca" style="left:{pct}%"></span></div></div>\n'
            f'          <div class="ic-pie"><span>{semana}</span>'
            f'<span>{vs_txt} su promedio</span></div>\n'
            f'          <div class="ic-m">{semana_m}</div>\n'
            f'        </a>')
    return "\n".join(out)


def filas_portada(catalogo: dict, fichas: dict) -> tuple:
    """(tabla, vigentes): las filas del catálogo con ficha publicada y precio
    en las últimas SEMANAS_TABLA semanas, en orden alfabético, y de ellas las
    que tienen precio en la semana vigente (las listas de "Esta semana")."""
    con_ficha = set(fichas)
    vigente = catalogo["semana"]
    if not vigente:
        return [], []
    corte = (datetime.date.fromisoformat(vigente) -
             datetime.timedelta(weeks=SEMANAS_TABLA - 1)).isoformat()
    tabla = sorted((f for f in catalogo["productos"]
                    if f["slug"] in con_ficha and f["semana"] >= corte),
                   key=lambda f: _orden(f["nombre"]))
    return tabla, [f for f in tabla if f["semana"] == vigente]


def html_listas(vigentes: list) -> str:
    """Más subieron, más bajaron y más caros respecto de su historia: 5 de
    cada una. Empates de percentil: primero el que más subió en un año."""
    sube = sorted((f for f in vigentes if (f["variacion_1s_pct"] or 0) > 0),
                  key=lambda f: (-f["variacion_1s_pct"], _orden(f["nombre"])))
    baja = sorted((f for f in vigentes if (f["variacion_1s_pct"] or 0) < 0),
                  key=lambda f: (f["variacion_1s_pct"], _orden(f["nombre"])))
    caros = sorted(vigentes, key=lambda f: (
        -f["percentil"], f["variacion_52s_pct"] is None,
        -(f["variacion_52s_pct"] or 0), _orden(f["nombre"])))
    listas = [
        ("sem-sub", "Más subieron", "Contra la semana anterior, en pesos de hoy",
         sube, lambda f: cambio(f["variacion_1s_pct"])),
        ("sem-baj", "Más bajaron", "Contra la semana anterior, en pesos de hoy",
         baja, lambda f: cambio(f["variacion_1s_pct"])),
        ("sem-car", "Más caros respecto de su historia", "Percentil de su serie completa",
         caros, lambda f: f"percentil {f['percentil']}"),
    ]
    out = []
    for i, (lid, titulo, sub, filas, valor) in enumerate(listas):
        lis = "\n".join(
            f'            <li><a href="/productos/{f["slug"]}.html"><span class="sn">'
            f'<b>{html.escape(f["nombre"])}</b> '
            f'<small>{UNI_TXT.get(f["unidad"], f["unidad"])}</small></span>'
            f'<span class="sv">{valor(f)}</span></a></li>'
            for f in filas[:TOP_SEMANA])
        if not lis:
            lis = '            <li class="vacio">Sin productos esta semana.</li>'
        out.append(
            f'          <div class="sem-l{" on" if i == 0 else ""}" id="{lid}">\n'
            f'            <div class="sem-h"><h3>{titulo}</h3><span>{sub}</span></div>\n'
            f'            <ul>\n{lis}\n            </ul>\n'
            f'          </div>')
    return "\n".join(out)


def html_productos(tabla: list, vigente: str) -> tuple:
    """(chips, filas) de la tabla de productos. Cada fila es un <a href> a la
    ficha con sus valores en data-* para ordenar en el navegador; el grupo va
    como índice de su chip."""
    grupos = list(dict.fromkeys(f["grupo"] for f in sorted(
        tabla, key=lambda f: (f["grupo"] == "Otros", _orden(f["grupo"])))))
    chips = ['        <button type="button" data-g="" aria-pressed="true">Todos</button>'] + [
        f'        <button type="button" data-g="{i}" aria-pressed="false">'
        f'{html.escape(g)}</button>' for i, g in enumerate(grupos)]

    def dato(k, x):
        return "" if x is None else f' data-{k}="{x}"'
    filas = []
    for f in tabla:
        uni = UNI_TXT.get(f["unidad"], f["unidad"])
        pct = f["percentil"]
        viejo = ("" if f["semana"] == vigente else
                 f'<small>semana del {f["semana"][8:10]}-{f["semana"][5:7]}</small>')
        filas.append(
            f'          <a class="fila" href="/productos/{f["slug"]}.html" '
            f'data-g="{grupos.index(f["grupo"])}"'
            f'{dato("p", f["precio_pesos_hoy"])}{dato("w", f["variacion_1s_pct"])}'
            f'{dato("t", f["variacion_13s_pct"])}{dato("y", f["variacion_52s_pct"])}'
            f'{dato("c", pct)}>'
            f'<span class="c-n"><span class="nm">{html.escape(f["nombre"])}</span>'
            f'<span class="mt"><span class="mg">{html.escape(f["grupo"])}, </span>por {uni}'
            f'<span class="mp">, percentil {pct}</span></span></span>'
            f'<span class="c-p">{fmt_clp(f["precio_pesos_hoy"])}{viejo}</span>'
            f'<span class="c-v c-w">{cambio(f["variacion_1s_pct"])}</span>'
            f'<span class="c-v c-t">{cambio(f["variacion_13s_pct"])}</span>'
            f'<span class="c-v c-y">{cambio(f["variacion_52s_pct"])}</span>'
            f'<span class="c-c"><span class="bar"><span style="width:{pct}%"></span></span>'
            f'<span class="cn">{pct}</span></span>'
            f'{sparkline(f["ultimas_52"])}</a>')
    return "\n".join(chips), "\n".join(filas)


def generar_portada(catalogo: dict, fichas: dict) -> None:
    """index.html: la portada en formato tabla (ver PORTADA_HTML)."""
    indices = DATA["indices"]
    tabla, vigentes = filas_portada(catalogo, fichas)
    chips, filas = html_productos(tabla, catalogo["semana"])
    # hashes de la app que redirigen a /graficos.html
    hashes = "|".join(["canasta(?:=.*)?", "comparar", "productos"] +
                      [re.escape(c) for c in indices])
    fecha = next(iter(indices.values()))["fecha"] if indices else "·"
    out = PORTADA_HTML
    for token, valor in [
        ("__HASHES__", hashes),
        ("__ICONO__", ICONO),
        ("__FUENTES__", FUENTES),
        ("__CSS_BASE__", CSS_BASE),
        ("__CSS_CABECERA__", CSS_CABECERA),
        ("__CSS_SITIO__", CSS_SITIO),
        ("__NAV__", nav_sitio()),
        ("__PIE__", pie_sitio()),
        ("__FECHA__", html.escape(fecha)),
        ("__CINTA__", html_cinta(indices)),
        ("__TARJETAS__", html_tarjetas(indices)),
        ("__LISTAS__", html_listas(vigentes)),
        ("__CHIPS__", chips),
        ("__FILAS__", filas),   # al final: HTML ya renderizado
    ]:
        out = out.replace(token, valor)
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(out)


# ---- textos/*.md (del dueño) ----
# Los textos van LITERALES: aquí solo se les da formato HTML. Una línea es un
# bloque; "## " título; "- " ítem de lista; **negrita**, `código`,
# [texto](url) y los correos (mailto) en línea. Nada se reescribe.
def md_en_linea(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: f'<a href="{html.escape(html.unescape(m.group(2)))}">'
                         f'{m.group(1)}</a>', s)
    partes = re.split(r"(<a\b[^>]*>.*?</a>)", s)
    for i in range(0, len(partes), 2):   # fuera de los links ya armados
        partes[i] = re.sub(r"(?<![\w.+-])([\w.+-]+@[\w-]+(?:\.[\w-]+)+)",
                           r'<a href="mailto:\1">\1</a>', partes[i])
    # RUT y fechas con guion (78.521.796-9, 22-07-2026) sin corte de línea;
    # solo en el texto, nunca dentro de una etiqueta
    partes = re.split(r"(<[^>]+>)", "".join(partes))
    for i in range(0, len(partes), 2):
        partes[i] = re.sub(r"(?<![\w.-])(\d+(?:[.\-]\d+)*-[\dkK]\d*)(?![\w-])",
                           r'<span class="nw">\1</span>', partes[i])
    return "".join(partes)


def md_a_html(texto: str) -> str:
    bloques, lista = [], []

    def cerrar_lista():
        if lista:
            bloques.append("<ul>\n" + "\n".join(lista) + "\n</ul>")
            lista.clear()

    for linea in texto.splitlines():
        s = linea.strip()
        if not s:
            cerrar_lista()
            continue
        if s.startswith("- "):
            lista.append(f"<li>{md_en_linea(s[2:])}</li>")
            continue
        cerrar_lista()
        if s.startswith("### "):
            bloques.append(f"<h3>{md_en_linea(s[4:])}</h3>")
        elif s.startswith("## "):
            bloques.append(f"<h2>{md_en_linea(s[3:])}</h2>")
        elif s.startswith("PENDIENTE"):
            bloques.append(f'<p class="pendiente">{md_en_linea(s)}</p>')
        elif s.startswith("Última actualización"):
            bloques.append(f'<p class="meta">{md_en_linea(s)}</p>')
        elif re.match(r"\d+\.\d+\.\s", s):
            bloques.append(f'<p class="sub">{md_en_linea(s)}</p>')
        else:
            bloques.append(f"<p>{md_en_linea(s)}</p>")
    cerrar_lista()
    return "\n".join(bloques)


# textos/{nombre}.md: los anexos del dueño (literales). Una línea que parte
# con "PENDIENTE" marca un texto que aún no llega completo: el build se niega
# a publicar (ver más abajo) salvo en una vista previa local con
# CARESTIA_BORRADOR=1.
TEXTOS = ["terminos", "privacidad", "acerca", "contacto",
          "metodologia", "notas_metodologicas", "404"]


def leer_texto(nombre: str) -> str:
    ruta = os.path.join("textos", f"{nombre}.md")
    if not os.path.exists(ruta):
        raise SystemExit(f"build_site.py: falta {ruta}")
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def texto_pendiente(nombre: str) -> bool:
    return any(l.strip().startswith("PENDIENTE")
               for l in leer_texto(nombre).splitlines())


def cargar_texto(nombre: str) -> tuple:
    """(título, html) de textos/{nombre}.md. Si la primera línea no vacía va
    entera en negrita, es el título de la página (h1); si no, título None."""
    lineas = leer_texto(nombre).splitlines()
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    titulo = None
    m = re.fullmatch(r"\*\*(.+)\*\*", lineas[0].strip()) if lineas else None
    if m and "**" not in m.group(1):
        titulo = m.group(1)
        lineas = lineas[1:]
    return titulo, md_a_html("\n".join(lineas))


def fmt_cantidad(qty, uni: str) -> str:
    n = f"{qty:g}".replace(".", ",")
    if uni == "un":
        return f"{n} unidad" if qty == 1 else f"{n} unidades"
    if uni == "l":
        return f"{n} litro" if qty == 1 else f"{n} litros"
    return f"{n} {uni}"


def html_canastas() -> str:
    """Las 4 canastas con sus cantidades, generadas desde el diccionario
    BASKETS de indices.py: la misma fuente que usa el cálculo. Cada producto
    va como "Asado de tira: 1 kg"."""
    bloques = []
    for code, meta in BASKETS.items():
        filas = "\n          ".join(
            f"<li>{html.escape(lab)}: {fmt_cantidad(qty, uni)}</li>"
            for (lab, _match, qty, uni) in meta["items"])
        bloques.append(
            f'      <div class="canasta" id="canasta-{code}">\n'
            f'        <h3>{html.escape(meta["nombre"])}</h3>\n'
            f'        <p class="csub">{html.escape(meta["subtitulo"])}</p>\n'
            f'        <ul>\n          {filas}\n        </ul>\n'
            f'      </div>')
    return '<div class="canastas">\n' + "\n".join(bloques) + '\n    </div>'


def secciones_md(texto: str) -> list:
    """[(título, html)] de un texto partido en sus líneas '## ' (títulos de
    sección); lo que vaya antes del primer título queda con título None."""
    secciones, titulo, cuerpo = [], None, []
    for linea in texto.splitlines() + ["## "]:   # centinela: cierra la última
        if linea.startswith("## "):
            if titulo is not None or any(l.strip() for l in cuerpo):
                secciones.append((titulo, md_a_html("\n".join(cuerpo))))
            titulo, cuerpo = linea[3:].strip(), []
        else:
            cuerpo.append(linea)
    return secciones


def generar_metodologia() -> None:
    """/metodologia.html: las secciones de textos/metodologia.md (literales,
    "Cómo se calcula", "Fuentes" y "Deslinde"), con "Las canastas" desde
    BASKETS tras la primera, y al final las de textos/notas_metodologicas.md.
    Cada sección lleva su propio título ('## ')."""
    secciones = []
    for titulo, contenido in secciones_md(leer_texto("metodologia")):
        titulo = titulo or "Metodología"
        secciones.append(("resumen" if titulo == "Cómo se calcula"
                          else slug_url(titulo), md_en_linea(titulo), contenido))
        if titulo == "Cómo se calcula":
            secciones.append(("canastas", html.escape("Las canastas"), html_canastas()))
    for titulo, contenido in secciones_md(leer_texto("notas_metodologicas")):
        titulo = titulo or "Notas metodológicas"
        secciones.append((slug_url(titulo), md_en_linea(titulo), contenido))
    cuerpo = "    <h1>Metodología</h1>\n" + "\n".join(
        f'    <section id="{sid}">\n    <h2>{t}</h2>\n{contenido}\n    </section>'
        for sid, t, contenido in secciones)
    escribir_pagina(
        "metodologia.html", f"{SITIO}/metodologia.html",
        "Metodología de los índices del costo de vida | Carestía",
        "Cómo se calculan los índices Carestía: canastas fijas, pesos de hoy "
        "con el IPC, percentil histórico, estacionalidad y fuentes (ODEPA y "
        "Banco Central de Chile).",
        cuerpo, actual="metodologia")


# (texto, archivo, url, clave nav/pie, título si el texto no trae uno,
#  <title>, description)
PAGINAS_TEXTO = [
    ("acerca", "acerca.html", f"{SITIO}/acerca.html", "acerca", "Acerca de",
     "Acerca de | Carestía",
     "Acerca de Carestía, índices del costo de vida en Chile."),
    ("contacto", "contacto.html", f"{SITIO}/contacto.html", "contacto", "Contacto",
     "Contacto | Carestía", "Contacto de Carestía."),
    ("terminos", "terminos.html", f"{SITIO}/terminos.html", "terminos",
     "Términos de uso", "Términos de uso | Carestía",
     "Términos de uso de carestia.cl."),
    ("privacidad", "privacidad.html", f"{SITIO}/privacidad.html", "privacidad",
     "Política de privacidad", "Política de privacidad | Carestía",
     "Política de privacidad de carestia.cl."),
    ("404", "404.html", None, "", "Página no encontrada",
     "Página no encontrada | Carestía", "Esta página no existe en carestia.cl."),
]


def generar_paginas_texto() -> None:
    for nombre, archivo, url, clave, titulo_def, title, desc in PAGINAS_TEXTO:
        titulo, cuerpo = cargar_texto(nombre)
        escribir_pagina(archivo, url, title, desc,
                        f"    <h1>{html.escape(titulo or titulo_def)}</h1>\n{cuerpo}",
                        actual=clave)


SITEMAP_URL = """  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
  </url>
"""


def generar_resumen() -> None:
    """resumen.json: endpoint liviano y estable con los 4 índices, para
    consumo externo (buscadores, agentes). Solo reempaqueta lo que ya viene
    calculado en indices.json; la variación semanal sale de las dos últimas
    semanas de la serie real. UTF-8 sin BOM, tildes literales."""
    indices = {}
    semana = None
    for code, d in DATA["indices"].items():
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
    resumen = {
        "generado": datetime.date.today().isoformat(),
        "semana": semana,
        "fuente": "Carestía",
        "url": "https://carestia.cl",
        "licencia_datos": "ODEPA (CC-BY), IPC Banco Central de Chile",
        "atribucion_requerida": True,
        "deslinde": "Información de consumo. No constituye asesoría "
                    "ni recomendación de inversión.",
        "frecuencia": "semanal (viernes)",
        "indices": indices,
    }
    with open("resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)


# páginas del sitio en el sitemap (el 404 no va). Van DESPUÉS de las fichas:
# salud.yml chequea la primera URL con /productos/ del sitemap y así sigue
# siendo una ficha
PAGINAS_SITEMAP = ["graficos.html", "productos/", "metodologia.html", "acerca.html",
                   "contacto.html", "terminos.html", "privacidad.html"]


def generar_sitemap(slugs: list) -> None:
    """Raíz + las URLs de producto + las páginas del sitio, todas con el
    lastmod del build."""
    lastmod = datetime.date.today().isoformat()
    locs = ["https://carestia.cl/"] + \
        [f"https://carestia.cl/productos/{s}.html" for s in slugs] + \
        [f"https://carestia.cl/{p}" for p in PAGINAS_SITEMAP]
    with open("sitemap.xml", "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for loc in locs:
            fh.write(SITEMAP_URL.format(loc=loc, lastmod=lastmod))
        fh.write('</urlset>\n')


# textos del dueño que aún no llegan completos: no se publica un sitio con
# páginas legales a medias (el workflow falla en "Generar sitio" y no hay
# deploy). Vista previa local, que no se publica: CARESTIA_BORRADOR=1
PENDIENTES = [n for n in TEXTOS if texto_pendiente(n)]
if PENDIENTES:
    if os.environ.get("CARESTIA_BORRADOR") != "1":
        raise SystemExit(
            "build_site.py: textos pendientes en textos/: "
            + ", ".join(f"{n}.md" for n in PENDIENTES)
            + ". No se genera el sitio hasta que estén completos.")
    print("BORRADOR: textos pendientes: " + ", ".join(PENDIENTES))

FICHAS = asignar_fichas(DATA.get("productos", {}))
SLUGS = slugs_de_datos(DATA.get("productos", {}), FICHAS)
CATALOGO = generar_catalogo(DATA.get("productos", {}), SLUGS)
UF = cargar_uf()
APP = generar_datos(SLUGS, CATALOGO, UF)

with open("graficos.html", "w", encoding="utf-8") as fh:
    fh.write(GRAFICOS_HTML.replace("__ICONO__", ICONO)
                          .replace("__FUENTES__", FUENTES)
                          .replace("__CSS_BASE__", CSS_BASE)
                          .replace("__CSS_CABECERA__", CSS_CABECERA)
                          .replace("__CSS_SITIO__", CSS_SITIO)
                          .replace("__GRUPOS__", json.dumps(GRUPO_TXT, ensure_ascii=False))
                          .replace("__NAV__", nav_sitio("indices"))
                          .replace("__PIE__", pie_sitio(graficos=True))
                          .replace("__TV_JS__", TV_JS)
                          .replace("__VER_TV__", _ver(FEED_JS))
                          .replace("__TV_CSS__", TV_CSS)
                          .replace("__VER_CSS__", _ver(tv_css()))
                          # la unidad: el selector, su línea y su JS
                          .replace("__SELECTOR_UNIDAD__", selector_unidad(APP["uf"]))
                          .replace("__LEYENDA__", leyenda_unidad(APP["uf"], ""))
                          .replace("__LEYENDA_MOVIL__", leyenda_unidad(APP["uf"], "mleg m-ind"))
                          .replace("__UNIDAD_REAL__", UNIDAD_TXT["real"])
                          .replace("__JS_UNIDAD__", JS_UNIDAD)
                          .replace("__UNIDAD_TXT__", _json(UNIDAD_TXT))
                          # "</" escapado: un label nunca puede cerrar el <script>
                          .replace("__DATA__", _json(APP).replace("</", "<\\/")))

generar_portada(CATALOGO, FICHAS)

with open("robots.txt", "w", encoding="utf-8") as fh:
    fh.write(ROBOTS)

generar_productos(FICHAS)
generar_indice_productos(FICHAS)
generar_metodologia()
generar_paginas_texto()
generar_sitemap(sorted(FICHAS))
generar_resumen()
generar_tradingview(APP, CATALOGO)

print(f"Listo: index.html + graficos.html + robots.txt + sitemap.xml + resumen.json + "
      f"{len(FICHAS)} páginas en productos/ + productos/index.html + "
      f"metodologia.html + {len(PAGINAS_TEXTO)} páginas institucionales + "
      f"datos/ ({len(DATA['indices'])} índices, "
      f"{len(DATA.get('productos', {}))} productos y catalogo.json)")
print(f"  index.html: {os.path.getsize('index.html'):,} bytes; "
      f"graficos.html: {os.path.getsize('graficos.html'):,} bytes; "
      f"catalogo.json: {os.path.getsize(os.path.join(DATOS, 'catalogo.json')):,} bytes")
for c, d in DATA["indices"].items():
    print(f"  {d['nombre']}: {d['veredicto']} (percentil {d['percentil']})")
if "productos" in DATA:
    print(f"  Productos: {len(DATA['productos'])} series")

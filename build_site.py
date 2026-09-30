"""
build_site.py - genera el sitio Carestía
========================================
Lee 'indices.json' (lo produce indices.py) y escribe 'index.html': un sitio
autocontenido con cinta ticker y una sola superficie: el hero es el único
lienzo de gráfico y las tabs lo cambian de MODO en el lugar (índices con
veredicto y línea/velas · Comparar productos en spaghetti · Arma tu
canasta), con una franja de contexto que acompaña a cada modo y footer
con atribución.

Identidad (tokens en CSS_BASE, iguales en todas las páginas): base neutra
con texto hueso; la brasa #e8743b solo vive en la í del wordmark y en la
línea de los índices oficiales; hueso es el color de las canastas de
usuario. El verde/ámbar/rojo del semáforo queda reservado al veredicto y a
las velas de los 4 índices. IBM Plex Sans para la interfaz y el texto, IBM
Plex Mono para etiquetas cortas en mayúsculas y Space Grotesk para el
wordmark y las cifras grandes.

La portada trae inline solo el primer pantallazo; las series completas van
a datos/ y se piden a demanda (ver generar_datos).

También escribe una ficha por producto (productos/{slug}.html), el listado
/productos/, /metodologia.html, las páginas institucionales y legales (con
los textos literales de textos/), robots.txt, sitemap.xml y resumen.json.
Todas las páginas comparten la navegación del encabezado y el pie.

Correr:
  python indices.py
  python build_site.py
  python -m http.server   (y abrir http://localhost:8000: la portada pide
                           datos/ por fetch, que no corre con file://)
"""

import datetime
import hashlib
import html
import json
import os
import re
import unicodedata

# las cantidades de /metodologia.html salen del mismo diccionario que usa el
# cálculo (nunca escritas a mano)
from indices import BASKETS

with open("indices.json", encoding="utf-8") as fh:
    DATA = json.load(fh)

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "101b8fafc10e4ae4b412859b124cb5ea"}'></script>
<style>
__CSS_BASE__

  /* ---- ticker ---- */
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
  #vista { opacity:1; transition:opacity .18s ease; }
  /* la barra de controles (~52px) sale del calc para que hero+barra sigan
     encuadrando la pantalla sin scroll */
  /* altura reservada por CSS antes de que Lightweight Charts monte, y en
     svh donde exista: 100vh cambia con la barra del navegador móvil y ese
     reflow se atribuía a los contenedores de chart (CLS) */
  .hero-wrap { position:relative; height:calc(100vh - 318px); min-height:320px;
    background:var(--bg); }
  @supports (height:100svh) {
    .hero-wrap { height:calc(100svh - 318px); } }
  /* sobre 640px la fila de navegación del sitio (33px, en el encabezado)
     también sale del calc: 272+33 y 368+33 */
  @media (min-width:760px) {
    .hero-wrap { height:calc(100vh - 305px); min-height:420px; }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 305px); } } }
  /* móvil: la franja bajo el lienzo (50px, ver .mstrip) y, bajo 641px, la
     segunda fila de tabs (+50px) salen del encuadre para que hero + barras
     sigan cerrando la pantalla sin scroll donde el alto alcance */
  @media (max-width:759px) {
    .hero-wrap { height:calc(100vh - 401px); }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 401px); } } }
  @media (max-width:640px) {
    .hero-wrap { height:calc(100vh - 419px); }
    @supports (height:100svh) {
      .hero-wrap { height:calc(100svh - 419px); } } }
  @media (max-width:759px) { .overlay .oname, .overlay .cstats, .overlay .caviso,
    .overlay .can-reg { max-width:calc(100vw - 160px); } }
  #chart, #pchart, #cchart { position:absolute; inset:0; }
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
  .cbar { display:flex; align-items:center; gap:14px; min-height:50px;
    padding:7px clamp(16px,3vw,32px); border-bottom:1px solid var(--line);
    overflow-x:auto; overflow-y:hidden; scrollbar-width:none;
    -webkit-overflow-scrolling:touch; }
  .cbar::-webkit-scrollbar { display:none; }
  .cbar-right { margin-left:auto; display:flex; align-items:center; gap:14px; }
  .cbar-right > * { flex:none; }
  .legend { display:none; flex-direction:column; align-items:flex-start; gap:4px;
    font:400 11px/1.5 var(--sans); color:var(--ash);
    max-width:min(40vw,440px); text-wrap:pretty; }
  @media (min-width:900px) { .legend { display:flex; } }
  .legend .sw { display:inline-block; width:16px; height:0; margin-right:6px;
    vertical-align:middle; }
  .vtoggle { display:flex; border:1px solid var(--line); background:var(--bg); }
  /* LÍNEA / VELAS son etiquetas cortas en mayúsculas (mono); los botones
     de texto normal (+ nominal, captura PNG) van en la tipografía de la
     interfaz */
  .vbtn { font:600 11px var(--mono); letter-spacing:.1em; padding:8px 14px;
    border:none; cursor:pointer; background:transparent; color:var(--ash); min-height:34px; }
  .vbtn + .vbtn { border-left:1px solid var(--line); }
  .vbtn.active { background:var(--bone); color:var(--bg); }
  .nomtoggle { border:1px solid var(--line); background:var(--bg);
    font:500 13px var(--sans); letter-spacing:0; }
  /* referencia de velas y pista de zoom: texto de ayuda dentro de la barra;
     bajo 760px se omiten para no alargar la fila de controles en móvil */
  .ref { display:none; max-width:300px; text-wrap:balance;
    font:400 11px/1.5 var(--sans); color:var(--dim); }
  .zoomhint { display:none; max-width:280px; text-wrap:balance;
    font:400 11px/1.5 var(--sans); color:var(--ash); }
  @media (min-width:760px) { .ref, .zoomhint { display:block; } }
  /* ---- franja móvil bajo el lienzo: leyenda compacta + pista táctil ---- */
  /* bajo 760px ni la leyenda completa (≥900px) ni la pista de zoom de la
     barra (≥760px) existen: esta franja trae ambas en versión corta, fuera
     del lienzo para no taparlo. Primera línea: solo swatch + etiqueta corta
     (la frase explicativa completa queda en desktop); segunda línea: la
     pista de gestos. En productos/canasta la leyenda (m-ind) se apaga y el
     min-height mantiene la franja estable; altura fija reservada desde el
     primer paint (CLS) */
  .mstrip { display:none; }
  @media (max-width:759px) {
    .mstrip { display:flex; flex-wrap:wrap; align-content:flex-start;
      align-items:center; gap:4px 14px; min-height:66px;
      padding:7px clamp(16px,3vw,32px);
      font:400 11px/16px var(--sans); color:var(--ash); }
    .mstrip .sw { display:inline-block; width:16px; height:0; margin-right:6px;
      vertical-align:middle; }
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
      <div class="wordmark"><span>CAREST<span class="i">Í</span>A</span></div>
      <div class="tagline">Índices del costo de vida en Chile</div>
    </div>
    <div class="semana">Semana del <span id="fecha"></span>. <span>Se actualiza los viernes.</span></div>
    __NAV__
  </header>

  <nav class="tabs" id="tabs" aria-label="Índices y herramientas"></nav>

  <div class="cbar" id="cbar">
    <div class="legend m-ind">
      <span><span class="sw" style="border-top:2px solid var(--ember)"></span>En pesos de hoy: lo que costaría hoy ese precio, sumando la inflación acumulada. Es parecido a medirlo en UF.</span>
      <span id="leg-nom"><span class="sw" style="border-top:1px solid var(--ash)"></span>Nominal: el precio de la boleta de ese día</span>
    </div>
    <div class="cbar-right">
      <span class="zoomhint">Para acercar, arrastra el eje de los años o el de los precios. En el celular, usa dos dedos.</span>
      <span class="ref m-ind" id="ref-velas"></span>
      <button class="vbtn nomtoggle m-ind" id="v-nominal">+ nominal</button>
      <div class="vtoggle m-ind">
        <button class="vbtn active" id="v-linea">LÍNEA</button>
        <button class="vbtn" id="v-velas">VELAS</button>
      </div>
      <button class="vbtn nomtoggle" id="shot">captura PNG</button>
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
          <div class="oprice" id="oprice"></div>
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
        <div class="onote">Cambio del precio real, en porcentaje</div>
      </div>
      <div class="overlay m-can">
        <div class="oname">ARMA TU CANASTA <span>Y COMPÁRTELA</span></div>
        <div class="orow"><div class="oprice" id="ccosto"></div></div>
        <div class="cstats" id="cstats"></div>
        <div class="cstats ctemporada" id="ctemporada"></div>
        <div class="caviso" id="caviso"></div>
        <div class="can-reg">Esta canasta la armaste tú con datos de ODEPA. No es un índice de Carestía.</div>
      </div>
      <div class="carga" id="carga" role="status" hidden>
        <span id="carga-txt"></span>
        <button class="vbtn nomtoggle" id="carga-reintentar">Reintentar</button>
      </div>
      <div class="tooltip" id="tooltip">
        <div class="tt-d" id="tt-d"></div>
        <div class="tt-r"><span id="tt-r"></span> <small>pesos de hoy</small></div>
        <div class="tt-n" id="tt-n"></div>
      </div>
    </section>

    <!-- franja móvil (<760px): leyenda compacta del modo índices y pista de
         gestos táctiles del lienzo; en desktop no existe -->
    <div class="mstrip">
      <span class="mleg m-ind"><span class="sw" style="border-top:2px solid var(--ember)"></span>En pesos de hoy</span>
      <span class="mleg m-ind" id="mleg-nom"><span class="sw" style="border-top:1px solid var(--ash)"></span>Nominal</span>
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
  // pide los productos que falten y llama a 'luego' cuando llegaron todos
  function pedirProductos(keys, luego) {
    const faltan = keys.filter(k => PRODS[k] && !PRODS[k].real);
    if (!faltan.length) return;
    Promise.all(faltan.map(cargarProducto)).then(luego, () => {}).finally(pintarCarga);
    pintarCarga();
  }
  const fmt = v => '$' + Math.round(v).toLocaleString('es-CL');
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
  // opciones comunes de los tres lienzos: la rueda y el swipe vertical
  // quedan para la página; el zoom sigue disponible arrastrando los ejes y
  // con dos dedos en táctil. El crosshair va en hueso tenue
  function opcionesChart(extra) {
    return Object.assign({
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: COL.ash,
        fontFamily: COL.sans },
      grid: { vertLines: { color: COL.grid }, horzLines: { color: COL.grid } },
      rightPriceScale: { borderColor: COL.line },
      timeScale: { borderColor: COL.line },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, vertTouchDrag: false,
        horzTouchDrag: true, pressedMouseMove: true },
      crosshair: { mode: 0,
        vertLine: { color: COL.cruz, labelBackgroundColor: COL.line },
        horzLine: { color: COL.cruz, labelBackgroundColor: COL.line } },
    }, extra);
  }

  let cur = CODES[0], vista = 'linea', nomVisible = false;
  let chart, sNom, sReal, sCandle, pchart;
  let realMap = new Map(), nomMap = new Map();

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
  function chartActivo() {
    return modo === 'productos' ? pchart : modo === 'canasta' ? cchart : chart;
  }
  // navegación del sitio: en la portada, Índices / Comparar / Arma tu
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

  /* ---------- hero chart ---------- */
  function initChart() {
    const el = document.getElementById('chart');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos (revisa la conexión).</div>';
      return;
    }
    chart = LightweightCharts.createChart(el,
      opcionesChart({ localization: { priceFormatter: fmt } }));
    sNom = chart.addLineSeries({ color: COL.ash, lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false, visible: false });
    // la línea de los índices oficiales: el único lugar de la brasa en los gráficos
    sReal = chart.addLineSeries({ color: COL.ember, lineWidth: 2, priceLineVisible: false });
    // C2: convención estándar de trading, verde sube y rojo baja
    sCandle = chart.addCandlestickSeries({
      upColor: COL.verde, downColor: COL.rojo, borderVisible: false,
      wickUpColor: COL.verde, wickDownColor: COL.rojo, visible: false });
    chart.subscribeCrosshairMove(onCrosshair);
  }

  const tooltip = document.getElementById('tooltip');
  function onCrosshair(param) {
    const el = document.getElementById('chart');
    if (!param.time || !param.point || param.point.x < 0) {
      tooltip.style.display = 'none';
      return;
    }
    const t = tstr(param.time);
    const rv = realMap.get(t), nv = nomMap.get(t);
    if (rv == null) { tooltip.style.display = 'none'; return; }
    document.getElementById('tt-d').textContent = ddmmyyyy(t);
    document.getElementById('tt-r').textContent = fmt(rv);
    document.getElementById('tt-n').textContent = (nv != null ? fmt(nv) : '·') + ' nominal';
    tooltip.style.display = 'block';
    const w = tooltip.offsetWidth, cw = el.clientWidth;
    let x = param.point.x + 14;
    if (x + w > cw - 8) x = param.point.x - w - 14;
    tooltip.style.left = Math.max(8, x) + 'px';
    tooltip.style.top = Math.min(param.point.y + 14, el.clientHeight - 80) + 'px';
  }

  function aplicarVista() {
    if (!chart) return;
    const linea = vista === 'linea';
    sNom.applyOptions({ visible: linea && nomVisible });
    sReal.applyOptions({ visible: linea });
    sCandle.applyOptions({ visible: !linea });
    document.getElementById('v-linea').classList.toggle('active', linea);
    document.getElementById('v-velas').classList.toggle('active', !linea);
    const nb = document.getElementById('v-nominal');
    nb.classList.toggle('active', nomVisible);
    nb.style.visibility = linea ? 'visible' : 'hidden';   // solo aplica a la vista Línea
    document.getElementById('leg-nom').style.opacity = nomVisible ? '' : '.35';
    // la leyenda compacta móvil acompaña el mismo atenuado
    document.getElementById('mleg-nom').style.opacity = nomVisible ? '' : '.35';
    document.getElementById('ref-velas').textContent =
      linea ? '' : 'Velas semanales. La mecha va del precio más bajo al más alto que ODEPA encontró entre los locales encuestados.';
    chart.timeScale().fitContent();
  }
  document.getElementById('v-linea').onclick = () => { vista = 'linea'; aplicarVista(); };
  document.getElementById('v-velas').onclick = () => { vista = 'velas'; aplicarVista(); };
  document.getElementById('v-nominal').onclick = () => { nomVisible = !nomVisible; aplicarVista(); };

  /* ---------- count-up del precio (~600ms) ---------- */
  let lastPrice = 0;
  function countUp(el, to) {
    if (reduced) { el.textContent = fmt(to); lastPrice = to; return; }
    const from = lastPrice, t0 = performance.now();
    (function step(t) {
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
  const fmtQty = q => String(q).replace('.', ',');
  function aplicar(code) {
    const d = INDICES[code];
    document.documentElement.style.setProperty('--verdict', d.color);
    document.getElementById('fecha').textContent = d.fecha;
    document.getElementById('oname').textContent = d.nombre.replace(/^Índice /i, '');
    document.getElementById('osub').textContent = d.subtitulo;
    countUp(document.getElementById('oprice'), d.costo_real);
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
    const d = INDICES[code];
    if (!d.real) {
      realMap = new Map(); nomMap = new Map();
      tooltip.style.display = 'none';
      if (chart) { sNom.setData([]); sReal.setData([]); sCandle.setData([]); }
      cargarIndice(code).then(() => { if (cur === code) pintarSerie(code); }, () => {})
        .finally(pintarCarga);
      pintarCarga();
      return;
    }
    realMap = new Map(d.real.map(p => [p.time, p.value]));
    nomMap = new Map(d.nominal.map(p => [p.time, p.value]));
    if (chart) {
      // si el usuario arrastró el eje de precios, autoScale quedó apagado
      // y la serie nueva caería fuera del encuadre
      chart.priceScale('right').applyOptions({ autoScale: true });
      sNom.setData(d.nominal); sReal.setData(d.real);
      sCandle.setData(d.velas || []);
      aplicarVista();
    }
    pintarCarga();
  }

  /* ---------- estado de carga del lienzo ---------- */
  // mientras falte alguna serie del modo activo, "Cargando datos..." sobre
  // el lienzo; si un pedido falló, el aviso con un botón para reintentar
  const cargaEl = document.getElementById('carga');
  function faltantes() {
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
  // C3: paleta propia (tokens --cmp1 a --cmp8), sin azules, sin los colores
  // del semáforo ni la brasa; 8 tonos que se distinguen también por claridad
  const PALETTE = [1, 2, 3, 4, 5, 6, 7, 8].map(i => tok('cmp' + i));
  const PKEYS = Object.keys(PRODS);
  const colorOf = k => PALETTE[PKEYS.indexOf(k) % PALETTE.length];

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
  ['asado_de_tira', 'palta', 'huevo_color'].forEach(w => {
    if (PRODS[w]) { psel.add(w); return; }
    const alt = PKEYS.find(k => k.indexOf(w.split('_')[0]) === 0);
    if (alt) psel.add(alt);
  });
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

  function syncProductos() {
    if (!pchart) return;
    // las series que falten se piden solo con Comparar a la vista; al
    // llegar todas, vuelve a sincronizar
    if (modo === 'productos') pedirProductos([...psel], syncProductos);
    PKEYS.forEach(k => {
      const on = psel.has(k);
      if (on && !PRODS[k].real) return;   // aún no llega: se agrega al llegar
      if (on && !pseries.has(k)) {
        const s = pchart.addLineSeries({ color: colorOf(k), lineWidth: 2,
          priceLineVisible: false, lastValueVisible: false });
        s.setData(PRODS[k].gaps);   // con huecos donde no hubo precio
        pseries.set(k, s);
      } else if (!on && pseries.has(k)) {
        pchart.removeSeries(pseries.get(k));
        pseries.delete(k);
      }
    });
    pchart.priceScale('right').applyOptions({ autoScale: true });
    pchart.timeScale().fitContent();
    pintarCarga();
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
      const paint = () => {
        const on = psel.has(k);
        b.classList.toggle('active', on);
        dot.style.background = on ? colorOf(k) : 'var(--dim)';
        b.style.borderColor = on ? colorOf(k) : 'var(--line)';
      };
      paint();
      b.onclick = () => {
        if (psel.has(k)) psel.delete(k); else psel.add(k);
        paint(); syncProductos();
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
    const ch = chartActivo();
    if (!ch) return;
    try { await datosDelModo(); } catch (e) { pintarCarga(); return; }
    // dos cuadros: el lienzo alcanza a dibujar lo que acaba de llegar
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
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
    const shot = ch.takeScreenshot();
    if (!shot || !shot.width) return;
    // lienzo de salida legible para compartir: nunca menos de 1200px de
    // ancho; takeScreenshot ya viene a devicePixelRatio y si aun así es
    // chico (móvil a DPR bajo) se escala el canvas
    const W = Math.max(1200, Math.round(shot.width));
    const pad = Math.round(W * 0.04);
    const chartW = W - pad * 2;
    const chartH = Math.round(shot.height * chartW / shot.width);
    // bajo el costo, la composición: en canasta "{label} {cantidad} {unidad}"
    // y en productos los elegidos del spaghetti; una línea o dos si no cabe,
    // el encabezado crece lo que ellas ocupen
    const compSize = Math.round(W * 0.013), compAlto = Math.round(compSize * 1.5);
    const compLineas = [];
    let partes = [];
    if (modo === 'canasta' && canasta.size) {
      partes = [...canasta.entries()].filter(([k]) => PRODS[k])
        .map(([k, q]) => PRODS[k].label + ' ' + fmtCant(q, PRODS[k].unidad));
    } else if (modo === 'productos') {
      partes = PKEYS.filter(k => psel.has(k)).map(k => PRODS[k].label);
    }
    if (partes.length) {
      const mctx = document.createElement('canvas').getContext('2d');
      mctx.font = '400 ' + compSize + 'px "IBM Plex Sans", sans-serif';
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
    const compH = compLineas.length * compAlto;
    const headH = Math.round(W * 0.13) + compH, footH = Math.round(W * 0.07);
    const H = headH + chartH + footH;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, W, H);
    // contexto arriba a la izquierda: qué es, cuánto vale, de cuándo;
    // productos no tiene un costo único y lleva su etiqueta en vez del monto
    let titulo, precio,
      precioFont = '700 ' + Math.round(W * 0.037) + 'px "Space Grotesk", sans-serif';
    if (modo === 'canasta') {
      titulo = 'TU CANASTA';
      precio = document.getElementById('ccosto').textContent || '·';
    } else if (modo === 'productos') {
      titulo = 'PRODUCTOS';
      precio = 'Cambio del precio real, en porcentaje';
      precioFont = '400 ' + Math.round(W * 0.02) + 'px "IBM Plex Sans", sans-serif';
    } else {
      const d = INDICES[cur];
      titulo = d.nombre.replace(/^Índice /i, '').toUpperCase();
      precio = fmt(d.costo_real);
    }
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
    ctx.font = '400 ' + Math.round(W * 0.012) + 'px "IBM Plex Sans", sans-serif';
    ctx.fillText('semana del ' + fecha, pad, Math.round(W * 0.098) + compH);
    ctx.drawImage(shot, pad, headH, chartW, chartH);
    marcaDeAgua(ctx, W - pad, H - Math.round(footH * 0.35), Math.round(W * 0.02));
    const nombre = 'carestia_' + (modo === 'indices' ? cur : modo) + '_' +
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
    buildTicker();
    buildTabs();
    initChart();
    render(CODES[0], true);
    initPChart();
    buildProductos();
    syncProductos();
    buildCanasta();
    activarDeepLink();
  });
</script>
</body>
</html>
"""

ROBOTS = """User-agent: *
Allow: /

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
NAV = [   # (clave, texto, href, modo de la portada que abre en el lugar)
    ("indices", "Índices", f"{SITIO}/", "indices"),
    ("productos", "Productos", f"{SITIO}/productos/", None),
    # deep links que ya existen en la portada (#comparar = alias de #productos)
    ("comparar", "Comparar", f"{SITIO}/#comparar", "productos"),
    ("canasta", "Arma tu canasta", f"{SITIO}/#canasta", "canasta"),
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
# para etiquetas cortas en mayúsculas y Space Grotesk solo para el wordmark y
# las cifras grandes.
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
    /* Comparar productos: ocho tonos sin azules ni celestes, cada uno con
       su propia claridad (L de 0,56 a 0,87 en OKLCH) para distinguirse
       también sin color; entre vecinos, diferencia de 14 o más (OKLab x100)
       incluso con protanopía o deuteranopía simuladas. El orden deja muy
       distintos los tres productos que Comparar muestra al entrar */
    --cmp1:#717c16; --cmp2:#b897f0; --cmp3:#b45ea1; --cmp4:#f29db1;
    --cmp5:#d1e25a; --cmp6:#d37daa; --cmp7:#d9b8fe; --cmp8:#9977e4;
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


def pie_sitio(actual: str = "") -> str:
    """Pie común: links institucionales y legales, atribución ODEPA CC-BY,
    deslinde, razón social y el aviso de atribución de Lightweight Charts
    tal cual su NOTICE, con link directo a tradingview.com (sin rel)."""
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
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
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
  main { max-width:980px; margin:0 auto;
    padding:clamp(20px,4vw,36px) clamp(16px,3vw,32px) clamp(28px,4vw,44px); }
  .miga { font:500 10px var(--mono); letter-spacing:.16em;
    color:var(--ash); text-transform:uppercase; }
  h1 { font:600 clamp(26px,5vw,40px)/1.15 var(--sans);
    letter-spacing:-.005em; margin-top:6px; }
  .orow { display:flex; align-items:baseline; gap:clamp(10px,2vw,18px);
    flex-wrap:wrap; margin-top:14px; min-height:52px; }
  .oprice { font:700 clamp(38px,7vw,64px)/1 var(--display);
    letter-spacing:-.01em; color:var(--bone); }
  .ouni { font:400 13px var(--sans); color:var(--ash); }
  .odelta { font:600 15px var(--sans); color:var(--ash); } /* deltas SIEMPRE en secundario */
  .odelta small { font:400 12px var(--sans); color:var(--dim); }
  .pct { font:400 15px/1.6 var(--sans); color:var(--bone);
    margin-top:12px; text-wrap:pretty; }
  /* altura reservada por CSS ANTES de que Lightweight Charts monte: la
     página no salta al renderizar (svh: estable frente a la barra móvil) */
  #grafico { position:relative; height:clamp(300px,52vh,480px);
    height:clamp(300px,52svh,480px); margin-top:22px; }
  .fecha { font:500 12px var(--sans); color:var(--ash); margin-top:14px; }
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
    <div class="miga">Precio real en Chile, en pesos de hoy</div>
    <h1>__LABEL__</h1>
    <div class="orow">
      <div class="oprice">__PRECIO__</div>
      <div class="ouni">por __UNI_TXT__, en pesos de hoy</div>
      <div class="odelta">__DELTA__ <small>sem.</small></div>
    </div>
    <p class="pct">__PCT_LINEA__</p>
    <div id="grafico"></div>
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
      <a href="https://carestia.cl/#canasta=__CANASTA__">ármalo en una canasta →</a>
    </nav>
  </main>

__PIE__

<script>
  // serie compacta del producto: t0 + valores semanales consecutivos, null en
  // semanas sin dato (estacionales); se expande a puntos con huecos visibles
  const T0 = '__T0__';
  const V = __V__;
  const DIA = 864e5, base = Date.parse(T0 + 'T00:00:00Z');
  const serie = V.map((v, i) => {
    const time = new Date(base + i * 7 * DIA).toISOString().slice(0, 10);
    return v == null ? { time } : { time, value: v };
  });
  const fmt = v => '$' + Math.round(v).toLocaleString('es-CL');
  window.addEventListener('load', () => {
    const el = document.getElementById('grafico');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos (revisa la conexión).</div>';
      return;
    }
    // colores desde los tokens de :root
    const vars = getComputedStyle(document.documentElement);
    const tok = n => vars.getPropertyValue('--' + n).trim();
    const chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: tok('ash'),
        fontFamily: tok('sans') },
      grid: { vertLines: { color: tok('grid') }, horzLines: { color: tok('grid') } },
      rightPriceScale: { borderColor: tok('line') },
      timeScale: { borderColor: tok('line') },
      localization: { priceFormatter: fmt },
      // misma política de gestos del sitio: la rueda y el swipe vertical
      // quedan para la página; zoom en los ejes y pinch en táctil
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, vertTouchDrag: false,
        horzTouchDrag: true, pressedMouseMove: true },
      crosshair: { mode: 0,
        vertLine: { color: tok('cruz'), labelBackgroundColor: tok('line') },
        horzLine: { color: tok('cruz'), labelBackgroundColor: tok('line') } },
    });
    // un producto no es un índice oficial: su línea va en hueso (la brasa
    // queda para los índices)
    chart.addLineSeries({ color: tok('bone'), lineWidth: 2, priceLineVisible: false })
      .setData(serie);
    chart.timeScale().fitContent();
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
# La portada lleva inline solo el primer pantallazo: el resumen de los 4
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
    """Lo que la portada muestra de un índice sin su serie: el overlay, el
    ticker, la estacionalidad y los componentes. La variación semanal es la
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


def generar_datos(slugs: dict) -> dict:
    """Escribe datos/ y devuelve lo que va inline en la portada."""
    indices = DATA["indices"]
    prods = DATA.get("productos", {})
    series = {code: compactar_indice(code, d) for code, d in indices.items()}
    for code, d in indices.items():
        completo = {k: v for k, v in d.items() if k not in SERIES_INDICE}
        completo["serie"] = series[code]
        escribir_json(os.path.join(DATOS, "indices", f"{code}.json"), completo)
    for clave, p in prods.items():
        escribir_json(os.path.join(DATOS, "productos", f"{slugs[clave]}.json"), p)
    escribir_json(os.path.join(DATOS, "catalogo.json"), generar_catalogo(prods, slugs))
    primero = next(iter(indices))
    return {
        "indices": {code: resumen_indice(d) for code, d in indices.items()},
        "series": {primero: series[primero]},
        "productos": {clave: {"label": p["label"], "grupo": p.get("grupo") or "Otros",
                              "unidad": p["unidad"], "slug": slugs[clave]}
                      for clave, p in prods.items()},
        "rango": rango_productos(prods),
        # versión de los datos: los pedidos a datos/ la llevan en la URL para
        # que el navegador no mezcle archivos de dos builds distintos
        "ver": hashlib.sha1(_json(DATA).encode("utf-8")).hexdigest()[:10],
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
        # HTML ya renderizado (seccion_otros escapa labels y grupo), no
        # se vuelve a escapar aquí
        ("__OTROS__", otros_html),
        # identidad, navegación y pie comunes; la ficha vive bajo /productos/
        ("__ICONO__", ICONO),
        ("__FUENTES__", FUENTES),
        ("__CSS_BASE__", CSS_BASE),
        ("__CSS_SITIO__", CSS_SITIO),
        ("__NAV__", nav_sitio("productos", exacto=False)),
        ("__PIE__", pie_sitio()),
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
PAGINAS_SITEMAP = ["productos/", "metodologia.html", "acerca.html",
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
PORTADA = generar_datos(slugs_de_datos(DATA.get("productos", {}), FICHAS))

with open("index.html", "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("__ICONO__", ICONO)
                 .replace("__FUENTES__", FUENTES)
                 .replace("__CSS_BASE__", CSS_BASE)
                 .replace("__CSS_SITIO__", CSS_SITIO)
                 .replace("__GRUPOS__", json.dumps(GRUPO_TXT, ensure_ascii=False))
                 .replace("__NAV__", nav_sitio("indices"))
                 .replace("__PIE__", pie_sitio())
                 # "</" escapado: un label nunca puede cerrar el <script>
                 .replace("__DATA__", _json(PORTADA).replace("</", "<\\/")))

with open("robots.txt", "w", encoding="utf-8") as fh:
    fh.write(ROBOTS)

generar_productos(FICHAS)
generar_indice_productos(FICHAS)
generar_metodologia()
generar_paginas_texto()
generar_sitemap(sorted(FICHAS))
generar_resumen()

print(f"Listo: index.html + robots.txt + sitemap.xml + resumen.json + "
      f"{len(FICHAS)} páginas en productos/ + productos/index.html + "
      f"metodologia.html + {len(PAGINAS_TEXTO)} páginas institucionales + "
      f"datos/ ({len(DATA['indices'])} índices, "
      f"{len(DATA.get('productos', {}))} productos y catalogo.json)")
print(f"  index.html: {os.path.getsize('index.html'):,} bytes; "
      f"catalogo.json: {os.path.getsize(os.path.join(DATOS, 'catalogo.json')):,} bytes")
for c, d in DATA["indices"].items():
    print(f"  {d['nombre']}: {d['veredicto']} (percentil {d['percentil']})")
if "productos" in DATA:
    print(f"  Productos: {len(DATA['productos'])} series")

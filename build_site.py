"""
build_site.py - genera el sitio Carestía
========================================
Lee 'indices.json' (lo produce indices.py) y escribe 'index.html': un sitio
autocontenido con cinta ticker, hero con veredicto en overlay, línea/velas,
franja de contexto (estacionalidad + componentes), vista Productos
(spaghetti multi-serie en variación real) y footer con atribución.

Identidad: paleta 2c "Hueso protagonista", hueso/ceniza sobre carbón; la
brasa #e8743b solo vive en el veredicto, en la í del wordmark y en la línea
"en pesos de hoy" (con su crosshair). El verde/rojo/ámbar del semáforo
queda reservado al veredicto y a las velas.

Correr:
  python indices.py
  python build_site.py
  open index.html
"""

import json

with open("indices.json", encoding="utf-8") as fh:
    DATA = json.load(fh)

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Carestía: Índices del costo de vida · Chile</title>
<meta name="description" content="Carestía: índices del costo de vida chileno en pesos de hoy, con datos semanales de ODEPA deflactados por IPC.">
<meta property="og:title" content="Carestía · Índices del costo de vida en Chile">
<meta property="og:description" content="Cuánto cuesta la vida cotidiana en Chile, en pesos de hoy. Índices propios sobre datos públicos de ODEPA, actualizados cada viernes.">
<meta property="og:image" content="https://pitvox.github.io/costo-de-vida-cl/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2317120e'/%3E%3Crect x='28.5' y='28' width='7' height='24' rx='2' fill='%23e4dacc'/%3E%3Cpath d='M29.5 22L39 13.5' stroke='%23e8743b' stroke-width='7' stroke-linecap='round' fill='none'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root {
    --bg:#17120e; --bg2:#120e0a; --panel:#1a140f;
    --line:#2a231c; --grid:#221b14;
    --bone:#e4dacc; --ash:#8b8276; --dim:#5a5348;
    --ember:#e8743b; --verdict:#e0552f;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  html { scroll-behavior:smooth; }
  body { background:var(--bg); color:var(--bone);
    font-family:"IBM Plex Mono",monospace; min-height:100vh; }
  button { font-family:inherit; }

  /* ---- ticker ---- */
  .ticker { position:sticky; top:0; z-index:50; display:flex; align-items:stretch;
    background:var(--bg2); border-bottom:1px solid var(--line); min-height:44px; }
  .ticker .tag { display:none; align-items:center; padding:0 18px;
    border-right:1px solid var(--line); font:600 10px "IBM Plex Mono",monospace;
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
  .titem:hover { background:#1f1913; }
  .titem .tn { font:600 12px "Space Grotesk",sans-serif; letter-spacing:.1em; color:var(--bone); }
  .titem .tp { font:500 12px "IBM Plex Mono",monospace;
    font-variant-numeric:tabular-nums; color:var(--bone); }
  .titem .td { font:500 11px "IBM Plex Mono",monospace;
    font-variant-numeric:tabular-nums; color:var(--ash); } /* deltas SIEMPRE en ceniza */
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
  .wordmark { font:700 clamp(20px,4vw,26px) "Space Grotesk",sans-serif;
    letter-spacing:.06em; color:var(--bone); display:flex; align-items:baseline; }
  /* í-brasa: la Í del wordmark es la I del tipo más el acento agudo del
     propio tipo en brasa. El span superpuesto pinta una Í completa y el
     clip-path deja visible solo el acento; a tamaño header el glow queda
     sutil y en móvil (chico) se apaga y la tilde va plana en brasa */
  .wordmark .i { position:relative; display:inline-block; }
  .wordmark .i .tilde { position:absolute; left:0; top:0; pointer-events:none;
    color:#e8743b; clip-path:inset(0 0 72% 0); }
  @media (min-width:760px) {
    .wordmark .i .tilde { color:#ff9455; text-shadow:0 0 8px #e8743b; }
  }
  .tagline { font:400 12px "IBM Plex Mono",monospace; color:var(--ash); letter-spacing:.04em; }
  .semana { font:500 11px "IBM Plex Mono",monospace; color:var(--ash); letter-spacing:.08em;
    text-transform:uppercase; }
  .semana span { color:var(--dim); }
  /* ---- tabs de índice ---- */
  .tabs { display:flex; gap:8px; padding:12px clamp(16px,3vw,32px);
    border-bottom:1px solid var(--line); overflow-x:auto; overflow-y:hidden;
    scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .tabs::-webkit-scrollbar { display:none; }
  .tab { flex:none; font:600 11px "IBM Plex Mono",monospace; letter-spacing:.1em;
    padding:8px 16px; min-height:34px; cursor:pointer; white-space:nowrap;
    background:transparent; border:1px solid var(--line); border-radius:999px;
    color:var(--ash); }
  .tab:hover { background:#1f1913; }
  .tab.active { background:var(--bone); border-color:var(--bone); color:#17120e; }
  /* separador fino entre los índices y la pill de sección Productos */
  .tab-sep { flex:none; width:1px; align-self:stretch; background:var(--line);
    margin:0 4px; }

  @keyframes car-pulse {
    0%,100% { box-shadow:0 0 0 0 rgba(232,116,59,.55); }
    50% { box-shadow:0 0 14px 3px rgba(232,116,59,.25); }
  }
  @media (prefers-reduced-motion: reduce) {
    * { animation:none !important; }
    html { scroll-behavior:auto; }
  }

  /* ---- hero ---- */
  #vista { opacity:1; transition:opacity .18s ease; }
  /* el hero termina ~56px antes del borde inferior (descontando ticker,
     header y tabs): el título de la sección siguiente asoma al cargar */
  .hero-wrap { position:relative; height:calc(100vh - 266px); min-height:320px;
    background:var(--bg); scroll-margin-top:52px; }
  @media (min-width:760px) {
    .hero-wrap { height:calc(100vh - 220px); min-height:420px; } }
  @media (max-width:759px) { .overlay .oname { max-width:calc(100vw - 160px); } }
  #chart { position:absolute; inset:0; }
  .overlay { position:absolute; left:clamp(12px,2.5vw,32px); top:clamp(12px,2.5vw,26px);
    pointer-events:none; z-index:5; max-width:88%; }
  .overlay .oname { font:500 clamp(10px,1.4vw,12px) "IBM Plex Mono",monospace;
    letter-spacing:.16em; color:var(--ash); text-transform:uppercase; }
  .overlay .oname span { color:var(--dim); text-transform:none; }
  .orow { display:flex; align-items:baseline; gap:clamp(8px,1.5vw,16px);
    margin-top:4px; flex-wrap:wrap; }
  .oprice { font:700 clamp(34px,6vw,68px)/1 "Space Grotesk",sans-serif;
    font-variant-numeric:tabular-nums; letter-spacing:-.01em; color:var(--bone); }
  .odelta { font:600 clamp(12px,1.6vw,18px) "IBM Plex Mono",monospace;
    font-variant-numeric:tabular-nums; color:var(--ash); }
  .odelta small { font:400 11px "IBM Plex Mono",monospace; color:var(--dim); }
  .overd { display:flex; align-items:center; gap:12px; margin-top:12px; flex-wrap:wrap; }
  .badge { font:700 clamp(11px,1.4vw,13px) "Space Grotesk",sans-serif; letter-spacing:.14em;
    padding:5px 12px; background:var(--verdict); color:var(--bg);
    animation:car-pulse 2.4s ease-in-out infinite; }
  .opct, .ovs { font:400 clamp(10px,1.3vw,12px) "IBM Plex Mono",monospace; color:var(--ash); }
  .ovs { margin-top:8px; }
  .controls { position:absolute; right:clamp(10px,2vw,76px); top:clamp(10px,2vw,26px);
    display:flex; align-items:center; gap:20px; z-index:6; }
  @media (max-width:759px) {
    .controls { flex-direction:column; align-items:flex-end; gap:8px; }
  }
  .legend { display:none; flex-direction:column; align-items:flex-start; gap:4px;
    font:400 10px/1.5 "IBM Plex Mono",monospace; color:var(--ash);
    max-width:min(44vw,420px); text-wrap:pretty; }
  @media (min-width:900px) { .legend { display:flex; } }
  .legend .sw { display:inline-block; width:16px; height:0; margin-right:6px;
    vertical-align:middle; }
  .vtoggle { display:flex; border:1px solid var(--line); background:var(--bg); }
  .vbtn { font:600 11px "IBM Plex Mono",monospace; letter-spacing:.1em; padding:8px 14px;
    border:none; cursor:pointer; background:transparent; color:var(--ash); min-height:34px; }
  .vbtn + .vbtn { border-left:1px solid var(--line); }
  .vbtn.active { background:var(--bone); color:var(--bg); }
  .nomtoggle { border:1px solid var(--line); background:var(--bg); }
  /* la referencia de velas y la pista de zoom viven bajo los controles;
     en móvil el hero ya va cargado (overlay + controles apilados +
     chevron) y la referencia se superpondría al overlay: ambas se omiten */
  .ref { display:none; position:absolute; right:clamp(10px,2vw,76px);
    top:calc(clamp(10px,2vw,26px) + 42px);
    font:400 10px "IBM Plex Mono",monospace; color:var(--dim); z-index:6; }
  .zoomhint { display:none; position:absolute; right:clamp(10px,2vw,76px);
    top:calc(clamp(10px,2vw,26px) + 64px);
    font:400 10px "IBM Plex Mono",monospace; color:var(--ash); z-index:6; }
  @media (min-width:760px) { .ref, .zoomhint { display:block; } }
  .scroll-cue { position:absolute; left:50%; bottom:8px; transform:translateX(-50%);
    z-index:5; pointer-events:none; color:var(--ash);
    font:400 20px/1 "Space Grotesk",sans-serif;
    animation:car-cue 2.2s ease-in-out infinite; transition:opacity .5s ease; }
  .scroll-cue.oculto { opacity:0; }
  @keyframes car-cue {
    0%,100% { transform:translate(-50%,0); }
    50% { transform:translate(-50%,7px); }
  }
  .tooltip { position:absolute; display:none; z-index:7; pointer-events:none;
    background:#0f0c09; border:1px solid var(--line); padding:8px 12px; white-space:nowrap; }
  .tooltip .tt-d { font:500 10px "IBM Plex Mono",monospace; letter-spacing:.1em; color:var(--ash); }
  .tooltip .tt-r { font:600 15px "IBM Plex Mono",monospace;
    font-variant-numeric:tabular-nums; color:var(--bone); margin-top:2px; }
  .tooltip .tt-r small { font:400 10px "IBM Plex Mono",monospace; color:var(--ash); }
  .tooltip .tt-n { font:400 11px "IBM Plex Mono",monospace;
    font-variant-numeric:tabular-nums; color:var(--ash); }

  /* ---- franja de contexto ---- */
  .contexto { display:grid; grid-template-columns:1fr; border-top:1px solid var(--line); }
  @media (min-width:900px) { .contexto { grid-template-columns:480px 1fr; } }
  .ctx-box { padding:clamp(16px,3vw,24px) clamp(16px,3vw,32px); }
  @media (min-width:900px) { .ctx-box + .ctx-box { border-left:1px solid var(--line); } }
  @media (max-width:899px) { .ctx-box + .ctx-box { border-top:1px solid var(--line); } }
  .ctx-h { font:600 11px "IBM Plex Mono",monospace; letter-spacing:.16em; color:var(--ash); }
  .ctx-h span { color:var(--dim); letter-spacing:.04em; }
  .bars { display:flex; align-items:flex-end; gap:6px; height:76px; margin-top:16px; }
  .bars .mcol { flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; }
  .bars .bar { width:100%; min-height:3px; background:var(--ash); }
  .bars .ml { font:400 9px "IBM Plex Mono",monospace; color:var(--dim); }
  .frase { font:400 12px/1.55 "IBM Plex Mono",monospace; color:var(--bone); margin-top:16px;
    text-wrap:pretty; }
  .frase b { font-weight:600; color:var(--bone); }
  .comp { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
  .comp .chip { display:flex; align-items:baseline; gap:10px; border:1px solid var(--line);
    padding:9px 14px; background:var(--panel); font:400 12px "IBM Plex Mono",monospace;
    color:var(--bone); }
  .comp .chip b { font-weight:600; font-variant-numeric:tabular-nums; }

  /* ---- productos ---- */
  .productos { border-top:1px solid var(--line); scroll-margin-top:52px;
    padding:clamp(16px,3vw,24px) clamp(16px,3vw,32px) clamp(20px,3vw,28px); }
  .prod-head { display:flex; align-items:baseline; justify-content:space-between;
    gap:10px; flex-wrap:wrap; }
  .prod-note { font:500 11px "IBM Plex Mono",monospace; color:var(--ash);
    border:1px solid var(--line); padding:4px 10px; background:var(--panel); }
  .pchips { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
  .pchip { display:flex; align-items:center; gap:8px; font:500 11px "IBM Plex Mono",monospace;
    padding:7px 12px; min-height:34px; cursor:pointer; background:transparent;
    border:1px solid var(--line); color:var(--ash); }
  .pchip .dot { width:8px; height:8px; border-radius:50%; background:var(--dim); flex:none; }
  .pchip.active { background:var(--panel); color:var(--bone); }
  .pchart-wrap { position:relative; height:280px; margin-top:18px; }
  @media (min-width:760px) { .pchart-wrap { height:360px; } }
  #pchart { position:absolute; inset:0; }

  /* ---- footer ---- */
  footer { border-top:1px solid var(--line); padding:18px clamp(16px,3vw,32px);
    display:flex; flex-direction:column; gap:6px; background:var(--bg2); }
  footer .attr { font:400 11px/1.6 "IBM Plex Mono",monospace; color:var(--ash); }
  footer .disc { font:400 11px/1.6 "IBM Plex Mono",monospace; color:var(--dim); }

  .nochart { display:flex; align-items:center; justify-content:center; height:100%;
    color:var(--ash); font-size:13px; padding:20px; text-align:center; }
</style>
</head>
<body>

  <div class="ticker">
    <div class="tag">ÍNDICES</div>
    <div class="ticker-scroll"><div class="ticker-track" id="ticker-track"></div></div>
  </div>

  <header>
    <div class="brand">
      <div class="wordmark">CAREST<span class="i">I<span class="tilde" aria-hidden="true">Í</span></span>A</div>
      <div class="tagline">Índices del costo de vida · Chile</div>
    </div>
    <div class="semana">Semana del <span id="fecha"></span> <span>· actualizado viernes</span></div>
  </header>

  <nav class="tabs" id="tabs" aria-label="Índices"></nav>

  <div id="vista">
    <section class="hero-wrap" id="hero">
      <div id="chart"></div>
      <div class="overlay">
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
      <div class="controls">
        <div class="legend">
          <span><span class="sw" style="border-top:2px solid #e8743b"></span>En pesos de hoy: cuánto valdría hoy ese precio antiguo por la inflación acumulada</span>
          <span id="leg-nom"><span class="sw" style="border-top:1px solid #8b8276"></span>Nominal: el precio de la boleta de ese día</span>
        </div>
        <button class="vbtn nomtoggle" id="v-nominal">+ nominal</button>
        <div class="vtoggle">
          <button class="vbtn active" id="v-linea">LÍNEA</button>
          <button class="vbtn" id="v-velas">VELAS</button>
        </div>
      </div>
      <div class="ref" id="ref-velas"></div>
      <div class="zoomhint">zoom: arrastra el eje de años o el de precios · pinch en táctil</div>
      <div class="scroll-cue" id="scroll-cue" aria-hidden="true">∨</div>
      <div class="tooltip" id="tooltip">
        <div class="tt-d" id="tt-d"></div>
        <div class="tt-r"><span id="tt-r"></span> <small>pesos de hoy</small></div>
        <div class="tt-n" id="tt-n"></div>
      </div>
    </section>

    <section class="contexto">
      <div class="ctx-box">
        <div class="ctx-h">ESTACIONALIDAD</div>
        <div class="bars" id="season-bars"></div>
        <div class="frase" id="season-frase"></div>
      </div>
      <div class="ctx-box">
        <div class="ctx-h">COMPONENTES DE LA CANASTA <span>· aporte al total</span></div>
        <div class="comp" id="comp"></div>
      </div>
    </section>
  </div>

  <section class="productos" id="productos">
    <div class="prod-head">
      <div class="ctx-h">PRODUCTOS <span id="prod-rango"></span></div>
      <div class="prod-note">variación real, no precio · arrastra el eje de años para acercar</div>
    </div>
    <div class="pchips" id="pchips"></div>
    <div class="pchart-wrap"><div id="pchart"></div></div>
  </section>

  <footer>
    <div class="attr">Fuente: precios al consumidor ODEPA (datos.odepa.gob.cl, CC-BY) · deflactado por IPC. Cada precio es el promedio de los puntos que ODEPA encuesta cada semana en la Región Metropolitana: ferias libres, supermercados y carnicerías. Por eso suele ser menor que el precio de supermercado. Canastas fijas; precios normalizados a kilo, unidad o litro según el envase que cotiza ODEPA.</div>
    <div class="disc">Información de consumo con fines analíticos. No constituye asesoría ni recomendación de inversión.</div>
  </footer>

<script>
  const DATA = __DATA__;
  const INDICES = DATA.indices;
  const CODES = Object.keys(INDICES);
  const PRODS = DATA.productos || {};
  const fmt = v => '$' + Math.round(v).toLocaleString('es-CL');
  const MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // colores del semáforo: SOLO veredicto y velas
  const VELA_UP = '#5bbf7a', VELA_DOWN = '#e0552f';

  let cur = CODES[0], vista = 'linea', nomVisible = false;
  let chart, sNom, sReal, sCandle, pchart;
  let realMap = new Map(), nomMap = new Map();

  function deltaSemanal(d) {
    const r = d.real;
    if (!r || r.length < 2) return null;
    return (r[r.length - 1].value / r[r.length - 2].value - 1) * 100;
  }
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
        b.onclick = () => { render(code); document.getElementById('hero')
          .scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' }); };
        track.appendChild(b);
      });
    }
  }

  const tscroll = document.querySelector('.ticker-scroll');
  tscroll.addEventListener('touchstart',
    () => tscroll.classList.add('tocado'), { passive: true });
  ['touchend', 'touchcancel'].forEach(ev => tscroll.addEventListener(ev,
    () => tscroll.classList.remove('tocado'), { passive: true }));

  /* ---------- tabs de índice ---------- */
  const tabsEl = document.getElementById('tabs');
  function buildTabs() {
    tabsEl.innerHTML = '';
    CODES.forEach(code => {
      const b = document.createElement('button');
      b.className = 'tab';
      b.dataset.code = code;
      b.textContent = INDICES[code].nombre.replace(/^Índice /i, '');
      b.onclick = () => { render(code); document.getElementById('hero')
        .scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' }); };
      tabsEl.appendChild(b);
    });
    // pill de sección: no es un índice, va tras un separador fino
    const sep = document.createElement('span');
    sep.className = 'tab-sep';
    tabsEl.appendChild(sep);
    const p = document.createElement('button');
    p.className = 'tab';
    p.textContent = 'Productos';
    p.onclick = () => document.getElementById('productos')
      .scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' });
    tabsEl.appendChild(p);
  }
  function syncTabs() {
    tabsEl.querySelectorAll('.tab').forEach(b =>
      b.classList.toggle('active', b.dataset.code === cur));
  }

  /* ---------- hero chart ---------- */
  function initChart() {
    const el = document.getElementById('chart');
    if (!window.LightweightCharts) {
      el.innerHTML = '<div class="nochart">No se pudo cargar el motor de gráficos (revisa la conexión).</div>';
      return;
    }
    chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8276',
        fontFamily: "'IBM Plex Mono', monospace" },
      grid: { vertLines: { color: '#221b14' }, horzLines: { color: '#221b14' } },
      rightPriceScale: { borderColor: '#2a231c' },
      timeScale: { borderColor: '#2a231c' },
      localization: { priceFormatter: fmt },
      // la rueda y el swipe vertical quedan para la página; el zoom sigue
      // disponible arrastrando el eje de tiempo y con pinch en táctil
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, vertTouchDrag: false,
        horzTouchDrag: true, pressedMouseMove: true },
      // crosshair en brasa tenue, acompaña a la línea protagonista
      crosshair: { mode: 0,
        vertLine: { color: 'rgba(232,116,59,0.35)', labelBackgroundColor: '#5c3a24' },
        horzLine: { color: 'rgba(232,116,59,0.35)', labelBackgroundColor: '#5c3a24' } },
    });
    sNom = chart.addLineSeries({ color: '#8b8276', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false, visible: false });
    sReal = chart.addLineSeries({ color: '#e8743b', lineWidth: 2, priceLineVisible: false });
    // C2: convención estándar de trading, verde sube y rojo baja
    sCandle = chart.addCandlestickSeries({
      upColor: '#5bbf7a', downColor: '#e0552f', borderVisible: false,
      wickUpColor: '#5bbf7a', wickDownColor: '#e0552f', visible: false });
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
    document.getElementById('ref-velas').textContent =
      linea ? '' : 'velas semanales · mecha = rango mín-máx entre locales encuestados';
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
      (fem ? 'barata' : 'barato') + ' en <b>' + MESES[e.mes_barato] +
      '</b> y más ' + (fem ? 'cara' : 'caro') + ' en <b>' + MESES[e.mes_caro] +
      '</b> respecto de su historia · brecha estacional de ' + e.amplitud + '%.';
    const vals = Object.values(e.factores);
    const maxDev = Math.max(...vals.map(v => Math.abs(v - 1))) || 0.01;
    for (let m = 1; m <= 12; m++) {
      const f = e.factores[m] != null ? e.factores[m] : 1;
      const dev = f - 1;
      const col = document.createElement('div'); col.className = 'mcol';
      const bar = document.createElement('div'); bar.className = 'bar';
      bar.style.height = (6 + Math.abs(dev) / maxDev * 50) + 'px';
      bar.style.background = dev >= 0 ? '#e4dacc' : '#5a5348';
      bar.title = MESES[m] + ': ' + (dev >= 0 ? '+' : '') + Math.round(dev * 100) + '%';
      const lab = document.createElement('div'); lab.className = 'ml';
      lab.textContent = MESES[m];
      if (m === e.mes_caro || m === e.mes_barato) lab.style.color = '#e4dacc';
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
    document.getElementById('osub').textContent = '· ' + d.subtitulo;
    countUp(document.getElementById('oprice'), d.costo_real);
    document.getElementById('odelta').textContent = fmtDelta(deltaSemanal(d));
    document.getElementById('obadge').textContent = d.veredicto;
    document.getElementById('obadge').style.background = d.color;
    document.getElementById('opct').textContent =
      'percentil ' + d.percentil + ' de ' + d.n + ' semanas';
    document.getElementById('ovs').textContent =
      (d.vs_promedio >= 0 ? '+' : '') + d.vs_promedio +
      '% vs su promedio histórico, en pesos de hoy';
    realMap = new Map(d.real.map(p => [p.time, p.value]));
    nomMap = new Map(d.nominal.map(p => [p.time, p.value]));
    if (chart) {
      sNom.setData(d.nominal); sReal.setData(d.real);
      sCandle.setData(d.velas || []);
      aplicarVista();
    }
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

  const vistaEl = document.getElementById('vista');
  function render(code, primera) {
    cur = code;
    syncTabs();          // estado activo también al navegar desde el ticker
    if (primera || reduced) { aplicar(code); return; }
    vistaEl.style.opacity = 0;                       // crossfade al cambiar índice
    setTimeout(() => { aplicar(code); vistaEl.style.opacity = 1; }, 180);
  }

  /* ---------- vista Productos ---------- */
  // C3: paleta propia, sin los colores del semáforo (#5bbf7a/#e0552f/#e0a83c)
  // ni la brasa; 8 tonos distinguibles sobre carbón.
  const PALETTE = ['#6ea8dc', '#58c5c0', '#9a8ec4', '#cf8bc0',
                   '#d18a92', '#c2c268', '#b58a5c', '#8f9bb3'];
  const PKEYS = Object.keys(PRODS);
  const colorOf = k => PALETTE[PKEYS.indexOf(k) % PALETTE.length];
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
    pchart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8276',
        fontFamily: "'IBM Plex Mono', monospace" },
      grid: { vertLines: { color: '#221b14' }, horzLines: { color: '#221b14' } },
      // modo percentage: rebase automático a la ventana visible
      rightPriceScale: { mode: LightweightCharts.PriceScaleMode.Percentage,
        borderColor: '#2a231c' },
      timeScale: { borderColor: '#2a231c' },
      // misma política que el hero: rueda y swipe vertical scrollean la página
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, vertTouchDrag: false,
        horzTouchDrag: true, pressedMouseMove: true },
      crosshair: { mode: 0,
        vertLine: { color: 'rgba(228,218,204,0.35)', labelBackgroundColor: '#3a3129' },
        horzLine: { color: 'rgba(228,218,204,0.35)', labelBackgroundColor: '#3a3129' } },
    });
  }

  function syncProductos() {
    if (!pchart) return;
    PKEYS.forEach(k => {
      const on = psel.has(k);
      if (on && !pseries.has(k)) {
        const s = pchart.addLineSeries({ color: colorOf(k), lineWidth: 2,
          priceLineVisible: false, lastValueVisible: false });
        s.setData(PRODS[k].real);
        pseries.set(k, s);
      } else if (!on && pseries.has(k)) {
        pchart.removeSeries(pseries.get(k));
        pseries.delete(k);
      }
    });
    pchart.timeScale().fitContent();
  }

  function buildProductos() {
    if (!PKEYS.length) { document.getElementById('productos').style.display = 'none'; return; }
    let y0 = 9999, y1 = 0;
    PKEYS.forEach(k => {
      const r = PRODS[k].real;
      if (!r.length) return;
      y0 = Math.min(y0, +r[0].time.slice(0, 4));
      y1 = Math.max(y1, +r[r.length - 1].time.slice(0, 4));
    });
    document.getElementById('prod-rango').textContent = '· ' + y0 + ' a ' + y1;
    const cont = document.getElementById('pchips');
    cont.innerHTML = '';
    PKEYS.forEach(k => {
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
      cont.appendChild(b);
    });
  }

  // el chevron invita a bajar; se apaga con el primer scroll del usuario
  window.addEventListener('scroll', () =>
    document.getElementById('scroll-cue').classList.add('oculto'),
    { once: true, passive: true });

  window.addEventListener('load', () => {
    buildTicker();
    buildTabs();
    initChart();
    render(CODES[0], true);
    initPChart();
    buildProductos();
    syncProductos();
  });
</script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)))

print("Listo: index.html")
for c, d in DATA["indices"].items():
    print(f"  {d['nombre']}: {d['veredicto']} (percentil {d['percentil']})")
if "productos" in DATA:
    print(f"  Productos: {len(DATA['productos'])} series")

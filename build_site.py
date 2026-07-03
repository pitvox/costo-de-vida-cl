"""
build_site.py - genera el sitio multi-indice
=============================================
Lee 'indices.json' (lo produce indices.py) y escribe 'index.html': un sitio
con pestañas para cambiar entre indices (Asado / Ensalada / Fruta), cada uno
con su precio en pesos de hoy, semaforo y grafico nominal vs real.

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
<title>Índices del costo de vida — Chile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root { --bg:#17120e; --panel:#1e1813; --bone:#e4dacc; --ash:#8b8276;
    --ember:#e8743b; --line:rgba(228,218,204,0.08); --verdict:#e0552f; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--bone); font-family:"IBM Plex Mono",monospace;
    min-height:100vh; padding:clamp(16px,4vw,40px); display:flex; flex-direction:column; gap:20px; }
  .eyebrow { font-size:12px; letter-spacing:0.22em; color:var(--ash); text-transform:uppercase; }
  .tabs { display:flex; gap:10px; flex-wrap:wrap; }
  .tab { font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--ash);
    background:transparent; border:1px solid var(--line); border-radius:999px;
    padding:8px 16px; cursor:pointer; transition:all .15s; }
  .tab:hover { color:var(--bone); }
  .tab.active { color:var(--bg); background:var(--bone); border-color:var(--bone); font-weight:500; }
  header { display:flex; flex-wrap:wrap; align-items:flex-end; gap:28px;
    border-bottom:1px solid var(--line); padding-bottom:22px; }
  .hero { display:flex; align-items:center; gap:20px; }
  .coal { width:46px; height:46px; border-radius:50%;
    background:radial-gradient(circle at 35% 30%, var(--verdict), #000 130%);
    box-shadow:0 0 26px -2px var(--verdict); flex:none; animation:glow 3.2s ease-in-out infinite; }
  @keyframes glow { 0%,100%{opacity:.78} 50%{opacity:1} }
  @media (prefers-reduced-motion: reduce){ .coal{animation:none} }
  .price { font-family:"Space Grotesk",sans-serif; font-weight:700;
    font-size:clamp(38px,7vw,62px); line-height:0.95; color:var(--bone); letter-spacing:-0.01em; }
  .price .v { color:var(--verdict); }
  .price small { display:block; font-family:"IBM Plex Mono",monospace; font-weight:400;
    font-size:13px; color:var(--ash); letter-spacing:0.03em; margin-top:10px; }
  .facts { margin-left:auto; text-align:right; display:grid; gap:8px; }
  .facts .big { font-family:"Space Grotesk",sans-serif; font-size:clamp(18px,3vw,24px);
    font-weight:500; color:var(--bone); }
  .facts .lbl { font-size:11px; color:var(--ash); letter-spacing:0.12em; text-transform:uppercase; }
  .chart-wrap { height:clamp(320px,52vh,600px); background:var(--panel);
    border:1px solid var(--line); border-radius:10px; padding:14px; }
  #chart { width:100%; height:100%; }
  .season { display:flex; flex-direction:column; gap:10px; }
  .season .frase { font-size:13px; color:var(--bone); }
  .season .frase b { color:var(--ember); font-weight:500; }
  .bars { display:flex; gap:6px; align-items:flex-end; height:64px; }
  .bars .mcol { flex:1; display:flex; flex-direction:column; align-items:center; gap:5px; }
  .bars .bar { width:100%; border-radius:3px 3px 0 0; min-height:3px; background:var(--ash); }
  .bars .ml { font-size:10px; color:var(--ash); letter-spacing:0.05em; }
  .legend { display:flex; gap:22px; font-size:12px; color:var(--ash); flex-wrap:wrap; align-items:center; }
  .legend b { font-weight:500; color:var(--bone); }
  .sw { display:inline-block; width:22px; height:3px; vertical-align:middle; margin-right:7px; }
  .vtoggle { margin-left:auto; display:flex; gap:6px; align-items:center; }
  .vbtn { font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ash);
    background:transparent; border:1px solid var(--line); border-radius:6px; padding:5px 12px; cursor:pointer; }
  .vbtn.active { color:var(--bone); border-color:var(--ash); }
  .ref { font-size:10px; color:#6a6258; margin-left:4px; }
  .comp { display:flex; flex-wrap:wrap; gap:8px; font-size:11px; }
  .comp .chip { border:1px solid var(--line); border-radius:6px; padding:5px 10px; color:var(--ash); }
  .comp .chip b { color:var(--bone); font-weight:500; }
  footer { font-size:11px; color:var(--ash); line-height:1.6; border-top:1px solid var(--line); padding-top:16px; }
  footer .disc { color:#6a6258; }
</style>
</head>
<body>
  <div class="eyebrow">Índices del costo de vida · Región Metropolitana</div>
  <div class="tabs" id="tabs"></div>

  <header>
    <div class="hero">
      <div class="coal" id="coal"></div>
      <div class="price"><span id="precio"></span> <span class="v" id="ver"></span>
        <small id="sub"></small>
      </div>
    </div>
    <div class="facts">
      <div><div class="lbl">Precio nominal hoy</div><div class="big" id="nom"></div></div>
      <div class="lbl" id="fecha"></div>
    </div>
  </header>

  <div class="legend">
    <span><span class="sw" style="background:#8b8276"></span><b>Nominal</b> — lo que pagaste ese día</span>
    <span><span class="sw" style="background:#e8743b"></span><b>En pesos de hoy</b> — descontada la inflación</span>
    <div class="vtoggle">
      <button class="vbtn active" id="v-linea" onclick="setView('linea')">Línea</button>
      <button class="vbtn" id="v-velas" onclick="setView('velas')">Velas</button>
      <span class="ref" id="ref-velas"></span>
    </div>
  </div>

  <div class="chart-wrap"><div id="chart"></div></div>

  <div class="season">
    <div class="frase" id="season-frase"></div>
    <div class="bars" id="season-bars"></div>
  </div>

  <div class="comp" id="comp"></div>

  <footer>
    Fuente: precios al consumidor ODEPA (datos.odepa.gob.cl, CC-BY) · deflactado por IPC. Canastas fijas; precios normalizados a kilo, unidad o litro según el envase que cotiza ODEPA (Región Metropolitana).<br>
    <span class="disc">Información de consumo con fines analíticos. No constituye asesoría ni recomendación de inversión.</span>
  </footer>

<script>
  const DATA = __DATA__;
  const codes = Object.keys(DATA.indices);
  const fmt = (v) => '$' + Math.round(v).toLocaleString('es-CL');

  let chart, sNom, sReal, sCandle, vista = 'linea';

  function aplicarVista() {
    if (!chart) return;
    const linea = vista === 'linea';
    sNom.applyOptions({ visible: linea });
    sReal.applyOptions({ visible: linea });
    sCandle.applyOptions({ visible: !linea });
    document.getElementById('v-linea').classList.toggle('active', linea);
    document.getElementById('v-velas').classList.toggle('active', !linea);
    document.getElementById('ref-velas').textContent =
      linea ? '' : 'velas semanales · mecha = rango mín-máx entre puntos de venta';
    chart.timeScale().fitContent();
  }
  function setView(v) { vista = v; aplicarVista(); }
  function initChart() {
    const el = document.getElementById('chart');
    if (!window.LightweightCharts) { el.innerHTML =
      '<p style="color:#8b8276;font-size:13px">No se pudo cargar el motor de gráficos (revisa la conexión).</p>'; return; }
    chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout:{ background:{type:'solid',color:'transparent'}, textColor:'#b9b0a4', fontFamily:"'IBM Plex Mono', monospace" },
      grid:{ vertLines:{color:'rgba(228,218,204,0.05)'}, horzLines:{color:'rgba(228,218,204,0.05)'} },
      rightPriceScale:{ borderColor:'rgba(228,218,204,0.10)' },
      timeScale:{ borderColor:'rgba(228,218,204,0.10)' },
      localization:{ priceFormatter: fmt },
      crosshair:{ mode:0, vertLine:{color:'rgba(232,116,59,0.4)',labelBackgroundColor:'#e8743b'},
        horzLine:{color:'rgba(232,116,59,0.4)',labelBackgroundColor:'#e8743b'} },
    });
    sNom = chart.addLineSeries({ color:'#8b8276', lineWidth:1, priceLineVisible:false });
    sReal = chart.addLineSeries({ color:'#e8743b', lineWidth:2, priceLineVisible:false });
    sCandle = chart.addCandlestickSeries({ upColor:'#e0552f', downColor:'#5bbf7a',
      borderVisible:false, wickUpColor:'#e0552f', wickDownColor:'#5bbf7a', visible:false });
    const fix = () => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    requestAnimationFrame(fix); setTimeout(fix, 250);
  }

  const MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

  function renderEstacional(d) {
    const e = d.estacionalidad || {};
    const frase = document.getElementById('season-frase');
    const cont = document.getElementById('season-bars');
    cont.innerHTML = '';
    if (!e.factores) { frase.textContent = ''; return; }
    frase.innerHTML = 'Estacionalmente, el ' + d.nombre.replace('Índice ','').toLowerCase() +
      ' suele estar más barato en <b>' + MESES[e.mes_barato] + '</b> y más caro en <b>' +
      MESES[e.mes_caro] + '</b> · amplitud ' + e.amplitud + '%';
    const vals = Object.values(e.factores);
    const maxDev = Math.max(...vals.map(v => Math.abs(v - 1))) || 0.01;
    for (let m = 1; m <= 12; m++) {
      const f = e.factores[m] != null ? e.factores[m] : 1;
      const dev = f - 1;
      const h = 6 + Math.abs(dev) / maxDev * 50;
      const col = document.createElement('div'); col.className = 'mcol';
      const bar = document.createElement('div'); bar.className = 'bar';
      bar.style.height = h + 'px';
      bar.style.background = dev >= 0 ? '#e8743b' : '#6f8a72';
      bar.title = MESES[m] + ': ' + (dev >= 0 ? '+' : '') + Math.round(dev * 100) + '%';
      const lab = document.createElement('div'); lab.className = 'ml'; lab.textContent = MESES[m][0];
      col.appendChild(bar); col.appendChild(lab); cont.appendChild(col);
    }
  }

  function render(code) {
    const d = DATA.indices[code];
    document.documentElement.style.setProperty('--verdict', d.color);
    document.getElementById('precio').textContent = fmt(d.costo_real);
    document.getElementById('ver').textContent = '· ' + d.veredicto;
    document.getElementById('sub').textContent =
      d.subtitulo + ', en pesos de hoy · percentil ' + d.percentil + ' de ' + d.n +
      ' semanas · ' + (d.vs_promedio>=0?'+':'') + d.vs_promedio + '% vs su promedio histórico';
    document.getElementById('nom').textContent = fmt(d.costo_nominal);
    document.getElementById('fecha').textContent = 'Semana del ' + d.fecha;
    if (chart) { sNom.setData(d.nominal); sReal.setData(d.real);
      sCandle.setData(d.velas || []); aplicarVista(); }
    renderEstacional(d);
    const comp = document.getElementById('comp');
    comp.innerHTML = '';
    (d.componentes || []).forEach(c => {
      if (c.aporte == null) return;
      const chip = document.createElement('div'); chip.className = 'chip';
      chip.innerHTML = c.label + ' <b>' + fmt(c.aporte) + '</b>';
      comp.appendChild(chip);
    });
    document.querySelectorAll('.tab').forEach(t =>
      t.classList.toggle('active', t.dataset.code === code));
  }

  const tabs = document.getElementById('tabs');
  codes.forEach(code => {
    const b = document.createElement('button');
    b.className = 'tab'; b.dataset.code = code; b.textContent = DATA.indices[code].nombre;
    b.onclick = () => render(code);
    tabs.appendChild(b);
  });

  window.addEventListener('load', () => { initChart(); render(codes[0]); });
</script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)))

print("Listo: index.html")
for c, d in DATA["indices"].items():
    print(f"  {d['nombre']}: {d['veredicto']} (percentil {d['percentil']})")

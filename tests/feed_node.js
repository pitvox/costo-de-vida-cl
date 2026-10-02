// Pruebas del datafeed de Advanced Charts (carestia-tv.js) contra un build
// de build_site.py, sin la librería: se lo llama como lo hace ella
// (onReady, searchSymbols, resolveSymbol y getBars con paginado por
// countBack) y se compara cada barra con indices.json y datos/.
//
//   node tests/feed_node.js DIR_DEL_BUILD
//
// DIR_DEL_BUILD es donde corrió build_site.py (indices.json, datos/ y
// carestia-tv.js). Lo llama tests/test_tradingview.py con datos sintéticos y
// con el indices.json real de carestia.cl. Termina con código 1 si algo falla.
'use strict';
const fs = require('fs');
const path = require('path');

const dir = path.resolve(process.argv[2] || '.');
const leer = r => JSON.parse(fs.readFileSync(path.join(dir, r), 'utf8'));
const TV = require(path.join(dir, 'carestia-tv.js'));
const DATA = leer('indices.json');
const CAT = leer(path.join('datos', 'catalogo.json'));
const CODES = Object.keys(DATA.indices);
const INDICES = CODES.map(c => ({ codigo: c, nombre: DATA.indices[c].nombre }));

let fallas = 0, chequeos = 0;
function ok(cond, msg) {
  chequeos++;
  if (!cond) { fallas++; console.log('FALLA ' + msg); }
}
const ms = t => Date.parse(t + 'T00:00:00Z');
const semana = 7 * 864e5;
const lunes = x => new Date(x).getUTCDay() === 1 && x % 864e5 === 0;
// los callbacks de la API se llaman en forma asíncrona: se marca la vuelta
// sincrónica y se verifica que el callback llegue después
function llamar(f) {
  return new Promise((res, rej) => {
    let sincrono = true;
    f(v => { ok(!sincrono, 'callback asíncrono'); res(v); },
      e => { ok(!sincrono, 'callback de error asíncrono'); rej(e); });
    sincrono = false;
  });
}

const pedidos = [];
const feed = TV.crearDatafeed({
  indices: INDICES,
  pedir: r => { pedidos.push(r); return Promise.resolve(leer(path.join('datos', r))); },
});

// la librería pide la historia hacia atrás: el primer pedido termina "ahora"
// y los siguientes en la barra más antigua recibida, hasta noData
async function historia(info, porPedido) {
  let to = Math.floor(Date.UTC(2100, 0, 1) / 1000), out = [], vueltas = 0, primero = true;
  for (;;) {
    const r = await llamar((res, rej) => feed.getBars(info, '1W',
      { from: to - porPedido * 7 * 86400, to, countBack: porPedido, firstDataRequest: primero },
      (bars, meta) => res({ bars, meta }), rej));
    primero = false;
    if (++vueltas > 1000) { ok(false, info.ticker + ': el paginado no termina'); break; }
    if (!r.bars.length) { ok(r.meta.noData === true, info.ticker + ': sin barras es noData'); break; }
    ok(r.meta.noData === false, info.ticker + ': con barras no es noData');
    ok(r.bars.length <= porPedido, info.ticker + ': no más de countBack barras');
    ok(r.bars[r.bars.length - 1].time < to * 1000, info.ticker + ': to no es inclusivo');
    out = r.bars.concat(out);
    to = r.bars[0].time / 1000;
  }
  return out;
}

function velas(bars, t) {
  ok(bars.every(b => lunes(b.time)), t + ': cada barra a las 00:00 UTC de un lunes');
  ok(bars.every((b, i) => !i || b.time > bars[i - 1].time), t + ': barras en orden y sin repetir');
  ok(bars.every(b => [b.open, b.high, b.low, b.close].every(Number.isInteger)),
     t + ': pesos sin decimales');
  ok(bars.every(b => b.low <= Math.min(b.open, b.close) && b.high >= Math.max(b.open, b.close)),
     t + ': mínimo y máximo envuelven el cuerpo');
}

(async () => {
  // ---- onReady ----
  const conf = await llamar(res => feed.onReady(res));
  ok(JSON.stringify(conf.supported_resolutions) === '["1W"]', 'onReady: solo 1W');
  ok(conf.supports_time === false && conf.supports_marks === false, 'onReady: sin hora ni marcas');

  // ---- símbolos ----
  const lista = await feed.lista();
  const tickers = lista.map(s => s.ticker);
  ok(new Set(tickers).size === tickers.length, 'tickers únicos');
  ok(tickers.every(t => /^[a-z0-9-]+$/.test(t)), 'tickers sin paréntesis ni dos puntos');
  ok(lista.length === 2 * (CODES.length + CAT.productos.length),
     'cada serie en pesos de hoy y nominal: ' + lista.length);
  CODES.forEach(c => ok(tickers.includes(c) && tickers.includes(c + '-nominal'), 'índice ' + c));
  CAT.productos.forEach(p => ok(tickers.includes(p.slug) && tickers.includes(p.slug + '-nominal'),
    'producto con el slug de su ficha: ' + p.slug));

  // ---- resolveSymbol ----
  for (const s of lista) {
    const info = await llamar((res, rej) => feed.resolveSymbol(s.ticker, res, rej));
    const t = s.ticker;
    ok(info.name === t && info.ticker === t, t + ': name y ticker = slug');
    ok(info.pricescale === 1 && info.minmov === 1 && info.currency_code === 'CLP',
       t + ': CLP sin decimales');
    ok(info.timezone === 'America/Santiago' && info.session === '24x7', t + ': zona');
    ok(JSON.stringify(info.supported_resolutions) === '["1W"]' && info.has_weekly_and_monthly === true
       && info.has_intraday === false, t + ': semanal');
    ok(info.visible_plots_set === 'ohlc', t + ': velas en índices y productos');
    // nombre corto (leyenda del celular) y largo (pantallas anchas y búsqueda)
    ok(info.long_description === s.descripcion && /, (nominal|en pesos de hoy)$/.test(info.long_description),
       t + ': descripción larga en español');
    ok(info.description === s.corto && info.description.length < info.long_description.length &&
       / nominal$/.test(info.description) === s.nominal, t + ': nombre corto');
  }
  const asado = await llamar((res, rej) => feed.resolveSymbol('Carestía:' + CODES[0].toUpperCase(), res, rej));
  ok(asado.ticker === CODES[0], 'resolveSymbol tolera prefijo de fuente y mayúsculas');
  let error = null;
  await llamar((res, rej) => feed.resolveSymbol('no-existe', res, rej)).catch(e => { error = e; });
  ok(typeof error === 'string', 'símbolo desconocido: onError');

  // ---- getBars: índices ----
  for (const c of CODES) {
    const d = DATA.indices[c];
    const real = await historia(await feed.info(c), 150);
    velas(real, c);
    ok(JSON.stringify(real) === JSON.stringify(d.velas.map(v =>
      ({ time: ms(v.time), open: v.open, high: v.high, low: v.low, close: v.close }))),
      c + ': las velas de indices.json, idénticas');
    ok(real.every((b, i) => !i || b.open === real[i - 1].close), c + ': apertura = cierre anterior');
    const nom = await historia(await feed.info(c + '-nominal'), 150);
    velas(nom, c + '-nominal');
    ok(JSON.stringify(nom.map(b => [b.time, b.close])) ===
       JSON.stringify(d.nominal.map(p => [ms(p.time), p.value])), c + '-nominal: cierre = nominal publicado');
    ok(nom.every((b, i) => !i || b.open === nom[i - 1].close), c + '-nominal: apertura = cierre anterior');
    // la mecha nominal es la real llevada a pesos de esa semana
    const porT = new Map(real.map(b => [b.time, b]));
    ok(nom.every(b => {
      const r = porT.get(b.time), k = b.close / r.close;
      return Math.abs(Math.max(b.open, b.close, r.high * k) - b.high) <= 1 &&
             Math.abs(Math.min(b.open, b.close, r.low * k) - b.low) <= 1;
    }), c + '-nominal: mecha = mínimo y máximo reales en pesos de la semana');
  }

  // ---- getBars: productos ----
  // el factor mensual (nominal / real de los índices) reproduce el nominal
  // publicado de cada índice a $1
  const factor = new Map();
  CODES.forEach(c => {
    const nom = new Map(DATA.indices[c].nominal.map(p => [p.time, p.value]));
    DATA.indices[c].real.forEach(p => {
      if (!nom.has(p.time)) return;
      const m = p.time.slice(0, 7), f = factor.get(m) || [0, 0];
      factor.set(m, [f[0] + nom.get(p.time), f[1] + p.value]);
    });
  });
  let maxErr = 0;
  CODES.forEach(c => {
    const nom = new Map(DATA.indices[c].nominal.map(p => [p.time, p.value]));
    DATA.indices[c].real.forEach(p => {
      const f = factor.get(p.time.slice(0, 7));
      maxErr = Math.max(maxErr, Math.abs(Math.round(p.value * f[0] / f[1]) - nom.get(p.time)));
    });
  });
  ok(maxErr <= 1, 'factor mensual: reproduce el nominal de los índices a $1 (error máximo $' + maxErr + ')');
  let sinFactor = 0, semanasProd = 0;
  for (const f of CAT.productos) {
    const p = leer(path.join('datos', 'productos', f.slug + '.json'));
    const esperado = [];
    p.v.forEach((v, i) => { if (v != null) esperado.push({ time: ms(p.t0) + i * semana, v, i }); });
    const real = await historia(await feed.info(f.slug), 400);
    velas(real, f.slug);
    // la vela: cuerpo desde el cierre anterior, mecha con el rango de ODEPA
    const rango = (a, i, v) => a && a[i] != null ? a[i] : v;
    ok(JSON.stringify(real) === JSON.stringify(esperado.map((e, k) => {
      const o = k ? esperado[k - 1].v : e.v;
      return { time: e.time, open: o, high: Math.max(o, e.v, rango(p.max, e.i, e.v)),
        low: Math.min(o, e.v, rango(p.min, e.i, e.v)), close: e.v };
    })), f.slug + ': la serie de datos/, en velas');
    // con rango de ODEPA (hay productos sin mínimo ni máximo), con mecha
    if (p.min && p.min.some((x, i) => x != null && p.v[i] != null && x < p.v[i]))
      ok(real.some(b => b.low < Math.min(b.open, b.close)), f.slug + ': con mecha');
    ok(real.length && real[real.length - 1].close === f.precio_pesos_hoy,
       f.slug + ': el último cierre es el precio de hoy del catálogo');
    const nom = await historia(await feed.info(f.slug + '-nominal'), 400);
    velas(nom, f.slug + '-nominal');
    const conFactor = esperado.filter(e => factor.has(new Date(e.time).toISOString().slice(0, 7)));
    sinFactor += esperado.length - conFactor.length;
    semanasProd += esperado.length;
    ok(JSON.stringify(nom.map(b => [b.time, b.close])) === JSON.stringify(conFactor.map(e => {
      const g = factor.get(new Date(e.time).toISOString().slice(0, 7));
      return [e.time, Math.round(e.v * g[0] / g[1])];
    })), f.slug + '-nominal: precio de hoy por el factor del mes');
  }

  // ---- otras resoluciones y búsqueda ----
  const d1 = await llamar((res, rej) => feed.getBars(asado, '1D',
    { from: 0, to: 4e9, countBack: 10, firstDataRequest: true }, (b, m) => res({ b, m }), rej));
  ok(!d1.b.length && d1.m.noData, 'resolución no semanal: noData');
  const buscar = (q, tipo) => llamar(res => feed.searchSymbols(q, '', tipo || '', res));
  const r1 = await buscar('indice');
  ok(r1.length === 2 * CODES.length, 'búsqueda sin tildes: "indice" encuentra los índices');
  ok(r1.every(r => r.symbol === r.ticker && !('full_name' in r) && !/[:()]/.test(r.ticker)
     && r.exchange === 'Carestía' && r.type === 'index'), 'resultados con el ticker y la fuente');
  const r2 = await buscar(INDICES[0].nombre.replace('Índice ', '').toLowerCase() + ' NOMINAL');
  ok(r2.length >= 1 && r2.every(r => /-nominal$/.test(r.ticker)), 'búsqueda con varias palabras');
  const r3 = await buscar('', 'commodity');
  ok(r3.length === 2 * CAT.productos.length, 'filtro por tipo: productos');
  ok((await buscar('zzzz-no-existe')).length === 0, 'búsqueda sin resultados');
  // la librería puede modificar las barras: cada respuesta es una copia
  const p1 = await llamar((res, rej) => feed.getBars(asado, '1W',
    { from: 0, to: 4e9, countBack: 5, firstDataRequest: false }, b => res(b), rej));
  const cierre = p1[4].close;
  p1[4].close = -1;
  const p2 = await llamar((res, rej) => feed.getBars(asado, '1W',
    { from: 0, to: 4e9, countBack: 5, firstDataRequest: false }, b => res(b), rej));
  ok(p2[4].close === cierre, 'getBars entrega copias');
  // sin countBack y sin barras en el tramo: al menos dos anteriores
  const p3 = await llamar((res, rej) => feed.getBars(asado, '1W',
    { from: 4e9 - 1, to: 4e9, countBack: 0, firstDataRequest: false }, (b, m) => res({ b, m }), rej));
  ok(p3.b.length === 2 && !p3.m.noData, 'sin countBack: las dos barras anteriores');

  // ---- formatos: pesos con punto de miles y fechas dd-mm-aaaa ----
  const f = TV.formateadores();
  const precio = f.priceFormatterFactory(null, '1');
  ok(precio.format(26467.4) === '26.467' && precio.format(980) === '980' &&
     precio.format(1234567) === '1.234.567', 'precio con punto de miles y sin decimales');
  ok(precio.format(1234, { signPositive: true }) === '+1.234' && precio.format(-1234) === '-1.234',
     'precio con signo');
  ok(f.dateFormatter.format(new Date(Date.UTC(2026, 8, 21))) === '21-09-2026', 'fecha dd-mm-aaaa');
  ok(f.dateFormatter.formatLocal(new Date(2026, 0, 5)) === '05-01-2026', 'fecha local dd-mm-aaaa');
  ok(f.dateFormatter.parse('5-1-2026') === '2026-01-05', 'fecha escrita a aaaa-mm-dd');

  // ---- guardado en el navegador (localStorage simulado) ----
  const mem = new Map();
  global.localStorage = { getItem: k => mem.has(k) ? mem.get(k) : null,
    setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
  const a = TV.almacenLocal('prueba:');
  const id = await a.saveChart({ name: 'Mi gráfico', symbol: 'asado', resolution: '1W', content: '{"x":1}' });
  await a.saveChart({ id, name: 'Mi gráfico', symbol: 'palta', resolution: '1W', content: '{"x":2}' });
  const lista2 = await a.getAllCharts();
  ok(lista2.length === 1 && lista2[0].symbol === 'palta' && Number.isInteger(lista2[0].timestamp)
     && !('content' in lista2[0]), 'saveChart reemplaza por id; getAllCharts sin contenido');
  ok(await a.getChartContent(id) === '{"x":2}', 'getChartContent');
  await a.saveStudyTemplate({ name: 'medias', content: 'c' });
  ok((await a.getAllStudyTemplates())[0].name === 'medias' &&
     await a.getStudyTemplateContent({ name: 'medias' }) === 'c', 'plantillas de indicadores');
  await a.saveDrawingTemplate('LineToolTrendLine', 'roja', 't');
  ok(JSON.stringify(await a.getDrawingTemplates('LineToolTrendLine')) === '["roja"]' &&
     await a.loadDrawingTemplate('LineToolTrendLine', 'roja') === 't', 'plantillas de dibujos');
  await a.removeChart(id);
  ok((await a.getAllCharts()).length === 0, 'removeChart');
  ok([...mem.keys()].every(k => k.startsWith('prueba:')), 'todo bajo el prefijo, en el navegador');
  const metodos = ['getAllCharts', 'removeChart', 'saveChart', 'getChartContent',
    'getAllStudyTemplates', 'removeStudyTemplate', 'saveStudyTemplate', 'getStudyTemplateContent',
    'getDrawingTemplates', 'loadDrawingTemplate', 'removeDrawingTemplate', 'saveDrawingTemplate',
    'getChartTemplateContent', 'getAllChartTemplates', 'saveChartTemplate', 'removeChartTemplate',
    'saveLineToolsAndGroups', 'loadLineToolsAndGroups'];
  ok(metodos.every(m => typeof a[m] === 'function'), 'IExternalSaveLoadAdapter completo');

  // ---- opciones del widget ----
  const TOK = { bg: '#000001', panel: '#000002', line: '#000003', grid: '#000004', bone: '#000005',
    ash: '#000006', dim: '#000007', ember: '#000008', verde: '#000009', rojo: '#00000a' };
  const o = TV.opcionesWidget({ contenedor: 'tv', libreria: '/charting_library/', simbolo: 'asado',
    datafeed: feed, tok: n => TOK[n], css: 'https://carestia.cl/carestia-tv.css' });
  ok(o.locale === 'es' && o.interval === '1W' && o.timezone === 'America/Santiago' &&
     o.theme === 'dark' && o.symbol === 'asado' && o.datafeed === feed, 'widget: es, 1W, Santiago, oscuro');
  ok(o.library_path === '/charting_library/' && o.autosize === true, 'widget: ruta de la librería');
  // nada que guarde fuera del navegador
  ok(!['charts_storage_url', 'charts_storage_api_version', 'client_id', 'user_id', 'snapshot_url',
       'settings_adapter'].some(k => k in o), 'widget: sin almacenamiento ni capturas en servidores');
  ok(typeof o.save_load_adapter.saveChart === 'function' && o.load_last_chart === true &&
     o.auto_save_delay > 0, 'widget: guardar y cargar en el navegador');
  ok(JSON.stringify(o.disabled_features) === '[]' &&
     ['study_templates', 'no_min_chart_width'].every(x => o.enabled_features.includes(x)),
     'widget: todas las funciones de fábrica, más plantillas y sin ancho mínimo');
  ok(o.time_frames.every(t => t.resolution === '1W' && /^\d+[ym]$/.test(t.text)), 'widget: plazos semanales');
  ok(o.numeric_formatting.decimal_sign === ',' && o.numeric_formatting.grouping_separator === '.',
     'widget: coma decimal y punto de miles');
  ok(o.custom_formatters.priceFormatterFactory(null, '1').format(26467) === '26.467', 'widget: formato de precio');
  ok(/IBM Plex Sans/.test(o.custom_font_family) && o.custom_css_url === 'https://carestia.cl/carestia-tv.css',
     'widget: Plex Sans y el tema del sitio');
  const ov = o.overrides;
  ok(ov['paneProperties.background'] === TOK.bg && ov['paneProperties.backgroundType'] === 'solid' &&
     ov['paneProperties.vertGridProperties.color'] === TOK.grid &&
     ov['scalesProperties.textColor'] === TOK.ash && ov['scalesProperties.lineColor'] === TOK.line,
     'widget: fondo, grilla y escalas con los tokens');
  ok(ov['mainSeriesProperties.style'] === 1 && ov['mainSeriesProperties.lineStyle.color'] === TOK.ember,
     'widget: velas por defecto y línea de índice en brasa');
  ok(['upColor', 'borderUpColor', 'wickUpColor'].every(k => ov['mainSeriesProperties.candleStyle.' + k] === TOK.verde) &&
     ['downColor', 'borderDownColor', 'wickDownColor'].every(k => ov['mainSeriesProperties.candleStyle.' + k] === TOK.rojo),
     'widget: velas verde sube, rojo baja');
  ok(o.loading_screen.backgroundColor === TOK.bg, 'widget: pantalla de carga con el fondo');

  // ---- configuración común: celular y páginas del sitio ----
  const base = { contenedor: 'tv', libreria: '/charting_library/', simbolo: 'asado', datafeed: feed,
    tok: n => TOK[n], css: 'x' };
  const esc = TV.opcionesWidget(Object.assign({ movil: false }, base));
  const mov = TV.opcionesWidget(Object.assign({ movil: true }, base));
  const sit = TV.opcionesWidget(Object.assign({ movil: false, sitio: true,
    comparar: [{ symbol: 'palta-nominal', title: 'Palta, nominal' }] }, base));
  const leyenda = x => ['symbolTextSource', 'showInterval', 'showExchange']
    .map(k => x.overrides['mainSeriesProperties.statusViewStyle.' + k]).join(',');
  ok(leyenda(esc) === 'long-description,true,true', 'escritorio: leyenda con el nombre largo');
  ok(leyenda(mov) === 'description,false,false', 'celular: leyenda con el nombre corto, sin intervalo ni fuente');
  ok(['header_resolutions', 'header_symbol_search', 'header_settings', 'header_undo_redo',
      'header_quick_search', 'header_screenshot', 'header_saveload'].every(f => mov.disabled_features.includes(f)),
     'celular: sin selector de intervalo ni lo que no cabe');
  ok(!['header_compare', 'header_indicators', 'header_chart_type', 'header_fullscreen_button',
       'left_toolbar', 'header_widget'].some(f => mov.disabled_features.includes(f) ||
       sit.disabled_features.includes(f)),
     'celular y sitio: quedan comparar, indicadores, tipo de gráfico, dibujo y pantalla completa');
  ok(['header_symbol_search', 'symbol_search_hot_key', 'header_saveload', 'mouse_wheel_scale',
      'mouse_wheel_scroll', 'vert_touch_drag_scroll'].every(f => sit.disabled_features.includes(f)) &&
     !sit.disabled_features.includes('horz_touch_drag_scroll') && !sit.disabled_features.includes('pinch_scale'),
     'sitio: la rueda y el deslizamiento vertical son de la página; un dedo mueve y dos acercan');
  ok(!('load_last_chart' in sit) && !('auto_save_delay' in sit), 'sitio: no abre ni guarda gráficos solo');
  ok(JSON.stringify(sit.compare_symbols) === '[{"symbol":"palta-nominal","title":"Palta, nominal"}]',
     'sitio: símbolos a mano en Comparar');
  ok([esc, mov, sit].every(x => x.time_scale && x.time_scale.min_bar_spacing <= 0.1),
     'toda la historia cabe en pantallas angostas');

  // ---- la ficha: su producto y su serie, sin esperar el catálogo ----
  const pedidos2 = [];
  const p0 = CAT.productos[0], j0 = leer(path.join('datos', 'productos', p0.slug + '.json'));
  const feed2 = TV.crearDatafeed({ indices: INDICES,
    productos: [{ slug: p0.slug, nombre: p0.nombre, unidad: p0.unidad }],
    precargados: { ['productos/' + p0.slug + '.json']: { t0: j0.t0, v: j0.v, min: j0.min, max: j0.max } },
    // el catálogo nunca llega
    pedir: r => { pedidos2.push(r); return r === 'catalogo.json' ? new Promise(() => {}) :
      Promise.resolve(leer(path.join('datos', r))); } });
  await llamar(res => feed2.onReady(res));
  const i2 = await llamar((res, rej) => feed2.resolveSymbol(p0.slug, res, rej));
  const b2 = await llamar((res, rej) => feed2.getBars(i2, '1W', { from: 0, to: 4e9, countBack: 2000,
    firstDataRequest: true }, b => res(b), rej));
  ok(i2.ticker === p0.slug && b2.length === j0.v.filter(x => x != null).length &&
     b2[b2.length - 1].close === p0.precio_pesos_hoy, 'ficha: su producto sin esperar el catálogo');
  ok(JSON.stringify(pedidos2) === '["catalogo.json"]', 'ficha: la serie precargada no se pide');

  ok(pedidos.every(r => /^(catalogo\.json|indices\/[a-z0-9_-]+\.json|productos\/[a-z0-9-]+\.json)$/.test(r)),
     'solo lee archivos de datos/');

  console.log(`datafeed: ${chequeos - fallas}/${chequeos} chequeos OK; ` +
    `${CODES.length} índices y ${CAT.productos.length} productos, cada uno en pesos de hoy y nominal; ` +
    `${semanasProd - sinFactor} de ${semanasProd} semanas de producto con nominal ` +
    `(${sinFactor} sin índice publicado ese mes); factor mensual con error máximo de $${maxErr}`);
  process.exit(fallas ? 1 : 0);
})().catch(e => { console.log('FALLA ' + (e && e.stack || e)); process.exit(1); });

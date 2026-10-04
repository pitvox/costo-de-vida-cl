// Pruebas del datafeed de Advanced Charts (carestia-tv.js) contra un build
// de build_site.py, sin la librería: se lo llama como lo hace ella
// (onReady, searchSymbols, resolveSymbol y getBars con paginado por
// countBack) y se compara cada barra con indices.json y datos/.
//
//   node tests/feed_node.js DIR_DEL_BUILD
//
// DIR_DEL_BUILD es donde corrió build_site.py (indices.json, datos/ y
// carestia-tv.js). Lo llama tests/test_tradingview.py con datos sintéticos
// (con y sin datos/uf.json) y con el indices.json real de carestia.cl. Si el
// build trae datos/uf.json, prueba también los símbolos en UF. Además de las
// semanas, prueba cada temporalidad (2W, 1M, 3M, 6M y 12M) contra una
// agrupación hecha aquí, aparte. Termina con código 1 si algo falla.
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
const UFJ = fs.existsSync(path.join(dir, 'datos', 'uf.json')) ? leer(path.join('datos', 'uf.json')) : null;
const UNIDADES = UFJ ? ['real', 'epoca', 'uf'] : ['real', 'epoca'];
const SUF = { real: '', epoca: '-epoca', uf: '-uf' };
const RES = ['1W', '2W', '1M', '3M', '6M', '12M'];

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
  indices: INDICES, uf: !!UFJ,
  pedir: r => { pedidos.push(r); return Promise.resolve(leer(path.join('datos', r))); },
});

// la librería pide la historia hacia atrás: el primer pedido termina "ahora"
// y los siguientes en la barra más antigua recibida, hasta noData
async function historia(info, porPedido, resolucion) {
  let to = Math.floor(Date.UTC(2100, 0, 1) / 1000), out = [], vueltas = 0, primero = true;
  for (;;) {
    const r = await llamar((res, rej) => feed.getBars(info, resolucion || '1W',
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

function velas(bars, t, enUF) {
  ok(bars.every(b => lunes(b.time)), t + ': cada barra a las 00:00 UTC de un lunes');
  ok(bars.every((b, i) => !i || b.time > bars[i - 1].time), t + ': barras en orden y sin repetir');
  // (ODEPA trae algunas semanas de 2009 con mínimo 0: la mecha llega a 0)
  if (enUF) ok(bars.every(b => [b.open, b.high, b.low, b.close].every(x => x >= 0 && x < 100) && b.close > 0),
     t + ': en UF, cifras chicas y no negativas');
  else ok(bars.every(b => [b.open, b.high, b.low, b.close].every(Number.isInteger)),
     t + ': pesos sin decimales');
  ok(bars.every(b => b.low <= Math.min(b.open, b.close) && b.high >= Math.max(b.open, b.close)),
     t + ': mínimo y máximo envuelven el cuerpo');
  ok(bars.every((b, i) => !i || b.open === bars[i - 1].close), t + ': apertura = cierre de la semana anterior');
}

// ---- temporalidades, hechas aquí aparte: cada semana va al período del
// lunes en que empieza; los meses se cuentan desde enero y las semanas desde
// el primer lunes del año, de nuevo cada año ----
function primerLunes(y) {
  let d = Date.UTC(y, 0, 1);
  while (new Date(d).getUTCDay() !== 1) d += 864e5;
  return d;
}
function claveDe(ms, res) {
  const n = Number(res.slice(0, -1)), d = new Date(ms), y = d.getUTCFullYear();
  if (res.endsWith('M')) return Date.UTC(y, Math.floor(d.getUTCMonth() / n) * n, 1);
  const a = primerLunes(y);
  return a + Math.floor((ms - a) / (n * semana)) * n * semana;
}
function agrupadas(semanales, res) {
  if (res === '1W') return semanales;
  const grupos = [];
  semanales.forEach(b => {
    const k = claveDe(b.time, res), g = grupos[grupos.length - 1];
    if (g && g.k === k) g.b.push(b); else grupos.push({ k, b: [b] });
  });
  return grupos.map(g => ({ time: g.k, open: g.b[0].open, high: Math.max(...g.b.map(x => x.high)),
    low: Math.min(...g.b.map(x => x.low)), close: g.b[g.b.length - 1].close }));
}
function anclas(bars, res, t) {
  const n = Number(res.slice(0, -1));
  ok(bars.every(b => b.time % 864e5 === 0), t + ' ' + res + ': a las 00:00 UTC');
  ok(bars.every((b, i) => !i || b.time > bars[i - 1].time), t + ' ' + res + ': en orden y sin repetir');
  if (res.endsWith('M')) {
    ok(bars.every(b => new Date(b.time).getUTCDate() === 1 && new Date(b.time).getUTCMonth() % n === 0),
       t + ' ' + res + ': el día 1 de un mes múltiplo de ' + n + ' contado desde enero');
  } else {
    ok(bars.every(b => lunes(b.time) &&
       (b.time - primerLunes(new Date(b.time).getUTCFullYear())) % (n * semana) === 0),
       t + ' ' + res + ': un lunes, de a ' + n + ' semanas desde el primer lunes del año');
  }
}
// las barras de una temporalidad: idénticas a las semanas agrupadas aquí, y
// cada semana en exactamente un período
async function temporalidades(info, semanales, t, completo) {
  for (const res of RES.slice(1)) {
    const esperado = agrupadas(semanales, res);
    const b = completo ? await historia(info, 150, res) : await feed.barras(info.ticker, res);
    anclas(b, res, t);
    ok(JSON.stringify(b) === JSON.stringify(esperado), t + ' ' + res + ': las semanas agrupadas, idénticas');
    ok(b.every(x => x.low <= Math.min(x.open, x.close) && x.high >= Math.max(x.open, x.close)),
       t + ' ' + res + ': mínimo y máximo envuelven el cuerpo');
    const inicios = new Set(b.map(x => x.time));
    ok(semanales.every(s => inicios.has(claveDe(s.time, res))), t + ' ' + res + ': cada semana en un período');
  }
}

(async () => {
  // ---- onReady ----
  const conf = await llamar(res => feed.onReady(res));
  ok(JSON.stringify(conf.supported_resolutions) === JSON.stringify(RES), 'onReady: 1S, 2S, 1M, 3M, 6M y 12M');
  ok(conf.supports_time === false && conf.supports_marks === false, 'onReady: sin hora ni marcas');

  // ---- símbolos ----
  const lista = await feed.lista();
  const tickers = lista.map(s => s.ticker);
  ok(new Set(tickers).size === tickers.length, 'tickers únicos');
  ok(tickers.every(t => /^[a-z0-9-]+$/.test(t)), 'tickers sin paréntesis ni dos puntos');
  ok(lista.length === UNIDADES.length * (CODES.length + CAT.productos.length),
     'cada serie en ' + UNIDADES.join(', ') + ': ' + lista.length);
  ok(!tickers.some(t => /nominal/.test(t)), 'sin "nominal" en los tickers');
  CODES.forEach(c => ok(UNIDADES.every(u => tickers.includes(c + SUF[u])), 'índice ' + c));
  CAT.productos.forEach(p => ok(UNIDADES.every(u => tickers.includes(p.slug + SUF[u])),
    'producto con el slug de su ficha: ' + p.slug));
  ok(UFJ || !tickers.some(t => /-uf$/.test(t)), 'sin datos/uf.json no hay símbolos en UF');

  // ---- resolveSymbol ----
  const LARGO = { real: ', en pesos de hoy', epoca: ', precio de la época', uf: ', en UF' };
  const CORTO = { real: '', epoca: ', precio de la época', uf: ', en UF' };
  for (const s of lista) {
    const info = await llamar((res, rej) => feed.resolveSymbol(s.ticker, res, rej));
    const t = s.ticker, uf = s.unidad === 'uf';
    ok(info.name === t && info.ticker === t, t + ': name y ticker = slug');
    ok(info.minmov === 1 && info.pricescale === (uf ? 10000 : 1) && info.currency_code === (uf ? 'UF' : 'CLP'),
       t + (uf ? ': UF con hasta 4 decimales' : ': CLP sin decimales'));
    ok(info.timezone === 'America/Santiago' && info.session === '24x7', t + ': zona');
    ok(JSON.stringify(info.supported_resolutions) === JSON.stringify(RES) && info.has_weekly_and_monthly === true
       && JSON.stringify(info.weekly_multipliers) === '["1","2"]'
       && JSON.stringify(info.monthly_multipliers) === '["1","3","6","12"]'
       && info.has_intraday === false && info.has_daily === false, t + ': semanas y meses');
    ok(info.visible_plots_set === 'ohlc', t + ': velas en índices y productos');
    // nombre corto (leyenda del celular) y largo (pantallas anchas y búsqueda)
    ok(info.long_description === s.descripcion && info.long_description.endsWith(LARGO[s.unidad]),
       t + ': descripción larga en español');
    ok(info.description === s.corto && info.description.length < info.long_description.length &&
       (CORTO[s.unidad] ? info.description.endsWith(CORTO[s.unidad]) : !/, (en|precio)/.test(info.description)),
       t + ': nombre corto');
  }
  const asado = await llamar((res, rej) => feed.resolveSymbol('Carestía:' + CODES[0].toUpperCase(), res, rej));
  ok(asado.ticker === CODES[0], 'resolveSymbol tolera prefijo de fuente y mayúsculas');
  const viejo = await llamar((res, rej) => feed.resolveSymbol(CODES[0] + '-nominal', res, rej));
  ok(viejo.ticker === CODES[0] + '-epoca', 'el sufijo -nominal de antes abre el precio de la época');
  let error = null;
  await llamar((res, rej) => feed.resolveSymbol('no-existe', res, rej)).catch(e => { error = e; });
  ok(typeof error === 'string', 'símbolo desconocido: onError');

  // ---- la UF de cada lunes ----
  const ufMap = new Map();
  if (UFJ) UFJ.v.forEach((x, i) => { if (x > 0) ufMap.set(ms(UFJ.t0) + i * semana, x); });
  // en UF: la vela a precio de la época dividida por la UF de su lunes; la
  // apertura es el cierre anterior en UF
  const enUF = epoca => {
    const out = [];
    epoca.forEach(b => {
      const u = ufMap.get(b.time);
      if (!u) return;
      const c = b.close / u, o = out.length ? out[out.length - 1].close : c;
      out.push({ time: b.time, open: o, high: Math.max(o, c, b.high / u), low: Math.min(o, c, b.low / u), close: c });
    });
    return out;
  };
  let semanasUF = 0, semanasSinUF = 0;

  // ---- getBars: índices ----
  for (const c of CODES) {
    const d = DATA.indices[c];
    const real = await historia(await feed.info(c), 150);
    velas(real, c);
    ok(JSON.stringify(real) === JSON.stringify(d.velas.map(v =>
      ({ time: ms(v.time), open: v.open, high: v.high, low: v.low, close: v.close }))),
      c + ': las velas de indices.json, idénticas');
    const epoca = await historia(await feed.info(c + '-epoca'), 150);
    velas(epoca, c + '-epoca');
    ok(JSON.stringify(epoca.map(b => [b.time, b.close])) ===
       JSON.stringify(d.nominal.map(p => [ms(p.time), p.value])), c + '-epoca: cierre = nominal publicado');
    // la mecha a precio de la época es la real llevada a pesos de esa semana
    const porT = new Map(real.map(b => [b.time, b]));
    ok(epoca.every(b => {
      const r = porT.get(b.time), k = b.close / r.close;
      return Math.abs(Math.max(b.open, b.close, r.high * k) - b.high) <= 1 &&
             Math.abs(Math.min(b.open, b.close, r.low * k) - b.low) <= 1;
    }), c + '-epoca: mecha = mínimo y máximo reales en pesos de la semana');
    await temporalidades(await feed.info(c), real, c, true);
    await temporalidades(await feed.info(c + '-epoca'), epoca, c + '-epoca', true);
    if (UFJ) {
      const uf = await historia(await feed.info(c + '-uf'), 150);
      velas(uf, c + '-uf', true);
      ok(JSON.stringify(uf) === JSON.stringify(enUF(epoca)), c + '-uf: precio de la época / UF del lunes');
      ok(uf.length === epoca.length, c + '-uf: la UF cubre todas sus semanas');
      await temporalidades(await feed.info(c + '-uf'), uf, c + '-uf', true);
    }
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
  for (const [n, f] of CAT.productos.entries()) {
    const p = leer(path.join('datos', 'productos', f.slug + '.json'));
    const esperado = [];
    p.v.forEach((v, i) => { if (v != null) esperado.push({ time: ms(p.t0) + i * semana, v, i }); });
    const real = await historia(await feed.info(f.slug), 400);
    velas(real, f.slug);
    // la vela: cuerpo desde el cierre de la semana anterior, mecha con el rango de ODEPA
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
    const epoca = await historia(await feed.info(f.slug + '-epoca'), 400);
    velas(epoca, f.slug + '-epoca');
    const conFactor = esperado.filter(e => factor.has(new Date(e.time).toISOString().slice(0, 7)));
    sinFactor += esperado.length - conFactor.length;
    semanasProd += esperado.length;
    ok(JSON.stringify(epoca.map(b => [b.time, b.close])) === JSON.stringify(conFactor.map(e => {
      const g = factor.get(new Date(e.time).toISOString().slice(0, 7));
      return [e.time, Math.round(e.v * g[0] / g[1])];
    })), f.slug + '-epoca: precio de hoy por el factor del mes');
    // las temporalidades: todas por getBars en algunos; en el resto, directo
    const completo = n % 25 === 0;
    await temporalidades(await feed.info(f.slug), real, f.slug, completo);
    await temporalidades(await feed.info(f.slug + '-epoca'), epoca, f.slug + '-epoca', completo);
    if (UFJ) {
      const uf = await feed.barras(f.slug + '-uf');
      velas(uf, f.slug + '-uf', true);
      ok(JSON.stringify(uf) === JSON.stringify(enUF(epoca)), f.slug + '-uf: precio de la época / UF del lunes');
      semanasUF += uf.length;
      semanasSinUF += epoca.length - uf.length;
      await temporalidades(await feed.info(f.slug + '-uf'), uf, f.slug + '-uf', completo);
    }
  }
  if (UFJ) ok(semanasSinUF === 0, 'la UF cubre todas las semanas de producto (' + semanasSinUF + ' sin UF)');

  // ---- otras resoluciones y búsqueda ----
  for (const r of ['1D', '60', '4W', '2M', '24M']) {
    const x = await llamar((res, rej) => feed.getBars(asado, r,
      { from: 0, to: 4e9, countBack: 10, firstDataRequest: true }, (b, m) => res({ b, m }), rej));
    ok(!x.b.length && x.m.noData, 'temporalidad ' + r + ' fuera de la lista: noData');
  }
  const w = await llamar((res, rej) => feed.getBars(asado, 'W',
    { from: 0, to: 4e9, countBack: 3, firstDataRequest: true }, b => res(b), rej));
  const w1 = await llamar((res, rej) => feed.getBars(asado, '1W',
    { from: 0, to: 4e9, countBack: 3, firstDataRequest: true }, b => res(b), rej));
  ok(w.length > 3 && JSON.stringify(w) === JSON.stringify(w1), '"W" es lo mismo que "1W"');
  const buscar = (q, tipo) => llamar(res => feed.searchSymbols(q, '', tipo || '', res));
  const r1 = await buscar('indice');
  ok(r1.length === UNIDADES.length * CODES.length, 'búsqueda sin tildes: "indice" encuentra los índices');
  ok(r1.every(r => r.symbol === r.ticker && !('full_name' in r) && !/[:()]/.test(r.ticker)
     && r.exchange === 'Carestía' && r.type === 'index'), 'resultados con el ticker y la fuente');
  const r2 = await buscar(INDICES[0].nombre.replace('Índice ', '').toLowerCase() + ' ÉPOCA');
  ok(r2.length >= 1 && r2.every(r => /-epoca$/.test(r.ticker)), 'búsqueda con varias palabras');
  if (UFJ) {
    const r4 = await buscar(CODES[0] + ' en uf');
    ok(r4.some(r => r.ticker === CODES[0] + '-uf') && r4.every(r => /-uf$/.test(r.ticker)), 'búsqueda en UF');
  }
  const r3 = await buscar('', 'commodity');
  ok(r3.length === UNIDADES.length * CAT.productos.length, 'filtro por tipo: productos');
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
  // la UF: coma decimal, 2 decimales desde 1 UF y 4 bajo 1 UF
  const casosUF = [[1.234, '1,23'], [12.3456, '12,35'], [0.66923, '0,6692'], [0.0089123, '0,0089'],
    [0.99996, '1,00'], [0.99994, '0,9999'], [1234.5, '1.234,50'], [-0.5, '-0,5000'], [-0.00001, '0,0000']];
  ok(casosUF.every(([x, t]) => TV.numUF(x) === t), 'UF: ' + casosUF.map(([x]) => TV.numUF(x)).join(' '));
  ok(TV.textoUF(0.0089123) === '0,0089 UF' && TV.textoUF(1.5) === '1,50 UF', 'UF con la sigla');
  const fUF = f.priceFormatterFactory({ ticker: 'asado-uf', currency_code: 'UF' }, '1');
  ok(fUF.format(0.66923) === '0,6692' && fUF.format(0.01, { signPositive: true }) === '+0,0100',
     'el eje de un símbolo en UF, con decimales');
  ok(f.priceFormatterFactory({ ticker: 'asado-epoca', currency_code: 'CLP' }, '1').format(26467.4) === '26.467',
     'el eje en pesos, sin decimales');

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
  ok(ov['mainSeriesProperties.style'] === 2 && ov['mainSeriesProperties.lineStyle.color'] === TOK.ember,
     'widget: línea por defecto, en brasa para los índices');
  ok(o.interval === '1W' && JSON.stringify(o.favorites.intervals) === JSON.stringify(RES) &&
     JSON.stringify(o.favorites.chartTypes) === '["Line","Candles"]',
     'widget: 1S por defecto; las temporalidades, la línea y las velas a un clic');
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
    comparar: [{ symbol: 'palta-epoca', title: 'Palta, precio de la época' }] }, base));
  const leyenda = x => ['symbolTextSource', 'showInterval', 'showExchange']
    .map(k => x.overrides['mainSeriesProperties.statusViewStyle.' + k]).join(',');
  ok(leyenda(esc) === 'long-description,true,true', 'escritorio: leyenda con el nombre largo');
  ok(leyenda(mov) === 'description,false,false', 'celular: leyenda con el nombre corto, sin intervalo ni fuente');
  ok(['header_symbol_search', 'header_settings', 'header_undo_redo',
      'header_quick_search', 'header_screenshot', 'header_saveload'].every(f => mov.disabled_features.includes(f)),
     'celular: sin lo que no cabe');
  ok(!mov.disabled_features.includes('header_resolutions') && !sit.disabled_features.includes('header_resolutions'),
     'celular y sitio: el selector de temporalidades se ve');
  ok(!['header_compare', 'header_indicators', 'header_chart_type', 'header_fullscreen_button',
       'left_toolbar', 'header_widget'].some(f => mov.disabled_features.includes(f) ||
       sit.disabled_features.includes(f)),
     'celular y sitio: quedan comparar, indicadores, tipo de gráfico, dibujo y pantalla completa');
  ok(['header_symbol_search', 'symbol_search_hot_key', 'header_saveload', 'vert_touch_drag_scroll']
      .every(f => sit.disabled_features.includes(f)) &&
     ['mouse_wheel_scale', 'mouse_wheel_scroll', 'horz_touch_drag_scroll', 'pinch_scale']
      .every(f => !sit.disabled_features.includes(f)),
     'sitio: la rueda acerca y mueve el gráfico; el deslizamiento vertical es de la página; dos dedos acercan');
  ok(!('load_last_chart' in sit) && !('auto_save_delay' in sit), 'sitio: no abre ni guarda gráficos solo');
  ok(JSON.stringify(sit.compare_symbols) === '[{"symbol":"palta-epoca","title":"Palta, precio de la época"}]',
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
  // la ficha en UF: pide la UF y los índices (el factor de la época), nunca su serie
  if (UFJ) {
    const feed3 = TV.crearDatafeed({ indices: INDICES, uf: true,
      productos: [{ slug: p0.slug, nombre: p0.nombre, unidad: p0.unidad }],
      precargados: { ['productos/' + p0.slug + '.json']: { t0: j0.t0, v: j0.v, min: j0.min, max: j0.max } },
      pedir: r => { pedidos2.push(r); return r === 'catalogo.json' ? new Promise(() => {}) :
        Promise.resolve(leer(path.join('datos', r))); } });
    const b3 = await feed3.barras(p0.slug + '-uf');
    ok(b3 && b3.length && JSON.stringify(b3) === JSON.stringify(await feed.barras(p0.slug + '-uf')),
       'ficha: su producto en UF sin esperar el catálogo');
    ok(!pedidos2.includes('productos/' + p0.slug + '.json') && pedidos2.includes('uf.json'),
       'ficha: en UF pide datos/uf.json y no su serie');
  }

  ok(pedidos.every(r => /^(catalogo\.json|uf\.json|indices\/[a-z0-9_-]+\.json|productos\/[a-z0-9-]+\.json)$/.test(r)),
     'solo lee archivos de datos/');
  ok(pedidos.filter(r => r === 'uf.json').length === (UFJ ? 1 : 0), 'datos/uf.json se pide una vez, y solo si hay UF');

  console.log(`datafeed: ${chequeos - fallas}/${chequeos} chequeos OK; ` +
    `${CODES.length} índices y ${CAT.productos.length} productos, cada uno en ${UNIDADES.join(', ')} ` +
    `y en ${RES.join(', ')}; ` +
    `${semanasProd - sinFactor} de ${semanasProd} semanas de producto con precio de la época ` +
    `(${sinFactor} sin índice publicado ese mes); factor mensual con error máximo de $${maxErr}` +
    (UFJ ? `; ${semanasUF} semanas de producto en UF (${UFJ.fuente}, UF del ${UFJ.t0} en adelante)` : '; sin UF'));
  process.exit(fallas ? 1 : 0);
})().catch(e => { console.log('FALLA ' + (e && e.stack || e)); process.exit(1); });

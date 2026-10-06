// Pruebas, sin navegador, del componente común de Comparar (JS_COMPARAR de
// build_site.py, el mismo en /graficos.html y en las fichas) y del tramo, la
// escala y la frase de "Comparar con" de las fichas (JS_FRASE). El JS lo
// extrae tests/test_comparar.py de build_site.py; aquí se le pasan gráficos
// de mentira que anotan lo que se les pide, como lo haría la librería.
//
//   node tests/comparar_node.js ARCHIVO   (JSON: { comparar, frase })
//
// Termina con código 1 si algo falla.
'use strict';
const fs = require('fs');

const js = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let fallas = 0, chequeos = 0;
function ok(cond, msg) {
  chequeos++;
  if (!cond) { fallas++; console.log('FALLA ' + msg); }
}
const igual = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b),
  msg + ': ' + JSON.stringify(a) + ' en vez de ' + JSON.stringify(b));

// Lightweight de mentira: solo lo que usa el componente
const LightweightCharts = { LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 } };
const { comparador, ONOTE, fmtPct } = new Function('LightweightCharts',
  js.comparar + '\nreturn { comparador, ONOTE, fmtPct };')(LightweightCharts);
const F = new Function(js.frase + '\nreturn { escalaVisible, textoEscala, semanasPropias, ' +
  'tramoPropio, fraseTramo, cifraTramo, enSemanasDe, fechaTxt };')();

const COLORES = ['c1', 'c2', 'c3', 'c4'];
const esperar = () => new Promise(r => setTimeout(r, 0));

// ---------- la elección: colores por orden de selección ----------
{
  const cmp = comparador({ colores: COLORES, max: 8, simbolo: k => k });
  ['a', 'b', 'c'].forEach(k => cmp.elegir(k));
  igual(['a', 'b', 'c'].map(k => cmp.estilo(k).color), ['c1', 'c2', 'c3'], 'colores por orden');
  cmp.soltar('b');
  ok(cmp.elegir('d'), 'elige d');
  // d toma el primer puesto libre (el de b) y los que estaban no cambian
  igual(cmp.estilo('d'), { color: 'c2', punteada: false }, 'd toma el puesto libre');
  igual(cmp.estilo('c'), { color: 'c3', punteada: false }, 'c no cambia');
  igual(cmp.claves(), ['a', 'd', 'c'], 'claves en el orden de los puestos');
  ['e', 'f', 'g', 'h', 'i'].forEach(k => cmp.elegir(k));
  igual(cmp.estilo('f'), { color: 'c1', punteada: true }, 'del 5º en adelante, punteada');
  ok(cmp.lleno() && !cmp.elegir('j') && !cmp.tiene('j'), 'con el máximo no entra otra');
  ok(cmp.alternar('a') && !cmp.tiene('a') && !cmp.lleno(), 'alternar suelta');
  ok(cmp.alternar('j') && cmp.estilo('j').color === 'c1', 'alternar elige en el puesto libre');
  ok(!cmp.elegir('j'), 'no se elige dos veces');
  cmp.vaciar();
  igual(cmp.claves(), [], 'vaciar');
}

// ---------- el botón muestra el estilo de su línea ----------
{
  const boton = () => {
    const clases = new Set(), attrs = {};
    return { style: {}, attrs, clases,
      dot: { style: {} },
      classList: { toggle: (c, on) => (on ? clases.add(c) : clases.delete(c)) },
      setAttribute: (k, v) => { attrs[k] = v; },
      querySelector() { return this.dot; } };
  };
  const cmp = comparador({ colores: COLORES, max: 5, simbolo: k => k });
  ['a', 'b', 'c', 'd', 'e'].forEach(k => cmp.elegir(k));
  const a = boton(), e = boton(), x = boton();
  cmp.pintar(a, 'a'); cmp.pintar(e, 'e'); cmp.pintar(x, 'x');
  ok(a.clases.has('active') && a.attrs['aria-pressed'] === 'true', 'elegido: activo');
  ok(a.dot.style.background === 'c1' && a.style.borderColor === 'c1', 'elegido: su color');
  ok(e.dot.style.background === 'transparent' && e.style.borderStyle === 'dashed' &&
     e.dot.style.boxShadow === 'inset 0 0 0 2px c1', 'punteada: anillo y borde de guiones');
  ok(!x.clases.has('active') && x.attrs['aria-pressed'] === 'false' && x.style.opacity === '.4',
     'con el máximo, los demás atenuados');
}

// ---------- Advanced Charts: la comparación de la librería ----------
function grafico(simbolo) {
  const log = [];
  let sim = simbolo, tipo = 1, modo = 0, n = 0, visible = true;
  const estudios = new Map();
  const c = {
    symbol: () => sim.toUpperCase(),
    setSymbol: s => { log.push('setSymbol ' + s); sim = s; return Promise.resolve(); },
    getSeries: () => ({ setVisible: v => { visible = v; } }),
    chartType: () => tipo,
    setChartType: t => { log.push('tipo ' + t); tipo = t; return Promise.resolve(); },
    createStudy: (nombre, a, b, entrada, estilo) => {
      const id = 'e' + (++n);
      estudios.set(id, { nombre, entrada, estilo });
      log.push('compara ' + entrada.symbol + ' ' + estilo['plot.color'] +
        (estilo['plot.linestyle'] ? ' punteada' : ''));
      return Promise.resolve(id);
    },
    removeEntity: id => { log.push('quita ' + estudios.get(id).entrada.symbol); estudios.delete(id); },
    getPanes: () => [{ getMainSourcePriceScale: () => ({ getMode: () => modo,
      setMode: m => { log.push('escala ' + m); modo = m; } }) }],
  };
  const overrides = [];
  const w = { activeChart: () => c, applyOverrides: o => overrides.push(o) };
  return { w, log, overrides, estudios, visible: () => visible, modo: () => modo };
}

async function pruebasTV() {
  // /graficos.html: sin principal fija, la primera elegida es la serie
  // principal y lleva su color
  {
    let unidad = '';
    const cmp = comparador({ colores: COLORES, max: 8, simbolo: k => k + unidad });
    const g = grafico('x');
    ['a', 'b', 'c'].forEach(k => cmp.elegir(k));
    await cmp.tv(g.w);
    igual(g.log, ['setSymbol a', 'tipo 2', 'compara b c2', 'compara c c3', 'escala 2'],
      'Comparar: la primera es la principal');
    ok(g.overrides[0]['mainSeriesProperties.lineStyle.color'] === 'c1', 'la principal con su color');
    g.log.length = 0;
    cmp.soltar('a');
    await cmp.tv(g.w);
    igual(g.log, ['quita b', 'setSymbol b'], 'al soltar la primera, la siguiente pasa a principal');
    g.log.length = 0;
    unidad = '-epoca';
    await cmp.tv(g.w);
    igual(g.log, ['quita c', 'setSymbol b-epoca', 'compara c-epoca c3'],
      'otra unidad: se rehacen las comparaciones');
    cmp.vaciar();
    await cmp.tv(g.w);
    ok(!g.visible() && g.estudios.size === 0, 'sin elegidos: la serie se oculta');
  }
  // la ficha: la serie principal es el producto de la ficha, en hueso (no la
  // toca), y sin comparados queda en precios
  {
    let unidad = '';
    const cmp = comparador({ colores: COLORES, max: 4, simbolo: k => k + unidad,
      principal: () => 'palta' + unidad });
    const g = grafico('palta');
    await cmp.tv(g.w);
    igual(g.log, [], 'la ficha sola: nada que comparar');
    ok(g.visible() && g.modo() === 0, 'la ficha sola, en precios');
    cmp.elegir('pera'); cmp.elegir('asado');
    // dos clics seguidos van en fila
    cmp.tv(g.w);
    await cmp.tv(g.w);
    igual(g.log, ['tipo 2', 'compara pera c1', 'compara asado c2', 'escala 2'],
      'la ficha: cada comparada con su color, en porcentaje');
    ok(g.overrides.length === 0, 'el color del producto de la ficha no cambia');
    g.log.length = 0;
    unidad = '-epoca';
    await cmp.tv(g.w);
    igual(g.log, ['quita pera', 'quita asado', 'setSymbol palta-epoca', 'compara pera-epoca c1',
      'compara asado-epoca c2'], 'la ficha en otra unidad');
    g.log.length = 0;
    cmp.vaciar();
    await cmp.tv(g.w);
    igual(g.log, ['quita pera-epoca', 'quita asado-epoca'], 'sin comparados se quitan todas');
    ok(g.visible(), 'el producto de la ficha sigue a la vista');
  }
}

// ---------- Lightweight: una línea por serie ----------
async function pruebasLW() {
  const series = [];
  const ch = {
    addLineSeries: o => { const s = { o, datos: null, setData(d) { this.datos = d; } }; series.push(s); return s; },
    removeSeries: s => { series.splice(series.indexOf(s), 1); },
    priceScale: () => ({ applyOptions() {} }),
    timeScale: () => ({ fitContent() {} }),
  };
  const cmp = comparador({ colores: COLORES, max: 8, simbolo: k => k });
  ['a', 'b', 'c', 'd', 'e'].forEach(k => cmp.elegir(k));
  const pedidos = [];
  let fallo = null, dibujos = 0;
  const x = u => ({ unidad: u, puntos: (k, uu) => {
    pedidos.push(k + ':' + uu);
    return uu === 'mala' ? Promise.reject(new Error('sin')) : Promise.resolve([{ time: '2026-01-05', value: 1 }]);
  }, alFallar: (uu, d) => { fallo = [uu, d]; }, alDibujar: () => { dibujos++; } });
  cmp.lw(ch, x('real'));
  await esperar();
  ok(series.length === 5 && series.every(s => s.datos), 'una línea por elegida, con sus datos');
  ok(series[4].o.lineStyle === LightweightCharts.LineStyle.Dotted && series[0].o.color === 'c1',
     'color y trazo de su puesto');
  ok(dibujos === 5, 'avisa al dibujar');
  cmp.soltar('b');
  pedidos.length = 0;
  cmp.lw(ch, x('real'));
  await esperar();
  ok(series.length === 4 && pedidos.length === 0, 'al soltar se quita su línea, sin pedir de nuevo');
  cmp.lw(ch, x('mala'));
  await esperar();
  igual(fallo, ['mala', 'real'], 'sin los puntos de esa unidad, vuelve a la dibujada');
}

// ---------- la escala y la frase ----------
const DIA = 864e5, SEM = 7 * DIA;
const lunes = s => Date.parse(s + 'T00:00:00Z');
const semanas = (ini, vals) => vals.map((v, i) => v == null ? null :
  { time: lunes(ini) + i * SEM, close: v }).filter(Boolean);
const texto = f => f.map(x => x.texto || '').join('');
function pruebasEscala() {
  // la escala explica lo que dibuja la librería: cada línea parte en 0% en la
  // primera barra a la vista, con el último precio de cada serie hasta ahí
  const P = semanas('2008-01-07', [100, 110, 120, 130, 125]);
  const pera = semanas('2008-01-07', [50, null, 55, 60, 40]);
  const tarde = semanas('2008-01-21', [10, 12, 15]);                // parte en la 3ª barra
  const vieja = semanas('2007-12-03', [7, 7]);                       // de antes, plana
  const e = F.escalaVisible(P, [pera, tarde, vieja, []], 0, Infinity);
  ok(e.t0 === lunes('2008-01-07') && e.base === 100, 'la escala parte en la primera barra a la vista');
  igual(e.partes, [null, lunes('2008-01-21'), null, null], 'solo parte después la que no tiene precio antes');
  igual(F.textoEscala(e, ['Palta', 'Pera', 'Aceite', 'Vieja', 'Otra']),
    'Todas las líneas parten en 0% el 07-01-2008, menos Aceite, que parte en su primer precio, ' +
    'el 21-01-2008.', 'la escala con una que parte después');
  igual(F.textoEscala(F.escalaVisible(P, [pera], 0, Infinity), ['Palta', 'Pera']),
    'Todas las líneas parten en 0% el 07-01-2008.', 'la escala del pedido');
  const dos = F.escalaVisible(P, [tarde, semanas('2008-01-28', [3, 4])], 0, Infinity);
  igual(F.textoEscala(dos, ['Palta', 'Aceite', 'Miel']),
    'Todas las líneas parten en 0% el 07-01-2008, menos Aceite (21-01-2008) y Miel ' +
    '(28-01-2008), que parten en su primer precio.', 'la escala con dos que parten después');
  const m = F.escalaVisible(P, [pera], lunes('2008-01-14'), lunes('2008-01-28') + 3 * DIA);
  ok(m.t0 === lunes('2008-01-14') && m.base === 110, 'un tramo a la mitad');
  ok(F.escalaVisible(P, [], lunes('2009-01-05'), lunes('2009-02-02')) === null, 'sin barras a la vista');
}

function pruebasFrase() {
  // la frase del pedido: "Desde [fecha], ajustado por inflación: Asado de
  // tira +38%, Palta −12%."
  const A = semanas('2008-01-07', [100, 138]), B = semanas('2008-01-07', [50, 44]);
  const series = [{ nombre: 'Asado de tira', color: 'h' }, { nombre: 'Palta', color: 'c1' }];
  const f = F.fraseTramo(F.tramoPropio(A, [B], 0, Infinity, true), series, 'ajustado por inflación');
  igual(texto(f), 'Desde 07-01-2008, ajustado por inflación: Asado de tira +38%, Palta −12%.', 'la frase');
  igual(f.filter(x => x.clase).map(x => x.texto + ' ' + x.clase), ['+38% v-sube', '−12% v-baja'],
    'las cifras en color con criterio de consumidor');
  igual(f.filter(x => x.muestra).map(x => x.muestra), ['h', 'c1'], 'el color de cada línea');
  // sin precio esta semana (o un tramo que no llega a hoy): del ... al ...
  igual(F.fraseTramo(F.tramoPropio(A, [B], 0, Infinity, false), series, 'a precio de la época')[0].texto,
    'Del 07-01-2008 al 14-01-2008, a precio de la época: ', 'sin precio esta semana: del ... al ...');

  // una comparada que empieza después del comienzo se mide desde su primer
  // dato y la frase lo dice: el año ("Palta −12% desde 2019") o, si es el
  // mismo año del comienzo, la fecha
  const ficha = semanas('2017-01-02', Array.from({ length: 200 }, (_, i) => 100 + i));
  const desde2019 = semanas('2019-01-07', [50].concat(Array(90).fill(47), [44]));
  const t1 = F.tramoPropio(ficha, [desde2019, semanas('2017-03-06', [10, 12])], 0, Infinity, true);
  igual(texto(F.fraseTramo(t1, [{ nombre: 'Asado de tira' }, { nombre: 'Palta' }, { nombre: 'Miel' }],
    'ajustado por inflación')),
    'Desde 02-01-2017, ajustado por inflación: Asado de tira +199%, Palta −12% desde 2019, ' +
    'Miel +20% desde el 06-03-2017 hasta la semana del 13-03-2017.', 'desde su primer dato, con su fecha');

  // si su último dato tiene más de 4 semanas, hasta ese dato, y lo dice
  const P = semanas('2026-01-05', Array.from({ length: 10 }, (_, i) => 1000 + 10 * i));   // al 09-03
  const hace4 = semanas('2026-01-05', [80, 81, 82, 83, 84, 88]);                           // al 09-02: 4 semanas
  const hace5 = semanas('2026-01-05', [80, 81, 82, 83, 90]);                               // al 02-02: 5 semanas
  const t2 = F.tramoPropio(P, [hace4, hace5], 0, Infinity, true);
  igual(t2.otras.map(x => x.hasta), [null, lunes('2026-02-02')], 'más de 4 semanas, hasta su último dato');
  igual(texto(F.fraseTramo(t2, [{ nombre: 'Palta' }, { nombre: 'A' }, { nombre: 'B' }], 'ajustado por inflación')),
    'Desde 05-01-2026, ajustado por inflación: Palta +9%, A +10%, B +13% hasta la semana del 02-02-2026.',
    'la frase dice hasta cuándo');

  // nunca el precio repetido de las semanas sin dato: las semanas que
  // indices.py completó (datos/repetidas/{slug}.json) no cuentan para nada
  const j = { t0: '2026-01-05', v: [100, 100, 100, 120, 130, 130] };
  const propias = F.semanasPropias(j, [1, 2, 5]);
  igual([...propias].map(F.fechaTxt), ['05-01-2026', '26-01-2026', '02-02-2026'],
    'las semanas propias: con precio y sin las repetidas');
  igual([...F.semanasPropias({ t0: '2026-01-05', v: [1, null, 3] }, [])].length, 2,
    'sin repetidas, toda semana con precio es propia');
  const todas = semanas('2026-01-05', j.v), solo = todas.filter(x => propias.has(x.time));
  // la ficha va del 12-01 en adelante: la semana repetida del 12-01 y la del
  // 19-01 no son base de nada; la comparada parte en su primer precio propio
  const t3 = F.tramoPropio(semanas('2026-01-12', [500, 505, 510, 515, 520]), [solo], lunes('2026-01-12'), Infinity, true);
  igual({ cambio: Math.round(t3.otras[0].cambio * 1000) / 1000, desde: t3.otras[0].desde },
    { cambio: 0.083, desde: lunes('2026-01-26') }, 'mide desde 120 (26-01), no desde el 100 repetido');
  // y termina en su último precio propio (130 del 02-02), no en el repetido del 09-02
  ok(Math.abs(t3.otras[0].cambio - (130 / 120 - 1)) < 1e-12, 'hasta el último precio propio');
  // la ficha, igual: sus semanas repetidas no son base ni final
  const fichaRep = semanas('2026-01-05', [100, 100, 100, 120, 130]);
  const t4 = F.tramoPropio(fichaRep.filter(x => propias.has(x.time)), [], 0, Infinity, true);
  ok(t4.t0 === lunes('2026-01-05') && t4.t1 === lunes('2026-02-02') &&
     Math.abs(t4.principal.cambio - 0.3) < 1e-12, 'la ficha con sus precios propios');

  // un tramo a la mitad: la ficha no llega a hoy y las comparadas se miden
  // hasta su último precio del tramo
  const t5 = F.tramoPropio(P, [hace4], lunes('2026-01-12'), lunes('2026-02-02') + 3 * DIA, true);
  igual(texto(F.fraseTramo(t5, [{ nombre: 'Palta' }, { nombre: 'A' }], 'ajustado por inflación')),
    'Del 12-01-2026 al 02-02-2026, ajustado por inflación: Palta +3%, A +4%.', 'un tramo a la mitad');
  // sin precios en el tramo y un solo precio
  const t6 = F.tramoPropio(P, [semanas('2025-01-06', [5, 6]), semanas('2026-02-16', [7])], 0, Infinity, true);
  igual(texto(F.fraseTramo(t6, [{ nombre: 'Palta' }, { nombre: 'Vieja' }, { nombre: 'Una' }], 'ajustado por inflación')),
    'Desde 05-01-2026, ajustado por inflación: Palta +9%, Vieja, sin precios en este tramo, ' +
    'Una, un solo precio en este tramo, la semana del 16-02-2026.', 'sin precios y un solo precio');
  ok(F.tramoPropio(P, [], lunes('2027-01-04'), Infinity, true) === null, 'sin precios de la ficha a la vista');
  // con la ficha al día, una comparada con precio después del último de la
  // ficha se mide hasta ese precio (el tramo llega a hoy)
  const t7 = F.tramoPropio(P.slice(0, 9), [semanas('2026-01-05', Array(10).fill(10).concat([20]))], 0,
    Infinity, true);
  ok(t7.hastaHoy && Math.abs(t7.otras[0].cambio - 1) < 1e-12 && t7.otras[0].hasta === null,
     'hasta hoy, con su precio más nuevo');

  igual([0.004, -0.004, 0.006, 12.344, -0.5].map(x => F.cifraTramo(x).texto),
    ['0%', '0%', '+1%', '+1.234%', '−50%'], 'las cifras');
  ok(!F.cifraTramo(0.004).clase, '0% sin color');

  // Lightweight: la comparada en las semanas de la ficha, como la dibuja
  // Advanced Charts (solo para el dibujo y la escala)
  const sem = [{ time: '2008-01-07', value: 1 }, { time: '2008-01-14' }, { time: '2008-01-21', value: 2 },
    { time: '2008-01-28', value: 3 }];
  igual(F.enSemanasDe(semanas('2008-01-14', [9, null, 8]), sem),
    [{ time: '2008-01-07' }, { time: '2008-01-14' }, { time: '2008-01-21', value: 9 },
      { time: '2008-01-28', value: 8 }], 'en las semanas de la ficha, con el último precio');

  // textos comunes
  ok(ONOTE.real === 'Cambio del precio ajustado por inflación, en porcentaje', 'la nota de Comparar');
  igual([fmtPct(39.984), fmtPct(-12.5), fmtPct(1234.5)], ['39,98%', '−12,50%', '1.234,50%'],
    'la escala porcentual de Lightweight');
}

(async () => {
  await pruebasTV();
  await pruebasLW();
  pruebasEscala();
  pruebasFrase();
  console.log(chequeos + ' chequeos, ' + fallas + ' fallas');
  if (fallas) process.exit(1);
  console.log('chequeos OK');
})().catch(e => { console.log('ERROR ' + (e && e.stack || e)); process.exit(1); });

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
const F = new Function(js.frase +
  '\nreturn { tramoVisible, textoEscala, fraseTramo, cifraTramo, enSemanasDe, fechaTxt };')();

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

// ---------- el tramo, la escala y la frase ----------
const DIA = 864e5, SEM = 7 * DIA;
const lunes = s => Date.parse(s + 'T00:00:00Z');
const semanas = (ini, vals) => vals.map((v, i) => v == null ? null :
  { time: lunes(ini) + i * SEM, close: v }).filter(Boolean);
function pruebasFrase() {
  const P = semanas('2008-01-07', [100, 110, 120, 130, 125]);
  const pera = semanas('2008-01-07', [50, null, 55, 60, 40]);
  const tarde = semanas('2008-01-21', [10, 12, 15]);              // parte en la 3ª semana
  const vieja = semanas('2007-12-03', [7, 7]);                     // sin precios en el tramo
  const t = F.tramoVisible(P, [pera, tarde, vieja, []], 0, Infinity);
  ok(t.t0 === lunes('2008-01-07') && t.t1 === lunes('2008-02-04') && t.ultima, 'el tramo completo');
  ok(t.base === 100 && Math.abs(t.cambio - 0.25) < 1e-12, 'la ficha: de su primera a su última barra');
  ok(Math.abs(t.otras[0].cambio - (40 / 50 - 1)) < 1e-12 && t.otras[0].parte === null,
     'una comparada desde la misma semana');
  ok(t.otras[1].parte === lunes('2008-01-21') && Math.abs(t.otras[1].cambio - 0.5) < 1e-12,
     'la que aún no tiene precio parte en el primero que tenga');
  ok(t.otras[2] === null && t.otras[3] === null, 'sin precios en el tramo: null');
  // un tramo a la mitad: el último precio publicado de cada una hasta ahí
  const m = F.tramoVisible(P, [pera], lunes('2008-01-14'), lunes('2008-01-28') + 3 * DIA);
  ok(m.t0 === lunes('2008-01-14') && m.t1 === lunes('2008-01-28') && !m.ultima, 'un tramo a la mitad');
  ok(Math.abs(m.otras[0].cambio - (60 / 50 - 1)) < 1e-12 && m.otras[0].parte === null,
     'parte con el último precio publicado hasta la primera barra');
  ok(F.tramoVisible(P, [], lunes('2009-01-05'), lunes('2009-02-02')) === null, 'sin barras a la vista');

  igual(F.textoEscala(F.tramoVisible(P, [pera], 0, Infinity), ['Palta', 'Pera']),
    'Todas las líneas parten en 0% el 07-01-2008.', 'la escala');
  igual(F.textoEscala(t, ['Palta', 'Pera', 'Aceite', 'Vieja', 'Otra']),
    'Todas las líneas parten en 0% el 07-01-2008, menos Aceite, que parte en su primer precio, ' +
    'el 21-01-2008.', 'la escala con una que parte después');
  const dos = F.tramoVisible(P, [tarde, semanas('2008-01-28', [3, 4])], 0, Infinity);
  igual(F.textoEscala(dos, ['Palta', 'Aceite', 'Miel']),
    'Todas las líneas parten en 0% el 07-01-2008, menos Aceite (21-01-2008) y Miel ' +
    '(28-01-2008), que parten en su primer precio.', 'la escala con dos que parten después');

  // la frase del pedido: "Desde [fecha], ajustado por inflación: Asado de
  // tira +38%, Palta −12%."
  const A = semanas('2008-01-07', [100, 138]), B = semanas('2008-01-07', [50, 44]);
  const series = [{ nombre: 'Asado de tira', color: 'h' }, { nombre: 'Palta', color: 'c1' }];
  const f = F.fraseTramo(F.tramoVisible(A, [B], 0, Infinity), series, 'ajustado por inflación', true);
  igual(f.map(x => x.texto || '').join(''),
    'Desde 07-01-2008, ajustado por inflación: Asado de tira +38%, Palta −12%.', 'la frase');
  igual(f.filter(x => x.clase).map(x => x.texto + ' ' + x.clase), ['+38% v-sube', '−12% v-baja'],
    'las cifras en color con criterio de consumidor');
  igual(f.filter(x => x.muestra).map(x => x.muestra), ['h', 'c1'], 'el color de cada línea');
  const sinDia = F.fraseTramo(F.tramoVisible(A, [B], 0, Infinity), series, 'a precio de la época', false);
  ok(sinDia[0].texto === 'Del 07-01-2008 al 14-01-2008, a precio de la época: ',
     'sin precio esta semana: del ... al ...');
  const ft = F.fraseTramo(t, [{ nombre: 'Palta' }, { nombre: 'Pera' }, { nombre: 'Aceite' },
    { nombre: 'Vieja' }], 'ajustado por inflación', true).map(x => x.texto || '').join('');
  igual(ft, 'Desde 07-01-2008, ajustado por inflación: Palta +25%, Pera −20%, Aceite +50% ' +
    '(desde el 21-01-2008), Vieja, sin precios en este tramo.', 'la frase con los casos');
  igual([0.004, -0.004, 0.006, 12.344, -0.5].map(x => F.cifraTramo(x).texto),
    ['0%', '0%', '+1%', '+1.234%', '−50%'], 'las cifras');
  ok(!F.cifraTramo(0.004).clase, '0% sin color');

  // Lightweight: la comparada en las semanas de la ficha, como la dibuja
  // Advanced Charts
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
  pruebasFrase();
  console.log(chequeos + ' chequeos, ' + fallas + ' fallas');
  if (fallas) process.exit(1);
  console.log('chequeos OK');
})().catch(e => { console.log('ERROR ' + (e && e.stack || e)); process.exit(1); });

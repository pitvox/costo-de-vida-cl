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
  'tramoComun, fraseTramo, notaTramo, periodoTxt, cifraTramo, enSemanasDe, fechaTxt };')();

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
  const tramo = (series, desde, hasta, alDia) => F.tramoComun(series, desde, hasta, alDia);
  const fin = b => b[b.length - 1].time;
  // el pedido: "Desde mayo de 2008, ajustado por inflación: Palta +40%,
  // Índice Asado +43%." Las dos del mismo período
  const palta = semanas('2008-05-05', [100, 110, 120, 130, 140]);
  const asado = semanas('2008-05-05', [200, 210, 250, 270, 286]);
  const series = [{ nombre: 'Palta', color: 'h' }, { nombre: 'Índice Asado', color: 'c1' }];
  const t = tramo([palta, asado], lunes('2008-05-05'), fin(palta), true);
  const f = F.fraseTramo(t, series, 'ajustado por inflación');
  igual(texto(f), 'Desde mayo de 2008, ajustado por inflación: Palta +40%, Índice Asado +43%.', 'la frase');
  igual(f.filter(x => x.clase).map(x => x.texto + ' ' + x.clase), ['+40% v-sube', '+43% v-sube'],
    'las cifras en color con criterio de consumidor');
  igual(f.filter(x => x.muestra).map(x => x.muestra), ['h', 'c1'], 'el color de cada línea');
  igual(F.notaTramo(t, ['Palta', 'Índice Asado']), '', 'sin nota si todas tienen precio reciente');

  // nunca dos períodos: si el índice parte en 2015, las dos cifras se miden
  // desde su primer precio (no la palta desde 2008 y el índice desde 2015)
  const n0 = (lunes('2015-12-14') - lunes('2008-05-05')) / SEM;   // la semana del índice en la palta
  const palta2 = semanas('2008-05-05', Array(n0).fill(80).concat(Array(200).fill(100), [125]));
  const asado2 = semanas('2015-12-14', Array(200).fill(200).concat([286]));
  const t2 = tramo([palta2, asado2], lunes('2008-05-05'), fin(palta2), true);
  ok(t2.t0 === lunes('2015-12-14') && t2.t1 === fin(palta2), 'el período parte en el primer precio del índice');
  igual(texto(F.fraseTramo(t2, series, 'ajustado por inflación')),
    'Desde diciembre de 2015, ajustado por inflación: Palta +25%, Índice Asado +43%.',
    'las dos cifras desde 2015');
  // con el tramo a la vista después, el período parte ahí
  const t2b = tramo([palta2, asado2], lunes('2018-01-01'), fin(palta2), true);
  ok(t2b.t0 === lunes('2018-01-01'), 'el período parte en el comienzo del tramo si es más tardío');

  // sin precio esta semana, o un tramo que no llega a hoy: "De ... a ..."
  const a3 = semanas('2008-05-05', Array(90).fill(100).concat([140]));
  const b3 = semanas('2008-05-05', Array(90).fill(50).concat([44]));
  igual(F.fraseTramo(tramo([a3, b3], 0, fin(a3), false), series, 'a precio de la época')[0].texto,
    'De mayo de 2008 a enero de 2010, a precio de la época: ', 'sin precio esta semana, de ... a ...');
  const a4 = semanas('2026-01-05', [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]);
  igual(F.periodoTxt(tramo([a4], 0, fin(a4), false)), 'De enero a marzo de 2026', 'el mismo año');
  igual(F.periodoTxt(tramo([a4], 0, lunes('2026-01-26'), false)), 'Del 05-01-2026 al 26-01-2026',
    'dentro de un mismo mes, las fechas');

  // sin precio propio en las últimas 4 semanas: fuera de la frase, con la
  // nota aparte; con 4 semanas justas, adentro (el plazo de las fichas)
  const P = semanas('2025-10-06', Array.from({ length: 52 }, (_, i) => 1000 + 10 * i));  // al 28-09-2026
  const hoy = fin(P);
  const cereza = semanas('2025-12-01', Array(10).fill(80));                             // al 02-02-2026
  const justa = semanas('2025-10-06', Array(48).fill(50).concat([60]));                 // al 31-08-2026: 4 semanas
  const t5 = tramo([P, justa, cereza], lunes('2025-10-06'), hoy, true);
  igual(t5.incluidas, [true, true, false], 'fuera, la de más de 4 semanas');
  const nombres5 = ['Palta', 'Pera', 'Cereza'];
  igual(texto(F.fraseTramo(t5, nombres5.map(nombre => ({ nombre })), 'ajustado por inflación')),
    'Desde octubre de 2025, ajustado por inflación: Palta +48%, Pera +20%.',
    'la frase, solo con las que tienen precio reciente, hasta la última semana de todas');
  ok(t5.t1 === fin(justa), 'el período termina en la última semana con precio de todas');
  igual(F.notaTramo(t5, nombres5), 'Sin precio reciente: Cereza (último dato: semana del 02-02-2026).',
    'la nota del pedido');
  ok(t5.hastaHoy, 'cuatro semanas antes de hoy aún es hoy');
  // dos fuera y una sin precios hasta ahí
  const t6 = tramo([P, cereza, semanas('2025-11-03', [7, 7]), semanas('2027-01-04', [1, 2])],
    lunes('2025-10-06'), hoy, true);
  igual(F.notaTramo(t6, ['Palta', 'Cereza', 'Sandía', 'Nueva']),
    'Sin precio reciente: Cereza (último dato: semana del 02-02-2026) y Sandía (último dato: semana ' +
    'del 10-11-2025). Sin precios en este tramo: Nueva.', 'varias fuera');
  // ninguna con precio reciente: sin frase, solo la nota
  const t7 = tramo([cereza], 0, hoy, true);
  ok(F.fraseTramo(t7, [{ nombre: 'Cereza' }], 'ajustado por inflación') === null, 'sin frase si no queda ninguna');
  // incluidas sin semanas en común
  const t8 = tramo([semanas('2026-01-05', [1, null, 2, null, 3]), semanas('2026-01-12', [4, null, 5])],
    0, lunes('2026-02-02'), false);
  igual(texto(F.fraseTramo(t8, [{ nombre: 'A' }, { nombre: 'B' }], 'ajustado por inflación')),
    'En este tramo no hay semanas con precio de todas a la vez.', 'sin semanas en común');

  // nunca el precio repetido de las semanas sin dato: las semanas que
  // indices.py completó (datos/repetidas/{slug}.json) no cuentan para nada
  const j = { t0: '2026-01-05', v: [100, 100, 100, 120, 130, 130] };
  const propias = F.semanasPropias(j, [1, 2, 5]);
  igual([...propias].map(F.fechaTxt), ['05-01-2026', '26-01-2026', '02-02-2026'],
    'las semanas propias: con precio y sin las repetidas');
  igual([...F.semanasPropias({ t0: '2026-01-05', v: [1, null, 3] }, [])].length, 2,
    'sin repetidas, toda semana con precio es propia');
  const solo = semanas('2026-01-05', j.v).filter(x => propias.has(x.time));
  // el tramo parte el 12-01 (una semana repetida): la frase parte en la
  // primera semana propia de las dos (26-01) y termina en la última (02-02),
  // no en la repetida del 09-02
  const ficha = semanas('2026-01-12', [500, 505, 510, 515, 520]);
  const t9 = tramo([ficha, solo], lunes('2026-01-12'), fin(ficha), true);
  ok(t9.t0 === lunes('2026-01-26') && t9.t1 === lunes('2026-02-02'), 'de la primera a la última semana propia de todas');
  ok(Math.abs(t9.cambios[1] - (130 / 120 - 1)) < 1e-12 && Math.abs(t9.cambios[0] - (515 / 510 - 1)) < 1e-12,
    'las dos cifras del mismo período, con precios propios');

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

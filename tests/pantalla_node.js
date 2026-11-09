// Pruebas de la pantalla completa (JS_PANTALLA de build_site.py) sin
// navegador: se toma el bloque de carestia-ficha.js y se corre con un
// documento, un historial y un gráfico de mentira.
//
//   node tests/pantalla_node.js DIR_DEL_BUILD
//
// Lo llama tests/test_buscador.py. Termina con código 1 si algo falla.
'use strict';
const fs = require('fs');
const path = require('path');

const dir = path.resolve(process.argv[2] || '.');
const js = fs.readFileSync(path.join(dir, 'carestia-ficha.js'), 'utf8');
const i = js.indexOf('/* ---------- pantalla completa ---------- */');
const j = js.indexOf('// la unidad: en Advanced Charts es otro símbolo');
if (i === -1 || j === -1 || j < i) { console.error('no está el bloque de pantalla completa'); process.exit(1); }

let fallas = 0, chequeos = 0;
const ok = (c, t) => { chequeos++; if (!c) { fallas++; console.error('FALLA: ' + t); } };

// ---- el entorno de mentira ----
const oyentes = { document: {}, window: {} };
const clases = () => {
  const s = new Set();
  return { toggle: (c, on) => { if (on) s.add(c); else s.delete(c); }, contains: c => s.has(c) };
};
const boton = () => {
  const b = { attrs: {}, focos: 0, clics: [], setAttribute: (k, v) => { b.attrs[k] = String(v); },
    focus: () => { b.focos++; }, addEventListener: (ev, f) => { if (ev === 'click') b.clics.push(f); },
    click: () => b.clics.forEach(f => f()) };
  return b;
};
const raiz = { classList: clases() };
const document = { documentElement: raiz,
  addEventListener: (ev, f) => { (oyentes.document[ev] = oyentes.document[ev] || []).push(f); } };
const window = { addEventListener: (ev, f) => { (oyentes.window[ev] = oyentes.window[ev] || []).push(f); } };
// el historial: pushState agrega un paso; back() lo saca y avisa (popstate)
const history = { pasos: 0, pushState() { this.pasos++; },
  back() { this.pasos--; (oyentes.window.popstate || []).forEach(f => f()); } };
const esperas = [];
const setTimeout = f => { esperas.push(f); };
const correrEsperas = () => { while (esperas.length) esperas.shift()(); };

const { pantallaCompleta, tramoTV, tramoLW } = new Function('document', 'window', 'history', 'setTimeout',
  js.slice(i, j) + '\nreturn { pantallaCompleta, tramoTV, tramoLW };')(document, window, history, setTimeout);

// ---- abrir y cerrar ----
const caja = { classList: clases() }, abrir = boton(), otro = boton(), cerrar = boton();
let tramo = { from: 100, to: 200 }, puestos = [], abiertas = 0;
const pc = pantallaCompleta({ caja, abrir: [abrir, otro], cerrar, alAbrir: () => { abiertas++; },
  tramo: () => ({ leer: () => tramo, poner: t => puestos.push(t) }) });

abrir.click();
ok(pc.abierta() && caja.classList.contains('pc') && raiz.classList.contains('pc-abierta'),
  'abre: la caja queda fija y la página no se desplaza');
ok(abrir.attrs['aria-expanded'] === 'true' && otro.attrs['aria-expanded'] === 'true', 'abre: aria-expanded en los dos botones');
ok(history.pasos === 1 && abiertas === 1 && cerrar.focos === 1, 'abre: un paso en el historial y el foco en Cerrar');
correrEsperas();
ok(puestos.length === 1 && puestos[0] === tramo, 'abre: el tramo a la vista se repone');

cerrar.click();
ok(!pc.abierta() && !caja.classList.contains('pc') && !raiz.classList.contains('pc-abierta'), 'cierra con su botón');
ok(history.pasos === 0, 'cierra con su botón: el paso del historial se devuelve');
ok(abrir.focos === 1 && otro.focos === 0, 'cierra: el foco vuelve al botón que la abrió');
correrEsperas();
ok(puestos.length === 2, 'cierra: el tramo se repone otra vez');

// "atrás" cierra sin retroceder de más
otro.click();
ok(pc.abierta() && history.pasos === 1, 'abre con el otro botón');
history.back();
ok(!pc.abierta() && history.pasos === 0 && otro.focos === 1, '"atrás" cierra y no retrocede otro paso');

// Escape
abrir.click();
oyentes.document.keydown.forEach(f => f({ key: 'a' }));
ok(pc.abierta(), 'otra tecla no cierra');
oyentes.document.keydown.forEach(f => f({ key: 'Escape' }));
ok(!pc.abierta() && history.pasos === 0, 'Escape cierra');
// cerrada, ni Escape ni "atrás" hacen nada
oyentes.document.keydown.forEach(f => f({ key: 'Escape' }));
(oyentes.window.popstate || []).forEach(f => f());
ok(!pc.abierta() && history.pasos === 0, 'cerrada, Escape y "atrás" no hacen nada');
correrEsperas();

// sin gráfico todavía (tramo null) también abre y cierra
const sin = pantallaCompleta({ caja: { classList: clases() }, abrir: [boton()], cerrar: boton(), tramo: () => null });
ok(!sin.abierta(), 'sin gráfico: parte cerrada');

// ---- el tramo en Advanced Charts ----
const SEMANA = 7 * 86400;
const llamadas = [];
const chart = { symbol: () => 'ODEPA:kiwi', resolution: () => '1W', getVisibleRange: () => ({ from: 5, to: 6 }),
  setVisibleRange: (t, op) => { llamadas.push(['rango', t, op]); return Promise.resolve(); } };
const w = { activeChart: () => chart };
const TV = { verTodo: (ww, feed, c) => { llamadas.push(['todo', c]); return Promise.resolve(); } };
const feed = { rango: (sim, res) => (sim === 'ODEPA:kiwi' && res === '1W' ? { from: 1000 * SEMANA, to: 2000 * SEMANA } : null) };
const t = tramoTV(TV, w, feed, 'caja');
ok(t.leer().from === 5, 'Advanced Charts: lee el tramo a la vista');
t.poner({ from: 1000 * SEMANA, to: 2000 * SEMANA });
ok(llamadas.length === 1 && llamadas[0][0] === 'todo' && llamadas[0][1] === 'caja',
  'Advanced Charts: con toda la historia a la vista, el encuadre de siempre');
t.poner({ from: 1500 * SEMANA, to: 2000 * SEMANA });
ok(llamadas.length === 2 && llamadas[1][0] === 'rango' && llamadas[1][1].from === 1500 * SEMANA &&
  llamadas[1][2].applyDefaultRightMargin === false, 'Advanced Charts: un tramo acercado se repone tal cual');
// sin las semanas del símbolo (rango null), se repone el tramo leído
tramoTV(TV, w, { rango: () => null }, 'caja').poner({ from: 1, to: 2 });
ok(llamadas.length === 3 && llamadas[2][0] === 'rango', 'Advanced Charts: sin rango conocido, el tramo leído');
// un rechazo de la librería no se propaga
chart.setVisibleRange = () => Promise.reject(new Error('tarde'));
Promise.resolve(tramoTV(TV, w, { rango: () => null }, 'caja').poner({ from: 1, to: 2 })).then(() => {
  // ---- el tramo en Lightweight ----
  let logico = { from: 3, to: 9 };
  const lw = tramoLW({ timeScale: () => ({ getVisibleLogicalRange: () => logico,
    setVisibleLogicalRange: r => { logico = r; } }) });
  lw.poner({ from: 1, to: 2 });
  ok(lw.leer().from === 1, 'Lightweight: lee y repone el tramo lógico');
  console.log(chequeos + ' chequeos, ' + fallas + ' fallas');
  process.exit(fallas ? 1 : 0);
}, e => { console.error('FALLA: el rechazo de setVisibleRange se propagó: ' + e); process.exit(1); });

// Corre, sin navegador, el JS de Arma tu canasta de /graficos.html sobre un
// build de build_site.py: expandirProducto (datos a demanda), calcularCanasta,
// syncCanasta (lo que escribe en ccosto, cstats, ctemporada y caviso),
// leerHash, hashCanasta, semanaISO y distSem, tal como salen en la página.
// tests/test_canastas.py le pasa ese JS y las canastas a probar, y compara
// lo que devuelve con las funciones de Python de las canastas de ejemplo.
//
//   node tests/canasta_node.js ARCHIVO   (JSON: { datos, fmt, canasta, prods,
//                                         dir, canastas, hashes, mapas,
//                                         fechas })
//
// Escribe un JSON con los resultados en la salida estándar.
'use strict';
const fs = require('fs');
const path = require('path');

const E = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
// los productos como los tiene la página: label, unidad y slug inline, y la
// serie de datos/productos/{slug}.json, expandida con su propio código
const PRODS = E.prods;
const { expandirProducto } = new Function(E.datos + '\nreturn { expandirProducto };')();
Object.keys(PRODS).forEach(k => {
  const ruta = path.join(E.dir, 'datos', 'productos', PRODS[k].slug + '.json');
  expandirProducto(PRODS[k], JSON.parse(fs.readFileSync(ruta, 'utf8')));
});

// lo que la franja necesita de la página: los elementos donde escribe y el
// hash; sin Advanced Charts ni Lightweight (no dibuja)
const els = {};
const document = { getElementById: id => (els[id] = els[id] || { textContent: '' }) };
const location = { hash: '', pathname: '/graficos.html', search: '' };
const history = { replaceState() {} };
const C = new Function('PRODS', 'document', 'location', 'history', 'modo', 'pedirProductos',
  'pintarCarga', 'tvListo', E.fmt + '\n' + E.canasta +
  '\nreturn { canasta, leerHash, hashCanasta, calcularCanasta, syncCanasta, semanaISO, distSem };')(
  PRODS, document, location, history, 'canasta', () => {}, () => {}, () => false);

const out = { canastas: [], hashes: [], mapas: [], iso: [], dist: [] };
for (const c of E.canastas) {
  C.canasta.clear();
  c.forEach(([k, q]) => C.canasta.set(k, q));
  C.syncCanasta();
  const r = C.calcularCanasta();
  out.canastas.push({
    serie: r.serie.map(p => [p.time, p.value]), truncada: r.truncada, limitante: r.limitante,
    costo: els.ccosto.textContent, stats: els.cstats.textContent,
    temporada: els.ctemporada.textContent, aviso: els.caviso.textContent,
  });
}
// un link de canasta: lo que lee leerHash y el hash que vuelve a escribir
for (const h of E.hashes) {
  C.canasta.clear();
  location.hash = h;
  const leido = C.leerHash();
  out.hashes.push({ leido, canasta: [...C.canasta.entries()], hash: C.hashCanasta() });
}
// hashCanasta de una canasta puesta tal cual, sin pasar por leerHash
for (const c of E.mapas) {
  C.canasta.clear();
  c.forEach(([k, q]) => C.canasta.set(k, q));
  out.mapas.push(C.hashCanasta());
}
out.iso = E.fechas.map(C.semanaISO);
for (let a = 1; a <= 53; a++) for (let b = 1; b <= 53; b++) out.dist.push(C.distSem(a, b));
process.stdout.write(JSON.stringify(out));

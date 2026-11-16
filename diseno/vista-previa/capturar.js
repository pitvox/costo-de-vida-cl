// diseno/vista-previa/capturar.js: las capturas de la vista previa del look
// claro. Temporal, como .github/workflows/vista-previa.yml, que lo corre:
// se borra con esta carpeta antes de mergear.
//
// Uso: node capturar.js <url del sitio servido> <carpeta public/> <carpeta de salida>
// Variables: COMMIT y FECHA (para el LEEME.md), LIBRERIA (ok o falla: con
// falla, el LEEME.md avisa que los gráficos son de Lightweight Charts).
// LW_LOCAL, solo fuera de Actions: un archivo de Lightweight Charts que
// reemplaza al de unpkg.com cuando la red no lo alcanza.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [base, publico, salida] = process.argv.slice(2);
const piezas = [];   // [archivo, título], en el orden del LEEME.md

async function esperarGraficos(page) {
  // los motores de gráficos marcan su estado en data-motor*: se espera a
  // que ninguno siga cargando y después a que la librería termine de dibujar
  await page.waitForFunction(() => {
    const els = [document.body, ...document.querySelectorAll('[data-motor]')];
    return els.every(el => Object.keys(el.dataset).filter(k => /^motor/.test(k))
      .every(k => el.dataset[k] !== 'cargando'));
  }, null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(4000);
}

async function abrir(page, ruta) {
  await page.goto(base + ruta, { waitUntil: 'networkidle', timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  await esperarGraficos(page);
}

// la parte de arriba de la página, hasta dos pantallas: lo que se ve al
// llegar y un poco más
async function foto(page, archivo, titulo) {
  const vp = page.viewportSize();
  const alto = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(salida, archivo),
    clip: { x: 0, y: 0, width: vp.width, height: Math.min(alto, vp.height * 2) } });
  piezas.push([archivo, titulo]);
}

async function fotoDe(page, selector, archivo, titulo) {
  const el = page.locator(selector).first();
  await el.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  // con un margen de 16px alrededor, dentro del ancho de la página
  const caja = await el.boundingBox();
  const y = await page.evaluate(() => window.scrollY);
  const ancho = page.viewportSize().width;
  const x0 = Math.max(0, caja.x - 16);
  await page.screenshot({ path: path.join(salida, archivo), fullPage: true,
    clip: { x: x0, y: Math.max(0, caja.y + y - 16), width: Math.min(ancho - x0, caja.width + 32),
      height: caja.height + 32 } });
  piezas.push([archivo, titulo]);
}

async function captura(page, archivo, titulo) {
  // la captura PNG que arma el JS (en escritorio se descarga)
  const [descarga] = await Promise.all([
    page.waitForEvent('download', { timeout: 60000 }),
    page.click('#shot'),
  ]);
  await descarga.saveAs(path.join(salida, archivo));
  piezas.push([archivo, titulo]);
}

async function comparar(page) {
  await abrir(page, '/graficos.html#comparar');
  // los que vienen elegidos fuera (pueden estar en grupos cerrados) y los
  // cuatro adentro, por su nombre exacto
  await page.$$eval('#pgroups .pchip.active', bs => bs.forEach(b => b.click()));
  await page.$$eval('#pgroups .pchip', (bs, nombres) => nombres.forEach(n => {
    const b = bs.find(x => x.textContent.trim() === n);
    if (b && !b.classList.contains('active')) b.click();
  }), ['Tomate', 'Palta', 'Papa', 'Limón']);
  await esperarGraficos(page);
}

async function canasta(page) {
  // el link de canasta compartido: el botón de la canasta de ejemplo
  await abrir(page, '/canastas/almuerzo-casino.html');
  const href = await page.locator('a[href*="#canasta="]').first().getAttribute('href');
  await abrir(page, href.replace('https://carestia.cl', ''));
}

async function recorrer(browser, nombre, opciones, soloCelular) {
  const ctx = await browser.newContext(Object.assign({ acceptDownloads: true }, opciones));
  const page = await ctx.newPage();
  if (process.env.LW_LOCAL) {
    await page.route('https://unpkg.com/**', r => r.fulfill({ path: process.env.LW_LOCAL,
      contentType: 'application/javascript' }));
  }
  page.on('pageerror', e => console.log(`[${nombre}] error de JS: ${e.message}`));
  const n = (i, s) => `${nombre}-${String(i).padStart(2, '0')}-${s}.png`;
  await abrir(page, '/index.html');
  await foto(page, n(1, 'portada'), `Portada (${nombre})`);
  await fotoDe(page, '[aria-labelledby="h-indices"]', n(2, 'portada-indices'),
    `Portada, Índices Carestía (${nombre})`);
  await abrir(page, '/graficos.html#asado');
  await foto(page, n(3, 'asado-linea'), `/graficos.html#asado en línea (${nombre})`);
  await page.click('#v-velas');
  await esperarGraficos(page);
  await foto(page, n(4, 'asado-velas'), `/graficos.html#asado en velas (${nombre})`);
  if (!soloCelular) await captura(page, n(5, 'asado-captura'), 'Captura PNG del Índice Asado');
  await comparar(page);
  await foto(page, n(6, 'comparar'), `Comparar productos: tomate, palta, papa y limón (${nombre})`);
  await canasta(page);
  await foto(page, n(7, 'canasta'), `Arma tu canasta: el link compartido del almuerzo de casino (${nombre})`);
  await abrir(page, '/productos/tomate.html');
  await foto(page, n(8, 'tomate'), `Ficha de tomate (${nombre})`);
  if (!soloCelular) await captura(page, n(9, 'tomate-captura'), 'Captura PNG de la ficha de tomate');
  await abrir(page, '/compras.html');
  await foto(page, n(10, 'compras'), `/compras.html (${nombre})`);
  if (soloCelular) {
    await abrir(page, '/metodologia.html');
    await foto(page, n(11, 'metodologia'), '/metodologia.html (celular)');
    await abrir(page, '/productos/');
    await foto(page, n(12, 'productos'), '/productos/ (celular)');
    await abrir(page, '/404.html');
    await foto(page, n(13, '404'), '404.html (celular)');
  }
  await ctx.close();
}

(async () => {
  fs.mkdirSync(salida, { recursive: true });
  for (const f of fs.readdirSync(salida)) if (f.endsWith('.png')) fs.unlinkSync(path.join(salida, f));
  const browser = await chromium.launch();
  await recorrer(browser, 'celular', { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    isMobile: true, hasTouch: true }, true);
  await recorrer(browser, 'escritorio', { viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 1 }, false);
  await browser.close();
  // las imágenes del build: tarjetas e ícono
  for (const [de, a, titulo] of [
    ['og.png', 'og.png', 'og.png, la tarjeta genérica'],
    ['og/indices/asado.png', 'og-indice-asado.png', 'Tarjeta del Índice Asado'],
    ['og/productos/tomate.png', 'og-producto-tomate.png', 'Tarjeta de tomate'],
    ['og/canastas/almuerzo-casino.png', 'og-canasta-almuerzo-casino.png',
      'Tarjeta de la canasta de ejemplo'],
    ['apple-touch-icon.png', 'apple-touch-icon.png', 'Ícono de iOS'],
  ]) {
    fs.copyFileSync(path.join(publico, de), path.join(salida, a));
    piezas.push([a, titulo]);
  }
  const libreria = process.env.LIBRERIA === 'ok';
  const leeme = [
    '# Vista previa: look claro',
    '',
    `Commit \`${process.env.COMMIT || '?'}\`, ${process.env.FECHA || ''}. Datos: el indices.json publicado en carestia.cl.`,
    '',
    libreria ? 'Gráficos de TradingView Advanced Charts.'
      : '**La librería de TradingView no bajó: los gráficos de estas capturas son de Lightweight Charts, el respaldo.**',
    '',
    'Celular: 390 px de ancho, escala 2. Escritorio: 1280 px. Cada captura de página muestra hasta dos pantallas desde arriba.',
    '',
    ...piezas.flatMap(([a, t]) => [`## ${t}`, '', `![${t}](${a})`, '']),
  ].join('\n');
  fs.writeFileSync(path.join(salida, 'LEEME.md'), leeme);
  console.log(`${piezas.length} imágenes en ${salida}`);
})().catch(e => { console.error(e); process.exit(1); });

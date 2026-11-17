// diseno/diagnostico/tema-tv.js: TEMPORAL, como .github/workflows/diagnostico-tema.yml,
// que lo corre en Actions (la librería de TradingView solo existe ahí). Se
// borra con esta carpeta antes de mergear.
//
// Recorre el sitio como una persona: entra en claro, mira una ficha y
// /graficos.html (con velas y de vuelta a línea), pasa al modo oscuro con la
// luna y vuelve a la ficha; y una persona nueva que llega en oscuro. En cada
// paso cuenta los píxeles de los lienzos de Advanced Charts en los colores
// de las líneas (exactos, a 3 de distancia) y anota lo que la librería guarda
// en el navegador (las claves tradingview.*).
//
// Uso: node tema-tv.js <url del sitio servido> <carpeta de salida>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [base, salida] = process.argv.slice(2);
const resultados = [];

async function esperar(page) {
  await page.waitForFunction(() => {
    const els = [document.body, ...document.querySelectorAll('[data-motor]')];
    return els.every(el => Object.keys(el.dataset).filter(k => /^motor/.test(k))
      .every(k => el.dataset[k] !== 'cargando'));
  }, null, { timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(6000);
}

async function medir(page, nombre) {
  await esperar(page);
  const r = await page.evaluate(() => {
    const tok = n => getComputedStyle(document.documentElement).getPropertyValue('--' + n).trim();
    const hex = h => { h = h.replace('#', ''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
    const objetivos = { '#111111 (tinta del claro)': '#111111', '#e4dacc (hueso)': '#e4dacc',
      '#e8743b (brasa)': '#e8743b', '#767676 (canasta del claro)': '#767676' };
    const conteo = {};
    let lienzos = 0;
    for (const f of document.querySelectorAll('iframe')) {
      if (!f.offsetParent) continue;
      let doc = null;
      try { doc = f.contentDocument; } catch (e) {}
      if (!doc) continue;
      for (const c of doc.querySelectorAll('canvas')) {
        if (c.width < 300 || c.height < 150) continue;
        let d;
        try { d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; } catch (e) { continue; }
        lienzos++;
        for (const [k, h] of Object.entries(objetivos)) {
          const [r0, g0, b0] = hex(h);
          let n = 0;
          for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] > 200 && Math.abs(d[i] - r0) + Math.abs(d[i + 1] - g0) + Math.abs(d[i + 2] - b0) <= 3) n++;
          }
          conteo[k] = (conteo[k] || 0) + n;
        }
      }
    }
    const guardado = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!/tradingview/i.test(k)) continue;
      const v = localStorage.getItem(k) || '';
      const trozos = [];
      for (const m of ['lineStyle', 'current_theme', '"theme', 'paneProperties', '"style"']) {
        const j = v.indexOf(m);
        if (j >= 0) trozos.push(v.slice(Math.max(0, j - 30), j + 260));
      }
      guardado[k] = { largo: v.length, inicio: v.slice(0, 120), trozos };
    }
    return { url: location.pathname + location.hash, tema: document.documentElement.dataset.tema || 'claro',
      motor: [document.body.dataset.motorIndices, (document.querySelector('[data-motor]') || {}).dataset?.motor]
        .filter(Boolean).join(' / '),
      tokens: { producto: tok('producto'), serie: tok('serie'), bg: tok('bg') }, lienzos, conteo, guardado };
  });
  r.nombre = nombre;
  resultados.push(r);
  console.log('### ' + nombre + '\n' + JSON.stringify(r, null, 1));
  await page.screenshot({ path: path.join(salida, nombre + '.png') });
}

async function luna(page) {
  await Promise.all([page.waitForEvent('load', { timeout: 60000 }), page.click('.sitenav > .tema')]);
}

(async () => {
  fs.mkdirSync(salida, { recursive: true });
  for (const f of fs.readdirSync(salida)) if (f.endsWith('.png')) fs.unlinkSync(path.join(salida, f));
  const b = await chromium.launch();
  const vp = { viewport: { width: 1280, height: 900 } };
  // una persona que entra en claro, cambia a velas y vuelve a línea, y
  // después pasa al oscuro con la luna
  let ctx = await b.newContext(vp);
  let p = await ctx.newPage();
  p.on('pageerror', e => console.log('error de JS:', e.message));
  await p.goto(base + '/productos/abastero.html', { waitUntil: 'networkidle' });
  await medir(p, '1-ficha-claro');
  await p.goto(base + '/graficos.html#asado', { waitUntil: 'networkidle' });
  await medir(p, '2-graficos-claro');
  await p.click('#v-velas');
  await p.waitForTimeout(3000);
  await p.click('#v-linea');
  await medir(p, '3-graficos-claro-velas-y-linea');
  await luna(p);
  await medir(p, '4-graficos-oscuro-tras-la-luna');
  await p.goto(base + '/productos/abastero.html', { waitUntil: 'networkidle' });
  await medir(p, '5-ficha-oscuro');
  await luna(p);
  await medir(p, '6-ficha-claro-de-vuelta');
  await ctx.close();
  // una persona nueva que llega en oscuro
  ctx = await b.newContext(vp);
  await ctx.addInitScript(() => {
    if (!sessionStorage.getItem('dx')) { localStorage.setItem('carestia-tema', 'oscuro'); sessionStorage.setItem('dx', '1'); }
  });
  p = await ctx.newPage();
  await p.goto(base + '/productos/abastero.html', { waitUntil: 'networkidle' });
  await medir(p, '7-ficha-oscuro-persona-nueva');
  await p.goto(base + '/graficos.html#asado', { waitUntil: 'networkidle' });
  await medir(p, '8-graficos-oscuro-persona-nueva');
  await ctx.close();
  await b.close();
  fs.writeFileSync(path.join(salida, 'resultados.json'), JSON.stringify(resultados, null, 1));
})().catch(e => { console.error(e); process.exit(1); });

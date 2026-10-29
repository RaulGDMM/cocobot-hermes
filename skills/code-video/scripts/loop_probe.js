// Pre-render probe: determinism + loop periodicity + page errors, without encoding anything.
// usage: node loop_probe.js PROJECT_DIR [--page index.html] [--size 1600x420] [--times 3.0,7.2] [--dur 10]
// Needs playwright (or puppeteer) installed in the project: npm i playwright && npx playwright install chromium
// The page must set window.READY and expose window.seek(t), like capture.mjs expects.
// PASS criteria: seek(t) hashes identical when revisited out of order; with --dur/window.DUR,
// t=dur hashes identical to t=0. Exit 0 only if everything passes.
import { createRequire } from 'node:module';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const argv = process.argv.slice(2);
const dir = path.resolve(argv[0] || '.');
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i < 0 ? d : argv[i + 1]; };
const page_ = opt('page', 'index.html');
const [W, H] = String(opt('size', '1920x1080')).split('x').map(Number);
const times = String(opt('times', '3.0,7.2')).split(',').map(Number);
const durOpt = opt('dur', null);

const { createRequire: _c } = { createRequire };
const req = createRequire(path.join(dir, 'package.json'));
const load = async n => { try { return req(n); } catch { return import(n); } };
const glArgs = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'];

let browser, page;
try {
  const pw = await load('playwright');
  browser = await pw.chromium.launch({ args: glArgs });
  page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
} catch {
  const puppeteer = (await load('puppeteer')).default;
  browser = await puppeteer.launch({ args: glArgs });
  page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
}
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.goto(pathToFileURL(path.join(dir, page_)).href);
await page.waitForFunction(() => window.READY === true && typeof window.seek === 'function', null, { timeout: 120000 });
const D = durOpt !== null ? +durOpt : await page.evaluate(() => window.DUR || 0);

const sha = async t => {
  await page.evaluate(async x => { await window.seek(x); }, t);
  const buf = await page.screenshot();
  return crypto.createHash('sha256').update(buf).digest('hex').slice(0, 16);
};

let fail = false;
const A = await sha(times[0]);
await sha(times[1]);            // disturb order before revisiting
const A2 = await sha(times[0]);
const det = A === A2;
console.log(`determinism t=${times[0]} (${A} vs ${A2}): ${det ? 'OK' : 'FAIL'}`);
fail = fail || !det;
if (D) {
  const P1 = await sha(D), P0 = await sha(0);
  const per = P1 === P0;
  console.log(`periodicity t=${D} vs t=0 (${P1} vs ${P0}): ${per ? 'OK' : 'FAIL'}`);
  fail = fail || !per;
} else {
  console.log('periodicity: skipped (no --dur and no window.DUR)');
}
console.log('page errors:', errs.length ? errs : 'none');
fail = fail || errs.length > 0;
await browser.close();
process.exit(fail ? 1 : 0);

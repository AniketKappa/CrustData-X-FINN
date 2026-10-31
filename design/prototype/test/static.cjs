// Static (no backend) mode: the UI must still work on built-in demo data. Serve design/prototype on :8765.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://localhost:8765/index.html';
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  const errors = []; const res = []; const check = (n, ok) => res.push(`${ok ? 'PASS' : 'FAIL'} ${n}`);
  p.on('console', (m) => { if (['error', 'warning'].includes(m.type()) && !m.text().includes('404')) errors.push(m.text()); });
  p.on('pageerror', (e) => errors.push(e.message));
  await p.goto(B + '#/briefing'); await p.waitForSelector('.bsec');
  check('briefing sections', await p.locator('.bsec').count() >= 3);
  check('results tiles', await p.locator('.tiles').count() >= 1);
  await p.locator('.li').first().click(); await p.waitForSelector('.detail'); check('detail', true);
  await p.goto(B + '#/portfolio'); await p.waitForSelector('.card.list'); check('portfolio (read-only)', await p.locator('#stock-search').count() === 0);
  await p.goto(B + '#/companies/FX-TUBES/promises'); await p.waitForSelector('.ledger'); check('fixture dossier', true);
  await p.goto(B + '#/research'); await p.waitForSelector('.ask'); await p.locator('[data-ask]').first().click();
  check('research example', await p.locator('.note-card .findings li').count() >= 1);
  console.log(res.join('\n')); console.log('ERRORS:', errors.length ? errors.join('\n') : 'none'); await b.close();
})().catch((e) => { console.error('CRASH', e); process.exit(1); });

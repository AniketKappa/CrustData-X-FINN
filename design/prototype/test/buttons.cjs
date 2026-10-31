// Button audit: on every screen, tap every visible button and in-app link and check it does its job:
// in-app links land on their own href; buttons don't throw, don't bounce the user to another screen
// (except the ones whose job is to navigate), and dialogs they open can be closed.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://localhost:8800/';
const SKIP = /delete-selected|r-rebuild|mic|reset-settings/;      // destructive or device-only; covered in v3.cjs
const NAVIGATES = /data-window|data-act="done"|data-act="snooze"|edit-portfolio/;
(async () => {
  const b = await chromium.launch(); const errors = [], fails = []; let n = 0;
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  await ctx.addInitScript(() => { try { localStorage.clear(); } catch {} });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push(e.message));
  const screens = ['#/briefing', '#/briefing?w=7d', '#/portfolio', '#/company/FXCABLES/overview', '#/company/FXCABLES/financials',
    '#/company/FXCABLES/documents', '#/research', '#/research?c=FXCABLES'];
  for (const s of screens) {
    await p.goto(B + s); await p.waitForTimeout(s.includes('research?c') ? 2500 : 900);
    const handles = await p.$$eval('main a[href^="#"], main button, header button', (els) => els.filter((e) => e.offsetParent).map((e, i) => {
      e.setAttribute('data-audit', String(i)); return { i, html: e.outerHTML.slice(0, 160), href: e.getAttribute('href'), text: (e.textContent || '').trim().slice(0, 30) };
    }));
    for (const h of handles) {
      if (SKIP.test(h.html)) continue;
      await p.goto('about:blank'); await p.goto(B + s); await p.waitForTimeout(s.includes('research?c') ? 1200 : 700);
      await p.$$eval('main a[href^="#"], main button, header button', (els) => els.filter((e) => e.offsetParent).forEach((e, i) => e.setAttribute('data-audit', String(i))));
      const el = p.locator(`[data-audit="${h.i}"]`);
      if (!(await el.count())) { fails.push(`${s} :: "${h.text}" missing after reload`); continue; }
      const before = await p.evaluate(() => location.hash);
      try { await el.first().click({ timeout: 2000 }); } catch (e) { fails.push(`${s} :: "${h.text}" not clickable`); continue; }
      n++;
      await p.waitForTimeout(350);
      const after = await p.evaluate(() => location.hash);
      if (h.href && h.href.startsWith('#/')) {
        if (after !== h.href && !after.startsWith(h.href.split('?')[0])) fails.push(`${s} :: link "${h.text}" -> ${after} (expected ${h.href})`);
      } else if (!NAVIGATES.test(h.html) && after.split('?')[0] !== before.split('?')[0] && !/data-filter|data-ptab|data-more/.test(h.html)) {
        fails.push(`${s} :: button "${h.text}" moved ${before} -> ${after}`);
      }
      if (await p.locator('dialog[open]').count()) { await p.click('.dlg-close'); await p.waitForTimeout(150);
        if (await p.locator('dialog[open]').count()) fails.push(`${s} :: dialog from "${h.text}" won't close`); }
    }
  }
  console.log(`tapped ${n} controls on ${screens.length} screens`);
  console.log(fails.length ? 'FAIL\n' + fails.join('\n') : 'PASS all controls'); console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await b.close();
})();

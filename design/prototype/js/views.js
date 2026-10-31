// Presentation only: functions that turn view models into HTML strings.
// Evidence objects and chart specs are registered here and resolved by app.js after render.
import { esc, cr, crShort, price, pctv, times, change, pts, dt, dateLong, unitFmt } from "./format.js";
import { CATEGORY_LABEL, WINDOWS, periodTable, margin, cashQuality, verdict, STATUSES } from "./logic.js";

export const registry = { ev: new Map(), charts: new Map() };
let seq = 0;
export function resetRegistry() { registry.ev.clear(); registry.charts.clear(); seq = 0; }
const evRef = (e) => { const k = `e${++seq}`; registry.ev.set(k, e); return k; };
const chartRef = (kind, spec) => { const k = `c${++seq}`; registry.charts.set(k, { kind, spec }); return k; };

// ---------- icons (line, 1.5px, only where they help) ----------
const I = {
  speaker: `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 8h3l4-3v10l-4-3H3z"/><path d="M13 7.5a3.5 3.5 0 0 1 0 5M15 5.5a6.5 6.5 0 0 1 0 9"/></svg>`,
  stop: `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><rect x="5" y="5" width="10" height="10" rx="1"/></svg>`,
  back: `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6"/></svg>`,
  ext: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 4H4v12h12v-4M11 4h5v5M16 4l-7 7"/></svg>`,
  doc: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.5h7l3 3v12H5z"/><path d="M8 9h5M8 12h5"/></svg>`,
};
export const icons = I;
export { evRef, chartRef, sourceButton, citeButton };

const fixtureTag = (x) => (x?.fixture ? `<span class="tag">Fixture</span>`
  : x?.alert && x?.live ? `<span class="tag">End of day</span>`
  : x?.real ? `<span class="tag real">${esc(x.exchange || "NSE")} filing</span>` : "");
const clip = (s, n) => (s && s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

function sourceButton(src, label = "Source") {
  const k = evRef({ ...src });
  const where = [src.source_name, src.locator].filter(Boolean).join(", ");
  return `<button type="button" class="src" data-ev="${k}">${I.doc}<span>${esc(label)}: ${esc(where)}</span></button>`;
}
function citeButton(n, c) {
  const k = evRef({ source_class: "PRIMARY_DOC", source_name: c.doc, locator: c.page ? `page ${c.page}` : c.locator, passage: c.passage, fixture: /fixture/i.test(c.doc), url: c.url || null, date: c.date });
  return `<button type="button" class="cite" data-ev="${k}" aria-label="Source ${n}: ${esc(c.doc)}${c.page ? ", page " + c.page : ""}">${n}</button>`;
}

// ---------- Briefing ----------
const sourceTag = (i) => (i.news ? `<span class="tag news">News · ${esc(i.publisher)}</span>` : "");

function resultsMini(r) {
  if (!r) return "";
  const pctc = (v) => (v == null ? `<span class="chg">—</span>` : change(v));
  return `<table class="tbl mini" aria-label="Headline results, ${esc(r.unit)}">
    <thead><tr><th scope="col">${esc(r.unit)}, ${esc(r.periods[0])}</th><th scope="col" class="n">Value</th><th scope="col" class="n">QoQ</th><th scope="col" class="n">YoY</th></tr></thead>
    <tbody>${r.rows.map((x) => `<tr><th scope="row">${esc(x.metric)}${x.derived && x.value != null ? "<sup>*</sup>" : ""}</th>
      <td class="n">${x.value == null ? `<span class="muted">${esc(x.note || "n/m")}</span>` : crShort(Math.round(x.value))}</td><td class="n">${pctc(x.qoq)}</td><td class="n">${pctc(x.yoy)}</td></tr>`).join("")}</tbody>
  </table>
  <p class="caption">QoQ vs ${esc(r.periods[1])}, YoY vs ${esc(r.periods[2])}. ${esc(r.basis)}${r.rows.some((x) => x.derived && x.value != null) ? " · *EBITDA = PBT + interest + depreciation − other income" : ""}. ${sourceButton(r.source, "Numbers")}</p>`;
}

function row(i, { high, selected }) {
  const label = i.alert && i.chg != null ? `<span class="chg ${i.chg >= 0 ? "up" : "down"}">${i.chg >= 0 ? "Up" : "Down"} ${Math.abs(i.chg).toFixed(1)}%</span> · ` : "";
  const why = i.why ? `<p class="why">${esc(i.why)}</p>` : i.detail ? `<p class="why"><span class="from">From the filing:</span> ${esc(clip(i.detail, 220))}</p>` : "";
  const results = i.resultsBlock ? (i.hideResults ? `<p class="note">Headline numbers are shown with the item above.</p>` : resultsMini(i.resultsBlock)) : i.resultsStatus ? `<p class="note">${esc(i.resultsStatus)}</p>` : "";
  return `<li class="row${high ? " high" : ""}${selected ? " sel" : ""}${i.news ? " is-news" : ""}" data-id="${esc(i.id)}">
    <p class="meta"><span class="co">${esc(i.company)}</span><span class="dot-sep">·</span>${esc(i.event)}<span class="dot-sep">·</span><time datetime="${esc(i.published_at)}">${esc(dt(i.published_at))}</time>${fixtureTag(i)}${sourceTag(i)}</p>
    <a class="title" href="#/briefing/item/${encodeURIComponent(i.id)}">${label}${esc(i.title)}</a>
    ${why}${results}
    <div class="foot">${sourceButton(i.source, i.news ? "Read" : "Source")}
      <span class="acts"><button type="button" class="link" data-act="done" data-id="${esc(i.id)}">Done</button><button type="button" class="link" data-act="snooze" data-id="${esc(i.id)}">Snooze 1 day</button></span>
    </div>
  </li>`;
}

export function briefingView({ sections, routine, hidden, windowId, asOf, summary, settings, holdings, selectedId, speaking, speechOk, routineOpen, live }) {
  const w = WINDOWS.find((x) => x.id === windowId);
  const seg = WINDOWS.map((x) => `<button type="button" class="seg-b" data-window="${x.id}" aria-pressed="${x.id === windowId}">${x.label}</button>`).join("");
  const full = sections.filter((s) => s.items.length);
  const empty = sections.filter((s) => !s.items.length);
  const isHigh = (i) => i.alert || i.tier === "high" || (i.score && i.score.total >= 70);
  return `
  <header class="page-head">
    <p class="kicker">Briefing · ${esc(dateLong(asOf))}</p>
    <h1 class="h1">What changed in your portfolio</h1>
    <p class="lede">${esc(summary)}</p>
    <dl class="context">
      <div><dt>Window</dt><dd>Last ${esc(w.label)} to ${esc(dt(asOf))} IST</dd></div>
      <div><dt>Portfolio</dt><dd>${holdings} holdings · <button type="button" class="link" data-act="open-settings">edit alerts</button></dd></div>
      <div><dt>Market alerts</dt><dd>±${settings.price_pct}% close or ${settings.vol_mult}× volume</dd></div>
      <div><dt>Data</dt><dd>${live
        ? `${live.fixture ? "Fixture API" : "Live"} · built ${esc(dt(asOf))} IST · <button type="button" class="link" data-act="refresh" ${live.refreshing ? "disabled" : ""}>${live.refreshing ? "Refreshing…" : "Refresh"}</button>`
        : `Fixture data as of ${esc(dt(asOf))}`}</dd></div>
    </dl>
    ${live?.message ? `<p class="note" role="status">${esc(live.message)}</p>` : ""}
    ${live?.disclosures?.length ? `<details class="notices"><summary>Data notes (${live.disclosures.length})</summary><ul>${live.disclosures.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
    <div class="controls">
      <div class="seg" role="group" aria-label="Time window">${seg}</div>
      <button type="button" class="btn" data-act="listen" ${speechOk ? "" : "disabled"} aria-pressed="${speaking}">${speaking ? I.stop + "Stop" : I.speaker + "Listen"}</button>
    </div>
    ${speechOk ? "" : `<p class="note">Spoken briefing needs a browser with speech synthesis.</p>`}
    <p class="legend-line"><span class="tag real">NSE filing</span> company's own disclosure · <span class="tag news">News</span> media report from a trusted outlet · <span class="tag">End of day</span> price data</p>
  </header>
  ${full.map((s) => `<section aria-labelledby="h-${s.id}" class="bsec">
    <h2 class="label" id="h-${s.id}">${esc(s.label)} <span class="count">${s.items.length}</span></h2>
    <ol class="rows">${s.items.map((i) => row(i, { high: isHigh(i), selected: i.id === selectedId })).join("")}</ol>
  </section>`).join("")}
  ${empty.length ? `<p class="empty-line">In this window: ${esc(empty.map((s) => s.empty).join("; "))}.</p>` : ""}
  <section class="routine">
    <button type="button" class="disclose" data-act="routine" aria-expanded="${routineOpen}" aria-controls="routine-list">
      <span>Routine filings</span><span class="count">${routine.length}</span><span class="chev" aria-hidden="true"></span>
    </button>
    <ul id="routine-list" class="rlist" ${routineOpen ? "" : "hidden"}>
      ${routine.map((i) => `<li><span class="meta"><span class="co">${esc(i.company)}</span><span class="dot-sep">·</span><time>${esc(dt(i.published_at))}</time>${fixtureTag(i)}</span><span class="rt">${esc(i.title)}</span>${sourceButton(i.source, i.source.url ? "Filing" : "Source")}</li>`).join("") || `<li class="empty">None in this window.</li>`}
    </ul>
  </section>
  ${hidden.length ? `<p class="hidden-note">${hidden.length} marked done or snoozed. <button type="button" class="link" data-act="restore">Show them again</button></p>` : ""}
  `;
}

export function itemDetail(i, { dossier, asPane }) {
  if (!i) return `<div class="pane-empty"><p>Select an item to see the analysis and its source.</p></div>`;
  let body = "";
  if (i.alert) {
    const c = i.calc;
    body += `<h3 class="label">Calculation${c.as_of ? `, session ${esc(c.as_of)}` : ""}</h3>
    <table class="tbl"><tbody>
      <tr><th scope="row">Close</th><td class="n">${price(c.close)}</td></tr>
      <tr><th scope="row">Previous close</th><td class="n">${price(c.prev_close)}</td></tr>
      <tr><th scope="row">Change</th><td class="n">${change(i.chg)}</td></tr>
      <tr><th scope="row">Volume</th><td class="n">${crShort(c.volume)}</td></tr>
      <tr><th scope="row">${c.lookback ? `${c.lookback}-session` : "20-day"} average volume</th><td class="n">${crShort(c.prev20 == null ? null : Math.round(c.prev20))}</td></tr>
      <tr><th scope="row">Multiple</th><td class="n">${times(i.mult)}</td></tr>
      ${c.thresholds ? `<tr><th scope="row">Your thresholds</th><td class="n">±${c.thresholds.pct_change_abs}% · ${c.thresholds.volume_multiple}×</td></tr>` : ""}
    </tbody></table>
    <p class="note">Evaluated against your thresholds each time the briefing loads. Change them under Portfolio &amp; alerts.</p>`;
  }
  if (i.resultsBlock) {
    body += `<h3 class="label">Headline numbers, ${esc(i.resultsBlock.periods[0])}</h3>${resultsMini(i.resultsBlock)}
      ${i.resultsBlock.notes?.length ? `<p class="note">${esc(i.resultsBlock.notes.join(" "))}</p>` : ""}
      <p class="note">From Screener's quarterly results table (₹ crore as published); changes computed by FINN. Check against the filing for the final word.</p>`;
  } else if (i.resultsStatus) {
    body += `<h3 class="label">Headline numbers</h3><p class="note">${esc(i.resultsStatus)}</p>`;
  }
  if (i.news) {
    body += `<h3 class="label">Media report</h3>
      <p>Reported by <b>${esc(i.publisher)}</b>. This is a news headline, not a company filing; FINN stores only the headline and link.</p>
      ${i.source.url ? `<p><a class="btn" href="${esc(i.source.url)}" target="_blank" rel="noopener">Read on ${esc(i.publisher)} ${I.ext}</a></p>` : ""}`;
  }
  if (i.results_ref && dossier && !i.resultsBlock) {
    const rows = periodTable(dossier.q, dossier.quarters);
    const m = margin(dossier.q.ebitda, dossier.q.revenue), n = m.length - 1;
    body += `<h3 class="label">Results, ${esc(dossier.quarters.at(-1))}</h3>${resultsTable(rows)}
    <p class="note">EBITDA margin ${pctv(m[n])}, ${pts(m[n] - m[n - 4])} year on year. Computed from the filed figures.</p>
    <p><a class="more" href="#/companies/${esc(i.symbol)}/financials">Open ${esc(i.company)} financials</a></p>`;
  }
  if (i.profile) {
    const p = i.profile;
    body += `<h3 class="label">Who</h3>
    <dl class="kv"><div><dt>Person</dt><dd>${esc(p.person)}</dd></div><div><dt>Role</dt><dd>${esc(p.role)}, ${esc(p.change)}</dd></div><div><dt>Effective</dt><dd>${esc(p.effective)}</dd></div></dl>
    <p>${esc(p.filing_profile)} ${citeButton(1, { doc: i.source.source_name, locator: i.source.locator, passage: p.passage })}</p>
    <p class="note">Profile is from the company's filing only. External background search is not part of this prototype.</p>`;
  }
  if (i.live && !i.alert && !i.news) {
    if (i.detail) body += `<h3 class="label">Filing text</h3><blockquote class="passage">${esc(i.detail)}</blockquote>
      <p class="note">Verbatim from the exchange announcement.</p>`;
    const c = i.classification;
    body += `<h3 class="label">Classification</h3>
      <p>${esc(CATEGORY_LABEL[c.category] || c.category)}${c.subtype ? ` · ${esc(i.event)}` : ""}. ${c.rule ? `Matched rule “${esc(c.rule)}”` : "No rule matched"}, confidence ${Math.round(c.confidence * 100)}%.</p>
      <p class="note">FINN doesn't read the document itself yet: results and management-profile extraction are the next build step. Open the original filing for the full text.</p>`;
  }
  if (i.live && i.news && i.classification) {
    body += `<h3 class="label">Classification</h3><p>${esc(CATEGORY_LABEL[i.classification.category] || i.classification.category)} (from the headline, rule “${esc(i.classification.rule || "none")}”).</p>`;
  }
  if (i.live && i.score) {
    body += `<h3 class="label">Why it's ranked here</h3>
      <ul class="reasons">${i.score.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <p class="note">Score ${i.score.total} of 100 = ${Object.entries(i.score.weights).map(([k, v]) => `${v} × ${k}`).join(" + ")}. Read first from 70; routine below 40.</p>`;
  }
  if (i.real && !i.live) {
    body += `<p class="note">This is a real NSE announcement (metadata observed on 29 Oct 2026). FINN's reading of the document needs the live backend, which this prototype does not include. Open the original below.</p>`;
  }
  return `<article class="detail">
    ${asPane ? "" : `<a class="back" href="#/briefing">${I.back}Briefing</a>`}
    <p class="meta"><span class="co">${esc(i.company)}</span><span class="dot-sep">·</span>${esc(CATEGORY_LABEL[i.category] || i.event)}<span class="dot-sep">·</span><time>${esc(dt(i.published_at))}</time>${fixtureTag(i)}${sourceTag(i)}</p>
    <h2 class="h2">${esc(i.title)}</h2>
    ${i.why ? `<p class="lede">${esc(i.why)}</p>` : ""}
    ${body}
    <h3 class="label">Source</h3>
    <p>${sourceButton(i.source, "Open evidence")}</p>
    ${dossier ? `<p><a class="more" href="#/companies/${esc(i.symbol)}/overview">Company research: ${esc(i.company)}</a></p>` : ""}
  </article>`;
}

function resultsTable(rows) {
  const names = { revenue: "Revenue", ebitda: "EBITDA", pbt: "PBT", pat: "PAT" };
  return `<table class="tbl"><thead><tr><th scope="col">₹ crore</th><th scope="col" class="n">Quarter</th><th scope="col" class="n">QoQ</th><th scope="col" class="n">YoY</th></tr></thead><tbody>
  ${rows.map((r) => `<tr><th scope="row">${names[r.key]}</th><td class="n">${crShort(r.value)}</td><td class="n">${change(r.qoq)}</td><td class="n">${change(r.yoy)}</td></tr>`).join("")}
  </tbody></table>`;
}

// ---------- Companies ----------
export function companiesView({ companies, query }) {
  const q = query.trim().toLowerCase();
  const match = (c) => !q || c.symbol.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
  const li = (c) => `<li><a class="crow" href="#/companies/${esc(c.symbol)}/overview">
      <span class="cname">${esc(c.name)}</span><span class="csym">NSE: ${esc(c.symbol)}</span>
      <span class="cstate">${c.fixture ? "Fixture data" : "Research not built yet"}</span></a></li>`;
  const holdings = companies.filter((c) => c.holding && match(c));
  const research = companies.filter((c) => !c.holding && match(c));
  const unknown = q && !holdings.length && !research.length;
  return `
  <header class="page-head">
    <p class="kicker">Companies</p>
    <h1 class="h1">Portfolio and research list</h1>
    <form class="search" role="search" data-form="company-search">
      <label for="csearch" class="sr">Search by company name or NSE symbol</label>
      <input id="csearch" name="q" type="search" autocomplete="off" placeholder="Company name or NSE symbol" value="${esc(query)}">
    </form>
    <p class="note">Full research pages exist only for the four fixture companies so far. Real companies appear in the live Briefing; their research pages are the next build step.</p>
  </header>
  ${unknown ? `<p class="empty">No match in your list. In the live app, any NSE-listed symbol can be researched; this prototype has no data for <b>${esc(query.toUpperCase())}</b>.</p>` : ""}
  ${holdings.length ? `<section><h2 class="label">Holdings <span class="count">${holdings.length}</span></h2><ul class="clist">${holdings.map(li).join("")}</ul></section>` : ""}
  ${research.length ? `<section><h2 class="label">Research list <span class="count">${research.length}</span></h2><ul class="clist">${research.map(li).join("")}</ul></section>` : ""}`;
}

const SECTIONS = [["overview", "Overview"], ["financials", "Financials"], ["cash", "Cash & debt"], ["promises", "Promises"]];

export function companyView({ company, dossier, section }) {
  if (!dossier) {
    return `<a class="back" href="#/companies">${I.back}Companies</a>
    <header class="page-head">
      <p class="kicker">NSE: ${esc(company.symbol)}</p>
      <h1 class="h1">${esc(company.name)}</h1>
      <p class="lede">Company research isn't built yet.</p>
      <p>This page will be built from the company's NSE filings, quarterly results tables, earnings-call transcripts and annual reports, with every figure linked to its source. Until then it shows nothing rather than placeholder numbers. Its filings and price alerts already appear in the Briefing.</p>
      <p><a class="more" href="https://www.nseindia.com/get-quotes/equity?symbol=${encodeURIComponent(company.symbol)}" target="_blank" rel="noopener">Open ${esc(company.symbol)} on NSE ${I.ext}</a></p>
    </header>`;
  }
  const d = dossier;
  const nav = SECTIONS.map(([id, label]) => `<a href="#/companies/${esc(d.symbol)}/${id}" ${id === section ? 'aria-current="page"' : ""}>${label}</a>`).join("");
  const body = { overview, financials, cash, promises }[section](d);
  return `<a class="back" href="#/companies">${I.back}Companies</a>
  <header class="co-head">
    <p class="kicker">NSE: ${esc(d.symbol)} · ${esc(d.sector)}<span class="tag">Fixture</span></p>
    <h1 class="h1">${esc(d.company)}</h1>
    <p class="price"><span class="pv">${price(d.price.value)}</span> <span class="muted">close ${esc(d.price.date)} · ${esc(d.price.source)}</span></p>
    <p class="muted small">Sources: ${d.coverage.transcripts} call transcripts, ${d.coverage.annual_reports} annual report · updated ${esc(d.coverage.updated_at)} · all fixture documents</p>
  </header>
  <nav class="secnav" aria-label="Company sections">${nav}</nav>
  <div class="sec">${body}</div>`;
}

function overview(d) {
  const rows = periodTable(d.q, d.quarters);
  const m = margin(d.q.ebitda, d.q.revenue);
  const ttm = d.q.revenue.slice(-4).reduce((a, b) => a + b, 0);
  const cq = cashQuality(d);
  const tally = STATUSES.map((s) => [s, d.ledger.filter((r) => verdict(r) === s).length]).filter(([, n]) => n);
  return `
  <p class="lede">${esc(d.overview.summary)} ${citeButton(1, d.overview.cite)}</p>
  <h2 class="label">At a glance</h2>
  <dl class="facts">
    <div><dt>Revenue, ${esc(d.quarters.at(-1))}</dt><dd>${cr(rows[0].value)} <small>${change(rows[0].yoy)} YoY</small></dd></div>
    <div><dt>Revenue, trailing four quarters</dt><dd>${cr(ttm)}</dd></div>
    <div><dt>EBITDA margin, ${esc(d.quarters.at(-1))}</dt><dd>${pctv(m.at(-1))} <small>${pts(m.at(-1) - m.at(-5))} YoY</small></dd></div>
    <div><dt>${cq.netCash ? "Net cash" : "Net debt to EBITDA"}</dt><dd>${cq.netCash ? cr(-d.debt.net_debt) : times(cq.netDebtEbitda)}</dd></div>
    <div><dt>Operating cash to PAT, ${esc(d.years[0])}–${esc(d.years.at(-1))}</dt><dd>${times(cq.cumConv)}</dd></div>
    <div><dt>Promises tracked</dt><dd>${d.ledger.length} <small>${tally.map(([s, n]) => `${n} ${s.toLowerCase()}`).join(", ")}</small></dd></div>
  </dl>
  <h2 class="label">Revenue by segment, ${esc(d.years.at(-1))}</h2>
  <table class="tbl"><thead><tr><th scope="col">Segment</th><th scope="col" class="n">Share of revenue</th></tr></thead><tbody>
  ${d.overview.segments.map((s) => `<tr><th scope="row">${esc(s.name)}</th><td class="n"><span class="share" style="--w:${s.share}%"></span>${s.share}%</td></tr>`).join("")}
  </tbody></table>
  <p class="caption">Source: ${esc(d.overview.segments_cite.doc)}, page ${d.overview.segments_cite.page} ${citeButton(2, d.overview.segments_cite)}</p>`;
}

function financials(d) {
  const rows = periodTable(d.q, d.quarters);
  const m = margin(d.q.ebitda, d.q.revenue);
  const rev = chartRef("bar", { labels: d.quarters, values: d.q.revenue, unit: "₹ crore", label: `Quarterly revenue, ₹ crore, ${d.quarters[0]} to ${d.quarters.at(-1)}` });
  const mar = chartRef("line", { labels: d.quarters, values: m, unit: "%", label: `EBITDA margin, percent, ${d.quarters[0]} to ${d.quarters.at(-1)}` });
  const full = ["revenue", "ebitda", "pbt", "pat"];
  const nm = { revenue: "Revenue", ebitda: "EBITDA", pbt: "PBT", pat: "PAT" };
  return `
  <h2 class="label">${esc(d.quarters.at(-1))} against prior periods</h2>
  ${resultsTable(rows)}
  <p class="caption">₹ crore, consolidated. QoQ against ${esc(d.quarters.at(-2))}, YoY against ${esc(d.quarters.at(-5))}. Source: ${esc(d.q_source)}.</p>

  <figure class="fig">
    <figcaption><b>Quarterly revenue</b><span>₹ crore · ${esc(d.quarters[0])} to ${esc(d.quarters.at(-1))}</span></figcaption>
    <div class="chart" data-chart="${rev}"></div>
  </figure>
  <figure class="fig">
    <figcaption><b>EBITDA margin</b><span>EBITDA ÷ revenue, % · axis does not start at zero</span></figcaption>
    <div class="chart" data-chart="${mar}"></div>
  </figure>
  <p class="caption">Source: ${esc(d.q_source)}. Margin computed by FINN from the filed EBITDA and revenue.</p>

  <details class="tview"><summary>All eight quarters as a table</summary>
    <div class="scroll"><table class="tbl wide"><thead><tr><th scope="col">₹ crore</th>${d.quarters.map((q) => `<th scope="col" class="n">${esc(q)}</th>`).join("")}</tr></thead><tbody>
    ${full.map((k) => `<tr><th scope="row">${nm[k]}</th>${d.q[k].map((v) => `<td class="n">${crShort(v)}</td>`).join("")}</tr>`).join("")}
    <tr><th scope="row">EBITDA margin</th>${m.map((v) => `<td class="n">${pctv(v)}</td>`).join("")}</tr>
    </tbody></table></div>
  </details>`;
}

function cash(d) {
  const cq = cashQuality(d);
  const ch = chartRef("grouped", { labels: d.years, a: d.cash.ocf, b: d.cash.pat, names: ["Operating cash flow", "PAT"], label: `Operating cash flow and profit after tax, ₹ crore, ${d.years[0]} to ${d.years.at(-1)}` });
  return `
  <p class="lede">Operating cash flow was ${times(cq.cumConv)} of reported profit over ${esc(d.years[0])}–${esc(d.years.at(-1))}${cq.cumConv < 0.9 ? ", so some profit has not yet turned into cash" : ""}.</p>
  <figure class="fig">
    <figcaption><b>Operating cash flow and PAT</b><span>₹ crore · same unit, one scale · ${esc(d.years[0])} to ${esc(d.years.at(-1))}</span></figcaption>
    <ul class="legend"><li><i class="sw s1"></i>Operating cash flow</li><li><i class="sw s2"></i>PAT</li></ul>
    <div class="chart" data-chart="${ch}"></div>
  </figure>
  <div class="scroll"><table class="tbl wide"><thead><tr><th scope="col">₹ crore</th>${d.years.map((y) => `<th scope="col" class="n">${y}</th>`).join("")}</tr></thead><tbody>
    <tr><th scope="row">Operating cash flow</th>${d.cash.ocf.map((v) => `<td class="n">${crShort(v)}</td>`).join("")}</tr>
    <tr><th scope="row">PAT</th>${d.cash.pat.map((v) => `<td class="n">${crShort(v)}</td>`).join("")}</tr>
    <tr><th scope="row">OCF ÷ PAT</th>${cq.conv.map((v) => `<td class="n">${times(v)}</td>`).join("")}</tr>
    <tr><th scope="row">Capex</th>${d.cash.capex.map((v) => `<td class="n">${crShort(v)}</td>`).join("")}</tr>
    <tr><th scope="row">Free cash flow</th>${cq.fcf.map((v) => `<td class="n">${crShort(v)}</td>`).join("")}</tr>
    <tr><th scope="row">Working-capital days</th>${d.debt.wc_days.map((v) => `<td class="n">${v}</td>`).join("")}</tr>
  </tbody></table></div>
  <p class="caption">Free cash flow = operating cash flow − capex. Source: ${esc(d.cash_source)}.</p>

  <h2 class="label">Leverage, ${esc(d.years.at(-1))} year end</h2>
  <dl class="facts">
    <div><dt>${cq.netCash ? "Net cash" : "Net debt"}</dt><dd>${cr(Math.abs(d.debt.net_debt))}</dd></div>
    <div><dt>Net debt ÷ EBITDA (trailing)</dt><dd>${cq.netCash ? "Net cash" : times(cq.netDebtEbitda)}</dd></div>
    <div><dt>Net debt ÷ equity</dt><dd>${cq.netCash ? "Net cash" : times(cq.netDebtEquity)}</dd></div>
    <div><dt>Shareholders' equity</dt><dd>${cr(d.debt.equity)}</dd></div>
  </dl>
  <p class="caption">Net debt = borrowings − cash and investments, from the balance sheet. Source: ${esc(d.cash_source)}.</p>`;
}

const statusClass = (s) => ({ Delivered: "ok", "Partly delivered": "part", Missed: "miss" }[s] || "na");

function promises(d) {
  return `
  <p class="lede">What management said, and what happened. Verdicts for numeric targets are computed by FINN; qualitative statements are checked for direction only.</p>
  <ol class="ledger">
  ${d.ledger.map((r) => {
    const s = verdict(r);
    const unit = r.band?.unit;
    const strip = r.kind === "quant" && r.scale && r.actual
      ? chartRef("strip", { band: r.band, actual: r.actual.value, scale: r.scale, unit, label: r.metric }) : null;
    const said = { doc: r.said.doc, page: r.said.page, passage: `“${r.statement}”`, date: r.said.date };
    const f = unitFmt(unit);
    const target = r.kind === "quant"
      ? (r.band.low === r.band.high ? `About ${f(r.band.low)}` : `${f(r.band.low)} to ${f(r.band.high)}`)
      : "No numeric target stated";
    const result = r.actual
      ? (r.kind === "quant" ? `${f(r.actual.value)}, ${esc(r.actual.period)}` : esc(r.actual.text))
      : "No result yet";
    return `<li class="lrow">
      <div class="lhead"><h3 class="h3">${esc(r.metric)} <span class="muted">· ${esc(r.period)}</span></h3><span class="status ${statusClass(s)}">${esc(s)}</span></div>
      <blockquote class="said">“${esc(r.statement)}” ${citeButton("Said", said)}<footer>${esc(r.said.doc)}, ${esc(r.said.date)}, page ${r.said.page}</footer></blockquote>
      ${strip ? `<div class="chart strip" data-chart="${strip}"></div>` : ""}
      <dl class="kv">
        <div><dt>Target</dt><dd>${target}</dd></div>
        <div><dt>Result</dt><dd>${result}${r.actual?.doc ? " " + citeButton("Result", { doc: r.actual.doc, page: r.actual.page, passage: r.kind === "quant" ? `${r.metric}: ${f(r.actual.value)}` : r.actual.text }) : ""}</dd></div>
        <div><dt>Compared by</dt><dd>${esc(r.method)}</dd></div>
      </dl>
      <p class="why">${esc(r.why)}</p>
    </li>`;
  }).join("")}
  </ol>
  <p class="caption">Rule: at or beyond the promised range is delivered; within 10% short of it is partly delivered; further short is missed. Periods that have not ended are not yet measurable.</p>`;
}

// ---------- Research ----------
export function researchView({ companies, symbol, notes, examples, speechOk, speakingId }) {
  const opts = companies.map((c) => `<option value="${esc(c.symbol)}" ${c.symbol === symbol ? "selected" : ""}>${esc(c.name)}</option>`).join("");
  const company = companies.find((c) => c.symbol === symbol);
  return `
  <header class="page-head">
    <p class="kicker">Research</p>
    <h1 class="h1">Ask about a company</h1>
    <form class="ask" data-form="ask">
      <div class="ask-co"><label for="rco">Company</label><select id="rco" name="symbol" data-act="company">${opts}</select></div>
      <label for="rq" class="sr">Your question</label>
      <textarea id="rq" name="q" rows="2" placeholder="Ask about results, guidance, cash flow or management commentary"></textarea>
      <div class="ask-foot"><span class="note">Answers cite filings and transcripts. Prototype: prepared answers for the example questions only.</span><button type="submit" class="btn primary">Ask</button></div>
    </form>
    ${examples.length ? `<div class="examples"><p class="label-sm">Examples for ${esc(company?.name || "")}</p><ul>${examples.map((e, k) => `<li><button type="button" class="link" data-ask="${k}">${esc(e)}</button></li>`).join("")}</ul></div>`
      : `<p class="note">No prepared answers for ${esc(company?.name || "this company")} in the prototype.</p>`}
  </header>
  <div class="notes" aria-live="polite">
    ${notes.map((n) => noteView(n, { speechOk, speaking: speakingId === n.id, followups: examples })).join("")}
  </div>`;
}

function noteView(n, { speechOk, speaking, followups }) {
  if (!n.answer) {
    return `<article class="note-card" id="${n.id}"><p class="meta">${esc(n.company)}</p><h2 class="h2">${esc(n.q)}</h2>
    <p>FINN can't answer this here. The prototype holds prepared answers for the example questions only; free questions need the live backend, which retrieves passages from the company's filings and transcripts and drops any claim it cannot cite.</p></article>`;
  }
  const a = n.answer;
  let k = 0;
  const cites = [];
  const finding = (f) => { k++; cites.push(f.cite); return `<li>${esc(f.text)} ${citeButton(k, f.cite)}</li>`; };
  const fu = followups.filter((q) => q !== n.q);
  return `<article class="note-card" id="${n.id}">
    <p class="meta">${esc(n.company)}<span class="tag">Fixture</span></p>
    <h2 class="h2">${esc(n.q)}</h2>
    <h3 class="label">Findings</h3><ul class="findings">${a.findings.map(finding).join("")}</ul>
    <h3 class="label">What it may mean <span class="muted">· interpretation</span></h3><p>${esc(a.implication)}</p>
    <h3 class="label">Uncertainty</h3><p>${esc(a.uncertainty)}</p>
    <h3 class="label">Sources</h3><ol class="srcs">${cites.map((c, i) => `<li>${esc(c.doc)}, page ${c.page} ${citeButton(i + 1, c)}</li>`).join("")}</ol>
    <div class="note-foot">
      <button type="button" class="btn" data-act="speak-note" data-id="${n.id}" ${speechOk ? "" : "disabled"} aria-pressed="${speaking}">${speaking ? I.stop + "Stop" : I.speaker + "Listen"}</button>
      ${fu.length ? `<span class="fu">Follow up: ${fu.slice(0, 2).map((q) => `<button type="button" class="link" data-ask-text="${esc(q)}">${esc(q)}</button>`).join("")}</span>` : ""}
    </div>
  </article>`;
}

// ---------- Dialog bodies ----------
export function evidenceBody(e) {
  const cls = { PRIMARY_DOC: "Primary document", MARKET_DATA: "Market data", STANDARDIZED_TABLE: "Standardized table", DERIVED: "Computed by FINN" }[e.source_class] || "Source";
  return `
  <p class="kicker">${esc(cls)}${e.fixture ? `<span class="tag">Fixture</span>` : ""}</p>
  <h2 class="h2" id="dlg-title">${esc(e.source_name)}</h2>
  <dl class="kv">${e.locator ? `<div><dt>Location</dt><dd>${esc(e.locator)}</dd></div>` : ""}${e.date ? `<div><dt>Date</dt><dd>${esc(e.date)}</dd></div>` : ""}</dl>
  ${e.passage ? `<blockquote class="passage">${esc(e.passage)}</blockquote>` : ""}
  ${e.url ? `<p><a class="btn" href="${esc(e.url)}" target="_blank" rel="noopener">Open original ${I.ext}</a></p><p class="note">${esc(e.note || "Opens the filing on the exchange's site.")}</p>`
    : e.fixture ? `<p class="note">Demonstration document. There is no original to open.</p>` : ""}`;
}

export function settingsBody({ settings, holdings, sources }) {
  const st = { ok: "working", degraded: "partly working", failed: "failing", disabled: "switched off", fixture: "fixture", cached: "cached" };
  const cats = [["results", "Results"], ["management_change", "Management change"], ["M&A", "M&A"], ["litigation", "Litigation"], ["credit_rating", "Credit rating"], ["market_move", "Price and volume alerts"]];
  return `
  <h2 class="h2" id="dlg-title">Alert settings</h2>
  <form data-form="settings" class="settings">
    <fieldset><legend>Market alerts</legend>
      <label class="field"><span>Daily close moves at least</span><span class="inp"><input name="price_pct" type="number" min="1" max="20" step="0.5" value="${settings.price_pct}" required> %</span></label>
      <label class="field"><span>Volume at least</span><span class="inp"><input name="vol_mult" type="number" min="1.2" max="10" step="0.1" value="${settings.vol_mult}" required> × 20-day average</span></label>
    </fieldset>
    <fieldset><legend>Highlight these updates</legend>
      ${cats.map(([k, l]) => `<label class="check"><input type="checkbox" name="cat" value="${esc(k)}" ${settings.categories[k] !== false ? "checked" : ""}> ${l}</label>`).join("")}
      <p class="note">Unticked types move to Other updates; unticking price and volume stops market alerts.</p>
    </fieldset>
    <p class="note">Add or remove stocks in the Portfolio tab. Alert settings are saved on this device.</p>
    <div class="dlg-actions"><button type="button" class="link" data-act="reset-settings">Reset to defaults</button><button type="submit" class="btn primary">Save</button></div>
  </form>`;
}

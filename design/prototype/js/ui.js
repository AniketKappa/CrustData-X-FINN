import { signalCard, healthCard, rankBadge, rankFormula, CAVEAT } from "./signal.js";
// Views for the v3 app (D-55): Briefing, item detail, Portfolio and live company pages. HTML strings only.
import { esc, crShort, price, change, dt, timeAgo, clock, dayLong, greeting, pctPill, avatar, shortName, shortDate } from "./format.js";
import { WINDOWS, CATEGORY_LABEL } from "./logic.js";
import { evRef, chartRef, icons as I } from "./views.js";

const SRC = {
  filing: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.5h7l3 3v12H5z"/><path d="M8 9h5M8 12h5"/></svg>`,
  news: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="2"/><path d="M6 8h8M6 11h5"/></svg>`,
  refresh: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M16 10a6 6 0 1 1-1.8-4.3M16 3.5V6.5h-3"/></svg>`,
  search: `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5"/><path d="M13 13l4 4"/></svg>`,
  x: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15"/></svg>`,
  plus: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12"/></svg>`,
  trash: `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"/></svg>`,
};

const GENERIC = /^(updates?|general updates?|credit rating|outcome of (the )?board meeting|analysts\/institutional investor meet\/con\. call updates|change in directors\/ ?key managerial personnel|press release|copy of newspaper publication|disclosure under sebi.*)$/i;
const clip1 = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const sourceLabel = (i) => (i.alert ? "Yahoo Finance, end of day" : i.news ? esc(i.publisher) : `${esc(i.exchange || "NSE")} filing`);

// ---------------------------------------------------------------- Briefing rows
function moveTags(i) {
  const t = [];
  if (i.rules?.includes("volume") && i.mult) t.push(`<span class="chip-tag">Volume ${i.mult.toFixed(1)}× average</span>`);
  return t.join("");
}

export function tiles(r) {
  if (!r) return "";
  const c = (v, k) => (v == null ? `<span class="c na">${k} —</span>` : `<span class="c ${v >= 0 ? "up" : "down"}">${k} ${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%</span>`);
  return `<div class="tiles" role="group" aria-label="Results ${esc(r.periods[0])}, ₹ crore">${r.rows.map((x) => `<div class="tile">
    <span class="k">${esc(x.metric)}</span><span class="v">${x.value == null ? "n/m" : "₹" + crShort(Math.round(x.value)) + " cr"}</span>${c(x.yoy, "YoY")}${c(x.qoq, "QoQ")}</div>`).join("")}</div>`;
}

function row(i, { selected, older }) {
  const href = `#/briefing/item/${encodeURIComponent(i.id)}`;
  const sym = esc(i.symbol || "");
  if (i.alert) {
    const c = i.calc || {};
    return `<a class="li${selected ? " sel" : ""}${older ? " older" : ""}" href="${href}" data-id="${esc(i.id)}">
      <div class="li-top">${avatar(i.symbol, i.company)}<span class="li-co"><span class="nm">${esc(shortName(i.company))}</span>
        <span class="sub">${sym} · ${c.live ? "Today so far" : c.as_of ? "Close " + esc(shortDate(c.as_of)) : esc(timeAgo(i.published_at))}</span></span>
        <span class="li-right"><span class="px">${c.close != null ? price(c.close) : ""}</span>${pctPill(i.chg)}</span></div>
      <div class="li-tags">${moveTags(i)}</div></a>`;
  }
  const r = i.resultsBlock && !i.hideResults ? tiles(i.resultsBlock) : "";
  // Exchanges often file under a generic subject ("Updates"); then the filing's own text is the better headline.
  const generic = !i.news && i.detail && GENERIC.test(i.title);
  const head = generic ? clip1(i.detail, 160) : i.title;
  return `<a class="li${selected ? " sel" : ""}${older ? " older" : ""}" href="${href}" data-id="${esc(i.id)}">
    <div class="li-top">${avatar(i.symbol, i.company)}<span class="li-co"><span class="nm">${esc(shortName(i.company))}</span>
      <span class="sub">${sym} · ${esc(timeAgo(i.published_at))}</span></span>${i.fixture ? `<span class="tag">Demo</span>` : ""}</div>
    <p class="li-head">${esc(head)}</p>${i.summary ? `<p class="li-sum">${esc(i.summary.text)}</p>` : ""}${r}${personMini(i.person)}
    <div class="li-meta">${i.news ? SRC.news : SRC.filing}<span>${sourceLabel(i)}</span></div></a>`;
}

function personMini(p) {
  if (!p || (!p.name && !p.outgoing)) return "";
  const role = p.role ? esc(p.role.replace(/^./, (c) => c.toUpperCase())) : "Role";
  const bg = p.brief || p.lines?.[0]?.text || "";
  return `<div class="person">
    <div class="person-row">${p.name ? `<span class="pk">Incoming</span><span class="pv">${esc(p.name)}</span>` : ""}
      ${p.outgoing ? `<span class="pk">Outgoing</span><span class="pv">${esc(p.outgoing)}</span>` : ""}<span class="pk">Role</span><span class="pv">${role}</span></div>
    ${bg ? `<p class="person-bio">${esc(bg.replace(/\s*\[\d+\]/g, "").slice(0, 140))}${bg.length > 140 ? "…" : ""}</p>` : ""}</div>`;
}

const CAP = 5;
// ---------------------------------------------------------------- Briefing grouped by company
// One card per company: its price move, ONE results item (the one with numbers; the other filings about the same
// results are folded under it), then other filings, then media headlines. Companies with the most important
// update come first (same score the type view uses).
const RANKV = (i) => (i.score ? i.score.total : (i.tier === "high" ? 80 : 50));
function compactRow(i, selectedId, label) {
  const generic = !i.news && i.detail && GENERIC.test(i.title);
  const head = generic ? clip1(i.detail, 160) : i.title;
  return `<a class="crow${i.id === selectedId ? " sel" : ""}" href="#/briefing/item/${encodeURIComponent(i.id)}" data-id="${esc(i.id)}">
    <span class="ck">${esc(label)}</span><span class="ct">${esc(clip1(head, 180))}</span>
    <span class="cm">${i.news ? SRC.news : SRC.filing}${sourceLabel(i)} · ${esc(timeAgo(i.published_at))}</span></a>`;
}
export function companyCards(sections, { selectedId, filter, expanded = new Set() }) {
  const items = sections.filter((s) => filter === "all" || filter === s.id).flatMap((s) => s.items.map((i) => ({ ...i, _sec: s })));
  const by = new Map();
  for (const i of items) {
    const k = i.symbol || i.company;
    if (!by.has(k)) by.set(k, { symbol: i.symbol, company: i.company, items: [], top: 0 });
    const g = by.get(k); g.items.push(i); g.top = Math.max(g.top, RANKV(i));
  }
  const groups = [...by.values()].sort((a, b) => b.top - a.top || b.items.length - a.items.length);
  if (!groups.length) return "";
  return `<section class="bsec" aria-label="Updates by company">${groups.map((g) => {
    const alert = g.items.find((i) => i.alert);
    const results = g.items.filter((i) => !i.alert && !i.news && i._sec.id === "results");
    const main = results.find((i) => i.resultsBlock) || results[0];
    const folded = results.filter((i) => i !== main);
    const filings = g.items.filter((i) => !i.alert && !i.news && i._sec.id !== "results").sort((a, b) => RANKV(b) - RANKV(a));
    const news = g.items.filter((i) => i.news).sort((a, b) => new Date(b.published_at) - new Date(a.published_at));
    const key = `co:${g.symbol}`, open = expanded.has(key);
    const extra = filings.slice(open ? 99 : 2).length + news.slice(open ? 99 : 1).length;
    const c = alert?.calc || {};
    return `<article class="card cocard">
      <a class="co-head" href="#/company/${encodeURIComponent(g.symbol || "")}/overview">${avatar(g.symbol, g.company)}
        <span class="li-co"><span class="nm">${esc(shortName(g.company))}</span><span class="sub">${esc(g.symbol || "")} · ${g.items.length} update${g.items.length === 1 ? "" : "s"}</span></span>
        ${alert ? `<span class="li-right"><span class="px">${c.close != null ? price(c.close) : ""}</span>${pctPill(alert.chg)}</span>` : `<span class="chev-r" aria-hidden="true"></span>`}</a>
      ${alert ? compactRow({ ...alert, title: alert.title || "Price move" }, selectedId, "Move") : ""}
      ${main ? `${compactRow(main, selectedId, "Results")}${main.resultsBlock && !main.hideResults ? `<div class="co-tiles">${tiles(main.resultsBlock)}</div>` : ""}
        ${folded.length ? `<details class="fold"><summary>${folded.length} more filing${folded.length === 1 ? "" : "s"} about these results</summary>${folded.map((i) => compactRow(i, selectedId, "Results")).join("")}</details>` : ""}` : ""}
      ${filings.slice(0, open ? 99 : 2).map((i) => compactRow(i, selectedId, i._sec.short || "Filing")).join("")}
      ${news.slice(0, open ? 99 : 1).map((i) => compactRow(i, selectedId, "News")).join("")}
      ${extra > 0 ? `<button type="button" class="more-row" data-more="${esc(key)}">Show ${extra} more</button>` : open && (filings.length > 2 || news.length > 1) ? `<button type="button" class="more-row" data-more="${esc(key)}">Show fewer</button>` : ""}
    </article>`;
  }).join("")}</section>`;
}

export function briefingV3({ movers = [], sessions = 1, sections, routine, hidden, windowId, asOf, holdings, holdingSyms = null, selectedId, group = "company", brief = "", speaking, speechOk, routineOpen, live, filter, counts, expanded = new Set(), busy = new Set() }) {
  const w = WINDOWS.find((x) => x.id === windowId);
  const total = sections.reduce((n, s) => n + s.items.filter((i) => !i.older).length, 0);
  const touched = new Set(sections.flatMap((s) => s.items.filter((i) => !i.older).map((i) => i.symbol)));
  // B2: count holdings and watchlist stocks separately ("13 of your 20 holdings and 2 watchlist stocks").
  const companies = holdingSyms ? [...touched].filter((x) => holdingSyms.has(x)).length : touched.size;
  const watchN = holdingSyms ? touched.size - companies : 0;
  const parts = sections.filter((s) => s.items.some((i) => !i.older)).map((s) => { const n = s.items.filter((i) => !i.older).length; return `${n} ${n === 1 ? s.one : s.many}`; });
  // By company: every count is a number of companies (one card each), not of individual filings.
  if (group === "company") {
    const live2 = (s) => new Set(s.items.filter((i) => !i.older).map((i) => i.symbol || i.company)).size;
    counts = Object.fromEntries(sections.map((s) => [s.id, live2(s)]));
  }
  const allN = group === "company" ? touched.size : total;
  const sum = total
    ? (group === "company"
      ? `<b>${touched.size} compan${touched.size === 1 ? "y" : "ies"}</b> with updates: ${companies} of your ${holdings} holdings${watchN ? ` and ${watchN} on your watchlist` : ""} · last ${esc(w.label)}`
      : `<b>${total} update${total === 1 ? "" : "s"}</b> across ${companies} of your ${holdings} holdings${watchN ? ` and ${watchN} watchlist stock${watchN === 1 ? "" : "s"}` : ""} · last ${esc(w.label)}`)
    : live?.refreshing ? `Fetching prices, filings and news for your ${holdings} holdings…`
    : `A quiet ${esc(w.label)} for your ${holdings} holdings. Try 3D or 7D for the wider picture.`;
  void parts;
  const chips = [`<button type="button" class="chip" data-filter="all" aria-pressed="${filter === "all"}">All <span class="n">${allN}</span></button>`]
    .concat(sections.map((s) => `<button type="button" class="chip${counts[s.id] ? "" : " zero"}" data-filter="${s.id}" aria-pressed="${filter === s.id}">${esc(s.short)} <span class="n">${counts[s.id]}</span></button>`)).join("");
  const seg = WINDOWS.map((x) => `<button type="button" class="seg-b" data-window="${x.id}" aria-pressed="${x.id === windowId}">${x.id.toUpperCase()}</button>`).join("");
  const shown = sections.filter((s) => (filter === "all" || filter === s.id) && s.items.length);
  const emptyNames = sections.filter((s) => !s.items.length).map((s) => s.label.toLowerCase());
  return `
  <section class="hero">
    <p class="date">${esc(dayLong(asOf))} · ${live ? (live.fixture ? "Demo data" : `Updated ${esc(clock(asOf))}`) : "Demo data"}</p>
    <h1>Briefing</h1>
    <p class="sum">${sum}</p>
    <div class="hero-meta">
      ${live ? `<button type="button" data-act="refresh" ${live.refreshing ? 'disabled aria-busy="true"' : ""}>${SRC.refresh}${live.refreshing ? "Updating…" : "Refresh"}</button>` : ""}
      <span class="dot"></span><button type="button" data-act="listen" ${speechOk ? "" : "disabled"} aria-pressed="${speaking}">${speaking ? I.stop + "Stop" : I.speaker + "Listen"}</button>
    </div>
    ${live?.message ? `<p class="note" role="status" style="margin-top:8px">${esc(live.message)}</p>` : ""}
  </section>
  ${brief}
  <div class="toolbar brief"><div class="seg" role="group" aria-label="Time window">${seg}</div>
    <div class="seg" role="group" aria-label="Group updates"><button type="button" class="seg-b" data-group="company" aria-pressed="${group === "company"}">By company</button><button type="button" class="seg-b" data-group="type" aria-pressed="${group !== "company"}">By type</button></div></div>
  <div class="tabwrap"><nav class="tabbar" role="group" aria-label="Show">${chips}</nav><button type="button" class="tab-more" aria-label="More tabs" tabindex="-1"><svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 5l5 5-5 5"/></svg></button></div>
  ${filter === "all" && movers.length ? `<section class="bsec" aria-labelledby="h-movers">
    <div class="sec-head"><h2 class="sec-title" id="h-movers">Biggest moves</h2><span class="sec-sub">${sessions === 1 ? (movers.some((m) => m.live) ? "today so far" : "last session") : `last ${sessions} sessions`}</span></div>
    <div class="movers">${movers.map((m) => `<a class="mover" href="#/company/${encodeURIComponent(m.symbol)}/overview"><span class="tk">${esc(m.symbol)}</span><span class="nm">${esc(shortName(m.name))}</span>${pctPill(m.chg)}</a>`).join("")}</div></section>` : ""}
  ${group === "company" ? (companyCards(shown, { selectedId, filter, expanded }) || (live?.refreshing ? `<p class="note" role="status">Getting the latest data…</p>` : `<div class="card empty-card">Nothing here in the last ${esc(w.label)}. Try a longer window.</div>`)) : shown.map((s) => {
    const open = expanded.has(s.id) || filter === s.id;
    const shownItems = open ? s.items : s.items.slice(0, CAP);
    const rest = s.items.length - shownItems.length;
    return `<section class="bsec" aria-labelledby="h-${s.id}">
      <div class="sec-head"><h2 class="sec-title" id="h-${s.id}">${esc(s.label)}<span class="n">${s.items.length}</span></h2></div>
      <div class="card list">${shownItems.map((i) => row(i, { selected: i.id === selectedId })).join("")}
        ${rest > 0 ? `<button type="button" class="more-row" data-more="${s.id}">Show ${rest} more</button>` : open && s.items.length > CAP && filter !== s.id ? `<button type="button" class="more-row" data-more="${s.id}">Show fewer</button>` : ""}</div></section>`;
  }).join("") || (live?.refreshing ? `<div class="skeleton" aria-hidden="true" style="margin-top:16px"><span></span><span></span><span></span></div><p class="note" role="status">Getting the latest data. This takes a few seconds; the list fills in on its own.</p>`
    : `<div class="card empty-card">Nothing here in the last ${esc(w.label)}. Try a longer window.</div>`)}
  ${filter === "all" && emptyNames.length && shown.length ? `<p class="empty-line">No ${esc(emptyNames.join(", "))} in the last ${esc(w.label)}.</p>` : ""}
  ${filter === "all" ? `<section class="routine">
    <button type="button" class="disclose" data-act="routine" aria-expanded="${routineOpen}" aria-controls="routine-list">
      <span>Routine filings</span><span class="count">${routine.length}</span><span class="chev" aria-hidden="true"></span></button>
    <ul id="routine-list" class="rlist" ${routineOpen ? "" : "hidden"}>
      ${routine.map((i) => `<li><span class="meta">${esc(shortName(i.company))} · ${esc(timeAgo(i.published_at))}</span><span class="rt">${i.source?.url ? `<a href="${esc(i.source.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)}</span></li>`).join("") || `<li class="empty">None in this window.</li>`}
    </ul></section>` : ""}
  ${hidden.length ? `<p class="hidden-note">${hidden.length} cleared or snoozed · <button type="button" class="link" data-act="restore">Show again</button></p>` : ""}
  <div class="foot-links"><button type="button" class="link" data-act="about-data">About this data</button><button type="button" class="link" data-act="open-settings">Alert settings</button></div>`;
}

// ---------------------------------------------------------------- item detail
export function detailV3(i, { asPane, settings }) {
  if (!i) return `<div class="pane-empty"><p>Select an update to see the details and the source.</p></div>`;
  const head = `<div class="head">${avatar(i.symbol, i.company, true)}<div><div style="font-weight:700">${esc(shortName(i.company))}</div>
    <div class="note" style="margin:0">${esc(i.symbol || "")} · ${esc(dt(i.published_at))} IST</div></div></div>`;
  let body = "";
  if (i.alert) {
    const c = i.calc || {};
    const title = `${i.chg >= 0 ? "Up" : "Down"} ${Math.abs(i.chg ?? 0).toFixed(1)}%${i.mult ? ` on ${i.mult.toFixed(1)}× its usual volume` : ""}`;
    body += `<h2>${esc(title)}</h2>
      <div class="card"><dl class="kv box">
        <div><dt>${c.live ? "Price so far today" : `Close${c.as_of ? `, ${esc(shortDate(c.as_of))}` : ""}`}</dt><dd>${price(c.close)}</dd></div>
        <div><dt>Previous close</dt><dd>${price(c.prev_close)}</dd></div>
        <div><dt>Day change</dt><dd>${change(i.chg)}</dd></div>
        <div><dt>Volume</dt><dd>${crShort(c.volume)} shares</dd></div>
        <div><dt>Average volume, last ${c.lookback || 20} sessions</dt><dd>${c.prev20 == null ? "—" : crShort(Math.round(c.prev20))}</dd></div>
      </dl></div>
      <h3>Why you're seeing this</h3>
      <p class="lede">You asked to hear about any ${settings.price_pct}% daily move or volume above ${settings.vol_mult}× the usual. ${esc(i.why || "")}</p>`;
  } else {
    body += `<h2>${esc(i.title)}</h2>`;
    if (i.resultsBlock) body += `<h3>Headline numbers, ${esc(i.resultsBlock.periods[0])}</h3>${tiles(i.resultsBlock)}
      <p class="caption">₹ crore, ${esc(i.resultsBlock.basis)}. QoQ vs ${esc(i.resultsBlock.periods[1])}, YoY vs ${esc(i.resultsBlock.periods[2])}. EBITDA = PBT + finance costs + depreciation − other income.
        ${i.resultsBlock.fromFiling ? `Read from the <a href="${esc(i.resultsBlock.url)}" target="_blank" rel="noopener">results filing, page ${esc(i.resultsBlock.page)}</a>${i.resultsBlock.check ? (i.resultsBlock.check.ok ? "; matches Screener's quarterly table." : "; differs from Screener, see note.") : "."}` : "Source: Screener's quarterly table (the results PDF hasn't been read yet)."}</p>
        ${i.resultsBlock.notes.length ? `<p class="note">${esc(i.resultsBlock.notes.join(" "))}</p>` : ""}`;
    else if (i.resultsStatus) body += `<p class="note">${esc(i.resultsStatus)}</p>`;
    if (i.summary) body += `<h3>What the filing says</h3><p class="lede">${esc(i.summary.text)} <a class="src-inline" href="${esc(i.summary.url)}" target="_blank" rel="noopener">p.${esc(i.summary.page)}</a></p><p class="caption">One-line summary written from the filed PDF; numbers checked against its text.</p>`;
    if (i.detail) body += `<h3>From the filing</h3><blockquote class="passage">${esc(i.detail)}</blockquote>`;
    if (i.person) body += personFull(i.person);
    if (i.news) body += `<p class="note" style="margin-top:12px">Media report from ${esc(i.publisher)}. FINN shows the headline and links to the article.</p>`;
    if (i.related?.length) body += `<h3>Also reported by</h3><div class="card list">${i.related.map((r) => `<a class="li" href="${esc(r.url)}" target="_blank" rel="noopener"><p class="li-head" style="margin:0;font-size:14px">${esc(r.headline)}</p><div class="li-meta">${SRC.news}<span>${esc(r.publisher)}</span></div></a>`).join("")}</div>`;
  }
  const url = i.source?.url;
  const ev = evRef({ ...i.source });
  body += `<div class="detail-actions">
      ${url ? `<a class="btn primary" href="${esc(url)}" target="_blank" rel="noopener">${i.news ? `Read on ${esc(i.publisher)}` : i.alert ? "Price chart" : "Open filing"} ${I.ext}</a>` : `<button type="button" class="btn" data-ev="${ev}">Source</button>`}
      ${i.symbol ? `<a class="btn" href="#/research?c=${encodeURIComponent(i.symbol)}">Dig in</a><a class="btn" href="#/company/${encodeURIComponent(i.symbol)}/overview">Company</a>` : ""}
      <button type="button" class="btn ghost" data-act="done" data-id="${esc(i.id)}">Clear</button>
      <button type="button" class="btn ghost" data-act="snooze" data-id="${esc(i.id)}">Snooze 1 day</button></div>`;
  if (i.score) body += `<details class="why-rank" style="margin-top:16px"><summary>Why it's ranked here</summary>
      ${i.classification ? `<p class="note">Read as ${esc(CATEGORY_LABEL[i.classification.category] || i.classification.category)} (rule “${esc(i.classification.rule || "none")}”, ${Math.round(i.classification.confidence * 100)}% confidence).</p>` : ""}
      <ul class="reasons">${i.score.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <p class="note">Score ${i.score.total}/100.</p></details>`;
  return `<article class="detail">${asPane ? "" : `<a class="back" href="#/briefing">${I.back}Briefing</a>`}${head}${body}</article>`;
}

function personFull(p) {
  if (!p.name && !p.outgoing) return "";
  const lines = p.lines || [], cov = p.coverage || [];
  const method = { filing: "the company's filing", search: "web search", wikipedia: "Wikipedia", headlines: "news coverage", pending: "" }[String(p.method).replace("+llm", "")] || "";
  let html = `<h3>${p.name ? `Who is ${esc(p.name)}?` : "Leadership change"}</h3><div class="card box person-card">
    <dl class="kv">${p.name ? `<div><dt>Incoming</dt><dd>${esc(p.name)}</dd></div>` : ""}${p.outgoing ? `<div><dt>Outgoing</dt><dd>${esc(p.outgoing)}</dd></div>` : ""}${p.role ? `<div><dt>Role</dt><dd>${esc(p.role)}</dd></div>` : ""}</dl>`;
  if (p.brief) html += `<p class="person-brief">${esc(p.brief)}</p><p class="caption">Written by FINN's language model only from the sources below; numbers in brackets point to them.</p>`;
  const srcs = [...lines, ...cov.slice(0, p.brief ? 4 : 0)];
  if (!p.brief && lines.length) html += `<ul class="bio">${lines.map((l) => `<li>${esc(l.text)} <a href="${esc(l.url || "#")}" target="_blank" rel="noopener" class="src-chip">${esc(l.source)}</a></li>`).join("")}</ul>`;
  if (p.brief && srcs.length) html += `<ol class="bio small">${srcs.map((l) => `<li><a href="${esc(l.url || "#")}" target="_blank" rel="noopener">${esc(l.source)}</a> — ${esc(l.text.slice(0, 140))}${l.text.length > 140 ? "…" : ""}</li>`).join("")}</ol>`;
  if (!p.brief && !lines.length) html += `<p class="note">${p.method === "pending" ? "Background is being gathered; it appears after the next refresh." : "No profile text found yet. Coverage about this person is below."}</p>`;
  if (cov.length && !p.brief) html += `<p class="label" style="margin-top:12px">Coverage</p><ul class="bio">${cov.slice(0, 5).map((l) => `<li><a href="${esc(l.url || "#")}" target="_blank" rel="noopener">${esc(l.text)}</a> <span class="muted">· ${esc(l.source)}</span></li>`).join("")}</ul>`;
  if (method) html += `<p class="caption">Background from ${esc(method)}${String(p.method).includes("+llm") ? ", summarised" : ""}. LinkedIn is not used.</p>`;
  return html + `</div>`;
}

// ---------------------------------------------------------------- About this data (dialog)
export function aboutDataBody({ disclosures, sources }) {
  const st = { ok: "Working", degraded: "Partly working", failed: "Failing", disabled: "Off", fixture: "Demo data" };
  const names = { prices: "Prices (Yahoo Finance)", nse_rss: "NSE announcements", nse_json: "NSE history", bse_rss: "BSE announcements",
    news: "News (Google News, ET, Moneycontrol)", screener: "Fundamentals (Screener)" };
  return `<h2 class="h2" id="dlg-title">About this data</h2>
    ${sources?.length ? `<dl class="kv">${sources.map((x) => `<div><dt>${esc(names[x.name] || x.name)}</dt><dd>${esc(st[x.status] || x.status)}</dd></div>`).join("")}</dl>` : ""}
    <h3 class="label">Notes</h3><ul class="reasons">${(disclosures || []).map((x) => `<li>${esc(x)}</li>`).join("") || "<li>No notes.</li>"}</ul>`;
}

// ---------------------------------------------------------------- Portfolio
// Search finds any stock and opens its page. Changing the lists happens only in Edit, which has two actions:
// Add (a sheet with its own search) and Delete (removes the ticked rows).
const CHECK = `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10.5l3.2 3L15 6.5"/></svg>`;
export function portfolioV3({ holdings, watchlist, tab, editing, editable, live, asOf, query, selected = new Set(), ranks = null, health = undefined }) {
  const list = tab === "watch" ? watchlist : holdings;
  const listName = tab === "watch" ? "watchlist" : "holdings";
  const rowp = (c) => {
    const s = c.signal || {};
    const on = selected.has(c.symbol);
    const right = `<span class="li-right">${ranks ? rankBadge(ranks[c.symbol]) : ""}<span class="px">${s.close != null ? price(s.close) : "—"}</span>${s.close != null ? pctPill(s.pct_change) : `<span class="note">${esc(s.availability === "no_data" ? "No price" : "Loading")}</span>`}</span>`;
    const who = `${avatar(c.symbol, c.name)}<span class="li-co"><span class="nm">${esc(shortName(c.name))}</span><span class="sub">${esc(c.symbol)}${c.sector ? " · " + esc(c.sector) : ""}${s.live ? " · live" : ""}</span></span>`;
    if (editing) return `<button type="button" class="li li-select" data-act="select-stock" data-symbol="${esc(c.symbol)}" aria-pressed="${on}">
      <span class="tick" aria-hidden="true">${on ? CHECK : ""}</span>${who}${right}</button>`;
    return `<a class="li" style="display:flex;align-items:center;gap:12px" href="#/company/${encodeURIComponent(c.symbol)}/overview">${who}${right}</a>`;
  };
  const n = [...selected].filter((sym) => list.some((c) => c.symbol === sym)).length;
  return `<section class="hero"><h1>Portfolio</h1>
    <p class="sum">${holdings.length} holdings · ${watchlist.length} on your watchlist${asOf ? ` · prices at ${esc(shortDate(asOf))}` : ""}</p></section>
    ${live ? `<div class="searchbox">${SRC.search}<label class="sr" for="stock-search">Search NSE or BSE stocks</label>
      <input id="stock-search" type="search" autocomplete="off" placeholder="Search any NSE or BSE stock" value="${esc(query || "")}"></div>
      <div id="search-results"></div>` : ""}
    <div class="toolbar"><div class="seg" role="group" aria-label="List">
      <button type="button" class="seg-b" data-ptab="hold" aria-pressed="${tab !== "watch"}">Holdings</button>
      <button type="button" class="seg-b" data-ptab="watch" aria-pressed="${tab === "watch"}">Watchlist</button></div>
      ${editable ? `<button type="button" class="btn ghost" data-act="edit-portfolio" aria-pressed="${editing}">${editing ? "Done" : "Edit"}</button>` : ""}</div>
    ${editing ? `<div class="editbar" role="group" aria-label="Edit ${listName}">
      <button type="button" class="btn primary" data-act="open-add">${SRC.plus}Add</button>
      <button type="button" class="btn danger" data-act="delete-selected" ${n ? "" : "disabled"}>${SRC.trash}Delete${n ? ` ${n}` : ""}</button>
      <span class="note">${n ? `${n} selected` : "Tick stocks to delete"}</span></div>` : ""}
    ${live && tab !== "watch" && !editing ? healthCard(health) : ""}
    <div class="card list">${list.map(rowp).join("") || `<div class="empty-card">No stocks here yet.${editable ? " Tap Edit, then Add." : ""}</div>`}</div>
    ${ranks ? `<p class="caption">The number by each price is FINN Rank (1–10) vs the stocks FINN tracks. ${esc(CAVEAT)}</p>${rankFormula(Object.keys(ranks).length)}` : ""}
    ${!editable && !live ? `<p class="note">Run FINN's backend to change your lists; this view shows the demo list.</p>` : ""}
`;
}

// Search results. mode "view": open the company page. mode "add": one Add button into the list being edited.
export function searchResults(results, note, have, mode = "view", role = "holding") {
  if (!results) return "";
  const who = (r) => `${avatar(r.symbol, r.name)}<span class="li-co"><span class="nm">${esc(r.name)}</span><span class="sub">${esc(r.symbol)} · ${esc(r.exchange || "NSE")}${r.sector ? " · " + esc(r.sector) : ""}</span></span>`;
  const rows = results.map((r) => mode === "view"
    ? `<a class="li" style="display:flex;align-items:center;gap:12px" href="#/company/${encodeURIComponent(r.symbol)}/overview">${who(r)}${have.has(r.symbol) ? `<span class="tag">In your list</span>` : `<span class="chev-r" aria-hidden="true"></span>`}</a>`
    : `<div class="li" style="display:flex;align-items:center;gap:12px">${who(r)}<span class="add">${have.has(r.symbol) ? `<span class="note">Added</span>`
      : `<button type="button" class="btn primary" data-add="${esc(r.symbol)}" data-name="${esc(r.name)}" data-sector="${esc(r.sector || "")}" data-role="${role}">Add</button>`}</span></div>`).join("");
  return `<div class="card list results-pop">${rows || `<div class="empty-card">No NSE or BSE stock matches.</div>`}</div>${note ? `<p class="note">${esc(note)}</p>` : ""}`;
}

export function addSheet(role, query) {
  return `<h2 style="margin-top:0">Add to your ${role === "research" ? "watchlist" : "holdings"}</h2>
    <div class="searchbox">${SRC.search}<label class="sr" for="add-search">Stock name or symbol</label>
      <input id="add-search" type="search" autocomplete="off" placeholder="Name or NSE symbol" value="${esc(query || "")}" autofocus></div>
    <div id="add-results"><p class="note">Type at least two letters.</p></div>
    <div style="display:flex;justify-content:flex-end;margin-top:12px"><button type="button" class="btn" data-act="close-dlg">Close</button></div>`;
}

// ---------------------------------------------------------------- live company page
const TABS = [["overview", "Overview"], ["financials", "Financials"], ["news", "News"], ["filings", "Filings"], ["documents", "Documents"]];

function tableCard(t, keys, title, unit = "₹ crore", last = 5) {
  if (!t) return "";
  const idx = t.periods.map((p, i) => i).slice(-last);
  const rows = keys.map((k) => [k, t.rows[k]]).filter(([, v]) => v);
  if (!rows.length) return "";
  return `<div class="card"><div class="scroll"><table class="tbl wide"><thead><tr><th scope="col">${esc(title)} <span class="muted">(${esc(unit)})</span></th>
    ${idx.map((i) => `<th scope="col" class="n">${esc(t.periods[i])}</th>`).join("")}</tr></thead><tbody>
    ${rows.map(([k, v]) => `<tr><th scope="row">${esc(t.labels?.[k] || k)}</th>${idx.map((i) => `<td class="n">${v[i] == null ? "—" : crShort(Math.round(v[i]))}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div></div>`;
}

export function companyV3(c, tab, sig = {}) {
  const s = c.signal || {}, snap = c.snapshot;
  const hist = c.history || [];
  const spark = hist.length > 2 ? chartRef("spark", { values: hist.map((h) => h.close), labels: hist.map((h) => shortDate(h.date)), label: `${c.name} closing price, last ${hist.length} sessions` }) : null;
  const nav = TABS.map(([id, l]) => `<a href="#/company/${encodeURIComponent(c.symbol)}/${id}" ${id === tab ? 'aria-current="page"' : ""}>${l}</a>`).join("");
  let body = "";
  if (tab === "overview") {
    body += signalCard(c, sig);
    body += c.results ? `<div class="card" style="padding:16px"><div class="sec-head" style="margin:0"><b>Latest results · ${esc(c.results.periods[0])}</b><span class="sec-sub">${esc(c.results.basis)}</span></div>${tiles(adaptRes(c.results))}</div>` : "";
    body += snap?.ratios?.length ? `<div class="card"><dl class="stats">${snap.ratios.filter(([k]) => !/current price/i.test(k)).slice(0, 8).map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl></div>` : "";
    body += snap?.about ? `<div class="card about">${esc(snap.about)}</div>` : "";
    body += c.news?.length ? `<div class="sec-head" style="margin-top:16px"><b>In the news</b><a class="more" href="#/company/${encodeURIComponent(c.symbol)}/news">All</a></div><div class="card list">${c.news.slice(0, 3).map(newsRow).join("")}</div>` : "";
  } else if (tab === "financials") {
    const q = snap?.quarters;
    if (q) {
      const per = q.periods.filter((p) => p !== "TTM");
      const rev = q.rows.sales || q.rows.revenue;
      const n = Math.min(8, per.length);
      const P = per.slice(-n), R = rev ? rev.slice(per.length - n, per.length) : [];
      const pbt = q.rows["profit before tax"], it = q.rows.interest, dp = q.rows.depreciation, oi = q.rows["other income"];
      const margin = rev && pbt && it && dp && oi && !c.results?.is_lender
        ? P.map((_, j) => { const i = per.length - n + j; const e = pbt[i] + it[i] + dp[i] - oi[i]; return rev[i] ? (e / rev[i]) * 100 : null; }) : null;
      if (R.length && R.every((v) => v != null)) body += `<div class="card"><figure class="fig"><figcaption><b>Quarterly revenue</b><span>₹ crore · ${esc(P[0])} to ${esc(P.at(-1))}</span></figcaption><div class="chart" data-chart="${chartRef("bar", { labels: P, values: R, label: "Quarterly revenue, ₹ crore" })}"></div></figure></div>`;
      if (margin && margin.every((v) => v != null)) body += `<div class="card"><figure class="fig"><figcaption><b>EBITDA margin</b><span>% of revenue · axis doesn't start at zero</span></figcaption><div class="chart" data-chart="${chartRef("line", { labels: P, values: margin, label: "EBITDA margin, %" })}"></div></figure></div>`;
      body += tableCard(q, ["sales", "revenue", "operating profit", "financing profit", "profit before tax", "net profit"], "Quarterly");
    }
    body += tableCard(snap?.annual, ["sales", "revenue", "operating profit", "net profit"], "Annual", "₹ crore", 6);
    const cf = snap?.cashflow, an = snap?.annual;
    if (cf && an && cf.rows["cash from operating activity"] && an.rows["net profit"]) {
      const yrs = cf.periods.filter((p) => an.periods.includes(p)).slice(-5);
      const ocf = yrs.map((y) => cf.rows["cash from operating activity"][cf.periods.indexOf(y)]);
      const pat = yrs.map((y) => an.rows["net profit"][an.periods.indexOf(y)]);
      if (yrs.length > 1 && [...ocf, ...pat].every((v) => v != null)) body += `<div class="card"><figure class="fig"><figcaption><b>Cash from operations vs profit</b><span>₹ crore · same unit, one scale</span></figcaption>
        <ul class="legend"><li><i class="sw s1"></i>Operating cash flow</li><li><i class="sw s2"></i>Net profit</li></ul>
        <div class="chart" data-chart="${chartRef("grouped", { labels: yrs, a: ocf, b: pat, names: ["Operating cash flow", "Net profit"], label: "Operating cash flow and net profit, ₹ crore" })}"></div></figure></div>`;
    }
    body += tableCard(snap?.balance, ["equity capital", "reserves", "borrowings", "total liabilities"], "Balance sheet", "₹ crore", 5);
    body += tableCard(snap?.efficiency, ["debtor days", "inventory days", "days payable", "cash conversion cycle", "working capital days", "roce %"], "Efficiency", "days / %", 5);
    if (!snap) body += `<div class="card empty-card">${esc(c.status?.[0] || "Fundamentals not available yet.")}</div>`;
    else body += `<p class="caption">Source: <a href="${esc(snap.source_url)}" target="_blank" rel="noopener">Screener</a> (${esc(snap.basis)}), fetched ${esc(shortDate(snap.retrieved_at))}. Figures as published there.</p>`;
  } else if (tab === "news") {
    body += c.news?.length ? `<div class="card list">${c.news.map(newsRow).join("")}</div>` : `<div class="card empty-card">No headlines from trusted outlets in the last few days.</div>`;
  } else if (tab === "filings") {
    body += c.filings?.length ? `<div class="card list">${c.filings.map((f) => `<a class="li" href="${esc(f.url || "#")}" target="_blank" rel="noopener">
      <div class="li-meta" style="margin:0">${SRC.filing}<span>${esc(dt(f.filed_at))}</span><span>·</span><span>${esc(CATEGORY_LABEL[f.category] || f.category)}</span></div>
      <p class="li-head" style="margin-top:6px">${esc(f.subject)}</p>${f.detail ? `<p class="note" style="margin:4px 0 0">${esc(f.detail.slice(0, 180))}</p>` : ""}</a>`).join("")}</div>`
      : `<div class="card empty-card">No exchange filings seen yet. FINN records NSE filings while it runs.</div>`;
  } else if (tab === "documents") {
    const cc = snap?.concalls || [], ar = snap?.annual_reports || [], cr = snap?.credit_ratings || [];
    body += cc.length ? `<div class="sec-head"><b>Earnings calls</b></div><div class="card list">${cc.slice(0, 8).map((x) => `<div class="li doc-row"><span>${esc(x.period)}</span><span class="doc-links">
      ${x.transcript ? `<a class="chip-tag" href="${esc(x.transcript)}" target="_blank" rel="noopener">Transcript</a>` : ""}${x.ppt ? `<a class="chip-tag" href="${esc(x.ppt)}" target="_blank" rel="noopener">Slides</a>` : ""}${x.recording ? `<a class="chip-tag" href="${esc(x.recording)}" target="_blank" rel="noopener">Recording</a>` : ""}</span></div>`).join("")}</div>` : "";
    body += ar.length ? `<div class="sec-head" style="margin-top:16px"><b>Annual reports</b></div><div class="card list">${ar.slice(0, 6).map((x) => `<a class="li doc-row" href="${esc(x.url)}" target="_blank" rel="noopener"><span>${esc(x.title)}</span><span class="note" style="margin:0">${esc(x.note || "")}</span></a>`).join("")}</div>` : "";
    body += cr.length ? `<div class="sec-head" style="margin-top:16px"><b>Credit ratings</b></div><div class="card list">${cr.slice(0, 6).map((x) => `<a class="li doc-row" href="${esc(x.url)}" target="_blank" rel="noopener"><span>${esc(x.title)}</span><span class="note" style="margin:0">${esc(x.note || "")}</span></a>`).join("")}</div>` : "";
    if (!cc.length && !ar.length && !cr.length) body += `<div class="card empty-card">${esc(snap ? "Screener lists no documents for this company." : (c.status?.[0] || "Documents not available yet."))}</div>`;
    else body += `<p class="caption">Links as listed on Screener; documents open on the exchange or company site. Research reads the latest of these.</p>`;
  }
  return `<a class="back" href="#/portfolio">${I.back}Portfolio</a>
    <section class="co-hero"><div class="row1">${avatar(c.symbol, c.name, true)}<div><h1>${esc(shortName(c.name))}</h1>
      <div class="sub">${esc(c.exchange)}: ${esc(c.symbol)}${c.sector ? " · " + esc(c.sector) : ""}${c.role === "research" ? " · Watchlist" : c.role === "holding" ? " · Holding" : ""}</div></div></div>
      <div class="quote"><span class="big">${s.close != null ? price(s.close) : "—"}</span>${s.close != null ? pctPill(s.pct_change) : ""}</div>
      <div class="asof">${s.live ? `Live · as of ${esc(clock(s.live_at))} IST · Yahoo Finance` : s.as_of ? `Close ${esc(shortDate(s.as_of))} · Yahoo Finance` : esc(s.notes?.[0] || "No price yet")}</div>
      ${spark ? `<div class="chart spark" data-chart="${spark}"></div>` : ""}
      <a class="btn primary dig" href="#/research?c=${encodeURIComponent(c.symbol)}">Research ${esc(shortName(c.name))}</a></section>
    <nav class="tabs" aria-label="Company sections">${nav}</nav>
    <div class="sec">${body}</div>`;
}

function newsRow(n) {
  return `<a class="li" href="${esc(n.url)}" target="_blank" rel="noopener"><p class="li-head" style="margin:0">${esc(n.headline)}</p>
    <div class="li-meta">${SRC.news}<span>${esc(n.publisher)}</span><span>·</span><span>${esc(timeAgo(n.published_at))}</span></div></a>`;
}

export function adaptRes(r) {
  return { periods: r.periods, basis: r.basis, rows: r.rows.map((x) => ({ metric: x.metric, value: x.latest, qoq: x.qoq, yoy: x.yoy })) };
}

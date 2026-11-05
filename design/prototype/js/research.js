// Research (Pull) views: a dossier built from the company's own documents and reported numbers, plus Ask.
// Every sentence carries numbered sources; tapping one opens the passage (document, page) or the figure and formula.
import { esc, crShort, shortName, avatar } from "./format.js";
import { evRef, chartRef, icons as I } from "./views.js";

const SEARCH = `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5"/><path d="M13 13l4 4"/></svg>`;
const MIC = `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><rect x="7.5" y="2.5" width="5" height="9" rx="2.5"/><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5"/></svg>`;
const SEND = `<svg class="ic" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 10h12M11 5.5l4.5 4.5-4.5 4.5"/></svg>`;
const REFRESH = `<svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M16 10a6 6 0 1 1-1.8-4.3M16 3.5V6.5h-3"/></svg>`;

export const VERDICT = { beat: "Beat", delivered: "Delivered", on_track: "On track", behind: "Behind so far", missed: "Missed", too_early: "Too early", unchecked: "Not checkable" };
const VTONE = { beat: "up", delivered: "up", on_track: "acc", behind: "down", missed: "down", too_early: "neu", unchecked: "neu" };
const STEP_ICON = { done: "✓", running: "", failed: "!", skipped: "–", pending: "" };
export const SUGGESTED = ["What did management guide for this year?", "What risks did management name on the last call?",
  "What drove margins in the latest quarter?", "How is working capital moving?"];

const fmtV = (v, unit) => {
  if (v == null) return "n/a";
  if (unit === "₹ cr") return `₹${crShort(Math.round(v))} cr`;
  if (unit === "%") return `${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(2)}×`;
  if (unit === "days") return `${Math.round(v)} days`;
  return String(v);
};

// ---------- evidence objects for the shared evidence sheet ----------
function evFor(id, src) {
  if (!src) return null;
  if (src.kind === "doc") return { source_class: "PRIMARY_DOC", source_name: src.title, locator: `Page ${src.page}`,
    passage: src.text, url: src.url, note: "Opens the company's document at this page." };
  return { source_class: "STANDARDIZED_TABLE", source_name: src.title,
    locator: [src.period, src.locator].filter(Boolean).join(" · "),
    passage: `${fmtV(src.value, src.unit)}${src.formula ? `. Formula: ${src.formula}` : ""}. ${src.source || ""}`.trim(),
    url: src.url, note: "Opens the company's page on Screener, where the reported table is." };
}
function cites(ids, sources, counter) {
  return ids.map((id) => {
    if (!counter.map.has(id)) counter.map.set(id, ++counter.k);
    const n = counter.map.get(id);
    const e = evFor(id, sources[id]);
    return e ? `<button type="button" class="cite" data-ev="${evRef(e)}" aria-label="Source ${n}: ${esc(e.source_name)}">${n}</button>` : "";
  }).join("");
}
const newCounter = () => ({ k: 0, map: new Map() });

function claimList(claims, sources, counter) {
  if (!claims?.length) return "";
  return `<ul class="claims">${claims.map((c) => `<li>${esc(c.text)}${cites(c.cites, sources, counter)}</li>`).join("")}</ul>`;
}
function gapsLine(gaps) {
  return gaps?.length ? `<p class="gaps"><b>Not in the documents:</b> ${esc(gaps.join(" "))}</p>` : "";
}

// ---------- picker ----------
export function researchPicker({ query, results, mine, llm }) {
  return `<section class="hero"><h1>Research</h1>
    <p class="sum">Any NSE company, from its own reports and calls. Every sentence cited.</p></section>
    <div class="searchbox">${SEARCH}<label class="sr" for="research-search">Company name or NSE symbol</label>
      <input id="research-search" type="search" autocomplete="off" placeholder="Any NSE company — name or symbol" value="${esc(query || "")}"></div>
    <div id="research-results">${results || ""}</div>
    ${mine.length ? `<div class="sec-head"><b>Your companies</b></div><div class="pick-grid">${mine.map((c) => `<a class="pick" href="#/research?c=${encodeURIComponent(c.symbol)}">${avatar(c.symbol, c.name)}<span class="nm">${esc(shortName(c.name))}</span><span class="sub">${esc(c.symbol)}</span></a>`).join("")}</div>` : ""}
    ${llm ? "" : `<p class="note">Written sections and Ask need a free Groq or OpenRouter key in <code>.env</code>; numbers and the document list work without one.</p>`}`;
}

export function researchResults(results, note) {
  if (!results) return "";
  return `<div class="card list results-pop">${results.map((r) => `<a class="li" style="display:flex;align-items:center;gap:12px" href="#/research?c=${encodeURIComponent(r.symbol)}">${avatar(r.symbol, r.name)}<span class="li-co"><span class="nm">${esc(r.name)}</span><span class="sub">${esc(r.symbol)} · ${esc(r.exchange || "NSE")}</span></span><span class="chev-r" aria-hidden="true"></span></a>`).join("") || `<div class="empty-card">No NSE company matches.</div>`}</div>${note ? `<p class="note">${esc(note)}</p>` : ""}`;
}

// ---------- dossier ----------
// One list drives both the tab bar and the panel heading, so what you tap is exactly what you see.
export const RTABS = [["summary", "Summary"], ["business", "Business"], ["promises", "Promises"], ["drivers", "Drivers"],
  ["numbers", "Numbers"], ["cash", "Cash & debt"], ["case", "Bull & bear"], ["ask", "Ask"], ["sources", "Sources"]];

export function researchDossier({ sym, d, tab = "summary", notes, asking, speechIn, listening }) {
  const name = d?.name || sym;
  const running = d?.status === "running";
  const head = `<section class="r-head">${avatar(sym, name, true)}<div class="r-id"><h1>${esc(shortName(name))}</h1>
      <p class="sub">${esc(sym)}${d?.sector ? ` · ${esc(d.sector)}` : ""}</p></div>
      <div class="r-act"><a class="btn ghost" href="#/research">Change</a>
      ${d && !running && d.status !== "idle" ? `<button type="button" class="btn ghost" data-act="r-rebuild" aria-label="Rebuild from the documents">${REFRESH}</button>` : ""}</div></section>`;
  if (!d || d.status === "idle") return head + `<div class="card empty-card" role="status">Starting…</div>`;
  if (d.status === "failed" && !d.numbers?.length) {
    return head + `<div class="card empty-card"><p>Couldn't build research for ${esc(sym)}.</p>
      <p class="note">${esc(stepNote(d, "fundamentals") || "Check the symbol, or try again in a minute.")}</p>
      <button type="button" class="btn" data-act="r-rebuild">Try again</button></div>`;
  }
  if (!RTABS.some(([id]) => id === tab)) tab = "summary";
  const counter = newCounter();
  const S = d.sections || {};
  const tabs = `<div class="tabwrap"><nav class="r-nav tabbar" aria-label="Research sections">${RTABS.filter(([id]) => id !== "ask").map(([id, l]) =>
    `<button type="button" class="chip" data-rtab="${id}" aria-pressed="${id === tab}">${l}</button>`).join("")}</nav><button type="button" class="tab-more" aria-label="More tabs" tabindex="-1"><svg class="ic sm" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 5l5 5-5 5"/></svg></button></div>`;
  const label = RTABS.find(([id]) => id === tab)[1];
  let body = "";
  switch (tab) {
    case "summary": body = summaryPanel(d, counter, running) + (notes.length ? "" : `<h3 class="r-h3">Ask</h3>
      <div class="chips sugg">${SUGGESTED.map((q) => `<button type="button" class="chip" data-rq="${esc(q)}">${esc(q)}</button>`).join("")}</div>`); break;
    case "business": body = S.business ? claimList(S.business.claims, S.business.sources, counter) + gapsLine(S.business.gaps) + llmMsg(S.business, "business") : pendingOr(d, "business"); break;
    case "promises": body = ledger(d, counter); break;
    case "drivers": body = S.narrative ? claimList(S.narrative.claims, S.narrative.sources, counter) + gapsLine(S.narrative.gaps) + llmMsg(S.narrative, "narrative") : pendingOr(d, "narrative"); break;
    case "numbers": body = numbersBody(d, ["financial", "trajectory"], counter); break;
    case "cash": body = numbersBody(d, ["balance", "cash"], counter); break;
    case "case": body = bullBear(S.bull_bear || S.case, counter) || pendingOr(d, "bull_bear"); break;
    case "ask": body = askThread({ name, notes }); break;
    case "sources": body = docsList(d); break;
  }
  const back = tab === "ask" ? `<button type="button" class="r-back" data-rtab="summary">← Back to the report</button>` : "";
  const convo = tab !== "ask" && notes.length ? `<button type="button" class="convo-link" data-rtab="ask">Your questions (${notes.length}) →</button>` : "";
  return head + tabs + `<section class="r-panel" aria-label="${esc(label)}">${back}<h2 class="r-title">${esc(tab === "ask" ? "Your questions" : label)}</h2>${body}</section>`
    + convo + askBar({ name, notes, asking, speechIn, listening });
}

function summaryPanel(d, counter, running) {
  let h = "";
  if (running || d.steps?.some((s) => s.status === "failed")) h += progress(d);
  h += glance(d, counter);
  const obs = (d.numbers || []).map((sec) => {
    const src = Object.fromEntries(sec.facts.map((f) => [f.id, factSrc(f)]));
    return sec.observations[0] ? `<li class="t-${sec.observations[0].tone}">${esc(sec.observations[0].text)}${cites(sec.observations[0].facts, src, counter)}</li>` : "";
  }).join("");
  if (obs) h += `<h3 class="r-h3">Key points</h3><ul class="obs">${obs}</ul>`;
  const sc = d.sections?.ledger?.score;
  if (sc?.total) h += `<button type="button" class="r-link" data-rtab="promises">Management kept ${sc.kept} of ${sc.checked} checkable promises · see all ${sc.total} →</button>`;
  return h || pendingOr(d, "numbers");
}

function stepNote(d, id) { return d.steps?.find((s) => s.id === id)?.note; }
function pendingOr(d, id) {
  const s = d.steps?.find((x) => x.id === id);
  if (!s) return "";
  if (s.status === "skipped") return `<p class="note">${esc(s.note || "Skipped.")}</p>`;
  if (s.status === "failed") return `<p class="note">This step failed. Use Rebuild to try again.</p>`;
  return `<div class="skeleton" aria-hidden="true"><span></span><span></span><span></span></div><p class="note" role="status">${s.status === "running" ? "Working on it…" : "Waiting for earlier steps…"}</p>`;
}
function llmMsg(sec, id) { return sec?.message ? `<div class="retry"><p>This part couldn't be written just now: the free AI limit was reached.</p><button type="button" class="btn" data-act="r-retry" data-sec="${esc(id)}">Try again</button></div>` : sec?.dropped ? `<p class="caption">${sec.dropped} draft sentence${sec.dropped > 1 ? "s" : ""} removed: a number or citation couldn't be found in the source.</p>` : ""; }

function progress(d) {
  return `<div class="card r-progress" role="status" aria-live="polite"><ol>${d.steps.map((s) => `<li class="st-${s.status}"><span class="dot" aria-hidden="true">${STEP_ICON[s.status] || ""}</span><span>${esc(s.label)}${s.note ? ` <span class="muted">· ${esc(s.note)}</span>` : ""}</span></li>`).join("")}</ol>
</div>`;
}


function fact(d, id) { return d.facts?.[id]; }
function findFact(d, label) { return Object.values(d.facts || {}).find((f) => f.label === label || f.label.startsWith(label)); }
function factSrc(f) { return { kind: "fact", title: f.label, period: f.period, value: f.value, unit: f.unit, formula: f.formula, url: f.url, source: f.source, locator: f.locator }; }

function glance(d, counter) {
  const sc = d.sections?.ledger?.score;
  const tiles = [];
  if (sc && sc.total) tiles.push({ k: "Promises kept", v: sc.checked ? `${sc.kept} of ${sc.checked}` : "—", s: sc.checked ? `${sc.pending} still open` : `${sc.total} found, none due yet` });
  const g = findFact(d, "Revenue growth, 3-year CAGR"), cq = findFact(d, "Cash ÷ profit,"), de = findFact(d, "Debt-to-equity"), om = findFact(d, "Operating margin");
  const t = (f, k) => f && f.value != null && tiles.push({ k, v: fmtV(f.value, f.unit), s: f.period, f });
  t(g, "Revenue growth, 3 yrs"); t(om, "Operating margin"); if (!d.lender) { t(cq, "Cash ÷ profit"); t(de, "Debt ÷ equity"); }
  if (!tiles.length) return "";
  return `<section id="r-glance" class="r-sec"><div class="glance">${tiles.slice(0, 4).map((x) => `<div class="g-tile"><span class="k">${esc(x.k)}</span><span class="v">${esc(x.v)}${x.f ? cites([x.f.id], { [x.f.id]: factSrc(x.f) }, counter) : ""}</span><span class="s">${esc(x.s || "")}</span></div>`).join("")}</div></section>`;
}

function ledger(d, counter) {
  const L = d.sections?.ledger;
  const g = d.steps?.find((s) => s.id === "guidance");
  if (!L || !L.rows?.length) return g && ["running", "pending"].includes(g.status) ? pendingOr(d, "guidance") : `<p class="note">${esc(g?.note || "No explicit guidance was found in the calls FINN read.")}</p>`;
  const rows = [...L.rows].sort((a, b) => order(a.verdict) - order(b.verdict));
  return `<p class="ledger-score">${L.score.checked ? `Kept <b>${L.score.kept} of ${L.score.checked}</b> promises that can be checked so far` : "No promise is due yet"}${L.score.pending ? ` · ${L.score.pending} still running` : ""}${L.score.unchecked ? ` · ${L.score.unchecked} not checkable from the P&L` : ""}.</p>
    <div class="ledger">${rows.map((r) => {
      const src = { [r.cite.id || r.cite.doc_id]: { kind: "doc", title: r.cite.title, page: r.cite.page, url: r.cite.url, text: r.quote } };
      const target = r.low == null && r.high == null ? "No number" : `${r.low === r.high || r.high == null ? r.low : `${r.low}–${r.high}`}${r.unit && r.unit.trim() !== "%" ? " " + esc(r.unit) : "%"}`;
      return `<article class="lr">
        <div class="lr-top"><span class="said">${esc(r.said_in)}</span><span class="verdict ${VTONE[r.verdict]}">${esc(VERDICT[r.verdict] || r.verdict)}</span></div>
        <p class="lr-st">${esc(r.statement || r.quote)}</p>
        <dl class="lr-kv"><div><dt>Guided</dt><dd>${esc(target)}${r.horizon ? ` · ${esc(r.horizon)}` : ""}</dd></div>
          <div><dt>${r.actual != null ? (["on_track", "behind"].includes(r.verdict) ? "So far" : "Actual") : "Actual"}</dt><dd>${r.actual != null ? `${r.actual.toFixed(1)}%` : "—"}${r.quarters?.length ? ` <span class="muted">(${esc(r.quarters.join(", "))})</span>` : ""}</dd></div></dl>
        <details><summary>Management's words${cites([r.cite.id || r.cite.doc_id], src, counter)}</summary><blockquote class="passage">${esc(r.quote)}</blockquote>${r.method ? `<p class="caption">${esc(r.method)}</p>` : ""}</details>
      </article>`;
    }).join("")}</div>`;
}
const order = (v) => ["missed", "behind", "beat", "delivered", "on_track", "too_early", "unchecked"].indexOf(v);

function numbersBody(d, ids, counter) {
  const secs = (d.numbers || []).filter((s) => ids.includes(s.id));
  if (!secs.length) return pendingOr(d, "numbers");
  const body = secs.map((s) => {
    const src = Object.fromEntries(s.facts.map((f) => [f.id, factSrc(f)]));
    let h = `<h3 class="r-h3">${esc(s.title)}</h3>`;
    if (s.observations.length) h += `<ul class="obs">${s.observations.map((o) => `<li class="t-${o.tone}">${esc(o.text)}${cites(o.facts, src, counter)}</li>`).join("")}</ul>`;
    const show = s.facts.filter((f) => f.value != null && !/three years earlier|, start$/.test(f.label)).slice(0, 8);
    if (show.length) h += `<dl class="stats">${show.map((f) => `<div><dt>${esc(f.label)}</dt><dd>${esc(fmtV(f.value, f.unit))}${cites([f.id], src, counter)}</dd><dd class="per">${esc(f.period)}</dd></div>`).join("")}</dl>`;
    for (const se of s.series) {
      if (!se.values.length || se.values.every((v) => v == null)) continue;
      if (se.label === "Net profit" && s.id === "cash") continue;
      const vals = se.values.map((v) => v ?? 0);
      if (s.id === "cash" && se.label === "Cash from operations") {
        const pat = s.series.find((x) => x.label === "Net profit");
        h += `<figure class="fig"><figcaption><b>Operating cash vs profit</b><span>₹ crore</span></figcaption><div class="chart" data-chart="${chartRef("grouped", { labels: se.periods, a: vals, b: (pat?.values || []).map((v) => v ?? 0), names: ["Operating cash", "Net profit"], label: "Operating cash flow and net profit, ₹ crore" })}"></div></figure>`;
      } else if (se.unit === "₹ cr") {
        h += `<figure class="fig"><figcaption><b>${esc(se.label)}</b><span>₹ crore · ${esc(se.periods[0])}–${esc(se.periods.at(-1))}</span></figcaption><div class="chart" data-chart="${chartRef("bar", { labels: se.periods, values: vals, label: `${se.label}, ₹ crore` })}"></div></figure>`;
      } else if (se.unit === "%") {
        h += `<figure class="fig"><figcaption><b>${esc(se.label)}</b><span>% · axis doesn't start at zero</span></figcaption><div class="chart" data-chart="${chartRef("line", { labels: se.periods, values: vals, label: `${se.label}, %` })}"></div></figure>`;
      }
    }
    if (s.table) h += `<div class="scroll"><table class="tbl wide"><thead><tr><th scope="col"><span class="muted">${esc(s.table.unit)}</span></th>${s.table.head.map((x) => `<th class="n" scope="col">${esc(x)}</th>`).join("")}</tr></thead><tbody>${s.table.rows.map((r) => `<tr><th scope="row">${esc(r[0])}</th>${r.slice(1).map((v) => `<td class="n">${v == null ? "—" : Math.abs(v) < 20 && !Number.isInteger(v) ? v.toFixed(2) : crShort(Math.round(v))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    if (s.notes.length) h += `<p class="note">${esc(s.notes.join(" "))}</p>`;
    return h;
  }).join("");
  return body + `<p class="caption">From reported tables. Tap a number for its formula.</p>`;
}

function bullBear(bb, counter) {
  if (!bb) return "";
  if (bb.message) return llmMsg(bb, "bull_bear");
  const col = (t, items, cls) => `<div class="bb ${cls}"><h3 class="r-h3">${t}</h3>${items.length ? `<ul class="claims">${items.map((c) => `<li>${esc(c.text)}${cites(c.cites, bb.sources || {}, counter)}</li>`).join("")}</ul>` : `<p class="note">No point survived source checks.</p>`}</div>`;
  return `<div class="bb-grid">${col("Bull case", bb.bull, "bull")}${col("Bear case", bb.bear, "bear")}</div>${bb.dropped ? `<p class="caption">${bb.dropped} draft point${bb.dropped > 1 ? "s" : ""} removed for missing or mismatched sources.</p>` : ""}`;
}

function docsList(d) {
  const docs = d.documents || [];
  if (!docs.length) return pendingOr(d, "documents");
  const kind = { transcript: "Call transcript", presentation: "Investor presentation", annual_report: "Annual report" };
  return `<ul class="docs">${docs.map((x) => `<li><span class="dk">${esc(kind[x.kind] || x.kind)}</span><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)} ${I.ext}</a>
      <span class="muted">${x.status === "ok" ? `${x.pages_read}${x.pages > x.pages_read ? ` of ${x.pages}` : ""} page${(x.pages > x.pages_read ? x.pages : x.pages_read) === 1 ? "" : "s"} read · ${esc(x.host)}` : x.status === "failed" ? `Couldn't read: ${esc(x.error || "")}` : "Waiting"}</span></li>`).join("")}</ul>
    ${d.fundamentals_url ? `<p class="caption">Numbers: <a href="${esc(d.fundamentals_url)}" target="_blank" rel="noopener">Screener standardised tables</a>, used for figures only.</p>` : ""}
    ${d.usage ? `<p class="caption">Models: ${esc(Object.keys(d.usage.by_model || {}).join(", ") || "none")} · ${d.usage.ok} calls · ~${crShort(d.usage.tokens)} tokens (free tier).</p>` : ""}`;
}

// ---------- ask: a conversation in its own tab; the ask bar stays at the bottom of every tab ----------
function askThread({ name, notes }) {
  const last = notes.length - 1;
  if (!notes.length) return `<p class="r-lead">Ask anything about ${esc(shortName(name))}. Answers use only its own documents.</p>
    <div class="chips sugg">${SUGGESTED.map((q) => `<button type="button" class="chip" data-rq="${esc(q)}">${esc(q)}</button>`).join("")}</div>`;
  return `<div class="thread" aria-live="polite">${notes.map((n, idx) => {
    const counter = newCounter();
    let body;
    if (n.pending) body = `<div class="skeleton" aria-hidden="true"><span></span><span></span></div>`;
    else if (n.status === "ok") body = `${claimList(n.claims, n.sources, counter)}${gapsLine(n.gaps)}`;
    else body = `<p class="a-msg">${esc(n.message || "No answer.")}</p>`;
    const chips = idx === last && !n.pending && n.follow_ups?.length
      ? `<div class="chips follow">${n.follow_ups.map((q) => `<button type="button" class="chip" data-rq="${esc(q)}">${esc(q)}</button>`).join("")}</div>` : "";
    return `<div class="turn" id="${esc(n.id)}"><p class="q-bubble"><span class="sr">You asked: </span>${esc(n.question)}</p>
      <div class="a-body">${body}</div>${chips}</div>`;
  }).join("")}</div><button type="button" class="link" data-act="r-clear">Clear conversation</button>`;
}

function askBar({ name, notes, asking, speechIn, listening }) {
  return `<form class="askbar${listening ? " listening" : ""}" data-form="rask" role="search">
      <label class="sr" for="rask-q">Ask a question about ${esc(name)}</label>
      <input id="rask-q" name="q" autocomplete="off" maxlength="300" placeholder="${listening ? "Listening… speak now" : notes.length ? "Ask a follow-up…" : `Ask about ${esc(shortName(name))}…`}">
      ${speechIn ? `<button type="button" class="icon-btn" data-act="mic" aria-pressed="${!!listening}" aria-label="${listening ? "Stop listening" : "Speak your question"}">${MIC}</button>` : ""}
      <button type="submit" class="icon-btn primary" aria-label="Send" ${asking ? 'disabled aria-busy="true"' : ""}>${SEND}</button>
    </form>`;
}

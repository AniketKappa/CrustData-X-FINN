// Decision-support views: FINN Signal card (rank, grades, flags, why it moved, Ask FINN), portfolio health and
// the morning briefing card. Everything shown comes from the API; nothing here computes a number.
import { esc } from "./format.js";

export const CAVEAT = "Experimental ranking — not investment advice.";
const GROUP_LABEL = { momentum: "Momentum", quality: "Quality", value: "Value", safety: "Safety" };
const FACTOR_LABEL = {
  mom_12_1: "12-month momentum (skip last month)", mom_6_1: "6-month momentum (skip last month)",
  high_52w: "Price vs 52-week high", vol_1y: "1-year volatility (lower is safer)", quality_roe: "Return on equity",
  quality_roce: "Return on capital employed", quality_cfo_pat: "Cash from operations ÷ profit (5 yrs)",
  quality_de: "Debt ÷ equity (lower is better)", value_ep: "Earnings yield (1 ÷ P/E)", value_bp: "Book ÷ price",
};
const pctFmt = (k, v) => v == null ? "—" : /^(mom_|value_)/.test(k) || k === "vol_1y" ? `${(v * 100).toFixed(1)}%`
  : k === "high_52w" ? `${(v * 100).toFixed(0)}% of high` : k.startsWith("quality_roe") || k === "quality_roce" ? `${v.toFixed(1)}%` : v.toFixed(2);

// How FINN Rank is calculated (shown on the company page and the portfolio; mirrors backend finn/decision.py).
export function rankFormula(n) {
  return `<details class="formula"><summary>How FINN Rank is calculated</summary>
    <ol>
      <li>Each measure is turned into a <b>percentile from 0 to 100</b> among the ${n || ""} stocks FINN tracks (100 = best). For volatility and debt, lower is better, so the order is flipped.</li>
      <li><b>Momentum</b> = average percentile of: return from 12 months ago to 1 month ago · return from 6 months ago to 1 month ago · price ÷ 52-week high.</li>
      <li><b>Quality</b> = average percentile of: ROE · ROCE · 5-year cash from operations ÷ 5-year profit · debt ÷ equity. Banks and NBFCs use ROE only. Loss-makers get no cash-conversion score; negative net worth gets the worst debt score.</li>
      <li><b>Value</b> = average percentile of: earnings yield (1 ÷ P/E) · book value ÷ price.</li>
      <li><b>Safety</b> = percentile of 1-year volatility of daily returns (lower volatility scores higher).</li>
      <li><b>Composite</b> = 0.35 × Momentum + 0.30 × Quality + 0.20 × Safety + 0.15 × Value. If a group has no data, the other weights are scaled up to add to 1.</li>
      <li><b>FINN Rank</b> = the composite's percentile ÷ 10, rounded up (1 to 10). Grades: A ≥ 80, B ≥ 60, C ≥ 40, D ≥ 20, F below 20.</li>
    </ol>
    <p class="caption">Prices: Yahoo Finance daily closes (10 years). Fundamentals: Screener, latest snapshot. ${esc(CAVEAT)}</p></details>`;
}

export function rankBadge(r) {
  if (!r || r.rank == null) return "";
  return `<span class="rank-b" title="FINN Rank ${r.rank}/10 · ${esc(r.label)} · ${esc(CAVEAT)}">${r.rank}<small>/10</small></span>`;
}

function flagRow(f) {
  return `<li class="flag ${esc(f.level)}"><span class="lvl">${esc(f.level)}</span>
    <a href="${esc(f.url || "#")}" target="_blank" rel="noopener">${esc(f.evidence)}</a>
    <span class="note">${esc(f.flag_type.replace(/_/g, " "))} · ${esc((f.filed_at || "").slice(0, 10))}</span></li>`;
}

export function signalCard(c, st = {}) {
  const r = c.rank;
  if (!r) return "";
  const grades = Object.entries(GROUP_LABEL).map(([g, l]) => `<div class="g"><span class="gl">${l}</span>
    <span class="gr gr-${esc((r.grades[g] || "—").replace("—", "na"))}">${esc(r.grades[g] || "—")}</span>
    <span class="note">${r.groups[g] == null ? "no data" : `${Math.round(r.groups[g])}th pct`}</span></div>`).join("");
  const ms = r.measures || [];
  const byG = Object.keys(GROUP_LABEL).map((g) => [g, ms.filter((m) => m.group === g)]).filter(([, xs]) => xs.length);
  const drivers = byG.map(([g, xs]) => `<li class="dg"><b>${GROUP_LABEL[g]}</b><span class="n">grade ${esc(r.grades[g] || "—")}${r.groups[g] == null ? "" : ` · ${Math.round(r.groups[g])}th pct`}</span></li>`
    + xs.map((m) => `<li><span>${esc(m.label)}<small class="mean">${esc(m.meaning)}</small></span><span class="n">${m.value == null ? "no data" : `${esc(m.value)} · ${m.percentile}th pct`}</span></li>`).join("")).join("");
  const reasons = (r.reasons || []).length ? `<ul class="reasons">${r.reasons.map((x, i) => `<li${i === 0 ? ' class="lead"' : ""}>${esc(x)}</li>`).join("")}</ul>` : "";
  const flags = c.flags?.length ? `<ul class="flags">${c.flags.map(flagRow).join("")}</ul>` : `<p class="note">No red or amber flags in filings FINN has seen.</p>`;
  const why = st.why ? whyBlock(st.why) : `<button type="button" class="btn ghost" data-act="why-move" data-symbol="${esc(c.symbol)}"${st.whyLoading ? " disabled" : ""}>${st.whyLoading ? "Checking filings and news…" : "Why did it move?"}</button>`;
  const ask = askBlock(c.symbol, st);
  return `<div class="card signal" style="padding:16px">
    <div class="sec-head" style="margin:0"><b>FINN Signal</b><span class="sec-sub">${esc(r.as_of ? `prices to ${r.as_of}` : "")}${r.data?.stale ? " · stale" : ""}</span></div>
    ${r.rank == null ? `<p class="note">Not enough data for a rank yet (${esc((r.data?.insufficient || []).length)} inputs missing). Long price history loads in the background after start-up.</p>` : `
    <div class="sig-top"><div class="rank-big">${r.rank}<small>/10</small></div><div><p class="sig-label">${esc(r.label)}</p>
      ${r.label_reason ? `<p class="sig-why">${esc(r.label_reason)}</p>` : ""}
      <p class="note">Overall score beats ${Math.round(r.composite_pct)}% of the ${r.universe_size} stocks FINN tracks.</p></div></div>
    <div class="grades">${grades}</div>
    <div class="sec-head" style="margin-top:10px"><b>Why this rank</b></div>${reasons}
    ${drivers ? `<details><summary>Every measure behind it</summary><ul class="drivers">${drivers}</ul>
      </details>` : ""}${rankFormula(r.universe_size)}`}
    <div class="sec-head" style="margin-top:14px"><b>Red flags</b><span class="sec-sub">from exchange filings</span></div>${flags}
    <div class="sec-head" style="margin-top:14px"><b>Latest move</b></div>${why}
    ${ask}
    <p class="caveat">${esc(CAVEAT)}</p></div>`;
}

function whyBlock(w) {
  if (!w.ok) return `<p class="note">${esc(w.reason || "Not available")}</p>`;
  const cited = (w.sources || []).filter((s) => (w.cited_ids || []).includes(s.id));
  const src = cited.length ? cited : (w.sources || []);   // rule-based text: list what FINN found around the move
  return `<p>${esc(w.summary)}</p>
    <p class="note">${esc(w.confidence_note)}${w.method === "llm" ? " · written by AI from the listed sources, numbers checked" : " · rule-based"}</p>
    ${w.pending ? `<p class="note">The AI explanation is still being written (the free model quota is queued). <button type="button" class="btn ghost" data-act="why-move" data-symbol="${esc(w.symbol)}">Check again</button></p>` : ""}
    ${src.length ? `<ul class="srcs">${src.map((s) => `<li><a href="${esc(s.url || "#")}" target="_blank" rel="noopener">${esc(s.text)}</a> <span class="note">${esc(s.type)}</span></li>`).join("")}</ul>` : ""}`;
}

function askBlock(sym, st) {
  const a = st.answer;
  const list = (t, xs) => xs?.length ? `<p class="ask-h">${t}</p><ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const ans = a ? `<div class="ask-ans">${a.headline ? `<p><b>${esc(a.headline)}</b></p>` : ""}
    ${list("Red flags", a.flags)}${list("In favour", a.for)}${list("Against", a.against)}${list("What to watch", a.what_to_watch)}
    ${a.bottom_line ? `<p>${esc(a.bottom_line)}</p>` : ""}
    ${a.citations?.length ? `<p class="caption">Sources: ${a.citations.map((c) => c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.label)}</a>` : esc(c.label)).join(" · ")}</p>` : ""}
    <p class="note">${a.method === "llm" ? "Written by AI from FINN's data; numbers and sources checked." : "Summary from FINN's data (no AI)."}</p></div>` : "";
  return `<div class="sec-head" style="margin-top:14px"><b>Ask FINN</b></div>
    <form class="ask-f" data-ask="${esc(sym)}"><label class="sr" for="ask-${esc(sym)}">Ask about ${esc(sym)}</label>
      <input id="ask-${esc(sym)}" name="q" maxlength="500" autocomplete="off" placeholder="e.g. What are the risks for ${esc(sym)}?" value="${esc(st.q || "")}">
      <button class="btn" type="submit"${st.asking ? " disabled" : ""}>${st.asking ? "Thinking…" : "Ask"}</button></form>${ans}`;
}

export function healthCard(h) {
  if (!h) return `<div class="card empty-card" role="status">Checking portfolio health…</div>`;
  if (!h.ok) return "";
  const item = (x) => `<li>${x.symbol ? `<a href="#/company/${encodeURIComponent(x.symbol)}/overview"><b>${esc(x.symbol)}</b></a> ` : ""}${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.text)}</a>` : esc(x.text)}${x.date ? ` <span class="note">${esc(x.type)} · ${esc(x.date)}</span>` : ""}</li>`;
  const comps = h.components.map((c) => `<li class="ded"><div class="ded-top"><span><b>${esc(c.label)}</b> <span class="note">weight ${c.weight}%</span></span>
      <span class="n">${c.value == null ? "no data" : `${Math.round(c.value)}/100 → ${c.contribution} pts`}</span></div>
    <p class="note" style="margin:2px 0 0">${esc(c.how)}</p>
    ${c.items?.length ? `<details class="fold" style="padding:0"><summary>${c.items.length} item${c.items.length === 1 ? "" : "s"}</summary><ul class="ded-items">${c.items.map(item).join("")}</ul></details>` : ""}</li>`).join("");
  return `<div class="card health" style="padding:16px"><div class="sec-head" style="margin:0"><b>Portfolio health</b><span class="sec-sub">${h.holdings} holdings · equal-weighted</span></div>
    <div class="sig-top"><div class="rank-big">${h.score}<small>/100</small></div><div><p class="note" style="margin:0">${esc(h.formula)}</p>
      ${h.pending?.length ? `<p class="note" style="margin:4px 0 0">${h.pending.length} holding${h.pending.length === 1 ? " is" : "s are"} still loading price history and ${h.pending.length === 1 ? "is" : "are"} not in Stock strength yet.</p>` : ""}</div></div>
    <ul class="drivers">${comps}</ul>
    <p class="caption">${esc(h.note)}</p><p class="caveat">${esc(CAVEAT)}</p></div>`;
}

export function aiBriefCard(b) {
  if (!b || !b.bullets?.length) return "";
  return `<section class="bsec aibrief" aria-labelledby="h-ai"><div class="sec-head"><h2 class="sec-title" id="h-ai">Morning briefing</h2><span class="sec-sub">${esc(b.headline)}</span></div>
    <div class="card list">${b.bullets.map((x) => `<a class="li" href="#/company/${encodeURIComponent(x.symbol)}/overview"><p class="li-head" style="margin:0">${esc(x.text)}</p></a>`).join("")}</div>
    <p class="caption">Built from filings, prices and FINN Rank. ${esc(CAVEAT)}</p></section>`;
}

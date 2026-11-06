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

const PARTS = [
  ["momentum", "Momentum", "Is the share price going up or down lately?", "Average of three measures: the price change over the past 12 months and over the past 6 months (both leaving out the latest month, which is often noisy), and how close today's price is to its highest price of the past year.", "35%"],
  ["quality", "Quality", "Does the business earn good profit, turn it into cash and keep debt low?", "Average of: ROE (profit for every ₹100 of the owners' money), ROCE (profit for every ₹100 of all money used, including loans), cash from operations ÷ profit over 5 years, and debt ÷ equity. Banks and NBFCs use ROE only, because their debt is their raw material.", "30%"],
  ["safety", "Safety", "How calm is the share price?", "How much the price moves up and down from day to day over the past year (volatility). Calmer prices score higher.", "20%"],
  ["value", "Value", "Is the share cheap for what the company earns and owns?", "Average of: earnings yield (yearly profit ÷ share price, the opposite of P/E) and book value ÷ price. Higher numbers mean cheaper.", "15%"],
];
const GRADES = [["A", "80 – 100", "Better than at least 80% of your stocks: among the best"], ["B", "60 – 79", "Better than most of your stocks"],
  ["C", "40 – 59", "Around the middle"], ["D", "20 – 39", "Worse than most of your stocks"], ["F", "0 – 19", "Among the weakest of your stocks"]];
const GRADE_WORD = { A: "among the best", B: "better than most", C: "around the middle", D: "worse than most", F: "among the weakest", "—": "no data" };
const n1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toString());

function howTab(n) {
  return `<p class="sig-p">FINN looks at four things about every stock and compares the stock with the <b>${n} stocks in your portfolio</b> (holdings and watchlist). The ranking changes when you add or delete stocks.</p>
    <table class="sig-t"><thead><tr><th>Part</th><th>What it tells you</th><th>How FINN measures it</th><th class="n">Weight</th></tr></thead>
    <tbody>${PARTS.map(([, name, q, how, w]) => `<tr><th scope="row">${name}</th><td>${q}</td><td>${how}</td><td class="n">${w}</td></tr>`).join("")}</tbody></table>
    <h4 class="sig-h">Step by step</h4>
    <ol class="sig-steps">
      <li><b>Percentile for each measure.</b> FINN lines up your ${n} stocks on that measure. A percentile of 80 means this stock is better than 80% of them; 0 is the worst, 100 the best. For volatility and debt, lower is better, so the order is flipped.</li>
      <li><b>Score for each part</b> = the average of its measures' percentiles. The grade comes from that score (table below).</li>
      <li><b>Overall score</b> = 35% × Momentum + 30% × Quality + 20% × Safety + 15% × Value. If a part has no data, the other weights are scaled up so they still add to 100%.</li>
      <li><b>FINN Rank</b> = how the overall score compares with your other stocks, as a percentile ÷ 10, rounded up. So the rank goes from 1 (weakest in your portfolio) to 10 (strongest).</li>
    </ol>
    <table class="sig-t"><thead><tr><th>Grade</th><th class="n">Score</th><th>What it means</th></tr></thead>
    <tbody>${GRADES.map(([g, r, m]) => `<tr><th scope="row"><span class="gr gr-${g}">${g}</span></th><td class="n">${r}</td><td>${m}</td></tr>`).join("")}</tbody></table>
    <p class="caption">Prices: Yahoo Finance daily closes (up to 10 years). Company figures: Screener, latest annual numbers.</p>`;
}

function calcTab(r) {
  const ms = r.measures || [];
  const parts = PARTS.map(([g, name]) => {
    const xs = ms.filter((m) => m.group === g);
    if (!xs.length) return "";
    const have = xs.filter((m) => m.percentile != null);
    const gv = r.groups[g], gr = r.grades[g] || "—";
    return `<table class="sig-t calc"><caption>${name}</caption><thead><tr><th>Measure</th><th class="n">This stock</th><th class="n">Percentile</th></tr></thead>
      <tbody>${xs.map((m) => `<tr><td>${esc(m.label)}<small class="mean">${esc(m.meaning)}</small></td><td class="n">${m.value == null ? "no data" : esc(m.value)}</td><td class="n">${m.percentile == null ? "—" : m.percentile}</td></tr>`).join("")}</tbody>
      <tfoot><tr><td colspan="3">${gv == null ? `${name}: not enough data.` : `${name} score = ${have.length > 1 ? `(${have.map((m) => m.percentile).join(" + ")}) ÷ ${have.length}` : `${have[0]?.percentile} (one measure)`} = <b>${n1(gv)}</b> → grade <span class="gr gr-${gr}">${gr}</span> (${GRADE_WORD[gr]})`}</td></tr></tfoot></table>`;
  }).join("");
  const W = { momentum: 0.35, quality: 0.30, safety: 0.20, value: 0.15 };
  const avail = Object.keys(W).filter((g) => r.groups[g] != null);
  const wsum = avail.reduce((a, g) => a + W[g], 0);
  const terms = avail.map((g) => `${Math.round((W[g] / wsum) * 100)}% × ${n1(r.groups[g])}`).join(" + ");
  const overall = r.composite_score;
  const rankLine = r.rank == null ? "Not enough data for a rank." : `Overall score ${n1(overall)} is higher than ${Math.round(r.composite_pct)}% of your ${r.universe_size} stocks → percentile ${Math.round(r.composite_pct)} ÷ 10, rounded up = <b>FINN Rank ${r.rank}/10</b>.`;
  return `${parts}<div class="sig-total"><p><b>Overall score</b> = ${terms} = <b>${n1(overall)}</b>${wsum < 0.999 ? ` <span class="note">(weights scaled up because ${Object.keys(W).filter((g) => !avail.includes(g)).join(", ")} has no data)</span>` : ""}</p><p>${rankLine}</p></div>`;
}

export function signalCard(c, st = {}) {
  const r = c.rank;
  if (!r) return "";
  const tab = st.tab || "how";
  const flags = c.flags?.length ? `<ul class="flags">${c.flags.map(flagRow).join("")}</ul>` : `<p class="note">No red or amber flags in the exchange filings FINN has seen for this company.</p>`;
  return `<div class="card signal" style="padding:16px">
    <div class="sec-head" style="margin:0"><b>FINN Signal</b><span class="sec-sub">${esc(r.as_of ? `prices to ${r.as_of}` : "")}${r.data?.stale ? " · stale" : ""}</span></div>
    <div class="sig-top"><div class="rank-big">${r.rank == null ? "—" : r.rank}<small>/10</small></div><div>
      <p class="sig-label">${esc(r.headline || r.label)}</p>
      <p class="note" style="margin:2px 0 0">Compared with the ${r.universe_size} stock${r.universe_size === 1 ? "" : "s"} in your portfolio. 10 = strongest, 1 = weakest.</p></div></div>
    <div class="seg sig-tabs" role="tablist" aria-label="FINN Rank">
      <button type="button" class="seg-b" role="tab" data-sigtab="how" data-symbol="${esc(c.symbol)}" aria-pressed="${tab === "how"}">How FINN Rank works</button>
      <button type="button" class="seg-b" role="tab" data-sigtab="calc" data-symbol="${esc(c.symbol)}" aria-pressed="${tab === "calc"}">Calculation for ${esc(c.symbol)}</button></div>
    <div class="sig-body">${tab === "calc" ? calcTab(r) : howTab(r.universe_size)}</div>
    <div class="sec-head" style="margin-top:16px"><b>Red flags</b><span class="sec-sub">from exchange filings</span></div>${flags}
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

export function healthCard(h, st = {}) {
  if (!h) return `<div class="card empty-card" role="status">Checking portfolio health…</div>`;
  if (!h.ok) return "";
  const tab = st.htab || "how";
  const by = Object.fromEntries(h.components.map((c) => [c.key, c]));
  const weakest = [...h.components].filter((c) => c.value != null).sort((a, b) => a.value - b.value)[0];
  const item = (x) => `<li>${x.symbol ? `<a href="#/company/${encodeURIComponent(x.symbol)}/overview"><b>${esc(x.symbol)}</b></a> ` : ""}${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.text)}</a>` : esc(x.text)}${x.date ? ` <span class="note">${esc(x.type)} · ${esc(x.date)}</span>` : ""}</li>`;
  const how = `<table class="sig-t"><thead><tr><th>Part</th><th>What it checks</th><th>How it is scored (0 – 100)</th><th class="n">Weight</th></tr></thead><tbody>
      <tr><th scope="row">Stock strength</th><td>Are your stocks good on their own?</td><td>Each holding gets a 0–100 score from fixed scales (below): momentum 35%, quality 30%, safety 20%, value 15%. This part is the average over your holdings.</td><td class="n">50%</td></tr>
      <tr><th scope="row">Filing risk</th><td>Did any of your companies file something worrying?</td><td>100 × (1 − (holdings with a red flag + ½ × holdings with only amber flags) ÷ number of holdings). Red: missed payments, regulator or court orders, auditor or CEO/CFO leaving, rating cuts. Amber: shares pledged, unclear court judgments, results within 5 days.</td><td class="n">20%</td></tr>
      <tr><th scope="row">Diversification</th><td>Is your money spread across different industries?</td><td>100 when every holding is in a different sector, 0 when all are in one. Formula: 100 × (1 − sum of squared sector shares) ÷ (1 − 1 ÷ number of holdings).</td><td class="n">15%</td></tr>
      <tr><th scope="row">Trend breadth</th><td>How many of your stocks are in a healthy price trend?</td><td>Share of holdings whose momentum percentile is 40 or more (not in the weaker part of your portfolio).</td><td class="n">15%</td></tr></tbody></table>
    <h4 class="sig-h">Fixed scales for stock strength</h4>
    <p class="sig-p">A measure gets 0 points at the first value and 100 points at the second, in a straight line in between. These don't depend on your other stocks, so removing a weak stock or adding a strong one always moves health the right way.</p>
    <table class="sig-t"><thead><tr><th>Measure</th><th class="n">0 points</th><th class="n">100 points</th></tr></thead>
      <tbody>${(h.scales || []).map((x) => `<tr><td>${esc(x.label)}</td><td class="n">${esc(x.zero)}</td><td class="n">${esc(x.full)}</td></tr>`).join("")}</tbody></table>
    <p class="caption">Every holding counts equally because FINN doesn't know how many shares you own.</p>`;
  const mine = `<table class="sig-t"><thead><tr><th>Part</th><th class="n">Score</th><th class="n">Weight</th><th class="n">Points</th></tr></thead><tbody>
      ${h.components.map((c) => `<tr><th scope="row">${esc(c.label)}</th><td class="n">${c.value == null ? "no data" : Math.round(c.value)}</td><td class="n">${c.weight}%</td><td class="n">${c.contribution == null ? "—" : c.contribution}</td></tr>`).join("")}</tbody>
      <tfoot><tr><th scope="row">Portfolio health</th><td></td><td></td><td class="n"><b>${h.score}</b></td></tr></tfoot></table>
    ${h.components.map((c) => `<div class="hc"><p><b>${esc(c.label)}</b>: ${esc(c.how)}</p>${c.items?.length ? `<ul class="ded-items">${c.items.map(item).join("")}</ul>` : ""}</div>`).join("")}`;
  return `<div class="card health" style="padding:16px"><div class="sec-head" style="margin:0"><b>Portfolio health</b><span class="sec-sub">${h.holdings} holdings</span></div>
    <div class="sig-top"><div class="rank-big">${h.score}<small>/100</small></div><div>
      <p class="sig-label" style="font-weight:500">${h.score >= 70 ? "In good shape" : h.score >= 50 ? "Reasonable, with some weak spots" : "Needs attention"}${weakest ? `. Weakest part: ${esc(weakest.label.toLowerCase())} (${Math.round(weakest.value)}/100).` : "."}</p>
      ${h.pending?.length ? `<p class="note" style="margin:2px 0 0">${h.pending.length} holding${h.pending.length === 1 ? " is" : "s are"} without enough price history yet (not in Stock strength).</p>` : ""}</div></div>
    <details class="hdetails"${st.hopen ? " open" : ""} data-hdetails="1"><summary>See how this is calculated</summary>
      <div class="seg sig-tabs" role="tablist" aria-label="Portfolio health">
        <button type="button" class="seg-b" data-htab="how" aria-pressed="${tab === "how"}">How health is calculated</button>
        <button type="button" class="seg-b" data-htab="mine" aria-pressed="${tab === "mine"}">Your portfolio's calculation</button></div>
      <div class="sig-body">${tab === "mine" ? mine : how}</div></details>
    <p class="caveat">${esc(CAVEAT)}</p></div>`;
}

export function aiBriefCard(b) {
  if (!b || !b.bullets?.length) return "";
  return `<section class="bsec aibrief" aria-labelledby="h-ai"><div class="sec-head"><h2 class="sec-title" id="h-ai">Morning briefing</h2><span class="sec-sub">${esc(b.headline)}</span></div>
    <div class="card list">${b.bullets.map((x) => `<a class="li" href="#/company/${encodeURIComponent(x.symbol)}/overview"><p class="li-head" style="margin:0">${esc(x.text)}</p></a>`).join("")}</div>
    <p class="caption">Built from filings, prices and FINN Rank. ${esc(CAVEAT)}</p></section>`;
}

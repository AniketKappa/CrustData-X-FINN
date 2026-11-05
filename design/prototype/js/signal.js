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
  const drivers = (r.drivers || []).map((d) => `<li><span>${esc(FACTOR_LABEL[d.factor] || d.factor)}</span>
    <span class="n">${esc(pctFmt(d.factor, d.value))} · ${d.pct}th pct</span></li>`).join("");
  const flags = c.flags?.length ? `<ul class="flags">${c.flags.map(flagRow).join("")}</ul>` : `<p class="note">No red or amber flags in filings FINN has seen.</p>`;
  const why = st.why ? whyBlock(st.why) : `<button type="button" class="btn ghost" data-act="why-move" data-symbol="${esc(c.symbol)}"${st.whyLoading ? " disabled" : ""}>${st.whyLoading ? "Checking filings and news…" : "Why did it move?"}</button>`;
  const ask = askBlock(c.symbol, st);
  return `<div class="card signal" style="padding:16px">
    <div class="sec-head" style="margin:0"><b>FINN Signal</b><span class="sec-sub">${esc(r.as_of ? `prices to ${r.as_of}` : "")}${r.data?.stale ? " · stale" : ""}</span></div>
    ${r.rank == null ? `<p class="note">Not enough data for a rank yet (${esc((r.data?.insufficient || []).length)} inputs missing). Long price history loads in the background after start-up.</p>` : `
    <div class="sig-top"><div class="rank-big">${r.rank}<small>/10</small></div><div><p class="sig-label">${esc(r.label)}</p>
      <p class="note">Composite ${Math.round(r.composite_pct)}th percentile among ${r.universe_size} stocks FINN tracks</p></div></div>
    <div class="grades">${grades}</div>
    ${drivers ? `<details><summary>What drives it</summary><ul class="drivers">${drivers}</ul>
      <p class="caption">Weights: momentum 35%, quality 30%, safety 20%, value 15%. Percentiles are within FINN's tracked stocks. Fundamentals from Screener (latest snapshot); prices from Yahoo Finance.</p></details>` : ""}`}
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
  const ded = h.deductions.map((d) => `<li><span>${esc(d.reason)}</span><span class="n">${d.points ? `−${d.points}` : "note"}</span></li>`).join("");
  const top = Object.entries(h.sectors).slice(0, 3).map(([s, n]) => `${esc(s)} ${n}`).join(" · ");
  return `<div class="card health" style="padding:16px"><div class="sec-head" style="margin:0"><b>Portfolio health</b><span class="sec-sub">equal-weighted</span></div>
    <div class="sig-top"><div class="rank-big">${h.score}<small>/100</small></div><div>
      <p class="note">Starts from the average FINN Rank percentile of your ${h.ranked} ranked holdings (${h.base_avg_composite_pct}), minus the items below.</p></div></div>
    ${ded ? `<ul class="drivers">${ded}</ul>` : `<p class="note">No deductions.</p>`}
    <p class="note">Largest sectors: ${top}</p><p class="caption">${esc(h.note)}</p><p class="caveat">${esc(CAVEAT)}</p></div>`;
}

export function aiBriefCard(b) {
  if (!b || !b.bullets?.length) return "";
  return `<div class="card aibrief" style="padding:16px;margin-bottom:12px"><div class="sec-head" style="margin:0"><b>Morning briefing</b><span class="sec-sub">${esc(b.headline)}</span></div>
    <ul class="drivers">${b.bullets.map((x) => `<li><a href="#/company/${encodeURIComponent(x.symbol)}/overview">${esc(x.text)}</a></li>`).join("")}</ul>
    <p class="caveat">Built from filings, prices and FINN Rank. ${esc(CAVEAT)}</p></div>`;
}

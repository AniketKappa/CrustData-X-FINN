// Business logic for the prototype. Pure functions only: no DOM, no fixtures imported.
// Mirrors what the backend computes in ARCHITECTURE §5 (numbers from code, not models).

export const HIGH_PRIORITY = ["results", "management_change", "M&A", "litigation", "credit_rating"];
export const CATEGORY_LABEL = {
  results: "Results", management_change: "Management change", "M&A": "M&A", litigation: "Litigation",
  credit_rating: "Credit rating", earnings_call: "Earnings call", board_meeting: "Board meeting",
  press_release: "Press release", unclassified: "Routine", market_move: "Price / volume",
  fund_raise: "Fund raise", insider_trading: "Insider trading", investor_meetings: "Investor meeting",
  dividend: "Dividend", bonus_split: "Bonus / split", capex: "Capex", postal_ballot: "Postal ballot",
  agm_egm: "AGM / EGM", pledging: "Pledging",
};
export const WINDOWS = [
  { id: "24h", label: "24 hours", hours: 24 },
  { id: "3d", label: "3 days", hours: 72 },
  { id: "7d", label: "7 days", hours: 168 },
];
export const DEFAULT_SETTINGS = {
  price_pct: 5, vol_mult: 2,
  categories: { results: true, management_change: true, "M&A": true, litigation: true, credit_rating: true, market_move: true },
};

const t = (iso) => new Date(iso).getTime();

export function inWindow(items, windowId, asOf) {
  const w = WINDOWS.find((x) => x.id === windowId) || WINDOWS[0];
  const end = t(asOf), start = end - w.hours * 3600e3;
  return items.filter((i) => t(i.published_at) > start && t(i.published_at) <= end);
}

// Market-move alerts are evaluated on read against the device's thresholds (ARCH §5.7).
export function evaluateAlerts(bars, settings, asOf) {
  if (!settings.categories.market_move) return [];
  const out = [];
  for (const b of bars) {
    const chg = ((b.close - b.prev_close) / b.prev_close) * 100;
    const mult = b.volume / b.prev20;
    const priceHit = Math.abs(chg) >= settings.price_pct;
    const volHit = mult >= settings.vol_mult;
    if (!priceHit && !volHit) continue;
    const parts = [];
    if (priceHit) parts.push(`close ${chg >= 0 ? "up" : "down"} ${Math.abs(chg).toFixed(1)}%`);
    if (volHit) parts.push(`volume ${mult.toFixed(1)}× its 20-day average`);
    out.push({
      id: `m-${b.symbol}`, symbol: b.symbol, company: b.company, category: "market_move", event: "Price / volume",
      published_at: `${b.date}T15:30:00+05:30`, fixture: true, alert: true,
      title: cap(parts.join("; ")),
      why: `Crossed your ${[priceHit && `±${settings.price_pct}% price`, volHit && `${settings.vol_mult}× volume`].filter(Boolean).join(" and ")} threshold. No announcement explains it yet.`,
      chg, mult, rules: [priceHit && "price", volHit && "volume"].filter(Boolean),
      source: { source_class: "MARKET_DATA", source_name: "End-of-day bar (fixture)", locator: `${b.date} close`, url: null, fixture: true },
      calc: { close: b.close, prev_close: b.prev_close, volume: b.volume, prev20: b.prev20 },
    });
  }
  // asOf is accepted so the live version can drop bars older than the window.
  void asOf;
  return out;
}

export function isHigh(item, settings) {
  if (item.category === "market_move") return true;
  return HIGH_PRIORITY.includes(item.category) && settings.categories[item.category] !== false;
}

// state: { done: {id:true}, snoozed: {id: untilMs} }
export function buildBriefing({ items, alerts, windowId, asOf, settings, state }) {
  const now = t(asOf);
  const visible = (i) => !state.done[i.id] && !(state.snoozed[i.id] > now);
  const pool = [...inWindow(items, windowId, asOf), ...alerts].sort((a, b) => t(b.published_at) - t(a.published_at));
  const hidden = pool.filter((i) => !visible(i));
  const live = pool.filter(visible);
  const routine = live.filter((i) => i.routine);
  const rest = live.filter((i) => !i.routine);
  const high = rest.filter((i) => isHigh(i, settings));
  const other = rest.filter((i) => !isHigh(i, settings));
  const companies = new Set(rest.map((i) => i.symbol)).size;
  return { high, other, routine, hidden, companies, total: pool.length };
}

// Live mode: the server has ranked and tiered the items (D-44) and applied the thresholds. The client only
// applies device state: Done/Snooze and the "Read first" category toggles.
export function buildLiveBriefing({ items, settings, state, nowMs }) {
  const visible = (i) => !state.done[i.id] && !(state.snoozed[i.id] > nowMs);
  const kept = items.filter((i) => !(i.alert && settings.categories.market_move === false));
  const hidden = kept.filter((i) => !visible(i));
  const live = kept.filter(visible);
  const routine = live.filter((i) => i.tier === "routine");
  const demoted = (i) => !i.alert && settings.categories[i.category] === false;
  const high = live.filter((i) => i.tier === "high" && !demoted(i));
  const other = live.filter((i) => i.tier === "normal" || (i.tier === "high" && demoted(i)));
  const companies = new Set([...high, ...other].map((i) => i.symbol)).size;
  return { high, other, routine, hidden, companies, total: kept.length };
}

export function summarize(b, windowLabel) {
  if (!b.high.length && !b.other.length) return `Nothing that needs attention in the last ${windowLabel}. ${b.routine.length} routine filings.`;
  const n = (k, one, many = one + "s") => `${k} ${k === 1 ? one : many}`;
  const other = b.other.length ? ` and ${n(b.other.length, "other update")}` : "";
  return `${n(b.high.length, "item")} to read first${other} across ${n(b.companies, "company", "companies")} in the last ${windowLabel}. ${n(b.routine.length, "routine filing")} below.`;
}

export function speechText(b, windowLabel, fmtTime) {
  const lines = [`FINN briefing. Demonstration data. ${summarize(b, windowLabel)}`];
  b.high.forEach((i, k) => lines.push(`${k + 1}. ${i.company}. ${i.title}. ${i.why || ""}`));
  if (b.other.length) lines.push(`Also: ${b.other.map((i) => `${i.company}, ${i.event.toLowerCase()}`).join("; ")}.`);
  void fmtTime;
  return lines.join(" ");
}

// ---------- financial computations ----------
export const pct = (a, b) => (b == null || b === 0 || a == null ? null : ((a - b) / Math.abs(b)) * 100);
export const margin = (num, den) => den.map((d, i) => (d ? (num[i] / d) * 100 : null));

export function periodTable(q, quarters) {
  const n = quarters.length - 1;
  return ["revenue", "ebitda", "pbt", "pat"].map((k) => ({
    key: k, value: q[k][n], prev: q[k][n - 1], yearAgo: q[k][n - 4] ?? null,
    qoq: pct(q[k][n], q[k][n - 1]), yoy: n >= 4 ? pct(q[k][n], q[k][n - 4]) : null,
  }));
}

export function cashQuality(d) {
  const { ocf, pat, capex } = d.cash;
  const conv = ocf.map((o, i) => (pat[i] ? o / pat[i] : null));
  const fcf = ocf.map((o, i) => o - capex[i]);
  const sum = (a) => a.reduce((x, y) => x + y, 0);
  const cumConv = sum(ocf) / sum(pat);
  const { net_debt, equity, ebitda_ttm } = d.debt;
  return { conv, fcf, cumConv, netDebtEbitda: net_debt / ebitda_ttm, netDebtEquity: net_debt / equity, netCash: net_debt < 0 };
}

// Verdict rules for quantitative guidance (ARCH §5.3). Higher is better unless direction === "lower".
export const PARTLY_TOLERANCE = 0.10;
export function verdict(row) {
  if (row.kind !== "quant") return row.status; // qualitative: status set by the reviewed evidence check
  if (!row.actual) return "Not yet measurable";
  const v = row.actual.value, { low, high } = row.band;
  const lower = row.direction === "lower";
  const met = lower ? v <= high : v >= low;
  if (met) return "Delivered";
  const gap = lower ? (v - high) / high : (low - v) / low;
  return gap <= PARTLY_TOLERANCE ? "Partly delivered" : "Missed";
}
export const STATUSES = ["Delivered", "Partly delivered", "Missed", "Not yet measurable", "Insufficient evidence"];

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ---------- brief sections (PRODUCT_SPEC §4.4; owner brief: one section per material type) ----------
export const SECTIONS = [
  { id: "market", label: "Market moves", short: "Moves", one: "market move", many: "market moves" },
  { id: "results", label: "Results", short: "Results", cats: ["results"], one: "result", many: "results" },
  { id: "management", label: "Management changes", short: "Management", cats: ["management_change"], one: "management change", many: "management changes" },
  { id: "deals", label: "Deals (M&A)", short: "Deals", cats: ["M&A"], one: "deal", many: "deals" },
  { id: "legal", label: "Legal & regulatory", short: "Legal", cats: ["litigation"], one: "legal update", many: "legal updates" },
  { id: "ratings", label: "Credit ratings", short: "Ratings", cats: ["credit_rating"], one: "rating action", many: "rating actions" },
  { id: "other", label: "Other updates", short: "Other", one: "other update", many: "other updates" },
];

export function sectionize(items, settings) {
  const out = SECTIONS.map((s) => ({ ...s, items: [], word: s.many }));
  const by = Object.fromEntries(out.map((s) => [s.id, s]));
  for (const i of items) {
    if (i.alert) { by.market.items.push(i); continue; }
    const sec = out.find((s) => s.cats?.includes(i.category));
    const on = settings.categories[i.category] !== false;
    (sec && on ? sec : by.other).items.push(i);
  }
  const rank = (i) => (i.score ? i.score.total : (i.tier === "high" ? 80 : 50));
  for (const s of out) s.items.sort((a, b) => rank(b) - rank(a) || new Date(b.published_at) - new Date(a.published_at));
  // Show a company's results numbers once (on its highest-ranked results item; filings outrank news).
  const shown = new Set();
  for (const s of out) for (const i of s.items) {
    if (!i.resultsBlock) continue;
    i.hideResults = shown.has(i.symbol);
    shown.add(i.symbol);
  }
  return out;
}

export function sectionSummary(sections, routineCount, windowLabel) {
  const n = (k, one, many = one + "s") => `${k} ${k === 1 ? one : many}`;
  const words = { market: ["market move"], results: ["result"], management: ["management change"], deals: ["deal"],
    legal: ["legal or regulatory item", "legal or regulatory items"], ratings: ["rating action"], other: ["other update"] };
  const parts = sections.filter((s) => s.items.length).map((s) => n(s.items.length, ...words[s.id]));
  const companies = new Set(sections.flatMap((s) => s.items.map((i) => i.symbol))).size;
  if (!parts.length) return `Nothing new for your portfolio in the last ${windowLabel}. ${n(routineCount, "routine filing")} collapsed below.`;
  return `${parts.join(", ")} across ${n(companies, "company", "companies")} in the last ${windowLabel}. `
    + `${n(routineCount, "routine filing")} collapsed below.`;
}

export function sectionSpeech(sections, routineCount, windowLabel) {
  const lines = [`FINN briefing. ${sectionSummary(sections, routineCount, windowLabel)}`];
  for (const s of sections) {
    if (!s.items.length) continue;
    lines.push(`${s.label}.`);
    s.items.slice(0, 4).forEach((i) => lines.push(`${i.company}: ${i.title}.${i.news ? ` Reported by ${i.publisher}.` : ""}`));
    if (s.items.length > 4) lines.push(`And ${s.items.length - 4} more.`);
  }
  return lines.join(" ");
}

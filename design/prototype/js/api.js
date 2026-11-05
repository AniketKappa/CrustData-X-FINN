// Client for the FINN API (ARCHITECTURE §10) and the adapter from API contracts to view items.
// When the page is served by the FINN backend, the Briefing runs on live data; when it is served by a plain
// static server, /health is missing and the app stays in fixture mode.


async function getJSON(url, opts = {}) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), opts.timeout ?? 15000);
  try {
    const r = await fetch(url, { cache: "no-store", signal: ctl.signal, ...opts });
    if (!r.ok) {
      let detail = "";
      try { detail = (await r.json()).detail || ""; } catch { /* not JSON */ }
      throw new Error(`HTTP ${r.status}${detail ? `: ${detail}` : ""}`);
    }
    return await r.json();
  } catch (e) {
    throw new Error(e.name === "AbortError" ? "the FINN API did not answer in time" : e.message);
  } finally {
    clearTimeout(t);
  }
}

export async function detectApi() {
  try {
    const h = await getJSON("/health", { timeout: 4000 });
    return h && h.ok ? h : null;
  } catch { return null; }
}

export const getPortfolio = () => getJSON("/v1/portfolio");
export const getHoldings = (settings) => getJSON(`/v1/holdings?price_pct=${settings.price_pct}&vol_mult=${settings.vol_mult}`);
export const searchStocks = (q) => getJSON(`/v1/search?q=${encodeURIComponent(q)}`, { timeout: 12000 });
export const getCompany = (sym) => getJSON(`/v1/company/${encodeURIComponent(sym)}`, { timeout: 45000 });
const post = (url, body) => getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const addHolding = (b) => post("/v1/holdings/add", b);
export const removeHolding = (symbol) => post("/v1/holdings/remove", { symbol });
export const getHealth = () => getJSON("/health", { timeout: 4000 });
export const triggerRefresh = () => getJSON("/jobs/refresh", { method: "POST", timeout: 180000 });
export const startResearch = (sym, force = false) => getJSON(`/v1/research/${encodeURIComponent(sym)}/start${force ? "?force=true" : ""}`, { method: "POST", timeout: 20000 });
export const retrySection = (sym, sec) => getJSON(`/v1/research/${encodeURIComponent(sym)}/retry?section=${encodeURIComponent(sec)}`, { method: "POST", timeout: 120000 });
export const getResearch = (sym) => getJSON(`/v1/research/${encodeURIComponent(sym)}`, { timeout: 10000 });
export const askResearch = (sym, question, history = []) => getJSON(`/v1/research/${encodeURIComponent(sym)}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, history }), timeout: 120000 });
export const getMove = (sym) => getJSON(`/v1/moves/${encodeURIComponent(sym)}`, { timeout: 60000 });
export const askAgent = (symbol, question) => getJSON("/v1/agent/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol, question }), timeout: 90000 });
export const getPortfolioHealth = () => getJSON("/v1/portfolio/health", { timeout: 30000 });
export const getRankList = () => getJSON("/v1/rank?scope=universe", { timeout: 30000 });
export const getAgentBriefing = () => getJSON("/v1/agent/briefing", { timeout: 30000 });
export const startRefresh = () => getJSON("/jobs/refresh?background=true", { method: "POST", timeout: 8000 });

// The app always loads the 7-day digest once and filters by window on the device, so switching windows is
// instant and empty sections can show "earlier this week" items.
export function getDigest(settings) {
  const q = new URLSearchParams({
    window_hours: 168,
    price_pct: settings.price_pct,
    vol_mult: settings.vol_mult,
  });
  return getJSON(`/v1/digest?${q}`);
}

const SUBTYPE_LABEL = {
  results_newspaper_ad: "Results newspaper ad", results_board_meeting_notice: "Board meeting notice",
  management_change_top: "Top management change", management_change_independent_director: "Independent director",
  credit_rating_downgrade: "Rating downgrade", credit_rating_reaffirmed: "Rating reaffirmed",
  earnings_call_transcript: "Call transcript", litigation_regulator: "Regulator action",
};

// Screener ResultsBlock -> the shape views.js renders (same as fixture results).
function adaptResults(r) {
  const filing = !!r.from_filing;
  return {
    periods: r.periods, basis: r.basis, unit: r.unit, notes: r.notes || [], isLender: r.is_lender, fromFiling: filing,
    page: r.page, url: r.source_url, check: r.check || null,
    rows: r.rows.map((x) => ({ metric: x.metric, value: x.latest, qoq: x.qoq, yoy: x.yoy, derived: x.derived, note: x.note })),
    source: filing
      ? { source_class: "PRIMARY_DOC", source_name: "Results filing", url: r.source_url, locator: `page ${r.page}`, fixture: !!r.provenance.fixture, passage: r.provenance.formula, note: "Opens the filed results PDF at this page." }
      : { source_class: "STANDARDIZED_TABLE", source_name: "screener.in Quarterly Results", url: r.source_url,
          locator: `${r.basis}, ${r.periods[0]}`, fixture: !!r.provenance.fixture, passage: r.provenance.formula },
  };
}

// DigestItem -> view item used by views.js. Original subject stays the title; nothing is generated.
export function adaptDigest(d, labels) {
  const signals = Object.fromEntries((d.market || []).map((s) => [s.symbol, s]));
  const annSymbols = new Set([...d.high, ...d.normal, ...d.routine].filter((i) => i.kind === "announcement").map((i) => i.symbol));
  const map = (i) => {
    const base = {
      id: i.id, symbol: i.symbol, company: i.company_name, category: i.category, tier: i.tier,
      published_at: i.filed_at, title: i.title, score: i.score, fixture: d.fixture, live: true,
      routine: i.tier === "routine",
    };
    if (i.kind === "market_alert") {
      const a = i.alert, s = signals[i.symbol] || {};
      return {
        ...base, alert: true, event: "Price / volume", chg: a.pct_change, mult: a.volume_multiple, rules: a.rules,
        why: annSymbols.has(i.symbol) ? "There's also a filing or news item from this company in your briefing."
          : "No filing or news from the company in this window explains the move yet.",
        latest: a.date === s.as_of, liveSession: !!a.live,
        calc: { close: a.close ?? s.close, prev_close: a.prev_close ?? s.prev_close, volume: a.volume ?? s.volume,
          prev20: a.avg_volume ?? s.avg_volume, lookback: a.lookback_used || s.lookback_used, live: !!a.live,
          as_of: a.date, thresholds: a.thresholds },
        source: { source_class: "MARKET_DATA", source_name: a.live ? `Price so far today (${a.provenance.source_name})` : `End-of-day prices (${a.provenance.source_name})`,
          locator: `session ${a.date}`, fixture: !!a.provenance.fixture,
          url: s.provenance?.url || null, date: a.date,
          passage: `${a.explanation}. ${a.provenance.formula || ""}`.trim() },
      };
    }
    if (i.kind === "news") {
      const n = i.news, c = i.classification;
      return {
        ...base, news: true, publisher: n.publisher, event: labels[c.category] || c.category, classification: c,
        related: i.related || [], person: i.person || null,
        resultsBlock: i.results ? adaptResults(i.results) : null, resultsStatus: i.results_status,
        source: { source_class: "EXTERNAL_WEB", source_name: n.publisher, locator: "news report", url: n.url,
          fixture: !!n.provenance.fixture, date: new Date(n.published_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
          passage: n.headline },
      };
    }
    const ann = i.announcement, c = i.classification;
    return {
      resultsBlock: i.results ? adaptResults(i.results) : null, resultsStatus: i.results_status, summary: i.summary || null,
      ...base, event: SUBTYPE_LABEL[c.subtype] || labels[c.category] || c.category, real: !d.fixture,
      detail: ann.detail, classification: c, exchange: ann.exchange,
      source: { source_class: "PRIMARY_DOC", source_name: `${ann.exchange} announcement`,
        locator: ann.attachments?.[0]?.size_text ? `attachment, ${ann.attachments[0].size_text}` : "attachment",
        url: ann.source_url, fixture: !!ann.provenance.fixture, date: new Date(ann.filed_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
        passage: ann.detail ? `${ann.subject} — ${ann.detail}` : ann.subject },
    };
  };
  return {
    items: [...d.high, ...d.normal, ...d.routine, ...(d.news || [])].map(map),
    signals, disclosures: d.disclosures || [], sources: d.sources || [],
    generatedAt: d.generated_at, windowEnd: d.window_end, fixture: d.fixture,
  };
}

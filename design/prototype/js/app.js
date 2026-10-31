// Controller: routing (URL hash is the state), data loading, event delegation, dialogs, charts, speech.
import { AS_OF, COMPANIES, ITEMS, EOD, DOSSIERS, RESEARCH } from "./fixtures.js";
import { WINDOWS, DEFAULT_SETTINGS, CATEGORY_LABEL, evaluateAlerts, buildBriefing, buildLiveBriefing, periodTable,
  sectionize, sectionSpeech } from "./logic.js";
import { detectApi, getDigest, getHealth, startRefresh, adaptDigest, getHoldings, searchStocks, getCompany,
  addHolding, removeHolding, startResearch, getResearch, askResearch } from "./api.js";
import { researchPicker, researchResults, researchDossier } from "./research.js";
import { registry, resetRegistry, companyView, researchView, evidenceBody, settingsBody } from "./views.js";
import { briefingV3, detailV3, aboutDataBody, portfolioV3, searchResults, companyV3, addSheet } from "./ui.js";
import { barChart, lineChart, groupedBars, rangeStrip, sparkline } from "./charts.js";
import { crShort, pctv, unitFmt, esc } from "./format.js";

const $ = (s, r = document) => r.querySelector(s);
const main = $("#main"), dlg = $("#dlg"), dlgBody = $("#dlg-body"), tip = $("#tip"), toast = $("#toast");
const wide = matchMedia("(min-width: 1024px)");
const speechOk = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

// ---------- device-local state (A-13) ----------
const store = {
  get(k, d) { try { const v = localStorage.getItem("finn." + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("finn." + k, JSON.stringify(v)); } catch { /* keep in memory */ } },
};
const S = {
  settings: { ...DEFAULT_SETTINGS, ...store.get("settings", {}), categories: { ...DEFAULT_SETTINGS.categories, ...(store.get("settings", {}).categories || {}) } },
  marks: store.get("marks", { done: {}, snoozed: {} }),
  routineOpen: false, speaking: null, notes: [], filter: "all",
  ptab: "hold", editing: false, search: { q: "", results: null, note: null }, expanded: new Set(), selected: new Set(),
  add: { q: "", results: null, note: null }, rsearch: { q: "", results: null, note: null },
};
// Actions that talk to the server are locked while in flight, so repeated or simultaneous taps run them once.
const busy = new Set();
async function once(key, fn) {
  if (busy.has(key)) return;
  busy.add(key);
  try { await fn(); } finally { busy.delete(key); }
}
// Live mode: on when the page is served by the FINN backend (same origin).
const LIVE = { on: false, mode: null, digest: null, digestKey: "", loading: false, error: null, refreshing: false, message: "",
  holdings: null, holdingsLoading: false, companies: new Map(), companyLoading: null, health: null,
  research: new Map(), rnotes: new Map(), asking: new Set() };
// Windows are measured from the server's clock (the digest's generated_at), so a fixture server and a live one
// both cut "last 24 hours" correctly.
const nowMs = () => (LIVE.on ? (LIVE.digest?.generatedAt ? Date.parse(LIVE.digest.generatedAt) : Date.now()) : new Date(AS_OF).getTime());
const thKey = () => `${S.settings.price_pct}|${S.settings.vol_mult}`;
const holdingsCount = () => (LIVE.holdings ? LIVE.holdings.holdings.length : COMPANIES.filter((c) => c.holding).length);

function showToast(msg) {
  toast.textContent = msg; toast.hidden = false;
  clearTimeout(showToast.t); showToast.t = setTimeout(() => { toast.hidden = true; }, 3800);
}

// ---------- loading ----------
async function loadDigest() {
  if (LIVE.loading) return;
  LIVE.loading = true; LIVE.error = null;
  const key = thKey();
  try {
    LIVE.digest = adaptDigest(await getDigest(S.settings), CATEGORY_LABEL);
    LIVE.digestKey = key;
  } catch (e) { LIVE.error = e.message; }
  LIVE.loading = false;
  render();
}
async function loadHoldings() {
  if (LIVE.holdingsLoading) return;
  LIVE.holdingsLoading = true;
  try { LIVE.holdings = await getHoldings(S.settings); } catch (e) { showToast(`Couldn't load your stocks: ${e.message}`); }
  LIVE.holdingsLoading = false;
  render();
}
async function loadCompany(sym) {
  if (LIVE.companyLoading === sym) return;
  LIVE.companyLoading = sym;
  try { LIVE.companies.set(sym, { data: await getCompany(sym), at: Date.now() }); }
  catch (e) { LIVE.companies.set(sym, { error: e.message, at: Date.now() }); }
  LIVE.companyLoading = null;
  render();
}
// Research: start (or join) the dossier build, then poll until it finishes. A build already running on the
// server is joined, so repeated taps never start a second one.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
async function loadResearch(sym, force = false) {
  await once(`research:${sym}`, async () => {
    let d;
    try { d = await startResearch(sym, force); } catch (e) { LIVE.research.set(sym, { data: { symbol: sym, status: "failed", error: e.message, steps: [] }, at: Date.now() }); render(); return; }
    LIVE.research.set(sym, { data: d, at: Date.now() }); render();
    while (d.status === "running") {
      await new Promise((r) => setTimeout(r, 2500));
      try { d = await getResearch(sym); } catch { continue; }
      LIVE.research.set(sym, { data: d, at: Date.now() });
      if (currentResearch() === sym) renderKeep();
    }
    if (currentResearch() === sym) renderKeep();
  });
}
const currentResearch = () => { const { parts, params } = parse(); return parts[0] === "research" ? (params.get("c") || "").toUpperCase() : null; };
// Re-render without losing what the user is typing in the ask bar.
function renderKeep() {
  const q = $("#rask-q"), v = q?.value, f = document.activeElement === q;
  render();
  const q2 = $("#rask-q"); if (q2 && v) q2.value = v; if (q2 && f) q2.focus();
}
async function askQuestion(sym, question) {
  question = question.trim();
  if (!question || LIVE.asking.has(sym)) return;
  stopListening();
  const notes = LIVE.rnotes.get(sym) || [];
  // The same question again (a double tap, or a repeat) scrolls to the answer already on screen.
  const same = notes.find((n) => n.question.toLowerCase() === question.toLowerCase() && (n.pending || n.status === "ok"));
  if (same) { document.getElementById(same.id)?.scrollIntoView({ block: "start", behavior: "smooth" }); return; }
  // Earlier answered turns go along as context, so "why?" or "and margins?" are understood.
  const history = notes.filter((n) => !n.pending && n.status === "ok").slice(-3)
    .map((n) => ({ question: n.question, answer: (n.claims || []).map((c) => c.text).join(" ").slice(0, 400) }));
  const id = `a${Date.now().toString(36)}`;
  notes.push({ id, question, pending: true });
  LIVE.rnotes.set(sym, notes); LIVE.asking.add(sym);
  render();
  document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });
  let a;
  try { a = await askResearch(sym, question, history); } catch (e) { a = { status: "error", message: `Couldn't get an answer: ${e.message}` }; }
  Object.assign(notes.find((n) => n.id === id), a, { pending: false });
  LIVE.asking.delete(sym);
  render();
  document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });
}
// Voice: words appear in the box as you speak; nothing is sent until you tap the arrow.
function listen() {
  if (!SR) return;
  if (S.rec) { stopListening(); return; }
  const rec = new SR(); rec.lang = "en-IN"; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
  const input = $("#rask-q"), before = input?.value ? input.value.trim() + " " : "";
  S.rec = rec; renderKeep();
  rec.onresult = (e) => {
    let text = "";
    for (let k = 0; k < e.results.length; k++) text += e.results[k][0].transcript;
    const box = $("#rask-q"); if (box) box.value = before + text;
  };
  rec.onerror = (e) => { if (e.error !== "aborted" && e.error !== "no-speech") showToast(e.error === "not-allowed" ? "Microphone access was blocked." : "Didn't catch that. Try again."); };
  rec.onend = () => { if (S.rec === rec) { S.rec = null; renderKeep(); const box = $("#rask-q"); if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); } } };
  rec.start();
}
function stopListening() { if (S.rec) { const r = S.rec; S.rec = null; try { r.stop(); } catch { /* already stopped */ } } }

function invalidate() { LIVE.digest = null; LIVE.holdings = null; LIVE.companies.clear(); }

// Fresh data on open: the app asks the server to fetch (respecting its short caches), shows what it has
// meanwhile, and reloads when the fetch finishes.
const FRESH_MS = 10 * 60e3;
async function pollRefresh() {
  LIVE.refreshing = true; render();
  let shownReady = false;
  for (let i = 0; i < 200; i++) {
    await new Promise((r) => setTimeout(r, i < 10 ? 1500 : 3000));
    let h;
    try { h = await getHealth(); } catch { break; }
    // Stage 1 done (prices, filings, news): show the Briefing now; PDF reading and backgrounds keep going.
    if (!shownReady && h.refresh?.stage === "ready") { shownReady = true; invalidate(); render(); }
    if (!h.refresh?.running) {
      if (h.refresh?.last_error) showToast(`Update finished with an error: ${h.refresh.last_error}`);
      break;
    }
  }
  LIVE.refreshing = false; invalidate(); render();
}
async function runRefresh() {
  await once("refresh", async () => {
    try { await startRefresh(); } catch (e) { showToast(`Couldn't start an update: ${e.message}`); return; }
    await pollRefresh();
    showToast("Up to date");
  });
}
async function refreshIfStale(h) {
  const last = h.refresh?.last_finished ? new Date(h.refresh.last_finished).getTime() : 0;
  if (h.refresh?.running) return once("refresh", pollRefresh);
  if (Date.now() - last > FRESH_MS) return runRefresh();
}

// ---------- routing ----------
function parse() {
  const raw = location.hash.replace(/^#\/?/, "") || "briefing";
  const [path, qs] = raw.split("?");
  return { parts: path.split("/").filter(Boolean), params: new URLSearchParams(qs || "") };
}
function go(hash) { if (location.hash !== hash) location.hash = hash; else render(); }
function setNav(top) {
  document.querySelectorAll(".nav a").forEach((a) => { if (a.dataset.nav === top) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
}

// Builds sections for the chosen window from a 7-day item set. Alerts always belong to the latest session.
function buildView(windowId) {
  const hours = WINDOWS.find((w) => w.id === windowId).hours;
  const cutoff = nowMs() - hours * 3600e3;
  let b7, all, asOf = AS_OF, live = null;
  if (LIVE.on) {
    b7 = buildLiveBriefing({ items: LIVE.digest.items, settings: S.settings, state: S.marks, nowMs: nowMs() });
    all = LIVE.digest.items; asOf = LIVE.digest.generatedAt;
    live = { refreshing: LIVE.refreshing, message: LIVE.message, fixture: LIVE.digest.fixture };
  } else {
    const alerts = evaluateAlerts(EOD, S.settings, AS_OF);
    const items = ITEMS.map(withFixtureResults);
    b7 = buildBriefing({ items, alerts, windowId: "7d", asOf: AS_OF, settings: S.settings, state: S.marks });
    all = [...items, ...alerts];
  }
  // The latest session's move always shows (on a Monday morning the 24H window would otherwise be empty);
  // older sessions' moves only in the windows that cover them, so 24H, 3D and 7D differ.
  const inWin = (i) => (i.alert && (i.latest || !LIVE.on)) || new Date(i.published_at).getTime() >= cutoff;
  const sections = sectionize([...b7.high, ...b7.other].filter(inWin), S.settings);
  const counts = Object.fromEntries(sections.map((s) => [s.id, s.items.filter((i) => !i.older).length]));
  // Biggest price changes over the window (1, 3 or 5 sessions), so the window changes the market picture too.
  const n = { "24h": "1", "3d": "3", "7d": "5" }[windowId];
  const names = Object.fromEntries((LIVE.holdings ? [...LIVE.holdings.holdings, ...LIVE.holdings.watchlist] : []).map((c) => [c.symbol, c.name]));
  const movers = LIVE.on ? Object.values(LIVE.digest.signals || {}).filter((s) => s.changes && s.changes[n] != null)
    .map((s) => ({ symbol: s.symbol, name: names[s.symbol] || s.symbol, chg: s.changes[n], close: s.close, live: s.live }))
    .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 6) : [];
  return { sections, counts, routine: b7.routine.filter(inWin), hidden: b7.hidden, all, asOf, live, movers, sessions: +n };
}

let lastRouteKey = "";
function render() {
  const { parts, params } = parse();
  let top = parts[0];
  if (top === "companies" && !parts[1]) { location.replace("#/portfolio"); return; }
  if (!["briefing", "portfolio", "company", "companies", "research"].includes(top)) top = "briefing";
  const navTop = top === "company" || top === "companies" ? "portfolio" : top;
  const scrollY = window.scrollY;
  resetRegistry();
  let html = "", title = "Briefing";

  if (top === "briefing") {
    const windowId = WINDOWS.some((w) => w.id === params.get("w")) ? params.get("w") : "24h";
    if (LIVE.on && (!LIVE.digest || LIVE.digestKey !== thKey())) {
      if (!LIVE.loading && !LIVE.error) loadDigest();
      if (!LIVE.holdings && !LIVE.holdingsLoading) loadHoldings();
      main.innerHTML = LIVE.error && !LIVE.loading
        ? `<div class="card empty-card"><p>Couldn't load your briefing: ${esc(LIVE.error)}.</p><button type="button" class="btn" data-act="retry-live">Try again</button></div>`
        : `<div class="card empty-card" role="status">${esc(LIVE.message || "Loading your briefing…")}</div>`;
      setNav("briefing");
      return;
    }
    const v = buildView(windowId);
    const selId = parts[1] === "item" ? decodeURIComponent(parts.slice(2).join("/")) : null;
    const sel = selId ? v.all.find((i) => i.id === selId) : null;
    const winLabel = WINDOWS.find((w) => w.id === windowId).label;
    S.lastBriefing = { sections: v.sections.map((s) => ({ ...s, items: s.items.filter((i) => !i.older) })), routine: v.routine, winLabel };
    if (S.filter !== "all" && !v.sections.some((s) => s.id === S.filter)) S.filter = "all";
    const list = briefingV3({ ...v, windowId, holdings: holdingsCount(), selectedId: selId, speaking: S.speaking === "brief", speechOk,
      routineOpen: S.routineOpen, filter: S.filter, expanded: S.expanded, busy });
    if (wide.matches) html = `<div class="split"><div class="col-list">${list}</div><aside class="pane" aria-label="Details">${detailV3(sel, { asPane: true, settings: S.settings })}</aside></div>`;
    else html = sel ? detailV3(sel, { asPane: false, settings: S.settings }) : list;
    if (selId && !sel) html = `<div class="card empty-card">That update is no longer in your briefing. <a href="#/briefing">Back</a></div>`;
    title = sel ? sel.title : "Briefing";
  } else if (top === "portfolio") {
    if (LIVE.on && !LIVE.holdings) {
      if (!LIVE.holdingsLoading) loadHoldings();
      html = `<div class="card empty-card" role="status">Loading your stocks…</div>`;
    } else {
      const h = LIVE.holdings || { holdings: COMPANIES.filter((c) => c.holding && !c.fixture).map((c) => ({ ...c, signal: null })),
        watchlist: COMPANIES.filter((c) => !c.holding && !c.fixture).map((c) => ({ ...c, signal: null })), editable: false };
      const asOf = h.holdings.find((c) => c.signal?.as_of)?.signal.as_of;
      html = portfolioV3({ holdings: h.holdings, watchlist: h.watchlist, tab: S.ptab, editing: S.editing, editable: LIVE.on && h.editable,
        live: LIVE.on, asOf, query: S.search.q, selected: S.selected });
    }
    title = "Portfolio";
  } else if (top === "company" || top === "companies") {
    const sym = decodeURIComponent(parts[1] || "").toUpperCase();
    const tab = parts[2] || "overview";
    if (DOSSIERS[sym] || !LIVE.on) {
      const company = COMPANIES.find((c) => c.symbol === sym) || { symbol: sym, name: sym };
      const section = ["overview", "financials", "cash", "promises"].includes(tab) ? tab : "overview";
      html = companyView({ company, dossier: DOSSIERS[sym], section });
      title = company.name;
    } else {
      const c = LIVE.companies.get(sym);
      if (!c || Date.now() - c.at > 5 * 60e3) {
        if (LIVE.companyLoading !== sym) loadCompany(sym);
        html = c?.data ? companyV3(c.data, tab) : `<div class="card empty-card" role="status">Loading ${esc(sym)}… the first visit fetches fundamentals from Screener.</div>`;
      } else if (c.error) {
        html = `<div class="card empty-card">Couldn't load ${esc(sym)}: ${esc(c.error)}</div>`;
      } else {
        html = companyV3(c.data, tab);
        title = c.data.name;
      }
    }
  } else if (LIVE.on) {
    const sym = (params.get("c") || "").toUpperCase();
    if (!sym) {
      if (!LIVE.holdings && !LIVE.holdingsLoading) loadHoldings();
      const mine = LIVE.holdings ? [...LIVE.holdings.watchlist, ...LIVE.holdings.holdings] : [];
      html = researchPicker({ query: S.rsearch.q, results: researchResults(S.rsearch.results, S.rsearch.note), mine, llm: LIVE.health?.research_llm });
    } else {
      const r = LIVE.research.get(sym);
      if (!r) loadResearch(sym);
      html = researchDossier({ sym, d: r?.data, notes: LIVE.rnotes.get(sym) || [], asking: LIVE.asking.has(sym), speechIn: !!SR, listening: !!S.rec });
      title = r?.data?.name ? `${r.data.name} research` : "Research";
    }
    title = title === "Briefing" ? "Research" : title;
  } else {
    const fixtures = COMPANIES.filter((c) => c.fixture);
    const symbol = fixtures.some((c) => c.symbol === params.get("c")) ? params.get("c") : "FX-TUBES";
    const examples = (RESEARCH[symbol] || []).map((n) => n.q);
    html = researchView({ companies: fixtures, symbol, notes: S.notes, examples, speechOk, speakingId: S.speaking });
    title = "Research";
  }

  main.innerHTML = html;
  document.title = `${title} · FINN`;
  setNav(navTop);
  drawCharts();
  if (top === "portfolio" && S.search.results) { const box = $("#search-results"); if (box) box.innerHTML = searchHtml(); }

  const key = location.hash.split("?")[0] + (wide.matches ? "w" : "n");
  if (key !== lastRouteKey) {
    const within = wide.matches && lastRouteKey.startsWith("#/briefing") && key.startsWith("#/briefing");
    if (within) window.scrollTo(0, scrollY);
    else { window.scrollTo(0, 0); if (lastRouteKey) main.focus({ preventScroll: true }); }
    lastRouteKey = key;
  } else window.scrollTo(0, scrollY);
}

function withFixtureResults(i) {
  const d = i.results_ref && DOSSIERS[i.results_ref];
  if (!d) return i;
  const n = d.quarters.length - 1;
  const names = { revenue: "Revenue", ebitda: "EBITDA", pbt: "PBT", pat: "PAT" };
  return { ...i, resultsBlock: {
    periods: [d.quarters[n], d.quarters[n - 1], d.quarters[n - 4]], basis: "consolidated (demo)", unit: "₹ crore", notes: [],
    rows: periodTable(d.q, d.quarters).map((r) => ({ metric: names[r.key], value: r.value, qoq: r.qoq, yoy: r.yoy })),
    source: { source_class: "STANDARDIZED_TABLE", source_name: d.q_source, locator: d.quarters[n], fixture: true },
  } };
}

// ---------- stock search (Portfolio search box: view only; Add sheet: add) ----------
const haveSymbols = () => new Set([...(LIVE.holdings?.holdings || []), ...(LIVE.holdings?.watchlist || [])].map((c) => c.symbol));
const addRole = () => (S.ptab === "watch" ? "research" : "holding");
const searchHtml = () => searchResults(S.search.results, S.search.note, haveSymbols(), "view");
const addHtml = () => searchResults(S.add.results, S.add.note, haveSymbols(), "add", addRole());
const searchers = {};
function makeSearch(state, boxId, html) {
  let timer = null, seq = 0;
  return (q) => {
    state.q = q;
    clearTimeout(timer);
    const box = () => document.getElementById(boxId);
    if (q.trim().length < 2) { state.results = null; if (box()) box().innerHTML = boxId === "add-results" ? `<p class="note">Type at least two letters.</p>` : ""; return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      if (box()) box().innerHTML = `<p class="note">Searching…</p>`;
      try {
        const r = await searchStocks(q.trim());
        if (mine !== seq) return;                 // a newer query is in flight: drop this answer
        state.results = r.results; state.note = r.note;
      } catch (e) { if (mine !== seq) return; state.results = []; state.note = `Search failed: ${e.message}`; }
      if (box()) box().innerHTML = html();
    }, 300);
  };
}
searchers["stock-search"] = makeSearch(S.search, "search-results", searchHtml);
searchers["add-search"] = makeSearch(S.add, "add-results", addHtml);
searchers["research-search"] = makeSearch(S.rsearch, "research-results", () => researchResults(S.rsearch.results, S.rsearch.note));

// ---------- charts ----------
function drawCharts() {
  main.querySelectorAll(".chart[data-chart]").forEach((el) => {
    const def = registry.charts.get(el.dataset.chart);
    if (!def) return;
    const width = Math.floor(el.clientWidth), s = def.spec;
    if (def.kind === "bar") el.innerHTML = barChart({ width, labels: s.labels, values: s.values, fmt: (v) => crShort(v), tipFmt: (v) => `₹${crShort(v)} crore`, label: s.label });
    if (def.kind === "line") el.innerHTML = lineChart({ width, labels: s.labels, values: s.values, fmt: (v) => pctv(v), tipFmt: (v) => pctv(v, 2), label: s.label });
    if (def.kind === "grouped") el.innerHTML = groupedBars({ width, labels: s.labels, a: s.a, b: s.b, names: s.names, fmt: (v) => crShort(v), tipFmt: (v) => `₹${crShort(v)} cr`, label: s.label });
    if (def.kind === "strip") el.innerHTML = rangeStrip({ width, band: s.band, actual: s.actual, scale: s.scale, fmt: unitFmt(s.unit), label: s.label });
    if (def.kind === "spark") el.innerHTML = sparkline({ width, values: s.values, labels: s.labels, label: s.label });
  });
}
let lastW = 0;
new ResizeObserver(() => { const w = main.clientWidth; if (Math.abs(w - lastW) > 4) { lastW = w; drawCharts(); } }).observe(main);
wide.addEventListener("change", render);
main.addEventListener("pointermove", (e) => {
  const h = e.target.closest?.(".hit");
  if (!h) { tip.hidden = true; return; }
  tip.textContent = h.dataset.tip; tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = `${Math.min(window.innerWidth - r.width - 8, Math.max(8, e.clientX - r.width / 2))}px`;
  tip.style.top = `${Math.max(8, e.clientY - r.height - 12)}px`;
});
main.addEventListener("pointerleave", () => { tip.hidden = true; });

// ---------- dialogs ----------
let opener = null, openedAt = 0;
function openDialog(html) {
  opener = document.activeElement; openedAt = Date.now();
  dlgBody.innerHTML = html;
  dlg.showModal();
  dlg.querySelector("[autofocus], input, .dlg-close")?.focus();
}
dlg.addEventListener("close", () => { opener?.focus?.(); });
// A tap on the backdrop closes the sheet, but not the second tap of a double-tap that opened it.
dlg.addEventListener("click", (e) => { if (e.target === dlg && Date.now() - openedAt > 400) dlg.close(); });
$(".dlg-close").addEventListener("click", () => dlg.close());


// ---------- speech ----------
function speak(text, id) {
  if (!speechOk) return;
  speechSynthesis.cancel();
  if (S.speaking === id) { S.speaking = null; render(); return; }
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-IN"; u.rate = 1;
  u.onend = u.onerror = () => { if (S.speaking === id) { S.speaking = null; render(); } };
  S.speaking = id; render();
  speechSynthesis.speak(u);
}
function stopSpeech() { if (speechOk && S.speaking) { speechSynthesis.cancel(); S.speaking = null; } }

// ---------- research (prepared examples until Pull is built) ----------
function ask(q, symbol) {
  const company = COMPANIES.find((c) => c.symbol === symbol);
  const hit = (RESEARCH[symbol] || []).find((n) => n.q.toLowerCase() === q.trim().toLowerCase());
  const id = `n${Date.now().toString(36)}${S.notes.length}`;
  S.notes.unshift({ id, q: hit ? hit.q : q.trim(), company: company.name, symbol, answer: hit || null });
  render();
  document.getElementById(id)?.scrollIntoView({ block: "start" });
}
const noteText = (n) => `${n.q}. Findings: ${n.answer.findings.map((f) => f.text).join(" ")} What it may mean: ${n.answer.implication} Uncertainty: ${n.answer.uncertainty}`;

// Research section tabs follow the reader: the tab of the section at the top of the screen is selected.
function markSection(id) {
  document.querySelectorAll(".r-nav [data-jump]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.jump === id)));
  document.querySelector(`.r-nav [data-jump="${id}"]`)?.scrollIntoView({ inline: "nearest", block: "nearest" });
}
let spyTick = 0;
window.addEventListener("scroll", () => {
  if (spyTick) return;
  spyTick = requestAnimationFrame(() => {
    spyTick = 0;
    const tabs = [...document.querySelectorAll(".r-nav [data-jump]")];
    if (!tabs.length) return;
    const line = 160;
    let cur = tabs[0].dataset.jump;
    for (const t of tabs) { const el = document.getElementById(t.dataset.jump); if (el && el.getBoundingClientRect().top <= line) cur = t.dataset.jump; }
    const now = document.querySelector('.r-nav [aria-pressed="true"]')?.dataset.jump;
    if (now !== cur) markSection(cur);
  });
}, { passive: true });

// ---------- events ----------
// Ghost-tap guard: when a tap opens another screen, a second tap that follows within 350 ms would land on whatever
// is now under the finger (often the bottom nav). Such taps are ignored. Only taps that navigate start the guard.
let navAt = 0;
document.addEventListener("click", (e) => {
  const el = e.target.closest("a, button");
  if (!el || e.target.closest("dialog")) return;
  if (Date.now() - navAt < 350) { e.preventDefault(); e.stopImmediatePropagation(); return; }
  if (el.matches('a[href^="#/"]')) navAt = Date.now();
}, true);
// A route change that wasn't caused by that tap (typed URL, back button, programmatic) ends the guard.
window.addEventListener("hashchange", () => { if (Date.now() - navAt > 80) navAt = 0; }, true);
document.addEventListener("click", async (e) => {
  const t = e.target.closest("button, a");
  if (!t) return;
  const ds = t.dataset;
  if (ds.ev) { const ev = registry.ev.get(ds.ev); if (ev && !dlg.open) openDialog(evidenceBody(ev)); return; }
  if (ds.window) { const { parts } = parse(); stopSpeech(); go(`#/briefing${parts[1] === "item" ? "/" + parts.slice(1).join("/") : ""}?w=${ds.window}`); return; }
  if (ds.filter) { S.filter = ds.filter; render(); return; }
  if (ds.more) { if (S.expanded.has(ds.more)) S.expanded.delete(ds.more); else S.expanded.add(ds.more); render(); return; }
  if (ds.jump) { markSection(ds.jump); document.getElementById(ds.jump)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); return; }
  if (ds.rq) { const sym = currentResearch(); if (sym) askQuestion(sym, ds.rq); return; }
  if (ds.ptab) { S.ptab = ds.ptab; S.selected.clear(); render(); return; }
  if (ds.ask) { const sym = $("#rco").value; ask(RESEARCH[sym][+ds.ask].q, sym); return; }
  if (ds.askText) { ask(ds.askText, $("#rco").value); return; }
  if (ds.add) {
    document.querySelectorAll(`[data-add="${CSS.escape(ds.add)}"]`).forEach((b) => { b.disabled = true; });
    await once(`add:${ds.add}`, async () => {
      try {
        const r = await addHolding({ symbol: ds.add, name: ds.name, sector: ds.sector || null, role: ds.role });
        showToast(`${r.added.name} added to your ${ds.role === "research" ? "watchlist" : "holdings"}. Fetching its prices, news and fundamentals…`);
        if (dlg.open) { const b = document.getElementById("add-results"); if (b) b.innerHTML = addHtml(); }
        invalidate(); await loadHoldings();
        if (dlg.open) { const b = document.getElementById("add-results"); if (b) b.innerHTML = addHtml(); }
        if (r.refreshing) setTimeout(() => { invalidate(); render(); }, 15000);   // anything still loading
        else { invalidate(); render(); }
      } catch (err) {
        showToast(`Couldn't add: ${err.message}`);
        document.querySelectorAll(`[data-add="${CSS.escape(ds.add)}"]`).forEach((b) => { b.disabled = false; });
      }
    });
    return;
  }
  switch (ds.act) {
    case "listen": { const { sections, routine, winLabel } = S.lastBriefing; speak(sectionSpeech(sections, routine.length, winLabel), "brief"); break; }
    case "speak-note": { const n = S.notes.find((x) => x.id === ds.id); if (n) speak(noteText(n), n.id); break; }
    case "routine": S.routineOpen = !S.routineOpen; render(); break;
    case "done": S.marks.done[ds.id] = true; store.set("marks", S.marks); afterMark(ds.id); break;
    case "snooze": S.marks.snoozed[ds.id] = nowMs() + 24 * 3600e3; store.set("marks", S.marks); afterMark(ds.id); break;
    case "refresh": if (!LIVE.refreshing) runRefresh(); break;
    case "retry-live": LIVE.error = null; render(); break;
    case "restore": S.marks = { done: {}, snoozed: {} }; store.set("marks", S.marks); render(); break;
    case "open-settings": case "menu": if (dlg.open) break; openDialog(settingsBody({ settings: S.settings, holdings: [] })); break;
    case "about-data": if (dlg.open) break; openDialog(aboutDataBody({ disclosures: LIVE.digest?.disclosures || ["Demo data: invented companies and documents, apart from four real Infosys filing links."], sources: LIVE.digest?.sources || [] })); break;
    case "reset-settings": S.settings = structuredClone(DEFAULT_SETTINGS); store.set("settings", S.settings); dlg.close(); invalidate(); render(); break;
    case "edit-portfolio": S.editing = !S.editing; S.selected.clear(); render(); break;
    case "close-dlg": dlg.close(); break;
    case "r-rebuild": { const sym = currentResearch(); if (sym) { LIVE.research.delete(sym); loadResearch(sym, true); } break; }
    case "mic": listen(); break;
    case "r-clear": { const sym = currentResearch(); if (sym) { LIVE.rnotes.delete(sym); render(); } break; }
    case "select-stock": if (S.selected.has(ds.symbol)) S.selected.delete(ds.symbol); else S.selected.add(ds.symbol); render(); break;
    case "open-add": if (dlg.open) break; S.add = { q: "", results: null, note: null }; searchers["add-search"] = makeSearch(S.add, "add-results", addHtml);
searchers["research-search"] = makeSearch(S.rsearch, "research-results", () => researchResults(S.rsearch.results, S.rsearch.note)); openDialog(addSheet(addRole(), "")); break;
    case "delete-selected": {
      const syms = [...S.selected];
      if (!syms.length) break;
      if (!confirmDelete(t, syms.length)) break;
      t.disabled = true;
      await once("delete", async () => {
        const failed = [];
        for (const sym of syms) { try { await removeHolding(sym); } catch { failed.push(sym); } }
        S.selected = new Set(failed);
        showToast(failed.length ? `Couldn't delete ${failed.join(", ")}.` : `Deleted ${syms.length} stock${syms.length > 1 ? "s" : ""}.`);
        invalidate(); await loadHoldings();
      });
      break;
    }
  }
});
// Deleting is reversible (Add again), so a second tap on the same button confirms.
function confirmDelete(btn, n) {
  if (btn.dataset.armed === "1") return true;
  btn.dataset.armed = "1"; btn.lastChild.textContent = `Tap again to delete ${n}`;
  setTimeout(() => { if (btn.isConnected && btn.dataset.armed === "1") { btn.dataset.armed = ""; render(); } }, 4000);
  return false;
}
function afterMark(id) {
  const { parts } = parse();
  if (parts[1] === "item") go("#/briefing" + (location.hash.includes("?") ? "?" + location.hash.split("?")[1] : ""));
  else render();
  void id;
}

document.addEventListener("submit", (e) => {
  const f = e.target;
  if (f.dataset.form === "settings") {
    e.preventDefault();
    const fd = new FormData(f), on = new Set(fd.getAll("cat"));
    S.settings = { price_pct: +fd.get("price_pct"), vol_mult: +fd.get("vol_mult"),
      categories: Object.fromEntries(Object.keys(DEFAULT_SETTINGS.categories).map((k) => [k, on.has(k)])) };
    store.set("settings", S.settings);
    dlg.close(); LIVE.holdings = null; render();
  } else if (f.dataset.form === "rask") {
    e.preventDefault();
    const sym = currentResearch(), q = String(new FormData(f).get("q") || "");
    if (sym && q.trim()) { f.reset(); askQuestion(sym, q); }
  } else if (f.dataset.form === "ask") {
    e.preventDefault();
    const q = new FormData(f).get("q");
    if (String(q).trim()) ask(String(q), $("#rco").value);
  }
});
document.addEventListener("input", (e) => { const f = searchers[e.target.id]; if (f) f(e.target.value); });
document.addEventListener("change", (e) => { if (e.target.id === "rco") { stopSpeech(); go(`#/research?c=${encodeURIComponent(e.target.value)}`); } });
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && e.target.id === "rq") { e.preventDefault(); e.target.form.requestSubmit(); }
});
window.addEventListener("hashchange", () => { stopListening(); if (S.speaking === "brief" && !location.hash.startsWith("#/briefing")) stopSpeech(); S.editing = false; S.selected.clear(); render(); });

async function boot() {
  const h = await detectApi();
  const banner = $("#banner");
  if (h) {
    LIVE.on = true; LIVE.mode = h.mode; LIVE.health = h;
    if (h.mode === "live") { banner.hidden = true; }
    else banner.innerHTML = "<b>Demo mode.</b> The server is running on invented companies and data. Not investment advice.";
  }
  render();
  if (h && h.mode === "live") refreshIfStale(h);
}
boot();

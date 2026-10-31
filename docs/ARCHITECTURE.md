# FINN — Architecture (initial proposal)

> Status: **proposal, not implemented**. Updated 2026-10-30 after the user's clarifications (REQUIREMENTS §8). Choices marked ⚠ depend on Phase-1 spikes (see `IMPLEMENTATION_PLAN.md`).

## 1. Principles
1. **Deterministic where possible, LLM where necessary.** Classification starts with rules. Numbers are parsed and computed in code. LLMs extract and write prose; they never produce a number that isn't in the source.
2. **Citations are data, not decoration.** Every generated claim is `{text, citations[]}`, and a validator drops any claim whose quote isn't found on the cited page.
3. **Cache everything by content hash.** Documents, parses, extractions and LLM outputs are all cached, so re-running costs ~0.
4. **Degrade honestly.** Missing data produces an explicit empty state, never a fabricated fill.
5. **Live by default, honest fallback.** Real data for any ticker is the normal path (R-30). A labelled snapshot is served only when a live source fails.
6. **Free tiers only** (R-35). Every external dependency has a no-card free tier, and the app degrades gracefully when a quota is hit.

## 2. System overview

```
                 ┌───────────────────────────── web/ (Next.js + TS, PWA) ─────────────────────────────┐
  Phone browser ─┤  Brief · Alerts · Research dossier · Evidence sheet · Settings                     │
                 └───────────────▲────────────────────────────────────────────────────────────────────┘
                                 │ JSON (typed; OpenAPI → generated TS types)
                 ┌───────────────┴──────────────────── backend/ (Python, FastAPI) ────────────────────┐
                 │ api/        REST: /digest /alerts /announcements/{id} /research/{ticker} /settings  │
                 │ push/       classify → score/tier → alert rules → card enrichers                   │
                 │ extract/    results (XBRL→PDF fallback) · mgmt profile · one-line summaries        │
                 │ research/   doc fetch → parse (page-aware) → chunk → retrieve (BM25) → sections    │
                 │             metrics (pure functions) · guidance extraction · promises ledger       │
                 │ llm/        routes fast|long × slots primary|fallback · quota · cache · log        │
                 │ sources/    nse_rss · bse_rss · prices (nse_udiff | upstox) · company_site · tavily│
                 │ store/      SQLite = rebuildable cache (ephemeral) · seed/ · seed_cache/ (committed)│
                 └───────────────▲────────────────────────────────────────────────────────────────────┘
                                 │ scheduled + on-demand
                 ┌───────────────┴───────────┐
                 │ jobs/ (CLI: finn ingest …) │  prices EOD · announcements poll · fundamentals on demand
                 └───────────────────────────┘
```

### Why this split
- **Python backend**: the best ecosystem for this work. feedparser/lxml for RSS and XBRL, PyMuPDF/pdfplumber for page-aware PDF text, lxml for XBRL, rank-bm25, pandas.
- **Next.js frontend**: fast to make mobile-first and installable as a PWA, and deploys on a free tier.
- **Alternative considered**: an all-TypeScript Next.js app. It was rejected because heavy PDF parsing and long LLM jobs fit poorly with serverless time limits, and Python's PDF and XBRL tooling is stronger. (DECISIONS D-02)

## 3. Deployment topology (decided: user Q-2)
| Piece | Where | Free-tier facts that shape the design (RESEARCH R10–R13) |
|---|---|---|
| Web (Next.js PWA) | **Vercel** (Hobby) | Static plus edge, so it opens instantly even while the API is waking up |
| API + jobs (FastAPI) | **Render free web service** | **Official** (render.com/docs/free): spins down after 15 min without inbound traffic; ~1 min to spin up; 750 free instance-hours per workspace per month (spun-down time doesn't count); **ephemeral filesystem** (local files and SQLite are lost on spin-down, restart or redeploy; free services cannot attach a persistent disk); Render **may suspend** a free service that initiates uncommonly high outbound traffic |
| Keep-warm + **RSS poller** | **GitHub Actions cron** (public repo: no billable minutes) | Every ~10 min, off the hour: pings `/health` and polls the official NSE/BSE RSS feeds, appending **metadata only** to a `data` branch (D-33, D-37). **Official** (GitHub docs): 5-min minimum; runs can be delayed or dropped, so the NSE announcements feed (~1 h window, R26) can be missed under load. Gaps are detected (pubDate discontinuity) and shown in the UI, never hidden |
| Storage | See **§4b Storage & restart behaviour** | Nothing on the server is assumed to persist |
| LLMs | **Gemini API (Flash family) + Groq**, free tiers | See §6 |
| People search | **Tavily** free Researcher plan | **Official**: 1,000 API credits/month, no card, basic search = 1 credit, credits reset on the 1st of each month; development keys allow 100 requests/min. Used only for Must-tier management changes |

**Cold-start UX.** If the API is asleep, the web app shows "Waking FINN's server, about a minute" with live progress, never a blank screen. Keep-warm makes this less frequent but cannot rule it out (scheduled runs are best effort).

**Outbound-traffic budget (Render suspension risk).** Each ticker fetches at most the latest AR plus 5 transcripts. PDFs are streamed to text and the binary is discarded. Ingestion is idempotent and skips unchanged documents (ETag/hash), and the committed seed cache (§4b) means demo tickers don't re-download on every boot. Downloaded bytes are logged per day so the risk is visible.

**Vercel Hobby note.** Vercel's docs restrict Hobby to non-commercial personal use. We treat a hiring-challenge prototype as personal use; flagged for the owner in README "Still open".

**Gate G1 check.** The RSS feeds, the chosen price source (D-36) and company IR pages for the demo set must be reachable **from GitHub Actions and Render**, not just the build sandbox. No exchange-website endpoints are used (D-32), so there is no website-automation fallback. If a feed is unreachable, the affected feature degrades with a visible notice.

## 4. Data model (typed; initial)
```
Company(symbol PK, name, isin, bse_code?, sector, is_lender: bool, in_portfolio: bool)
PriceBar(symbol, date, open, high, low, close, volume, source)            PK(symbol,date)
Announcement(id PK = exchange+seq_id, symbol, exchange, ts_ist, raw_subject, raw_text,
             attachment_url, xbrl_url?, category, category_source: rule|llm, confidence,
             score, tier: must|glance|routine, one_liner?, enrichment_json?)
AlertRule{scope: global|symbol, symbol?, kind: price_pct|volume_mult|category, params}   # client-held, sent with requests (§4b)
AlertEvent{key = hash(rule, symbol, date|announcement_id), symbol, ts, rule, observed}    # computed on read, not stored; read/unread lives on the client
Document(id = sha256, symbol, kind: annual_report|transcript|results|presentation, period, url, fetched_at, pages)
Chunk(id, doc_id, page, start, end, text, section_hint)
SourceClass = PRIMARY_DOC | STANDARDIZED_TABLE | DERIVED | MARKET_DATA | EXTERNAL_WEB     (see §4a)
Provenance{source_class, source_name, url, retrieved_at, locator, doc_hash?, formula?, inputs?: Provenance[]}
   # locator = "p.37" for documents, "quarters:Sales:Jun 2026" for tables, "xbrl:RevenueFromOperations:Q2FY27" for XBRL
Metric{name, value, unit, period, basis: consolidated|standalone, provenance: Provenance}
Citation{doc_id, page, quote, url, source_class = PRIMARY_DOC}   # quote-bearing; only primary documents
Claim{text, kind: narrative|numeric, citations: Citation[], metric_refs: Metric.id[]}
   # narrative claims need ≥1 Citation (PRIMARY_DOC); numeric claims need ≥1 Citation or metric_ref
GuidanceItem(id, symbol, made_in_period, metric, target_low?, target_high?, unit, horizon, quote, citation)
LedgerRow(guidance_id, actual: Metric?, crosscheck: Metric?, verdict, note)   # promise side is always a PRIMARY_DOC Citation
LlmCall(id, route: fast|long, slot: primary|fallback, provider, model, purpose, input_hash, prompt_version,
        tokens_in, tokens_out, status: ok|rate_limited|error, cached: bool)
```
The Pydantic models are the single source of truth. The frontend types are generated from OpenAPI, so they are never hand-copied.

## 4a. Source provenance & the primary-source boundary
The brief requires Pull to be grounded in primary sources (R-19). The owner has also explicitly allowed screener.in standardised tables for numbers (Q-7, D-19). These rules keep the two from blurring:

| Source class | Examples | Allowed in Push | Allowed in Pull | What it may support |
|---|---|---|---|---|
| `PRIMARY_DOC` | Annual reports, concall transcripts, exchange filings, results PDF/XBRL | ✅ | ✅ | **Narrative and numeric** claims (quote-verified) |
| `STANDARDIZED_TABLE` | Tables **derived from filings** (D-35 option A), or screener.in tables **only if** the owner chooses D-35 option B | ✅ | ✅ **numbers only** | **Numeric values only.** It can never be the citation for a narrative claim (strategy, guidance, reasons, tone), and it can never be the "promised" side of the ledger |
| `DERIVED` | QoQ/YoY %, margins, D/E, CFO/PAT, EBITDA | ✅ | ✅ | A number computed in code. It carries `formula` and the provenance of every input; its effective class is the weakest input class |
| `MARKET_DATA` | EOD prices and volume from the D-36 source (yfinance first per D-38; NSE UDiFF bhavcopy fallback planned) | ✅ | ❌ | Push alerts only |
| `EXTERNAL_WEB` | News headlines via RSS (D-51); Tavily results (planned) | ✅ news headlines and people background | ❌ **never** | Push only, always labelled "News · Publisher" or "web"; headline + link only |

Enforcement (each is tested, EVALUATION §3, R-19/R-36):
1. **Context builder.** The Pull/Ask prompt context is built only from `PRIMARY_DOC` chunks and `Metric`s whose class is `PRIMARY_DOC`, `STANDARDIZED_TABLE` or `DERIVED`. `MARKET_DATA` and `EXTERNAL_WEB` objects are rejected by type.
2. **Claim validator.** `narrative` claims with no valid `PRIMARY_DOC` citation are dropped. `numeric` claims must match a provided `Metric` (number guard) or a quoted number.
3. **Ledger.** Promised = transcript quote (`PRIMARY_DOC`). Delivered = a `Metric`: primary results XBRL if parsed, otherwise the screener table, labelled. If both exist and differ by more than 1% (after unit normalisation), the cell shows both and a ⚠ "sources differ" note; neither is silently preferred.
4. **API and UI.** Every number the API returns carries its `provenance`. The UI shows a source tag ("Filing p.37", "screener.in table", "Derived: formula") and the evidence sheet shows the full chain.
5. **Labels never collapse.** Summaries, caching and serialisation must keep provenance intact. A cached Claim without its citations is treated as invalid.

## 4b. Storage & restart behaviour (Render free = ephemeral filesystem)
Official Render behaviour: local files, including SQLite, are lost on every spin-down, restart and redeploy, and free services cannot attach a persistent disk. Keep-warm reduces spin-downs but does not prevent restarts or redeploys. **So the server keeps no state that matters, and every server-side item is either committed, re-derivable, or acceptable to lose.**

| Data | Lives in | Survives server spin-down/restart/redeploy? | Survives a browser/device change? | Notes |
|---|---|---|---|---|
| Portfolio (18) + research list (4) | `config/portfolio.yaml` in the repo | ✅ (committed) | ✅ | **Read-only in the MVP UI.** Changing it is a config change (no portfolio editing; scope not broadened) |
| Default alert thresholds & categories | `config/alerts.yaml` + env | ✅ | ✅ | |
| User threshold overrides, category toggles | Browser `localStorage`, sent with `/alerts` and `/digest` requests | ✅ (not on server) | ❌ (per device) | Server stays stateless; overrides travel with the request |
| Alert events | Computed on read from bars, announcements and the request's rules | ✅ (re-derived) | ✅ | Deterministic: same data + rules = same alerts |
| Alert read/unread, swipe done/snoozed | Browser `localStorage`, keyed by stable `AlertEvent.key` / announcement id | ✅ | ❌ (per device) | Wrapped in try/catch; private mode loses it, and the UI still works |
| **Announcement metadata log** (time, company, symbol, subject, attachment URL, our category/tier) | `data` branch, JSON Lines, appended by the GitHub Actions poller (D-37) | ✅ (in Git) | — | Metadata + links only (D-31). Gaps recorded. This is the digest's history; it starts at the first poll |
| Price bars, announcements, classifications, tiers | SQLite on the ephemeral disk | ❌ → rebuilt at boot (seed + catch-up ingest) | — | Boot time measured in S7; UI shows "Refreshing data…" during catch-up |
| Seed snapshot (last good bars/announcements) | `data/seed/` committed (demo bootstrap), with an `as_of` stamp; **metadata only** (id, date, title, URL, category) plus our own bars-derived figures (D-31) | ✅ | — | Used for boot speed and as the per-source fallback (banner shown) |
| Downloaded PDFs / XBRL | Ephemeral cache | ❌ → re-fetched on demand | — | Watch the outbound-traffic budget (§3) |
| LLM outputs: demo tickers (22) | `data/seed_cache/` committed **FINN-derived** JSON (claims, short cited quotes ≤ 1 sentence + deep links, prompt_version, doc_hash); no raw document text (D-31) | ✅ | — | Produced by `scripts/build_seed_cache.py`. Protects free quotas and makes the demo reproducible |
| LLM outputs: unseen tickers | Ephemeral cache | ❌ (recomputed on the next request, costing quota) | — | Accepted trade-off; stated in the writeup |
| Tavily results | Ephemeral, plus seed for demo-set appointees | demo ✅ / others ❌ | — | |
| LLM quota counters | In-memory | ❌ → reset on restart; provider 429/headers remain the source of truth | — | §6 |
| Call log (debug drawer) | In-memory ring buffer | ❌ | — | |

**Repository content policy (D-31, APPROVED).** The repo, including the `data` branch, `data/seed*` and test fixtures, may contain only:
- **Metadata:** time, company, symbol, subject, category, and the source URL.
- **FINN-derived outputs:** computed metrics with provenance, claims, and short cited quotes of at most one sentence with deep links.
- **Synthetic test documents** that we write ourselves.

It must **never** contain filing PDFs, full document text, raw exchange datasets (e.g. bhavcopy files), screener tables, or secrets. A CI check enforces this (`test_seed_content_policy`, `test_fixture_content_policy`). Reproducibility comes from documented live access plus synthetic fixtures, not from copies of third-party data.

**Durable server-side storage is not used in the MVP.** Render's free Postgres is official but expires after 30 days (with a 14-day grace period). Adopting it, or any other hosted DB, needs the owner's approval and a DECISIONS entry.

## 5. Pipelines

### 5.1 Push: classify → score → tier → enrich
1. **Classify** (rules first). Rules read **both** the subject/category **and** the free-text description (D-29). In the RSS feed that means the `|SUBJECT:` part of `description` plus the sentence before it; results arrive as "Outcome of Board Meeting" and transcripts as generic updates. XBRL links in the Integrated-Filing feed mark results filings. Patterns such as "Financial Results", "Earnings Call Transcript", "Change in Directors/KMP", "Credit Rating" map to REF categories through a rule table plus keyword regexes. The `fast` LLM route is used only when rules give `unclassified` with low confidence, and the result is cached by announcement id.
2. **Score** = category base weight + modifiers. Weights below are **initial guesses to tune** against a hand-labelled sample (EVALUATION §2):

| Category | Base | Treatment |
|---|---|---|
| results | 90 | Must · results card (P-3) |
| M&A | 85 | Must · one-liner (counterparty, size if stated) |
| management_change | 80 (CEO/CFO/MD +10; independent director −30) | Must/Glance · mgmt card (P-4) |
| fund_raise | 75 | Must · one-liner (instrument, amount) |
| litigation | 70 | Glance→Must if a regulator or fine is stated · one-liner |
| credit_rating | 60 (downgrade +25, reaffirm −30) | one-liner |
| pledging | 65 | one-liner (% pledged change) |
| capex | 60 | one-liner (amount, capacity) |
| insider_trading | 50 | one-liner (who, buy/sell, value) |
| bonus_split | 45 | one-liner (ratio, record date) |
| dividend | 35 | filing only (amount, record date in title) |
| press_release | 35 | one-liner |
| earnings_call | 25 | Routine, but a transcript triggers Pull doc refresh |
| investor_meetings, agm_egm, postal_ballot | 10–15 | Routine |
| unclassified | 5 | Routine |

   Modifiers: same-day price/volume alert on the ticker (+15); a duplicate across NSE and BSE is collapsed into one item.
3. **Tier**: ≥ 75 Must · 40–74 Glance · < 40 Routine. Cut-offs are configurable.
4. **Enrich** only Must and Glance items (saves cost): results extractor, mgmt profile extractor, one-liner (Groq, from the filing's text only).

### 5.2 Results extraction (P-3)
1. **XBRL path ⚠** (Spike S4): parse the Integrated Filing–Financial XBRL. Map tags for revenue from operations, other income, finance costs, D&A, PBT and PAT, consolidated if present. The current quarter, previous quarter and year-ago quarter columns are usually all in the same filing.
2. **PDF fallback**: extract the results table with pdfplumber. The `fast` route maps rows to fields and returns **row labels plus raw strings**. Code then parses the numbers and the units (₹ lakh / crore / million).
3. **Validation gates** (any failure → "couldn't verify"):
   - PBT − tax ≈ PAT (±1% or ±1 unit of rounding).
   - Every number appears verbatim in the source text.
   - The units are detected.
4. EBITDA = PBT + finance costs + D&A − other income. **Derived, labelled, with the formula shown.** For lenders it is `null` with reason "n/m".

### 5.3 Management profile (P-4)
Find the Reg-30 annexure rows ("Brief profile", "Reason for change", "Date of appointment"). Extract them with the `fast` route, constrained to a JSON schema and verbatim quotes, then verify the quotes are in the text.
**Web enrichment (user Q-8, on by default):** one Tavily basic search (`"<name>" <role> <company>`, 1 credit). The `fast` route then summarises **only the returned snippets** into two or three background facts, each linked to its result URL, and stores them separately as `external`. The UI shows them under "Public background (web)", visually distinct from the filing profile. Results are cached per (person, company). If the Tavily quota is exhausted, the card shows the filing profile only.

### 5.4 Pull: research dossier
1. **Discover documents** (D-34), in order: (a) the **company website** (SEBI Reg 46 mandates results, the full annual report and transcripts there; URLs for the 22 demo companies are curated in `config/ir_sources.yaml`, each verified by the owner); (b) **exchange RSS attachments** for filings published since polling began; (c) for unseen tickers, **Tavily search restricted to the company's own domain**, otherwise an honest "documents not found". screener.in is a link-out only. Standardised tables follow D-35 (unresolved). Every document keeps its original URL. Respect robots.txt. Aim for latest 1–2 ARs and latest 5 transcripts.
2. **Fetch and parse** the PDFs page-aware (PyMuPDF). Store `Document` and `Chunk` (≈800–1200 tokens, page boundaries kept). Cache by sha256.
3. **Metrics** (pure Python): growth, margins, D/E, CFO/PAT, working-capital days. Each value is a `Metric` with full `Provenance` (§4a). Screener inputs are `STANDARDIZED_TABLE`; outputs are `DERIVED` with their inputs listed.
4. **Retrieve**: BM25 over the chunks plus section heuristics (e.g. the AR's "Management Discussion"). There is **no vector DB in the MVP** (DECISIONS D-05).
5. **Guidance extraction** (Gemini, long context, per transcript, cached): a JSON list of `GuidanceItem` with verbatim quotes, quote-verified.
6. **Promises Ledger** (code): match each guidance item's metric and horizon to actuals from the quarterly tables. The verdict rules are deterministic, e.g. `actual ≥ low` → Delivered, within 10% short → Partly delivered, further short → Missed; period not ended → Not yet measurable; no disclosed figure → Insufficient evidence. Qualitative statements get a directional check only, never an invented numeric target (D-42). Gemini writes only the 2–3 sentence synthesis, from the ledger rows it is given.
7. **Sections** (business snapshot; one-line reads on financials and balance sheet/cash): the `long` route gets **only the context builder's output** (allowed source classes, §4a: primary chunks and sourced metrics). The system prompt forbids outside knowledge, and the output is a `Claim[]` schema. (Bull vs Bear is out of scope, Q-10.)
8. **Citation validator**: normalise whitespace and case, then check that each `quote` ⊂ `chunk(page).text`. A claim with no valid citation is dropped, and the drop count is logged and shown in debug.
9. **Number guard**: any number in generated prose must equal a provided metric (after rounding) or appear inside a cited quote. Otherwise the claim is dropped.

### 5.5 Ask box (R-31)
`POST /research/{ticker}/ask {question}`. The pipeline:
1. Make sure the company's documents are ingested (they reuse the §5.4 cache).
2. BM25 retrieval, top-k chunks, plus the relevant computed metrics.
3. The `long` route with the Claim schema and the primary-sources-only system prompt; context comes from the §4a context builder.
4. Citation validator, then number guard.
5. Render.

If zero claims survive, the reply is "Not answered in this company's filings." There is no fallback to general knowledge. Limits: 10 questions per company per session. Answers are cached by (doc-set hash, normalised question).

### 5.6 Swipe triage & voice briefing (frontend only)
- **Triage state** (`done`, `snoozed_until`) is kept per announcement. In the MVP it lives in browser storage (single user, wrapped in try/catch); syncing it server-side is a later step.
- **Voice**: the Web Speech API (`speechSynthesis`) reads a script assembled in code from the Brief's card fields. **No LLM call and no new claims.** If the browser has no voice, the button is hidden. Implemented behind a `SpeechOutput` adapter (§6.4); browser `speechSynthesis` is the default (Baseline, no key). Server TTS (e.g. Gemini Flash-Lite TTS, free tier) is an optional adapter, off by default. Speech **input** is out of scope.

### 5.7 Alerts engine
Alerts are **computed on read** (§4b): `/alerts` receives the device's rules (global plus per-ticker overrides and category toggles) and evaluates pure functions `evaluate(rule, bars|announcement) → AlertEvent?` over the stored EOD bars and announcements. No server-side alert state; read/unread is on the device, keyed by `AlertEvent.key = hash(rule, symbol, date|announcement_id)`. Pure functions make them trivially unit-testable.

## 6. LLM routing, fallback & quotas (free tiers only: Q-1, R-35)
### 6.1 Routes and slots
There are two **routes**, each with a **primary** and a **fallback** slot. Every slot names **both provider and model**, so a fallback is never ambiguous.

| Route | Used for | Primary slot (default) | Fallback slot (default) | Notes |
|---|---|---|---|---|
| `fast` | Classification fallback, one-liners, mgmt-profile JSON, Tavily snippet summary, results row-mapping | Groq · `<model from S6>` | Google · `<Flash-Lite-class model from S6>` | Short inputs (≤ ~4K tokens), JSON output |
| `long` | Guidance extraction (whole transcript), business snapshot, ledger synthesis, financial/BS reads, Ask box | Google · `<Flash-class model from S6>` | Groq · `<model from S6>` **in reduced mode** | Reduced mode: when the fallback's context or per-minute token limit is smaller, the input is split into page-bounded chunks and the results are merged in code (guidance), or top-k is lowered (Ask/sections). Output schema is unchanged |

- **No model ID is hard-coded or assumed available.** Groq's docs list `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` as "Contact Sales" in its production table, so their free-plan availability is **unverified**. Spike S6 lists models from each key (`GET https://api.groq.com/openai/v1/models`, and the Gemini models-list endpoint), runs one JSON-schema call per chosen slot, and records the result in RESEARCH R14.
- **Config validation at startup.** All four slots must name a provider whose key is set and a model that is non-empty. If a slot is misconfigured, the server starts with that slot disabled and logs a clear error. If both slots of a route are disabled, the features on that route show "Analysis unavailable" (never fabricated output).
- Optional third slot: `LLM_<ROUTE>_FALLBACK2_*` for a second same-provider model (e.g. another Gemini Flash variant). Off by default.

### 6.2 Independent quota handling
Each slot has its **own** quota tracker keyed by `(provider, model)`:
- **Provider signals are the source of truth.** Groq returns `retry-after` and `x-ratelimit-*` headers, documented as requests-per-day and tokens-per-minute (official). Gemini returns HTTP 429 `RESOURCE_EXHAUSTED`; its rate limits are per project and RPD resets at midnight Pacific (official). The exact numbers are shown only in AI Studio, not published.
- **Optional self-imposed budgets** (`LLM_<ROUTE>_<SLOT>_MAX_RPM` / `_MAX_RPD`) let us stop *before* a provider 429. They start **blank** and are set to ~80% of the limits each account's console shows (S6). We never put guessed numbers in config.
- **State machine per slot**: `ok` → (429 with retry-after/RPM) `cooling(until)` → `ok`; (daily exhaustion) `exhausted(until next reset)`. A cooling or exhausted primary sends calls to the fallback slot. The fallback's state is tracked separately, so one provider running out never marks the other as out. Same-provider slots (e.g. two Gemini models) also get separate trackers. Whether quotas are shared across models in one Google project is **unverified**; a third-party forum answer says per-model, and S6 will observe it.
- **Both slots unavailable**: serve the cached result if one exists (with "cached <time>"), otherwise "Analysis paused: free model quota reached; retry after <time>". Never degrade to an unvalidated output.
- **Restart behaviour**: trackers are in memory and reset on restart (§4b). That's safe because the provider's next 429 re-establishes state.

### 6.3 Provider data-use (official, RESEARCH R20)
- **Gemini free tier:** content is used to improve Google products, and human reviewers may read inputs and outputs. Send only public filings and FINN prompts, never user data or secrets.
- **Groq:** no retention of inference data by default. Preferred for anything a user types into the Ask box when the `long` route can fall back to it.

### 6.4 Provider-agnostic adapters (D-26)
Business logic depends only on these typed interfaces. Each provider is one adapter module, selected by config, so swapping providers never touches `push/`, `extract/` or `research/`:
```
LlmProvider.generate(route, prompt, json_schema, slot) -> LlmResult{json, usage, provider, model}
AnnouncementSource.poll(since) -> list[Announcement]                       # nse_rss | nse_json (per-company backfill) | bse  (D-33, D-38)
PriceSource.eod(symbols, from, to) -> list[PriceBar]                       # yfinance | nse_udiff  (D-36, D-38)
DocumentSource.discover(symbol) -> list[DocumentRef]; fetch(ref) -> Document   # exchange | screener_links | company_site  (D-34, D-38)
TableSource.tables(symbol) -> StandardizedTables                           # screener (D-35 = B) | filings_derived (later)
PeopleSearch.lookup(name, role, company) -> list[ExternalSnippet]          # tavily | none  (also: IrDiscovery.find(company) for D-34 (c))
Retriever.search(symbol, query, k) -> list[Chunk]                          # bm25 | embeddings(optional)
SpeechOutput (frontend) .speak(script) / .stop()                           # browser | server_tts(optional)
```
Each adapter has a fixture-backed contract test, so a replacement adapter must pass the same tests before it is enabled.

### 6.5 Other rules
- Every call is logged as an `LlmCall` with route, slot, provider, model, prompt_version and status. The debug drawer shows request counts and tokens (I-9); dollar cost is $0 on free tiers.

## 7. Testing strategy
- **Fixtures**: real responses and documents saved during the spikes (announcement JSON, 3–5 results XBRL/PDFs, 2 appointment filings, 2 transcripts). Tests never hit the network.
- **Unit**: classifier rules, scoring, alert rules, metric functions, EBITDA derivation, XBRL/PDF number parsing and units, citation validator, number guard, verdict rules, **provenance boundary** (context builder, claim validator), **LLM slot config and per-slot quota trackers**, boot rebuild from seed.
- **Golden**: results extraction against hand-checked numbers for 5 filings.
- **Contract**: OpenAPI schema snapshot; generated frontend types compile.
- **E2E smoke** (Playwright, mobile viewport): Brief loads, a card opens, Dig in opens the dossier, and an evidence sheet shows a snippet.

## 8. Security & config
- Secrets live only in env vars. `.env` is gitignored and `.env.example` holds placeholders.
- No secrets are sent to the frontend. Only `NEXT_PUBLIC_*` values are exposed, and none of them are secrets.
- Outbound fetches use a polite User-Agent, rate limiting and backoff, and respect source terms.

## 9. Frontend architecture & component boundaries (D-39)
**Choice:** Next.js (App Router, TypeScript strict) with a **static export** deployed to Vercel, plus Tailwind using the CSS-variable tokens from PRODUCT_SPEC §6. All data comes from the FastAPI service via typed client-side fetches. There are no server components fetching data, because Render can be asleep and the UI must show a waking state. There's no global state library and no UI kit: React state, the URL and a ~40-line `useApi` hook (loading / data / error / stale). This is the simplest stack that meets the PWA, design and Render-cold-start constraints; nothing was added for fashion.

```
web/
  app/                      routes = screens (URL is state, PRODUCT_SPEC §4.2; IA v2 per D-42)
    page.tsx                Briefing (alerts inline; ?w=24h|3d|7d)
    item/[id]/page.tsx      Item detail (desktop: pane beside the list)
    companies/page.tsx, companies/[symbol]/[section]/page.tsx   overview|financials|cash|promises
    research/page.tsx       Research workspace (?c=symbol)
  components/
    shell/      AppShell (bottom nav / rail), Header, PortfolioAlertsDialog, StatusBanner
    briefing/   BriefingHeader, ContextStrip, WindowControl, ListenButton, BriefingRow, RoutineGroup
    results/    ResultsTable, ProfileBlock, AlertCalculation
    company/    CompanyHeader, SectionNav, Overview, Financials, CashDebt, Ledger, LedgerEntry, RangeStrip
    charts/     BarChart, LineChart, GroupedBars (SVG at measured width; prototype: design/prototype/js/charts.js)
    research/   AskForm, ResearchNote, Citation
    evidence/   EvidenceDialog, SourceButton
    common/     EmptyState, Skeleton, Button, Segmented
  lib/
    api.ts      typed fetch client (types generated from OpenAPI → lib/api-types.ts)
    device.ts   localStorage wrapper (thresholds, triage, read state) with try/catch
    speech.ts   SpeechOutput adapter (browser speechSynthesis)
    format.ts   ₹/crore/lakh, signed %, Indian fiscal periods (pure, unit-tested)
  styles/tokens.css   the only place colours, type and spacing are defined
```
**Boundaries:**
- Components never format numbers themselves; they use `lib/format.ts`.
- Components never call `fetch`; they use the `lib/api.ts` hooks.
- Only `lib/device.ts` touches browser storage.
- Presentational components take typed props and are previewable with fixtures (`web/fixtures/*.ts`, all named "Fixture …").

## 10. API data contracts (v1, JSON; Pydantic is the source of truth, TS generated)
All numbers are `Metric` objects with provenance (§4a); all generated text is `Claim`s. Times are ISO-8601 with `+05:30`.

```ts
type SourceClass = "PRIMARY_DOC" | "STANDARDIZED_TABLE" | "DERIVED" | "MARKET_DATA" | "EXTERNAL_WEB";
interface Provenance { source_class: SourceClass; source_name: string; url: string | null;
  retrieved_at: string; locator: string | null; formula?: string; inputs?: Provenance[] }
interface Metric { name: string; value: number | null; unit: "INR_CR" | "PCT" | "PTS" | "X" | "INR_PER_T" | string;
  period: string; basis?: "consolidated" | "standalone"; provenance: Provenance; note?: string }   // value null ⇒ show reason in note
interface Citation { doc_id: string; title: string; page: number | null; quote: string; url: string }
interface Claim { text: string; kind: "narrative" | "numeric"; citations: Citation[]; metric_refs: string[] }
interface SystemState { mode: "live" | "fallback"; stale_sources: { name: string; as_of: string }[];
  quota: { route: "fast" | "long"; status: "ok" | "cooling" | "exhausted"; until?: string }[] }

// GET /v1/digest?window=24h|3d|7d|from&to  (+ device rules in header X-Finn-Rules: base64 JSON)
interface Digest { window: { from: string; to: string }; counts: { must: number; glance: number; routine: number; holdings: number };
  must: ItemSummary[]; glance: ItemSummary[]; routine_breakdown: { subject: string; count: number }[];
  routine: ItemSummary[]; system: SystemState }
interface ItemSummary { id: string; symbol: string; company: string; category: string; tier: "must" | "glance" | "routine";
  published_at: string; title: string; why?: Claim; facts?: Metric[]; source_url: string; exchange: "NSE" | "BSE" }

// GET /v1/items/{id}
interface ItemDetail extends ItemSummary { what_changed: Claim[]; results?: ResultsBlock; profile?: ProfileBlock }
interface ResultsBlock { period: string; basis: "consolidated" | "standalone"; is_lender: boolean;
  rows: { name: "Revenue" | "EBITDA" | "PBT" | "PAT"; value: Metric; qoq: Metric; yoy: Metric }[];
  status: "verified" | "unverified"; unverified_reason?: string }
interface ProfileBlock { person: string; role: string; change: "appointed" | "resigned" | "retired"; effective: string | null;
  filing_profile: Claim[]; web_background: { text: string; url: string }[] }

// GET /v1/alerts  (+ X-Finn-Rules)
interface Alert { key: string; symbol: string; company: string; rule: "price_pct" | "volume_mult" | "category";
  sentence: string; observed: Metric; threshold: number; date: string; item_id?: string }
// GET /v1/alerts/{key}/context → { series: Metric[]; threshold: number }

// GET /v1/research/{symbol}  (202 + {job, steps[]} while building; poll)
interface Dossier { symbol: string; company: string; coverage: { transcripts: number; annual_reports: number; updated_at: string };
  ledger: { summary: Claim; rows: LedgerRow[] }; financials: { series: Metric[][]; read?: Claim };
  balance_cash: { metrics: Metric[]; read?: Claim }; business: Claim[]; gaps: string[]; system: SystemState }
interface LedgerRow { metric: string; period: string; promise: Claim; band: { low: number | null; high: number | null; unit: string };
  actual: Metric | null; crosscheck: Metric | null; verdict: "Delivered" | "Partly delivered" | "Missed" | "Not yet measurable" | "Insufficient evidence";  // D-42
  method: string; explanation: string;  // comparison method and one-line reason, shown in the ledger
  scale: { min: number; max: number } }

// POST /v1/research/{symbol}/ask {question} → { answer: Claim[] } | { answer: [], reason: "not_in_filings" | "quota_paused" }
// GET /v1/evidence?ref=<metric or citation id> → { title: string; chain: Provenance[]; snippet?: Citation }
// GET /v1/health → { ok: true, warm: boolean, system: SystemState }
```
**Contract rules:** responses never contain a number without `provenance`; an item has no `why` unless it is a validated Claim; `ResultsBlock.status = "unverified"` means the UI shows "Couldn't verify numbers. Open filing." and no figures. Contract tests snapshot the OpenAPI schema (EVALUATION §3).

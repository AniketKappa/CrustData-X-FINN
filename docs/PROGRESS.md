
# FINN — Progress Log

Update this file at the end of **every** phase. Record only what is actually done and verified. Anything unverified goes under "Not verified".

## Current status
- **Phase**: 0 complete, including the design system and static prototype → next is **Phase 1**: environment, repo, keys and spikes S1–S9 (O1–O3 decided by D-38; O4 open)
- **Implemented features**: see the phase entries below (latest: Phase 3 hackathon decision support).
- **Deployed URL**: none yet

---

## Phase 0: Initialization & requirements (2026-10-30, ~01:00–02:00 IST)
**Done**
- Read both challenge PDFs in full (MAIN 4 pp, REF 3 pp).
- Created CLAUDE.md, README.md, `.env.example`, `.gitignore` and `docs/` (REQUIREMENTS, PRODUCT_SPEC, ARCHITECTURE, IMPLEMENTATION_PLAN, RESEARCH, DECISIONS, PROGRESS, EVALUATION).
- Desk research on data sources (RESEARCH.md R2–R8).
- `git init` (no commits yet).

**Verified**
- Claude's build workspace cannot reach NSE, BSE, screener.in or Yahoo Finance (curl test). It can reach PyPI and npm.

**Not verified**
- Whether any data source works from the user's machine or a cloud host (Spikes S1–S5).
- Candidate portfolio symbol validity (S5).
- LLM provider availability and limits (S6).

**Open questions**: see README "Open questions".

**Next** (as planned at the time; superseded by Phase 0b/0c): Phase 1 spikes and scaffold.

## Phase 0b: Owner clarifications (2026-10-30, ~01:38–01:55 IST)
**Done**
- Desk research on free tiers: Gemini, Groq, OpenRouter, Tavily, Render/Fly/Koyeb, jugaad-data (RESEARCH R10–R13).
- Three rounds of multiple-choice questions with the owner; answers recorded in REQUIREMENTS §8.
- Docs updated: new requirements R-30–R-35; DECISIONS D-15–D-21; ARCH §3 (hosting) and §6 (LLM routing); PRODUCT_SPEC §3 and §6; plan and traceability.

**Verified**
- The build-sandbox block is a network **policy** (proxy logged a 403 on CONNECT for each data host), fixable by setting Network access to Full.

**Not verified**
- Anything about live data sources, free quotas, or Render behaviour. That all needs Phase 1.

**Next**: the owner completes U1–U4 (IMPLEMENTATION_PLAN Phase 1) and opens a new session with Full network access on the GitHub repo.

## Phase 0c: Planning-quality pass (2026-10-30, ~03:06–03:40 IST)
**Corrections made**
1. **Primary-source boundary.** Added the source-class model (`PRIMARY_DOC`, `STANDARDIZED_TABLE`, `DERIVED`, `MARKET_DATA`, `EXTERNAL_WEB`) with `Provenance` on every number and claim (ARCH §4a, R-36, D-22). Screener tables supply numbers only; narrative and the ledger's "promised" side must cite primary documents; web and market data never enter Pull; the ledger shows both sources when XBRL and screener differ by more than 1%. Ten enforcement tests added to EVALUATION §3, plus Q14.
2. **Evidence classes.** RESEARCH R10–R12 rewritten so every service claim is tagged [OFFICIAL] / [OBSERVED] / [3RD-PARTY] / [UNVERIFIED]. Third-party quota numbers are explicitly excluded from planning. R14 created for observed account limits (empty).
3. **LLM config.** Replaced the single fallback var with routes × slots (`fast`/`long` × primary/fallback), each naming provider **and** model; an independent quota tracker per (provider, model); provider 429/headers are the source of truth; self-imposed budgets left blank. Updated in ARCH §6, `.env.example`, CLAUDE.md rule 11 and D-23. **Removed the previously invented budget numbers (200/800 requests/day).**
4. **Acceptance criteria and cuts.** IMPLEMENTATION_PLAN rewritten with a protected core (mobile UI, real-data Push, source-grounded Pull, Promises Ledger, reproducible demo), a 9-step explicit cut order, time-boxed checkpoints, and evidence-required acceptance lists per phase and gate (G1–G5) (D-24).
5. **Storage and restart.** Render's official docs confirm an ephemeral filesystem with no disk on free. The server is now stateless: committed config/seed/seed cache; device-side settings, read state and triage; alerts computed on read (ARCH §4b, D-16 revised, D-25 portfolio read-only). `.gitignore` now allows `data/seed/` and `data/seed_cache/` (verified with `git check-ignore`).
6. **Consistency sweep.** Fixed: the leftover "Postgres (deploy)" in the architecture diagram, LLM provider names hard-wired into pipeline steps (now routes), alert timing (computed on read, not at ingestion), the Settings "data mode" toggle (removed; portfolio read-only), unbacked capacity claims in EVALUATION Q8, and snapshot-mode wording. Bull vs Bear appears only as an explicit exclusion.
7. **Scope preserved.** Same portfolio and research list, research sections, interaction features, design direction and free-only constraint. Nothing added.

**Verified this pass (official docs, read via search extracts; direct fetches of these domains were blocked in this session)**
- Gemini: limits per project; RPD resets at midnight Pacific; free numbers shown only in AI Studio; free-tier content is used to improve Google products; billing-linked projects are charged.
- Groq: per-org limits in the console; `retry-after` and `x-ratelimit-*` headers; production table lists gpt-oss models and marks the Llama 3.x models "Contact Sales".
- Tavily: 1,000 credits/month free, no card; basic search = 1 credit; resets on the 1st.
- Render: 15-min spin-down, ~1-min spin-up, 750 instance-hours, ephemeral FS, no free disk, possible suspension for high outbound traffic; Postgres free expires after 30 days.
- Vercel Hobby: non-commercial personal use only; 300 s functions. GitHub Actions: 5-min minimum schedule, delays and drops possible.

**Still unverified (blocking or shaping Phase 1)**
- [UNVERIFIED] NSE/BSE/screener reachability from the build sandbox (needs Full network, U1) and **from Render** (S1–S3).
- [UNVERIFIED] Which Gemini/Groq models our free keys can call, and their limits (S6 → R14). No account has been tested.
- [UNVERIFIED] Free capacity suffices for 22 seeded tickers plus unseen tickers (A-11).
- [UNVERIFIED] Screener document links are visible without login (S3).
- [UNVERIFIED] XBRL tag mapping and per-announcement XBRL access (S4).
- [UNVERIFIED] Boot-rebuild time and outbound MB per ingest on Render (S7).
- [UNVERIFIED] Tavily result quality for Indian appointees (S8).
- [UNVERIFIED] The 22 NSE symbol mappings (S5).
- [OWNER] Acceptability of per-device settings (A-13) and of Vercel Hobby terms for this prototype.

## Phase 0d: Provider, data & product research (2026-10-30, ~03:16–04:05 IST)
**Done**
- Official docs reviewed for Gemini (structured output, pricing, terms/data use, TTS, Transcribe), Groq (models, rate limits, STT, TTS, data retention), OpenRouter (free limits), MDN Web Speech (recognition and synthesis), Deepgram, ElevenLabs, yfinance, NSE (terms, copyright, bhavcopy/UDiFF), BSE (disclaimer, data products), screener.in (terms, no-API statement), Quartr, AlphaSense, Screener AI. Findings in RESEARCH R15–R24 with URLs, access date and evidence class.
- Claude in Chrome: opened NSE's announcements page and its JSON endpoint once (read-only); parsed 74 INFY records → field list, `desc` vs `attchmntText` behaviour, `hasXbrl` caveat (R15). Screener redirected to a **signed-in** dashboard, so that session was not used. Tab closed.
- DECISIONS D-26 (recommended stack), D-27 (rejected alternatives), D-28 (data licensing, **pending owner**), D-29 (classification fields), D-30 (document discovery order), D-31 (repo content policy, **pending owner**).
- ARCHITECTURE: §5.1 classification fields; §5.4 discovery order; §5.6 voice adapter; §4b repo-content constraint; new §6.3 data-use and §6.4 provider-agnostic adapter interfaces. EVALUATION: adapter contract, classification and seed-policy tests.

**Verified**
- [OBSERVED] NSE announcements JSON shape for one symbol from the owner's browser (one page view). **Not** verified from a server or from Render.

**Not verified / open**
- Free-plan model access and numeric quotas on our own Gemini/Groq keys (S6). No account was tested.
- Whether Groq Orpheus TTS is usable on the free plan (priced, preview).
- Logged-out visibility of screener.in documents (S3).
- Quartr coverage of the 22 Indian companies (positioning only).
- **Owner decisions D-28 and D-31.**

## Phase 0e: Source-access decisions (2026-10-30, ~03:55–04:35 IST)
**Done**
- Re-read the exact official terms: NSE ToU (Items 8, 9), NSE Copyright, NSE RSS page, BSE Disclaimer, BSEPlus terms, screener.in Terms, Yahoo ToS. Separated automated access, personal use, storage, redistribution/display and commercial use (RESEARCH R25). No legal determination made.
- Found officially offered channels: NSE RSS (22 corporate feeds, URLs recorded) and BSE RSS; SEBI LODR Reg 46 company-website disclosures (results, full AR, transcripts); half-yearly BS/cash flow in results (SEBI FAQ); NSE UDiFF bhavcopy; Upstox historical-candle API docs (R26).
- Fetched three NSE RSS feeds once: announcements feed ≈ 1-hour rolling window, name only (no symbol); Integrated-Filing feed has XBRL links; the legacy Financial Results feed is stale (R26).
- Decisions: **D-31 APPROVED**; **D-32 APPROVED** (policy); D-33, D-34, D-36, D-37 **CONDITIONAL**; **D-35 UNRESOLVED**; D-19 reopened; D-26/D-28/D-30 superseded in part. yfinance rejected (Yahoo ToS).
- ARCHITECTURE: diagram, §3 RSS poller, §4a/4b repo content policy + metadata log, §5.1, §5.4, §6.4 adapters updated. IMPLEMENTATION_PLAN Phase 1 rewritten (owner decisions, environment, repo, keys, spikes S1–S9, G1). README, CLAUDE.md (source-access rules), PRODUCT_SPEC, REQUIREMENTS (A-4 reopened), EVALUATION rows aligned.

**Not verified**
- Whether server-side RSS polling is acceptable under NSE/BSE terms (ambiguous; owner decision O1).
- Upstox API terms and auth requirement.
- RSS window at peak load; GitHub Actions schedule reliability (S1, S9).
- Company-site availability of ≥ 4 transcripts for the research companies (S3).

**Next:** the owner answers O1–O4, then does E1–E3, R1–R3 and K1–K3.

## Phase 0f: Owner source decision + design system (2026-10-30, ~04:05–04:50 IST)
**Done**
- Recorded the owner decision D-38 (personal non-commercial project; all publicly accessible sources; guardrails kept; D-31 kept). Updated D-32/33/35/36/37, CLAUDE.md, README, ARCH adapters, Phase 1 spikes.
- Design system (PRODUCT_SPEC §6), screen hierarchy, navigation, journeys J1–J7, interaction decisions, 26 component specs (§4–4c).
- ARCH §9 frontend boundaries (D-39) and §10 typed API contracts.
- Static prototype `design/prototype/index.html` with labelled fixture data (Infosys rows use real NSE metadata observed 29 Oct). Rendered with Playwright at 390×844 (brief, detail, dossier, evidence, dark) and 1280×800. Fixed after review: change-colour specificity bug, range-strip label overlap, 36 → 44 px tap targets, active-tab state, sheet z-order.

**Not verified**
- Colour contrast measured by tool (visual check only so far).
- Plex rendering from `next/font` (the prototype loads it from Google Fonts).

## Phase 0g: UI redesign v2 — functional prototype (2026-10-30)
**Problems found in v1** (`design/prototype/archive/index-v1.html`): Alerts and Settings tabs led nowhere; three of four dossier tabs were dead; window control, Listen and the routine button did nothing; must-read items were boxed cards with three heavy buttons; no financial charts, Overview or Cash & debt; the ledger lacked dates, comparison method and qualitative statuses; the Ask input was fixed over content; the desktop detail pane always showed one fixture; invalid CSS (`width:minmax(...)`); no freshness or portfolio context; the cool palette read as a generic dashboard.

**Done**
- New IA (D-42): Briefing / Companies / Research, plus a "Portfolio & alerts" header dialog. Bottom nav on mobile, rail at ≥ 1024 px, active state synced from the route.
- Light editorial design system v2 (PRODUCT_SPEC §6): warm ground, Plex Sans + Plex Serif, rules instead of cards, one blue accent. Text contrast measured (all AA). The chart series pair was validated for colour-vision deficiency (ΔE 22.9).
- Prototype split into `index.html`, `styles.css` and ES modules: `fixtures` (contract-shaped, labelled data), `logic` (window filter, priority, alerts on read, QoQ/YoY, margins, cash quality, ledger verdicts; pure), `format`, `charts` (SVG at measured width), `views` (HTML only), `app` (routing, events, dialogs, speech, device storage).
- Working: window control in the URL; Listen and Stop (speechSynthesis); routine expansion; Done / Snooze / restore; item detail (route on mobile, sticky pane on desktop); evidence dialog (real NSE links for the four Infosys rows, fixture passages otherwise); thresholds and categories saved per device and applied to alerts; company search with honest empty states for real companies; Overview, Financials (table + revenue + EBITDA-margin charts + 8-quarter table), Cash & debt (OCF vs PAT, OCF/PAT, capex, FCF, working-capital days, leverage), Promises (five statuses, method, explanation, range strips); Research (company selector, examples, cited notes, interpretation and uncertainty labelled, follow-ups, spoken notes, honest reply to free questions).
- Tests: `design/prototype/test/smoke.cjs` (Playwright, 390×844, 820×1180, 1280×800): **40/40 checks pass, 0 console errors or warnings** (`test/last-run.txt`). Screenshots in `design/prototype/shots/`.
- Docs: PRODUCT_SPEC §4 and §6 rewritten (with §4.5, implemented vs not); ARCH §9 routes and components, §5 ledger rules and §10 `LedgerRow` statuses; D-40 superseded by D-42.

**Not done / limits**
- Static prototype only: no backend, no live data, and free-typed research questions aren't answered. Real companies show no figures.
- Not in v2: alert context chart, per-holding overrides, holdings editing, swipe, custom window, dark mode, web background for appointees.
- Speech was tested only for the control state. Audio output was not verified in headless Chromium.
- No screen-reader pass with real assistive technology; keyboard checks are automated only (skip link, Esc, focus return).

**Next:** Phase 1 owner setup (Full network session, repo, keys, spikes S1–S9), then slice 1 (live Briefing) built on these components.

## Phase 1a: Push data pipeline, backend (2026-10-30)
**Done**
- `backend/` Python package `finn`, with typed Pydantic contracts and provenance on every observation (source, retrieval time, data date, fixture flag).
- Prices: yfinance adapter (`.NS`/`.BO`, lazy import, timeout, one bounded retry; "possibly delisted"/empty mapped to `no_data` without retry) and a deterministic fixture provider. NSE/BSE symbol normalisation.
- Signals: daily % change, volume ÷ mean of the previous N sessions (zero-volume days excluded), partial-session guard, staleness by weekdays, insufficient-history handling. Plain-language disclosures for stale, no-data, provider-error and short-history cases; cached bars are used, with a note, when a refresh fails.
- Alerts: deterministic ≥ thresholds from `config/alerts.yaml`, env or per request. Boundaries tested (5.0% fires, 4.99% doesn't; 2.0× fires, 1.9999× doesn't). No alerts on stale data.
- Announcements: NSE RSS, NSE JSON (undocumented, schema-checked, backfill only) and BSE RSS (disabled until its URL is verified) parsers. Extracts symbol (via name aliases for RSS), verbatim subject, attachment text, IST filing time, category label, link and attachment size/kind. Dedup per D-43; NSE/BSE copies collapse.
- Classification: ordered rule table over subject + attachment text for all 17 REF categories plus subtypes (results ad, board notice, top management, independent director, rating downgrade/reaffirm, transcript, regulator); rule name and confidence returned.
- Ranking: explainable weighted score and tiers (D-44); routine items collapsed; window 24 h default, 72 h and 168 h allowed.
- Network discipline (D-47): reads never fetch; TTL caches plus failure backoff; timeouts, bounded retries, per-host delay, no retry on 401/403/404. SQLite store.
- Demo portfolio: 18 holdings (15 sectors, large/mid/small) + 4 research companies in config. Fixture portfolio of fictitious companies (D-46).
- API (`/health`, `/v1/digest`, `/v1/market`, `/v1/sources`, `POST /jobs/refresh` with a shared secret) and CLI (`refresh`, `digest`, `check-live`).
- **Tests: 125 passed, offline** (symbols, market boundaries, HTTP retry/timeout/backoff, price adapter, parsers, dedup, classifier, ranking, pipeline, cache, failure handling, API, config, fixture content policy, secret scan).

**Not verified / not done**
- No live source reached: from the build environments, `check-live` gives a proxy 403 for Yahoo, nseindia.com and nsearchives (README "Live integrations").
- No exchange holiday calendar, no bhavcopy fallback, no LLM classification fallback, no results extraction yet.
- The prototype UI is not yet wired to the API; the Next.js app is not started.
- Ranking weights and materiality values are initial guesses, not yet tuned on a hand-labelled sample (EVALUATION §2).

**Live check on the owner's PC (2026-10-30 05:20 IST):** yfinance ok (INFY.NS, 9 bars, latest 28 Oct, one session behind); NSE RSS ok (5 items parsed, 0 from the portfolio); NSE JSON **HTTP 403** → disabled, not worked around (D-49). Added `python -m finn inspect-rss` to show raw `pubDate` values and per-item mapping and classification.

**Next:** run `inspect-rss` during the evening filing peak (about 17:00–20:00 IST) to check name mapping and window length; then schedule RSS polling every ≤ 10 min; then the Next.js Briefing on `/v1/digest`.

## Phase 1b: Briefing connected to the live API (2026-10-30)
**Done**
- `finn.api` serves the web app at `/` (D-50), adds `/v1/portfolio`, runs one background refresh at start-up in live mode, serialises refreshes and reports progress in `/health`.
- UI: `js/api.js` client and adapter (DigestItem → view item); the Briefing uses live data when the API is present. Window, thresholds (sent to the API), Refresh button with result message, "Data notes" with the server's disclosures, data-source status in the settings dialog, item detail with verbatim filing text, classification rule and score reasons, alert calculation with the thresholds used. Loading, error ("no fallback to demo data") and first-refresh states. Companies/Research copy updated ("research not built yet").
- Tests: backend **128 passed**; UI smoke (static mode) 40/40; new `design/prototype/test/live-api.cjs` (UI served by the API in fixture mode, plus live mode with no network): all checks pass, no console errors.

**Not verified**
- The live Briefing with real data was exercised only on fixtures and in a no-network state here; the owner's PC is the first real run.

## Phase 1c: News headlines, Screener results, brief-aligned Briefing (2026-10-30)
**Done**
- `providers/news.py`: Google News RSS search per company (trusted outlets only) and publisher RSS (ET company and stocks, Moneycontrol business). Headline, publisher, time and link only; whole-word company match with exclusions (e.g. ITC vs ITC Hotels, L&T vs L&T Finance); one item per story across outlets. Top 10 in the digest, classified with the same rules, confidence capped at 60, labelled as media.
- `providers/screener.py`: Quarterly Results table → Revenue, EBITDA (derived), PBT, PAT with QoQ/YoY; lenders get EBITDA n/m; consolidated then standalone; schema errors become visible notes. Fetched only for companies with results items, cached 6 h.
- Pipeline `refresh_all` (prices → filings → news → results); CLI `refresh` table, `digest` prints news and the results card; `check-live` tests news feeds and Screener.
- Briefing UI regrouped into the brief's sections (D-53) with source labels, results tables (once per company), news detail with "Read on <publisher>", empty-section line and section-wise spoken briefing.
- Tests: backend **140 passed**; UI static smoke and API-mode suites pass with no console errors.

**Not verified**
- News feeds and Screener have not been fetched by FINN yet; run `python -m finn check-live` on the owner's PC.
- Management bios: no LinkedIn (terms); web-search enrichment not built.

## Phase 1d: Coverage portfolio, Portfolio tab, live company pages, UI v3 (2026-10-30)
**Owner's live run (05:59 IST) before this phase:** 3 market moves and 10 results across 5 companies over 7 days; one news feed returned HTTP 403 (others worked); prices and Screener results worked.

**Done**
- Portfolio (D-54): 20 holdings + 4 watchlist chosen to cover all six alert types; news terms with exclusions and case-exact matching (`=Eternal`, `=Trent`, `=Astral`).
- Backend: editable portfolio saved to `data/portfolio.json`; `/v1/holdings`, `/v1/holdings/add`, `/v1/holdings/remove`, `/v1/search` (Yahoo Finance search, NSE/BSE equities, local fallback), `/v1/company/{symbol}`. Screener parser rewritten on a small DOM: key ratios, about, sector/industry, quarterly, annual P&L, balance sheet, cash flow, efficiency ratios, annual reports, concall transcripts/slides/recordings, credit-rating documents. Fundamentals refreshed for every tracked company (12 h cache); results cards come from the same snapshot.
- UI v3 (D-55): new design system; Briefing with hero summary, filter chips, sections including Credit ratings, price rows for market moves, results tiles, "earlier this week" fill, About-this-data sheet; item detail with plain-language "Why you're seeing this"; Portfolio tab with search/add/watch/remove; company pages with price chart, results, ratios, about, news, filings, charts and tables, documents.
- Tests: backend **144 passed**; `test/v3.cjs` (API-served app, mobile + desktop) all pass, no console errors; `test/static.cjs` (no backend) passes. Old v2 browser tests retired (`smoke.cjs`, `live-api.cjs` are superseded).

**Not verified**
- Live Screener page layout for the new sections (documents, ratios) and Yahoo search: built against Screener's documented page structure and synthetic fixtures; first real check is the owner's PC.
- Which news feed returns 403 (likely Moneycontrol's RSS URL, which was unverified).

## Phase 2: Pull research, market-move windows, portfolio edit (2026-10-31)
**Done**
- Market moves: today's in-session price (labelled live), per-session alerts within the window, "Biggest moves" over 1/3/5 sessions; windows measured from the server clock.
- Portfolio: search opens company pages only; Edit = Add (sheet) + Delete (tick, second tap confirms). Company pages fetch prices and fundamentals on open; records saved by older versions are re-fetched.
- Research (`finn/research/`): documents, BM25 retrieval, numbers, claims validator, guidance ledger, engine with background jobs and 24 h cache; API `/v1/research/{sym}/start|ask`, `GET /v1/research/{sym}`. UI: picker (search any NSE company), progress, summary tiles, business, promised vs delivered, management's explanation, numbers with charts, cash & debt, bull vs bear, sources, Ask bar with voice input (Web Speech), citations open the passage and page.
- LLM routing with per-model minute budgets, 429 fallback, call log.
- Keys moved from `.env.example` to the ignored `.env` on the owner's PC.

**Verified**: backend tests pass (incl. `test_research.py`: validator, quotes, horizons, verdicts, end-to-end dossier on fixture PDFs); `v3.cjs` 38 browser checks pass twice, no console errors.

**Not verified**: live Groq/OpenRouter/Tavily calls and downloading real BSE/company PDFs (this build environment has no internet access; to be checked on the owner's PC). Vercel deployment not done (awaiting owner decision).

## Phase 1e: Story clustering, executive backgrounds, fresh-on-open, interaction hardening (2026-10-30)
**Diagnosis from the owner's database (06:38 IST):** 410 headlines, 25 Screener pages and 30 price series were fetched fine; Moneycontrol RSS 403; NSE RSS had 5 unmapped items. Management (Trent, Info Edge, HDFC Bank) and legal (Yes Bank AT1) stories existed but a global 10-headline cap hid them, and the same top 10 showed in every window.

**Done**
- Noise filter, story clustering with "also reported by", headline-tuned rules (management phrasings, AT1/court/notice, stake deals, investment plans, orders/guidance); ITC input-tax-credit false positives excluded.
- `people.py`: incoming/outgoing name and role extraction (tested on real headlines), filing "Brief profile" from PDF, Tavily search, Wikipedia check, coverage, optional cited LLM brief (`llm.py`: Groq → OpenRouter, free tiers). `.env` loader; keys never committed.
- API: background refresh, health flags (`llm`, `web_search`). App: fresh-on-open, "Updating…" state, 5-per-section with Show more, management cards in the list and a "Who is …?" section in the detail, action locks, sheet double-tap guard, design v3.1 consistency.
- Tests: backend **163 passed**; `v3.cjs` 25 browser checks pass including triple-tap Refresh (1 request), multi-tap Add (1 request), double-tap settings (sheet stays), rapid chips, two quick item taps; no console errors.

**Not verified**
- Tavily and Groq/OpenRouter calls (no keys in this environment); PDF brief-profile extraction against a real NSE attachment.

## Phase 3 (hackathon): Decision support — rank, backtest, flags, why-moved, Ask FINN, health (2026-11-06)
**Done**
- Bug fixes: B1 Yahoo requests use explicit start/end with end = tomorrow in IST (latest session no longer dropped); B2 Briefing header counts holdings and watchlist stocks separately; B3 `?s=bull_bear` deep link maps to the Bull & bear tab; B4 "about the same as" (generator fixed and cached dossiers corrected when served) and "1 page read"; B5 company page prefers the curated portfolio sector.
- Background 10-year price backfill after start-up for tracked stocks + `^NSEI`/`^CRSLDX` (`finn/decision_service.py`), `POST /jobs/backfill` (secret-protected).
- New endpoints: `/v1/history/{symbol}`, `/v1/benchmark`, `/v1/data-status`, `/v1/rank`, `/v1/rank/{symbol}`, `/v1/backtest/latest`, `/v1/flags`, `/v1/flags/{symbol}`, `/v1/moves/{symbol}`, `POST /v1/agent/ask`, `/v1/agent/briefing`, `/v1/portfolio/health`; `/v1/company/{symbol}` gains `rank`, `flags` and `history_long` (`?days=`); digest market alerts gain `why`.
- Pure logic in `finn/decision.py` (factors, guards, percentiles, grades, labels, backtest, flag rules, date parser, explanation validator, health).
- UI: FINN Signal card on the company overview (rank, grades, drivers, red flags, "Why did it move?", Ask FINN), rank badges and a Portfolio health card on Portfolio, a Morning briefing card on the Briefing; caveat on every decision view.

**Verified**
- `pytest`: 224 passed, 0 failed (37 new, up from 187: Appendix E flag fixtures 27/27, 6 day-first date formats, Appendix F price fixtures, CFO/PAT and negative-equity guards, NaN-free JSON, backtest equal-weight and benchmark consistency, a no-look-ahead tamper test, explanation validator, health de-duplication, all new endpoints in fixture mode).
- `node --check` on every JS module; fixture-mode UI rendered in headless Chromium (Briefing, Portfolio, company page with Why/Ask) with no page errors.

**Not verified**
- Live data: the build sandbox can't reach Yahoo/BSE/Screener, so the live backfill, `^CRSLDX` availability, real rank distribution and the live backtest numbers are unmeasured until deployed.
- LLM-written explanations and Ask FINN answers (no keys in the sandbox); only the deterministic paths and the validators were tested.

**Live finding (deployed at https://finn-mux5.onrender.com, 6 Nov 04:05 IST)**: every stock showed 4 Nov as the latest close. Observed cause: Yahoo's 5 Nov daily row had open/high/low/volume but a null close; the quote metadata held the session price (INFY regularMarketPrice 1167.4 at 15:28 IST). Fix: when the last row's close is null and Yahoo's regularMarketTime is the same IST day, use regularMarketPrice and label the bar's provenance; batch rows with a null last close are re-fetched singly. The 10-year backfill now starts when the first refresh is "ready" instead of after PDF reading. **Follow-up (observed 6 Nov 04:30 IST):** from Render, yfinance returns the 5 Nov row with a null close and no quote metadata, and Yahoo answers a direct chart request with HTTP 429. FINN therefore does not fill the close (no invented or worked-around data): it keeps the previous close, shows a disclosure ("Yahoo hasn't published the 05 Nov closing price yet…") and re-asks at most once an hour per stock; `/v1/data-status` → `latest_session_topup` shows the route and result per symbol.

**Live verification (Render, 6 Nov 04:40–05:00 IST, measured)**
- Backfill: 26/26 series (24 stocks + Nifty 50 + Nifty 500), 2,461–2,471 daily bars each (ETERNAL 1,307, POLYCAB 1,867, PAYTM 1,227 since listing), ~50 s; `with_1y_history` 26.
- Rank: 24/24 ranked; spread 1–10. Backtest: 106 months (Dec 2017–Sep 2026); top third CAGR 20.9% (vol 19.1%, max drawdown −21.6%), bottom third 20.9% (vol 28.2%, −50.4%), equal weight 19.3%, Nifty 50 9.3%; mean rank IC 0.017; top beat Nifty in 57.5% of months. Survivorship bias explains much of the gap to Nifty. Not flagged implausible.
- Flags: 3 (ASTRAL GST order: red; YESBANK Supreme Court AT-1 judgment: amber; POLYCAB CIRP update: info via the negation guard). Coverage since 29 Oct 2026.
- Portfolio health 40/100 (base 48.3; −2 amber flag, −6 weak momentum).
- "Why did it move" (SUZLON) and Ask FINN (Vedanta) returned validated LLM answers with cited ids; the probability question was refused by rule.
- Groq answered HTTP 404 for `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`; both removed from the routes.
- Known limitation: prices are unadjusted closes; corporate actions such as demergers (e.g. VEDL) distort momentum and 1-year change.

**Owner feedback round (6 Nov 05:30–06:00 IST), fixed**: briefing grouped by company (one results item per company, related filings folded; counts are companies); morning briefing in the app's typography; "Why this rank" in plain English plus every measure and the rank formula; Ask FINN gets display-ready values and explains factors; portfolio health ranks against a fixed reference set (removing a weak stock no longer lowers the others' percentiles; added stocks get 10-year history at once) and lists each flag and weak-momentum stock; Back returns to the previous briefing filter and closes dialogs.

**Next**: deploy the Render Blueprint, check `/v1/data-status` (expect ≥ 20 symbols with 1-year history) and `/v1/backtest/latest`, then record the measured numbers here.

## Metrics (filled in as measured)
| Metric | Value | Date |
|---|---|---|
| — | — | — |

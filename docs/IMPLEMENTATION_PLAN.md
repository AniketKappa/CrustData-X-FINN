# FINN — Implementation Plan

**Deadline: Sunday, 1 November 2026.** The user controls when it is submitted (Q-4). The times below are internal targets, not commitments.
Planning started Fri 30 Oct 2026, 01:00 IST (≈ 2.8 calendar days). The schedule is worked backward from the deadline.

## 1. Backward schedule (IST)

| When | Phase | Gate |
|---|---|---|
| **Sun 1 Nov 18:00–20:00** | **Submit**: email to assessment@enam.com, subject "ENAM - IIT screening - 2027" | All 4 deliverables sent |
| Sun 1 Nov 14:00–18:00 | Phase 9: README, DEMO.md, writeup, build-history export, final phone test | **G5** |
| Sun 1 Nov 09:00–14:00 | Phase 8: hardening, seed cache, eval run, deploy | **G4** |
| **Sat 31 Oct 24:00** | **Feature freeze**: fixes only after this | — |
| Sat 31 Oct 19:00–24:00 | Phase 7: Pull UI, evidence sheet, Dig in, Ask box UI, voice | **G3** |
| Sat 31 Oct 13:00–19:00 | Phase 6: guidance, Promises Ledger, sections, Ask API, validators | (Phase 6 acceptance) |
| Sat 31 Oct 08:00–13:00 | Phase 5: Pull ingestion, provenance-tagged metrics | (Phase 5 acceptance) |
| Fri 30 Oct 19:00–24:00 | Phase 4: Push UI incl. swipe triage | **G2** |
| Fri 30 Oct 14:00–19:00 | Phase 3: alerts, results card, mgmt card | (Phase 3 acceptance) |
| Fri 30 Oct 11:00–14:00 | Phase 2: Push ingestion, classification, scoring | (Phase 2 acceptance) |
| Fri 30 Oct 08:00–11:00 | Phase 1: user actions, spikes, scaffold, deploy skeleton | **G1** |
| Fri 30 Oct 01:00–03:30 | Phase 0: requirements, clarifications, planning pass | ✅ done |

## 1a. Protected core & cut order
**Protected core. Never cut; a phase cannot be marked done if it breaks any of these:**
1. **Working mobile interface**: the deployed web app loads and is usable on a real phone (390 px) for every shipped screen.
2. **Real-data Push workflow**: a 24h/7d digest from live NSE/BSE announcements for the 18-stock portfolio, classified and tiered, plus price/volume alerts from real EOD data with user-set thresholds.
3. **Source-grounded Pull workflow**: a dossier for **any** NSE ticker typed in, with every number carrying provenance and every narrative claim citing a primary document (R-19, R-36).
4. **Promises Ledger**: promised (transcript-cited) vs delivered (sourced number) with code-computed verdicts, for the 4 research companies at least.
5. **Reproducible demo**: a clean clone plus free keys plus documented steps gives the same demo; offline tests pass; the seed snapshot and seed cache are committed (R-37).

**Cut order. If time runs short, cut from the top, one item at a time. Each cut is logged in DECISIONS, and the owner is told the same day.** All of these are owner-confirmed features, so cutting is a contingency, not a plan.

| Order | Feature | What remains if cut |
|---|---|---|
| 1 | Voice briefing (R-33) | — |
| 2 | Ask box (R-31) | Fixed dossier sections |
| 3 | Business snapshot section | Ledger, Financials, Balance sheet + cash |
| 4 | Tavily web background on mgmt cards | Filing "brief profile" only |
| 5 | Swipe *gestures* (R-32) | Done / Snooze / Dig in **buttons** (the triage state is kept) |
| 6 | Balance sheet + cash section | Ledger + Financials |
| 7 | Per-ticker threshold overrides | Global thresholds (R-12c still met) |
| 8 | Results card PDF fallback | XBRL path only; otherwise "Couldn't verify — open filing" |
| 9 | Promises Ledger verdicts | **Guidance tracker** (cited promises + actuals, no verdict). This is the last resort: it degrades core item 4 and must be approved by the owner |

**Time-boxed checkpoints** (decide at these times):
- **Fri 19:00**: results extraction not passing golden tests → apply cut 8.
- **Fri 24:00**: G2 not met → stop all Push polish; apply cuts 5 and 7 if needed; do not start Pull UI until G2 passes.
- **Sat 13:00**: Pull ingestion works for fewer than 2 research companies → apply cuts 2 and 3.
- **Sat 19:00**: ledger acceptance not met → spend until 21:00; then cut 9 only with owner approval.
- **Sat 22:00**: Pull UI incomplete → apply cut 1.
- **Sun 09:00**: freeze. Fix only protected-core defects.

## 2. Phases, tasks & acceptance criteria
Priority: **P0** = protected core · **P1** = confirmed scope, cuttable in the order above.
Every acceptance item must be **verified and recorded in PROGRESS.md** (command output, screenshot path, or test name) before the phase is closed.

### Phase 1: Feasibility (environment, repo, keys, spikes); **no application code yet**
Purpose: prove every source and provider is reachable through a permitted channel **before** building. Spike code lives in `spikes/` as throwaway scripts; nothing in `backend/` or `web/` beyond a hello-world. **No scrapers** (D-32).

#### 1A. Owner decisions (block everything else)
- [x] O1 **Decided (D-38):** yes; all publicly accessible sources allowed, with guardrails
- [x] O2 **Decided (D-38):** D-35 = B, screener.in tables, labelled
- [x] O3 **Decided (D-38):** yfinance first, NSE UDiFF bhavcopy fallback (S2 confirms)
- [ ] O4 Confirm the per-device settings model (A-13). Vercel Hobby fits (personal project, D-38)

#### 1B. Environment setup (owner, ~10 min)
- [ ] E1 claude.ai/code → environment gear → **Edit cloud environment → Network access: Full** → save. Start a **new** session for Phase 1 (settings apply to new sessions only).
- [ ] E2 In the same environment, add **environment secrets** (not plain env vars): `GOOGLE_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY` (from 1D).
- [ ] E3 Verify in the new session: `curl -sI https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml` returns 200 (not a proxy 403).

#### 1C. Repository setup (owner + Claude, ~10 min)
- [ ] R1 Create a **public** GitHub repo (`finn`), default branch `main`; push the Phase-0 docs (zip contents).
- [ ] R2 Create the empty branch `data` (for D-37), protected from force-push.
- [ ] R3 Repo settings → Actions → allow workflows; add **repository secrets** with the same three keys for Actions. Never commit `.env`.
- [ ] R4 Claude adds CI: `ruff`/`pytest` placeholder, **secret scan** (gitleaks or equivalent free action), and the **content-policy check** (D-31: fail on `*.pdf`, bhavcopy zips, or quote fields over one sentence in `data/`, `backend/tests/fixtures/`, `data` branch).
- [ ] R5 Connect the repo to **Vercel** (web) and **Render** (free web service, Python); deploy hello-world `/health`; open on a phone.

#### 1D. Provider keys (owner, ~10 min; all free, no card)
- [ ] K1 **Google AI Studio** API key in a project with **no billing linked** (check AI Studio shows "Free" plan).
- [ ] K2 **Groq** console API key (Free plan).
- [ ] K3 **Tavily** API key (Researcher free plan, development key).
- [ ] K4 (Only if O3 leans to Upstox) create an Upstox developer app; record whether historical candles need auth.

#### 1E. Verification spikes (Claude, in the new session; each writes a short result to RESEARCH R14/R26 and PROGRESS)
| # | Spike | Pass criterion | Output |
|---|---|---|---|
| S1 | NSE: RSS feeds (`Online_announcements.xml`, `Integrated_Filing_Financials.xml`) **and** the per-company announcements JSON (7-day backfill for 3 symbols) from the sandbox **and Render** | 200s; parseable; record items-per-feed and **time window covered** (min/median); ≥ 15 of 18 portfolio names matchable to symbols | `spikes/s1_report.md`; **synthetic** fixture mirroring the observed schema |
| S1b | BSE Corporate Announcements RSS: same | Same; overlap with NSE measured | report |
| S2 | Prices: (a) yfinance batch EOD for the 22 symbols × 60 sessions (note 429s); (b) one CM-UDiFF bhavcopy as fallback | All 22 resolve; (a) vs (b) closes agree for 3 symbols | report; synthetic fixtures; **no bhavcopy committed** |
| S3 | Documents and tables: screener.in public company page for 6 companies (tables + document links, logged out); exchange attachments; company sites as fallback; fetch 1 transcript each and extract text with page numbers | ≥ 5/6 have ≥ 4 transcripts; tables parse | report; `config/ir_sources.yaml` (URLs only) |
| S4 | XBRL: take 1 Integrated-Filing XBRL link from S1; map Revenue, Other income, Finance costs, D&A, PBT, PAT; detect period and consolidation | All 6 tags found and values match the PDF results | tag map in RESEARCH; synthetic XBRL fixture |
| S5 | Map the 22 confirmed companies to NSE symbols **and** their exact RSS company names | 22/22 mapped | `config/portfolio.yaml` |
| S6 | LLM keys: list models (Gemini, Groq); one strict-JSON call per chosen slot; record console limits and headers | All 4 slots callable on free keys | `.env` values (local only); R14 filled |
| S7 | Render: boot time of hello-world; outbound MB for one transcript fetch | Boot < 60 s | report |
| S8 | Tavily: (a) one appointee background query; (b) IR-page discovery for one **unseen** ticker, restricted to the company domain | Relevant results with URLs | report |
| S9 | GitHub Actions schedule reliability: a 10-min cron for ≥ 3 h logging actual run times | Median delay and max gap recorded; max gap < the S1 feed window | report → confirms or rejects D-37 |

#### 1F. Gate G1 (all required before Phase 2)
- [ ] O1–O3 decided and recorded in DECISIONS.
- [ ] S1, S2, S3, S5, S6 pass; S9 shows the RSS window is safely covered (or the owner accepts the gap risk).
- [ ] CI green, including the secret scan and content-policy checks; no secrets or third-party documents in Git history.
- [ ] Hello-world reachable on a phone (Vercel → Render).
- [ ] PROGRESS updated with evidence for each item.

### Phase 2: Push ingestion (P0)
- [ ] `sources/prices_<D-36 choice>.py` EOD fetch (one file or call per day), cache → `PriceBar` with `MARKET_DATA` provenance.
- [ ] `sources/nse_rss.py` + `bse_rss.py` pollers (GitHub Action, D-37) → metadata log on the `data` branch → `Announcement` (idempotent; NSE/BSE duplicates collapsed; gaps recorded).
- [ ] `push/classify.py` rules plus keywords; `fast` route fallback (cached).
- [ ] `push/score.py` weights, modifiers, tiers.
- [ ] Boot sequence: load the seed, then catch-up ingest (ARCH §4b).
- [ ] Hand-label ~60 announcements → `tests/fixtures/labels.csv`.
- [ ] `GET /digest?from&to` (thresholds/toggles accepted from the request).

**Acceptance:**
- [ ] On the **deployed** API, `/digest` for the last 7 days returns real announcements for the portfolio, each with an exchange link.
- [ ] Classifier ≥ 85% on the labelled set (Q1); ≥ 70% classified by rules.
- [ ] Restarting the Render service → `/digest` returns the same items after the boot rebuild (restart test logged).
- [ ] Re-running ingest creates no duplicates (`test_announcement_dedup`).

### Phase 3: Push enrichment & alerts (P0 except where marked)
- [ ] `push/alerts.py` pure functions: price %, volume multiple (prior 20-session mean), category; global and per-ticker (P1); computed on read.
- [ ] `extract/results.py` XBRL path; validation gates; derived EBITDA; lender n/m; PDF fallback (P1, cut 8).
- [ ] `extract/mgmt.py` annexure profile with quote verification.
- [ ] `extract/people_web.py` Tavily background (P1, cut 4), labelled `EXTERNAL_WEB`.
- [ ] `extract/oneliner.py` one-liners for Must/Glance only.

**Acceptance:**
- [ ] Results golden tests: 5 filings × 4 metrics × 3 periods; **zero wrong numbers shown** (exact, or "couldn't verify") (Q3).
- [ ] Alert unit tests pass (thresholds fire and don't fire at the boundaries; per-ticker override precedence).
- [ ] Mgmt profile golden test on 2 filings; every profile sentence is quote-verified.
- [ ] Web background never appears without its URL and the "web" label (`test_external_web_labelled`).

### Phase 4: Push UI (P0; swipe gestures P1). **First vertical slice (D-41)** starts here, built on the design system in PRODUCT_SPEC §6 and the contracts in ARCH §10
- [ ] Slice 1 = J1 end-to-end on a real phone: `/v1/digest` + `/v1/items/{id}` → `AppShell`, `StatusBanner`, `BriefHeader`, `WindowControl`, `ItemMust`, `ItemRow`, `RoutineGroup`, Item detail, `EvidenceSheet` (source link level)
- [ ] Brief: window chips, tier sections, routine collapsed with a count, cards with "why it matters".
- [ ] Card detail: results table with source tags; mgmt profile (filing) and web background (separate).
- [ ] Alerts inbox; Settings (read-only portfolio, thresholds, toggles; "saved on this device").
- [ ] Triage: Done/Snooze/Dig in **buttons** (P0) plus swipe gestures (P1, cut 5); browser-storage state.
- [ ] Waking-server and source-fallback banners.

**G2 acceptance (all required):**
- [ ] On a **real phone**, against the **deployed** stack and **live** data: open → Brief → change the window → open a Must card → see evidence → back, with no horizontal scroll and tap targets ≥ 44 px (Q7 partial).
- [ ] Changing a threshold changes which alerts appear; the setting survives a page reload **and** an API restart.
- [ ] Triage state survives a reload; with browser storage unavailable the app still works (state just isn't kept).
- [ ] Playwright mobile smoke test for the Brief passes in CI against fixtures.

### Phase 5: Pull ingestion (P0)
- [ ] `sources/company_site.py` (curated `ir_sources.yaml` + Tavily domain-restricted discovery) → document refs (D-34); tables per D-35 (`STANDARDIZED_TABLE` provenance with locator).
- [ ] `research/docs.py` fetch, hash, page text, chunk (`PRIMARY_DOC` provenance with page); binaries discarded after parsing; outbound bytes logged.
- [ ] `research/metrics.py` pure functions → `Metric` with `DERIVED` provenance listing inputs and the formula.
- [ ] `research/retrieve.py` BM25 plus section heuristics.

**Acceptance:**
- [ ] For the 4 research companies **and** 1 unseen ticker: docs and tables are ingested live on the deployed API; an honest empty state for anything missing.
- [ ] Every `Metric` returned has complete provenance (`test_metric_has_provenance`); derived metrics list their inputs (`test_derived_metric_lists_inputs`).
- [ ] Outbound MB per ticker is recorded and within `MAX_OUTBOUND_MB_PER_DAY` if set.

### Phase 6: Pull analysis (ledger P0; others P1)
- [ ] P0 `research/guidance.py` per transcript (`long` route, strict schema, quote-verified, cached by doc hash + prompt version).
- [ ] P0 `research/ledger.py` matching, XBRL/screener crosscheck, deterministic verdicts.
- [ ] P0 `research/context.py` context builder that admits only allowed source classes (ARCH §4a).
- [ ] P0 `research/citations.py` claim validator plus number guard.
- [ ] P0 Financials + trajectory with a cited one-line read.
- [ ] P1 Balance sheet + cash (cut 6), Business snapshot (cut 3), Ask API (cut 2).
- [ ] `llm/` routes × slots, per-slot quota trackers, fallback, "paused" state (ARCH §6).

**Acceptance:**
- [ ] Ledger for all 4 research companies (subject to available transcripts): every promise cites a transcript page whose quote is found; every actual shows its source tag; 5 rows hand-checked and logged.
- [ ] Q4 = 100% valid citations; Q5 = 0 untraceable claims on 3 dossiers.
- [ ] Provenance boundary tests pass (EVALUATION §3, R-36 rows).
- [ ] Quota tests pass: primary 429 → fallback used; both exhausted → cached or "paused"; trackers are independent (Q12).

### Phase 7: Pull UI (P0; Ask/voice P1)
- [ ] Dossier tabs (Promises · Financials · Balance sheet & cash · Business); ledger scorecard; source tags on every number.
- [ ] Evidence bottom sheet showing the provenance chain.
- [ ] Ticker search for any NSE symbol; Dig in from Push.
- [ ] Ask box UI (cut 2); Voice "Listen" (cut 1).
- [ ] Design pass vs PRODUCT_SPEC §6.

**G3 acceptance (all required):**
- [ ] On a real phone against the deployed stack: dossiers render for 1 portfolio company, 1 research company and **1 ticker the owner picks blind** (Q6 partial).
- [ ] Tapping any number shows its source; tapping any claim shows the quote and page.
- [ ] Screener-sourced numbers are visibly labelled; no narrative claim shows a table as its only source (UI test).

### Phase 8: Hardening & reproducibility (P0)
- [ ] `scripts/build_seed_cache.py` builds the seed snapshot and seed cache for the 22 demo tickers (with `as_of`, prompt version and doc hashes); committed.
- [ ] Per-source fallback banner tested by forcing each source down.
- [ ] Run all EVALUATION §2 gates; record the results in PROGRESS.
- [ ] Debug drawer (usage meter).
- [ ] Playwright mobile smoke tests (fixture mode in CI; live mode against the deployed URL, run manually).

**G4 acceptance (all required):**
- [ ] All protected-core items (§1a) are demonstrated on the deployed URL from a real phone, with the evidence logged.
- [ ] Fresh-clone test: a new directory, `cp .env.example .env` plus keys, the documented commands → local app runs; offline test suite green.
- [ ] Service restart on Render → the app recovers with no manual steps (boot rebuild, seed cache).
- [ ] EVALUATION §2 results recorded, honestly, including any misses.

### Phase 9: Submission (P0)
- [ ] `docs/DEMO.md` scripted walkthrough (≤ 5 min) with the exact tickers and taps.
- [ ] README describes only implemented and verified behaviour, plus run steps.
- [ ] Writeup: what was built, decisions and trade-offs, what was left out (including any cuts), what's next.
- [ ] AI build history export and links.

**G5 acceptance:** every REQUIREMENTS §1 deliverable is present and its link opens on a phone; the owner signs off on the writeup.

## 3. Definition of done (every phase)
1. Relevant tests pass (`pytest`, `vitest`, `playwright` where applicable). Results are pasted into PROGRESS.
2. No secrets in the diff.
3. The phase's acceptance checklist is complete with evidence.
4. `docs/PROGRESS.md`, `docs/DECISIONS.md` and EVALUATION §3 statuses are updated.

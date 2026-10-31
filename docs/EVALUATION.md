# FINN — Evaluation & Traceability

## 1. How we map to the graders' signals
| Brief signal (REQUIREMENTS §3) | How FINN demonstrates it | Evidence for graders |
|---|---|---|
| Creativity, product sense | "Brief, not feed"; Push→Pull hand-off; Promises Ledger | The demo flow, plus the writeup's "point of view" paragraph |
| Judgment | Per-category treatments; EBITDA n/m for lenders; "couldn't verify" instead of guessing; filing-sourced bios | DECISIONS.md; ARCH §5.1 table |
| Architecture | Deterministic core; Claim/Citation schema; tiered LLM routing; content-hash cache | ARCHITECTURE.md; tests |
| Point of view on interaction | Ranked brief with visible filtering; evidence sheet; "Dig in" | The live prototype |
| Analysing, not summarising management | Promises Ledger with code-computed verdicts | Dossier for the ad-hoc tickers |
| Efficiency bonus | Rules before LLM; Groq/Gemini routing on free tiers; cache; request meter | Cost per report logged in PROGRESS §metrics |
| How you work with AI tools | CLAUDE.md rules, phased docs, build history | Repo + exported sessions |
| It runs | Live by default; per-source seed fallback; stateless server; fresh-clone and restart tests; real-phone checks | Deployed URL; DEMO.md |

## 2. Quality gates (measured before submission)
The targets below are what we aim for. The results get filled in **only** after they've been measured.

| # | Metric | Method | Target | Result |
|---|---|---|---|---|
| Q1 | Classifier accuracy (category) | ~60 hand-labelled announcements | ≥ 85% | — |
| Q2 | Must-read precision | Same set: items tiered Must that a human also marks material | ≥ 80% | — |
| Q3 | Results numbers exact | 5 golden filings × 4 metrics × 3 periods | 100% exact, or flagged "couldn't verify" (zero wrong numbers shown) | — |
| Q4 | Citation validity | All claims in 3 dossiers | 100% of rendered claims have ≥ 1 quote found on the cited page | — |
| Q5 | Outside-knowledge leakage | Manual review: each claim traceable to a provided chunk or metric | 0 untraceable claims | — |
| Q6 | Generalisation (live, R-30) | 3 tickers chosen blind by the user, typed into the **deployed** app | Each dossier renders from live data, or shows an honest "data unavailable" state; no crash; no manual steps | — |
| Q11 | Ask box grounding | 10 questions (5 answerable, 5 not answerable from filings) | Answerable: cited answer. Unanswerable: "Not answered in this company's filings". 0 uncited claims | — |
| Q12 | Quota resilience | Simulate a 429 on each slot independently, then on both slots of a route | Primary 429 → fallback slot (provider + model logged); a fallback 429 doesn't mark the primary exhausted; both out → cached or "paused"; no fabricated content | — |
| Q14 | Provenance completeness | All numbers and claims in 3 dossiers + 10 Push cards | 100% carry provenance; 0 narrative claims whose only support is `STANDARDIZED_TABLE`; 0 `EXTERNAL_WEB`/`MARKET_DATA` items in Pull | — |
| Q15 | Restart resilience | Restart the Render service; reload the phone | App recovers with no manual step; Push items identical after rebuild; device settings and triage intact | — |
| Q16 | Reproducibility | Fresh clone + `.env` keys + documented commands | Local app runs; offline suite green; demo tickers served from the seed cache with 0 LLM calls | — |
| Q13 | Design bar (R-34) | Review against PRODUCT_SPEC §6 checklist | Tabular figures; colour only carries meaning; light + dark; no decorative elements; user sign-off | — |
| Q7 | Mobile usability | Real phone, 390px width; Brief→card→Dig in→evidence | No horizontal scroll; tap targets ≥ 44px; flow under 4 taps | — |
| Q8 | Requests/tokens per dossier (cold) | Call log | Record actual; target ≤ 15 LLM requests per new ticker; compare against the observed limits in RESEARCH R14 (no capacity claim until then) | — |
| Q9 | Requests per dossier (warm/cached) | Call log | 0 LLM requests | — |
| Q10 | Latency: Brief load (warm) | Browser timing | < 2 s | — |

## 3. Requirement → test traceability
Status values: Not started · In progress · Implemented · **Verified** (acceptance criterion checked and recorded in PROGRESS).

| Req | Requirement (short) | Implementation approach | Acceptance criterion (verifiable) | Test(s) | Status |
|---|---|---|---|---|---|
| R-1, R-22, D-2 | Mobile-first, try on a phone | Next.js PWA, mobile-first CSS, deployed URL | Q7 passes on a real phone; manifest installable | Playwright mobile smoke; manual phone check | Not started |
| R-2 | Push + Pull modes | Brief/Alerts tabs (Push), Research tab (Pull) | Both reachable from bottom nav and work on real data | E2E smoke | Not started |
| R-3 | 15–20 portfolio companies | `config/portfolio.yaml`, validated in S5 | 15 ≤ count ≤ 20; every symbol resolves in prices and announcements | `test_portfolio_config` | Not started |
| R-4 | 3–5 ad-hoc companies | `config/adhoc.yaml` | 3–5 entries; each has ≥ 1 AR and ≥ 4 transcripts | `test_adhoc_config` + S5 log | Not started |
| R-5 | Generalise to any NSE ticker | Ticker → screener resolver; no per-ticker code paths | Q6 passes; grep finds no demo symbols in `research/` | `test_no_hardcoded_symbols`; Q6 | Not started |
| R-6 | EOD price & volume | `PriceSource` = NSE UDiFF bhavcopy or Upstox API (D-36; yfinance rejected) | ≥ 60 sessions per portfolio ticker available at boot; no raw bhavcopy committed | `test_udiff_parser` (synthetic fixture), `test_prices_incremental` | Not started |
| R-7 | NSE/BSE announcements | Official RSS poller → metadata log on `data` branch (D-33, D-37) | Continuous log since the first poll; gaps detected and shown; NSE/BSE duplicates collapsed | `test_rss_parse` (synthetic), `test_gap_detection`, `test_announcement_dedup` | Not started |
| R-8 | Taxonomy usage | Rule table + LLM fallback → REF categories | Q1 ≥ 85% | `test_classifier_rules`; Q1 script | Not started |
| R-9 | AR + transcripts | Company-website documents (curated `ir_sources.yaml`) + RSS attachments (D-34) | Docs found with page numbers for the 4 research companies; unseen ticker → found or honest empty state | `test_pdf_page_chunks` (synthetic PDF), S3 log | Not started |
| R-11 | Windowed digest, default 24h, user-chosen window | `/digest?from&to`; window chips | Default request = last 24h; custom range returns only in-window items; routine collapsed | `test_digest_window`; E2E | Not started |
| R-11 | Prioritised, routine collapsed | Scoring + tiers (ARCH §5.1) | Q2 ≥ 80%; routine tier hidden by default with a count | `test_scoring_tiers`; Q2 | Not started |
| R-12a | Material announcement alerts | Category rule, user-toggled | Toggling a category on/off changes whether an `AlertEvent` is created for a fixture announcement | `test_alert_category_rule` | Not started |
| R-12b | Volume / price alerts | Pure functions over `PriceBar` | Volume 2.1× → fires at 2.0, not at 2.5; price −5.2% → fires at ±5% | `test_alert_volume`, `test_alert_price` | Not started |
| R-12c | Configurable thresholds | Settings API + UI; global + per-ticker | A per-ticker override beats the global; persists across reload and API restart (device storage, sent with requests) | `test_rule_precedence`, `test_alerts_computed_from_request_rules`; E2E settings | Not started |
| R-13 | Management bio | Reg-30 annexure extractor + quote check; Tavily web background (labelled, linked) | For 2 fixture filings: name, role, date and profile extracted; profile quote found in the filing | `test_mgmt_profile` (golden) | Not started |
| R-14 | Results first cut (Rev, EBITDA, PBT, PAT; QoQ, YoY) | XBRL → PDF fallback → validation; derived EBITDA; lender n/m | Q3: zero wrong numbers; QoQ/YoY % recomputed in code match | `test_results_xbrl`, `test_results_pdf`, `test_ebitda_derivation`, `test_lender_nm` | Not started |
| R-15 | Per-type attention judgment | Treatment table (ARCH §5.1) | Every REF category has a defined treatment; one-liners only for Must/Glance | `test_every_category_has_treatment` | Not started |
| R-16, R-17 | Grounded Pull sections | Promises Ledger, Financials + trajectory, Balance sheet + cash, Business snapshot (no Bull/Bear, Q-10) | Each section renders for 3 tickers; Q4 = 100% | `test_section_schema`; Q4 | Not started |
| R-18 | Promised vs delivered (last 4 quarters) | Guidance extraction → ledger matching → code verdicts | For 2 ad-hoc tickers: each row has a promise citation, an actual (or "Too early"/"Not measurable") and a code verdict; spot-check 5 rows by hand | `test_verdict_rules`; manual spot-check log | Not started |
| R-19 | Primary sources only; no outside knowledge | Retrieval restricted to company docs; Claim/Citation schema; validator; number guard | Q4 = 100%, Q5 = 0; no news/broker URLs in any citation | `test_citation_validator`, `test_number_guard`, `test_citation_domains` | Not started |
| R-36 | Provenance & primary boundary (screener = numbers only) | Source-class model; context builder; claim validator; ledger crosscheck; UI source tags (ARCH §4a) | Q14 passes, plus each test below | `test_metric_has_provenance` (every Metric has class, name, locator, retrieved_at) · `test_derived_metric_lists_inputs` (formula + input provenance; effective class = weakest input) · `test_pull_context_rejects_external_and_market` (MARKET_DATA/EXTERNAL_WEB objects raise) · `test_narrative_claim_requires_primary_citation` (claim citing only a screener table is dropped) · `test_numeric_claim_matches_metric_or_quote` · `test_ledger_promise_is_primary` · `test_ledger_crosscheck_flags_mismatch` (XBRL vs screener > 1% → both shown, ⚠) · `test_api_numbers_carry_source_tag` (OpenAPI contract) · `test_cache_roundtrip_preserves_citations` · Playwright: screener-sourced figure shows "screener.in table" tag | Not started |
| R-23 | No AI slop; density & design | Design pass; caps on card text length | One-liner ≤ 140 chars; "why it matters" ≤ 1 sentence; user review sign-off | `test_text_length_caps`; review | Not started |
| R-25–27, R-35 | Model choice, efficiency, free tiers only | Gemini + Groq routes, rules first, cache, per-slot quota trackers | Q8/Q9 recorded; ≥ 70% of classifications made by rules; only google/groq/tavily keys in config; Google project has no billing linked (owner confirms); Q12 passes | `test_cache_hit`, `test_allowed_providers_only`; owner check | Not started |
| R-30 | Live by default, any ticker, one click | Render API with scheduled ingest + on-demand research; per-source seed fallback | Q6 passes on the deployed URL; snapshot banner appears only when a source is forced down | E2E on deployed URL; `test_source_fallback_banner` | Not started |
| R-31 | Ask box | ARCH §5.5 | Q11 passes | `test_ask_unanswerable`; Q11 | Not started |
| R-32 | Swipe triage | Gesture + button actions; local state | Swipe right → done (card leaves, counter increments); left → snoozed; state survives reload; buttons do the same | Playwright touch test | Not started |
| R-33 | Voice briefing | Web Speech API over card fields | "Listen" reads Must-read items in order; ≤ 60 s; hidden if unsupported; no LLM call made | Unit test of the script builder; manual phone check | Not started |
| R-34 | Design bar | PRODUCT_SPEC §6 | Q13 | Review | Not started |
| R-28 | Thin-but-working; must run | Protected core + cut order (PLAN §1a); per-source seed fallback; smoke tests; feature freeze | Deployed URL passes the smoke test on submission day; forcing a source down shows its seed data with an "as of" banner | E2E smoke (fixture + live); `test_source_fallback_banner` | Not started |
| R-37 | Reproducible demo | Committed config, seed snapshot, seed cache; DEMO.md; offline tests | Q16 passes | `test_seed_cache_hit_no_llm_calls`; fresh-clone check | Not started |
| ARCH §4b | Storage & restart behaviour | Stateless server; device storage; boot rebuild | Q15 passes | `test_boot_rebuild_from_seed`; `test_alerts_computed_from_request_rules`; Playwright: triage/settings survive reload; app works with storage disabled | Not started |
| ARCH §6.4 | Provider-agnostic adapters | Typed interfaces; one adapter module per provider | Swapping an adapter in config changes no business-logic file; every adapter passes its fixture contract test | `test_adapter_contract_<interface>` (per adapter); grep: no provider SDK imports outside `llm/` and `sources/` | Not started |
| D-29 | Classification on desc + attchmntText | Rule table over both fields | Fixtures: an "Outcome of Board Meeting" with results text → `results`; an "Updates" with "Earnings Call Transcript" → `earnings_call`; `hasXbrl` ignored | `test_classify_uses_attachment_text` | Not started |
| D-31 | Repo holds no raw third-party data | Content policy covering seed, seed-cache, fixtures and the `data` branch | CI fails on PDFs, bhavcopy/zip files, screener tables, or quote fields over one sentence anywhere in tracked data; fixtures are synthetic | `test_seed_content_policy`, `test_fixture_content_policy` | Not started (D-31 approved) |
| ARCH §6 | LLM slots & independent quotas | Routes × slots config; per-(provider, model) trackers | Q12 passes; startup rejects a slot with a missing provider key or model | `test_slot_config_validation`, `test_fallback_uses_named_provider_model`, `test_quota_trackers_independent`, `test_both_exhausted_serves_cache_or_paused` | Not started |
| D-3…D-6 | Repo, build history, writeup, email | Phase 9 checklist | Each item present and linked in the sent email | Manual checklist | Not started |

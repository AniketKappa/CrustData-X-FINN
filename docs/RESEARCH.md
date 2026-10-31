# FINN — Research Notes

> Findings from desk research on 2026-10-30. **Nothing here has been verified against live endpoints or our own accounts yet.**

**Evidence classes used below** (every service claim carries one):
- **[OFFICIAL]**: read on the provider's own docs or pricing page (via search-result extracts on 2026-10-30; direct fetching of these domains was blocked from this session).
- **[OBSERVED]**: measured on *our* accounts/keys. **None yet.** Filled in by Spike S6–S8 in R14.
- **[3RD-PARTY]**: blogs, aggregators, forums (including staff replies on forums). Indicative only; never used as a config value.
- **[UNVERIFIED]**: our assumption, not yet backed by any source.

Rule: config values and capacity plans may rely on **[OFFICIAL]** or **[OBSERVED]** only.

## R1. Reachability from Claude's build workspace (tested)
- **Root cause found (2026-10-30 01:45 IST).** The session proxy logged `connect_rejected … gateway answered 403 to CONNECT` for nseindia.com, screener.in, yahoo.com and api.bseindia.com. This is a **network policy** on the cloud environment ("Trusted" level), not the sites blocking us. Fix: set the environment's Network access to **Full** (user chose this, Q-5). It applies to new sessions. Docs: https://code.claude.com/docs/en/cloud-environments
- On 2026-10-30, Claude's cloud workspace could **not** reach `nseindia.com`, `api.bseindia.com`, `screener.in` or `query1.finance.yahoo.com`. It could reach PyPI and npm.
- **What this means**: the workspace's network allowlist blocks them. This says nothing about whether those sites work from the user's machine or a cloud host.
- **Consequence**: data-source spikes (S1–S5) must be run on the user's machine and on the candidate deploy host. Code written in the workspace must be tested with saved fixtures.

## R2. NSE corporate announcements (Confidence: M)
- NSE's website JSON APIs are known to need a browser-like **cookie session**, set by first visiting the homepage. Community reports describe time-based cookies.
  - Source: https://kiwix.lema.org/stackoverflow.com_en_all_2023-11/questions/63995488/unable-to-fetch-json-data-from-nse
  - Source (open-source client with a cookie session module): https://images.glama.ai/mcp/servers/icharshal/NSE-MCP
- Attachment PDFs are served from `nsearchives.nseindia.com/corporate/...` (observed in search results).
- Paid wrappers exist, e.g. an Apify actor at about $50 per 1,000 records (https://apify.com/nexgendata/nse-bse-announcements). These are **not used**, because the brief says free tiers suffice and cost discipline is graded.
- **To verify (S1)**: does the announcements endpoint work from (a) the user's machine and (b) the chosen host? What is the exact JSON shape, does it include an XBRL link, and what is the rate tolerance?

## R3. BSE corporate announcements (Confidence: M)
- `bse` on PyPI (BennyThadikaran/BseIndiaApi) is an unofficial client with `announcements(scripcode, fromDate, toDate)`. It needs BSE scrip codes (`getScripCode`).
  - Source: https://pypi.org/project/bse/ · docs https://bennythadikaran.github.io/BseIndiaApi/
- A forum commenter notes these unofficial tools are not real-time (https://tradingqna.com/t/corporate-announcement-data-api/178154). That's acceptable for polling.
- Attachments are served from `bseindia.com/xml-data/corpfiling/AttachHis/<uuid>.pdf`.
- **Role**: fallback, or a second source to deduplicate against, if NSE is blocked.

## R4. Results filings carry structured XBRL (Confidence: M-H)
- [3RD-PARTY summary of an official circular] An NSE circular (NSE/CML/2025/20, 2 Apr 2025) says that from **1 Apr 2025** listed entities must submit financial results through the **"Integrated Filing – Financial" XBRL** utility, alongside the PDF announcement on the same day.
  - Source: https://taxguru.in/?p=956595
- [OFFICIAL] NSE's financial-results page notes that results for the quarter ended **March 2025 onward** appear under Integrated Filing – Financials.
  - Source: https://www.nseindia.com/companies-listing/corporate-filings-financial-results
- The XBRL taxonomies are published by NSE: https://www.nseindia.com/static/companies-listing/xbrl-information
- **Implication**: the results card (P-3) can read structured numbers instead of parsing PDFs, for all quarters in our 4-quarter window.
- **To verify (S4)**: how to locate the XBRL instance for a given announcement, which tag names hold revenue, finance cost, D&A, PBT and PAT, and how consolidated vs standalone contexts are marked.

## R5. Management-change filings include a "brief profile" (Confidence: H for the practice, M for coverage)
- [OFFICIAL: the filings themselves] Reg-30 disclosures for director or KMP appointments include a table with "Reason for change", "Date of appointment" and "**Brief profile (in case of appointment)**", citing SEBI circulars (2015; SEBI/HO/CFD/CFD-PoD-1/P/CIR/2023/123 of 13 Jul 2023). A March 2026 filing cites a newer circular dated 30 Jan 2026.
  - Examples: https://bseindia.com/xml-data/corpfiling/AttachHis/622c81cb-dacb-4d76-8547-768e2faab35d.pdf · https://nsearchives.nseindia.com/corporate/AKSHAR_27012025163124_CS_Dheeraj_Kumar_Sahu.pdf · https://nsearchives.nseindia.com/corporate/PRSMJOHNSN_02032026082607_SEIntimationApptOfSanjayRoy.pdf
- Profile quality varies: some are a full career summary, others a single line.
- **Implication**: a primary, free, citable bio source. Web enrichment becomes optional (DECISIONS D-08).

## R6. screener.in (Confidence: M, with a conflict to resolve)
- Company pages (`/company/<SYMBOL>/`) expose quarterly results, P&L, balance sheet, cash flow, ratios and a documents section with annual reports and concalls (transcript / PPT / recording links).
  - Source: https://www.pkgstats.com/pkg:screener-scraper-pro
- **Conflict**: one Python wrapper's docs say "Login is required for all document methods" (https://sfinance.readthedocs.io/en/latest/_sources/usage.rst.txt). Another scraper claims document links come from public pages.
- Screener also has its own AI product over filings (https://screener.in/ai). It is not used; noted only as prior art.
- **To verify (S3)**: are AR and transcript links visible without login? Do the links point to BSE/NSE or company PDFs that can be fetched directly? What rate limits apply? Do the terms allow light personal use?
- **Fallback**: a company IR site, or the exchange "Annual Report" and transcript announcements (the `earnings_call` category carries transcripts as filings).

## R7. yfinance EOD prices (Confidence: M)
- [3RD-PARTY] Since 2025, `YFRateLimitError: Too Many Requests` has been widely reported, especially on bursts and on some IPs.
  - Sources: https://github.com/ranaroussi/yfinance/discussions/2431 · https://github.com/ranaroussi/yfinance/issues/2422
- **Mitigation**: one batched `yf.download` for all ~20 tickers per day, a local cache with only incremental fetches, exponential backoff, and pinning a recent yfinance version.
- **Fallback**: NSE's daily bhavcopy (the official EOD file for all securities). Its URL and format are to be verified in S2.

## R8. LinkedIn (judgment, not desk research)
- The brief names LinkedIn only as an example. Scraping LinkedIn needs a login and conflicts with its terms, so FINN won't do it.
- Plan: use the filing profile (R5) first. Optionally add a search-API lookup that returns a public URL plus snippet, shown as "external" and behind a flag.

## R10. Free LLM APIs
### Google Gemini API
| Claim | Class | Source |
|---|---|---|
| A free tier exists with "limited access to certain models", free input/output tokens, and content "used to improve our products" | [OFFICIAL] | https://ai.google.dev/gemini-api/docs/pricing |
| Models marked "Free of charge" on the free tier include Gemini 3.8 Flash, 3.6 Flash, 3.1 Flash-Lite, 3 Flash Preview, 2.5 Pro, Gemma 4 and Gemini Embedding. Gemini 3.1 Pro Preview is "Not available" on the free tier | [OFFICIAL] (pricing page as extracted 2026-10-30) | same |
| Grounding with Google Search is "Not available" on the free tier for Gemini 3.8 Flash | [OFFICIAL] | same. Irrelevant: Pull forbids web grounding anyway |
| Rate limits are measured as RPM, input TPM and RPD; applied **per project, not per API key**; **RPD resets at midnight Pacific** | [OFFICIAL] | https://ai.google.dev/gemini-api/docs/rate-limits |
| Exact per-model free limits are **not published** on that page; they "can be viewed in Google AI Studio" | [OFFICIAL] | same |
| Linking a billing account moves the project to Tier 1, where usage is charged. **So the FINN project must never have billing linked** (R-35) | [OFFICIAL] (tier table) | same |
| Free quotas are enforced per model, not shared across models | [3RD-PARTY] (forum answer citing the docs) | https://discuss.ai.google.dev/t/does-gemini-api-free-tier-have-a-shared-quota-across-models/184308 |
| Free quotas have been cut sharply without notice before (e.g. a Flash RPD drop reported Dec 2025); Google staff describe the free tier as best effort | [3RD-PARTY] (forum, incl. staff replies) | https://discuss.ai.google.dev/t/gemini-rate-limit-20-rpd/111274 |
| Specific numbers such as "Flash 10 RPM / 250 RPD" or "~20–50 RPD" | [3RD-PARTY], conflicting | various blogs. **Not used for planning** |

### Groq
| Claim | Class | Source |
|---|---|---|
| Free plan exists ($0, "Build and Test on Groq") | [OFFICIAL] | https://console.groq.com/settings/billing/plans |
| Limits are measured as RPM/RPD/TPM/TPD (plus ITPM/OTPM for some orgs); exact limits for *your* org are on the console limits page; cached tokens don't count | [OFFICIAL] | https://console.groq.com/docs/rate-limits |
| 429 responses carry `retry-after`; `x-ratelimit-*-requests` = RPD and `x-ratelimit-*-tokens` = TPM | [OFFICIAL] | same |
| Limits apply at the organization level; projects can only set lower limits | [OFFICIAL] | https://console.groq.com/docs/projects |
| Production model table lists `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (131K context; strict JSON-schema outputs supported) and marks `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` as "Contact Sales" | [OFFICIAL] | https://console.groq.com/docs/models · https://console.groq.com/docs/structured-outputs |
| Which of these models the **free plan** can call | [UNVERIFIED] | S6: `GET /openai/v1/models` plus one call each |
| Free-plan numbers such as "30 RPM, 1,000 RPD, 6K–12K TPM" | [3RD-PARTY] | https://eesel.ai/blog/groq-pricing. **Not used for planning** |

### OpenRouter (not used; recorded for completeness)
- `:free` models: 20 RPM; 50 requests/day unless ≥ $10 of credit was ever bought. [3RD-PARTY] https://www.truefoundry.com/es/blog/openrouter-rate-limits-your-free-tier-depends-on-what-youve-already-paid

## R11. Free people/web search: Tavily
| Claim | Class | Source |
|---|---|---|
| Researcher (free) plan: 1,000 API credits/month, no credit card | [OFFICIAL] | https://docs.tavily.com/documentation/api-credits · https://www.tavily.com/pricing |
| Basic search = 1 credit; advanced = 2 | [OFFICIAL] | api-credits page |
| Credits reset on the first day of each month | [OFFICIAL] | pricing page FAQ |
| Development key: up to 100 requests/min | [OFFICIAL] (help centre) | https://help.tavily.com/articles/9170796666-how-can-i-create-an-api-key |
| Result quality for Indian appointees | [UNVERIFIED] | S8 |

## R12. Free hosting & scheduling
| Claim | Class | Source |
|---|---|---|
| Render free web service spins down after 15 min without inbound traffic; spin-up takes about a minute | [OFFICIAL] | https://render.com/docs/free |
| **Ephemeral filesystem**: local files (incl. SQLite) are lost on redeploy, restart or spin-down; free services **cannot** attach a persistent disk | [OFFICIAL] | same |
| 750 free instance-hours per workspace per calendar month; spun-down time doesn't count; exhausting them suspends free services until next month | [OFFICIAL] | same |
| Render **may suspend** a free service that initiates uncommonly high outbound traffic (e.g. calling external APIs, transferring data) | [OFFICIAL] | same |
| Free Render Postgres: 1 GB, expires after 30 days (+14-day grace) | [OFFICIAL] | same · https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026 |
| A user's service was suspended while pinging every 5 min from GitHub Actions (attributed by Render staff to outbound traffic, not the pings) | [3RD-PARTY] (Render community) | https://community.render.com/t/how-much-api-calls-for-free-tier/22873 |
| Whether NSE/BSE/screener accept requests from Render IPs | [UNVERIFIED] | S1–S3 on host |
| Boot-rebuild time from the seed | [UNVERIFIED] | S7 |
| Vercel Hobby: free; functions up to 300 s; **non-commercial personal use only** | [OFFICIAL] | https://vercel.com/docs/plans/hobby · https://vercel.com/docs/limits |
| GitHub Actions `schedule`: shortest interval 5 min; can be delayed at high load (start of each hour); queued jobs may be dropped | [OFFICIAL] | https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows |
| Public repos: no billable Actions minutes on GitHub-hosted runners | [OFFICIAL] | https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/viewing-job-execution-time |
| Fly.io has no free tier for new users; Koyeb closed its free tier to new users | [3RD-PARTY] | render.com article above; https://kuberns.com/blogs/post/koyeb-alternatives/ |

## R13. Indian market data libraries (free, unofficial)
- **jugaad-data** (PyPI): works with the current NSE website, has built-in caching "to play nice with NSE", and downloads bhavcopy and historical stock data. A candidate fallback for EOD prices if yfinance rate-limits. Source: https://pypi.org/project/jugaad-data
- **bse** (PyPI): BSE announcements client (see R3).


---
# Part 2: Provider, data-source & product research (2026-10-30, ~03:20–04:00 IST)
Method: official docs read via search-result extracts (direct fetches of most provider domains are blocked from this session); NSE pages were inspected with **Claude in Chrome** in the owner's browser (read-only, one page view each, no sign-in used). Screener.in redirected to a signed-in dashboard, so its logged-in session was **not** used for research. All items were accessed on **2026-10-30**.
Novelty column: **EXISTS** = shipped elsewhere · **COMMON** = widely used pattern · **HYPOTHESIS** = our unverified idea.

## R15. NSE corporate announcements: observed response shape
- **Source:** https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=INFY (opened once in Chrome after loading https://www.nseindia.com/companies-listing/corporate-filings-announcements).
- **Establishes [OBSERVED]:** returns a JSON array. 74 complete records parsed (30-May-2026 → 29-Oct-2026; the page text was truncated at 50K chars). Fields: `an_dt, attFileSize, attchmntFile, attchmntText, bflag, csvName, desc, difference, dt, exchdisstime, fileSize, hasXbrl, old_new, orgid, seq_id, smIndustry, sm_isin, sm_name, sort_date, symbol`. Attachments are PDFs on `nsearchives.nseindia.com/corporate/…`.
- **Important for classification:** results appear as `desc = "Outcome of Board Meeting"`, and **earnings-call transcripts** appear as `desc = "Updates"`. The real signal is in `attchmntText` ("…regarding 'Earnings Call Transcript'"). `hasXbrl` was **true on all 74** records, including newspaper ads, so it does **not** identify results XBRL.
- **Limitations:** an undocumented web endpoint that needs a browser session (cookies). Under the Terms of Use (R16), automated collection is prohibited.
- **FINN learns:** (1) classify on `desc` + `attchmntText`, never `desc` alone; (2) concall transcripts and results are **themselves exchange filings**, a primary source that reduces dependence on screener.in for documents; (3) `seq_id` is the dedup key. **Novelty:** COMMON (many unofficial clients use this endpoint, e.g. NseIndiaApi).

## R16. Exchange & data-site terms (licensing flags) ⚠
| Source | What it says | Class | URL |
|---|---|---|---|
| NSE Terms of Use | Users are "prohibited to conduct any systematic or automated data collection activities (including scraping, data mining, data extraction and data harvesting)"; content may not be stored in an electronic retrieval system or redistributed without written permission | [OFFICIAL] | https://www.nseindia.com/static/nse-terms-of-use |
| NSE Copyright | Users may view, print and download content for **personal, non-commercial or educational** purposes, unaltered and with acknowledgement | [OFFICIAL] | https://www.nseindia.com/static/nse-copyright |
| BSE Disclaimer | Reproduction, redistribution or transmission of website information is "strictly prohibited" | [OFFICIAL] | https://www.bseindia.com/static/about/disclaimer.htm |
| BSE data products | Corporate announcements/results are sold as licensed data products (paid) | [OFFICIAL] | https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf |
| screener.in Terms | Licence is for "personal, non-commercial transitory viewing only"; no copying, public display, or mirroring | [OFFICIAL] | https://www.screener.in/guides/terms/ |
| screener.in support | "we don't provide APIs on Screener" (CSV export exists for screens) | [OFFICIAL] | https://support.screener.in/article/28-export-screen-results |
| yfinance | "the Yahoo! finance API is intended for personal use only"; not affiliated with Yahoo | [OFFICIAL] (project docs) | https://ranaroussi.github.io/yfinance/ |

**What this means.** Every free source the brief points to (NSE/BSE, screener.in, Yahoo) restricts automated, non-personal use, even though the brief calls this data "freely scrapable". FINN is a non-commercial, single-user prototype. **That reduces the risk but does not remove it, and it is a decision for the owner, not something to engineer around** (D-28). I am not a lawyer; this is a factual summary of the published terms.

**Mitigations already compatible with the architecture:** low volume (portfolio-scoped, polite intervals), on-demand fetches for Pull, attribution and deep links to originals, no rehosting of PDFs, and (new) **no raw exchange data or document text in the public repo** (D-31).

## R17. NSE end-of-day files (bhavcopy)
- **Source:** https://www.nseindia.com/all-reports · https://www.nseindia.com/static/resources/forms-formats-members
- **Establishes [OFFICIAL]:** the legacy CM bhavcopy CSV was discontinued w.e.f. 08-Jul-2024; the replacement is "CM-UDiFF Common Bhavcopy Final (zip)", with its format spec published on NSE's forms-and-formats page.
- **Limitations:** same Terms of Use (R16); the download URL pattern and access from Render are unverified (S2).
- **FINN learns:** the official EOD fallback for prices must parse the **UDiFF** format, not the old CSV. **Novelty:** COMMON.

## R18. yfinance  ⟶ *superseded by R25: Yahoo ToS prohibits automated collection; not a permitted method*
- **Sources:** https://ranaroussi.github.io/yfinance/ · https://github.com/ranaroussi/yfinance · rate-limit reports R7.
- **Establishes:** [OFFICIAL] unofficial wrapper over Yahoo's public endpoints, for personal use. [3RD-PARTY] frequent `YFRateLimitError` (429) since 2025.
- **Limitations:** no SLA; IP-based throttling; Yahoo terms apply. `.NS` coverage for all 22 symbols is unverified (S5).
- **FINN learns:** keep it behind a `PriceSource` adapter with the NSE UDiFF parser as the alternative; one batched call per day; cache. **Novelty:** COMMON.

## R19. Primary documents: where ARs and transcripts live
- **Exchange filings [OBSERVED R15]:** transcripts and results PDFs are filed as NSE announcements.
- **NSE annual-report/results listings [3RD-PARTY docs]:** NseIndiaApi v5 lists `annual_reports` and `financial_results` methods backed by NSE pages. https://bennythadikaran.github.io/NseIndiaApi/api.html · https://github.com/BennyThadikaran/NseIndiaApi
- **BSE [3RD-PARTY docs]:** `bse` package `announcements(page_no, from_date, to_date, scripcode, category, subcategory)`; attachments at `bseindia.com/xml-data/corpfiling/AttachHis/<name>`. https://bennythadikaran.github.io/BseIndiaApi/usage.html
- **screener.in [OFFICIAL]:** no API; documents section visibility when logged out is **[UNVERIFIED]** (S3); licence restrictions in R16.
- **Company IR sites:** layouts vary per company; scraping is fragile. Use them only as a fallback link.
- **FINN learns:** document discovery order should be **exchange filings → screener links → IR site**, and every document keeps its original URL (provenance). **Novelty:** COMMON.

## R20. LLM providers (update to R10)
**Gemini API**
- Structured output: `response_mime_type: application/json` + `response_json_schema`/`response_schema`; supports "a subset of the JSON Schema specification". [OFFICIAL] https://ai.google.dev/gemini-api/docs/generate-content/structured-output · https://ai.google.dev/gemini-api/docs/interactions/structured-output
- Two API surfaces exist: `generateContent` (docs label it "Legacy") and the newer Interactions API. Our adapter must hide which one is used. [OFFICIAL] https://ai.google.dev/api/interactions-api
- **Data use on the free tier [OFFICIAL]:** for Unpaid Services Google uses submitted content and responses "to provide, improve, and develop Google products"; **human reviewers may read** API input/output; "Do not submit sensitive, confidential, or personal information". (EEA/CH/UK users get paid-service terms.) https://ai.google.dev/gemini-api/terms
- Abuse-monitoring retention of 55 days for prompts, context and output. [OFFICIAL] https://ai.google.dev/gemini-api/docs/usage-policies
- Free-tier models confirmed "Free of charge" on the pricing page include Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Flash, 2.5 Flash-Lite, 2.5 Pro, Gemma 4, Gemini Embedding, **Gemini 3.5 Transcribe**, and **Gemini 3.8 Flash-Lite TTS**. [OFFICIAL] https://ai.google.dev/gemini-api/docs/pricing
- Per-model numeric quotas: not published (R10). [UNVERIFIED for our account]

**Groq**
- Production models include `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (131,072 context); strict JSON-schema mode is supported on gpt-oss-20b/120b. [OFFICIAL] https://console.groq.com/docs/models · https://console.groq.com/docs/structured-outputs
- Llama 3.x models are marked "Contact Sales" in the production table, so free-plan access is [UNVERIFIED].
- **Data use [OFFICIAL]:** "By default, Groq does not retain customer data for inference requests"; temporary logging only for reliability or abuse (up to 30 days); Zero Data Retention is available in Data Controls. https://console.groq.com/docs/your-data
- Prompt caching: automatic, volatile, expires after inactivity; cached tokens don't count toward rate limits. [OFFICIAL] https://console.groq.com/docs/prompt-caching · https://console.groq.com/docs/rate-limits
- Free-plan numeric limits: shown per org in the console only. [UNVERIFIED for our account]

**OpenRouter**
- Free variants (`:free`): **20 requests/min and 50/day**, rising to 1,000/day only after ≥ $10 of lifetime credit purchases; failed attempts count toward the daily cap. [OFFICIAL] https://openrouter.ai/pricing · https://openrouter.ai/collections/free-models · https://openrouter.ai/docs/api_reference/limits
- Some free models state that inputs and outputs **may be used for training** (e.g. listed poolside models). [OFFICIAL, per-model] https://openrouter.ai/collections/free-models
- Remaining quota is readable at `GET /api/v1/key` (`free_model_daily_requests`). [OFFICIAL]
- **FINN verdict:** 50 requests/day is too small for the primary slots, and the $10 unlock is a paid purchase (R-35), so it's rejected. It could be a last-resort third slot only with explicit owner approval.

## R21. Speech-to-text (STT)
| Option | Free? | Key facts | Class | Source |
|---|---|---|---|---|
| Browser `SpeechRecognition` (Web Speech API) | Free | **Limited availability (not Baseline).** On some browsers, e.g. Chrome, audio is sent to a server engine (not offline). Supported languages are browser-dependent and can't be listed programmatically. On-device `processLocally` is experimental | [OFFICIAL] | https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition · https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionErrorEvent/error |
| Groq Whisper (`whisper-large-v3`, `whisper-large-v3-turbo`) | Free plan exists; numbers per org | 99+ languages; FLAC/MP3/M4A/MPEG/MPGA/OGG/WAV/WEBM; max file 25 MB on the free tier; turbo has no translation | [OFFICIAL] | https://console.groq.com/docs/speech-to-text · https://console.groq.com/docs/model/whisper-large-v3 |
| Gemini 3.5 Transcribe | "Free of charge" on the free tier | Audio up to 1 h; diarisation, word timestamps, custom vocabulary. Free-tier data-use terms apply | [OFFICIAL] | https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe · pricing page |
| Deepgram | **Promotional credit**, not a free tier | "$200 credit then pay-as-you-go", no card | [OFFICIAL] | https://deepgram.com/pricing |
| ElevenLabs Scribe | Free plan 10K credits/month | Free plan has **no commercial licence** and requires attribution when publishing | [OFFICIAL] | https://elevenlabs.io/pricing · https://help.elevenlabs.io/hc/en-us/articles/13313564601361 |

**Scope note:** the owner chose voice *output* (the briefing), not voice input. STT is **out of MVP scope**; recorded for completeness only.

## R22. Text-to-speech (TTS)
| Option | Free? | Key facts | Class | Source |
|---|---|---|---|---|
| Browser `speechSynthesis` | Free, no key | `SpeechSynthesisVoice` is **Baseline, widely available since Sept 2018**; voices may be local or remote (`localService` flag); Chrome loads voices asynchronously (`voiceschanged`, Baseline since Sept 2022); utterance text max 32,767 chars | [OFFICIAL] | https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice · https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/voiceschanged_event · https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/text |
| Gemini 3.8 Flash-Lite TTS (`gemini-3.8-flash-lite-tts`) | "Free of charge" (Standard, free tier) | 101 languages; server-side audio generation; free-tier data-use terms; quotas unpublished | [OFFICIAL] | https://ai.google.dev/gemini-api/docs/pricing · https://ai.google.dev/gemini-api/docs/models |
| Groq Orpheus (`canopylabs/orpheus-v1-english`) | **Priced** ($22 / 1M chars); listed as a **Preview** model; free-plan access unverified | Replaced PlayAI TTS (shut down 31-Dec-2025) | [OFFICIAL] / [UNVERIFIED free access] | https://console.groq.com/docs/text-to-speech/orpheus · https://console.groq.com/docs/deprecations |
| ElevenLabs | Free 10K credits/month (~10 min audio) | No commercial licence on free; attribution required; voice library not available via API on free | [OFFICIAL] | https://elevenlabs.io/pricing · https://elevenlabs.io/docs/overview/capabilities/text-to-speech |
| Deepgram TTS | Promotional credit only | — | [OFFICIAL] | https://deepgram.com/pricing |

## R23. Existing products: what FINN can learn
| Product | What the source establishes | Interaction patterns | Limitations | FINN lesson | Novelty of FINN's analogue |
|---|---|---|---|---|---|
| **Quartr** (https://quartr.com/products/mobile-app · /features/ai-earnings-summaries · /features/transcript-search · /features/live-calls-and-transcripts) | [OFFICIAL] Free mobile app; AI chat over first-party IR material; "every output traceable to its original source"; summaries where "every line … includes direct source links"; keyword alerts; watchlists; live calls with synced transcripts; jump to Q&A; highlights | Feed of followed companies; event page with an Overview summary; tap a citation to open the exact page; text↔audio sync | Global first-party IR coverage. **Indian small/mid-cap coverage for our 22 names: [UNVERIFIED]** | Cited summaries and watchlist alerts are table stakes, not novel. Our differentiation must come from the **Promises Ledger** (promise→delivery verdicts) and **exchange-filing triage** for Indian companies | Cited summaries: **EXISTS**. Keyword/watchlist alerts: **EXISTS** |
| **AlphaSense** (https://help.alpha-sense.com/hc/en-us/articles/41669307479443 · https://www.alpha-sense.com/solutions/generative-ai-investment-research/) | [OFFICIAL] Smart Summaries on transcripts with **Highlights, Lowlights, Guidance** and **Q&A Highlights**; deep-linked citations to exact snippets; Generative Grid (same questions across many docs in a table); automations "tracking a company's self-reported guidance"; mobile app | Summary → citation → snippet; grid view across peers | Enterprise, paid; content includes broker research and expert calls (**forbidden for FINN Pull**, R-19) | **Guidance tracking exists commercially.** FINN's angle is *verdicts computed in code against reported numbers, Indian filings, free and primary-only*. A Grid-like peer view is a good post-MVP idea | Guidance tracking: **EXISTS**. Code-computed promise-vs-delivered verdicts with dual-source crosscheck: **HYPOTHESIS** (no evidence found either way) |
| **Screener AI** (https://www.screener.in/ai/) | [OFFICIAL] Q&A over Indian companies' ARs and earnings calls, pay-as-you-use | Ask box over filings | Paid; licence R16 | The Ask box concept **EXISTS** for Indian stocks; FINN must differentiate via the brief/triage workflow and the ledger | Ask box: **EXISTS** |
| Mobile research-card apps (e.g. DeepView, Fincards on the App Store) | [3RD-PARTY] card-based, thesis-first mobile reading | Card stacks; progressive disclosure | Marketing claims only | Card + progressive disclosure is a **COMMON** pattern; our "brief, not feed" with a visible hidden-routine count and swipe triage is a variation | Card UI: **COMMON**. Visible "N routine hidden" triage counter: **HYPOTHESIS** |

## R24. Retrieval
- **Facts:** per-company corpora are a few hundred pages (an AR plus ~5 transcripts) [UNVERIFIED size, S3]. Gemini Embedding is listed "Free of charge" on the free tier [OFFICIAL, pricing page] if BM25 proves insufficient.
- **FINN learns:** keep deterministic page-aware chunking + BM25 (no new service, no quota). Add embeddings only if EVALUATION Q4/Q11 fail, behind a `Retriever` adapter. **Novelty:** COMMON.

---
# Part 3: Source-access recheck for D-28 (2026-10-30, ~04:00–04:30 IST)
Not legal advice. These are factual readings of published terms, quoted briefly. Ambiguities are stated, not resolved.

## R25. Terms recheck, by dimension
Legend: ✗ = prohibited without permission · ~ = ambiguous / not addressed · ✓ = expressly allowed.

| Source / terms | Automated access | Personal use | Storage | Redistribution / display | Commercial use | Notes |
|---|---|---|---|---|---|---|
| **NSE Terms of Use** (https://www.nseindia.com/static/nse-terms-of-use) [OFFICIAL] | ✗ Item 9: "prohibited to conduct any systematic or automated data collection activities" | ~ No personal/commercial split; Item 8 grants a "limited right to access" | ✗ Item 8: no storing "in an electronic retrieval system" without permission | ✗ Item 8: no copying, reproducing, transmitting, "hyperlinked", distributing without prior written permission | ✗ no selling or licensing | **Item 8 carve-out:** "Unless the information or Content is available for download, not to aggregate, copy or duplicate"; what *is* allowed for downloadable content is not stated. The Terms **do not mention RSS**. A referenced "Hyperlinking Policy" was not readable here |
| **NSE Copyright** (https://www.nseindia.com/static/nse-copyright) [OFFICIAL] | ~ | ✓ view, print, download for "personal, non-commercial or educational purpose", unaltered, with acknowledgement | ~ | ✗ reproduction elsewhere | ✗ | Conflicts in tone with ToU Item 8; both apply |
| **NSE RSS page** (https://www.nseindia.com/static/rss-feed) [OFFICIAL] | ✓-ish: the page says subscribers "have immediate access to the latest information… without having to visit the website" via a feed reader | ~ | ~ | ~ | ~ | Officially offered machine-readable channel. **No reuse licence stated on the page.** Whether a *server application* polling RSS is a "feed reader" in NSE's sense is **ambiguous** |
| **BSE Disclaimer** (https://www.bseindia.com/static/about/disclaimer.htm) [OFFICIAL] | ~ | ~ | ~ | ✗ "Any reproduction, redistribution or transmission… strictly prohibited" | ✗ | BSE also offers official RSS (https://beta.bseindia.com/rss-feed.html) for Corporate Announcements, Annual Reports, Financial Results, Board Meetings and more; the page describes feed-reader use and states no reuse licence |
| **BSEPlus terms** (https://bseplus.bseindia.com/Terms_condition_Bseplus.htm) [OFFICIAL, scope uncertain] | ✗ no database "by regularly or systematically downloading and storing" | ✓ extracts for personal non-commercial use | ✗ | ✗ | ✗ | Applies to the BSEPlus site; whether it governs bseindia.com is **unclear** |
| **screener.in Terms** (https://www.screener.in/guides/terms/) [OFFICIAL] | ~ not named | ✓ "personal, non-commercial transitory viewing only" | ✗ (no copying/mirroring) | ✗ **"public display (commercial or non-commercial)"** prohibited | ✗ | Displaying screener tables inside FINN to reviewers looks like public display. Linking out is not restricted by the text read |
| **Yahoo Terms of Service** (https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html) [OFFICIAL] | ✗ must not "access or collect data… using any automated means… for any purpose without our express, prior permission" | ~ | ~ | ✗ | ✗ "may not access or reuse the Services… for any commercial purpose" | Clear on automation, so **yfinance is not a permitted method** |

## R26. Permitted-leaning access methods found
| Need | Method | Evidence | Remaining uncertainty |
|---|---|---|---|
| New announcements (Push) | **NSE RSS** `Online_announcements.xml`; **BSE Corporate Announcements RSS** | [OFFICIAL] feed list: https://www.nseindia.com/static/rss-feed. [OBSERVED, fetched 2026-10-30] item = company **name** (no symbol), attachment link (PDF/XBRL/zip), description with `|SUBJECT:`, pubDate; ~232 items covered only ~1 hour (18:13–19:14 IST) | Server polling vs "feed reader" (R25). **Rolling window**: frequent gapless polling is needed; no backfill. Name→symbol mapping needed |
| Results numbers | **NSE RSS** `Integrated_Filing_Financials.xml` → XBRL links | [OBSERVED, fetched 2026-10-30] 20 items covering ~2 h on 22-Oct-2026; title = company name; description = Original/Revision. The legacy `Financial_Results.xml` was **stale** (last items 24-Aug-2026, periods ending Mar-2021) | Same ambiguity; quarter/consolidation must be read from the XBRL itself (S4) |
| Annual reports | NSE RSS `Annual_Reports.xml`; BSE Annual Reports RSS; **company website** | [OFFICIAL] SEBI LODR Reg 46(2)(l): the listed entity's website must carry financial results and the "complete copy of the annual report" (https://www.sebi.gov.in/sebi_data/attachdocs/1441284401427.pdf) | Company-site terms vary; robots.txt must be respected |
| Earnings-call transcripts | **Company website** (legally mandated); exchange announcement attachments | [OFFICIAL, SEBI] Reg 46(2)(oa): transcripts on the website within five working days, mandatory from 1-Apr-2022 (https://www.sebi.gov.in/sebi_data/attachdocs/nov-2022/1668240795810.pdf). An Expert Committee recommended keeping transcripts on the website for 5 years (https://www.sebi.gov.in/sebi_data/meetingfiles/oct-2024/1728300135040_1.pdf); whether adopted is **unverified** | Per-company page structure (discovery). Companies may link to exchange pages instead of hosting (allowed by the committee's "curated links" recommendation) |
| Balance sheet & cash flow | **Half-yearly results** include a statement of assets & liabilities and cash flows | [OFFICIAL] SEBI LODR FAQ on Reg 33(3)(f) (https://www.sebi.gov.in/sebi_data/faqfiles/apr-2025/1745399101865.pdf) | Requires parsing results filings |
| EOD prices | **NSE CM-UDiFF bhavcopy** (one downloadable file per trading day) | [OFFICIAL] https://www.nseindia.com/all-reports | Falls under ToU Item 8's "available for download" wording, but Item 9 (automated collection) still applies to a scheduled download. **Ambiguous** |
| EOD prices (alt.) | **Broker API: Upstox Historical Candle Data** | [OFFICIAL docs] daily intervals available (https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/); [3RD-PARTY forum, Upstox staff] "balance offering APIs for free for everyone" | **Upstox API terms, auth requirement, redistribution/display rights: UNVERIFIED.** Likely needs an Upstox account |
| Standardised multi-year tables | **Derive from filings** (XBRL for new quarters, results PDFs for history) | Follows from R25 (screener display restriction) | Much more parsing effort than screener tables |

## R27. Trade-off: Push workflow vs permitted-leaning access
- **RSS-only Push**: officially offered and no bypassing, but the feed is a ~1-hour rolling window. A *24-hour digest* needs **gapless polling around the clock**. GitHub Actions schedules can be delayed or dropped [OFFICIAL, R12], and Render's disk is ephemeral, so the metadata log must persist somewhere durable or the digest loses history on restart. **A 7-day window on first deploy is impossible** (history only accumulates from the first poll).
- **Per-company JSON endpoint** (R15): gives full history per symbol on demand (good for a 7-day digest and unseen tickers), but it is automated collection from the website under ToU Item 9.
- **Documents for history** (last 4 quarters): company websites are the legally mandated home, but discovery per company is fragile. For the 22 demo companies a **curated, verified IR-URL config** is reliable; unseen tickers are best-effort.
- None of these choices is a legal determination. The owner chooses the risk posture (D-28).

## R14. Observed account limits (filled in by Spikes S6–S8; **empty until measured**)
| Provider / model | Console-shown limits | Observed behaviour | Date |
|---|---|---|---|
| — | — | — | — |

## R9. Open research items
| # | Question | Spike |
|---|---|---|
| 1 | NSE endpoint reachable from host? | S1 |
| 2 | Bhavcopy URL/format as yfinance fallback | S2 |
| 3 | Screener document links without login | S3 |
| 4 | XBRL tag mapping for results | S4 |
| 5 | Symbol validity of candidate portfolio | S5 |
| 6 | Free-tier limits and model IDs for Gemini + Groq keys | S6 |
| 7 | NSE/screener reachable **from Render** | S1–S3 repeated on host |
| 8 | ~~Render free disk persistence~~ Resolved [OFFICIAL]: ephemeral, no disk on free. Remaining: boot-rebuild time | S7 |
| 9 | Which Groq/Gemini models the free keys can actually call | S6 |
| 10 | Outbound MB per ticker ingest (Render suspension risk) | S7 |
| 11 | Owner decision on data-licensing risk (R16) | D-28 |
| 12 | Quartr coverage of our 22 Indian companies (positioning only) | optional |
| 13 | Logged-out visibility of screener documents (not tested: Chrome session was signed in) | S3 |

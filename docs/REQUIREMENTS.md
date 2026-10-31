# FINN — Requirements

Source documents (read in full on 2026-10-30):
- **[MAIN]** `1. ENAM AI Engineer Build Challenge Main.pdf` (4 pages, released Tue 27 Oct 2026)
- **[REF]** `2. ENAM AI Engineer Build Challenge Reference.pdf` (3 pages, "Announcement Categories & Financial Glossary")

Page references below are to these PDFs (e.g. MAIN p2).

Every requirement gets one of five labels. **Examples from the brief are not mandatory requirements**, and the labels keep them apart:

| Label | Meaning |
|---|---|
| **M — Mandatory** | Stated as required, as a deliverable, or as a hard discipline. Missing it fails the brief. |
| **S — Strong signal** | Described as an example, but the brief explicitly says it "loves" it or values it "most". It is optional, but leaving it out costs evaluation signal. |
| **O — Optional menu item** | Listed as one example among several ("treat them as a menu", "illustrations, not a checklist"). |
| **I — Proposed innovation** | Our own idea. Nothing in the brief asks for it. Needs owner approval. |
| **A — Assumption** | Our interpretation of something the brief leaves open. Must be validated (see §6). |

---

## 1. Deadline & deliverables (verbatim facts)

| ID | Fact / requirement | Source | Label |
|---|---|---|---|
| D-1 | Deadline: **Sunday, November 1, 2026**. The time of day and time zone are not stated. | MAIN p1 | M |
| D-2 | Deliverable: a **mobile-first working prototype**, such as a deployed link, Expo/TestFlight, or responsive web. It must be "easy for us to try on a phone". | MAIN p1, p4 | M |
| D-3 | The **GitHub repository**. | MAIN p4 | M |
| D-4 | **AI build history**: coding-agent and LLM conversations (exports or share links). | MAIN p4 | M |
| D-5 | A **short writeup in the covering email** covering what was built, key decisions and trade-offs, what was deliberately left out, and where it goes next. | MAIN p4 | M |
| D-6 | Email to **assessment@enam.com** with the subject **"ENAM - IIT screening - 2027"**, including links and attachments. | MAIN p4 | M |

## 2. Product requirements

### 2.1 Core shape
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-1 | FINN is a **mobile-first** financial investment agent. | MAIN p1 | M |
| R-2 | It works in two interaction modes: **Push** (proactively tells you what changed and why you should care) and **Pull** (research or analysis on demand). | MAIN p1 | M |
| R-3 | A mock **portfolio of 15–20 NSE/BSE-listed companies**, mixed across sectors and sizes. | MAIN p1 | M (the count) / S (the mix) |
| R-4 | **3–5 ad-hoc research companies**, which may be outside the portfolio, for demoing Pull. | MAIN p1 | M |
| R-5 | Research must **generalise to any NSE ticker where data is available**, with nothing hard-wired to the demo set. "We may point it at a company you didn't pick." | MAIN p2 | M |

### 2.2 Data sources (backend is "plumbing, not the point")
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-6 | **End-of-day price and volume** for portfolio stocks. yfinance with `.NS`/`.BO` is suggested; "anything equivalent works". | MAIN p2 | M (the data) / O (the provider) |
| R-7 | **Corporate announcements and filings** from NSE/BSE for those stocks. | MAIN p2 | M |
| R-8 | The announcement taxonomy in REF §1 (17 categories) may be used, adapted or ignored. | MAIN p2, REF p1 | O |
| R-9 | **Fundamentals**: annual reports and concall transcripts, via links on screener.in or the company's IR site. | MAIN p2 | M |
| R-10 | "Don't over-engineer" the data layer. | MAIN p2 | Guidance |

### 2.3 Push
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-11 | **Windowed digest**: every filing or announcement across the portfolio for a user-chosen window (default **last 24h**, user can pick the period), **filtered and prioritised**, with routine items **collapsed or hidden**. | MAIN p2 | S (the brief calls it one of "two flavours" of Push; we treat it as core) |
| R-12 | **Triggered alerts** when something crosses a threshold. | MAIN p2 | S (core) |
| R-12a | Alert on a material announcement of a type the user cares about (results, M&A, management change, etc.). | MAIN p2 | S |
| R-12b | Alert on an unusual EOD move, e.g. volume above ~2× its recent average or price beyond ±X% in a day. | MAIN p2 | S |
| R-12c | **The threshold must be configurable** ("I decide what 'unusual' means"). | MAIN p2 | M (explicit "Make the threshold configurable") |
| R-13 | **Management change**: a short background or bio of the incoming person (LinkedIn is given as an example source). | MAIN p2 | S ("two examples we love") |
| R-14 | **Quarterly results**: a first cut of **Revenue, EBITDA, PBT, PAT**, QoQ and YoY, taken from **the actual results filing**. | MAIN p2 | S ("two examples we love") |
| R-15 | For each other announcement type, decide what earns attention: a one-line summary or just the filing at the right priority. "That judgment is the point." | MAIN p2 | S (judgment signal) |

### 2.4 Pull
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-16 | On-demand analysis of a company, **grounded in fundamentals** (annual reports and concall transcripts). | MAIN p2 | M |
| R-17 | Menu of 8 outputs: Business snapshot, Financial snapshot, Trajectory, Balance sheet, Cash quality, Narrative vs numbers, Guidance, Bull vs bear. "Pick what you build and how deep you go." | MAIN p3 | O (each item) |
| R-18 | **Worked example: promised vs delivered** over the last four quarters, comparing management's guidance and growth commentary with actual results. "The kind of thing we value most." | MAIN p3 | S (the highest-value Pull signal) |
| R-19 | **Primary sources only** for Pull: no broker notes, news or research reports, and no leaning on the model's outside knowledge of the company. | MAIN p3, REF p2 | **M (hard discipline)** |
| R-20 | Push-side enrichment, such as a person's professional background, is explicitly exempt from R-19. | MAIN p3 | Clarification |

### 2.5 Interaction & quality bar
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-21 | The interaction model is ours to choose; experiment beyond the obvious (chat, voice, copilot, dashboard, …). "Show a point of view." | MAIN p3 | S |
| R-22 | Everything mobile-first. | MAIN p3 | M |
| R-23 | "No AI slop": core, concise, beautifully presented, interactive. **Density and design both count.** | MAIN p3 | S (graded) |
| R-24 | Saves the investor time and shows only what's important. | MAIN p1, p3 | S |

### 2.6 Tools, cost, scope
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-25 | No restriction on models. Choosing the right tool per step is itself evaluated. | MAIN p3 | Constraint / signal |
| R-26 | Doable on free tiers; no spending needed. | MAIN p3 | Constraint |
| R-27 | **Efficiency earns bonus points**: model routing, caching, chunking. | MAIN p3 | S (bonus) |
| R-28 | **Thin-but-working beats broad-but-broken.** "A demo that doesn't run is the worst outcome." | MAIN p3–4 | **M (in effect)** |
| R-29 | "Build the smallest thing that proves you can build the real thing well." | MAIN p4 | Guidance |

## 3. Evaluation signals (what graders look at)
Taken directly from the brief. These are the things we optimise for (see `EVALUATION.md`):
1. **How you build, what you choose to build, creativity and judgment** — "not completeness or polish" (MAIN p1).
2. **Creativity, product sense, judgment, architecture** (MAIN p3).
3. A **point of view on interaction**, not just data display (MAIN p3).
4. **Frontend/product is "the heart"**: "That's where we most want to see how you think" (MAIN p1–2).
5. **Analysing management, not summarising it** (promised vs delivered) (MAIN p3).
6. **Efficiency / cost discipline** as a bonus (MAIN p3).
7. **How you work with AI tools**, seen through the build history (MAIN p4).
8. **It runs.** A broken demo is the worst outcome (MAIN p4).

## 4. Explicitly NOT required (examples we are free to skip)
- Any specific Pull section beyond what we choose (R-17 is a menu).
- LinkedIn specifically, which is given only as an example source for R-13.
- yfinance specifically, or the REF taxonomy specifically.
- Native app, voice, chat, or any particular interaction paradigm.
- Completeness or broad polish.

## 5. Proposed innovations (I) — pending owner approval
| ID | Proposal | Why |
|---|---|---|
| I-1 | **"Brief, not feed"**: the Push home is a ranked brief ("3 things that matter today") plus an explicit count of hidden routine filings, not a chronological list. | Matches "filtering is the scarce skill". |
| I-2 | **"Why it matters" line on every surfaced card**: what changed, why care, and a link to the evidence. | Turns Push into judgment, not aggregation. |
| I-3 | **Push → Pull hand-off ("Dig in")**: any pushed card opens Pull, pre-scoped to that company and question. | A single workflow instead of two separate apps. |
| I-4 | **Promises Ledger**: a scorecard of every guided metric with promised vs delivered and a code-computed verdict, each cell cited to transcript page and results quarter. | The brief's most-valued Pull output, made glanceable on mobile. |
| I-5 | **Evidence-first UI**: tap any number to see the source document, page and snippet. Uncited claims are not rendered. | Enforces R-19 visibly and builds trust. |
| I-6 | **Bio from the filing itself**: SEBI Reg-30 appointment disclosures typically include a "brief profile" annexure (see RESEARCH R5). Extract it first; optional web enrichment second. | Reliable, primary and free, and avoids scraping LinkedIn. |
| I-7 | **Lender-aware results card**: for banks/NBFCs, EBITDA is shown as "not meaningful" and not computed. | Shows domain judgment; avoids a fake number. |
| I-8 | **Seed snapshot as per-source fallback** (revised by Q-3/R-30): live is the default; a committed, "as of"-labelled seed is served only for a source that is failing. | Addresses R-28 without weakening R-30. |
| I-9 | **Usage meter**: requests and tokens per research report, by route/slot/provider/model, shown in a debug drawer (dollar cost is $0 on free tiers). | Makes R-27 legible to graders. |

## 6. Assumptions requiring validation
| ID | Assumption | How we'll validate | Owner |
|---|---|---|---|
| A-1 | ~~Deadline time-of-day~~ **Resolved (Q-4):** the user owns the submission timing. The plan targets Sunday 1 Nov 2026. | — | User |
| A-2 | "The moment something crosses a threshold" is met by **EOD evaluation** for price/volume (the data is EOD by definition) and **polling** (≈15 min) for announcements. True real-time is not required. | Ask the user; stated in the writeup. | User |
| A-3 | NSE/BSE announcement endpoints and screener.in pages are reachable from (a) the Claude Code cloud environment once it is set to **Full** network access (Q-5) and (b) Render. **Unverified**: the old environment was policy-blocked (403). | Spikes S1–S3 in the new session, then repeated on Render. | Phase 1 |
| A-4 | **Reopened (D-35, owner decision):** Q-7 allowed screener.in tables, but screener's licence prohibits public display (RESEARCH R25). Previously: yes, with the boundary defined in R-36 and ARCHITECTURE §4a: screener.in tables may supply **numbers only**, always labelled; narrative claims and the "promised" side of the ledger must cite primary documents. | — | User |
| A-5 | NSE "Integrated Filing – Financial" XBRL is retrievable per filing and yields Revenue, PBT, PAT, finance cost and D&A, so EBITDA can be derived. | Spike S4. | Phase 1 |
| A-6 | EBITDA is **derived**, because filings rarely state it: `PBT + finance costs + D&A − other income`. It is labelled "derived" in the UI, with the formula shown. | Owner sign-off (DECISIONS D-07). | User |
| A-7 | Single-user demo; no auth or multi-tenant requirements. | Brief is silent; low risk. | — |
| A-8 | A web PWA counts as "easy to try on a phone". The brief lists responsive web as acceptable. | Brief text (MAIN p4). | — |
| A-9 | The **user-confirmed** portfolio and research list (Q-6, PRODUCT_SPEC §5) map to valid NSE symbols. The names are confirmed; the **symbols are not yet verified**. | Spike S5. | Phase 1 |
| A-11 | **Free-tier capacity is enough for the demo** (22 seeded tickers plus a few unseen tickers per day). **Unverified**: official docs don't publish free numbers for Gemini; Groq's are per-org in the console. | S6 + R14; seed cache reduces load | Phase 1 |
| A-12 | The groq/gemini models we choose are callable on free keys. **Unverified** (Groq lists Llama models as "Contact Sales"). | S6 | Phase 1 |
| A-13 | Per-device browser storage is acceptable for threshold overrides, read state and triage (single-user demo; no server persistence on Render free). | Owner review of ARCH §4b | User |
| A-10 | **Resolved (Q-1):** free-tier LLMs only, Gemini (Flash family) + Groq. The user will create both free keys and a free Tavily key. | — | User |

## 7. Traceability
Each requirement's implementation approach, verifiable acceptance criterion and test(s) are tracked in [`EVALUATION.md` §3](EVALUATION.md#3-requirement--test-traceability).

## 8. Clarifications from the user (2026-10-30, 01:38–01:50 IST)
These answers are binding unless the user changes them.

| # | Question | User's answer | Effect |
|---|---|---|---|
| Q-1 | LLM provider | **Gemini + Groq, free tiers only** | DECISIONS D-15; ARCH §6 |
| Q-2 | Hosting | **Vercel (web) + Render free (API)** | DECISIONS D-13 (resolved), D-16 |
| Q-3 | Where development happens | Clarified: **the deployed app must fetch and process live data for any NSE ticker in one click**, the same way the designs/wireframes show | **New hard requirement R-30** below; snapshot demoted to emergency fallback only |
| Q-4 | Deadline time | "Do what I say": the user controls timing | A-1 resolved; plan targets 1 Nov |
| Q-5 | Network access for the build environment | **Full** network access on the Claude Code cloud environment | Phase 1 starts in a new session with Full access |
| Q-6 | Demo companies | **Confirmed list** (see PRODUCT_SPEC §5) | A-9 narrowed to symbol checks |
| Q-7 | Screener.in tables for Pull numbers | **Yes**, labelled | A-4 resolved |
| Q-8 | Management bios | **Filing profile + Tavily web search** (free tier) | DECISIONS D-08 updated |
| Q-9 | Extra interaction styles | **Ask box on a company, Swipe triage, Voice briefing** | New R-31, R-32, R-33 |
| Q-10 | Research sections besides the Promises Ledger | **Business snapshot; Financials + trajectory; Balance sheet + cash quality.** Bull vs Bear **not selected** | PRODUCT_SPEC §3.2 |
| Q-11 | Visual direction | "Simple, elegant, premium; designed by an experienced product designer for professional investors; clean layouts, excellent typography, precise data visualisation, high density without clutter; no generic AI aesthetic, gradients, flashy animation or decoration; every decision serves the workflow" | New R-34; PRODUCT_SPEC §6 |

### New requirements from clarifications
| ID | Requirement | Source | Label |
|---|---|---|---|
| R-30 | **Live by default.** The deployed app fetches, processes and renders real data for portfolio stocks **and any NSE ticker the reviewer types**, with no manual steps. Snapshot data may be used only as a clearly labelled fallback when a source is down. | User Q-3 + MAIN p2 | **M** |
| R-31 | **Ask box**: a free-form question about one company, answered only from that company's primary documents, with citations. | User Q-9 | M (user-requested) |
| R-32 | **Swipe triage** on the brief: swipe to mark done, snooze, or dig in. | User Q-9 | M (user-requested) |
| R-33 | **Voice briefing**: the phone reads out today's brief. | User Q-9 | M (user-requested; lowest in the build order) |
| R-34 | Visual quality bar as stated in Q-11. | User Q-11 + MAIN p3 | M |
| R-35 | **Zero paid APIs.** Every external API (LLM, search, hosting) must be on a free tier with no card needed. | User request (2026-10-30) + MAIN p3 | M |
| R-36 | **Source provenance & primary boundary.** Every number and claim the API returns carries provenance (source class, name, locator, retrieval time). In Pull, narrative claims must cite a primary document; screener.in tables may support numbers only and are always labelled; market data and web results never enter Pull. | MAIN p3 + Q-7 (planning pass 2026-10-30) | M |
| R-37 | **Reproducible demo.** From a clean clone plus free keys, documented steps produce the same demo: a committed portfolio config, seed snapshot and seed cache (with `as_of` and prompt version), a scripted walkthrough (`docs/DEMO.md`, Phase 9), and offline fixture-based tests. | MAIN p4 ("a demo that doesn't run is the worst outcome") | M |

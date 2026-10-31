---
title: FINN
emoji: 📈
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Mobile-first investment intelligence for NSE portfolios
---

# FINN — Financial Investment Agent

A mobile-first investment intelligence agent for Indian equities (NSE/BSE), built for the ENAM Holdings AI Engineer Build Challenge (deadline **1 Nov 2026**).

- **Push**: tells you what changed across your portfolio and why it matters, through a prioritised digest and configurable alerts.
- **Pull**: on-demand research on any NSE company, grounded only in primary sources (annual reports, concall transcripts, filings), with every claim cited.

## Status
- **Phase 0 (planning) is complete.** Design prototype v2 (`design/prototype/`) works on labelled fixture data.
- **Push data pipeline (backend) is implemented and tested offline:** prices and volume, announcements, classification, ranking, digest, API and CLI. **125 tests pass.** No live source has been verified yet; see "Live integrations" below.
- **The app runs end to end for Push:** the backend serves the web app at http://localhost:8000 and the Briefing reads `/v1/digest` (live data). Companies and Research still run on fixture data.
- Not built yet: Pull research (company pages from filings, Q&A), LLM features, the Next.js rebuild and deployment. See [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Planned MVP
- Ranked daily brief with a window selector (24h default) and routine filings collapsed
- Alerts for price moves, volume spikes and material announcement types, with user-set thresholds
- Results card: Revenue, EBITDA (derived), PBT, PAT, QoQ and YoY, taken from the filing
- Management-change card with the appointee's profile from the filing
- Research dossier with a **Promises Ledger**: management's guidance vs what was delivered, last 4 quarters, every cell cited

Full scope, including what's out: [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md).

## Docs
| Doc | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Rules for AI coding agents on this repo |
| [REQUIREMENTS](docs/REQUIREMENTS.md) | Requirements extracted from the brief, labelled mandatory / signal / optional / innovation / assumption |
| [PRODUCT_SPEC](docs/PRODUCT_SPEC.md) | Point of view, MVP scope, screens, demo companies |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design, pipelines, data model, LLM routing |
| [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) | Backward schedule, phases, prioritised tasks, cut lines |
| [RESEARCH](docs/RESEARCH.md) | Data-source findings and what still needs verifying |
| [DECISIONS](docs/DECISIONS.md) | Decision log |
| [EVALUATION](docs/EVALUATION.md) | Quality gates and requirement → test traceability |
| [PROGRESS](docs/PROGRESS.md) | What's actually done and verified |

## Run the app
One command starts the API and the web app together:
```powershell
cd "C:\Enam Holding\backend"
python -m pip install -r requirements.txt     # first time only
python -m uvicorn finn.api:app --port 8000
```
Open **http://localhost:8000**. On start-up the server fetches live prices and NSE filings in the background (about a minute); the Briefing shows a status line until that finishes. **Refresh** in the Briefing fetches again (cached sources are skipped). The phone layout is in Chrome DevTools (F12, then Ctrl+Shift+M); from a phone on the same Wi-Fi, run uvicorn with `--host 0.0.0.0` and open `http://<your-PC-IP>:8000`.

The app has three tabs: **Briefing**, **Portfolio** (search to add any NSE/BSE stock, Edit to remove; saved in `data/portfolio.json`) and **Research** (prepared examples until Pull is built). Tap any company to open its page: price chart, latest results, key ratios, news, exchange filings, annual reports and concall transcripts.

What is live: **the Briefing**, in the brief's sections: Market moves (Yahoo end-of-day price/volume against your thresholds), Results (with Revenue / EBITDA / PBT / PAT, QoQ and YoY from Screener), Management changes, Deals, Legal & regulatory and Other updates, each mixing NSE filings and trusted news headlines (labelled), with routine filings collapsed, Done/Snooze, data notes and a spoken briefing. What is still demo: **Research** answers (prepared examples). For demo data everywhere, set `$env:FINN_DATA_MODE="fixture"` first.

## Setup (backend)
Requires Python 3.10+.
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest                   # 125 offline tests, no network
python -m finn digest --fixture    # demo digest on fictitious companies, no network
python -m finn check-live          # one real call per source; run on a machine with internet access
python -m finn refresh             # live fetch into data/finn.db (cached; respects TTLs)
python -m finn digest --window 24  # 24 | 72 | 168 hours; --price-pct 4 --vol-mult 2.5 to override alerts
uvicorn finn.api:app --reload      # API: /health, /v1/digest, /v1/market, /v1/sources, POST /jobs/refresh
```
Set `FINN_DATA_MODE=fixture` to run the API on fixtures. Copy `.env.example` to `.env` for settings; never commit `.env`.

### Backend layout
| Path | What it does |
|---|---|
| `backend/config/portfolio.yaml` | Demo portfolio: 18 holdings across 15 sectors and three sizes, plus 4 research companies. Demo choices only; any NSE symbol or BSE code works |
| `backend/config/alerts.yaml` | Price % and volume-multiple thresholds, lookback, minimum history, staleness |
| `backend/config/ranking.yaml` | Materiality per category, weights, recency half-life, tier cut-offs, window options |
| `backend/config/sources.yaml` | Source URLs, enable flags, verification status, timeouts, retries, TTLs |
| `finn/symbols.py` | NSE/BSE ticker normalisation (`INFY`, `INFY.NS`, `NSE:INFY`, `500209`, `500209.BO`, `BSE:500209`) |
| `finn/providers/prices.py` | yfinance adapter and deterministic fixture provider |
| `finn/providers/announcements.py` | NSE RSS, NSE JSON (undocumented, backfill), BSE RSS parsers and fetchers; dedup key |
| `finn/market.py` | Daily % change, volume vs N-session average, staleness, alerts |
| `finn/classify.py` | Rule classifier over the 17 REF categories, reading subject and attachment text |
| `finn/rank.py` | Explainable score and tiers |
| `finn/pipeline.py` | Refresh (network, cached) and digest (store only) |
| `finn/store.py` | SQLite cache of bars, announcements and the fetch log |
| `finn/api.py`, `finn/__main__.py` | FastAPI app and CLI |

## Live integrations
Checked with `python -m finn check-live` on the owner's PC, 30 Oct 2026 05:20 IST. The build environments themselves can't reach these sites (proxy 403). Run `python -m finn inspect-rss` to see how FINN reads every item in the current RSS feed.

| Integration | State in code | What's unverified |
|---|---|---|
| yfinance EOD prices (`.NS` / `.BO`) | **Verified working** (INFY.NS, 9 bars) | The latest bar was 28 Oct when 29 Oct was expected, so Yahoo may lag a day. Rate limits, BSE `.BO` coverage and the full portfolio are untested |
| NSE RSS `Online_announcements.xml` | **Verified working** (5 items parsed at 05:20) | No portfolio company was in the feed, so name→symbol mapping is unproven. Rolling-window length at busy times is unmeasured |
| NSE corporate-announcements JSON (undocumented) | **Blocked: HTTP 403**, now disabled (D-49) | Not worked around. No backfill source remains |
| BSE RSS | Parser implemented, **disabled** | Feed URL and item layout (Spike S1) |
| News headlines: Google News RSS search, ET and Moneycontrol RSS (D-51) | Implemented, enabled | Not yet fetched by FINN. The Moneycontrol feed URL is from memory; Google News may rate-limit 22 queries per refresh (cached 60 min) |
| screener.in Quarterly Results (D-52) | Implemented, enabled (results items only) | Not yet fetched by FINN; the table layout is assumed from Screener's public page and checked by schema |
| LinkedIn profiles | **Not used** | LinkedIn's terms forbid scraping (D-51) |
| NSE UDiFF bhavcopy (price fallback) | **Not implemented** | — |
| Exchange holiday calendar | **Not implemented** | Holidays may show as stale prices |
| LLM classification fallback, results extraction, Tavily, Gemini/Groq | **Not implemented** | Keys and free-tier access (S6) |
| BSE scrip codes in the portfolio | From memory | Spike S5 |
| Render / Vercel deployment, keep-alive, GitHub Actions poller | **Not implemented** | — |

## Free services used (no paid APIs)
Gemini API (free tier) · Groq (free tier) · Tavily (free plan) · Vercel (Hobby) · Render (free web service) · GitHub Actions. Details and limits: [RESEARCH R10–R12](docs/RESEARCH.md).

## Decisions confirmed by the owner
See [REQUIREMENTS §8](docs/REQUIREMENTS.md). In short: Gemini + Groq free tiers; Vercel + Render; live data for any NSE ticker by default; filing bios plus a Tavily web search; table source pending D-35; the Ask box, swipe triage and voice briefing are in; Bull vs Bear is out; the design brief is understated premium.

## How data is stored
The server keeps **no durable state**: Render's free tier wipes local files on every spin-down, restart or redeploy. The portfolio and defaults are committed config. Your threshold changes, read/unread state and swipe triage are saved **in your browser on that device**. Market data and filings are re-fetched on boot from a committed seed. Details: [ARCHITECTURE §4b](docs/ARCHITECTURE.md).

## Source rules (planned)
Research narrative cites primary documents only (annual reports, transcripts, filings). Where numbers come from is pending decision D-35 (tables derived from filings are recommended). Data is accessed only through official channels: exchange RSS feeds, downloadable files, company websites and documented APIs. No website scraping (D-32). Web search is used only for management-change backgrounds in Push, and is labelled. Details: [ARCHITECTURE §4a](docs/ARCHITECTURE.md).

## Decisions: status
- **Approved:** D-31 (repo holds metadata, links, FINN-derived outputs and synthetic fixtures only); **D-38 (personal non-commercial project; all publicly accessible web sources allowed; guardrails: no login/CAPTCHA bypass, no signed-in sessions, polite rates, attribution)**; D-39–D-41 (frontend stack, design system, first vertical slice).
- **Conditional on Phase-1 spikes:** D-33 announcements (NSE RSS + per-company JSON backfill, BSE fallback); D-34 documents (company websites, exchange attachments, screener links); D-36 prices (yfinance first, NSE bhavcopy fallback); D-37 GitHub-Actions metadata log is now optional.
- **Unresolved (owner):** per-device settings (A-13) only. D-35 → screener tables (D-38); O1 → yes; Vercel Hobby fits (personal project).

Details: [DECISIONS](docs/DECISIONS.md), evidence in [RESEARCH R25–R27](docs/RESEARCH.md), checklist in [IMPLEMENTATION_PLAN Phase 1](docs/IMPLEMENTATION_PLAN.md).

## Still open (technical)
1. Real free quotas and model access on your keys (S6).
2. RSS feed window length at peak times vs GitHub Actions schedule reliability (S1, S9).
3. Alert timing: EOD price/volume checks plus ~10-min announcement polling as the reading of "the moment".
4. Build-history export format for the submission.

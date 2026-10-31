# CLAUDE.md — Rules for AI coding agents working on FINN

FINN is a mobile-first financial investment intelligence agent with Push (digest + alerts) and Pull (grounded research) modes, built for the ENAM Holdings AI Engineer Build Challenge. **Deadline: Sunday, 1 November 2026.**

Read first, in this order: `docs/PROGRESS.md` (current state) → `docs/REQUIREMENTS.md` → `docs/IMPLEMENTATION_PLAN.md` → whichever of `docs/ARCHITECTURE.md` / `docs/DECISIONS.md` is relevant to the task.

## Non-negotiable rules

### Working style
1. **Inspect before editing.** Read the relevant files (and their tests) before changing them. Don't edit code you haven't read.
2. **No unnecessary rewrites.** Make the smallest change that solves the task. Don't reformat, rename or restructure unrelated code. Don't replace a working module wholesale without a logged decision.
3. **Stay in scope.** Build what `IMPLEMENTATION_PLAN.md` says for the current phase. New scope requires an entry in `docs/DECISIONS.md`. After the feature freeze (Sat 31 Oct 24:00 IST), only fixes are allowed.
4. **Never claim a capability that doesn't exist.** README, UI copy and docs describe only implemented, verified behaviour. Planned work is labelled "planned".

### Financial truthfulness
5. **Never fabricate financial facts.** No invented numbers, dates, names, guidance or quotes, and no placeholder figures that look real. If data is missing or fails validation, show an explicit "unavailable / couldn't verify" state.
6. **Numbers come from code, not models.** LLMs may locate and label values. Parsing, unit conversion and arithmetic (QoQ, YoY, margins, ratios) are done in typed Python functions with tests.
7. **Preserve citations end to end.** Every generated claim is a `Claim{text, citations[]}`. Transformations (summarising, merging, reformatting, UI rendering) must carry the citations through. Never strip, merge away or invent a citation. Uncited claims are dropped, not shown.
8. **Pull = primary sources for narrative; labelled tables for numbers.** Follow the source-class rules in `docs/ARCHITECTURE.md` §4a exactly: every number and claim carries `Provenance`; narrative claims cite `PRIMARY_DOC`; standardised tables (`STANDARDIZED_TABLE`, source per D-35) supply numbers only and are always labelled; `MARKET_DATA` and `EXTERNAL_WEB` never enter Pull.
   Never use news, broker notes, research reports, or model background knowledge about the company. Prompts must say so, and the validator must enforce it.
9. **Label derived and stale data.** Derived metrics (e.g. EBITDA) show their formula. Snapshot data shows "as of <timestamp>".

### Code quality
10. **Typed interfaces.** Python: type hints everywhere, Pydantic/SQLModel for all I/O and LLM outputs, mypy-clean on new code. TypeScript: `strict: true`, no `any` in new code, API types generated from OpenAPI rather than hand-written.
11. **LLM calls go through `llm/` only.** They need a JSON-schema output and a route (`fast` | `long`). The route resolves to primary/fallback **slots, each naming provider + model** (ARCH §6), with independent quota tracking, a content-hash cache keyed by prompt version, and a call log. No ad-hoc SDK calls, no hard-coded model IDs, no guessed quota numbers.
12. **Tests never hit the network.** Use saved fixtures in `backend/tests/fixtures/`. Pure functions (scoring, alert rules, metrics, verdicts, validators) need unit tests.
13. **Run relevant tests before declaring a task done**, and report the actual result. If tests can't run, say so and why.

### Infrastructure facts to respect
- **The server is stateless** (Render free has an ephemeral filesystem). Don't store anything server-side that must survive a restart. Durable data is committed (config, seed, seed cache) or kept on the device (ARCH §4b).
- **Label evidence.** When writing docs, tag service claims as [OFFICIAL], [OBSERVED], [3RD-PARTY] or [UNVERIFIED] (RESEARCH.md). Config values may use only official or observed numbers.
- **Protect the core.** Never break the protected-core items in IMPLEMENTATION_PLAN §1a. Cut features only in the listed order, and log each cut.

### Product constraints set by the owner
- **Live by default (R-30).** The deployed app must fetch and process real data for any NSE ticker with no manual steps. The snapshot is only a labelled fallback when a source fails. Never ship a feature that works only on the demo set.
- **Free tiers only (R-35).** No paid APIs, models or services. Every LLM call must handle a 429 by falling back or showing a "paused" state.
- **Design bar (R-34, PRODUCT_SPEC §6).** Understated premium: typography, tabular figures, colour only for meaning, no gradients, decorative motion or AI-styled ornament.
- **Scope**: Bull vs Bear is out (Q-10). Don't add it back without the owner's approval.

### Source access (D-38, owner-approved)
- Personal, non-commercial project. The deployed app may use publicly accessible sources: NSE/BSE website endpoints and RSS, screener.in public pages, yfinance, company websites.
- **Hard guardrails:** never bypass logins, CAPTCHAs or rate limits; never use anyone's signed-in session; polite request rates with backoff and caching; honest User-Agent; attribution plus deep links in the UI.
- The repo (all branches, fixtures, seeds) holds **metadata, links, FINN-derived outputs and synthetic "Fixture …" data only**: never filing PDFs, document text, bhavcopy files or screener tables (D-31).

### Secrets & safety
14. **Never expose secrets.** No keys in code, docs, fixtures, logs, commits or frontend bundles. Only `.env.example` (placeholders) is committed. Only `NEXT_PUBLIC_*` vars reach the browser, and they must never hold secrets.
15. **Be a polite scraper.** Rate-limit, back off, cache, and send an honest User-Agent. Don't scrape LinkedIn or anything behind a login.

### Process
16. **Update `docs/PROGRESS.md` after every phase** with: done, verified (and how), not verified, open questions, next. Record measured metrics only.
17. **Log decisions** in `docs/DECISIONS.md` when choosing between real alternatives.
18. **Update traceability** status in `docs/EVALUATION.md` §3 when a requirement is implemented or verified.

## Repository layout (planned; created in Phase 1)
```
backend/   FastAPI app: sources/ push/ extract/ research/ llm/ store/ api/ jobs/ tests/
web/       Next.js (TypeScript, Tailwind) PWA
config/    portfolio.yaml, adhoc.yaml, alert defaults
docs/      planning and tracking documents
```

## Commands
To be defined in Phase 1 once the scaffold exists. Don't guess commands that don't exist yet.

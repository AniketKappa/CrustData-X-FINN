# FINN — Product Spec

> Status: **proposal**. Nothing described here is implemented yet. See `PROGRESS.md` for what actually exists.

## 1. Point of view
**An investor doesn't need more information. They need a short list of what changed, why it matters, and proof.**

FINN's interaction model rests on three ideas:

1. **Brief, not feed.** The home screen is a *ranked brief* with a hard cap on what gets attention (target: ≤ 5 "Must read" items per day). Everything routine is collapsed behind a count ("37 routine filings hidden"), so the investor can see the filtering happen.
2. **Every claim carries its receipt.** Each number or claim links to a document, page and snippet. If FINN can't cite it, FINN doesn't say it. This is the visible form of the primary-source discipline (REQ R-19).
3. **Push flows into Pull.** A pushed item ends with *Dig in*, which opens a research dossier already scoped to that company and that question. Push and Pull are one workflow rather than two separate products.

The intended daily loop is: open → glance at the brief (30 s) → act on 1–2 cards → occasionally dig in (2–5 min) → close.

## 2. Users & jobs
Primary user: a portfolio manager or analyst at a lean public-markets fund, on a phone between meetings.

| Job | Mode | MVP? |
|---|---|---|
| "What happened across my book since I last looked?" | Push: digest | ✅ |
| "Tell me when something unusual happens to a stock I hold." | Push: alerts | ✅ |
| "Results just dropped. Are they good or bad, at a glance?" | Push: results card | ✅ |
| "A new CFO was announced. Who is this person?" | Push: management card | ✅ |
| "Has this management team delivered what they promised?" | Pull: Promises Ledger | ✅ |
| "Give me the shape of this business and its numbers, fast." | Pull: snapshot + trajectory | ✅ |
| "Is the balance sheet / cash flow healthy?" | Pull: balance sheet + cash quality | ✅ |
| "Ask anything about this company's filings." | Pull: Ask box (grounded Q&A) | ✅ |
| "Clear my brief quickly." | Push: swipe triage | ✅ |
| "Brief me while I commute." | Push: voice briefing | ✅ (built last) |
| "What's the case for and against?" | Pull: bull vs bear | ❌ Not selected by user (Q-10) |

## 3. MVP scope (explicit)

### 3.1 In MVP — Push
**P-1 Windowed digest**
- Covers the configured portfolio (15–20 tickers).
- Window chips: **24h (default)**, 3d, 7d, custom range.
- Each announcement is classified into the REF taxonomy (17 categories), then scored into tiers:
  - **Must read**: shown expanded, with a "why it matters" line.
  - **Worth a glance**: one-line summary.
  - **Routine**: collapsed behind a count, expandable.
- Each item shows company, category chip, time, source exchange and a link to the original filing.

**P-2 Triggered alerts**
- Price rule: |close / prev_close − 1| ≥ **X%** (default 5%).
- Volume rule: today's volume ≥ **N ×** the mean volume of the prior **20 sessions** (default N = 2.0).
- Material-announcement rule: the user toggles which categories alert. Defaults: results, M&A, management_change, fund_raise, litigation, credit_rating, pledging.
- Thresholds can be set **globally and per ticker** (REQ R-12c). They are stored **on the device** (browser storage) and sent with each request; see ARCHITECTURE §4b.
- Delivery: an in-app **Alerts inbox** with an unread badge. Alerts are computed when the inbox or Brief loads, from the latest ingested EOD data and announcements (ingest cadence: REQUIREMENTS A-2). Read/unread is saved on the device.

**P-3 Results card** (for `results` announcements)
- Revenue, EBITDA, PBT, PAT for the reported quarter, with **QoQ and YoY %**.
- Source order: the filing's XBRL first, then the PDF table with validation (ARCHITECTURE §5.2).
- EBITDA carries a "derived" badge, and tapping it shows the formula.
- For lenders (banks/NBFCs), EBITDA is shown as "n/m — not meaningful for lenders".
- Consolidated figures are used if available, otherwise standalone, and the basis is labelled.
- If extraction fails validation, the card says *"Couldn't verify numbers — open filing"*. **A guessed number is never shown.**

**P-4 Management-change card** (for `management_change`)
- Who, role, joining or leaving, effective date.
- Background: the "brief profile" extracted from the filing's Reg-30 annexure (primary, cited).
- Optional external enrichment (web search) sits behind a feature flag. It must be labelled with its source link and is never mixed with filing text.

**P-5 Other categories**: following REQ R-15, we decide per category in `ARCHITECTURE §5.1` whether an item earns a one-line summary or just a priority placement.

### 3.2 In MVP — Pull
**L-1 Research dossier for any NSE ticker** (generalised; nothing hard-wired)
- Entry points: search box, a "Dig in" from Push, or the ad-hoc demo list.
- If documents are unavailable, an honest empty state says what was found and what wasn't.

Sections in MVP (user-selected, Q-10), in build order:
1. **Promises Ledger** (the signature feature): for the last 4 quarters, each guided metric shows *promised → delivered → verdict*. Every promise cites a **transcript page (primary)**. Every actual is a sourced number: results XBRL if parsed, otherwise the screener.in table, with its source tag shown. If the two disagree, the cell shows both with ⚠. Verdicts are computed in code: `Delivered`, `Partly`, `Missed`, `Too early`, `Not measurable`.
2. **Financials + Trajectory**: headline numbers, margins, multi-year direction, as small precise charts. Numbers are **computed in code**; their **source depends on D-35 (unresolved)**: tables derived from filings (recommended) or screener.in tables (if the owner accepts the licence conflict). Every figure carries a source tag. Any reason or explanation in the one-line read must cite a primary document (ARCHITECTURE §4a).
3. **Balance sheet + Cash quality**: debt and D/E, working-capital days, CFO/PAT and FCF trend. Mostly deterministic, with a one-line cited read.
4. **Business snapshot**: what the company does, segments, revenue mix (from the latest AR, cited).

**L-2 Ask box** (user-requested, R-31): a single input on the dossier ("Ask about ASTRAL's filings…"). The answer is built only from that company's retrieved chunks and computed metrics, in Claim/Citation form. If the documents don't answer it, FINN says so. The scope stays fixed to the company; there is no open web and no general chat.

Not in scope: **Bull vs Bear** (not selected, Q-10).

### 3.2b Push interaction extras (user-requested, Q-9)
**P-6 Swipe triage** (R-32; state saved on this device): on the Brief, swipe right = **Done**, swipe left = **Snooze** (until the next window), tap = open, and a long-press or button = **Dig in**. A header counter ("4 of 7 cleared") makes the brief feel like an inbox you finish. Every gesture also has a visible button equivalent, for accessibility and desktop.

**P-7 Voice briefing** (R-33): a "Listen" button reads the Brief aloud (Must-read items, then counts) using the **browser's built-in speech synthesis**. That costs nothing and needs no API. The script is generated from the same card data (no new claims) and capped at about 60 seconds. Built **last**; first to cut if time runs out.

### 3.3 Platform in MVP
- Responsive **PWA**, deployed at a public URL, installable to the home screen.
- **Live by default** (R-30): the deployed app ingests real data on a schedule and researches any NSE ticker on demand.
- **Fallback snapshot**: used **only** when a live source fails, always with a visible "Showing data as of <timestamp>: live source unavailable" banner.
- A debug drawer with token and cost per request (innovation I-9).

### 3.4 Explicitly OUT of MVP (and why)
| Out | Why |
|---|---|
| Voice *input* / conversational voice | Voice *output* (briefing) is in; speech input adds cost and risk for little signal. |
| Bull vs Bear section | Not selected by the user (Q-10). |
| Native app / TestFlight | A PWA is acceptable (MAIN p4) and avoids review and build friction. |
| Intraday or real-time prices | The brief specifies EOD data. |
| News, broker notes, sentiment | Forbidden for Pull (R-19); noise for Push. |
| LinkedIn scraping | Against LinkedIn's terms and behind a login wall. Filing profiles cover the need (I-6). |
| Auth, multi-user, portfolio import | Not needed for a single-user demo. |
| Web push notifications | Stretch. On iOS they need the PWA installed to the home screen. |
| Narrative-vs-numbers section, standalone Guidance section | The Promises Ledger already covers both. |
| Any paid API or paid model | Free tiers only (R-35). |

## 4. Screens, navigation & journeys
Reference prototype: `design/prototype/` (v2, 30 Oct 2026). It is a **functional static prototype on labelled fixture data**: `index.html`, `styles.css` and ES modules `js/{fixtures,logic,format,charts,views,app}.js`. Serve the folder (`python3 -m http.server`); modules do not load over `file://`. Screenshots are in `design/prototype/shots/`; v1 is kept in `design/prototype/archive/`.

### 4.1 Screen hierarchy (v2, D-42)
```
Briefing (home) ─┬─ Item detail (analysis + source) ─┬─ Evidence dialog
                 │                                   └─ Company research
                 ├─ Market alerts (inline in "Read first", from thresholds)
                 └─ Routine filings (expands in place)
Companies ───────┬─ Search (name or NSE symbol) · Holdings · Research list
                 └─ Company ─┬─ Overview      (business, at a glance, segments)
                             ├─ Financials    (Rev/EBITDA/PBT/PAT QoQ/YoY, revenue chart, EBITDA-margin chart, 8-quarter table)
                             ├─ Cash & debt   (OCF vs PAT chart, OCF/PAT, capex, FCF, working-capital days, leverage)
                             └─ Promises      (ledger) ── Evidence dialog
Research ────────── Company selector · question · examples · cited notes · follow-ups · Listen
Header menu ─────── Portfolio & alerts: price/volume thresholds, "Read first" categories, holdings (read-only)
```
There is **no Alerts tab and no Settings tab**. Triggered alerts appear in the Briefing; thresholds live in the header menu.

### 4.2 Primary navigation
- **Three destinations:** Briefing (Push), Companies (company research for holdings, the research list or any NSE symbol), Research (Pull Q&A).
- **Mobile (< 1024 px):** bottom bar with text labels and line icons; the active destination has an ink top rule and `aria-current="page"`. Content has bottom padding so nothing sits under the bar.
- **Desktop (≥ 1024 px):** a left rail with the same three links. The Briefing becomes two columns: the list and a sticky detail pane that follows the selected item.
- **Header:** wordmark and one "Portfolio & alerts" control opening a dialog.
- **URL is state:** `#/briefing?w=24h|3d|7d`, `#/briefing/item/:id`, `#/companies?q=`, `#/companies/:symbol/overview|financials|cash|promises`, `#/research?c=:symbol`. Back works and every screen can be reloaded.

### 4.3 Key user journeys (each is a demo script line)
| # | Journey | Taps | Success |
|---|---|---|---|
| J1 | Morning glance: open → read the summary → open the top "Read first" item → source → back → **Done** | ≤ 4 | Knows what changed and has seen proof in under a minute |
| J2 | Results triage: results item → Rev/EBITDA/PBT/PAT with QoQ and YoY → "Open financials" | 2 | Trusts the numbers without opening the PDF |
| J3 | New CFO: management item → filing profile with citation | 1 | Knows who the person is and where it came from |
| J4 | Unusual move: Briefing shows "Down 4.8% · volume 2.7× its 20-day average" → calculation | 1 | Sees exactly why it fired and that no filing explains it |
| J5 | Does management deliver? Companies → company → Promises → "Said" → quote at page | 3 | Has a verdict, the comparison method and both sources |
| J6 | Any ticker: Companies → type a symbol | 1 | Live: dossier builds. Prototype: says honestly that it has no data |
| J7 | Tune noise: Portfolio & alerts → volume 3× → Save | 3 | The volume alert leaves the Briefing |
| J8 | Ask: Research → example question → cited note → tap [1] → passage → follow-up | 3 | Has an answer whose every finding opens its source |

### 4.4 Key interaction decisions
1. **The summary is the headline**, followed by a context strip: window, holdings count, alert thresholds and data freshness.
2. **Two weights, not card styles.** "Read first" items use a serif 17 px headline and a stronger rule; "Other updates" are plain rows. Routine filings are a counted disclosure button that expands in place (`aria-expanded`).
3. **Each item states:** company, event type, IST timestamp, headline, one-sentence why-it-matters, and a visible source reference that opens the evidence dialog. Done and Snooze 1 day are quiet text actions; "Show them again" restores.
4. **High priority** = results, management change, M&A, litigation, credit rating, and price/volume alerts that cross the device thresholds. Unchecking a category in the menu moves it to "Other updates".
5. **Market alerts are computed on read** from end-of-day bars: `|close change| ≥ price %` or `volume ÷ 20-day average ≥ multiple`. The detail shows the calculation.
6. **The ledger is the signature.** Each entry shows the statement in quotes with document, date and page; the explicit target or "No numeric target stated"; the result with its source; the comparison method; one of five statuses (**Delivered, Partly delivered, Missed, Not yet measurable, Insufficient evidence**), each with a word and a shape marker; and a one-line explanation. Quantitative entries with a result get a range strip; qualitative ones never get a chart.
7. **Research is a workspace, not a chat.** One question box with a company selector, a few example questions, and answers as notes: Findings (each cited), What it may mean (labelled interpretation), Uncertainty, Sources, Listen and follow-ups tied to the same company.
8. **Listen** reads the summary, then the "Read first" items, then a list of other updates via `speechSynthesis` (en-IN). Toggles to Stop. It is disabled with a note if the browser lacks speech.
9. **Honest gaps.** Real portfolio companies open a page saying the prototype has no data for them (with a link to the company on NSE) instead of placeholder numbers. Free-typed research questions get a plain statement that the prototype answers only the examples.

### 4.5 Implemented in prototype v2 vs not
| Implemented and tested (Playwright, 40 checks) | Not implemented |
|---|---|
| Three-destination nav with route sync; window control (24 h / 3 d / 7 d); Listen; routine expansion; Done / Snooze / restore; item detail (mobile route, desktop pane); evidence dialog with real NSE links for Infosys rows; thresholds and categories saved per device and applied to alerts; company search and honest empty states; four company sections with charts, tables and tooltips; ledger with five statuses; research examples, citations, follow-ups, spoken notes; skip link, focus states, Esc-to-close dialogs, reduced motion | Any live data or backend; free-question answering; holdings editing; alert context chart (30-session); per-holding threshold overrides; swipe gestures; dark mode (v2 is light-only by design); custom date window; web background for appointees |

## 4b. Component specifications
> v2 note (D-42): `ItemMust`/`ItemRow` are now one `BriefingRow` with a high-priority variant; `AlertRow` is a `BriefingRow` with an explicit "Up/Down x%" label; `SectionTabs` are Overview · Financials · Cash & debt · Promises; `AskBox` is the Research workspace form; `EvidenceSheet` is a native `<dialog>` (bottom sheet on mobile, centred on wider screens); `ContextChart`, `SmallMultiples` and `Skeleton` are not in the prototype. Statuses in `LedgerRow` follow §4.4 item 6.

Tokens are in §6. Every component has loading, empty and error states; all text is sentence case.

| Component | Purpose | Anatomy | States / rules |
|---|---|---|---|
| `AppShell` | Layout + navigation | Tab bar (mobile) or rail (≥ 1024); list and detail slots | Active tab set from the route; safe-area insets; skip link |
| `StatusBanner` | System state | One line, icon-free, tinted per kind | `waking`, `refreshing`, `stale-source(as_of)`, `quota-paused(until)`, `fixture` (dev/demo only) |
| `BriefHeader` | Date, title, summary sentence | Date line, h1, sentence with bold counts | Counts come from the API, never computed client-side from partial lists |
| `WindowControl` | 24 h, 3 days, 7 days, custom | Segmented control, 44 px | Selected state uses ink fill; custom opens a date sheet |
| `ListenButton` | Voice briefing | Outlined text button | Hidden if `speechSynthesis` is absent; "Stop" while speaking |
| `ItemMust` | Must-read announcement | Who line (company, category, time), title, optional `FactRow`, why line, `SourceLine`, action row | Done/Snooze update the progress count; error state "Couldn't verify numbers. Open filing." |
| `ItemRow` | Worth-a-glance announcement | Who line, one-line summary | Tap → Item detail |
| `RoutineGroup` | Collapsed routine filings | One button sentence listing the top 3 subtypes | Expands in place; `aria-expanded` |
| `FactRow` | Two or three key numbers inline | Label + signed value | Sign always shown; colour only for meaning; tabular figures |
| `ResultsTable` | Revenue, EBITDA, PBT, PAT × value, QoQ, YoY | Caption with unit and basis; rows; footnote with source and formula | `derived` badge; lender → "n/m for lenders"; every cell tappable → Evidence |
| `ProfileBlock` | Appointee background | Filing profile (cited), then a separately titled "Public background (web)" with links | Web block hidden if none; never merged with filing text |
| `AlertRow` | Triggered alert | Company, rule sentence ("Volume 2.7× its 20-session average"), date, unread dot | Read state on device |
| `ContextChart` | Alert context | 30-session bars (volume) or line (close), threshold as a dashed line, last value labelled | No gridlines beyond the threshold; axis at zero for bars |
| `DossierHeader` | Company + coverage | Name, symbol, "N transcripts and M annual reports read. Updated <date>." | Building state shows step progress |
| `SectionTabs` | Promises · Financials · Balance sheet and cash · Business | Underlined text tabs, horizontally scrollable | Route-driven |
| `LedgerSummary` | One sentence | "Management delivered on X of Y guided numbers over the last four quarters." | Counts only verdicts that were measurable |
| `LedgerRow` | Promise vs delivery | Metric, period, verdict word; quote + cite link; `RangeStrip` or note | Verdict colour + word (never colour alone); "Too early" / "Not measurable" have no strip |
| `RangeStrip` | Signature viz | Labelled scale endpoints, promised band, delivered tick with value above | `role="img"` + full aria-label; ⚠ marker when sources differ (shows both ticks) |
| `SmallMultiples` | Financials trajectory | 4–6 mini charts (Revenue, EBITDA margin, PAT, CFO/PAT…), 8 quarters or 5 years | Direct end labels; units in the title; zero-based for bars |
| `MetricTile` | Single figure | Label, value, period, source tag | Tappable → Evidence |
| `SourceLine` / `SourceTag` | Provenance at a glance | "From the filing's XBRL", "screener.in table", "Derived" | Always present on numbers |
| `EvidenceSheet` | Proof | Title (metric + value), derivation chain, snippet with highlight, actions "Open <doc> at page N" | Focus-trapped dialog; Esc/back closes; right panel on desktop |
| `AskBox` + `AnswerBlock` | Grounded Q&A | Input; answer paragraphs, each with citations | "Not answered in this company's filings" state; 10 per session limit message |
| `SettingsForm` | Thresholds | Numeric steppers with units, per-holding override list | Saved on device; note says so |
| `EmptyState` | Nothing to show | One sentence + next action | e.g. "No filings in the last 24 hours. Try 3 days." |
| `Skeleton` | Loading | Grey bars matching layout | Never longer than the waking banner implies |

## 4c. Data honesty in the UI
- **No fake live data.** Production screens show only API data. The prototype and tests use **fixture companies named "Fixture …"**, always with the `fixture` banner.
- **No predictions, scores out of 10, or AI adjectives** ("strong", "robust") unless they're quoted from a filing with a citation.
- **No decorative charts.** A chart appears only where it answers a question (alert context, trajectory, ledger strip).

## 5. Demo companies — **confirmed by the user (Q-6)**
The company names are confirmed. The NSE **symbols below are our mapping and still need Spike S5** (they must resolve on the chosen price source and the NSE announcements source). If a symbol fails, we fix the mapping, not the company.

**Portfolio (18)**, chosen to cover sectors, sizes and filing behaviour:
| Size | Candidates | Why they make the demo interesting |
|---|---|---|
| Large | RELIANCE, HDFCBANK, INFY, ITC, LT, SUNPHARMA, MARUTI, BHARTIARTL | Conglomerate, lender (tests EBITDA n/m), IT, FMCG, capital goods, pharma, auto, telecom |
| Mid | TRENT, POLYCAB, PERSISTENT, DIXON, CHOLAFIN, TATAPOWER, PIIND | High-growth consumer, industrials, NBFC, utilities, agrochem |
| Small/active | KAYNES, CDSL, SUZLON | Frequent filings and volatile volume, which give alerts something to fire on |

**Ad-hoc research (4)**: Pidilite Industries (PIDILITIND), Astral (ASTRAL), APL Apollo Tubes (APLAPOLLO), Havells India (HAVELLS). If one has fewer than 4 transcripts, the ledger shows fewer quarters and says so; we don't swap the company without asking the user.

We also plan to test generalisation on one ticker the user picks blind during QA (EVALUATION §3).

## 6. Design system (v2, D-42 — supersedes the v1 cool palette of D-40)
> Owner brief (Q-11, redesign brief 30 Oct): restrained, light editorial; for professional investors; aligned columns, rules and whitespace; no emoji, gradients, oversized rounded cards, excessive pills or ornamental icons.

**Concept:** an annotated research note. Warm paper ground, white only for genuine surfaces (dialogs, inputs), dark ink, thin rules for structure, one restrained blue for links and actions. Serif for headlines and quoted statements; sans for everything else.

### 6.1 Colour tokens (light only)
| Token | Value | Use | Contrast on `--bg` |
|---|---|---|---|
| `--bg` | `#F7F5F0` | Page | — |
| `--surface` | `#FFFFFF` | Dialogs, inputs, selected rail item | — |
| `--ink` / `--ink-2` / `--muted` | `#1C1D1F` / `#45484D` / `#6B675F` | Text tiers | — / 8.4:1 / 5.2:1 |
| `--rule` / `--rule-2` | `#E3DFD6` / `#CBC5B8` | Dividers / control borders | — |
| `--accent` | `#1F4E8C` | Links, primary button, focus, citations | 7.6:1 |
| `--up` / `--down` / `--part` | `#1D6A44` / `#A2281D` / `#85580A` | Changes and statuses, always with a word ("up 3.9%", "Missed") | 6.0 / 6.7 / 5.7:1 |
| `--s1` / `--s2` | `#3A6EA5` / `#C08A2E` | Chart series (validated pair: CVD ΔE 22.9, both ≥ 3:1 on white) | — |
| `--band` | `#C9D7EA` | Promised band; earlier bars in a single-series chart | — |
Contrast ratios measured with the WCAG formula on 30 Oct 2026; all text tokens pass AA.

### 6.2 Typography
- **IBM Plex Sans** 400/500/600 for UI, tables and charts; **IBM Plex Serif** 400/500 (and italic) for page titles, item headlines in "Read first", and quoted management statements. Loaded from Google Fonts in the prototype; `next/font` in the app.
- `font-variant-numeric: tabular-nums lining-nums` on the body.
- Scale: 12 · 13 · 15 (body) · 17 · 22 · 28 (32 on ≥ 768). Section labels are 12 px uppercase with letter-spacing over a 1 px ink rule; this is the only uppercase.

### 6.3 Spacing, shape, elevation
- 4-pt base: 4, 8, 12, 16, 24, 32, 48.
- Radius 4 px for controls; 2 px for tags and citation markers; 8 px only on the top of the mobile dialog. No card containers for list items.
- Elevation: dialogs only. Structure comes from rules: 1 px `--rule` between rows, 1 px `--ink` under section labels.

### 6.4 Chart conventions
- One measure per axis. Revenue (bars, ₹ crore, zero-based) and EBITDA margin (line, %, axis may not start at zero and says so) are separate charts. OCF and PAT share one chart because both are ₹ crore, with a legend.
- The latest period is accented; the value is labelled at the end. X labels thin to every other period on narrow screens, always keeping the latest.
- Charts are SVG rendered at the container's measured width (re-rendered on resize), so text stays 11–12 px on phones. Hover/touch tooltips; every chart has a table with the same values; `role="img"` with a full label.
- Every chart states unit, periods and source; FINN-computed values say so. No interpolation, no decorative charts.
- Range strip: labelled scale endpoints, promised band, actual tick labelled above.

### 6.5 Accessibility
- WCAG 2.2 AA target. Tap targets ≥ 44 px for navigation and primary controls (inline text actions ≥ 32 px). 2 px `--accent` focus ring. Skip link. `prefers-reduced-motion` removes transitions; `forced-colors` keeps chart marks visible.
- Colour never carries meaning alone: "up/down" words, status words with distinct marker shapes (filled dot, half dot, square, ring).
- Dialogs are native `<dialog>`: focus moves in, Esc closes, focus returns to the opener. Tables use `<th scope>`. Language `en-IN`.

### 6.6 Breakpoints
| Range | Layout |
|---|---|
| < 768 px | Single column, bottom nav, item detail as its own route, bottom-sheet dialog |
| 768–1023 px | Wider single column (max 760 px), four-column context strip, centred dialog |
| ≥ 1024 px | Rail 208 px + content; Briefing list + sticky detail pane (340–400 px) |

### 6.7 Motion
None, apart from the native dialog. Nothing animates on load.

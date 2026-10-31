// FINN prototype data. Shapes follow ARCHITECTURE §10 (Digest, ItemSummary, Metric, Claim, Dossier, LedgerRow).
// DEMONSTRATION DATA: every company named "Fixture …", every number and every fixture passage is invented
// for design review. Rows marked real: true are Infosys announcement metadata observed on NSE on 29 Oct 2026.

export const AS_OF = "2026-10-29T19:30:00+05:30";
export const FRESHNESS = "Fixture data as of 29 Oct 2026, 19:30 IST. Infosys rows: NSE announcement metadata observed 29 Oct 2026.";

const fx = (name, locator) => ({ source_class: "PRIMARY_DOC", source_name: name, url: null, fixture: true, locator });

// ---------- Portfolio and company directory ----------
// Real names are the owner-confirmed portfolio (PRODUCT_SPEC §5). They carry no data in this static prototype.
export const COMPANIES = [
  ...[["RELIANCE","Reliance Industries"],["HDFCBANK","HDFC Bank"],["INFY","Infosys"],["ITC","ITC"],["LT","Larsen & Toubro"],
      ["SUNPHARMA","Sun Pharmaceutical Industries"],["MARUTI","Maruti Suzuki India"],["BHARTIARTL","Bharti Airtel"],["TRENT","Trent"],
      ["POLYCAB","Polycab India"],["PERSISTENT","Persistent Systems"],["DIXON","Dixon Technologies"],["CHOLAFIN","Cholamandalam Investment and Finance"],
      ["TATAPOWER","Tata Power"],["PIIND","PI Industries"],["KAYNES","Kaynes Technology"],["CDSL","Central Depository Services"],["SUZLON","Suzlon Energy"]]
    .map(([symbol, name]) => ({ symbol, name, holding: true, fixture: false })),
  ...[["PIDILITIND","Pidilite Industries"],["ASTRAL","Astral"],["APLAPOLLO","APL Apollo Tubes"],["HAVELLS","Havells India"]]
    .map(([symbol, name]) => ({ symbol, name, holding: false, research: true, fixture: false })),
  { symbol: "FX-CABLES", name: "Fixture Cables Ltd", holding: true, fixture: true, sector: "Cables and wires (fixture)" },
  { symbol: "FX-PHARMA", name: "Fixture Pharma Ltd", holding: true, fixture: true, sector: "Pharmaceuticals (fixture)" },
  { symbol: "FX-POWER",  name: "Fixture Power Ltd",  holding: true, fixture: true, sector: "Power utilities (fixture)" },
  { symbol: "FX-TUBES",  name: "Fixture Tubes Ltd",  holding: false, research: true, fixture: true, sector: "Steel tubes (fixture)" },
];

// ---------- Announcements (ItemSummary + detail) ----------
export const ITEMS = [
  { id: "a1", symbol: "FX-CABLES", company: "Fixture Cables Ltd", category: "results", event: "Quarterly results",
    published_at: "2026-10-29T18:42:00+05:30", fixture: true,
    title: "Q2 FY27 results: revenue up 14.1% year on year, EBITDA margin down 1.2 points",
    why: "Revenue grew faster than its four-quarter average while margin fell for a second straight quarter.",
    source: fx("Q2 FY27 results filing (fixture)", "XBRL, statement of profit and loss"), results_ref: "FX-CABLES" },
  { id: "a2", symbol: "FX-PHARMA", company: "Fixture Pharma Ltd", category: "management_change", event: "Management change",
    published_at: "2026-10-29T17:05:00+05:30", fixture: true,
    title: "CFO resigns; successor from a listed peer joins on 1 December",
    why: "Second CFO change in 18 months; the filing gives the successor's last two roles.",
    source: fx("Reg-30 disclosure (fixture)", "Annexure A, brief profile"),
    profile: { person: "Fixture Person A", role: "Chief Financial Officer", change: "appointed", effective: "1 Dec 2026",
      filing_profile: "Chartered accountant; previously finance controller at a listed generics maker and treasury lead at a fixture conglomerate.",
      passage: "Brief profile: Fixture Person A is a member of ICAI with 19 years of experience in finance, most recently as Finance Controller…" } },
  { id: "a3", symbol: "FX-CABLES", company: "Fixture Cables Ltd", category: "M&A", event: "Acquisition",
    published_at: "2026-10-24T11:20:00+05:30", fixture: true,
    title: "Agrees to acquire 51% of a wire-harness maker for ₹180 crore",
    why: "First acquisition in five years; the deal is about 4% of last year's revenue.",
    source: fx("Reg-30 disclosure (fixture)", "Para 1, terms of acquisition") },
  { id: "g1", symbol: "INFY", company: "Infosys", category: "earnings_call", event: "Earnings call transcript",
    published_at: "2026-10-28T17:38:42+05:30", real: true,
    title: "Earnings call transcript filed",
    why: "Adds the latest call to the Promises Ledger once the live backend is running.",
    source: { source_class: "PRIMARY_DOC", source_name: "NSE announcement", locator: "attachment",
      url: "https://nsearchives.nseindia.com/corporate/Infosys_28102026173824_SE_filing_Earnings_call_transcript.pdf" } },
  { id: "g2", symbol: "FX-POWER", company: "Fixture Power Ltd", category: "credit_rating", event: "Credit rating",
    published_at: "2026-10-29T16:20:00+05:30", fixture: true,
    title: "Long-term rating reaffirmed; outlook revised to positive",
    why: "An outlook change usually precedes a rating move within 12 to 18 months.",
    source: fx("Rating rationale (fixture)", "page 1") },
  { id: "g3", symbol: "INFY", company: "Infosys", category: "results", event: "Financial results",
    published_at: "2026-10-23T16:08:26+05:30", real: true,
    title: "Financial results for the quarter and half year submitted",
    why: "Headline numbers appear here once the live results extractor is connected.",
    source: { source_class: "PRIMARY_DOC", source_name: "NSE corporate announcements", locator: "23 Oct 2026, 16:08",
      url: "https://www.nseindia.com/companies-listing/corporate-filings-announcements" } },
  { id: "g4", symbol: "FX-TUBES", company: "Fixture Tubes Ltd", category: "board_meeting", event: "Board meeting",
    published_at: "2026-10-27T10:02:00+05:30", fixture: true,
    title: "Board meets on 5 November to consider Q2 FY27 results",
    why: "Results date for a research company; the ledger updates after the call.",
    source: fx("Board meeting intimation (fixture)", "page 1") },
  // routine
  { id: "r1", symbol: "INFY", company: "Infosys", category: "unclassified", event: "Newspaper publication",
    published_at: "2026-10-29T15:15:01+05:30", real: true, routine: true, title: "Copy of newspaper publication",
    source: { source_class: "PRIMARY_DOC", source_name: "NSE announcement", locator: "attachment",
      url: "https://nsearchives.nseindia.com/corporate/INFY_29102026151445_SE_intimation_Newspaper_ad_2.pdf" } },
  { id: "r2", symbol: "INFY", company: "Infosys", category: "press_release", event: "Press release",
    published_at: "2026-10-29T15:05:32+05:30", real: true, routine: true,
    title: "Winners of Qorus–Infosys Finacle Banking Innovation Awards 2026 announced",
    source: { source_class: "PRIMARY_DOC", source_name: "NSE announcement", locator: "attachment",
      url: "https://nsearchives.nseindia.com/corporate/INFY_29102026150417_PR_29102026.pdf" } },
  { id: "r3", symbol: "FX-CABLES", company: "Fixture Cables Ltd", category: "unclassified", event: "ESOP allotment",
    published_at: "2026-10-29T12:40:00+05:30", fixture: true, routine: true, title: "Allotment of 41,200 shares under ESOP 2021",
    source: fx("Allotment intimation (fixture)", "page 1") },
  { id: "r4", symbol: "FX-PHARMA", company: "Fixture Pharma Ltd", category: "unclassified", event: "Trading window",
    published_at: "2026-10-28T09:30:00+05:30", fixture: true, routine: true, title: "Trading window closed until results",
    source: fx("Intimation (fixture)", "page 1") },
  { id: "r5", symbol: "FX-POWER", company: "Fixture Power Ltd", category: "unclassified", event: "Compliance certificate",
    published_at: "2026-10-26T14:00:00+05:30", fixture: true, routine: true, title: "Certificate under Reg 74(5) of SEBI (DP) Regulations",
    source: fx("Certificate (fixture)", "page 1") },
];

// ---------- End-of-day bars for market-move alerts (fixture) ----------
// prev20 = mean volume of the prior 20 sessions (shares); computed upstream in the real backend.
export const EOD = [
  { symbol: "FX-POWER",  company: "Fixture Power Ltd",  date: "2026-10-29", close: 312.4, prev_close: 328.1, volume: 9_180_000, prev20: 3_400_000 },
  { symbol: "FX-CABLES", company: "Fixture Cables Ltd", date: "2026-10-29", close: 1_284.0, prev_close: 1_210.2, volume: 1_120_000, prev20: 800_000 },
  { symbol: "FX-PHARMA", company: "Fixture Pharma Ltd", date: "2026-10-29", close: 642.5, prev_close: 655.6, volume: 2_050_000, prev20: 1_280_000 },
];

// ---------- Dossiers (fixture companies only) ----------
const Q = ["Q3 FY25","Q4 FY25","Q1 FY26","Q2 FY26","Q3 FY26","Q4 FY26","Q1 FY27","Q2 FY27"];
export const DOSSIERS = {
  "FX-TUBES": {
    symbol: "FX-TUBES", company: "Fixture Tubes Ltd", exchange: "NSE", sector: "Steel tubes (fixture)",
    price: { value: 1_146.3, date: "29 Oct 2026", source: "Fixture EOD data" },
    coverage: { transcripts: 4, annual_reports: 1, updated_at: "29 Oct 2026" },
    overview: {
      summary: "Makes structural steel tubes and hollow sections for construction, infrastructure and solar mounting structures, sold mainly through distributors.",
      cite: { doc: "Annual Report FY26 (fixture)", page: 14, passage: "We manufacture structural steel tubes… our distribution network spans 820 distributors across 29 states…" },
      segments: [ { name: "Construction and infrastructure", share: 62 }, { name: "Solar structures", share: 21 }, { name: "Agriculture and other", share: 17 } ],
      segments_cite: { doc: "Annual Report FY26 (fixture)", page: 38, passage: "Segment-wise revenue share: construction 62%, solar 21%, other 17%." },
    },
    quarters: Q,
    q: { revenue: [3_820, 4_105, 4_010, 4_260, 4_480, 4_915, 4_690, 4_872],
         ebitda:  [ 305,  341,  317,  349,  363,  413,  371,  360 ],
         pbt:     [ 236,  268,  242,  271,  283,  329,  289,  276 ],
         pat:     [ 176,  200,  181,  203,  212,  246,  216,  206 ] },
    q_source: "Quarterly results tables (fixture)",
    years: ["FY22","FY23","FY24","FY25","FY26"],
    cash: { ocf: [ 410, 288, 702, 655, 841 ], pat: [ 512, 598, 641, 705, 842 ], capex: [ 210, 340, 410, 380, 455 ] },
    debt: { net_debt: 1_120, equity: 3_980, ebitda_ttm: 1_507, wc_days: [ 58, 55, 52, 48, 41 ] },
    cash_source: "Annual reports FY22–FY26, cash-flow statements (fixture)",
    ledger: [
      { metric: "Sales volume growth", period: "FY26 guidance", kind: "quant",
        statement: "We should comfortably do 15 to 18% volume growth this year.",
        said: { doc: "Q4 FY25 earnings call (fixture)", date: "12 May 2025", page: 6 },
        band: { low: 15, high: 18, unit: "%" }, scale: { min: 0, max: 30 },
        actual: { value: 19.2, unit: "%", period: "FY26", doc: "Q4 FY26 earnings call (fixture)", page: 4 },
        method: "Reported annual sales volume, FY26 vs FY25.", status: "Delivered",
        why: "Reported 19.2% is above the top of the promised range." },
      { metric: "EBITDA per tonne", period: "Q2 FY27 guidance", kind: "quant",
        statement: "We expect ₹4,500 to ₹5,000 a tonne going forward.",
        said: { doc: "Q1 FY27 earnings call (fixture)", date: "6 Aug 2026", page: 9 },
        band: { low: 4500, high: 5000, unit: "₹/t" }, scale: { min: 3500, max: 5500 },
        actual: { value: 4310, unit: "₹/t", period: "Q2 FY27", doc: "Q2 FY27 results + call (fixture)", page: 4 },
        method: "EBITDA from results ÷ sales volume stated in the call.", status: "Partly delivered",
        why: "₹4,310 is 4.2% below the bottom of the range; FINN marks shortfalls within 10% as partly delivered." },
      { metric: "Capital expenditure", period: "FY27 guidance", kind: "quant",
        statement: "Capex of about ₹600 crore this year.",
        said: { doc: "Q4 FY26 earnings call (fixture)", date: "14 May 2026", page: 11 },
        band: { low: 600, high: 600, unit: "₹ cr" }, scale: null,
        actual: null, method: "Full-year cash-flow statement.", status: "Not yet measurable",
        why: "FY27 ends in March 2027. H1 spend of ₹212 crore is reported in the half-yearly cash flow, but a run-rate is not a result." },
      { metric: "Working capital", period: "FY26 commitment", kind: "qual",
        statement: "Bringing working capital down is a priority for us this year.",
        said: { doc: "Q4 FY25 earnings call (fixture)", date: "12 May 2025", page: 8 },
        actual: { text: "Working-capital days fell from 48 to 41 (FY25 → FY26), computed from the balance sheet.", doc: "Annual Report FY26 (fixture)", page: 112 },
        method: "Directional check only; no numeric target was stated.", status: "Delivered",
        why: "The direction matches the commitment. No target was given, so FINN does not judge the size." },
      { metric: "Exports", period: "FY26 commitment", kind: "qual",
        statement: "We want to build a meaningful export business.",
        said: { doc: "Q2 FY26 earnings call (fixture)", date: "7 Nov 2025", page: 12 },
        actual: null, method: "Needs an export revenue figure.", status: "Insufficient evidence",
        why: "Neither the annual report nor later calls disclose export revenue, so the statement can't be checked." },
    ],
  },
};
DOSSIERS["FX-CABLES"] = {
  symbol: "FX-CABLES", company: "Fixture Cables Ltd", exchange: "NSE", sector: "Cables and wires (fixture)",
  price: { value: 1_284.0, date: "29 Oct 2026", source: "Fixture EOD data" },
  coverage: { transcripts: 4, annual_reports: 1, updated_at: "29 Oct 2026" },
  overview: { summary: "Makes power and control cables and building wires for utilities, industry and housing.",
    cite: { doc: "Annual Report FY26 (fixture)", page: 9, passage: "Our products span power cables, control cables and building wires…" },
    segments: [ { name: "Cables", share: 71 }, { name: "Building wires", share: 29 } ],
    segments_cite: { doc: "Annual Report FY26 (fixture)", page: 31, passage: "Cables 71%, building wires 29% of revenue." } },
  quarters: Q,
  q: { revenue: [1_920, 2_002, 1_985, 2_119, 2_204, 2_281, 2_281, 2_418],
       ebitda:  [ 259,  273,  264,  281,  289,  302,  298,  291 ],
       pbt:     [ 214,  226,  219,  237,  241,  253,  254,  244 ],
       pat:     [ 160,  169,  163,  178,  180,  189,  189,  182 ] },
  q_source: "Quarterly results tables (fixture)",
  years: ["FY22","FY23","FY24","FY25","FY26"],
  cash: { ocf: [ 380, 420, 515, 610, 640 ], pat: [ 410, 480, 560, 640, 716 ], capex: [ 120, 150, 190, 230, 260 ] },
  debt: { net_debt: -240, equity: 3_100, ebitda_ttm: 1_180, wc_days: [ 72, 70, 69, 66, 67 ] },
  cash_source: "Annual reports FY22–FY26, cash-flow statements (fixture)",
  ledger: [
    { metric: "Revenue growth", period: "FY27 guidance", kind: "quant",
      statement: "We are targeting 12 to 15% revenue growth in FY27.",
      said: { doc: "Q4 FY26 earnings call (fixture)", date: "13 May 2026", page: 5 },
      band: { low: 12, high: 15, unit: "%" }, scale: null, actual: null,
      method: "Full-year revenue, FY27 vs FY26.", status: "Not yet measurable",
      why: "FY27 is not complete. H1 growth is shown in Financials but is not treated as the result." },
  ],
};

// ---------- Research notes (prepared answers for the example questions; fixture) ----------
export const RESEARCH = {
  "FX-TUBES": [
    { q: "Why did EBITDA per tonne fall short of guidance?",
      findings: [
        { text: "Q2 FY27 EBITDA per tonne was ₹4,310, below the ₹4,500–5,000 range given in the Q1 call.", cite: { doc: "Q2 FY27 results + call (fixture)", page: 4, passage: "…EBITDA per tonne for the quarter was ₹4,310…" } },
        { text: "Management attributed the gap to lower realisations in solar structures after a steel price correction.", cite: { doc: "Q2 FY27 earnings call (fixture)", page: 7, passage: "…the correction in HR coil prices compressed realisations, particularly in solar structures…" } },
      ],
      implication: "If the explanation holds, the shortfall is price-driven rather than a loss of volume; volume grew 21% year on year.",
      uncertainty: "The call gives no split of EBITDA per tonne by segment, so the solar explanation can't be verified from the numbers." },
    { q: "What did management guide for FY27 capex, and how much has been spent?",
      findings: [
        { text: "Management guided about ₹600 crore of capex for FY27.", cite: { doc: "Q4 FY26 earnings call (fixture)", page: 11, passage: "…capex of about ₹600 crore this year, largely for the new Raipur line…" } },
        { text: "H1 FY27 capex was ₹212 crore according to the half-yearly cash-flow statement.", cite: { doc: "H1 FY27 results (fixture)", page: 6, passage: "Purchase of property, plant and equipment: (212.4)" } },
      ],
      implication: "Spending would need to roughly double in H2 to reach the guidance.",
      uncertainty: "Capex is often back-ended; one half-year is not evidence of a miss." },
    { q: "How has working capital changed over the last two years?",
      findings: [
        { text: "Working-capital days fell from 52 in FY24 to 41 in FY26, computed from receivables, inventory and payables.", cite: { doc: "Annual Report FY26 (fixture)", page: 112, passage: "Trade receivables 512.6; Inventories 798.2; Trade payables 506.9" } },
      ],
      implication: "Lower working capital explains part of the jump in operating cash flow in FY26.",
      uncertainty: "Year-end balances can be managed; quarterly balances are not disclosed." },
  ],
};

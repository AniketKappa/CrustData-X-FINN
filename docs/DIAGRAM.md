# FINN — how it is built

```mermaid
flowchart LR
  subgraph Sources["Public data sources (polite, cached, no logins)"]
    Y["Yahoo Finance<br/>daily prices, 10 yrs + Nifty 50/500"]
    N["NSE RSS<br/>announcements"]
    B["BSE API<br/>filings + PDFs"]
    S["Screener<br/>results, ratios, docs"]
    G["Google News / publisher RSS<br/>headlines only"]
  end

  subgraph Server["FastAPI server on Render (one container)"]
    R["Refresh pipeline<br/>every 10 min + backfill at start-up"]
    DB[("SQLite store<br/>prices, filings, news, snapshots")]
    C["Rules in Python<br/>classify filings · alerts · red flags"]
    F["Factor engine<br/>momentum · quality · safety · value"]
    K["FINN Rank 1–10<br/>+ price-only backtest"]
    H["Portfolio health<br/>fixed formula"]
    P["PDF reader<br/>results numbers, one-line summaries"]
    RS["Research engine<br/>BM25 over annual reports + transcripts"]
    V["Validators<br/>citations exist · numbers match · no advice words"]
    L["LLM router (llm.py)<br/>fast / long routes, quota tracking, cache"]
  end

  subgraph Models["Free models"]
    Q1["Groq: gpt-oss-120b, gpt-oss-20b<br/>+ any other model the key can use"]
    Q2["OpenRouter free models"]
  end

  subgraph App["Web app (PWA, same origin)"]
    U1["Briefing<br/>by company"]
    U2["Company page<br/>FINN Signal + calculation"]
    U3["Portfolio<br/>health + ranks"]
    U4["Research<br/>cited dossier + Ask"]
  end

  Y & N & B & S & G --> R --> DB
  DB --> C --> U1
  DB --> F --> K --> U2
  K --> H --> U3
  B --> P --> L
  DB --> RS --> L
  L <--> Q1
  L <--> Q2
  L --> V --> U1
  V --> U4
  C --> U2
```

**Rule of the system:** numbers, ranks, flags and health are computed in Python. Models only locate or reword
facts they are given, and every model output is checked (cited ids must exist, every % and ₹ must match the
data, no advice or prediction words) before it is shown; otherwise a rule-based text is shown instead.

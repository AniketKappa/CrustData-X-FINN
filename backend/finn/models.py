"""Typed data contracts for the Push pipeline (ARCHITECTURE §4, §4a, §10).

Pydantic models are the single source of truth; the frontend types are generated from OpenAPI.
Every observation carries Provenance: where it came from, when it was retrieved, and for which date.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SourceClass(str, Enum):
    PRIMARY_DOC = "PRIMARY_DOC"
    STANDARDIZED_TABLE = "STANDARDIZED_TABLE"
    DERIVED = "DERIVED"
    MARKET_DATA = "MARKET_DATA"
    EXTERNAL_WEB = "EXTERNAL_WEB"


class Provenance(BaseModel):
    source_class: SourceClass
    source_name: str                      # e.g. "yfinance", "nse_rss", "fixture"
    url: Optional[str] = None
    retrieved_at: datetime                # when FINN fetched it (UTC-aware)
    data_date: Optional[date] = None      # the trading/filing date the value belongs to
    locator: Optional[str] = None
    formula: Optional[str] = None
    fixture: bool = False                 # True for synthetic test/demo data


Exchange = Literal["NSE", "BSE"]


class Instrument(BaseModel):
    """A normalised listing. `key` is the canonical id used across the pipeline (e.g. 'NSE:INFY')."""
    exchange: Exchange
    code: str                             # NSE symbol ('INFY', 'M&M') or BSE scrip code ('500209')
    key: str
    yahoo: str                            # 'INFY.NS' / '500209.BO'


class Company(BaseModel):
    symbol: str                           # NSE symbol; canonical company id
    name: str
    bse_code: Optional[str] = None
    sector: Optional[str] = None
    size: Optional[str] = None
    is_lender: bool = False
    role: Literal["holding", "research", "other"] = "other"
    aliases: list[str] = Field(default_factory=list)
    news_terms: list[str] = Field(default_factory=list)
    news_exclude: list[str] = Field(default_factory=list)


# ---------- market data ----------
class PriceBar(BaseModel):
    instrument_key: str
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[float] = None
    provenance: Provenance


class Availability(str, Enum):
    OK = "ok"
    STALE = "stale"                       # latest bar older than the expected session
    INSUFFICIENT_HISTORY = "insufficient_history"
    NO_DATA = "no_data"                   # empty response / unknown or suspended symbol
    PROVIDER_ERROR = "provider_error"     # provider failed; may fall back to cached bars


class MarketSignal(BaseModel):
    """Derived daily metrics for one instrument. Values are None when they cannot be computed honestly."""
    instrument_key: str
    symbol: str
    as_of: Optional[date] = None          # date of the latest bar used
    close: Optional[float] = None
    prev_close: Optional[float] = None
    pct_change: Optional[float] = None    # (close / prev_close - 1) * 100
    volume: Optional[float] = None
    avg_volume: Optional[float] = None    # mean of the previous N sessions (excludes as_of)
    volume_multiple: Optional[float] = None
    lookback_used: int = 0
    live: bool = False                    # True while today's session is open (price so far, not a close)
    live_at: Optional[datetime] = None    # when the in-session price was fetched
    changes: dict[str, float] = Field(default_factory=dict)   # "1"/"3"/"5" sessions back -> % change to latest
    availability: Availability
    notes: list[str] = Field(default_factory=list)   # plain-language disclosures shown in the UI
    provenance: Optional[Provenance] = None


class AlertThresholds(BaseModel):
    pct_change_abs: float = Field(5.0, gt=0, le=50)
    volume_multiple: float = Field(2.0, gt=1, le=50)
    lookback_sessions: int = Field(20, ge=2, le=250)
    min_history_sessions: int = Field(10, ge=1, le=250)


class MarketAlert(BaseModel):
    key: str                              # stable: hash(rule, symbol, date)
    symbol: str
    date: date
    rules: list[Literal["price", "volume"]]
    pct_change: Optional[float]
    volume_multiple: Optional[float]
    explanation: str                      # e.g. "Close down 5.2% (threshold ±5.0%)"
    close: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None
    avg_volume: Optional[float] = None
    lookback_used: int = 0
    live: bool = False                    # today's session still open: move so far
    thresholds: AlertThresholds
    provenance: Provenance


# ---------- announcements ----------
CATEGORIES = (
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
)


class Attachment(BaseModel):
    url: str
    size_text: Optional[str] = None       # as published, e.g. "245 KB"
    kind: Optional[str] = None            # pdf | xml | zip | other


class Announcement(BaseModel):
    """The source record. Original subject and link are preserved verbatim and never replaced."""
    uid: str                              # dedup key, see dedup_key()
    source: str                           # nse_rss | nse_json | bse_rss | fixture
    exchange: Exchange
    symbol: Optional[str]                 # None when the item could not be mapped
    company_name: str
    subject: str                          # original subject / desc, verbatim
    detail: Optional[str] = None          # original attachment text / description, verbatim
    filed_at: datetime                    # exchange dissemination time, timezone-aware (IST)
    source_url: Optional[str] = None      # link to the original filing/attachment
    attachments: list[Attachment] = Field(default_factory=list)
    source_category: Optional[str] = None # exchange's own category label if present
    exchange_id: Optional[str] = None     # e.g. NSE seq_id
    provenance: Provenance


class NewsItem(BaseModel):
    """A media headline about a portfolio company (EXTERNAL_WEB). Only the headline, publisher, time and link
    are kept: never the article text. It is labelled as news everywhere and never presented as a filing."""
    uid: str
    symbol: str
    company_name: str
    headline: str                         # as published, minus the trailing " - Publisher" that aggregators add
    publisher: str
    publisher_domain: Optional[str] = None
    url: str
    published_at: datetime
    feed: str                             # google_news | publisher RSS name
    provenance: Provenance


class Classification(BaseModel):
    category: str
    subtype: Optional[str] = None
    method: Literal["rule", "llm", "default"]
    rule: Optional[str] = None            # which rule matched (explainability)
    confidence: float = Field(ge=0, le=1)


class ScoreBreakdown(BaseModel):
    materiality: float
    recency: float
    relevance: float
    confidence: float
    weights: dict[str, float]
    total: float
    reasons: list[str]


Tier = Literal["high", "normal", "routine"]


class DigestItem(BaseModel):
    id: str
    kind: Literal["announcement", "market_alert", "news"]
    symbol: Optional[str]
    company_name: str
    title: str                            # original subject (never a generated summary)
    filed_at: datetime
    category: str
    tier: Tier
    score: ScoreBreakdown
    source_url: Optional[str]
    announcement: Optional[Announcement] = None
    classification: Optional[Classification] = None
    alert: Optional[MarketAlert] = None
    news: Optional[NewsItem] = None
    results: Optional[dict] = None        # screener ResultsBlock (headline numbers) for results items
    results_status: Optional[str] = None  # why numbers are missing, if they are
    summary: Optional[dict] = None          # one-line summary read from the filed PDF {text, url, page}
    related: list[dict] = Field(default_factory=list)   # other outlets' headlines for the same story
    person: Optional[dict] = None         # management changes: incoming person and sourced background
    summary: Optional[str] = None         # optional generated one-liner, shown IN ADDITION to the title
    why: Optional[dict] = None            # market alerts: "why did it move" {summary, cited_ids, confidence_note}


class SourceStatus(BaseModel):
    name: str
    enabled: bool
    status: Literal["ok", "degraded", "failed", "disabled", "cached", "fixture"]
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
    items: int = 0
    note: Optional[str] = None


class Digest(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    window_hours: int
    high: list[DigestItem]
    normal: list[DigestItem]
    routine: list[DigestItem]
    routine_count: int
    news: list[DigestItem] = Field(default_factory=list)   # media headlines, top N, kept apart from filings
    market: list[MarketSignal]
    sources: list[SourceStatus]
    disclosures: list[str]                # delayed/stale/unavailable notices for the banner
    fixture: bool

"""Push pipeline: refresh (network, cached, rate-limited) and digest (read-only, no network).

refresh_*  fetch from providers at most once per TTL per key, write to the store, log every attempt.
digest     reads the store only, so rendering never triggers an external call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .classify import classify, classify_headline
from .config import Portfolio, Settings
from .http import FetchError
from .market import session_alerts, compute_signal, evaluate_alert, expected_session
from .models import (AlertThresholds, Announcement, Availability, Company, Digest, DigestItem, MarketSignal,
                     SourceStatus)
from .providers.announcements import (BseRssSource, NseJsonSource, NseRssSource, SourceSchemaError)
from .people import BioLine, Change, Person, brief_profile_from_pdf, parse_change, sentences_about, wikipedia_match, write_brief
from .providers.news import NewsSource, is_noise, publisher_rank
from .providers.websearch import tavily_search
from .providers.prices import PriceProvider, PriceProviderError
from .providers.screener import CompanySnapshot, results_from_snapshot
from .rank import score_alert, score_announcement
from .store import Store
from .symbols import SymbolError, normalize

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class RefreshReport:
    fetched: list[str] = field(default_factory=list)
    skipped_fresh: list[str] = field(default_factory=list)
    skipped_backoff: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    new_announcements: int = 0
    merged_announcements: int = 0


def fetch_parallel(calls: list, workers: int = 6) -> list:
    """Run network calls concurrently; returns [(key, result or exception)] in the input order. Only the network
    part runs in threads; callers write to the store from the main thread. Per-host spacing still applies (HttpClient)."""
    from concurrent.futures import ThreadPoolExecutor

    def run(item):
        key, call = item
        try:
            return key, call()
        except Exception as e:  # noqa: BLE001 - returned to the caller, who classifies it
            return key, e
    if len(calls) <= 1:
        return [run(c) for c in calls]
    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as ex:
        return list(ex.map(run, calls))


class Pipeline:
    def __init__(self, settings: Settings, portfolio: Portfolio, store: Store, prices: PriceProvider,
                 nse_rss: Optional[NseRssSource] = None, nse_json: Optional[NseJsonSource] = None,
                 bse_rss: Optional[BseRssSource] = None, clock: Callable[[], datetime] | None = None,
                 fixture: bool = False, news: Optional[NewsSource] = None, screener=None, llm=None, bse_api=None,
                 filings=None):
        self.s, self.portfolio, self.store, self.prices = settings, portfolio, store, prices
        self.news = news
        self.screener = screener
        self.llm = llm
        self.research = None                       # set by factory.attach_research
        self.nse_rss, self.nse_json, self.bse_rss = nse_rss, nse_json, bse_rss
        self.bse_api = bse_api
        self.filings = filings                     # FilingReader: results numbers + one-line summaries from PDFs
        self.clock = clock or (lambda: datetime.now(IST))
        self.fixture = fixture

    # ------------------------------------------------------------ refresh: prices
    def tracked(self) -> list[str]:
        return [c.symbol for c in self.portfolio.holdings + self.portfolio.research]

    def refresh_prices(self, symbols: list[str] | None = None, force: bool = False) -> RefreshReport:
        rep = RefreshReport()
        cfg = self.s.sources["prices"]
        due = []
        for sym in symbols or self.tracked():
            try:
                inst = normalize(sym)
            except SymbolError as e:
                self.store.log_fetch("prices", sym, False, f"unsupported: {e}")
                rep.failed[sym] = f"unsupported: {e}"
                continue
            if not force and self.store.is_fresh("prices", inst.key, cfg["cache_ttl_minutes"], self.clock()):
                rep.skipped_fresh.append(inst.key)
                continue
            if not force and self.store.in_backoff("prices", inst.key, cfg["failure_backoff_minutes"], self.clock()):
                rep.skipped_backoff.append(inst.key)
                continue
            due.append(inst)
        if not due:
            return rep
        if len(due) > 1 and getattr(self.prices, "name", "") == "yfinance":
            from .providers.prices import fetch_many_yf
            results = fetch_many_yf(self.prices, due, cfg["history_days"])     # one request for the whole list
        else:
            results = {}
            for inst in due:
                try:
                    results[inst.key] = self.prices.fetch(inst, cfg["history_days"])
                except PriceProviderError as e:
                    results[inst.key] = e
        for inst in due:
            r = results.get(inst.key)
            if isinstance(r, PriceProviderError) or r is None:
                err = r or PriceProviderError("error", "no result")
                self.store.log_fetch("prices", inst.key, False, f"{err.kind}: {err.detail}", at=self.clock())
                rep.failed[inst.key] = err.kind
                continue
            self.store.upsert_bars(r)
            self.store.log_fetch("prices", inst.key, True, items=len(r), at=self.clock())
            rep.fetched.append(inst.key)
        return rep

    # ------------------------------------------------------------ refresh: announcements
    def refresh_announcements(self, force: bool = False, backfill: bool = True,
                              symbols: list[str] | None = None) -> RefreshReport:
        rep = RefreshReport()
        ttl = self.s.sources["announcements"]["cache_ttl_minutes"]
        backoff = self.s.sources["announcements"]["failure_backoff_minutes"]
        feeds = [(self.nse_rss, "feed"), (self.bse_rss, "feed")]
        for src, key in feeds:
            if src is None:
                continue
            if not force and self.store.is_fresh(src.name, key, ttl, self.clock()):
                rep.skipped_fresh.append(f"{src.name}:{key}")
                continue
            if not force and self.store.in_backoff(src.name, key, backoff, self.clock()):
                rep.skipped_backoff.append(f"{src.name}:{key}")
                continue
            self._run(src.name, key, lambda s=src: s.fetch(), rep)
        if self.bse_api is not None:
            due = []
            for sym in (symbols or self.tracked()):
                snap = self.snapshot(sym)
                code = snap.bse_code if snap else None
                if not code:
                    self.store.log_fetch("bse_api", sym, False, "no_code: BSE code not found on the Screener page",
                                         at=self.clock())
                    continue
                if not force and self.store.is_fresh("bse_api", sym, ttl, self.clock()):
                    rep.skipped_fresh.append(f"bse_api:{sym}")
                    continue
                if not force and self.store.in_backoff("bse_api", sym, backoff, self.clock()):
                    rep.skipped_backoff.append(f"bse_api:{sym}")
                    continue
                due.append((sym, lambda s=sym, c=code: self.bse_api.fetch_code(s, c)))
            for sym, res in fetch_parallel(due):
                self._run("bse_api", sym, (lambda r=res: _raise_or(r)), rep)
        if self.nse_json is not None and backfill:
            for sym in self.tracked():
                if not force and self.store.is_fresh("nse_json", sym, ttl, self.clock()):
                    rep.skipped_fresh.append(f"nse_json:{sym}")
                    continue
                if not force and self.store.in_backoff("nse_json", sym, backoff, self.clock()):
                    rep.skipped_backoff.append(f"nse_json:{sym}")
                    continue
                ok = self._run("nse_json", sym, lambda s=sym: self.nse_json.fetch_symbol(s), rep)
                if ok == "schema":   # the endpoint changed shape: stop calling it this run
                    break
        return rep

    def refresh_all(self, force: bool = False, on_stage: Optional[Callable[[str], None]] = None) -> dict:
        """Two stages, so the Briefing appears fast.
        Stage 1 (seconds): prices (one batched request), Screener pages, news and the NSE feed in parallel; then
        each company's BSE filings in parallel (they need the BSE code from the Screener page). -> on_stage("ready")
        Stage 2 (slower, model-bound): read results PDFs, one-line summaries, executive backgrounds."""
        from concurrent.futures import ThreadPoolExecutor

        out: dict = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_prices = ex.submit(self.refresh_prices, None, force)
            f_news = ex.submit(self.refresh_news, force)
            f_comp = ex.submit(self.refresh_companies, None, force)
            out["companies"] = f_comp.result()
            out["announcements"] = self.refresh_announcements(force=force)
            out["prices"], out["news"] = f_prices.result(), f_news.result()
        if on_stage:
            on_stage("ready")
        out["filings"] = self.refresh_filings()
        out["people"] = self.refresh_people(force=force)
        if on_stage:
            on_stage("done")
        return {k: v.__dict__ for k, v in out.items()}

    # ------------------------------------------------------------ refresh: news (D-51)
    def refresh_news(self, force: bool = False) -> RefreshReport:
        rep = RefreshReport()
        if self.news is None:
            return rep
        cfg = self.s.sources["news"]
        jobs = [(f"google:{c.symbol}", (lambda c=c: self.news.fetch_company(c)))
                for c in self.portfolio.holdings + self.portfolio.research]
        jobs += [(f"feed:{f['name']}", (lambda f=f: self.news.fetch_publisher(f))) for f in cfg.get("publisher_feeds", [])]
        due = []
        for key, call in jobs:
            if not force and self.store.is_fresh("news", key, cfg["cache_ttl_minutes"], self.clock()):
                rep.skipped_fresh.append(key)
                continue
            if not force and self.store.in_backoff("news", key, cfg["failure_backoff_minutes"], self.clock()):
                rep.skipped_backoff.append(key)
                continue
            due.append((key, call))
        for key, items in fetch_parallel(due):
            if isinstance(items, Exception):
                e = items
                if not isinstance(e, (SourceSchemaError, FetchError)):
                    e = FetchError(key, "error", f"{e.__class__.__name__}: {e}")
                self.store.log_fetch("news", key, False, f"{getattr(e, 'kind', 'schema')}: {getattr(e, 'detail', e)}",
                                     at=self.clock())
                rep.failed[key] = getattr(e, "kind", "schema")
                continue
            rep.new_announcements += self.store.add_news(items)
            self.store.log_fetch("news", key, True, items=len(items), at=self.clock())
            rep.fetched.append(key)
        return rep

    # ------------------------------------------------------------ refresh: company fundamentals (screener)
    def refresh_companies(self, symbols: list[str] | None = None, force: bool = False) -> RefreshReport:
        rep = RefreshReport()
        if self.screener is None:
            return rep
        cfg = self.s.sources["screener"]
        due = []
        for sym in symbols or self.tracked():
            # A record saved by an older version may be missing: then the TTL does not apply.
            if not force and self.store.get_company(sym) is not None and \
                    self.store.is_fresh("screener", sym, cfg["cache_ttl_minutes"], self.clock()):
                rep.skipped_fresh.append(sym)
                continue
            if not force and self.store.in_backoff("screener", sym, cfg["failure_backoff_minutes"], self.clock()):
                rep.skipped_backoff.append(sym)
                continue
            due.append((sym, lambda s=sym: self.screener.fetch_company(s)))
        for sym, snap in fetch_parallel(due):
            if isinstance(snap, Exception):
                e = snap
                self.store.log_fetch("screener", sym, False, f"{getattr(e, 'kind', 'schema')}: {getattr(e, 'detail', e)}",
                                     at=self.clock())
                rep.failed[sym] = getattr(e, "kind", "schema")
                continue
            self.store.put_company(sym, snap.model_dump_json())
            self.store.log_fetch("screener", sym, True, items=1, at=self.clock())
            rep.fetched.append(sym)
        return rep

    # ------------------------------------------------------------ refresh: read the filed PDFs
    SUMMARY_CATEGORIES = {"M&A", "fund_raise", "management_change", "litigation", "credit_rating", "capex",
                          "press_release", "dividend", "bonus_split", "pledging", "insider_trading"}

    def refresh_filings(self, days: int = 7, max_results: int = 8, max_summaries: int = 20) -> RefreshReport:
        """Results numbers from results PDFs and one-line summaries of other material filings (cached per filing)."""
        rep = RefreshReport()
        if self.filings is None or not self.filings.available:
            return rep
        now = self.clock()
        aliases: dict = {}
        anns = [a for a in _collapse_cross_exchange(self.store.announcements_between(now - timedelta(days=days), now), aliases)
                if self.portfolio.role_of(a.symbol) in ("holding", "research") and a.attachments
                and (a.attachments[0].kind or "pdf") == "pdf"]
        anns.sort(key=lambda a: a.filed_at, reverse=True)
        n_res = n_sum = 0
        for a in anns:
            if self.filings.cached(a.uid):
                continue
            c = classify(a)
            # the other exchange's copy of the same filing, if any: its PDF is tried when this one can't be read
            urls = [a.attachments[0].url] + [b.attachments[0].url for b in aliases.get(a.uid, []) if b.attachments]
            url = urls[0]
            try:
                if c.category == "results" and c.subtype not in ("results_newspaper_ad", "results_board_meeting_notice"):
                    if n_res >= max_results:
                        continue
                    n_res += 1
                    snap = self.snapshot(a.symbol)
                    latest = None
                    if snap and snap.quarters:
                        rev = snap.quarters.rows.get("sales") or snap.quarters.rows.get("revenue")
                        qs = [i for i, p in enumerate(snap.quarters.periods) if p != "TTM"]
                        latest = rev[qs[-1]] if rev and qs else None
                    co = self.portfolio.companies.get(a.symbol)
                    lender = bool((co and co.is_lender) or (snap and snap.quarters and "financing profit" in snap.quarters.rows))
                    for url in urls:
                        r = self.filings.results(a.uid, url, a.symbol, lender, latest, self.fixture)
                        if r.get("status") != "unreadable":
                            break
                elif c.category in self.SUMMARY_CATEGORIES:
                    if n_sum >= max_summaries:
                        continue
                    n_sum += 1
                    for url in urls:
                        r = self.filings.summary(a.uid, url, a.subject)
                        if r.get("status") != "unreadable":
                            break
                else:
                    continue
            except Exception as e:  # noqa: BLE001 - one bad PDF must not stop the refresh
                rep.failed[a.uid] = e.__class__.__name__
                continue
            (rep.fetched if r.get("status") == "ok" else rep.skipped_backoff).append(a.uid)
        return rep

    def snapshot(self, symbol: str) -> Optional[CompanySnapshot]:
        raw = self.store.get_company(symbol)
        return CompanySnapshot.model_validate_json(raw) if raw else None

    def attach_results(self, items: list[DigestItem]) -> None:
        if self.filings is not None:
            for i in items:
                if i.kind == "announcement" and i.category != "results":
                    ext = self.filings.cached(i.id)
                    if ext and ext.get("status") == "ok" and ext.get("text"):
                        i.summary = {"text": ext["text"], "url": ext["url"], "page": ext["page"]}
        for i in items:
            if i.category != "results" or not i.symbol:
                continue
            if i.classification and i.classification.subtype in ("results_newspaper_ad", "results_board_meeting_notice"):
                continue
            ext = self.filings.cached(i.id) if (self.filings is not None and i.kind == "announcement") else None
            if ext and ext.get("status") == "ok" and ext.get("block"):
                i.results = ext["block"]                 # numbers read from the filed results PDF
                continue
            snap = self.snapshot(i.symbol)
            c = self.portfolio.companies.get(i.symbol)
            if snap is not None:
                try:
                    i.results = results_from_snapshot(snap, bool(c and c.is_lender)).model_dump(mode="json")
                except SourceSchemaError as e:
                    i.results_status = f"Headline numbers unavailable: {e}"
            else:
                last = self.store.last_fetch("screener", i.symbol)
                i.results_status = ("Headline numbers unavailable: " + last["error"]) if last is not None and not last["ok"] \
                    else ("Headline numbers not fetched yet; they will appear in a moment." if self.screener else
                          "Headline numbers need the Screener source, which is switched off.")

    # ------------------------------------------------------------ portfolio edits
    def add_company(self, company: Company) -> Company:
        c = self.portfolio.add(company)
        if self.news is not None:
            self.news.portfolio = self.portfolio
        return c

    def refresh_symbol(self, symbol: str) -> dict:
        """Everything for one newly added company, in parallel where possible (bypasses TTLs for that symbol):
        prices + news + Screener at once, then its BSE filings (they need the BSE code from Screener)."""
        from concurrent.futures import ThreadPoolExecutor

        c = self.portfolio.companies.get(symbol)
        out: dict = {}

        def news():
            rep = RefreshReport()
            if self.news is None or c is None:
                return rep
            try:
                items = self.news.fetch_company(c)
                rep.new_announcements = self.store.add_news(items)
                self.store.log_fetch("news", f"google:{symbol}", True, items=len(items), at=self.clock())
                rep.fetched.append(f"google:{symbol}")
            except (SourceSchemaError, FetchError) as e:
                self.store.log_fetch("news", f"google:{symbol}", False, str(e), at=self.clock())
                rep.failed[f"google:{symbol}"] = getattr(e, "kind", "schema")
            return rep
        with ThreadPoolExecutor(max_workers=3) as ex:
            fp = ex.submit(self.refresh_prices, [symbol], True)
            fn = ex.submit(news)
            out["companies"] = self.refresh_companies([symbol], force=True).__dict__
            out["announcements"] = self.refresh_announcements(force=True, backfill=False, symbols=[symbol]).__dict__
            out["prices"], out["news"] = fp.result().__dict__, fn.result().__dict__
        return out

    # ------------------------------------------------------------ company page
    def company_view(self, symbol: str, th: AlertThresholds | None = None) -> dict:
        c = self.portfolio.companies.get(symbol)
        inst = normalize(symbol)
        bars = self.store.bars(inst.key, limit=70)
        sig = compute_signal(symbol, inst.key, bars, th or self.s.thresholds, self.clock(), self.s.staleness_days)
        snap = self.snapshot(symbol)
        results = None
        if snap is not None:
            try:
                results = results_from_snapshot(snap, bool(c and c.is_lender)).model_dump(mode="json")
            except SourceSchemaError:
                results = None
        anns = self.store.announcements_for(symbol)
        return {
            "symbol": symbol, "name": (c.name if c else (snap.name if snap else symbol)),
            "role": c.role if c else "other", "sector": (c.sector if c and c.sector else (snap.sector if snap else None)),   # B5: curated first
            "industry": snap.industry if snap else None, "exchange": inst.exchange,
            "signal": sig.model_dump(mode="json"),
            "history": [{"date": b.date.isoformat(), "close": b.close, "volume": b.volume} for b in bars],
            "snapshot": snap.model_dump(mode="json") if snap else None, "results": results,
            "filings": [{"id": a.uid, "subject": a.subject, "detail": a.detail, "filed_at": a.filed_at.isoformat(),
                         "url": a.source_url, "category": classify(a).category} for a in anns],
            "news": [n.model_dump(mode="json") for n in self.store.news_for(symbol)],
            "status": self._company_status(symbol, snap),
            "fixture": self.fixture,
        }

    def _company_status(self, symbol: str, snap) -> list[str]:
        notes = []
        last = self.store.last_fetch("screener", symbol)
        if snap is None:
            notes.append("Fundamentals not fetched yet." if last is None or last["ok"] else
                         f"Fundamentals unavailable from Screener ({last['error']}).")
        elif snap.notes:
            notes += snap.notes
        return notes

    def _run(self, source: str, key: str, call, rep: RefreshReport) -> str:
        try:
            items = call()
        except SourceSchemaError as e:
            self.store.log_fetch(source, key, False, f"schema: {e}", at=self.clock())
            rep.failed[f"{source}:{key}"] = "schema"
            return "schema"
        except FetchError as e:
            self.store.log_fetch(source, key, False, f"{e.kind}: {e.detail}", at=self.clock())
            rep.failed[f"{source}:{key}"] = e.kind
            return "error"
        new, merged = self.store.add_announcements(items)
        rep.new_announcements += new
        rep.merged_announcements += merged
        self.store.log_fetch(source, key, True, items=len(items), at=self.clock())
        rep.fetched.append(f"{source}:{key}")
        return "ok"

    # ------------------------------------------------------------ read side
    def market_signals(self, th: AlertThresholds) -> list[MarketSignal]:
        out = []
        now = self.clock()
        for sym in self.tracked():
            inst = normalize(sym)
            bars = self.store.bars(inst.key, limit=th.lookback_sessions + 5)
            sig = compute_signal(sym, inst.key, bars, th, now, self.s.staleness_days)
            last = self.store.last_fetch("prices", inst.key)
            if last is not None and not last["ok"]:
                err = last["error"] or "unknown error"
                if not bars:
                    sig.availability = (Availability.NO_DATA if err.startswith(("no_data", "unsupported"))
                                        else Availability.PROVIDER_ERROR)
                    sig.notes = [_plain_price_error(err)]
                else:
                    sig.notes.append(f"Latest refresh failed ({err.split(':')[0]}); showing cached prices "
                                     f"to {sig.as_of:%d %b %Y}.")
            elif last is None and not bars:
                sig.notes = ["Prices have not been fetched yet."]
            out.append(sig)
        return out

    def digest(self, window_hours: int | None = None, thresholds: AlertThresholds | None = None,
               include_non_portfolio: bool = False) -> Digest:
        rcfg = self.s.ranking
        window_hours = window_hours or rcfg["default_window_hours"]
        if window_hours not in rcfg["allowed_window_hours"]:
            raise ValueError(f"window_hours must be one of {rcfg['allowed_window_hours']}")
        th = thresholds or self.s.thresholds
        now = self.clock()
        start = now - timedelta(hours=window_hours)

        signals = self.market_signals(th)
        alerts = []
        sessions = max(1, min(10, round(window_hours / 24 * 5 / 7) + 1))
        for sig in signals:
            if sig.availability in (Availability.STALE, Availability.NO_DATA, Availability.PROVIDER_ERROR):
                continue
            bars = self.store.bars(sig.instrument_key, limit=th.lookback_sessions + sessions + 5)
            for j, (al, s) in enumerate(session_alerts(sig.symbol, sig.instrument_key, bars, th, now, sessions,
                                                        self.s.staleness_days)):
                close_at = (s.live_at or now) if al.live else datetime.combine(al.date, time(15, 30), tzinfo=IST)
                latest = al.date == sig.as_of
                if close_at > start or latest:
                    alerts.append((al, s, min(close_at, now)))
        alert_dates = {(al.symbol, al.date) for al, _, _ in alerts}

        anns = self.store.announcements_between(start, now)
        if not include_non_portfolio:
            anns = [a for a in anns if self.portfolio.role_of(a.symbol) in ("holding", "research")]
        anns = _collapse_cross_exchange(anns)

        items: list[DigestItem] = []
        for a in anns:
            c = classify(a)
            role = self.portfolio.role_of(a.symbol)
            s, tier = score_announcement(a, c, role, now, rcfg, alert_dates)
            items.append(DigestItem(id=a.uid, kind="announcement", symbol=a.symbol, company_name=a.company_name,
                                    title=a.subject, filed_at=a.filed_at, category=c.category, tier=tier, score=s,
                                    source_url=a.source_url, announcement=a, classification=c))
        for al, sig, close_at in alerts:
            conf = 100.0 if sig.availability == Availability.OK else 70.0
            role = self.portfolio.role_of(al.symbol)
            s, tier = score_alert(al, role, now, rcfg, conf, close_at)
            name = self.portfolio.companies[al.symbol].name if al.symbol in self.portfolio.companies else al.symbol
            items.append(DigestItem(id=f"alert:{al.key}", kind="market_alert", symbol=al.symbol, company_name=name,
                                    title=al.explanation, filed_at=close_at, category="market_move", tier=tier,
                                    score=s, source_url=al.provenance.url, alert=al))
        items.sort(key=lambda i: (-i.score.total, -i.filed_at.timestamp()))
        routine = [i for i in items if i.tier == "routine"]
        news = self._news_items(start, now, rcfg, alert_dates)
        self.attach_results(items + news)
        return Digest(
            generated_at=now, window_start=start, window_end=now, window_hours=window_hours,
            high=[i for i in items if i.tier == "high"], normal=[i for i in items if i.tier == "normal"],
            routine=routine, routine_count=len(routine), news=news, market=signals, sources=self.source_status(),
            disclosures=self.disclosures(signals), fixture=self.fixture,
        )

    def _news_items(self, start, now, rcfg, alert_dates) -> list[DigestItem]:
        """Headlines -> one item per story. Noise (price pages, stock-picks, market wraps, multi-company round-ups)
        is dropped; reports of the same event (same company, type and day) become one item with `related` links."""
        if self.news is None:
            return []
        from .models import Announcement as _A, Provenance as _P  # noqa: N814 - local alias for scoring only
        clusters: dict[tuple, list] = {}
        for n in self.store.news_between(start, now):
            role = self.portfolio.role_of(n.symbol)
            if role not in ("holding", "research") or is_noise(n.headline):
                continue
            probe = _A(uid=n.uid, source="news", exchange="NSE", symbol=n.symbol, company_name=n.company_name,
                       subject=n.headline, filed_at=n.published_at,
                       provenance=_P(source_class=n.provenance.source_class, source_name=n.feed, retrieved_at=now))
            c = classify(probe)
            c = c.model_copy(update={"confidence": min(0.6, c.confidence)})
            day = n.published_at.astimezone(IST).date()
            clusters.setdefault((n.symbol, c.category, day), []).append((n, probe, c, role))
        out = []
        for (sym, cat, _day), group in clusters.items():
            group.sort(key=lambda g: (publisher_rank(g[0].publisher), -g[0].published_at.timestamp()))
            n, probe, c, role = group[0]
            s, _ = score_announcement(probe, c, role, now, rcfg, alert_dates)
            s.reasons.append(f"media report via {n.publisher}, not a company filing"
                             + (f"; {len(group) - 1} more outlet(s) reported it" if len(group) > 1 else ""))
            item = DigestItem(id=n.uid, kind="news", symbol=n.symbol, company_name=n.company_name, title=n.headline,
                              filed_at=min(g[0].published_at for g in group), category=c.category, tier="normal",
                              score=s, source_url=n.url, classification=c, news=n,
                              related=[{"headline": g[0].headline, "publisher": g[0].publisher, "url": g[0].url,
                                        "published_at": g[0].published_at.isoformat()} for g in group[1:8]])
            if cat == "management_change":
                item.person = self._person_for(sym, [g[0].headline for g in group])
            out.append(item)
        out.sort(key=lambda i: (-i.score.total, -i.filed_at.timestamp()))
        return out[: self.s.sources.get("news", {}).get("max_items", 80)]

    # ------------------------------------------------------------ people (management changes)
    def _person_for(self, symbol: str, texts: list[str]) -> Optional[dict]:
        c = self.portfolio.companies.get(symbol)
        name = c.name if c else symbol
        change = Change()
        for t in texts:
            ch = parse_change(t, name)
            change.incoming = change.incoming or ch.incoming
            change.outgoing = change.outgoing or ch.outgoing
            change.role = change.role or ch.role
        if not change.incoming and not change.outgoing:
            return None
        raw = self.store.get_person(symbol, change.incoming) if change.incoming else None
        if raw:
            p = Person.model_validate_json(raw)
            p.outgoing = p.outgoing or change.outgoing
            return p.model_dump()
        return {"name": change.incoming, "role": change.role, "company": name, "symbol": symbol,
                "outgoing": change.outgoing, "brief": None, "lines": [], "coverage": [], "method": "pending"}

    def refresh_people(self, days: int = 7, force: bool = False) -> RefreshReport:
        """Background for incoming executives named in management-change news or filings of the last `days` days."""
        rep = RefreshReport()
        now = self.clock()
        start = now - timedelta(days=days)
        texts: dict[str, list[str]] = {}
        for n in self.store.news_between(start, now):
            if self.portfolio.role_of(n.symbol) in ("holding", "research") and classify_headline(n.headline).category == "management_change":
                texts.setdefault(n.symbol, []).append(n.headline)
        filings: dict[str, list] = {}
        for a in self.store.announcements_between(start, now):
            if a.symbol and classify(a).category == "management_change":
                texts.setdefault(a.symbol, []).append(f"{a.subject}. {a.detail or ''}")
                filings.setdefault(a.symbol, []).append(a)
        for sym, ts in texts.items():
            c = self.portfolio.companies.get(sym)
            company = c.name if c else sym
            change = Change()
            for t in ts:
                ch = parse_change(t, company)
                change.incoming = change.incoming or ch.incoming
                change.outgoing = change.outgoing or ch.outgoing
                change.role = change.role or ch.role
            if not change.incoming:
                continue
            key = f"people:{sym}:{change.incoming}"
            if not force and self.store.is_fresh("people", key, 24 * 60, now):
                rep.skipped_fresh.append(key)
                continue
            p = Person(name=change.incoming, role=change.role, company=company, symbol=sym, outgoing=change.outgoing)
            surname = change.incoming.split()[-1]
            # 1) the company's own filing ("Brief profile")
            for a in filings.get(sym, []):
                if a.source_url and a.source_url.lower().endswith(".pdf"):
                    try:
                        prof = brief_profile_from_pdf(self.http_get_bytes(a.source_url))
                    except Exception:  # noqa: BLE001 - a PDF failure only removes this source
                        prof = None
                    if prof:
                        p.lines.append(BioLine(text=prof[:600], source=f"{a.exchange} filing", url=a.source_url))
                        p.method = "filing"
                        break
            # 2) web search (optional free key)
            try:
                for r in tavily_search(f'"{change.incoming}" {company.split()[0]} {change.role or ""} background career'):
                    for sent in sentences_about(r["content"], change.incoming, limit=2):
                        if len(p.lines) < 5:
                            p.lines.append(BioLine(text=sent, source=_site(r["url"]), url=r["url"]))
                if p.lines and p.method == "headlines":
                    p.method = "search"
            except Exception as e:  # noqa: BLE001
                rep.failed[f"tavily:{sym}"] = str(e)[:80]
            # 3) Wikipedia, only when it is clearly the same person
            if len(p.lines) < 2 and self.news is not None:
                try:
                    r = self.news.http.get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                                           + change.incoming.replace(" ", "_"))
                    ext = wikipedia_match(r.json(), change.incoming, company)
                    if ext:
                        p.lines.append(BioLine(text=ext[:500], source="Wikipedia",
                                               url=r.json().get("content_urls", {}).get("desktop", {}).get("page")))
                        p.method = "wikipedia" if p.method == "headlines" else p.method
                except Exception:  # noqa: BLE001 - not found / unreachable
                    pass
            # 4) coverage: headlines about the person (always)
            seen = set()
            for n in self.store.news_between(start, now):
                if surname in n.headline and n.headline not in seen:
                    seen.add(n.headline)
                    p.coverage.append(BioLine(text=n.headline, source=n.publisher, url=n.url))
            if self.news is not None:
                try:
                    for n in self.news.search_person(change.incoming, company)[:6]:
                        if n.headline not in seen:
                            seen.add(n.headline)
                            p.coverage.append(BioLine(text=n.headline, source=n.publisher, url=n.url))
                except Exception:  # noqa: BLE001
                    pass
            p.coverage = p.coverage[:8]
            p.brief = write_brief(p, self.llm if self.llm and self.llm.available else None)
            if p.brief:
                p.method += "+llm"
            self.store.put_person(sym, change.incoming, p.model_dump_json())
            self.store.log_fetch("people", key, True, items=len(p.lines) + len(p.coverage), at=now)
            rep.fetched.append(key)
        return rep

    def http_get_bytes(self, url: str) -> bytes:
        return self.nse_rss.http.get(url).content if self.nse_rss is not None else b""

    # ------------------------------------------------------------ status and disclosures
    def source_status(self) -> list[SourceStatus]:
        cfg = self.s.sources["announcements"]["sources"]
        out = []
        for name, enabled, note in (
            ("prices", True, f"{self.prices.name}, end-of-day"),
            ("nse_rss", self.nse_rss is not None, cfg["nse_rss"].get("note")),
            ("nse_json", self.nse_json is not None, cfg["nse_json"].get("note")),
            ("bse_rss", self.bse_rss is not None, cfg["bse_rss"].get("note") or "Disabled until the feed URL is verified."),
            ("bse_api", self.bse_api is not None, (cfg.get("bse_api") or {}).get("note")),
            ("news", self.news is not None, "Headlines from Google News RSS and publisher RSS feeds (media, not filings)."),
            ("screener", self.screener is not None, "Company fundamentals and results tables from screener.in."),
        ):
            rows = self.store.source_rows(name)
            if not enabled:
                status = "disabled"
            elif not rows:
                status = "degraded"
                note = (note or "") + " Not fetched yet."
            else:
                oks = sum(r["ok"] for r in rows)
                status = "fixture" if self.fixture and oks else ("ok" if oks == len(rows) else "degraded" if oks else "failed")
            err = next((r["error"] for r in rows if not r["ok"]), None)
            out.append(SourceStatus(name=name, enabled=enabled, status=status, last_success_at=self.store.last_success(name),
                                    last_error=err, items=sum(r["items"] or 0 for r in rows), note=note))
        return out

    def disclosures(self, signals: list[MarketSignal]) -> list[str]:
        d: list[str] = []
        if self.fixture:
            d.append("Fixture mode: synthetic companies, prices and filings for testing and demos. Nothing here is real.")
        if self.prices.name == "yfinance":
            d.append("Prices are end-of-day from Yahoo Finance via yfinance (unofficial); they may be delayed or "
                     "revised and are not real-time.")
        d.append("Exchange holidays are not yet applied: on a market holiday, prices may be flagged stale.")
        by = {}
        for s in signals:
            by.setdefault(s.availability, []).append(s.symbol)
        labels = {Availability.STALE: "Stale prices", Availability.NO_DATA: "No price data",
                  Availability.PROVIDER_ERROR: "Price provider failed", Availability.INSUFFICIENT_HISTORY:
                  "Not enough history for volume comparison"}
        for k, lab in labels.items():
            if by.get(k):
                d.append(f"{lab}: {', '.join(sorted(by[k]))}.")
        for st in self.source_status():
            if st.name != "prices" and st.enabled and st.status in ("failed", "degraded"):
                when = f" Last success {st.last_success_at:%d %b %H:%M} UTC." if st.last_success_at else " No successful fetch yet."
                d.append(f"Announcements source {st.name} is {st.status}"
                         f"{': ' + st.last_error if st.last_error else ''}.{when}")
        if self.news is not None:
            d.append("'In the news' shows media headlines from trusted publishers via RSS. They are reports, not "
                     "company filings; open the link to read the article.")
        if self.nse_rss is not None:
            if self.nse_json is None:
                d.append("Announcements come from the NSE RSS feed, which covers roughly the last hour. FINN only knows "
                         "filings it saw while polling; there is no backfill source for earlier ones.")
            else:
                d.append("The NSE RSS feed covers roughly the last hour; filings from before FINN started polling "
                         "appear only if the per-symbol backfill succeeded.")
        return d


def _plain_price_error(err: str) -> str:
    kind = err.split(":")[0]
    return {
        "no_data": "No price data: the symbol may be unknown, suspended or delisted on this provider.",
        "unsupported": "This symbol is not in a supported NSE/BSE format.",
        "error": "The price provider failed (timeout, network or rate limit); no cached prices are available.",
    }.get(kind, f"Prices unavailable ({err}).")


def _raise_or(r):
    if isinstance(r, Exception):
        raise r
    return r


def _subject_key(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def _collapse_cross_exchange(items: list[Announcement], aliases: Optional[dict] = None) -> list[Announcement]:
    """The same filing on NSE and BSE becomes one item (NSE kept). Key: symbol + subject + filing date."""
    seen: dict[tuple, Announcement] = {}
    for a in sorted(items, key=lambda x: (x.exchange != "NSE", x.filed_at)):
        k = (a.symbol, _subject_key(a.subject), a.filed_at.astimezone(IST).date()) if a.symbol else ("uid", a.uid)
        seen.setdefault(k, a)
    # Exchanges word the same filing differently ("Outcome of Board Meeting" vs "... Financial Results ..."):
    # same company, same type, filed within 15 minutes on the other exchange -> one item.
    kept: list[Announcement] = []
    for a in seen.values():
        if a.symbol:
            cat = classify(a).category
            dup = next((b for b in kept if b.symbol == a.symbol and b.exchange != a.exchange
                        and abs((b.filed_at - a.filed_at).total_seconds()) <= 900 and classify(b).category == cat), None)
            if dup is not None:
                if aliases is not None:
                    aliases.setdefault(dup.uid, []).append(a)
                continue
        kept.append(a)
    return kept


def session_date(now: datetime) -> date:
    return expected_session(now)


def _site(url: str) -> str:
    from urllib.parse import urlparse
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h

"""Builds a Pipeline for live or fixture mode. Fixture mode never touches the network: its HTTP client is
served from synthetic files through httpx.MockTransport, so the real parsers and retry code are exercised."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .config import BACKEND_DIR, Settings, load_portfolio, load_settings
from .http import HttpClient, HttpPolicy
from .pipeline import Pipeline
from .providers.announcements import BseApiSource, BseRssSource, NseJsonSource, NseRssSource
from .providers.news import NewsSource
from .providers.prices import FixturePriceProvider, YFinanceProvider
from .providers.screener import ScreenerSource
from .store import Store

IST = ZoneInfo("Asia/Kolkata")
FIXTURES = BACKEND_DIR / "tests" / "fixtures"
FIXTURE_NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)
FIXTURE_URLS = {
    "rss": "https://fixtures.finn.invalid/rss/Online_announcements.xml",
    "home": "https://fixtures.finn.invalid/",
    "json": "https://fixtures.finn.invalid/api/corporate-announcements?index=equities&symbol={symbol}",
    "bse": "https://fixtures.finn.invalid/bse/rss.xml",
    "bse_api": "https://fixtures.finn.invalid/bse/api?code={code}&from={start}&to={end}",
    "bse_att": "https://fixtures.finn.invalid/bse/att/{name}",
}


def fixture_transport(fixtures: Path = FIXTURES) -> httpx.MockTransport:
    nse_json = json.loads((fixtures / "nse_json.json").read_text(encoding="utf-8"))

    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if u.endswith("Online_announcements.xml"):
            return httpx.Response(200, text=(fixtures / "nse_rss.xml").read_text(encoding="utf-8"))
        if "/news/rss/search" in u:
            q = req.url.params.get("q", "")
            name = "news_google_cables.xml" if "Fixture Cables" in q else "news_google_pharma.xml" if "Fixture Pharma" in q else None
            return httpx.Response(200, text=(fixtures / name).read_text(encoding="utf-8") if name else
                                  '<rss version="2.0"><channel><title>empty</title></channel></rss>')
        if "/news/feed.xml" in u:
            return httpx.Response(200, text=(fixtures / "news_publisher.xml").read_text(encoding="utf-8"))
        if "/screener/company/" in u:
            sym = u.split("/screener/company/")[1].split("/")[0]
            f = fixtures / f"screener_{sym}.html"
            if f.exists() and "consolidated" in u:
                return httpx.Response(200, text=f.read_text(encoding="utf-8"))
            return httpx.Response(404)
        if "/bse/api" in u:
            code = req.url.params.get("code", "")
            data = json.loads((fixtures / "bse_api.json").read_text(encoding="utf-8"))
            return httpx.Response(200, json={"Table": data.get(code, []), "Table1": [{"ROWCNT": len(data.get(code, []))}]})
        if "/bse/att/" in u:
            from .research.fixture import fixture_doc_bytes
            try:
                return httpx.Response(200, content=fixture_doc_bytes(u))
            except FileNotFoundError:
                return httpx.Response(404)
        if "/bse/rss.xml" in u:
            return httpx.Response(200, text=(fixtures / "bse_rss.xml").read_text(encoding="utf-8"))
        if "/api/corporate-announcements" in u:
            sym = req.url.params.get("symbol", "")
            return httpx.Response(200, json=nse_json.get(sym, []))
        if u.rstrip("/") == FIXTURE_URLS["home"].rstrip("/"):
            return httpx.Response(200, text="<html>fixture home</html>", headers={"set-cookie": "fx=1; Path=/"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def attach_research(pipe: Pipeline, fixture: bool) -> Pipeline:
    """Pull research engine (any NSE ticker): Screener links -> company documents -> cited dossier."""
    from .research.documents import DocumentSource
    from .research.engine import ResearchEngine

    def get_snapshot(sym: str):
        if pipe.screener is not None:
            pipe.refresh_companies([sym])
        return pipe.snapshot(sym)

    def name_of(sym: str):
        c = pipe.portfolio.companies.get(sym)
        return c.name if c else None

    def is_lender(sym: str, snap) -> bool:
        c = pipe.portfolio.companies.get(sym)
        return bool((c and c.is_lender) or (snap.quarters and "financing profit" in snap.quarters.rows))

    if fixture:
        from .research.fixture import FixtureLLM, fixture_doc_bytes
        docs, llm = DocumentSource(pipe.store, fetch_bytes=fixture_doc_bytes, clock=pipe.clock), FixtureLLM()
    else:
        docs, llm = DocumentSource(pipe.store, clock=pipe.clock), pipe.llm
    pipe.research = ResearchEngine(pipe.store, docs, llm, get_snapshot, name_of, is_lender)
    from .filings import FilingReader
    pipe.filings = FilingReader(docs, llm, pipe.store)
    return pipe


def build_pipeline(mode: str = "live", db_path: str | None = None, settings: Settings | None = None) -> Pipeline:
    return attach_research(_build_pipeline(mode, db_path, settings), mode == "fixture")


def _build_pipeline(mode: str = "live", db_path: str | None = None, settings: Settings | None = None) -> Pipeline:
    from .config import load_dotenv
    from .llm import LLM

    if mode != "fixture":
        load_dotenv()
    settings = settings or load_settings()
    if mode == "fixture":
        portfolio = load_portfolio(FIXTURES)
        store = Store(db_path or ":memory:")
        policy = HttpPolicy(min_delay_seconds=0, max_retries=0)
        http = HttpClient(policy, transport=fixture_transport(), sleep=lambda s: None)
        clock = lambda: FIXTURE_NOW  # noqa: E731
        news_cfg = {**settings.sources["news"], "google_news_url": "https://fixtures.finn.invalid/news/rss/search?q={query}",
                    "trusted_domains": ["fixturewire.invalid", "fixturetimes.invalid"],
                    "publisher_feeds": [{"name": "fx_feed", "publisher": "Fixture Times",
                                         "url": "https://fixtures.finn.invalid/news/feed.xml"}]}
        settings.sources = {**settings.sources, "news": news_cfg}
        return Pipeline(settings, portfolio, store, FixturePriceProvider(FIXTURE_NOW.date()),
                        news=NewsSource(http, portfolio, news_cfg, clock, fixture=True),
                        screener=ScreenerSource(http, "https://fixtures.finn.invalid/screener/company/{symbol}/{basis}",
                                                clock, fixture=True),
                        nse_rss=NseRssSource(http, portfolio, FIXTURE_URLS["rss"], clock, fixture=True),
                        nse_json=NseJsonSource(http, FIXTURE_URLS["home"], FIXTURE_URLS["json"], clock, fixture=True),
                        bse_rss=BseRssSource(http, portfolio, FIXTURE_URLS["bse"], clock, fixture=True),
                        bse_api=BseApiSource(http, FIXTURE_URLS["bse_api"], clock, fixture=True,
                                             attach_template=FIXTURE_URLS["bse_att"]),
                        clock=clock, fixture=True)

    from .config import REPO_DIR

    portfolio = load_portfolio(user_path=REPO_DIR / "data" / "portfolio.json")
    store = Store(db_path or settings.db_path)
    http = HttpClient(HttpPolicy.from_config(settings.sources["http"]))
    clock = lambda: datetime.now(IST)  # noqa: E731
    src = settings.sources["announcements"]["sources"]
    nse_rss = NseRssSource(http, portfolio, src["nse_rss"]["url"], clock) if src["nse_rss"]["enabled"] else None
    nse_json = (NseJsonSource(http, src["nse_json"]["home_url"], src["nse_json"]["url"], clock)
                if src["nse_json"]["enabled"] else None)
    bse_rss = (BseRssSource(http, portfolio, src["bse_rss"]["url"], clock)
               if src["bse_rss"]["enabled"] and src["bse_rss"].get("url") else None)
    pcfg = settings.sources["http"]
    prices = YFinanceProvider(timeout=pcfg["timeout_seconds"], retries=min(1, pcfg["max_retries"]))
    news = NewsSource(http, portfolio, settings.sources["news"], clock) if settings.sources.get("news", {}).get("enabled") else None
    scr = settings.sources.get("screener", {})
    screener = ScreenerSource(http, scr["url_template"], clock) if scr.get("enabled") else None
    bse_api = (BseApiSource(http, src["bse_api"]["url"], clock)
               if src.get("bse_api", {}).get("enabled") and src["bse_api"].get("url") else None)
    return Pipeline(settings, portfolio, store, prices, nse_rss=nse_rss, nse_json=nse_json, bse_rss=bse_rss,
                    clock=clock, fixture=False, news=news, screener=screener, llm=LLM(), bse_api=bse_api)

"""Company news headlines from RSS feeds (D-51). Plumbing only: no article pages are fetched.

  google_news  Google News RSS search, one query per company, restricted to trusted publishers.
               Items carry <source url="https://www.moneycontrol.com">Moneycontrol</source>.
  publisher    Publisher RSS feeds (e.g. Economic Times company news, Moneycontrol business news);
               items are matched to companies by `news_terms` in the headline.

Kept: headline, publisher, time, link. Not kept: article text or RSS descriptions (copyright; D-31).
A headline must name the company (whole-word match on news_terms) to be attached to it.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import quote_plus, urlparse

from ..config import Portfolio
from ..http import HttpClient
from ..models import Company, NewsItem, Provenance, SourceClass
from .announcements import SourceSchemaError, parse_time


def terms_for(c: Company) -> list[str]:
    if c.news_terms:
        return c.news_terms
    base = re.sub(r"\b(ltd|limited|the)\b\.?", "", c.name, flags=re.I).strip(" .,")
    return [base]


def about(headline: str, c: Company) -> bool:
    """True if the headline names the company and none of its exclusions (e.g. 'ITC Hotels' for ITC)."""
    return mentions(headline, terms_for(c)) and not mentions(headline, c.news_exclude)


def mentions(headline: str, terms: Iterable[str]) -> bool:
    for t in terms:
        exact = t.startswith("=") or len(t) <= 4        # "=Eternal", ITC, RIL, L&T: case must match exactly
        t = t.lstrip("=")
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", headline, flags=0 if exact else re.I):
            return True
    return False


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _trusted(domain: str | None, trusted: list[str]) -> bool:
    return bool(domain) and any(domain == t or domain.endswith("." + t) for t in trusted)


def _clean_title(title: str, publisher: str | None) -> str:
    t = " ".join((title or "").split())
    if publisher and t.endswith(f" - {publisher}"):
        t = t[: -len(publisher) - 3]
    return t.strip()


NOISE = re.compile(
    r"share price(,| today| live)|stock price (live|today)|price today|stocks? to (watch|buy)|market wrap|top gainers|"
    r"top losers|gainers and losers|buy,? sell or hold|top \d+ stocks|stocks in news|trade setup|technical (view|picks)|"
    r"\bnifty\b.{0,30}\b(climbs|falls|slips|ends|opens|ends)|sensex.{0,20}(points|ends|opens)|earnings central|"
    r"dividend champions|stocks that|stock picks|market live|live updates|q[1-4] preview|results preview|"
    r"target of rs|target price|(?:^|\s)(buy|sell|neutral|hold|accumulate|reduce)\s+[a-z][a-z .&]+;\s+target|"
    r"share price highlights|stock price history|52-week (highs?|lows?)|retains '?(buy|neutral|sell|hold)|"
    r"bullish on|ipos? listing", re.I)


def is_noise(headline: str) -> bool:
    """Price pages, stock tips, market wraps and multi-company round-ups are not news about the company."""
    if NOISE.search(headline or ""):
        return True
    return headline.count(",") >= 4 or (headline.count(",") >= 3 and ":" in headline)   # multi-company round-ups


PUBLISHER_RANK = ["Reuters", "The Economic Times", "Moneycontrol", "Moneycontrol.com", "Business Standard", "Livemint", "Mint",
                  "BusinessLine", "The Hindu BusinessLine", "CNBC TV18", "CNBC-TV18", "NDTV Profit", "The Financial Express",
                  "The Hindu"]


def publisher_rank(p: str) -> int:
    return PUBLISHER_RANK.index(p) if p in PUBLISHER_RANK else len(PUBLISHER_RANK)


def news_uid(symbol: str, headline: str) -> str:
    """One story reported by several outlets with the same headline collapses to one item."""
    norm = " ".join(re.sub(r"[^a-z0-9 ]", " ", headline.lower()).split())
    return f"news:{symbol}:{hashlib.sha1(norm.encode()).hexdigest()[:16]}"


def _root(xml_text: str):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SourceSchemaError(f"RSS is not valid XML: {e}") from e
    if root.find("channel") is None:
        raise SourceSchemaError("not an RSS document")
    return root


def parse_google_news(xml_text: str, company: Company, trusted: list[str], retrieved_at: datetime, url: str,
                      fixture: bool = False) -> list[NewsItem]:
    out = []
    for it in _root(xml_text).findall("./channel/item"):
        src = it.find("source")
        publisher = (src.text or "").strip() if src is not None else ""
        pub_domain = _domain(src.get("url")) if src is not None else None
        if not _trusted(pub_domain, trusted):
            continue
        headline = _clean_title(it.findtext("title") or "", publisher)
        link = (it.findtext("link") or "").strip()
        if not headline or not link or not about(headline, company):
            continue
        try:
            when = parse_time(it.findtext("pubDate") or "")
        except ValueError:
            continue
        out.append(NewsItem(uid=news_uid(company.symbol, headline), symbol=company.symbol, company_name=company.name,
                            headline=headline, publisher=publisher or pub_domain, publisher_domain=pub_domain, url=link,
                            published_at=when, feed="google_news",
                            provenance=Provenance(source_class=SourceClass.EXTERNAL_WEB, source_name="google_news",
                                                  url=url, retrieved_at=retrieved_at, data_date=when.date(),
                                                  fixture=fixture, locator=publisher)))
    return out


def parse_publisher_feed(xml_text: str, feed_name: str, publisher: str, portfolio: Portfolio, retrieved_at: datetime,
                         url: str, fixture: bool = False) -> list[NewsItem]:
    out = []
    companies = portfolio.holdings + portfolio.research
    for it in _root(xml_text).findall("./channel/item"):
        headline = " ".join((it.findtext("title") or "").split())
        link = (it.findtext("link") or "").strip()
        if not headline or not link:
            continue
        try:
            when = parse_time(it.findtext("pubDate") or "")
        except ValueError:
            continue
        for c in companies:
            if about(headline, c):
                out.append(NewsItem(uid=news_uid(c.symbol, headline), symbol=c.symbol, company_name=c.name,
                                    headline=headline, publisher=publisher, publisher_domain=_domain(link), url=link,
                                    published_at=when, feed=feed_name,
                                    provenance=Provenance(source_class=SourceClass.EXTERNAL_WEB, source_name=feed_name,
                                                          url=url, retrieved_at=retrieved_at, data_date=when.date(),
                                                          fixture=fixture, locator=publisher)))
    return out


class NewsSource:
    name = "news"

    def __init__(self, http: HttpClient, portfolio: Portfolio, cfg: dict, clock: Callable[[], datetime],
                 fixture: bool = False):
        self.http, self.portfolio, self.cfg, self.clock, self.fixture = http, portfolio, cfg, clock, fixture

    def google_url(self, c: Company) -> str:
        q = " OR ".join(f'"{t.lstrip("=")}"' for t in terms_for(c)) + f" when:{self.cfg.get('lookback_days', 7)}d"
        return self.cfg["google_news_url"].format(query=quote_plus(q))

    def fetch_company(self, c: Company) -> list[NewsItem]:
        url = self.google_url(c)
        r = self.http.get(url)
        return parse_google_news(r.text, c, self.cfg["trusted_domains"], self.clock(), url, self.fixture)

    def search_person(self, person: str, company: str) -> list[NewsItem]:
        """Headlines about an executive (trusted outlets), for the management-change background."""
        q = quote_plus(f'"{person}" when:30d')
        url = self.cfg["google_news_url"].format(query=q)
        fake = Company(symbol="_", name=company, news_terms=[person])
        return parse_google_news(self.http.get(url).text, fake, self.cfg["trusted_domains"], self.clock(), url, self.fixture)

    def fetch_publisher(self, feed: dict) -> list[NewsItem]:
        r = self.http.get(feed["url"])
        return parse_publisher_feed(r.text, feed["name"], feed["publisher"], self.portfolio, self.clock(), feed["url"],
                                    self.fixture)

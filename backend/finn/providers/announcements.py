"""Corporate-announcement sources (D-33, D-38) and their parsers.

  nse_rss   Official NSE RSS feed (Online_announcements.xml). Rolling ~1 h window; company NAME only.
  nse_json  NSE website JSON used by its own announcements page. UNDOCUMENTED: may change or vanish.
            Used per symbol for backfill, schema-checked, and treated as optional.
  bse_rss   BSE RSS (official feed list). Disabled until its URL is verified (Spike S1).
  bse_api   BSE website JSON used by bseindia.com's own announcements page (owner-approved, D-65). UNDOCUMENTED.
            Per company (BSE scrip code from the Screener page), whole window, with the filed PDF.

Parsers are pure functions over text/JSON so they can be tested against synthetic fixtures. No source
is assumed stable: any parse or schema problem becomes a SourceStatus error, never a crash.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..config import Portfolio
from ..http import FetchError, HttpClient
from ..models import Announcement, Attachment, Provenance, SourceClass

IST = ZoneInfo("Asia/Kolkata")


class SourceSchemaError(Exception):
    """The payload no longer has the shape we parse. The source is marked failed, not guessed at."""


# ---------------------------------------------------------------- helpers
def parse_time(raw: str) -> datetime:
    """Parse exchange timestamps. Naive times are IST (exchanges publish IST)."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    try:
        dt = parsedate_to_datetime(s)              # RFC 822, e.g. "Wed, 29 Oct 2026 19:14:00 +0530"
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M", "%d %b %Y %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(f"unrecognised timestamp {raw!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def _norm_subject(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def dedup_key(exchange: str, *, attachment_url: Optional[str], exchange_id: Optional[str],
              symbol_or_name: str, filed_at: datetime, subject: str) -> str:
    """Stable identifier for one filing (documented in DECISIONS D-43).

    1. exchange + attachment file name: the same PDF link appears in the RSS feed and the JSON endpoint.
    2. exchange + exchange id (NSE seq_id) when there is no attachment.
    3. sha1(exchange | symbol-or-name | filed minute | normalised subject) as a last resort.
    """
    if attachment_url:
        name = urlparse(attachment_url).path.rsplit("/", 1)[-1]
        if name:
            return f"{exchange}:att:{name}"
    if exchange_id:
        return f"{exchange}:id:{exchange_id}"
    basis = f"{exchange}|{symbol_or_name.upper()}|{filed_at.astimezone(IST):%Y-%m-%d %H:%M}|{_norm_subject(subject)}"
    return f"{exchange}:h:{hashlib.sha1(basis.encode()).hexdigest()[:20]}"


def _kind(url: str) -> str:
    ext = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
    return ext if ext in ("pdf", "xml", "zip", "html") else "other"


# ---------------------------------------------------------------- NSE RSS
def parse_nse_rss(xml_text: str, portfolio: Portfolio, retrieved_at: datetime, url: str,
                  fixture: bool = False) -> list[Announcement]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SourceSchemaError(f"RSS is not valid XML: {e}") from e
    items = root.findall("./channel/item")
    if root.tag != "rss" or root.find("channel") is None:
        raise SourceSchemaError("not an RSS 2.0 document")
    out: list[Announcement] = []
    for it in items:
        name = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip() or None
        desc = (it.findtext("description") or "").strip()
        pub = it.findtext("pubDate") or ""
        if not name or not pub:
            continue
        try:
            filed = parse_time(pub)
        except ValueError:
            continue
        detail, subject = desc, desc
        if "|SUBJECT:" in desc:
            detail, subject = (p.strip() for p in desc.split("|SUBJECT:", 1))
        subject = subject or detail or "(no subject)"
        company = portfolio.match_name(name)
        symbol = company.symbol if company else None
        out.append(Announcement(
            uid=dedup_key("NSE", attachment_url=link, exchange_id=None, symbol_or_name=symbol or name,
                          filed_at=filed, subject=subject),
            source="nse_rss", exchange="NSE", symbol=symbol, company_name=name, subject=subject,
            detail=detail if detail != subject else None, filed_at=filed, source_url=link,
            attachments=[Attachment(url=link, kind=_kind(link))] if link else [],
            provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="nse_rss", url=url,
                                  retrieved_at=retrieved_at, data_date=filed.date(), fixture=fixture,
                                  locator="RSS item"),
        ))
    return out


# ---------------------------------------------------------------- NSE JSON (undocumented)
NSE_JSON_REQUIRED = {"symbol", "desc", "seq_id"}


def parse_nse_json(payload, symbol_hint: str, retrieved_at: datetime, url: str,
                   fixture: bool = False) -> list[Announcement]:
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise SourceSchemaError("expected a JSON array of announcements")
    out: list[Announcement] = []
    for r in rows:
        if not isinstance(r, dict) or not NSE_JSON_REQUIRED <= set(r):
            raise SourceSchemaError(f"announcement row missing fields {sorted(NSE_JSON_REQUIRED - set(r or {}))}")
        ts = r.get("exchdisstime") or r.get("an_dt") or r.get("sort_date")
        try:
            filed = parse_time(ts)
        except ValueError:
            continue
        att = (r.get("attchmntFile") or "").strip() or None
        subject = (r.get("desc") or "").strip() or "(no subject)"
        sym = (r.get("symbol") or symbol_hint).strip().upper()
        out.append(Announcement(
            uid=dedup_key("NSE", attachment_url=att, exchange_id=str(r["seq_id"]), symbol_or_name=sym,
                          filed_at=filed, subject=subject),
            source="nse_json", exchange="NSE", symbol=sym, company_name=(r.get("sm_name") or sym).strip(),
            subject=subject, detail=(r.get("attchmntText") or "").strip() or None, filed_at=filed, source_url=att,
            attachments=[Attachment(url=att, size_text=r.get("fileSize") or r.get("attFileSize"), kind=_kind(att))]
            if att else [],
            source_category=r.get("smIndustry"), exchange_id=str(r["seq_id"]),
            provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="nse_json", url=url,
                                  retrieved_at=retrieved_at, data_date=filed.date(), fixture=fixture,
                                  locator=f"seq_id {r['seq_id']}"),
        ))
    return out


# ---------------------------------------------------------------- BSE RSS (generic)
_BSE_CODE = re.compile(r"\b(\d{6})\b")


def parse_bse_rss(xml_text: str, portfolio: Portfolio, retrieved_at: datetime, url: str,
                  fixture: bool = False) -> list[Announcement]:
    """Generic RSS parse. The exact BSE item layout is unverified; a six-digit scrip code in the title
    or description maps the item to a company when it matches the portfolio."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SourceSchemaError(f"RSS is not valid XML: {e}") from e
    if root.find("channel") is None:
        raise SourceSchemaError("not an RSS document")
    out: list[Announcement] = []
    for it in root.findall("./channel/item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip() or None
        desc = (it.findtext("description") or "").strip()
        try:
            filed = parse_time(it.findtext("pubDate") or "")
        except ValueError:
            continue
        m = _BSE_CODE.search(title) or _BSE_CODE.search(desc)
        company = portfolio.by_bse_code(m.group(1)) if m else None
        out.append(Announcement(
            uid=dedup_key("BSE", attachment_url=link, exchange_id=None,
                          symbol_or_name=(company.symbol if company else title), filed_at=filed, subject=title),
            source="bse_rss", exchange="BSE", symbol=company.symbol if company else None,
            company_name=company.name if company else title.split(" - ")[0], subject=title, detail=desc or None,
            filed_at=filed, source_url=link, attachments=[Attachment(url=link, kind=_kind(link))] if link else [],
            provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="bse_rss", url=url,
                                  retrieved_at=retrieved_at, data_date=filed.date(), fixture=fixture),
        ))
    return out


# ---------------------------------------------------------------- fetchers
class AnnouncementSource:
    name: str
    enabled: bool = True

    def fetch(self, symbols: Iterable[str]) -> list[Announcement]:  # pragma: no cover - interface
        raise NotImplementedError


class NseRssSource(AnnouncementSource):
    name = "nse_rss"

    def __init__(self, http: HttpClient, portfolio: Portfolio, url: str, clock: Callable[[], datetime],
                 fixture: bool = False):
        self.http, self.portfolio, self.url, self.clock, self.fixture = http, portfolio, url, clock, fixture

    def fetch(self, symbols: Iterable[str] = ()) -> list[Announcement]:
        r = self.http.get(self.url)
        return parse_nse_rss(r.text, self.portfolio, self.clock(), self.url, self.fixture)


class NseJsonSource(AnnouncementSource):
    name = "nse_json"

    def __init__(self, http: HttpClient, home_url: str, url_template: str, clock: Callable[[], datetime],
                 fixture: bool = False):
        self.http, self.home_url, self.url_template, self.clock, self.fixture = http, home_url, url_template, clock, fixture
        self._primed = False

    def _prime(self) -> None:
        # The endpoint expects the cookies a browser receives on the public home page. FINN loads that
        # page once, like a browser. It never signs in and never handles a CAPTCHA (D-38 guardrails).
        if not self._primed:
            self.http.get(self.home_url)
            self._primed = True

    def fetch_symbol(self, symbol: str) -> list[Announcement]:
        self._prime()
        url = self.url_template.format(symbol=symbol)
        r = self.http.get(url, headers={"Accept": "application/json", "Referer": self.home_url})
        try:
            payload = r.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise SourceSchemaError("response is not JSON (the endpoint may have changed or been blocked)") from e
        return parse_nse_json(payload, symbol, self.clock(), url, self.fixture)


# ---------------------------------------------------------------- BSE website JSON (per company)
BSE_ATTACH = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}"
BSE_REQUIRED = {"NEWSID", "SCRIP_CD", "NEWSSUB", "NEWS_DT"}


def parse_bse_api(payload, symbol: str, retrieved_at: datetime, url: str, fixture: bool = False,
                  attach_template: str = BSE_ATTACH) -> list[Announcement]:
    rows = payload.get("Table") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise SourceSchemaError("expected {'Table': [...]} from BSE")
    out: list[Announcement] = []
    for r in rows:
        if not isinstance(r, dict) or not BSE_REQUIRED <= set(r):
            raise SourceSchemaError(f"BSE row missing fields {sorted(BSE_REQUIRED - set(r or {}))}")
        try:
            filed = parse_time(str(r.get("DissemDT") or r.get("NEWS_DT")).split(".")[0])
        except ValueError:
            continue
        name = (r.get("ATTACHMENTNAME") or "").strip()
        att = attach_template.format(name=name) if name else None
        subject = " ".join(str(r.get("NEWSSUB") or r.get("HEADLINE") or "(no subject)").split())
        subject = re.sub(r"^.{2,120}? - \d{6} - ", "", subject) or subject   # BSE prefixes "Company - code - "
        headline = " ".join(str(r.get("HEADLINE") or "").split())
        cat = " / ".join(x for x in (r.get("CATEGORYNAME"), r.get("SUBCATNAME")) if x and str(x).strip() not in ("", "-"))
        size = r.get("Fld_Attachsize")
        size_text = f"{int(size) // 1024} KB" if isinstance(size, (int, float)) and size else None
        out.append(Announcement(
            uid=dedup_key("BSE", attachment_url=att, exchange_id=str(r["NEWSID"]), symbol_or_name=symbol,
                          filed_at=filed, subject=subject),
            source="bse_api", exchange="BSE", symbol=symbol, company_name=(r.get("SLONGNAME") or symbol).strip(),
            subject=subject, detail=headline if headline and headline.lower() != subject.lower() else None,
            filed_at=filed, source_url=att,
            attachments=[Attachment(url=att, size_text=size_text, kind=_kind(att))] if att else [],
            source_category=cat or None, exchange_id=str(r["NEWSID"]),
            provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="bse_api", url=url,
                                  retrieved_at=retrieved_at, data_date=filed.date(), fixture=fixture,
                                  locator=f"BSE news id {r['NEWSID']}"),
        ))
    return out


class BseApiSource(AnnouncementSource):
    """bseindia.com's announcements JSON, per company. Sends an honest User-Agent and the site's own Referer (the
    JSON is served to bseindia.com pages); no cookies, no login, no retry around a refusal (D-38, D-65)."""
    name = "bse_api"

    def __init__(self, http: HttpClient, url_template: str, clock: Callable[[], datetime], days: int = 8,
                 fixture: bool = False, attach_template: str = BSE_ATTACH):
        self.http, self.url_template, self.clock, self.days, self.fixture = http, url_template, clock, days, fixture
        self.attach_template = attach_template

    def fetch_code(self, symbol: str, code: str) -> list[Announcement]:
        from datetime import timedelta
        now = self.clock().astimezone(IST)
        url = self.url_template.format(code=code, start=(now - timedelta(days=self.days)).strftime("%Y%m%d"),
                                       end=now.strftime("%Y%m%d"))
        r = self.http.get(url, headers={"Accept": "application/json, text/plain, */*",
                                        "Referer": "https://www.bseindia.com/"})
        try:
            payload = r.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise SourceSchemaError("BSE did not return JSON (the endpoint may have changed or refused)") from e
        return parse_bse_api(payload, symbol, self.clock(), url, self.fixture, self.attach_template)


class BseRssSource(AnnouncementSource):
    name = "bse_rss"

    def __init__(self, http: HttpClient, portfolio: Portfolio, url: str, clock: Callable[[], datetime],
                 fixture: bool = False):
        self.http, self.portfolio, self.url, self.clock, self.fixture = http, portfolio, url, clock, fixture

    def fetch(self, symbols: Iterable[str] = ()) -> list[Announcement]:
        r = self.http.get(self.url)
        return parse_bse_rss(r.text, self.portfolio, self.clock(), self.url, self.fixture)


__all__ = ["FetchError", "SourceSchemaError", "NseRssSource", "NseJsonSource", "BseRssSource", "BseApiSource", "parse_bse_api",
           "parse_nse_rss", "parse_nse_json", "parse_bse_rss", "dedup_key", "parse_time"]

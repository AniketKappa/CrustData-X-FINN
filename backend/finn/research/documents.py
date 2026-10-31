"""Primary documents for Pull research (R-19, D-31): concall transcripts, investor presentations and annual reports.

Where the links come from: the company's Screener page lists them, and they point at the documents themselves on
BSE/NSE or the company's own website. FINN reads only those PDFs. It never reads news, broker notes or Screener's
own text for narrative claims; Screener's tables supply numbers only, labelled (numbers.py).

Documents are downloaded on demand, read page by page with pypdf, and cached in the local SQLite store (never
committed). Each page keeps its number so every claim can link to "<document>, p. N".
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from ..http import FetchError, HttpClient, HttpPolicy

MAX_PDF_BYTES = 45 * 1024 * 1024
import os as _os
# Business overview, MD&A and the key statements sit in the first part of a report. Small hosts (512 MB) can lower it.
AR_MAX_PAGES = int(_os.environ.get("FINN_AR_MAX_PAGES", "180"))
OTHER_MAX_PAGES = 80
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class Doc(BaseModel):
    id: str
    kind: str                     # transcript | presentation | annual_report
    title: str                    # "Q2 FY27 call transcript (Oct 2026)"
    period: str                   # as listed: "Oct 2026", "Annual Report 2026"
    url: str
    host: str
    pages: int = 0
    pages_read: int = 0
    status: str = "pending"       # pending | ok | failed
    error: Optional[str] = None
    retrieved_at: Optional[datetime] = None


def doc_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def fiscal_label(period: str) -> str:
    """Call month -> quarter discussed: 'Oct 2026' -> 'Q2 FY27' (calls follow the quarter they discuss)."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", period.strip())
    mon = _MONTHS.get(m.group(1).lower()) if m else None
    if not mon:
        return period
    yr = int(m.group(2))
    end_mon, end_yr = {1: (12, yr - 1), 2: (12, yr - 1), 3: (12, yr - 1), 4: (3, yr), 5: (3, yr), 6: (3, yr),
                       7: (6, yr), 8: (6, yr), 9: (6, yr), 10: (9, yr), 11: (9, yr), 12: (9, yr)}[mon]
    q = {6: 1, 9: 2, 12: 3, 3: 4}[end_mon]
    fy = end_yr + 1 if end_mon != 3 else end_yr
    return f"Q{q} FY{fy % 100:02d}"


def select_docs(snap, transcripts: int = 4, reports: int = 1, presentations: int = 1) -> list[Doc]:
    """Latest N transcripts (one per call), the latest investor presentation and the latest annual report."""
    out: list[Doc] = []
    seen_periods = set()
    for c in snap.concalls:
        if len([d for d in out if d.kind == "transcript"]) >= transcripts:
            break
        if c.transcript and c.period not in seen_periods:
            seen_periods.add(c.period)
            out.append(_doc("transcript", f"{fiscal_label(c.period)} call transcript ({c.period})", c.period, c.transcript))
    for c in snap.concalls:
        if len([d for d in out if d.kind == "presentation"]) >= presentations:
            break
        if c.ppt:
            out.append(_doc("presentation", f"Investor presentation ({c.period})", c.period, c.ppt))
    for a in snap.annual_reports[:reports]:
        if re.search(r"annual report|financial year", a.title, re.I):
            out.append(_doc("annual_report", a.title, a.title, a.url))
    return out


def _doc(kind: str, title: str, period: str, url: str) -> Doc:
    return Doc(id=doc_id(url), kind=kind, title=title, period=period, url=url, host=urlparse(url).netloc)


def pdf_pages(data: bytes, max_pages: int) -> tuple[list[str], int]:
    """Text of each page (up to max_pages) and the document's total page count."""
    from pypdf import PdfReader  # imported lazily; only research needs it

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    out = []
    for i, page in enumerate(reader.pages):
        if i >= max_pages:
            break
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one unreadable page must not lose the document
            t = ""
        out.append(_clean(t))
    return out, total


def _clean(t: str) -> str:
    t = t.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


@dataclass
class Chunk:
    id: str                       # "<doc_id>:<page>:<n>"
    doc_id: str
    page: int
    text: str
    kind: str = ""
    title: str = ""
    url: str = ""
    tokens: list[str] = field(default_factory=list)


def chunk_pages(doc: Doc, pages: list[str], size: int = 1100, overlap: int = 150) -> list[Chunk]:
    out = []
    for p, text in enumerate(pages, 1):
        if len(text) < 40:
            continue
        i, n = 0, 0
        while i < len(text):
            piece = text[i:i + size]
            if i + size < len(text):                      # end on a sentence or line break where possible
                cut = max(piece.rfind(". "), piece.rfind("\n"))
                if cut > size * 0.6:
                    piece = piece[:cut + 1]
            out.append(Chunk(id=f"{doc.id}:{p}:{n}", doc_id=doc.id, page=p, text=piece.strip(), kind=doc.kind,
                             title=doc.title, url=doc.url))
            n += 1
            i += max(len(piece) - overlap, 200)
    return out


class DocumentSource:
    """Downloads and caches primary documents. Fetches respect the polite HTTP client (delay, retries, no bypass)."""

    def __init__(self, store, http: Optional[HttpClient] = None, clock: Callable[[], datetime] = datetime.now,
                 fetch_bytes: Optional[Callable[[str], bytes]] = None):
        self.store, self.clock = store, clock
        self.http = http or HttpClient(HttpPolicy(timeout_seconds=60, max_retries=1, min_delay_seconds=1.0,
                                                  user_agent="Mozilla/5.0 (compatible; FINN-research-prototype/0.2; personal, non-commercial)"))
        self._fetch = fetch_bytes or self._get

    def _get(self, url: str) -> bytes:
        try:
            r = self.http.get(url, headers={"Accept": "application/pdf,*/*"})
        except FetchError as e:
            if e.status == 404 and "/AttachLive/" in url:          # BSE moves older filings to AttachHis
                r = self.http.get(url.replace("/AttachLive/", "/AttachHis/"), headers={"Accept": "application/pdf,*/*"})
            else:
                raise
        data = r.content
        if len(data) > MAX_PDF_BYTES:
            raise FetchError(url, "too_large", f"{len(data) // (1024 * 1024)} MB")
        return data

    def load(self, doc: Doc) -> tuple[Doc, list[str]]:
        """Pages for a document, from the cache or downloaded now. Never raises: failures are recorded on the doc."""
        raw = self.store.get_doc(doc.id)
        if raw:
            cached = Doc.model_validate_json(raw)
            if cached.status == "ok":
                return cached, self.store.doc_pages(doc.id)
        try:
            data = self._fetch(doc.url)
            if not data.startswith(b"%PDF"):
                raise ValueError("not a PDF (the site returned a web page)")
            pages, total = pdf_pages(data, AR_MAX_PAGES if doc.kind == "annual_report" else OTHER_MAX_PAGES)
            if sum(len(p) for p in pages) < (120 if doc.kind == "filing" else 500):
                raise ValueError("no readable text (scanned document)")
            doc = doc.model_copy(update={"status": "ok", "pages": total, "pages_read": len(pages), "error": None,
                                         "retrieved_at": self.clock()})
            self.store.put_doc(doc.id, doc.model_dump_json(), pages)
            return doc, pages
        except FetchError as e:
            err = f"{e.kind}: {e.detail}"
        except Exception as e:  # noqa: BLE001 - pypdf and friends raise many types
            err = f"{e.__class__.__name__}: {str(e)[:160]}"
        doc = doc.model_copy(update={"status": "failed", "error": err, "retrieved_at": self.clock()})
        self.store.put_doc(doc.id, doc.model_dump_json())
        return doc, []

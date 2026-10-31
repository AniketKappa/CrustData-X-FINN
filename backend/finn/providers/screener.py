"""Company fundamentals from screener.in (D-35 option B, D-38, D-52; STANDARDIZED_TABLE).

One fetch of the public company page per TTL gives everything the Companies screen and the results card need:
key ratios, the "about" text, sector, the Quarterly / Profit & Loss / Balance Sheet / Cash Flow / Ratios tables,
and the document links (annual reports, concall transcripts, credit-rating documents). FINN keeps these parsed
values and links, not the page. Every section is optional: a missing or changed section becomes a note.

Results card:
  Revenue = "Sales" (or "Revenue" for lenders) · EBITDA = PBT + Interest + Depreciation − Other Income (n/m for
  lenders) · PBT = "Profit before tax" · PAT = "Net Profit". ₹ crore as published; QoQ/YoY computed in code.
"""
from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable, Optional

from pydantic import BaseModel, Field

from ..http import HttpClient
from ..models import Provenance, SourceClass
from .announcements import SourceSchemaError

# ------------------------------------------------------------------ tiny DOM
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "base", "embed", "param", "track"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    def text(self) -> str:
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return " ".join(" ".join(out).split())

    def own_text(self) -> str:
        return " ".join(" ".join(c for c in self.children if isinstance(c, str)).split())

    def iter(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def find_all(self, tag=None, **attrs):
        for n in self.iter():
            if tag and n.tag != tag:
                continue
            ok = True
            for k, v in attrs.items():
                k = k.rstrip("_")
                val = n.attrs.get(k) or ""
                if k == "class":
                    ok = v in val.split()
                else:
                    ok = val == v
                if not ok:
                    break
            if ok:
                yield n

    def find(self, tag=None, **attrs):
        return next(self.find_all(tag, **attrs), None)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.children.append(data)


def parse_dom(html: str) -> Node:
    b = _Builder()
    b.feed(html)
    return b.root


# ------------------------------------------------------------------ models
class Table(BaseModel):
    periods: list[str]
    rows: dict[str, list[Optional[float]]]      # normalised label -> values aligned with periods
    labels: dict[str, str] = Field(default_factory=dict)   # normalised -> label as shown


class DocLink(BaseModel):
    title: str
    url: str
    note: Optional[str] = None                  # e.g. "from bse", "5 Aug from icra"


class Concall(BaseModel):
    period: str
    transcript: Optional[str] = None
    ppt: Optional[str] = None
    recording: Optional[str] = None


class CompanySnapshot(BaseModel):
    symbol: str
    basis: str                                  # consolidated | standalone
    name: Optional[str] = None
    about: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    ratios: list[tuple[str, str]] = Field(default_factory=list)   # top ratios as shown ("Market Cap", "₹ 19,40,123 Cr.")
    quarters: Optional[Table] = None
    annual: Optional[Table] = None
    balance: Optional[Table] = None
    cashflow: Optional[Table] = None
    efficiency: Optional[Table] = None
    annual_reports: list[DocLink] = Field(default_factory=list)
    concalls: list[Concall] = Field(default_factory=list)
    credit_ratings: list[DocLink] = Field(default_factory=list)
    bse_code: Optional[str] = None              # from the page's link to the company on bseindia.com
    website: Optional[str] = None
    source_url: str
    retrieved_at: datetime
    notes: list[str] = Field(default_factory=list)
    fixture: bool = False


def _num(s: str) -> Optional[float]:
    s = (s or "").replace(",", "").replace("%", "").replace("₹", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _label(s: str) -> str:
    return re.sub(r"[^a-z% ]", "", s.lower().replace("\xa0", " ").replace("+", "")).strip()


_PERIOD = re.compile(r"^([A-Z][a-z]{2} \d{4}|TTM)$")


def _table(section: Optional[Node]) -> Optional[Table]:
    if section is None:
        return None
    t = section.find("table")
    if t is None:
        return None
    trs = list(t.find_all("tr"))
    if len(trs) < 2:
        return None
    head = [c.text() for c in trs[0].children if isinstance(c, Node) and c.tag in ("th", "td")]
    periods = [h for h in head[1:] if _PERIOD.match(h)]
    if not periods:
        return None
    rows, labels = {}, {}
    for tr in trs[1:]:
        cells = [c.text() for c in tr.children if isinstance(c, Node) and c.tag in ("th", "td")]
        if not cells or not cells[0]:
            continue
        key = _label(cells[0])
        rows[key] = [_num(x) for x in cells[1:1 + len(periods)]]
        labels[key] = cells[0].replace("+", "").replace("\xa0", " ").strip()
    return Table(periods=periods, rows=rows, labels=labels)


def _section(root: Node, sid: str) -> Optional[Node]:
    return root.find("section", id=sid)


def parse_company(html: str, symbol: str, url: str, basis: str, retrieved_at: datetime,
                  fixture: bool = False) -> CompanySnapshot:
    root = parse_dom(html)
    quarters = _table(_section(root, "quarters"))
    if quarters is None:
        raise SourceSchemaError("Screener page has no Quarterly Results table (layout changed or company not found)")
    snap = CompanySnapshot(symbol=symbol, basis=basis, source_url=url, retrieved_at=retrieved_at, fixture=fixture,
                           quarters=quarters, annual=_table(_section(root, "profit-loss")),
                           balance=_table(_section(root, "balance-sheet")), cashflow=_table(_section(root, "cash-flow")),
                           efficiency=_table(_section(root, "ratios")))
    h1 = root.find("h1")
    snap.name = h1.text() if h1 is not None else None
    about = root.find("div", class_="about")
    if about is not None:
        snap.about = about.text()[:1200]
    for a in root.find_all("a"):
        t = a.attrs.get("title")
        if t == "Sector" and not snap.sector:
            snap.sector = a.text()
        elif t == "Industry" and not snap.industry:
            snap.industry = a.text()
    for a in root.find_all("a"):
        href = a.attrs.get("href") or ""
        m = re.search(r"(?:bseindia\.com|/bse-quote)/.*?/(\d{6})/?", href)
        if m and not snap.bse_code:
            snap.bse_code = m.group(1)
        elif not snap.website and href.startswith("http") and "screener.in" not in href and \
                a.attrs.get("target") == "_blank" and re.search(r"^https?://(www\.)?[a-z0-9-]+\.(com|in|co\.in|net)/?$", href):
            snap.website = href
    ul = root.find("ul", id="top-ratios")
    if ul is not None:
        for li in ul.find_all("li"):
            name = li.find("span", class_="name")
            value = li.find("span", class_="value")
            if name is not None and value is not None:
                snap.ratios.append((name.text(), value.text()))
    for box in root.find_all("div", class_="documents"):
        cls = box.attrs.get("class", "")
        if "annual-reports" in cls:
            for a in box.find_all("a"):
                if a.attrs.get("href"):
                    note = a.find("div")
                    title = a.own_text() or a.text()
                    snap.annual_reports.append(DocLink(title=title, url=a.attrs["href"], note=note.text() if note else None))
        elif "credit-ratings" in cls:
            for a in box.find_all("a"):
                if a.attrs.get("href"):
                    note = a.find("div")
                    snap.credit_ratings.append(DocLink(title=a.own_text() or a.text(), url=a.attrs["href"],
                                                       note=note.text() if note else None))
        elif "concalls" in cls:
            for li in box.find_all("li"):
                period_div = li.find("div")
                c = Concall(period=period_div.text() if period_div is not None else "")
                for a in li.find_all("a"):
                    kind, href = a.text().lower(), a.attrs.get("href")
                    if not href:
                        continue
                    if "transcript" in kind:
                        c.transcript = href
                    elif "ppt" in kind:
                        c.ppt = href
                    elif "rec" in kind:
                        c.recording = href
                if c.period and (c.transcript or c.ppt or c.recording):
                    snap.concalls.append(c)
    for name, val in (("annual P&L", snap.annual), ("balance sheet", snap.balance), ("cash flow", snap.cashflow)):
        if val is None:
            snap.notes.append(f"Screener's {name} table was not found on the page.")
    return snap


# ------------------------------------------------------------------ results card
class ResultsRow(BaseModel):
    metric: str
    latest: Optional[float]
    prev: Optional[float]
    year_ago: Optional[float]
    qoq: Optional[float]
    yoy: Optional[float]
    derived: bool = False
    note: Optional[str] = None


class ResultsBlock(BaseModel):
    symbol: str
    basis: str
    unit: str = "₹ crore"
    periods: list[str]
    rows: list[ResultsRow]
    is_lender: bool
    source_url: str
    provenance: Provenance
    notes: list[str] = []


def _pct(a, b):
    """Change vs a comparison value; uses |b| so a move from a loss to a smaller loss reads as an improvement."""
    return None if a is None or b in (None, 0) else (a - b) / abs(b) * 100


def parse_quarters(html: str) -> tuple[list[str], dict[str, list[Optional[float]]]]:
    t = _table(_section(parse_dom(html), "quarters"))
    if t is None:
        raise SourceSchemaError("Screener page has no Quarterly Results table (layout changed or company not found)")
    return t.periods, t.rows


def build_results(symbol: str, periods: list[str], rows: dict, url: str, basis: str, retrieved_at: datetime,
                  is_lender: bool, fixture: bool = False) -> ResultsBlock:
    periods = [p for p in periods if p != "TTM"]
    if len(periods) < 2:
        raise SourceSchemaError("fewer than two quarters published")
    n = len(periods) - 1
    ya = n - 4 if n >= 4 else None

    def pick(*names):
        for nm in names:
            if nm in rows:
                return rows[nm]
        return None

    rev = pick("sales", "revenue")
    pbt = pick("profit before tax")
    pat = pick("net profit")
    if rev is None or pbt is None or pat is None:
        raise SourceSchemaError(f"missing rows; found {sorted(rows)[:12]}")
    notes = []
    interest, dep, oth = pick("interest"), pick("depreciation"), pick("other income")
    if is_lender or "financing profit" in rows:
        ebitda, is_lender = None, True
        notes.append("EBITDA is not meaningful for lenders (interest is their main cost of business).")
    elif interest and dep and oth:
        ebitda = [None if None in (p, i, d, o) else p + i + d - o for p, i, d, o in zip(pbt, interest, dep, oth)]
    else:
        ebitda = None
        notes.append("EBITDA could not be derived: interest, depreciation or other income is missing.")

    def row(metric, series, derived=False, note=None):
        if series is None:
            return ResultsRow(metric=metric, latest=None, prev=None, year_ago=None, qoq=None, yoy=None,
                              derived=derived, note=note or "n/m")
        cur, prev = series[n], series[n - 1]
        yr = series[ya] if ya is not None else None
        return ResultsRow(metric=metric, latest=cur, prev=prev, year_ago=yr, qoq=_pct(cur, prev), yoy=_pct(cur, yr),
                          derived=derived, note=note)

    out_rows = [row("Revenue", rev), row("EBITDA", ebitda, derived=True,
                                         note=None if ebitda else ("n/m for lenders" if is_lender else "not derivable")),
                row("PBT", pbt), row("PAT", pat)]
    if ya is None:
        notes.append("Fewer than five quarters published, so YoY is not available.")
    return ResultsBlock(symbol=symbol, basis=basis, periods=[periods[n], periods[n - 1], periods[ya] if ya is not None else "—"],
                        rows=out_rows, is_lender=is_lender, source_url=url, notes=notes,
                        provenance=Provenance(source_class=SourceClass.STANDARDIZED_TABLE, source_name="screener.in",
                                              url=url, retrieved_at=retrieved_at, locator=f"Quarterly Results, {periods[n]}",
                                              formula="EBITDA = PBT + Interest + Depreciation − Other Income; "
                                                      "QoQ/YoY = latest ÷ comparison − 1",
                                              fixture=fixture))


def results_from_snapshot(s: CompanySnapshot, is_lender: bool) -> ResultsBlock:
    return build_results(s.symbol, s.quarters.periods, s.quarters.rows, s.source_url, s.basis, s.retrieved_at,
                         is_lender, s.fixture)


class ScreenerSource:
    name = "screener"

    def __init__(self, http: HttpClient, url_template: str, clock: Callable[[], datetime], fixture: bool = False):
        self.http, self.url_template, self.clock, self.fixture = http, url_template, clock, fixture

    def fetch_company(self, symbol: str) -> CompanySnapshot:
        last_err: Exception | None = None
        for basis in ("consolidated", "standalone"):   # consolidated first; fall back when not published
            url = self.url_template.format(symbol=symbol, basis="consolidated/" if basis == "consolidated" else "")
            try:
                return parse_company(self.http.get(url).text, symbol, url, basis, self.clock(), self.fixture)
            except SourceSchemaError as e:
                last_err = e
        raise last_err  # type: ignore[misc]

    def fetch_results(self, symbol: str, is_lender: bool) -> ResultsBlock:
        return results_from_snapshot(self.fetch_company(symbol), is_lender)

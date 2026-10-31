"""Reading the filed PDFs behind Push items (brief: "take the actual results filing ..."; "a one-line summary").

results   The model finds the results table (current quarter, previous quarter, same quarter last year) and copies
          Revenue, other income, finance costs, depreciation, PBT and PAT. Every copied number must appear on the
          page it came from, or it is discarded. Units are converted, EBITDA, QoQ and YoY are computed in code, and
          the result is cross-checked against Screener's quarterly table; a mismatch is shown, not hidden.
summary   One sentence (≤ 30 words) on what a material filing discloses, from its first pages only. Any number in
          the sentence must appear in the filing text.

Both are cached per filing, so each PDF is read once. Without an LLM key, nothing here runs and the app shows the
filing link and Screener's numbers as before.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .research.claims import numbers_in
from .research.documents import Doc, DocumentSource, doc_id

UNIT_TO_CRORE = {"crore": 1.0, "crores": 1.0, "lakh": 0.01, "lakhs": 0.01, "million": 0.1, "millions": 0.1,
                 "thousand": 1e-5, "thousands": 1e-5, "rupees": 1e-7, "rs": 1e-7, "inr": 1e-7, "billion": 100.0}
RESULT_WORDS = ("revenue from operations", "total income", "profit before tax", "net profit", "profit for the period",
                "quarter ended", "three months ended", "finance cost", "depreciation", "other income", "interest earned")

RESULTS_SYSTEM = """You copy numbers from a company's quarterly results table. Use only the page given.
Pick the CONSOLIDATED table if the page has one, otherwise the standalone table. Copy each number exactly as printed
(keep commas and decimals; write negatives as -123 when printed in brackets). Do not calculate anything.
Reply with JSON only."""

RESULTS_SHAPE = ('{"basis":"consolidated | standalone","unit":"crore | lakh | million | thousand | rupees",'
                 '"columns":["label of current quarter column","previous quarter","same quarter last year"],'
                 '"revenue":["current","previous","year ago"],"other_income":["","",""],"finance_costs":["","",""],'
                 '"depreciation":["","",""],"pbt":["","",""],"pat":["","",""]}')

SUMMARY_SYSTEM = """You write one plain sentence (at most 30 words) saying what a company's stock-exchange filing
discloses and the concrete fact an investor would care about (who, what, how much, when). Use only the text given.
Copy any number exactly. If the text is routine paperwork with no concrete fact, say so in a few words.
Reply with JSON only: {"summary":"...","page":1}"""


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def _present(v, page_numbers: set[str]) -> bool:
    x = _to_float(v)
    if x is None:
        return False
    s = f"{abs(x):.2f}".rstrip("0").rstrip(".")
    return s in page_numbers or f"{abs(x):.0f}" in page_numbers or f"{abs(x):.1f}" in page_numbers


def best_results_page(pages: list[str]) -> Optional[int]:
    best, idx = 0, None
    for i, t in enumerate(pages):
        low = t.lower()
        score = sum(w in low for w in RESULT_WORDS) + (2 if "consolidated" in low else 0)
        if score > best:
            best, idx = score, i
    return idx if best >= 4 else None


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def period_label(col: str) -> str:
    """'Quarter ended 30.09.2026' / '30 September 2026' / 'Sep 30, 2026' -> 'Sep 2026' (Screener's style)."""
    m = re.search(r"\b\d{1,2}[./-](\d{1,2})[./-](\d{4})\b", col)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{_MONTHS[int(m.group(1)) - 1]} {m.group(2)}"
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(?:\d{1,2},?\s*)?(\d{4})", col, re.I)
    if m:
        return f"{m.group(1).title()} {m.group(2)}"
    return col


def _pct(a, b):
    return None if a is None or b in (None, 0) else (a - b) / abs(b) * 100


def results_block(raw: dict, page_text: str, page_no: int, url: str, symbol: str, is_lender: bool,
                  screener_latest: Optional[float] = None, fixture: bool = False) -> Optional[dict]:
    """Validated results block in the same shape as Screener's (so the app renders it the same way)."""
    nums = numbers_in(page_text)
    unit = str(raw.get("unit") or "").lower().strip().split()[0] if raw.get("unit") else ""
    if unit not in UNIT_TO_CRORE:
        m = re.search(r"(?:₹|rs\.?|inr)?\s*in\s+(crores?|lakhs?|millions?|thousands?|rupees)", page_text, re.I)
        unit = m.group(1).lower() if m else ""
    if unit not in UNIT_TO_CRORE:
        return None
    k = UNIT_TO_CRORE[unit]
    rows, dropped = {}, 0
    for key in ("revenue", "other_income", "finance_costs", "depreciation", "pbt", "pat"):
        vals = list(raw.get(key) or [])[:3] + [None] * 3
        clean = []
        for v in vals[:3]:
            if v in (None, "") or not _present(v, nums):
                if v not in (None, ""):
                    dropped += 1
                clean.append(None)
            else:
                clean.append(_to_float(v) * k)
        rows[key] = clean
    if None in (rows["revenue"][0], rows["pbt"][0], rows["pat"][0]):
        return None                                      # the headline numbers couldn't be verified on the page
    ebitda = None
    if not is_lender and all(x is not None for x in rows["finance_costs"] + rows["depreciation"] + rows["other_income"]):
        ebitda = [p + f + d - o for p, f, d, o in zip(rows["pbt"], rows["finance_costs"], rows["depreciation"],
                                                         rows["other_income"])]

    def row(metric, s, derived=False, note=None):
        if s is None:
            return {"metric": metric, "latest": None, "prev": None, "year_ago": None, "qoq": None, "yoy": None,
                    "derived": derived, "note": note or "n/m"}
        return {"metric": metric, "latest": s[0], "prev": s[1], "year_ago": s[2], "qoq": _pct(s[0], s[1]),
                "yoy": _pct(s[0], s[2]), "derived": derived, "note": note}

    cols = [period_label(str(c)[:40]) for c in (raw.get("columns") or [])][:3] + ["", "", ""]
    notes = []
    if is_lender:
        notes.append("EBITDA is not meaningful for lenders.")
    elif ebitda is None:
        notes.append("EBITDA could not be derived: finance costs, depreciation or other income wasn't found on the page.")
    if dropped:
        notes.append(f"{dropped} value(s) could not be found on the page and were left out.")
    check = None
    if screener_latest:
        diff = abs(rows["revenue"][0] - screener_latest) / screener_latest * 100
        check = {"screener_revenue": screener_latest, "diff_pct": diff, "ok": diff <= 2.0}
        if diff > 2.0:
            notes.append(f"Revenue differs from Screener's latest quarter by {diff:.1f}% "
                         "(different basis or a quarter Screener hasn't updated yet).")
    basis = "consolidated" if "consol" in str(raw.get("basis", "")).lower() else "standalone"
    return {
        "symbol": symbol, "basis": basis, "unit": "₹ crore", "periods": [cols[0] or "This quarter", cols[1] or "Previous quarter",
                                                                       cols[2] or "Year-ago quarter"],
        "rows": [row("Revenue", rows["revenue"]), row("EBITDA", ebitda, True, None if ebitda else
                                                      ("n/m for lenders" if is_lender else "not derivable")),
                 row("PBT", rows["pbt"]), row("PAT", rows["pat"])],
        "is_lender": is_lender, "source_url": f"{url}#page={page_no}", "notes": notes, "check": check,
        "from_filing": True, "page": page_no, "unit_in_filing": unit,
        "provenance": {"source_class": "PRIMARY_DOC", "source_name": "results filing", "url": url,
                       "locator": f"page {page_no}", "fixture": fixture,
                       "formula": "Copied from the filed results table; EBITDA = PBT + finance costs + depreciation − "
                                  "other income; QoQ/YoY = latest ÷ comparison − 1"},
    }


def summary_ok(text: str, source: str) -> bool:
    if not text or len(text.split()) > 45:
        return False
    return not (numbers_in(text) - numbers_in(source))


class FilingReader:
    def __init__(self, docs: DocumentSource, llm, store):
        self.docs, self.llm, self.store = docs, llm, store

    @property
    def available(self) -> bool:
        return bool(self.llm and self.llm.available)

    def cached(self, uid: str) -> Optional[dict]:
        raw = self.store.get_research(f"filing:{uid}", 24 * 30)
        return json.loads(raw) if raw else None

    def _save(self, uid: str, rec: dict) -> dict:
        self.store.put_research(f"filing:{uid}", json.dumps(rec))
        return rec

    def _pages(self, url: str, title: str) -> tuple[Doc, list[str]]:
        d = Doc(id=doc_id(url), kind="filing", title=title, period="", url=url, host="")
        return self.docs.load(d)

    def results(self, uid: str, url: str, symbol: str, is_lender: bool, screener_latest: Optional[float],
                fixture: bool = False) -> dict:
        doc, pages = self._pages(url, "Results filing")
        if not pages:
            return self._save(uid, {"kind": "results", "status": "unreadable", "error": doc.error})
        i = best_results_page(pages)
        if i is None:
            return self._save(uid, {"kind": "results", "status": "no_table"})
        text = pages[i][:7000]
        raw = self.llm.complete_json(f"Page {i + 1} of the results filing:\n{text}\n\nReturn JSON exactly in this shape: "
                                     f"{RESULTS_SHAPE}", system=RESULTS_SYSTEM, max_tokens=700, route="fast")
        if raw is None:
            return {"kind": "results", "status": "llm_failed"}           # not cached: retried next refresh
        block = results_block(raw, text, i + 1, url, symbol, is_lender, screener_latest, fixture)
        return self._save(uid, {"kind": "results", "status": "ok" if block else "unverified", "block": block})

    def summary(self, uid: str, url: str, subject: str) -> dict:
        doc, pages = self._pages(url, subject[:80])
        if not pages:
            return self._save(uid, {"kind": "summary", "status": "unreadable", "error": doc.error})
        text = "\n".join(pages[:2])[:3500]
        raw = self.llm.complete_json(f"Filing subject: {subject}\n\nFiling text (first pages):\n{text}",
                                     system=SUMMARY_SYSTEM, max_tokens=200, route="fast")
        if raw is None:
            return {"kind": "summary", "status": "llm_failed"}
        s = " ".join(str(raw.get("summary") or "").split())
        if not summary_ok(s, text):
            return self._save(uid, {"kind": "summary", "status": "unverified"})
        page = raw.get("page") if isinstance(raw.get("page"), int) and 1 <= raw.get("page") <= 2 else 1
        return self._save(uid, {"kind": "summary", "status": "ok", "text": s, "page": page, "url": f"{url}#page={page}"})

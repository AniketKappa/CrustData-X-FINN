"""Promises ledger: what management guided on each call vs what the reported numbers then showed.

The model only finds guidance and copies the quote (verified against the transcript). Matching a promise to a
period, computing the actual, and the verdict are done here, in code, from the quarterly table.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

CHECKABLE = {"revenue_growth": ("revenue", "Revenue growth, YoY"), "pat_growth": ("pat", "Profit growth, YoY"),
             "ebitda_margin": ("opm", "Operating (EBITDA) margin")}
_MON = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}


class LedgerRow(BaseModel):
    said_in: str                 # "Q2 FY27 call"
    metric: str
    statement: str
    quote: str
    cite: dict                   # {doc_id, title, page, url}
    low: Optional[float] = None
    high: Optional[float] = None
    unit: str = ""
    horizon: str = ""
    quarters: list[str] = []     # quarters used for the actual
    actual: Optional[float] = None
    actual_label: str = ""
    verdict: str = "unchecked"   # delivered | beat | on_track | behind | missed | too_early | unchecked
    method: str = ""


def quarter_key(period: str) -> Optional[tuple[int, int]]:
    """'Sep 2026' -> (2027, 2): fiscal year, quarter number."""
    m = re.match(r"([A-Za-z]{3}) (\d{4})", period)
    if not m or m.group(1) not in _MON:
        return None
    mon, yr = _MON[m.group(1)], int(m.group(2))
    return (yr, 4) if mon == 3 else (yr + 1, {6: 1, 9: 2, 12: 3}[mon])


def horizon_quarters(horizon: str, call_label: str) -> Optional[list[tuple[int, int]]]:
    """Quarters a guidance horizon covers, or None if it can't be pinned to quarters."""
    h = (horizon or "").upper().replace(" ", "")
    cm = re.match(r"Q([1-4])FY(\d{2})", call_label.replace(" ", ""))
    call = (2000 + int(cm.group(2)), int(cm.group(1))) if cm else None
    m = re.search(r"Q([1-4])FY'?(\d{2,4})", h)
    if m:
        return [(_fy(m.group(2)), int(m.group(1)))]
    m = re.search(r"H([12])FY'?(\d{2,4})", h)
    if m:
        y = _fy(m.group(2))
        return [(y, 1), (y, 2)] if m.group(1) == "1" else [(y, 3), (y, 4)]
    m = re.search(r"FY'?(\d{2,4})", h)
    if m:
        y = _fy(m.group(1))
        return [(y, q) for q in (1, 2, 3, 4)]
    if call and re.search(r"NEXTQUARTER|COMINGQUARTER|NEXTQTR", h):
        y, q = call
        return [(y, q + 1)] if q < 4 else [(y + 1, 1)]
    if call and re.search(r"THISYEAR|CURRENTYEAR|THISFISCAL|CURRENTFISCAL|FULLYEAR", h):
        y = call[0] if call[1] < 4 else call[0] + 1
        return [(y, q) for q in (1, 2, 3, 4)]
    return None


def _fy(s: str) -> int:
    n = int(s)
    return 2000 + n if n < 100 else n


def evaluate(row: LedgerRow, actuals: list[dict], call_label: str) -> LedgerRow:
    if row.metric not in CHECKABLE:
        row.verdict, row.method = "unchecked", "Not checkable from the reported P&L; see the quote."
        return row
    if row.low is None and row.high is None:
        row.verdict, row.method = "unchecked", "No number was guided."
        return row
    if row.unit and row.unit.strip() not in ("%", "percent"):
        row.verdict, row.method = "unchecked", "Guided in absolute terms; FINN compares percentage guidance only."
        return row
    qs = horizon_quarters(row.horizon, call_label)
    by_q = {quarter_key(a["period"]): a for a in actuals if quarter_key(a["period"])}
    if qs is None:                                  # unpinned horizon: compare with quarters reported since the call
        cm = re.match(r"Q([1-4]) FY(\d{2})", call_label)
        if not cm:
            row.verdict, row.method = "unchecked", "The guidance period could not be matched to quarters."
            return row
        start = (2000 + int(cm.group(2)), int(cm.group(1)))
        qs = sorted(k for k in by_q if k > start)
        open_ended = True
    else:
        open_ended = False
    have = [q for q in qs if q in by_q]
    if not have:
        row.verdict, row.method = "too_early", "No quarter in the guided period has been reported yet."
        return row
    key, label = CHECKABLE[row.metric]
    row.quarters = [by_q[q]["period"] for q in have]
    row.actual_label = label
    if key == "opm":
        num = sum((by_q[q]["opm"] or 0) * (by_q[q]["revenue"] or 0) for q in have)
        den = sum((by_q[q]["revenue"] or 0) for q in have if by_q[q]["opm"] is not None)
        row.actual = num / den if den else None
        row.method = "Revenue-weighted operating margin of the quarters below (Screener quarterly table)."
    else:
        cur = sum(by_q[q][key] or 0 for q in have)
        prev_keys = [(y - 1, n) for y, n in have]
        if not all(p in by_q and by_q[p][key] is not None for p in prev_keys):
            row.verdict, row.method = "unchecked", "The same quarters a year earlier are not in the table."
            return row
        prev = sum(by_q[p][key] for p in prev_keys)
        row.actual = (cur / prev - 1) * 100 if prev > 0 else None
        row.method = "Growth of the quarters below vs the same quarters a year earlier (Screener quarterly table)."
    if row.actual is None:
        row.verdict = "unchecked"
        return row
    lo = row.low if row.low is not None else row.high
    hi = row.high if row.high is not None else row.low
    tol = 0.5 if key == "opm" else 1.0
    complete = not open_ended and len(have) == len(qs)
    if row.actual > hi + tol:
        row.verdict = "beat" if complete else "on_track"
    elif row.actual >= lo - tol:
        row.verdict = "delivered" if complete else "on_track"
    else:
        row.verdict = "missed" if complete else "behind"
    return row


VERDICT_LABEL = {"beat": "Beat", "delivered": "Delivered", "on_track": "On track", "behind": "Behind so far",
                 "missed": "Missed", "too_early": "Too early", "unchecked": "Not checkable"}


def scorecard(rows: list[LedgerRow]) -> dict:
    checked = [r for r in rows if r.verdict in ("beat", "delivered", "missed")]
    kept = [r for r in checked if r.verdict in ("beat", "delivered")]
    return {"checked": len(checked), "kept": len(kept), "pending": sum(r.verdict in ("on_track", "behind", "too_early")
                                                                       for r in rows),
            "unchecked": sum(r.verdict == "unchecked" for r in rows), "total": len(rows)}

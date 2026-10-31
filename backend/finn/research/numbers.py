"""Numbers for the research dossier, computed in code from Screener's standardised tables (STANDARDIZED_TABLE,
D-35). LLMs never produce or transform these numbers (CLAUDE.md rule 6). Every fact carries its formula and source.

Each section returns facts (citable as [F#]) and plain observations written by code from those facts.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


class Fact(BaseModel):
    id: str                        # "F3": the citation handle
    label: str
    value: Optional[float]
    unit: str                      # "₹ cr" | "%" | "x" | "days"
    period: str
    formula: Optional[str] = None
    source: str = "screener.in standardised table"
    locator: str = ""
    url: str = ""

    def text(self) -> str:
        return f"{self.label} ({self.period}): {fmt(self.value, self.unit)}"


class Observation(BaseModel):
    text: str
    facts: list[str]               # fact ids
    tone: str = "neutral"          # good | watch | neutral


class Series(BaseModel):
    label: str
    unit: str
    periods: list[str]
    values: list[Optional[float]]


class NumbersSection(BaseModel):
    id: str
    title: str
    facts: list[Fact] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    table: Optional[dict] = None   # {"head": [...], "rows": [[label, v1, v2...]], "unit": str}
    notes: list[str] = Field(default_factory=list)


def fmt(v: Optional[float], unit: str) -> str:
    if v is None:
        return "n/a"
    if unit == "₹ cr":
        return f"₹{v:,.0f} cr"
    if unit == "%":
        return f"{v:.1f}%"
    if unit == "x":
        return f"{v:.2f}×"
    if unit == "days":
        return f"{v:.0f} days"
    return f"{v:,.2f}"


def _row(t, *names) -> Optional[list[Optional[float]]]:
    if t is None:
        return None
    for n in names:
        if n in t.rows:
            return t.rows[n]
    return None


def _years(t) -> list[int]:
    """Indexes of fiscal-year columns (drops TTM)."""
    return [i for i, p in enumerate(t.periods) if p != "TTM"] if t is not None else []


def cagr(a: Optional[float], b: Optional[float], years: int) -> Optional[float]:
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return ((b / a) ** (1 / years) - 1) * 100


def fy(period: str) -> str:
    m = re.match(r"[A-Za-z]{3} (\d{4})", period)
    return f"FY{int(m.group(1)) % 100:02d}" if m else period


class FactBook:
    def __init__(self, url: str, basis: str):
        self.url, self.basis, self.facts = url, basis, []

    def add(self, label, value, unit, period, formula=None, locator="") -> Fact:
        f = Fact(id=f"F{len(self.facts) + 1}", label=label, value=value, unit=unit, period=period, formula=formula,
                 locator=locator, url=self.url, source=f"screener.in standardised table ({self.basis})")
        self.facts.append(f)
        return f


def build(snap, is_lender: bool = False) -> tuple[list[NumbersSection], FactBook]:
    fb = FactBook(snap.source_url, snap.basis)
    return [financial(snap, fb, is_lender), trajectory(snap, fb, is_lender), balance(snap, fb, is_lender),
            cash(snap, fb, is_lender)], fb


# ------------------------------------------------------------------ sections
def financial(s, fb: FactBook, lender: bool) -> NumbersSection:
    sec = NumbersSection(id="financial", title="Financial snapshot")
    a = s.annual
    if a is None:
        sec.notes.append("Screener's annual P&L table is missing for this company.")
        return sec
    ys = _years(a)
    if not ys:
        return sec
    i = ys[-1]
    per = fy(a.periods[i])
    rev = _row(a, "sales", "revenue")
    pat = _row(a, "net profit")
    op = _row(a, "operating profit", "financing profit")
    opm = _row(a, "opm %", "financing margin %")
    if rev:
        sec.facts.append(fb.add("Revenue", rev[i], "₹ cr", per, locator=f"Profit & Loss, {a.periods[i]}"))
    if op:
        sec.facts.append(fb.add("Financing profit" if lender else "Operating profit (EBITDA)", op[i], "₹ cr", per,
                                locator=f"Profit & Loss, {a.periods[i]}"))
    if opm:
        sec.facts.append(fb.add("Financing margin" if lender else "Operating margin", opm[i], "%", per,
                                formula="operating profit ÷ revenue", locator=f"Profit & Loss, {a.periods[i]}"))
    if pat:
        sec.facts.append(fb.add("Net profit (PAT)", pat[i], "₹ cr", per, locator=f"Profit & Loss, {a.periods[i]}"))
        if rev and rev[i]:
            sec.facts.append(fb.add("Net margin", pat[i] / rev[i] * 100 if pat[i] is not None else None, "%", per,
                                    formula="PAT ÷ revenue"))
    if "TTM" in a.periods and rev and pat:
        t = a.periods.index("TTM")
        sec.facts.append(fb.add("Revenue, last 12 months", rev[t], "₹ cr", "TTM", locator="Profit & Loss, TTM"))
        sec.facts.append(fb.add("PAT, last 12 months", pat[t], "₹ cr", "TTM", locator="Profit & Loss, TTM"))
    for name, value in s.ratios:
        n = name.strip().lower()
        num = _num(value)
        if n in ("roce", "roe", "stock p/e", "market cap", "dividend yield") and num is not None:
            unit = "%" if n in ("roce", "roe", "dividend yield") else ("₹ cr" if n == "market cap" else "x")
            sec.facts.append(fb.add({"stock p/e": "Price / earnings", "market cap": "Market cap"}.get(n, name.strip()),
                                    num, unit, "latest", locator="Top ratios"))
    f = {x.label: x for x in sec.facts}
    if "Operating margin" in f and "Net margin" in f and f["Operating margin"].value is not None:
        sec.observations.append(Observation(
            text=f"In {per} the business earned an operating margin of {fmt(f['Operating margin'].value, '%')} "
                 f"and kept {fmt(f['Net margin'].value, '%')} of revenue as profit.",
            facts=[f["Operating margin"].id, f["Net margin"].id]))
    return sec


def trajectory(s, fb: FactBook, lender: bool) -> NumbersSection:
    sec = NumbersSection(id="trajectory", title="Trajectory")
    a = s.annual
    ys = _years(a)
    if len(ys) < 3:
        sec.notes.append("Fewer than three years of annual numbers.")
        return sec
    ys = ys[-10:]
    rev = _row(a, "sales", "revenue")
    pat = _row(a, "net profit")
    opm = _row(a, "opm %", "financing margin %")
    labels = [fy(a.periods[i]) for i in ys]
    for name, r, unit in (("Revenue", rev, "₹ cr"), ("Net profit", pat, "₹ cr"), ("Operating margin", opm, "%")):
        if r:
            sec.series.append(Series(label=name, unit=unit, periods=labels, values=[r[i] for i in ys]))
    last = ys[-1]
    for span in (3, 5):
        if len(ys) > span:
            first = ys[-1 - span]
            for name, r in (("Revenue", rev), ("Net profit", pat)):
                if r:
                    sec.facts.append(fb.add(f"{name} growth, {span}-year CAGR", cagr(r[first], r[last], span), "%",
                                            f"{fy(a.periods[first])}–{fy(a.periods[last])}",
                                            formula="(end ÷ start)^(1/years) − 1", locator="Profit & Loss"))
    if opm and len(ys) > 3:
        first = ys[-4]
        sec.facts.append(fb.add("Operating margin, start", opm[first], "%", fy(a.periods[first]), locator="Profit & Loss"))
        sec.facts.append(fb.add("Operating margin, latest", opm[last], "%", fy(a.periods[last]), locator="Profit & Loss"))
    f = {x.label: x for x in sec.facts}
    r3, p3 = f.get("Revenue growth, 3-year CAGR"), f.get("Net profit growth, 3-year CAGR")
    if r3 and p3 and r3.value is not None and p3.value is not None:
        lead = "Profit grew faster than sales" if p3.value > r3.value + 2 else (
            "Profit lagged sales" if p3.value < r3.value - 2 else "Profit kept pace with sales")
        sec.observations.append(Observation(
            text=f"Over three years revenue compounded at {fmt(r3.value, '%')} a year and profit at {fmt(p3.value, '%')}. "
                 f"{lead}.", facts=[r3.id, p3.id], tone="good" if p3.value >= r3.value else "watch"))
    m0, m1 = f.get("Operating margin, start"), f.get("Operating margin, latest")
    if m0 and m1 and m0.value is not None and m1.value is not None:
        d = m1.value - m0.value
        word = "expanded" if d > 1 else ("compressed" if d < -1 else "held roughly steady")
        sec.observations.append(Observation(
            text=f"Operating margin {word}: {fmt(m0.value, '%')} in {m0.period} to {fmt(m1.value, '%')} in {m1.period}.",
            facts=[m0.id, m1.id], tone="good" if d > 1 else ("watch" if d < -1 else "neutral")))
    return sec


def balance(s, fb: FactBook, lender: bool) -> NumbersSection:
    sec = NumbersSection(id="balance", title="Balance sheet")
    b = s.balance
    ys = _years(b)
    if not ys:
        sec.notes.append("Screener's balance sheet table is missing for this company.")
        return sec
    i = ys[-1]
    per = fy(b.periods[i])
    eqc, res, bor = _row(b, "equity capital"), _row(b, "reserves"), _row(b, "borrowings", "borrowing")
    dep = _row(b, "deposits")
    equity = [None if x is None or y is None else x + y for x, y in zip(eqc or [], res or [])] if eqc and res else None
    if bor:
        sec.facts.append(fb.add("Borrowings", bor[i], "₹ cr", per, locator=f"Balance Sheet, {b.periods[i]}"))
    if equity:
        sec.facts.append(fb.add("Shareholders' equity", equity[i], "₹ cr", per, formula="equity capital + reserves",
                                locator=f"Balance Sheet, {b.periods[i]}"))
    if dep:
        sec.facts.append(fb.add("Deposits", dep[i], "₹ cr", per, locator=f"Balance Sheet, {b.periods[i]}"))
    de_series = []
    if bor and equity:
        de_series = [None if (x is None or e in (None, 0)) else x / e for x, e in zip(bor, equity)]
        sec.facts.append(fb.add("Debt-to-equity", de_series[i], "x", per, formula="borrowings ÷ (equity capital + reserves)"))
        if len(ys) > 3:
            j = ys[-4]
            sec.facts.append(fb.add("Debt-to-equity, three years earlier", de_series[j], "x", fy(b.periods[j]),
                                    formula="borrowings ÷ (equity capital + reserves)"))
        sec.series.append(Series(label="Debt-to-equity", unit="x", periods=[fy(b.periods[k]) for k in ys[-8:]],
                                 values=[de_series[k] for k in ys[-8:]]))
    e = s.efficiency
    ey = _years(e)
    if ey:
        k = ey[-1]
        rows = [("Debtor days", "debtor days"), ("Inventory days", "inventory days"), ("Payable days", "days payable"),
                ("Cash conversion cycle", "cash conversion cycle"), ("Working capital days", "working capital days")]
        head = [fy(e.periods[x]) for x in ey[-5:]]
        trows = []
        for label, key in rows:
            r = _row(e, key)
            if r:
                trows.append([label] + [r[x] for x in ey[-5:]])
                sec.facts.append(fb.add(label, r[k], "days", fy(e.periods[k]), locator=f"Ratios, {e.periods[k]}"))
        if trows:
            sec.table = {"head": head, "rows": trows, "unit": "days"}
    f = {x.label: x for x in sec.facts}
    de, de0 = f.get("Debt-to-equity"), f.get("Debt-to-equity, three years earlier")
    if lender:
        sec.notes.append("For lenders, borrowing is the raw material of the business; debt-to-equity is not a risk "
                         "measure here. Capital adequacy and asset quality are in the annual report.")
    elif de and de.value is not None:
        level = "little debt" if de.value < 0.3 else ("moderate debt" if de.value < 1 else "high debt")
        txt = f"Debt-to-equity is {fmt(de.value, 'x')} ({level})"
        ids = [de.id]
        if de0 and de0.value is not None:
            txt += f", {'down' if de.value < de0.value else 'up'} from {fmt(de0.value, 'x')} in {de0.period}"
            ids.append(de0.id)
        sec.observations.append(Observation(text=txt + ".", facts=ids, tone="good" if de.value < 0.5 else "watch"))
    ccc = f.get("Cash conversion cycle")
    if ccc and ccc.value is not None and sec.table:
        first = next((r for r in sec.table["rows"] if r[0] == "Cash conversion cycle"), None)
        if first and first[1] is not None:
            d = ccc.value - first[1]
            sec.observations.append(Observation(
                text=f"Cash is tied up in operations for {fmt(ccc.value, 'days')} (cash conversion cycle), "
                     f"{'longer' if d > 5 else 'shorter' if d < -5 else 'about the same'} than in {sec.table['head'][0]} "
                     f"({fmt(first[1], 'days')}).", facts=[ccc.id], tone="watch" if d > 5 else "neutral"))
    return sec


def cash(s, fb: FactBook, lender: bool) -> NumbersSection:
    sec = NumbersSection(id="cash", title="Cash quality")
    c, a = s.cashflow, s.annual
    cy = _years(c)
    if not cy or a is None:
        sec.notes.append("Screener's cash-flow table is missing for this company.")
        return sec
    cfo, cfi = _row(c, "cash from operating activity"), _row(c, "cash from investing activity")
    pat = _row(a, "net profit")
    if not cfo or not pat:
        return sec
    pat_by = {fy(a.periods[i]): pat[i] for i in _years(a)}
    years = [fy(c.periods[i]) for i in cy][-6:]
    idx = cy[-6:]
    cfo_v = [cfo[i] for i in idx]
    pat_v = [pat_by.get(y) for y in years]
    ratio = [None if (x is None or p in (None, 0) or p < 0) else x / p for x, p in zip(cfo_v, pat_v)]
    sec.series.append(Series(label="Cash from operations", unit="₹ cr", periods=years, values=cfo_v))
    sec.series.append(Series(label="Net profit", unit="₹ cr", periods=years, values=pat_v))
    trows = [["Cash from operations"] + cfo_v, ["Net profit"] + pat_v, ["Cash ÷ profit"] + ratio]
    if cfi:
        fcf = [None if x is None or y is None else x + y for x, y in zip(cfo_v, [cfi[i] for i in idx])]
        trows.append(["Operating + investing cash"] + fcf)
    sec.table = {"head": years, "rows": trows, "unit": "₹ cr; ratio in ×"}
    sec.facts.append(fb.add("Cash from operations", cfo_v[-1], "₹ cr", years[-1], locator=f"Cash Flows, {years[-1]}"))
    sec.facts.append(fb.add("Cash from operations ÷ PAT", ratio[-1], "x", years[-1], formula="CFO ÷ PAT"))
    tot_cfo = sum(x for x in cfo_v if x is not None)
    tot_pat = sum(p for p in pat_v if p is not None)
    if tot_pat > 0:
        sec.facts.append(fb.add(f"Cash ÷ profit, {len(years)} years combined", tot_cfo / tot_pat, "x",
                                f"{years[0]}–{years[-1]}", formula="Σ CFO ÷ Σ PAT"))
    if cfi:
        sec.facts.append(fb.add("Operating + investing cash", trows[-1][-1], "₹ cr", years[-1],
                                formula="CFO + cash from investing (includes treasury investments, not only capex)"))
    f = {x.label: x for x in sec.facts}
    comb = next((x for x in sec.facts if x.label.startswith("Cash ÷ profit,")), None)
    if lender:
        sec.notes.append("A lender's operating cash flow swings with loan growth, so cash ÷ profit says little about "
                         "earnings quality for banks and NBFCs.")
    elif comb and comb.value is not None:
        q = "profits turned into cash" if comb.value >= 0.9 else ("most profit turned into cash" if comb.value >= 0.7
                                                                  else "a large share of profit did not turn into cash")
        sec.observations.append(Observation(
            text=f"Over {len(years)} years, operating cash was {fmt(comb.value, 'x')} reported profit: {q}.",
            facts=[comb.id], tone="good" if comb.value >= 0.9 else "watch"))
    return sec


def _num(v: str) -> Optional[float]:
    m = re.search(r"-?[\d,]+(?:\.\d+)?", v or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# ------------------------------------------------------------------ quarterly actuals for the promises ledger
def quarter_actuals(s) -> list[dict]:
    """Per quarter: revenue, operating margin, PAT and their YoY growth. Periods like 'Jun 2026'."""
    q = s.quarters
    if q is None:
        return []
    ps = [p for p in q.periods if p != "TTM"]
    rev, pat, opm = _row(q, "sales", "revenue"), _row(q, "net profit"), _row(q, "opm %", "financing margin %")
    out = []
    for i, p in enumerate(ps):
        row = {"period": p, "revenue": rev[i] if rev else None, "pat": pat[i] if pat else None,
               "opm": opm[i] if opm else None}
        if i >= 4:
            row["revenue_yoy"] = _g(rev[i] if rev else None, rev[i - 4] if rev else None)
            row["pat_yoy"] = _g(pat[i] if pat else None, pat[i - 4] if pat else None)
        out.append(row)
    return out


def _g(a, b):
    return None if a is None or b in (None, 0) else (a / b - 1) * 100 if b > 0 else None

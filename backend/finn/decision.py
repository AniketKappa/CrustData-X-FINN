"""Decision support (hackathon playbook §8–§10): factors, grades, FINN Rank, a price-only backtest, red flags,
"why did it move" validation and portfolio health.

Everything here is deterministic Python (CLAUDE.md rule 6). LLMs only write wording, and their output is
validated against the numbers and source ids computed here. FINN Rank is an experimental ranking vs FINN's
tracked stocks. It is not a prediction or a probability, and no output here gives buy/sell advice.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Sequence

MODEL_VERSION = "rank-v0-hackathon"
RANK_CAVEAT = "Experimental ranking vs FINN's tracked stocks — not investment advice."
BACKTEST_CAVEAT = ("Universe = today's FINN stocks (survivorship bias: winners that are still listed). Price signals "
                   "only; fundamentals excluded because they aren't point-in-time. Costs and risk-free rate are "
                   "assumptions. Past results don't predict future returns.")
WEIGHTS = {"momentum": 0.35, "quality": 0.30, "safety": 0.20, "value": 0.15}
PRICE_WEIGHTS = {"momentum": 0.35 / 0.55, "safety": 0.20 / 0.55}     # 0.636 / 0.364
FORBIDDEN = ["guaranteed", "sure shot", "sure-shot", "will rise", "will fall", "will go up", "will go down",
             "target price", "price target", "% chance", "percent chance", "probability of", "multibagger",
             "can't lose", "risk-free", "definitely buy", "definitely sell", "strong buy", "strong sell"]
REFUSAL = "FINN doesn't give probabilities or price targets"


# ------------------------------------------------------------------ number parsing (Indian formats)
_LAKH = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7}


def parse_num(s: object) -> Optional[float]:
    """'₹ 4,74,227 Cr.' -> 474227 (stays in crore); '31.9 %' -> 31.9; '−5.0%' -> -5.0; '(10.2)' -> -10.2;
    '1.2 Lakh' -> 120000; 'abc' -> None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return None if (isinstance(s, float) and not math.isfinite(s)) else float(s)
    t = str(s).strip().replace("−", "-").replace("–", "-").replace("—", "-").replace("\xa0", " ")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    mult = 1.0
    low = t.lower()
    for word, m in _LAKH.items():
        if re.search(rf"\b{word}\b", low):
            mult = m
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+", t)
    if not m:
        return None
    try:
        v = float(m.group(0).replace(",", "")) * mult
    except ValueError:
        return None
    return -abs(v) if neg else v


def clean(obj):
    """NaN/inf -> None so every JSON we emit is strict."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


# ------------------------------------------------------------------ price factors
def price_factors(closes: Sequence[float]) -> dict[str, Optional[float]]:
    """Closes ascending; the last one is 't'. Gates per playbook §8.1."""
    P = list(closes)
    n = len(P)
    t = n - 1
    out: dict[str, Optional[float]] = {"mom_12_1": None, "mom_6_1": None, "high_52w": None, "vol_1y": None}
    if n >= 273:
        out["mom_12_1"] = P[t - 21] / P[t - 252] - 1
    if n >= 147:
        out["mom_6_1"] = P[t - 21] / P[t - 126] - 1
    if n >= 252:
        out["high_52w"] = P[t] / max(P[t - 251:t + 1])
        r = [P[i] / P[i - 1] - 1 for i in range(t - 250, t + 1)]          # 251 returns inside the 252-bar window
        mu = sum(r) / len(r)
        out["vol_1y"] = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
    return out


# ------------------------------------------------------------------ fundamental factors (Screener snapshot)
def _norm(s: str) -> str:
    return s.replace("+", "").replace("\xa0", " ").strip().lower()


def _row(table, name: str) -> Optional[dict[str, Optional[float]]]:
    if table is None:
        return None
    for k, vals in table.rows.items():
        if _norm(k) == name:
            return {p: v for p, v in zip(table.periods, vals) if p != "TTM"}
    return None


def _ratio(snap, name: str) -> Optional[float]:
    for k, v in snap.ratios:
        if _norm(k) == _norm(name):
            return parse_num(v)
    return None


def fundamental_factors(snap, is_lender: bool) -> tuple[dict[str, Optional[float]], dict[str, bool]]:
    """Returns (values, guards). guards['negative_equity'] forces quality_de's percentile to 0."""
    f: dict[str, Optional[float]] = {k: None for k in ("quality_roe", "quality_roce", "quality_cfo_pat",
                                                       "quality_de", "value_ep", "value_bp")}
    guards = {"negative_equity": False}
    if snap is None:
        return f, guards
    f["quality_roe"] = _ratio(snap, "ROE")
    if not is_lender:
        f["quality_roce"] = _ratio(snap, "ROCE")
    pe = _ratio(snap, "Stock P/E")
    f["value_ep"] = 1 / pe if pe and pe > 0 else None
    bv, price = _ratio(snap, "Book Value"), _ratio(snap, "Current Price")
    f["value_bp"] = bv / price if bv and bv > 0 and price and price > 0 else None
    if not is_lender:
        pat, cfo = _row(snap.annual, "net profit"), _row(snap.cashflow, "cash from operating activity")
        if pat and cfo:
            common = [p for p in pat if p in cfo and pat[p] is not None and cfo[p] is not None][-5:]
            if len(common) >= 3:
                sp, sc = sum(pat[p] for p in common), sum(cfo[p] for p in common)
                if sp > 0:
                    f["quality_cfo_pat"] = 0.0 if sc <= 0 else min(3.0, sc / sp)
        bor, eq, res = (_row(snap.balance, x) for x in ("borrowings", "equity capital", "reserves"))
        if bor and eq and res:
            per = [p for p in bor if p in eq and p in res and None not in (bor[p], eq[p], res[p])]
            if per:
                p = per[-1]
                nw = eq[p] + res[p]
                if nw <= 0:
                    guards["negative_equity"] = True
                    f["value_bp"] = None
                else:
                    f["quality_de"] = bor[p] / nw
    return f, guards


# ------------------------------------------------------------------ scoring
LOWER_BETTER = {"vol_1y", "quality_de"}
GROUPS = {"momentum": ["mom_12_1", "mom_6_1", "high_52w"],
          "quality": ["quality_roe", "quality_roce", "quality_cfo_pat", "quality_de"],
          "value": ["value_ep", "value_bp"], "safety": ["vol_1y"]}


def percentiles(values: dict[str, Optional[float]], lower_better: bool = False) -> dict[str, Optional[float]]:
    """Percentile rank 0..100 among non-missing values (ties share the mean rank)."""
    xs = {k: v for k, v in values.items() if v is not None and math.isfinite(v)}
    out: dict[str, Optional[float]] = {k: None for k in values}
    if not xs:
        return out
    if len(xs) == 1:
        return {**out, **{k: 50.0 for k in xs}}
    srt = sorted(xs.values(), reverse=lower_better)
    for k, v in xs.items():
        below = sum(1 for x in srt if (x < v if not lower_better else x > v))
        equal = sum(1 for x in srt if x == v)
        out[k] = 100.0 * (below + (equal - 1) / 2) / (len(srt) - 1)
    return out


def grade(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return "A" if p >= 80 else "B" if p >= 60 else "C" if p >= 40 else "D" if p >= 20 else "F"


def _bucket(p: Optional[float]) -> Optional[str]:
    return None if p is None else "G" if p >= 60 else "M" if p >= 40 else "B"


def plain_label(q: Optional[float], v: Optional[float], m: Optional[float]) -> str:
    Q, V, M = _bucket(q), _bucket(v), _bucket(m)
    if Q == "G" and V == "G" and M == "G":
        return "Strong, reasonably priced, and in favour"
    if Q == "G" and V == "G":
        return "Strong and cheap, but the market hasn't noticed yet"
    if Q == "G" and V == "B" and M == "G":
        return "Strong and popular, but expensive"
    if Q == "G" and V == "B":
        return "Strong company, expensive price, losing steam"
    if Q == "B" and V == "G":
        return "Cheap for a reason? Weak fundamentals"
    if Q == "B" and M == "G":
        return "Price running ahead of fundamentals — higher risk"
    if Q == "M" or None in (Q, V, M):
        return "Mixed picture"
    return "Weak on most measures"


@dataclass
class StockInputs:
    symbol: str
    closes: list[float]
    price_as_of: Optional[date] = None
    snapshot: object = None
    is_lender: bool = False
    stale: bool = False


def score_universe(stocks: Iterable[StockInputs], groups_used: Sequence[str] = tuple(WEIGHTS),
                   weights: Optional[dict[str, float]] = None) -> dict[str, dict]:
    stocks = list(stocks)
    weights = weights or WEIGHTS
    raw: dict[str, dict[str, Optional[float]]] = {}
    neg_eq: set[str] = set()
    for s in stocks:
        f = price_factors(s.closes)
        if any(g in groups_used for g in ("quality", "value")):
            ff, guards = fundamental_factors(s.snapshot, s.is_lender)
            f.update(ff)
            if guards["negative_equity"]:
                neg_eq.add(s.symbol)
        raw[s.symbol] = f
    keys = sorted({k for f in raw.values() for k in f})
    pct: dict[str, dict[str, Optional[float]]] = {s: {} for s in raw}
    for k in keys:
        col = percentiles({s: raw[s].get(k) for s in raw}, lower_better=k in LOWER_BETTER)
        for s in raw:
            pct[s][k] = col[s]
    for s in neg_eq:                             # negative net worth: worst leverage percentile, never a ratio
        pct[s]["quality_de"] = 0.0
    out: dict[str, dict] = {}
    for s in raw:
        grp: dict[str, Optional[float]] = {}
        for g in groups_used:
            vals = [pct[s].get(k) for k in GROUPS[g] if pct[s].get(k) is not None]
            grp[g] = sum(vals) / len(vals) if vals else None
        avail = {g: v for g, v in grp.items() if v is not None}
        comp = None
        if len(avail) >= 2:
            w = sum(weights[g] for g in avail)
            comp = sum(weights[g] * v for g, v in avail.items()) / w
        out[s] = {"raw": raw[s], "pct": pct[s], "groups": grp, "composite": comp}
    comp_pct = percentiles({s: out[s]["composite"] for s in out})
    by_sym = {s.symbol: s for s in stocks}
    for s, o in out.items():
        cp = comp_pct[s]
        o["composite_pct"] = cp
        o["rank"] = None if cp is None else max(1, min(10, math.ceil(cp / 10) or 1))
        o["grades"] = {g: grade(v) for g, v in o["groups"].items()}
        o["label"] = (plain_label(o["groups"].get("quality"), o["groups"].get("value"), o["groups"].get("momentum"))
                      if o["rank"] is not None else "Insufficient data")
        drivers = [{"factor": k, "value": o["raw"].get(k), "pct": round(v)} for k, v in o["pct"].items()
                   if v is not None and o["raw"].get(k) is not None]
        drivers.sort(key=lambda d: abs(d["pct"] - 50), reverse=True)
        o["drivers"] = drivers[:4]
        st = by_sym[s]
        o["insufficient"] = [k for k, v in o["raw"].items() if v is None]
        o["price_as_of"] = st.price_as_of.isoformat() if st.price_as_of else None
        o["stale"] = st.stale
        o["fundamentals_retrieved_at"] = (st.snapshot.retrieved_at.isoformat()
                                          if st.snapshot is not None and getattr(st.snapshot, "retrieved_at", None)
                                          else None)
    return out


FACTOR_INFO = {
    "mom_12_1": ("momentum", "Return from 12 months ago to 1 month ago", "pct",
                 "how much the price rose or fell over the past year, leaving out the latest month"),
    "mom_6_1": ("momentum", "Return from 6 months ago to 1 month ago", "pct",
                "the same over the past half-year"),
    "high_52w": ("momentum", "Price ÷ 52-week high", "pct",
                 "how close the price is to its best level of the past year (100% = at the high)"),
    "vol_1y": ("safety", "1-year volatility of daily returns (annualised)", "pct",
               "how much the price swings day to day; lower is safer"),
    "quality_roe": ("quality", "Return on equity (ROE)", "num%", "profit earned per ₹100 of shareholders' money"),
    "quality_roce": ("quality", "Return on capital employed (ROCE)", "num%",
                     "profit earned per ₹100 of all capital, debt included"),
    "quality_cfo_pat": ("quality", "5-year cash from operations ÷ 5-year profit", "x",
                        "whether reported profit turns into cash (1.0× or more is healthy)"),
    "quality_de": ("quality", "Debt ÷ equity (latest year)", "x", "borrowing relative to shareholders' money; lower is safer"),
    "value_ep": ("value", "Earnings yield (1 ÷ P/E)", "pct", "profit per ₹100 of share price; higher is cheaper"),
    "value_bp": ("value", "Book value ÷ price", "x", "net assets per ₹1 of share price; higher is cheaper"),
}


def fmt_factor(k: str, v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    kind = FACTOR_INFO[k][2]
    return f"{v * 100:+.1f}%" if kind == "pct" and k.startswith("mom_") else (
        f"{v * 100:.1f}%" if kind == "pct" else f"{v:.1f}%" if kind == "num%" else f"{v:.2f}×")


def measures(o: dict) -> list[dict]:
    """Every input behind the rank, in plain words: value, percentile among FINN's stocks, and what it measures."""
    out = []
    for k, (group, label, _, meaning) in FACTOR_INFO.items():
        if k not in o["raw"]:
            continue
        p = o["pct"].get(k)
        out.append({"factor": k, "group": group, "label": label, "value": fmt_factor(k, o["raw"].get(k)),
                    "percentile": None if p is None else round(p), "meaning": meaning,
                    "reading": None if p is None else ("strong" if p >= 60 else "middling" if p >= 40 else "weak")})
    return out


GROUP_ORDER = [("momentum", "Momentum", "recent price trend"), ("quality", "Quality", "how profitable and sound the business is"),
               ("safety", "Safety", "how calm the price is"), ("value", "Value", "how cheap the share is for what it earns and owns")]


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def rank_reasons(o: dict, universe: int) -> list[str]:
    """Plain-English reasoning built from the numbers (no model): a lead sentence, then one line per group."""
    ms = measures(o)
    if o["rank"] is None:
        return ["Not enough data for a rank yet: " + ", ".join(m["label"] for m in ms if m["value"] is None)[:200] + "."]
    cp = round(o["composite_pct"])
    lines = [f"FINN Rank {o['rank']}/10: its weighted score is higher than {cp}% of the {universe} stocks FINN tracks."]
    graded = [(g, name, o["groups"].get(g)) for g, name, _ in GROUP_ORDER if o["groups"].get(g) is not None]
    best = max(graded, key=lambda x: x[2]) if graded else None
    worst = min(graded, key=lambda x: x[2]) if graded else None
    if best and worst and best[0] != worst[0]:
        lines[0] += f" Strongest: {best[1].lower()}. Weakest: {worst[1].lower()}."
    for g, name, what in GROUP_ORDER:
        gp = o["groups"].get(g)
        if gp is None:
            lines.append(f"{name} ({what}): no data.")
            continue
        word = "strong" if gp >= 60 else "average" if gp >= 40 else "weak"
        parts = [f"{m['label'][0].lower() + m['label'][1:]} {m['value']} ({_ord(m['percentile'])} percentile)" for m in ms
                 if m["group"] == g and m["value"] is not None and m["percentile"] is not None]
        lines.append(f"{name} is {word} — grade {grade(gp)}, {_ord(round(gp))} percentile ({what}): " + "; ".join(parts) + ".")
    return lines


_PLAIN = {"momentum": ("price trend", "stronger", "weaker"), "quality": ("business quality", "better", "worse"),
          "value": ("valuation", "cheaper", "pricier"), "safety": ("price stability", "steadier", "more volatile")}


def label_reason(o: dict) -> Optional[str]:
    """One plain sentence under the label: each group's verdict with its most telling measure, e.g.
    'Cheap: earnings yield 9.1% is cheaper than 85% of FINN's stocks. Weak business: ROE 7.2% is worse than 80%.'"""
    if o["rank"] is None:
        return None
    ms = [m for m in measures(o) if m["value"] is not None and m["percentile"] is not None]
    parts = []
    for g in ("quality", "value", "momentum", "safety"):
        gp = o["groups"].get(g)
        xs = [m for m in ms if m["group"] == g]
        if gp is None or not xs:
            continue
        m = max(xs, key=lambda m: abs(m["percentile"] - 50))
        what, good, bad = _PLAIN[g]
        verdict = "strong" if gp >= 60 else "weak" if gp < 40 else "average"
        share = lambda k: "all the other" if k >= 100 else f"{k}% of the"  # noqa: E731
        cmp = (f"{good} than {share(m['percentile'])}" if m["percentile"] >= 50 else f"{bad} than {share(100 - m['percentile'])}")
        parts.append(f"{what.capitalize()} is {verdict}: {m['label'][0].lower() + m['label'][1:]} {m['value']} is "
                     f"{cmp} stocks FINN tracks.")
    return " ".join(parts)


def rank_payload(symbol: str, o: dict, universe_size: int, as_of: Optional[str]) -> dict:
    r = lambda v: None if v is None else round(v, 1)  # noqa: E731
    return clean({
        "symbol": symbol, "as_of": as_of, "rank": o["rank"], "composite_pct": r(o["composite_pct"]),
        "grades": o["grades"], "groups": {g: r(v) for g, v in o["groups"].items()}, "label": o["label"],
        "drivers": [{**d, "value": None if d["value"] is None else round(d["value"], 4)} for d in o["drivers"]],
        "factors": {k: (None if v is None else round(v, 4)) for k, v in o["raw"].items()},
        "factor_pct": {k: (None if v is None else round(v)) for k, v in o["pct"].items()},
        "measures": measures(o),
        "reasons": rank_reasons(o, universe_size),
        "label_reason": label_reason(o),
        "data": {"price_as_of": o["price_as_of"], "fundamentals_retrieved_at": o["fundamentals_retrieved_at"],
                 "stale": o["stale"], "insufficient": o["insufficient"]},
        "universe_size": universe_size, "model_version": MODEL_VERSION, "caveat": RANK_CAVEAT,
        "weights": WEIGHTS,
    })


# ------------------------------------------------------------------ backtest (price-only, no look-ahead)
def _month_ends(dates: Sequence[date]) -> list[int]:
    idx = []
    for i in range(len(dates) - 1):
        if dates[i].month != dates[i + 1].month:
            idx.append(i)
    return idx


def _spearman(a: list[float], b: list[float]) -> Optional[float]:
    if len(a) < 3:
        return None
    ra = percentiles(dict(enumerate(a)))
    rb = percentiles(dict(enumerate(b)))
    x, y = [ra[i] for i in range(len(a))], [rb[i] for i in range(len(b))]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx == 0 or sy == 0:
        return None
    return sum((x[i] - mx) * (y[i] - my) for i in range(len(x))) / (sx * sy)


def _stats(monthly: list[float], rf: float = 0.065) -> dict:
    if not monthly:
        return {}
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in monthly:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    yrs = len(monthly) / 12
    cagr = eq ** (1 / yrs) - 1 if eq > 0 else -1.0
    mu = sum(monthly) / len(monthly)
    sd = math.sqrt(sum((r - mu) ** 2 for r in monthly) / max(1, len(monthly) - 1))
    vol = sd * math.sqrt(12)
    sharpe = (cagr - rf) / vol if vol > 0 else None
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd, "months": len(monthly)}


def backtest(series: dict[str, list[tuple[date, float]]], benchmark: Optional[list[tuple[date, float]]] = None,
             cost: float = 0.003, min_bars: int = 273) -> dict:
    """Monthly rebalance; at each month-end d, factors use only bars dated <= d; hold one month."""
    all_dates = sorted({d for s in series.values() for d, _ in s})
    if not all_dates:
        return {"ok": False, "reason": "no price history", "caveat": BACKTEST_CAVEAT}
    lookup = {s: dict(v) for s, v in series.items()}
    ordered = {s: sorted(v) for s, v in series.items()}
    bench = dict(benchmark or [])
    ends = _month_ends(all_dates)
    rows = []
    prev_top: set[str] = set()
    prev_bot: set[str] = set()
    for a, b in zip(ends, ends[1:]):
        d, d_next = all_dates[a], all_dates[b]
        inputs, fwd = [], {}
        for s, bars in ordered.items():
            hist = [c for dd, c in bars if dd <= d]
            if len(hist) < min_bars or d not in lookup[s] or d_next not in lookup[s]:
                continue
            assert max(dd for dd, _ in bars if dd <= d) <= d          # no look-ahead (c3_lookahead_assert)
            inputs.append(StockInputs(symbol=s, closes=hist))
            fwd[s] = lookup[s][d_next] / lookup[s][d] - 1
        if len(inputs) < 6:
            continue
        sc = score_universe(inputs, groups_used=("momentum", "safety"), weights=PRICE_WEIGHTS)
        ranked = sorted((s for s in sc if sc[s]["composite"] is not None), key=lambda s: sc[s]["composite"],
                        reverse=True)
        if len(ranked) < 6:
            continue
        k = len(ranked) // 3
        top, bot = set(ranked[:k]), set(ranked[-k:])
        t_cost = cost * (len(top - prev_top) / k if prev_top else 1.0)
        b_cost = cost * (len(bot - prev_bot) / k if prev_bot else 1.0)
        prev_top, prev_bot = top, bot
        r_top = sum(fwd[s] for s in top) / k - t_cost
        r_bot = sum(fwd[s] for s in bot) / k - b_cost
        r_ew = sum(fwd[s] for s in ranked) / len(ranked)
        r_b = bench[d_next] / bench[d] - 1 if d in bench and d_next in bench else None
        ic = _spearman([sc[s]["composite"] for s in ranked], [fwd[s] for s in ranked])
        rows.append({"date": d.isoformat(), "top": r_top, "bottom": r_bot, "equal": r_ew, "nifty50": r_b, "ic": ic,
                     "n": len(ranked)})
    if not rows:
        return {"ok": False, "reason": "not enough history (needs ~14 months for 6+ stocks)", "caveat": BACKTEST_CAVEAT}
    out = {"ok": True, "model_version": MODEL_VERSION, "weights": PRICE_WEIGHTS, "cost_per_rebalance": cost,
           "start": rows[0]["date"], "end": rows[-1]["date"], "months": len(rows),
           "portfolios": {p: _stats([r[p] for r in rows]) for p in ("top", "bottom", "equal")}}
    if all(r["nifty50"] is not None for r in rows):
        out["portfolios"]["nifty50"] = _stats([r["nifty50"] for r in rows])
        out["pct_months_top_beats_nifty"] = 100 * sum(r["top"] > r["nifty50"] for r in rows) / len(rows)
    ics = [r["ic"] for r in rows if r["ic"] is not None]
    out["mean_ic"] = sum(ics) / len(ics) if ics else None
    spread = out["portfolios"]["top"]["cagr"] - out["portfolios"]["bottom"]["cagr"]
    out["top_minus_bottom_cagr"] = spread
    pt, pb = out["portfolios"]["top"], out["portfolios"]["bottom"]
    if abs(spread) < 0.01:
        out["summary"] = ("On this small universe the top and bottom thirds by price signals earned similar returns"
                          + ("; the top third did so with lower volatility and a smaller worst fall"
                             if pt["vol"] < pb["vol"] and pt["max_drawdown"] > pb["max_drawdown"] else ""))
    elif spread < 0:
        out["summary"] = "On this small universe the price signals did not separate winners from losers"
    else:
        out["summary"] = "On this small universe, the top third by price signals beat the bottom third over the period"
    p = out["portfolios"]
    out["implausible"] = any(v.get("cagr", 0) > 0.8 or (v.get("sharpe") or 0) > 3 or v.get("max_drawdown") == 0
                             for v in p.values())
    out["monthly"] = rows
    out["caveat"] = BACKTEST_CAVEAT
    return clean(out)


# ------------------------------------------------------------------ red flags (text rules, no LLM)
_ROLE = re.compile(r"\b(ceo|md|cfo|managing director|chief executive officer|chief financial officer|"
                   r"whole[- ]time director)\b", re.I)
_REG = re.compile(r"sebi order|show cause|penalt|adjudicat|\bnclt\b|\bnclat\b|insolvency|\bcirp\b|enforcement "
                  r"directorate|search and seizure|income tax search|gst order|demand order", re.I)
_COURT = re.compile(r"high court|supreme court", re.I)
_NEG = re.compile(r"setting aside|set aside|sets aside|quashed|withdrawn|dismissed the petition|no penalty|"
                  r"in favour of the company|does not constitute|no impact", re.I)
_DEFAULT = re.compile(r"\bdefault|delay in payment|non-payment|invocation of pledge|one time settlement", re.I)
_DEFAULT_NEG = re.compile(r"\bno default|not defaulted|has not defaulted|no delay", re.I)
_PLEDGE = re.compile(r"pledge|encumbrance", re.I)
_RESULTS = re.compile(r"board meeting|intimation", re.I)
_RESULTS2 = re.compile(r"result", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                            "nov", "dec"])}


def parse_meeting_date(text: str) -> Optional[date]:
    """Day-first Indian dates: 12-11-2026, 12/11/2026, November 12, 2026, 12th November 2026, 12 Nov 2026, ISO."""
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text)
    if m:
        return _safe_date(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b", text)
    if m and m[2][:3].lower() in _MONTHS:
        return _safe_date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1]))
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", text)
    if m and m[1][:3].lower() in _MONTHS:
        return _safe_date(int(m[3]), _MONTHS[m[1][:3].lower()], int(m[2]))
    return None


def _safe_date(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def flag_for(text: str, category: Optional[str] = None, today: Optional[date] = None) -> Optional[tuple[str, str]]:
    """(flag_type, level) or None. First match wins, in the playbook's order. One flag per filing."""
    t = text or ""
    low = t.lower()
    if _DEFAULT.search(t) and not _DEFAULT_NEG.search(t):
        return "default", "red"
    if _REG.search(t):
        return ("regulator_litigation", "info") if _NEG.search(t) else ("regulator_litigation", "red")
    if "auditor" in low and ("resign" in low or "casual vacancy" in low):
        return "auditor_exit", "red"
    if re.search(r"resign|cessation|step(?:s|ped)? down", low) and _ROLE.search(t) and "independent director" not in low:
        return "top_exit", "red"
    if re.search(r"downgrad", low) and "rating" in low:
        return "rating_downgrade", "red"
    if _PLEDGE.search(t):
        return "pledge", "amber"
    if _RESULTS.search(t) and _RESULTS2.search(t):
        d = parse_meeting_date(t)
        if d and today and 0 <= (d - today).days <= 5:
            return "results_due", "amber"
        return None
    if _COURT.search(t):
        return "legal_event", "amber"
    return None


# ------------------------------------------------------------------ "why did it move" validation
_PCT = re.compile(r"[-+−]?\d+(?:\.\d+)?\s?%")
_RUPEE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d+)?)", re.I)
_NUM = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "").replace("−", "-")))
        except ValueError:
            pass
    return out


def validate_explanation(obj: object, source_ids: set[str], allowed: list[float], prices: list[float],
                         source_text: str) -> list[str]:
    """Returns a list of problems; empty means the explanation can be shown."""
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    errs = []
    summary = obj.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return ["missing summary"]
    if len(summary) > 600:
        errs.append("summary longer than 600 characters")
    cited = obj.get("cited_ids") or []
    if not isinstance(cited, list):
        errs.append("cited_ids is not a list")
        cited = []
    bad = [c for c in cited if c not in source_ids]
    if bad:
        errs.append(f"unknown cited ids: {bad[:3]}")
    note = obj.get("confidence_note")
    if note not in ("explained", "partly explained", "not explained"):
        errs.append("bad confidence_note")
    if note != "not explained" and not cited:
        errs.append("claims an explanation without citing a source")
    pool = [abs(x) for x in allowed] + [abs(x) for x in numbers_in(source_text)]
    for p in _PCT.findall(summary):
        v = abs(float(p.replace("%", "").replace("−", "-").strip()))
        if not any(abs(v - a) <= 0.15 for a in pool):
            errs.append(f"percentage {p} not in the facts or sources")
    src_nums = numbers_in(source_text)
    for r in _RUPEE.findall(summary):
        v = float(r.replace(",", ""))
        if not any(abs(v - p) <= 0.005 * p for p in prices if p) and not any(abs(v - n) < 1e-6 for n in src_nums):
            errs.append(f"rupee amount {r} not in the facts or sources")
    low = summary.lower()
    for ph in FORBIDDEN:
        if ph in low:
            errs.append(f"forbidden phrase: {ph}")
    return errs


def fallback_explanation(symbol: str, pct: Optional[float], vm: Optional[float]) -> dict:
    move = f"moved {pct:+.1f}%" if pct is not None else "moved"
    vol = f" on {vm:.1f}× normal volume" if vm is not None else ""
    return {"summary": f"{symbol} {move}{vol}. No filing or news in FINN explains it yet.", "cited_ids": [],
            "confidence_note": "not explained", "method": "fallback"}


def has_forbidden(text: str) -> list[str]:
    low = (text or "").lower().replace(REFUSAL.lower(), "")
    return [p for p in FORBIDDEN if p in low]


# ------------------------------------------------------------------ portfolio health (equal weights)
@dataclass
class HealthInputs:
    symbols: list[str]
    ranks: dict[str, dict]
    flags: list[dict]
    sectors: dict[str, Optional[str]]
    stale: list[str] = field(default_factory=list)


HEALTH_WEIGHTS = {"strength": 0.50, "filings": 0.20, "diversification": 0.15, "trend": 0.15}
HEALTH_FORMULA = ("Health = 50% Stock strength + 20% Filing risk + 15% Diversification + 15% Trend breadth, each "
                  "scored 0–100 over your current holdings, every holding weighted equally.")


def portfolio_health(h: HealthInputs) -> dict:
    """One fixed formula over the CURRENT holdings (equal weights: FINN stores no quantities).

    Stock strength   = average FINN Rank composite percentile of the ranked holdings.
    Filing risk      = 100 x (1 - (holdings with a red flag + 0.5 x holdings with only amber flags) / holdings).
    Diversification  = 100 x (1 - HHI) / (1 - 1/N), HHI = sum of squared sector shares (N = holdings).
    Trend breadth    = share of ranked holdings whose momentum percentile is 40 or more (not a weak trend).
    Percentiles are against FINN's fixed reference set of stocks, so removing a below-average holding raises
    Stock strength and adding an above-average one raises it; nothing else moves."""
    syms = list(h.symbols)
    n = len(syms)
    if n == 0:
        return {"ok": False, "reason": "no holdings"}
    ranked = [s for s in syms if h.ranks.get(s, {}).get("composite_pct") is not None]
    pending = [s for s in syms if s not in ranked]
    strength = sum(h.ranks[s]["composite_pct"] for s in ranked) / len(ranked) if ranked else None

    seen: dict[str, dict] = {}
    for f in h.flags:
        if f["symbol"] in syms:
            seen.setdefault(f["source_id"], f)            # one filing counts once
    red_syms = sorted({f["symbol"] for f in seen.values() if f["level"] == "red"})
    amber_syms = sorted({f["symbol"] for f in seen.values() if f["level"] == "amber"} - set(red_syms))
    filings = 100.0 * max(0.0, 1 - (len(red_syms) + 0.5 * len(amber_syms)) / n)

    sec: dict[str, int] = {}
    for s in syms:
        k = h.sectors.get(s) or "Unknown"
        sec[k] = sec.get(k, 0) + 1
    hhi = sum((c / n) ** 2 for c in sec.values())
    divers = 100.0 * (1 - hhi) / (1 - 1 / n) if n > 1 else 0.0

    mom = {s: h.ranks[s].get("groups", {}).get("momentum") for s in ranked}
    mom = {s: v for s, v in mom.items() if v is not None}
    weak = sorted((s for s, v in mom.items() if v < 40), key=lambda s: mom[s])
    trend = 100.0 * (len(mom) - len(weak)) / len(mom) if mom else None

    comps = {"strength": strength, "filings": filings, "diversification": divers, "trend": trend}
    avail = {k: v for k, v in comps.items() if v is not None}
    wsum = sum(HEALTH_WEIGHTS[k] for k in avail)
    score = sum(HEALTH_WEIGHTS[k] * v for k, v in avail.items()) / wsum if wsum else 0.0

    def fl(level):
        return [{"symbol": f["symbol"], "text": f.get("evidence", ""), "url": f.get("url"),
                 "type": f.get("flag_type", "").replace("_", " "), "date": (f.get("filed_at") or "")[:10]}
                for f in seen.values() if f["level"] == level]

    r1 = lambda v: None if v is None else round(v, 1)  # noqa: E731
    components = [
        {"key": "strength", "label": "Stock strength", "weight": 50, "value": r1(strength),
         "how": f"Average FINN Rank percentile of your {len(ranked)} ranked holding{'s' if len(ranked) != 1 else ''}"
                + (f" ({len(pending)} still loading history: {', '.join(pending[:5])})" if pending else ""),
         "items": [{"symbol": s, "text": f"FINN Rank {h.ranks[s]['rank']}/10 · {round(h.ranks[s]['composite_pct'])}th "
                                         "percentile"} for s in sorted(ranked, key=lambda s: h.ranks[s]["composite_pct"])]},
        {"key": "filings", "label": "Filing risk", "weight": 20, "value": r1(filings),
         "how": f"100 × (1 − (holdings with a red flag {len(red_syms)} + ½ × holdings with only amber flags "
                f"{len(amber_syms)}) ÷ {n} holdings). Red: defaults, regulator or court orders, auditor or CEO/CFO "
                "exits, rating downgrades. Amber: pledges, court judgments without a clear direction, results due "
                "within 5 days.",
         "items": fl("red") + fl("amber")},
        {"key": "diversification", "label": "Diversification", "weight": 15, "value": r1(divers),
         "how": f"100 × (1 − concentration) ÷ (1 − 1/{n}); concentration = sum of squared sector shares "
                f"({hhi:.2f}). 100 = every holding in a different sector.",
         "items": [{"symbol": "", "text": f"{k}: {v} holding{'s' if v != 1 else ''}"}
                   for k, v in sorted(sec.items(), key=lambda kv: -kv[1])[:6]]},
        {"key": "trend", "label": "Trend breadth", "weight": 15, "value": r1(trend),
         "how": "Share of ranked holdings whose price trend (FINN momentum percentile) is 40 or more. Weak trend = "
                "momentum below the 40th percentile, i.e. weaker than 60% of the stocks FINN tracks.",
         "items": [{"symbol": s, "text": f"momentum {round(mom[s])}th percentile (weak)"} for s in weak]},
    ]
    for c in components:
        c["contribution"] = None if c["value"] is None else round(HEALTH_WEIGHTS[c["key"]] * c["value"] / wsum, 1)
    return clean({"ok": True, "score": round(score), "formula": HEALTH_FORMULA, "components": components,
                  "holdings": n, "ranked": len(ranked), "pending": pending, "weighting": "equal",
                  "sectors": dict(sorted(sec.items(), key=lambda kv: -kv[1])),
                  "red_flags": fl("red"), "amber_flags": fl("amber"),
                  "note": "Every holding counts equally: FINN doesn't know how much of each stock you hold.",
                  "caveat": RANK_CAVEAT})


def window_days(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)

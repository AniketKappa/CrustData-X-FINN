"""Decision support: parsing, factors, guards, scoring, backtest, flags, explanation validation, health.
Playbook checks C3/C4 as unit tests (synthetic data only; no network)."""
import json
import math
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from finn.decision import (FORBIDDEN, HealthInputs, StockInputs, backtest, clean, flag_for, fundamental_factors,
                           grade, parse_meeting_date, parse_num, percentiles, portfolio_health, price_factors,
                           score_universe, validate_explanation, fallback_explanation)
from finn.providers.prices import yf_window
from finn.providers.screener import Table


# ---------------------------------------------------------------- B1
def test_yf_window_ends_tomorrow_ist():
    # 23:00 UTC on 5 Nov is already 6 Nov in India; end must be the 7th (Yahoo's end is exclusive).
    start, end = yf_window(10, datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc))
    assert (start, end) == ("2026-10-27", "2026-11-07")


# ---------------------------------------------------------------- parsing
@pytest.mark.parametrize("s,v", [("₹ 4,74,227 Cr.", 474227), ("31.9 %", 31.9), ("−5.0%", -5.0), ("–3.2", -3.2),
                                 ("(10.2)", -10.2), ("1,08,247", 108247), ("1.2 Lakh", 120000), ("abc", None)])
def test_parse_num(s, v):
    assert parse_num(s) == (None if v is None else pytest.approx(v))


# ---------------------------------------------------------------- price factors (Appendix F)
def test_flat_then_jump():
    f = price_factors([100.0] * 300 + [110.0] * 21)
    assert f["mom_12_1"] == pytest.approx(0.0, abs=1e-9)
    assert f["high_52w"] == pytest.approx(1.0, abs=1e-9)
    assert 0 < f["vol_1y"] < 0.2


def test_linear_up_and_crash():
    up = price_factors([100 * 1.001 ** k for k in range(400)])
    assert up["mom_12_1"] == pytest.approx(1.001 ** 231 - 1, abs=1e-9)
    assert up["high_52w"] == pytest.approx(1.0, abs=1e-9)
    assert up["vol_1y"] == pytest.approx(0.0, abs=1e-9)
    crash = price_factors([100.0] * 300 + [50.0] * 10)
    assert crash["high_52w"] == pytest.approx(0.5)
    assert crash["vol_1y"] > up["vol_1y"]


def test_short_history_gates():
    f = price_factors([100.0] * 200)
    assert f["mom_12_1"] is None and f["high_52w"] is None and f["vol_1y"] is None and f["mom_6_1"] is not None


# ---------------------------------------------------------------- fundamentals guards
def _snap(pat, cfo, eq=10.0, res=90.0, bor=50.0, ratios=None):
    per = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "TTM"]
    return SimpleNamespace(
        ratios=ratios or [("ROE", "20 %"), ("ROCE", "25 %"), ("Stock P/E", "25"), ("Book Value", "100"),
                          ("Current Price", "500")],
        annual=Table(periods=per, rows={"net profit": pat + [999.0]}),
        cashflow=Table(periods=per[:-1], rows={"cash from operating activity": cfo}),
        balance=Table(periods=per[:-1], rows={"borrowings": [bor] * 5, "equity capital": [eq] * 5,
                                              "reserves": [res] * 5}),
        retrieved_at=datetime(2026, 11, 5, tzinfo=timezone.utc))


def test_cfo_pat_guards():
    f, _ = fundamental_factors(_snap([-10.0] * 5, [-20.0] * 5), False)
    assert f["quality_cfo_pat"] is None                    # loss-maker: negative/negative must not look excellent
    f, _ = fundamental_factors(_snap([10.0] * 5, [-1.0] * 5), False)
    assert f["quality_cfo_pat"] == 0.0
    f, _ = fundamental_factors(_snap([10.0] * 5, [12.0] * 5), False)
    assert f["quality_cfo_pat"] == pytest.approx(1.2)      # TTM (999) excluded
    assert f["value_ep"] == pytest.approx(0.04) and f["value_bp"] == pytest.approx(0.2)
    assert f["quality_de"] == pytest.approx(0.5)


def test_negative_net_worth_forces_worst_leverage():
    f, g = fundamental_factors(_snap([10.0] * 5, [12.0] * 5, eq=10.0, res=-50.0), False)
    assert g["negative_equity"] and f["quality_de"] is None and f["value_bp"] is None
    stocks = [StockInputs(symbol=f"S{i}", closes=[100.0 + i] * 300, snapshot=_snap([10.0] * 5, [12.0] * 5,
                                                                                    bor=10.0 * i)) for i in range(5)]
    stocks.append(StockInputs(symbol="NEG", closes=[100.0] * 300, snapshot=_snap([10.0] * 5, [12.0] * 5, res=-50.0)))
    sc = score_universe(stocks)
    assert sc["NEG"]["pct"]["quality_de"] == 0.0


def test_lender_skips_leverage_and_cash_conversion():
    f, _ = fundamental_factors(_snap([10.0] * 5, [12.0] * 5), True)
    assert f["quality_de"] is None and f["quality_cfo_pat"] is None and f["quality_roe"] == 20.0


# ---------------------------------------------------------------- scoring
def _walk(n, drift, wob, seed):
    out, c = [], 100.0
    for i in range(n):
        c *= 1 + drift + wob * math.sin(i * (0.7 + seed / 10))
        out.append(c)
    return out


def test_scoring_ranges_and_direction():
    stocks = [StockInputs(symbol=f"S{i}", closes=_walk(320, 0.0005 * (i - 5), 0.002 * (1 + i % 4), i))
              for i in range(12)]
    sc = score_universe(stocks)
    for o in sc.values():
        assert o["rank"] in range(1, 11)
        assert 0 <= o["composite_pct"] <= 100
        assert set(o["grades"].values()) <= {"A", "B", "C", "D", "F", "—"}
    best_mom = max(sc, key=lambda s: sc[s]["raw"]["mom_12_1"])
    worst_vol = max(sc, key=lambda s: sc[s]["raw"]["vol_1y"])
    assert sc[best_mom]["grades"]["momentum"] in ("A", "B")
    assert sc[worst_vol]["grades"]["safety"] in ("D", "F")
    json.loads(json.dumps(clean(sc)), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_insufficient_groups_gives_no_rank():
    sc = score_universe([StockInputs(symbol="A", closes=[100.0] * 50), StockInputs(symbol="B", closes=[101.0] * 50)])
    assert sc["A"]["rank"] is None and sc["A"]["label"] == "Insufficient data"


def test_percentiles_and_grades():
    p = percentiles({"a": 1.0, "b": 2.0, "c": 3.0, "d": None})
    assert p == {"a": 0.0, "b": 50.0, "c": 100.0, "d": None}
    assert percentiles({"a": 1.0, "b": 2.0}, lower_better=True) == {"a": 100.0, "b": 0.0}
    assert [grade(x) for x in (95, 70, 50, 30, 5, None)] == ["A", "B", "C", "D", "F", "—"]


# ---------------------------------------------------------------- backtest
def _series(n_stocks=9, days=900):
    start = date(2022, 1, 3)
    dates = []
    d = start
    while len(dates) < days:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return {f"S{i}": list(zip(dates, _walk(days, 0.0003 * (i - 4), 0.004 * (1 + i % 3), i))) for i in range(n_stocks)}, dates


def test_backtest_runs_and_is_consistent():
    series, dates = _series()
    bench = list(zip(dates, _walk(len(dates), 0.0003, 0.003, 99)))
    res = backtest(series, bench)
    assert res["ok"] and res["months"] >= 20 and "survivorship" in res["caveat"]
    assert isinstance(res["implausible"], bool)   # synthetic trends are deliberately extreme
    lookup = {s: dict(v) for s, v in series.items()}
    row = res["monthly"][3]
    d = date.fromisoformat(row["date"])
    nxt = date.fromisoformat(res["monthly"][4]["date"])
    ew = sum(lookup[s][nxt] / lookup[s][d] - 1 for s in lookup) / len(lookup)
    assert row["equal"] == pytest.approx(ew, abs=1e-9)        # equal-weight = mean of constituents
    b = dict(bench)
    nifty = (b[nxt] / b[d] - 1)
    assert row["nifty50"] == pytest.approx(nifty, abs=1e-9)


def test_backtest_has_no_lookahead():
    """Changing prices AFTER a rebalance date must not change that date's portfolio return inputs."""
    series, _ = _series()
    a = backtest(series)
    cut = date.fromisoformat(a["monthly"][5]["date"])
    tampered = {s: [(d, c * (3 if d > cut + timedelta(days=40) else 1)) for d, c in v] for s, v in series.items()}
    b = backtest(tampered)
    assert [r["top"] for r in a["monthly"][:5]] == [r["top"] for r in b["monthly"][:5]]


def test_backtest_needs_history():
    series, _ = _series(days=200)
    assert backtest(series)["ok"] is False


# ---------------------------------------------------------------- flags (Appendix E)
TODAY = date(2026, 11, 8)
FLAG_CASES = [
    ("Credit Rating — CRISIL downgrades long-term rating to AA- from AA", "rating_downgrade"),
    ("Credit Rating — ICRA reaffirms rating at AAA (Stable)", None),
    ("Announcement under Regulation 30 (LODR) — Resignation of Chief Financial Officer", "top_exit"),
    ("Appointment of Independent Director", None),
    ("Resignation of Statutory Auditors", "auditor_exit"),
    ("Receipt of Show Cause Notice from SEBI", "regulator_litigation"),
    ("Order passed by NCLT admitting insolvency petition", "regulator_litigation"),
    ("Disclosure of delay in payment of interest on NCDs", "default"),
    ("Disclosure under Reg 31(1) SAST — creation of encumbrance by promoter", "pledge"),
    ("Board Meeting Intimation for Financial Results on 12-11-2026", "results_due"),
    ("Financial Results For The Quarter Ended September 30, 2026", None),
    ("Press Release — Commissioning of 300 MW solar project", None),
    ("Income tax search at company premises", "regulator_litigation"),
    ("Intimation of penalty imposed by stock exchange for delayed filing", "regulator_litigation"),
    ("Cessation of Managing Director due to completion of tenure", "top_exit"),
    ("Transcript of Earnings Call", None),
    ("Invocation of pledged shares by lender", "default"),
    ("Change in Company Secretary", None),
    ("Allotment of ESOP shares", None),
    ("Board Meeting on November 10, 2026 to consider Q2 results", "results_due"),
    ("Corporate Insolvency Resolution Process — Order passed by NCLAT setting aside the order of NCLT", "info"),
    ("Clarification: no default has occurred on any borrowing", None),
    ("Credit rating reaffirmed at CARE AA+ (Stable)", None),
    ("Appointment of Chief Financial Officer", None),
    ("Resignation of Independent Director due to pre-occupation", None),
    ("Receipt of GST Order — demand of ₹4.2 crore", "regulator_litigation"),
    ("Outcome of Supreme Court hearing on AT-1 bonds write-off", "legal_event"),
]


def test_flag_rules_appendix_e():
    correct, false_red = 0, []
    for text, want in FLAG_CASES:
        got = flag_for(text, None, TODAY)
        kind = None if got is None else ("info" if got[1] == "info" else got[0])
        correct += kind == want
        if want in (None, "info") and got and got[1] == "red":
            false_red.append(text)
    assert not false_red
    assert correct == len(FLAG_CASES)


@pytest.mark.parametrize("s", ["12-11-2026", "12/11/2026", "November 12, 2026", "12th November 2026", "12 Nov 2026",
                               "2026-11-12"])
def test_meeting_dates_day_first(s):
    assert parse_meeting_date(f"Board meeting on {s}") == date(2026, 11, 12)


# ---------------------------------------------------------------- why-moved validation
def test_explanation_validation():
    ids, allowed, prices = {"BSE:1"}, [-1.73, 2.4], [1500.0, 1526.4]
    src = "Q2 results: revenue up 18% YoY"
    ok = {"summary": "The stock fell 1.7% after results showed revenue up 18% (reported).", "cited_ids": ["BSE:1"],
          "confidence_note": "partly explained"}
    assert validate_explanation(ok, ids, allowed, prices, src) == []
    bad_pct = {**ok, "summary": "The stock fell 4.5% after results."}
    assert any("4.5%" in e for e in validate_explanation(bad_pct, ids, allowed, prices, src))
    bad_id = {**ok, "cited_ids": ["BSE:404"]}
    assert validate_explanation(bad_id, ids, allowed, prices, src)
    uncited = {**ok, "cited_ids": []}
    assert validate_explanation(uncited, ids, allowed, prices, src)
    rupee = {**ok, "summary": "It closed at ₹1,500 after results."}
    assert validate_explanation(rupee, ids, allowed, prices, src) == []
    rupee_bad = {**ok, "summary": "It closed at ₹1,800 after results."}
    assert validate_explanation(rupee_bad, ids, allowed, prices, src)
    for ph in ("price target", "will rise"):
        assert validate_explanation({**ok, "summary": f"Analysts say it {ph}."}, ids, allowed, prices, src)
    assert validate_explanation("nope", ids, allowed, prices, src)


def test_fallback_text():
    f = fallback_explanation("INFY", -3.21, 2.5)
    assert f["summary"] == "INFY moved -3.2% on 2.5× normal volume. No filing or news in FINN explains it yet."
    assert f["confidence_note"] == "not explained" and f["cited_ids"] == []
    assert all(p not in f["summary"].lower() for p in FORBIDDEN)


# ---------------------------------------------------------------- portfolio health
def _hin(symbols, comp, mom=None, flags=(), sectors=None):
    ranks = {s: {"composite_pct": comp[s], "rank": 5, "absolute": {"overall": comp[s]},
                 "groups": {"momentum": (mom or {}).get(s, 50.0)}} for s in comp}
    return HealthInputs(symbols=symbols, ranks=ranks, flags=list(flags),
                        sectors=sectors or {s: f"Sector {i}" for i, s in enumerate(symbols)})


def test_health_fixed_formula():
    h = portfolio_health(_hin(["A", "B", "C", "D"], {"A": 80.0, "B": 60.0, "C": 40.0, "D": 20.0},
                              mom={"D": 10.0}, flags=[{"symbol": "A", "level": "red", "source_id": "x"},
                                                      {"symbol": "A", "level": "red", "source_id": "x"},
                                                      {"symbol": "B", "level": "amber", "source_id": "y"}]))
    c = {x["key"]: x["value"] for x in h["components"]}
    assert c["strength"] == 50.0                                   # mean of 80, 60, 40, 20
    assert c["filings"] == pytest.approx(100 * (1 - (1 + 0.5) / 4), abs=0.1)
    assert c["diversification"] == 100.0                           # four different sectors
    assert c["trend"] == 75.0                                      # D is weak
    assert h["score"] == round(0.5 * 50 + 0.2 * 62.5 + 0.15 * 100 + 0.15 * 75)
    assert len(h["red_flags"]) == 1                                # the same filing counts once


def test_health_moves_the_right_way():
    base = {"A": 80.0, "B": 60.0, "C": 30.0}
    with_c = portfolio_health(_hin(["A", "B", "C"], base))["score"]
    without_c = portfolio_health(_hin(["A", "B"], base))["score"]
    with_strong = portfolio_health(_hin(["A", "B", "C", "E"], {**base, "E": 95.0}))["score"]
    assert without_c > with_c                                      # removing a below-average holding raises it
    assert with_strong > with_c                                    # adding an above-average holding raises it
    again = portfolio_health(_hin(["A", "B", "C"], base))["score"]
    assert again == with_c                                         # remove then add back: same score

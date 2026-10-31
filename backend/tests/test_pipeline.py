import httpx
import pytest

from finn.factory import build_pipeline
from finn.http import HttpClient, HttpPolicy
from finn.models import AlertThresholds, Availability
from finn.providers.announcements import NseJsonSource
from finn.providers.prices import PriceProviderError


def titles(items):
    return [(i.symbol, i.category) for i in items]


def test_default_window_is_24h_and_tiers(pipe):
    d = pipe.digest()
    assert d.window_hours == 24 and d.fixture
    assert ("FXCABLES", "results") in titles(d.high)
    assert ("FXPHARMA", "management_change") in titles(d.high)
    assert {i.symbol for i in d.high if i.kind == "market_alert"} == {"FXCABLES", "FXPHARMA", "FXPOWER"}
    assert d.routine_count == len(d.routine) == 2
    assert all(i.tier == "routine" for i in d.routine)


def test_windows_include_older_items(pipe):
    ids = lambda d: {i.id for i in d.high + d.normal + d.routine}  # noqa: E731
    d24, d72, d168 = pipe.digest(24), pipe.digest(72), pipe.digest(168)
    assert ids(d24) < ids(d72) < ids(d168)
    assert ("FXCABLES", "M&A") in titles(d168.high) and ("FXCABLES", "M&A") not in titles(d72.high + d72.normal)


def test_invalid_window_rejected(pipe):
    with pytest.raises(ValueError):
        pipe.digest(5)


def test_original_subject_and_link_preserved(pipe):
    item = next(i for i in pipe.digest().high if i.category == "results")
    assert item.title == "Outcome of Board Meeting" == item.announcement.subject
    assert item.source_url.endswith(".pdf") and item.summary is None


def test_dedup_rss_json_and_cross_exchange(pipe):
    d = pipe.digest()
    results = [i for i in d.high + d.normal if i.symbol == "FXCABLES" and i.category == "results"]
    assert len(results) == 1                          # RSS + JSON same attachment -> one record
    cfo = [i for i in d.high if i.symbol == "FXPHARMA" and i.category == "management_change"]
    assert len(cfo) == 1 and cfo[0].announcement.exchange == "NSE"   # NSE and BSE copies collapsed
    rep = pipe.refresh_announcements(force=True)
    assert rep.new_announcements == 0                 # re-ingesting adds nothing


def test_non_portfolio_items_excluded_by_default(pipe):
    assert all(i.symbol for i in pipe.digest().high + pipe.digest().normal)
    assert any(i.symbol is None for i in pipe.digest(include_non_portfolio=True).normal +
               pipe.digest(include_non_portfolio=True).high)


def test_thresholds_from_request_change_alerts(pipe):
    strict = AlertThresholds(pct_change_abs=7, volume_multiple=3.0)
    alerts = [i.symbol for i in pipe.digest(thresholds=strict).high if i.kind == "market_alert"]
    assert alerts == ["FXCABLES"]                     # 3.1x volume only


def test_market_disclosures(pipe):
    sig = {s.symbol: s for s in pipe.market_signals(pipe.s.thresholds)}
    assert sig["FXHALTED"].availability == Availability.STALE
    assert sig["FXGONE"].availability == Availability.NO_DATA
    assert sig["FXBROKEN"].availability == Availability.PROVIDER_ERROR
    assert sig["FXNEWCO"].availability == Availability.INSUFFICIENT_HISTORY
    text = " ".join(pipe.digest().disclosures)
    for s in ("FXHALTED", "FXGONE", "FXBROKEN", "FXNEWCO", "Fixture mode"):
        assert s in text


def test_price_cache_prevents_refetch():
    p = build_pipeline("fixture")
    calls = []
    orig = p.prices.fetch
    p.prices.fetch = lambda inst, days: calls.append(inst.key) or orig(inst, days)
    p.refresh_prices()
    n = len(calls)
    rep = p.refresh_prices()
    assert len(calls) == n                                          # nothing re-fetched inside the TTL
    assert len(rep.skipped_fresh) == n - 2 and len(rep.skipped_backoff) == 2   # FXGONE, FXBROKEN in failure backoff
    p.refresh_prices(force=True)
    assert len(calls) == 2 * n


def test_provider_failure_falls_back_to_cached_bars():
    p = build_pipeline("fixture")
    p.refresh_prices()

    def boom(inst, days):
        raise PriceProviderError("error", "simulated timeout")
    p.prices.fetch = boom
    p.refresh_prices(["FXTUBES"], force=True)
    s = {x.symbol: x for x in p.market_signals(p.s.thresholds)}["FXTUBES"]
    assert s.close is not None and any("cached prices" in n for n in s.notes)


def test_digest_makes_no_network_calls(pipe):
    pipe.prices.fetch = lambda *a: pytest.fail("digest must not fetch prices")
    for src in (pipe.nse_rss, pipe.bse_rss):
        src.fetch = lambda *a: pytest.fail("digest must not fetch announcements")
    pipe.nse_json.fetch_symbol = lambda *a: pytest.fail("digest must not fetch announcements")
    pipe.digest()
    pipe.market_signals(pipe.s.thresholds)


def test_announcement_ttl_cache(pipe):
    rep = pipe.refresh_announcements()
    assert not rep.fetched and rep.skipped_fresh


def test_nse_json_schema_change_stops_run_and_is_reported():
    p = build_pipeline("fixture")
    calls = []

    def h(req):
        calls.append(str(req.url))
        if "api" in str(req.url):
            return httpx.Response(200, json={"error": "changed"})
        return httpx.Response(200, text="home")
    http = HttpClient(HttpPolicy(min_delay_seconds=0, max_retries=0), transport=httpx.MockTransport(h))
    p.nse_json = NseJsonSource(http, "https://h.invalid/", "https://h.invalid/api?symbol={symbol}", p.clock)
    rep = p.refresh_announcements()
    assert sum("api" in c for c in calls) == 1        # stopped after the first schema failure
    st = {s.name: s for s in p.source_status()}["nse_json"]
    assert st.status in ("failed", "degraded") and "schema" in st.last_error


def test_source_failure_is_disclosed_not_raised():
    p = build_pipeline("fixture")
    http = HttpClient(HttpPolicy(min_delay_seconds=0, max_retries=1),
                      transport=httpx.MockTransport(lambda r: httpx.Response(503)), sleep=lambda s: None)
    p.nse_rss.http = http
    p.refresh_announcements()
    d = p.digest()
    assert any("nse_rss" in x and ("failed" in x or "degraded" in x) for x in d.disclosures)


def test_fetch_parallel_keeps_order_and_returns_errors():
    import time
    from finn.pipeline import fetch_parallel
    calls = [(i, (lambda i=i: (time.sleep(0.05), i * 2)[1] if i != 3 else 1 / 0)) for i in range(6)]
    t0 = time.monotonic()
    out = fetch_parallel(calls, workers=6)
    assert time.monotonic() - t0 < 0.2                              # ran concurrently, not 6 x 0.05 s
    assert [k for k, _ in out] == list(range(6)) and out[2][1] == 4 and isinstance(out[3][1], ZeroDivisionError)


def test_polite_spacing_holds_across_threads():
    import threading
    from finn.http import HttpClient, HttpPolicy
    slept = []
    clock = [0.0]
    h = HttpClient(HttpPolicy(min_delay_seconds=0.5), sleep=lambda s: slept.append(round(s, 2)), clock=lambda: clock[0])
    ts = [threading.Thread(target=h._polite_wait, args=("https://same.invalid/x",)) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]                  # noqa: E702
    assert sorted(slept) == [0.5, 1.0, 1.5]                          # one host: requests spaced, never bunched


def test_batched_prices_split_per_symbol():
    import pandas as pd
    from finn.providers.prices import YFinanceProvider, fetch_many_yf
    from finn.symbols import normalize
    idx = pd.to_datetime(["2026-10-28", "2026-10-29"])
    cols = pd.MultiIndex.from_product([["AAA.NS", "BBB.NS"], ["Open", "High", "Low", "Close", "Volume"]])
    frame = pd.DataFrame([[1, 1, 1, 10, 100, 2, 2, 2, 20, 200], [1, 1, 1, 11, 110, 2, 2, 2, 21, 210]], index=idx, columns=cols)
    prov = YFinanceProvider(fetch_frame=lambda *a: (_ for _ in ()).throw(RuntimeError("no data found")), retries=0)
    out = fetch_many_yf(prov, [normalize("AAA"), normalize("BBB"), normalize("CCC")], 30, download=lambda *a: frame)
    assert [b.close for b in out["NSE:AAA"]] == [10, 11] and [b.close for b in out["NSE:BBB"]] == [20, 21]
    assert out["NSE:CCC"].kind == "no_data"                          # missing symbol -> its own error, others fine

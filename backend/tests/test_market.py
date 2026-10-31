from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from finn.market import session_alerts, compute_signal, evaluate_alert, expected_session
from finn.models import AlertThresholds, Availability, PriceBar, Provenance, SourceClass

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)          # Thursday evening
TH = AlertThresholds(pct_change_abs=5.0, volume_multiple=2.0, lookback_sessions=20, min_history_sessions=10)


def bars(closes, vols, end=date(2026, 10, 29)):
    ds, d = [], end
    while len(ds) < len(closes):
        if d.weekday() < 5:
            ds.append(d)
        d -= timedelta(days=1)
    ds.reverse()
    prov = lambda d: Provenance(source_class=SourceClass.MARKET_DATA, source_name="test", retrieved_at=NOW, data_date=d)  # noqa: E731
    return [PriceBar(instrument_key="NSE:T", date=d, close=c, volume=v, provenance=prov(d)) for d, c, v in zip(ds, closes, vols)]


def sig(closes, vols, th=TH, now=NOW):
    return compute_signal("T", "NSE:T", bars(closes, vols), th, now)


def series(last_close, last_vol, n=21):
    return [100.0] * (n - 1) + [last_close], [1000.0] * (n - 1) + [last_vol]


# ---- price threshold boundaries ----
@pytest.mark.parametrize("close,fires", [(105.0, True), (95.0, True), (104.99, False), (95.01, False), (110, True)])
def test_price_boundary(close, fires):
    s = sig(*series(close, 1000.0))
    al = evaluate_alert(s, TH)
    assert (al is not None and "price" in al.rules) is fires


# ---- volume threshold boundaries ----
@pytest.mark.parametrize("vol,fires", [(2000.0, True), (1999.99, False), (5000.0, True)])
def test_volume_boundary(vol, fires):
    s = sig(*series(100.0, vol))
    assert s.volume_multiple == pytest.approx(vol / 1000)
    al = evaluate_alert(s, TH)
    assert (al is not None and "volume" in al.rules) is fires


def test_configurable_thresholds_change_outcome():
    s = sig(*series(103.0, 2500.0))
    assert evaluate_alert(s, TH).rules == ["volume"]
    assert evaluate_alert(s, AlertThresholds(pct_change_abs=3, volume_multiple=3)).rules == ["price"]
    assert evaluate_alert(s, AlertThresholds(pct_change_abs=4, volume_multiple=3)) is None


def test_lookback_excludes_latest_and_respects_n():
    closes = [100.0] * 30
    vols = [5000.0] * 9 + [1000.0] * 20 + [2000.0]
    s = sig(closes, vols)
    assert s.lookback_used == 20 and s.avg_volume == 1000.0 and s.volume_multiple == 2.0


def test_insufficient_history_disables_volume_only():
    s = sig([100, 100, 100, 106], [1, 1, 1, 9])
    assert s.availability == Availability.INSUFFICIENT_HISTORY and s.volume_multiple is None
    assert evaluate_alert(s, TH).rules == ["price"]
    assert any("prior sessions" in n for n in s.notes)


def test_single_bar_no_change():
    s = sig([100.0], [10.0])
    assert s.pct_change is None and evaluate_alert(s, TH) is None


def test_zero_volume_sessions_excluded():
    closes, vols = series(100.0, 2000.0, n=21)
    vols[3] = 0.0
    s = sig(closes, vols)
    assert s.lookback_used == 19 and any("zero-volume" in n for n in s.notes)


def test_stale_data_is_flagged_and_never_alerts():
    b = bars(*series(120.0, 9000.0), end=date(2026, 10, 22))
    s = compute_signal("T", "NSE:T", b, TH, NOW)
    assert s.availability == Availability.STALE and evaluate_alert(s, TH) is None
    assert "trading days behind" in " ".join(s.notes)


def test_open_session_shows_todays_price_so_far():
    morning = datetime(2026, 10, 29, 11, 0, tzinfo=IST)
    s = compute_signal("T", "NSE:T", bars(*series(150.0, 9000.0)), TH, morning)
    assert s.as_of == date(2026, 10, 29) and s.live and round(s.pct_change) == 50
    assert s.volume_multiple is None and any("after the close" in n for n in s.notes)   # part-day volume not compared
    al = evaluate_alert(s, TH)
    assert al is not None and al.live and al.rules == ["price"] and "so far today" in al.explanation
    assert s.availability == Availability.OK


def test_window_changes_and_per_session_alerts():
    closes = [100.0] * 18 + [110.0, 110.0, 99.0]          # +10% three sessions ago, -10% today
    vols = [1000.0] * 21
    b = bars(closes, vols)
    s = compute_signal("T", "NSE:T", b, TH, NOW)
    assert round(s.changes["1"]) == -10 and round(s.changes["3"]) == -1 and round(s.changes["5"]) == -1
    one = session_alerts("T", "NSE:T", b, TH, NOW, 1)
    five = session_alerts("T", "NSE:T", b, TH, NOW, 5)
    assert [a.date for a, _ in one] == [date(2026, 10, 29)]
    assert [a.date for a, _ in five] == [date(2026, 10, 29), date(2026, 10, 27)]
    assert five[1][0].close == 110.0 and five[1][0].prev_close == 100.0


def test_empty_bars_no_data():
    s = compute_signal("T", "NSE:T", [], TH, NOW)
    assert s.availability == Availability.NO_DATA and evaluate_alert(s, TH) is None


def test_expected_session_weekend_and_before_close():
    assert expected_session(datetime(2026, 11, 1, 12, 0, tzinfo=IST)) == date(2026, 10, 30)   # Sunday -> Friday
    assert expected_session(datetime(2026, 11, 2, 10, 0, tzinfo=IST)) == date(2026, 10, 30)   # Monday morning
    assert expected_session(datetime(2026, 11, 2, 16, 1, tzinfo=IST)) == date(2026, 11, 2)


def test_alert_key_is_stable():
    s = sig(*series(106.0, 1000.0))
    assert evaluate_alert(s, TH).key == evaluate_alert(s, TH).key


def test_thresholds_validated():
    with pytest.raises(ValueError):
        AlertThresholds(pct_change_abs=0)
    with pytest.raises(ValueError):
        AlertThresholds(volume_multiple=1.0)

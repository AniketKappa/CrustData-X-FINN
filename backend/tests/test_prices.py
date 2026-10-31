import math
from datetime import date

import pandas as pd
import pytest

from finn.providers.prices import FixturePriceProvider, PriceProviderError, YFinanceProvider, frame_to_bars
from finn.symbols import normalize

INST = normalize("INFY")


def frame(rows):
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="Asia/Kolkata") for d, *_ in rows])
    return pd.DataFrame([{"Open": c, "High": c, "Low": c, "Close": c, "Volume": v} for _, c, v in rows], index=idx)


def test_frame_to_bars_keeps_provenance_and_skips_gaps():
    f = frame([("2026-10-27", 100.0, 10), ("2026-10-28", math.nan, 11), ("2026-10-29", 102.0, 12)])
    bars = frame_to_bars(f, INST, "yfinance")
    assert [b.date for b in bars] == [date(2026, 10, 27), date(2026, 10, 29)]     # NaN close skipped, not interpolated
    p = bars[-1].provenance
    assert p.source_name == "yfinance" and p.data_date == date(2026, 10, 29) and p.retrieved_at.tzinfo
    assert "INFY.NS" in p.url


def test_empty_frame_is_no_data():
    with pytest.raises(PriceProviderError) as e:
        frame_to_bars(pd.DataFrame(), INST, "yfinance")
    assert e.value.kind == "no_data"


def test_unexpected_columns_is_error():
    with pytest.raises(PriceProviderError) as e:
        frame_to_bars(pd.DataFrame({"x": [1]}, index=pd.DatetimeIndex(["2026-10-29"])), INST, "yfinance")
    assert e.value.kind == "error"


def test_yfinance_delisted_message_maps_to_no_data_without_retry():
    calls = []

    def fetch(sym, days, timeout):
        calls.append(sym)
        raise RuntimeError("$XYZ.NS: possibly delisted; no price data found")
    with pytest.raises(PriceProviderError) as e:
        YFinanceProvider(fetch, retries=2, sleep=lambda s: None).fetch(normalize("XYZ"), 30)
    assert e.value.kind == "no_data" and len(calls) == 1


def test_yfinance_transient_error_bounded_retry():
    calls = []

    def fetch(sym, days, timeout):
        calls.append(timeout)
        raise TimeoutError("read timed out")
    with pytest.raises(PriceProviderError) as e:
        YFinanceProvider(fetch, timeout=7, retries=1, sleep=lambda s: None).fetch(INST, 30)
    assert e.value.kind == "error" and calls == [7, 7]


def test_yfinance_success_and_bse_suffix():
    seen = []

    def fetch(sym, days, timeout):
        seen.append(sym)
        return frame([("2026-10-28", 10.0, 5), ("2026-10-29", 11.0, 6)])
    bars = YFinanceProvider(fetch).fetch(normalize("500209"), 30)
    assert seen == ["500209.BO"] and bars[-1].instrument_key == "BSE:500209"


def test_fixture_provider_is_deterministic_and_labelled():
    p = FixturePriceProvider(date(2026, 10, 29))
    a, b = p.fetch(normalize("FXTUBES"), 30), p.fetch(normalize("FXTUBES"), 30)
    assert [x.close for x in a] == [x.close for x in b]
    assert all(x.provenance.fixture for x in a)

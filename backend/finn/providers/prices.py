"""End-of-day price providers (D-36, D-38: yfinance first; NSE bhavcopy fallback not yet implemented).

A provider returns PriceBars or raises PriceProviderError with a kind the UI can explain:
  no_data      empty response: unknown, delisted or suspended symbol, or no trading in the period
  unsupported  the provider cannot serve this instrument
  error        timeout, network, rate limit or an unexpected payload
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol

from ..models import Instrument, PriceBar, Provenance, SourceClass


class PriceProviderError(Exception):
    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail = kind, detail


class PriceProvider(Protocol):
    name: str

    def fetch(self, inst: Instrument, days: int) -> list[PriceBar]: ...


# ---------------------------------------------------------------- yfinance
FrameFetcher = Callable[[str, int, float], "object"]   # (yahoo_symbol, days, timeout) -> pandas.DataFrame


def _yf_fetch(yahoo_symbol: str, days: int, timeout: float):
    import yfinance as yf  # imported lazily so tests and fixture mode never need the network

    return yf.Ticker(yahoo_symbol).history(period=f"{days}d", interval="1d", auto_adjust=False,
                                           actions=False, timeout=timeout, raise_errors=True)


class YFinanceProvider:
    """Wraps yfinance (unofficial Yahoo Finance client). Data is end-of-day and may be delayed."""

    name = "yfinance"

    def __init__(self, fetch_frame: FrameFetcher = _yf_fetch, timeout: float = 10.0, retries: int = 1,
                 sleep: Callable[[float], None] | None = None):
        import time

        self._fetch, self._timeout, self._retries = fetch_frame, timeout, retries
        self._sleep = sleep or time.sleep

    def fetch(self, inst: Instrument, days: int) -> list[PriceBar]:
        last: Exception | None = None
        for attempt in range(1 + self._retries):
            try:
                frame = self._fetch(inst.yahoo, days, self._timeout)
                break
            except Exception as e:  # yfinance raises a variety of types; classify by message
                msg = str(e) or e.__class__.__name__
                if _looks_like_no_data(msg):
                    raise PriceProviderError("no_data", msg[:200]) from e
                last = e
                if attempt < self._retries:
                    self._sleep(min(2.0 * (attempt + 1), 6.0))
        else:
            raise PriceProviderError("error", (str(last) or "yfinance failed")[:200])
        return frame_to_bars(frame, inst, source="yfinance")


def _looks_like_no_data(msg: str) -> bool:
    m = msg.lower()
    return any(s in m for s in ("no data found", "possibly delisted", "no timezone found", "symbol may be delisted",
                                "no price data", "404"))


def frame_to_bars(frame, inst: Instrument, source: str, retrieved_at: datetime | None = None) -> list[PriceBar]:
    """Convert a yfinance-style DataFrame (index = dates; Open/High/Low/Close/Volume columns) to bars."""
    if frame is None or getattr(frame, "empty", True):
        raise PriceProviderError("no_data", f"empty response for {inst.yahoo}")
    missing = {"Close"} - set(map(str, frame.columns))
    if missing:
        raise PriceProviderError("error", f"unexpected columns {list(frame.columns)}")
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    bars: list[PriceBar] = []
    for idx, row in frame.iterrows():
        d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        close = _num(row.get("Close"))
        if close is None or close <= 0:
            continue                               # gaps are skipped, never interpolated
        bars.append(PriceBar(
            instrument_key=inst.key, date=d, open=_num(row.get("Open")), high=_num(row.get("High")),
            low=_num(row.get("Low")), close=close, volume=_num(row.get("Volume")),
            provenance=Provenance(source_class=SourceClass.MARKET_DATA, source_name=source,
                                  url=f"https://finance.yahoo.com/quote/{inst.yahoo}", retrieved_at=retrieved_at,
                                  data_date=d, locator=f"{inst.yahoo} daily bar"),
        ))
    if not bars:
        raise PriceProviderError("no_data", f"no valid closes for {inst.yahoo}")
    return bars


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


# ---------------------------------------------------------------- fixture
def weekdays_back(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


class FixturePriceProvider:
    """Deterministic synthetic bars for tests and the offline demo. Every bar is marked fixture=True.

    Scenarios (by NSE code) exercise each disclosure path; everything else gets a calm random walk.
    """

    name = "fixture"
    # Scenarios use FICTITIOUS fixture companies only, so no invented move is ever attached to a real company.
    SCENARIOS = {
        "FXPHARMA": "price_drop",       # close -5.2%
        "FXPOWER": "volume_spike",      # volume 2.7x the 20-session average
        "FXCABLES": "both",             # +6.1% on 3.1x volume
        "FXNEWCO": "short_history",     # 6 sessions only
        "FXHALTED": "stale",            # last bar 5 weekdays old
        "FXGONE": "no_data",
        "FXBROKEN": "error",
    }

    def __init__(self, as_of: date, scenarios: dict[str, str] | None = None):
        self.as_of = as_of
        self.scenarios = dict(self.SCENARIOS if scenarios is None else scenarios)

    def fetch(self, inst: Instrument, days: int) -> list[PriceBar]:
        sc = self.scenarios.get(inst.code, "calm")
        if sc == "no_data":
            raise PriceProviderError("no_data", f"fixture: no data for {inst.yahoo}")
        if sc == "error":
            raise PriceProviderError("error", "fixture: simulated provider timeout")
        end = self.as_of if sc != "stale" else weekdays_back(self.as_of, 6)[0]
        n = 6 if sc == "short_history" else min(days, 40)
        dates = weekdays_back(end, n)
        seed = int(hashlib.sha256(inst.key.encode()).hexdigest()[:8], 16)
        base = 100 + seed % 2000
        vol0 = 200_000 + seed % 3_000_000
        closes, vols = [], []
        for i, _ in enumerate(dates):
            wiggle = ((seed >> (i % 24)) % 21 - 10) / 1000          # -1.0% .. +1.0%, deterministic
            closes.append(round((closes[-1] if closes else base) * (1 + wiggle), 2))
            vols.append(round(vol0 * (1 + (((seed >> (i % 20)) % 11) - 5) / 50)))
        if sc in ("price_drop", "both", "volume_spike"):
            prev = closes[-2]
            closes[-1] = round(prev * (1 - 0.052), 2) if sc == "price_drop" else (
                round(prev * 1.061, 2) if sc == "both" else round(prev * 1.012, 2))
            avg = sum(vols[-21:-1]) / len(vols[-21:-1])
            if sc == "volume_spike":
                vols[-1] = round(avg * 2.7)
            elif sc == "both":
                vols[-1] = round(avg * 3.1)
        now = datetime.combine(self.as_of, datetime.min.time(), tzinfo=timezone.utc)
        return [PriceBar(instrument_key=inst.key, date=d, open=c, high=c, low=c, close=c, volume=v,
                         provenance=Provenance(source_class=SourceClass.MARKET_DATA, source_name="fixture",
                                               retrieved_at=now, data_date=d, fixture=True,
                                               locator=f"synthetic bar ({sc})"))
                for d, c, v in zip(dates, closes, vols)]

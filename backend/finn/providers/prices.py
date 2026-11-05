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


IST = timezone(timedelta(hours=5, minutes=30))


def yf_window(days: int, now: datetime | None = None) -> tuple[str, str]:
    """Explicit [start, end) dates for Yahoo. `end` is tomorrow in IST because Yahoo's end date is exclusive:
    with `period=` (or end=today) the latest Indian session was sometimes missing (bug B1)."""
    today = (now or datetime.now(timezone.utc)).astimezone(IST).date()
    return (today - timedelta(days=days)).isoformat(), (today + timedelta(days=1)).isoformat()


def _yf_fetch(yahoo_symbol: str, days: int, timeout: float):
    import yfinance as yf  # imported lazily so tests and fixture mode never need the network

    start, end = yf_window(days)
    t = yf.Ticker(yahoo_symbol)
    frame = t.history(start=start, end=end, interval="1d", auto_adjust=False, actions=False, timeout=timeout,
                      raise_errors=True)
    try:   # Yahoo's quote metadata holds the session price when the daily row's close is still null (B1)
        frame.attrs["finn_meta"] = dict(t.history_metadata or {})
    except Exception:  # noqa: BLE001 - metadata is a bonus; the bars still stand
        pass
    return frame


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


def _yf_quote_frame(yahoo_symbol: str, timeout: float):
    """Last 5 daily rows plus Yahoo's quote metadata (the request shape verified to carry regularMarketPrice)."""
    import yfinance as yf

    t = yf.Ticker(yahoo_symbol)
    frame = t.history(period="5d", interval="1d", auto_adjust=False, actions=False, timeout=timeout)
    meta = {}
    try:
        meta = dict(t.history_metadata or {})
    except Exception:  # noqa: BLE001
        pass
    return frame, meta


UA = "FINN-research-prototype/0.1 (personal, non-commercial)"


def _yahoo_chart_quote(yahoo_symbol: str, timeout: float):
    """Yahoo's public chart endpoint (the one yfinance itself calls), read directly: 5 daily rows + quote meta.
    Observed 6 Nov 2026: it carries regularMarketPrice for a day whose daily close is still null. Falls back to
    yfinance on any failure; the route taken is recorded in meta['_route'] for /v1/data-status."""
    import httpx
    import pandas as pd

    try:
        r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
                      params={"range": "5d", "interval": "1d"}, headers={"User-Agent": UA}, timeout=timeout)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").normalize()
        frame = pd.DataFrame({"Open": q.get("open"), "High": q.get("high"), "Low": q.get("low"),
                              "Close": q.get("close"), "Volume": q.get("volume")}, index=idx).astype(float)
        return frame, {**(res.get("meta") or {}), "_route": "chart"}
    except Exception as e:  # noqa: BLE001
        frame, meta = _yf_quote_frame(yahoo_symbol, timeout)
        return frame, {**meta, "_route": f"yfinance (chart failed: {(str(e) or e.__class__.__name__)[:60]})"}


def _yf_info_price(yahoo_symbol: str) -> dict:
    """Last resort: Yahoo's quote summary via yfinance (it handles Yahoo's cookie/crumb)."""
    import yfinance as yf

    info = yf.Ticker(yahoo_symbol).info or {}
    return {"regularMarketPrice": info.get("regularMarketPrice") or info.get("currentPrice"),
            "regularMarketTime": info.get("regularMarketTime")}


def _yf_quote(yahoo_symbol: str, timeout: float):
    frame, meta = _yf_quote_frame(yahoo_symbol, timeout)
    return frame, {**meta, "_route": "yfinance"}


# The direct chart call is NOT the default: from Render, Yahoo answered it with HTTP 429 (6 Nov 2026), and FINN
# never works around rate limits (CLAUDE.md). yfinance + the quote summary are used instead.
def session_bar(provider: "YFinanceProvider", inst: Instrument, after: date,
                quote=_yf_quote, info=_yf_info_price) -> tuple["PriceBar | None", str]:
    """Top-up for B1: returns (bar, note) for the latest session after `after` when the normal fetch lacked it.
    Uses the daily row's close if Yahoo has finalised it, else Yahoo's regularMarketPrice for the same IST day."""
    try:
        frame, meta = quote(inst.yahoo, provider._timeout)
    except Exception as e:  # noqa: BLE001
        return None, f"error: {(str(e) or e.__class__.__name__)[:120]}"
    route = meta.pop("_route", "?")
    if frame is None or getattr(frame, "empty", True):
        return None, f"no rows via {route}"
    frame.attrs["finn_meta"] = meta
    if _session_price(frame) is None and last_close_missing(frame):
        try:
            frame.attrs["finn_meta"] = {**meta, **{k: v for k, v in info(inst.yahoo).items() if v}}
            route += " + quote summary"
        except Exception as e:  # noqa: BLE001
            route += f" + quote summary failed ({(str(e) or e.__class__.__name__)[:60]})"
    try:
        bars = frame_to_bars(frame, inst, source="yfinance")
    except PriceProviderError as e:
        return None, f"{e.kind} via {route}"
    last = bars[-1]
    if last.date <= after:
        lastrow = frame.index[-1].date() if hasattr(frame.index[-1], "date") else frame.index[-1]
        sess = _session_price(frame)
        return None, (f"no bar after {after} via {route}; last row {lastrow} close "
                      f"{'missing' if last_close_missing(frame) else 'present'}; session price "
                      f"{('for ' + str(sess[0])) if sess else 'absent'}")
    kind = "session price" if "not yet finalised" in (last.provenance.locator or "") else "daily close"
    return last, f"{kind} via {route}"


def _yf_download(yahoo_symbols: list[str], days: int, timeout: float):
    import yfinance as yf

    start, end = yf_window(days)
    return yf.download(tickers=" ".join(yahoo_symbols), start=start, end=end, interval="1d", group_by="ticker",
                       auto_adjust=False, actions=False, threads=True, progress=False, timeout=timeout)


def fetch_many_yf(provider: "YFinanceProvider", insts: list[Instrument], days: int,
                  download=_yf_download) -> dict[str, "list[PriceBar] | PriceProviderError"]:
    """One request for many symbols (much faster than one per symbol). Symbols missing from the answer fall back
    to the single-symbol path, so one bad ticker never blanks the rest."""
    out: dict = {}
    try:
        frame = download([i.yahoo for i in insts], days, provider._timeout * 3)
    except Exception:  # noqa: BLE001 - fall back to one-by-one
        frame = None
    for inst in insts:
        sub = None
        if frame is not None and not getattr(frame, "empty", True):
            try:
                cols = frame.columns
                sub = frame[inst.yahoo] if getattr(cols, "nlevels", 1) > 1 and inst.yahoo in cols.get_level_values(0) else (
                    frame if len(insts) == 1 else None)
                if sub is not None:
                    sub = sub.dropna(how="all")
            except Exception:  # noqa: BLE001
                sub = None
        try:
            # A null latest close is handled by Pipeline.top_up_sessions (one small request), not by re-fetching
            # the whole span one symbol at a time.
            out[inst.key] = frame_to_bars(sub, inst, source="yfinance") if sub is not None and not sub.empty \
                else provider.fetch(inst, days)
        except PriceProviderError as e:
            out[inst.key] = e
    return out


def last_close_missing(frame) -> bool:
    """Yahoo sometimes returns the latest daily row with open/high/low/volume but a null close for hours after
    the session (observed 6 Nov 2026 04:00 IST for every NSE stock). The batch download has no quote metadata
    to fill it, so such symbols are re-fetched one by one."""
    try:
        return _num(frame.iloc[-1].get("Close")) is None
    except Exception:  # noqa: BLE001
        return False


def _session_price(frame) -> tuple[date, float] | None:
    meta = getattr(frame, "attrs", {}).get("finn_meta") or {}
    price, ts = _num(meta.get("regularMarketPrice")), meta.get("regularMarketTime")
    if price is None or price <= 0 or not ts:
        return None
    try:
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST).date()
    except (TypeError, ValueError, OverflowError):
        return None
    return d, price


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
    sess = _session_price(frame)
    n = len(frame)
    for i, (idx, row) in enumerate(frame.iterrows()):
        d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        close = _num(row.get("Close"))
        locator = f"{inst.yahoo} daily bar"
        if (close is None or close <= 0) and i == n - 1 and sess and sess[0] == d:
            close = sess[1]                        # B1: Yahoo's own session price for that same day
            locator = f"{inst.yahoo} daily bar; close = Yahoo regularMarketPrice (daily close not yet finalised)"
        if close is None or close <= 0:
            continue                               # gaps are skipped, never interpolated
        bars.append(PriceBar(
            instrument_key=inst.key, date=d, open=_num(row.get("Open")), high=_num(row.get("High")),
            low=_num(row.get("Low")), close=close, volume=_num(row.get("Volume")),
            provenance=Provenance(source_class=SourceClass.MARKET_DATA, source_name=source,
                                  url=f"https://finance.yahoo.com/quote/{inst.yahoo}", retrieved_at=retrieved_at,
                                  data_date=d, locator=locator),
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
        if days > 60 and sc != "short_history":
            return self._long(inst, days, sc)
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

    def _long(self, inst: Instrument, days: int, sc: str) -> list[PriceBar]:
        """A long backfill: the same recent 40 sessions as a normal fetch, preceded by an older synthetic walk
        computed backwards from them, so refresh and backfill never disagree on a date."""
        recent = self.fetch(inst, 40)
        older = weekdays_back(recent[0].date - timedelta(days=1), max(0, days * 5 // 7 - len(recent)))
        c = recent[0].close
        rows = []
        for i, d in enumerate(reversed(older)):
            h = int(hashlib.sha256(f"{inst.key}:{i}".encode()).hexdigest()[:6], 16)
            c = round(c / (1 + (h % 41 - 20) / 1000 + 0.0003), 2)    # -2% .. +2% a day, slight upward drift
            rows.append((d, max(c, 1.0), recent[0].volume))
        p0 = recent[0].provenance
        return [PriceBar(instrument_key=inst.key, date=d, open=x, high=x, low=x, close=x, volume=v,
                         provenance=p0.model_copy(update={"data_date": d}))
                for d, x, v in reversed(rows)] + recent

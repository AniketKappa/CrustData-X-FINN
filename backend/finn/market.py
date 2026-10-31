"""Daily market signals and deterministic price/volume alerts (ARCHITECTURE §5.7). Pure functions."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import AlertThresholds, Availability, MarketAlert, MarketSignal, PriceBar, Provenance, SourceClass

IST = ZoneInfo("Asia/Kolkata")
SESSION_COMPLETE_AT = time(16, 0)     # NSE/BSE close 15:30 IST; allow 30 min for EOD data to settle


def expected_session(now: datetime) -> date:
    """Latest weekday whose session should be complete at `now`. Exchange holidays are NOT applied."""
    local = now.astimezone(IST)
    d = local.date()
    if local.time() < SESSION_COMPLETE_AT:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def weekdays_between(a: date, b: date) -> int:
    """Number of weekdays in (a, b]."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def compute_signal(symbol: str, instrument_key: str, bars: list[PriceBar], th: AlertThresholds,
                   now: datetime, staleness_days: int = 1) -> MarketSignal:
    notes: list[str] = []
    if not bars:
        return MarketSignal(instrument_key=instrument_key, symbol=symbol, availability=Availability.NO_DATA,
                            notes=["No price data available for this symbol."])
    bars = sorted(bars, key=lambda b: b.date)
    exp = expected_session(now)
    live = bars[-1].date > exp              # today's session is still open: the last bar is the price so far
    last = bars[-1]
    sig = MarketSignal(instrument_key=instrument_key, symbol=symbol, as_of=last.date, close=last.close,
                       volume=last.volume, availability=Availability.OK, notes=notes, provenance=last.provenance,
                       live=live, live_at=last.provenance.retrieved_at if live else None)
    notes = sig.notes                       # pydantic copies the list; keep appending to the model's own list
    if live:
        at = sig.live_at.astimezone(IST).strftime("%H:%M") if sig.live_at else "now"
        notes.append(f"Today's session is open: price as of {at} IST (Yahoo data can lag ~15 minutes).")
        exp = last.date
    for n in (1, 3, 5):
        if len(bars) > n and bars[-1 - n].close:
            sig.changes[str(n)] = (last.close / bars[-1 - n].close - 1) * 100

    lag = weekdays_between(last.date, exp)
    if lag > staleness_days:
        sig.availability = Availability.STALE
        notes.append(f"Latest price is from {last.date:%d %b %Y}, {lag} trading days behind (possible suspension, "
                     "holiday or provider delay).")

    if len(bars) >= 2:
        prev = bars[-2]
        sig.prev_close = prev.close
        sig.pct_change = (last.close / prev.close - 1) * 100
    else:
        notes.append("Only one session available; daily change can't be computed.")

    if live:                                # a part-day volume would always look low against full days
        notes.append("Volume is compared with its average after the close.")
        return sig
    prior = [b.volume for b in bars[:-1][-th.lookback_sessions:] if b.volume is not None]
    zeros = sum(1 for v in prior if v == 0)
    prior = [v for v in prior if v > 0]
    if zeros:
        notes.append(f"{zeros} zero-volume session(s) excluded from the average.")
    sig.lookback_used = len(prior)
    if last.volume is None:
        notes.append("Volume not reported for the latest session.")
    elif len(prior) < th.min_history_sessions:
        if sig.availability == Availability.OK:
            sig.availability = Availability.INSUFFICIENT_HISTORY
        notes.append(f"Only {len(prior)} prior sessions with volume; at least {th.min_history_sessions} are needed "
                     "for a volume comparison.")
    else:
        sig.avg_volume = sum(prior) / len(prior)
        sig.volume_multiple = last.volume / sig.avg_volume
    if last.provenance.fixture:
        notes.append("Synthetic fixture data.")
    return sig


def _ge(value: float | None, threshold: float) -> bool:
    """At-or-beyond comparison, robust to float noise (5.000000000000004 vs 5.0)."""
    return value is not None and round(value, 9) >= round(threshold, 9)


def evaluate_alert(sig: MarketSignal, th: AlertThresholds) -> MarketAlert | None:
    """Fire when |daily change| >= pct threshold or volume multiple >= volume threshold.

    No alert on stale or missing data: an old move is not news, and the disclosure explains why.
    """
    if sig.availability in (Availability.STALE, Availability.NO_DATA, Availability.PROVIDER_ERROR) or sig.as_of is None:
        return None
    rules, parts = [], []
    if sig.pct_change is not None and _ge(abs(sig.pct_change), th.pct_change_abs):
        rules.append("price")
        parts.append(f"{'price so far today' if sig.live else 'close'} {'up' if sig.pct_change > 0 else 'down'} "
                     f"{abs(sig.pct_change):.1f}% "
                     f"(threshold ±{th.pct_change_abs:g}%)")
    if sig.volume_multiple is not None and _ge(sig.volume_multiple, th.volume_multiple):
        rules.append("volume")
        parts.append(f"volume {sig.volume_multiple:.1f}× its {sig.lookback_used}-session average "
                     f"(threshold {th.volume_multiple:g}×)")
    if not rules:
        return None
    key = hashlib.sha1(f"{sig.instrument_key}|{sig.as_of}|{','.join(rules)}|{th.pct_change_abs}|{th.volume_multiple}"
                       .encode()).hexdigest()[:16]
    base = sig.provenance
    prov = Provenance(source_class=SourceClass.DERIVED, source_name=base.source_name if base else "unknown",
                      retrieved_at=base.retrieved_at if base else datetime.now(IST), data_date=sig.as_of,
                      formula="pct = (close/prev_close - 1)*100; mult = volume / mean(prev N volumes)",
                      fixture=bool(base and base.fixture))
    text = "; ".join(parts)
    return MarketAlert(key=key, symbol=sig.symbol, date=sig.as_of, rules=rules, pct_change=sig.pct_change,
                       volume_multiple=sig.volume_multiple, explanation=text[0].upper() + text[1:],
                       close=sig.close, prev_close=sig.prev_close, volume=sig.volume, avg_volume=sig.avg_volume,
                       lookback_used=sig.lookback_used, live=sig.live, thresholds=th, provenance=prov)


def session_alerts(symbol: str, instrument_key: str, bars: list[PriceBar], th: AlertThresholds, now: datetime,
                   sessions: int, staleness_days: int = 1) -> list[tuple[MarketAlert, MarketSignal]]:
    """Alerts for each of the last `sessions` sessions (latest first): a 7-day window lists every day that
    crossed a threshold, not just the latest one."""
    bars = sorted(bars, key=lambda b: b.date)
    out = []
    for j in range(sessions):
        upto = bars[:len(bars) - j]
        if len(upto) < 2:
            break
        sig = compute_signal(symbol, instrument_key, upto, th, now, staleness_days if j == 0 else 10 ** 6)
        al = evaluate_alert(sig, th)
        if al is not None:
            out.append((al, sig))
    return out

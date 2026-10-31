"""Explainable ranking (ARCHITECTURE §5.1). Every score carries its components, weights and reasons.

score = Σ weight_k × component_k, components on 0–100:
  materiality  category base (REF taxonomy) or subtype override; +10 if the same symbol has a market alert that day
  recency      100 × 0.5^(age_hours / half_life)
  relevance    holding / research / other (config)
  confidence   classifier confidence × 100 (× 0.8 if the company could not be mapped to a symbol)
Tier: high ≥ tiers.high; normal ≥ tiers.normal; otherwise routine. Routine categories and very low
materiality are always routine (collapsed).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .models import Announcement, Classification, MarketAlert, ScoreBreakdown, Tier


def _recency(filed_at: datetime, now: datetime, half_life_h: float) -> tuple[float, float]:
    age_h = max(0.0, (now - filed_at).total_seconds() / 3600)
    return 100 * 0.5 ** (age_h / half_life_h), age_h


def _combine(cfg: dict[str, Any], m: float, rc: float, rv: float, cf: float, reasons: list[str]) -> ScoreBreakdown:
    w = cfg["weights"]
    total = w["materiality"] * m + w["recency"] * rc + w["relevance"] * rv + w["confidence"] * cf
    return ScoreBreakdown(materiality=round(m, 1), recency=round(rc, 1), relevance=round(rv, 1),
                          confidence=round(cf, 1), weights=dict(w), total=round(total, 1), reasons=reasons)


def _age(h: float) -> str:
    return f"{h:.0f} h ago" if h < 48 else f"{h / 24:.0f} days ago"


def score_announcement(a: Announcement, c: Classification, role: str, now: datetime, cfg: dict[str, Any],
                       alert_dates: set[tuple[str, date]] | None = None) -> tuple[ScoreBreakdown, Tier]:
    base = cfg["materiality"].get(c.category, cfg["materiality"]["unclassified"])
    m = cfg.get("subtype_materiality", {}).get(c.subtype, base) if c.subtype else base
    reasons = [f"{c.category}{' / ' + c.subtype if c.subtype else ''}: materiality {m:g}"]
    base_m = m                                   # routine floor uses materiality before modifiers
    if alert_dates and a.symbol and (a.symbol, a.filed_at.date()) in alert_dates:
        m = min(100, m + 10)
        reasons.append("same-day price/volume alert: +10")
    rc, age_h = _recency(a.filed_at, now, cfg["recency_half_life_hours"])
    reasons.append(f"filed {_age(age_h)}: recency {rc:.0f}")
    rv = cfg["relevance"].get(role, cfg["relevance"]["other"])
    reasons.append(f"{'portfolio holding' if role == 'holding' else 'research list' if role == 'research' else 'not in portfolio'}: relevance {rv:g}")
    cf = c.confidence * 100 * (1.0 if a.symbol else 0.8)
    reasons.append(f"classified by {c.method}{' ' + repr(c.rule) if c.rule else ''}: confidence {cf:.0f}"
                   + ("" if a.symbol else " (company not mapped to a symbol)"))
    s = _combine(cfg, m, rc, rv, cf, reasons)
    return s, tier_for(s.total, c.category, base_m, cfg)


def score_alert(al: MarketAlert, role: str, now: datetime, cfg: dict[str, Any], data_confidence: float,
                session_close: datetime) -> tuple[ScoreBreakdown, Tier]:
    m = cfg.get("market_alert_materiality", 80)
    rc, age_h = _recency(session_close, now, cfg["recency_half_life_hours"])
    rv = cfg["relevance"].get(role, cfg["relevance"]["other"])
    reasons = [f"market alert ({', '.join(al.rules)}): materiality {m:g}", f"session closed {_age(age_h)}: recency {rc:.0f}",
               f"{'portfolio holding' if role == 'holding' else role}: relevance {rv:g}",
               f"data confidence {data_confidence:.0f}"]
    s = _combine(cfg, m, rc, rv, data_confidence, reasons)
    return s, ("high" if s.total >= cfg["tiers"]["normal"] else "normal")   # an alert is never collapsed


def tier_for(total: float, category: str, materiality: float, cfg: dict[str, Any]) -> Tier:
    if category in cfg.get("routine_categories", []) or materiality < cfg.get("routine_max_materiality", 20):
        return "routine"
    if total >= cfg["tiers"]["high"]:
        return "high"
    if total >= cfg["tiers"]["normal"]:
        return "normal"
    return "routine"

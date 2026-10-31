from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from finn.classify import classify
from finn.config import load_settings
from finn.models import Announcement, Provenance, SourceClass
from finn.rank import score_announcement, tier_for

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)
CFG = load_settings().ranking


def ann(subject, detail=None, hours_ago=1, symbol="X"):
    t = NOW - timedelta(hours=hours_ago)
    return Announcement(uid=subject, source="t", exchange="NSE", symbol=symbol, company_name="X", subject=subject,
                        detail=detail, filed_at=t,
                        provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="t", retrieved_at=t))


def score(a, role="holding", alerts=None):
    return score_announcement(a, classify(a), role, NOW, CFG, alerts)


def test_weights_sum_to_one():
    assert abs(sum(CFG["weights"].values()) - 1) < 1e-9


def test_breakdown_is_explainable_and_consistent():
    s, tier = score(ann("Outcome of Board Meeting", "unaudited financial results"))
    w = s.weights
    assert abs(s.total - (w["materiality"] * s.materiality + w["recency"] * s.recency + w["relevance"] * s.relevance
                          + w["confidence"] * s.confidence)) < 0.2
    assert tier == "high" and len(s.reasons) == 4 and "results" in s.reasons[0]


def test_recency_halves_per_half_life():
    a, _ = score(ann("Dividend", "record date", hours_ago=0))
    b, _ = score(ann("Dividend", "record date", hours_ago=CFG["recency_half_life_hours"]))
    assert a.recency == 100 and b.recency == 50


def test_relevance_orders_holding_over_research_over_other():
    x = [score(ann("Credit Rating", "reaffirmed rating"), role)[0].total for role in ("holding", "research", "other")]
    assert x[0] > x[1] > x[2]


def test_unmapped_company_lowers_confidence():
    a, _ = score(ann("Dividend", "interim dividend"))
    b, _ = score(ann("Dividend", "interim dividend", symbol=None))
    assert b.confidence < a.confidence


def test_routine_rules():
    assert score(ann("Trading Window", "closure"))[1] == "routine"                  # routine category
    assert score(ann("Copy of Newspaper Publication", "financial results"))[1] == "routine"   # low materiality subtype
    # the same-day alert bonus never lifts a routine item out of the collapsed section
    assert score(ann("Copy of Newspaper Publication", "financial results"), alerts={("X", NOW.date())})[1] == "routine"


def test_alert_bonus():
    a, _ = score(ann("Dividend", "interim dividend"))
    b, _ = score(ann("Dividend", "interim dividend"), alerts={("X", NOW.date())})
    assert b.materiality == a.materiality + 10


def test_tier_cutoffs_boundaries():
    assert tier_for(CFG["tiers"]["high"], "results", 90, CFG) == "high"
    assert tier_for(CFG["tiers"]["high"] - 0.1, "results", 90, CFG) == "normal"
    assert tier_for(CFG["tiers"]["normal"], "dividend", 35, CFG) == "normal"
    assert tier_for(CFG["tiers"]["normal"] - 0.1, "dividend", 35, CFG) == "routine"

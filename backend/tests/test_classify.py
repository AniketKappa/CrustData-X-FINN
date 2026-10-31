from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from finn.classify import classify
from finn.models import CATEGORIES, Announcement, Provenance, SourceClass

T = datetime(2026, 10, 29, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def ann(subject, detail=None):
    return Announcement(uid="x", source="fixture", exchange="NSE", symbol="X", company_name="X", subject=subject,
                        detail=detail, filed_at=T,
                        provenance=Provenance(source_class=SourceClass.PRIMARY_DOC, source_name="t", retrieved_at=T))


CASES = [
    # D-29: the attachment text decides, not the subject
    ("Outcome of Board Meeting", "approved the unaudited financial results for the quarter", "results", None),
    ("Updates", "Transcript of the earnings call held on 28 Oct", "earnings_call", "earnings_call_transcript"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of analyst meet on 4 Nov", "investor_meetings", None),
    ("Copy of Newspaper Publication", "Publication of financial results in newspapers", "results", "results_newspaper_ad"),
    ("Copy of Newspaper Publication", "Notice to shareholders on IEPF transfer", "unclassified", None),
    ("Board Meeting Intimation", "meeting of the Board on 5 Nov to consider financial results", "results",
     "results_board_meeting_notice"),
    ("Change in Directors/ Key Managerial Personnel", "Resignation of Chief Financial Officer", "management_change",
     "management_change_top"),
    ("Change in Directors/ Key Managerial Personnel", "Appointment of Mr X as Independent Director", "management_change",
     "management_change_independent_director"),
    ("Appointment of Statutory Auditors", None, "unclassified", None),
    ("Acquisition", "Agreement to acquire 51% stake", "M&A", None),
    ("Scheme of Arrangement", "Demerger of the consumer business", "M&A", None),
    ("Allotment of Equity Shares", "Allotment under ESOP 2021", "unclassified", None),
    ("Qualified Institutions Placement", "Launch of QIP", "fund_raise", None),
    ("Credit Rating", "rating reaffirmed at AA; outlook stable", "credit_rating", "credit_rating_reaffirmed"),
    ("Credit Rating", "ICRA has downgraded the long-term rating", "credit_rating", "credit_rating_downgrade"),
    ("Updates", "Receipt of show cause notice from SEBI", "litigation", "litigation_regulator"),
    ("Updates", "Order of the High Court in the tax matter", "litigation", None),
    ("Disclosure under SEBI (PIT) Regulations", "Regulation 7(2) disclosure of sale by promoter", "insider_trading", None),
    ("Dividend", "Record date for interim dividend", "dividend", None),
    ("Bonus issue", "Recommendation of bonus issue 1:1", "bonus_split", None),
    ("Updates", "Commissioning of new plant at Raipur", "capex", None),
    ("Press Release", "Order win of Rs 500 crore", "press_release", None),
    ("Postal Ballot", "Scrutinizer's report", "postal_ballot", None),
    ("Shareholders meeting", "Notice of the 40th Annual General Meeting", "agm_egm", None),
    ("Disclosure of encumbrance", "Creation of pledge by promoter", "pledging", None),
    ("Trading Window", "Closure of trading window", "unclassified", None),
    ("Certificate under Regulation 74(5)", None, "unclassified", None),
    ("Outcome of Board Meeting", None, "results", None),
    ("Something else entirely", None, "unclassified", None),
]


@pytest.mark.parametrize("subject,detail,cat,sub", CASES)
def test_rules(subject, detail, cat, sub):
    c = classify(ann(subject, detail))
    assert (c.category, c.subtype) == (cat, sub)
    assert c.category in CATEGORIES


def test_explainable_and_low_confidence_fallbacks():
    c = classify(ann("Outcome of Board Meeting"))
    assert c.rule == "board_meeting_outcome" and c.confidence < 0.5
    d = classify(ann("Misc"))
    assert d.method == "default" and d.rule is None


def test_every_category_reachable():
    assert {c for _, _, c, _ in CASES} == set(CATEGORIES)

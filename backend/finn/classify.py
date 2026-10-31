"""Rule-based announcement classifier over the REF §1 taxonomy (17 categories; D-29).

Rules read the subject AND the attachment text/description, never the subject alone: NSE files results as
"Outcome of Board Meeting" and transcripts as "Updates" or "Analysts/Institutional Investor Meet/Con. Call
Updates". Rules are ordered: the first match wins, and its name is returned for explainability.
An LLM fallback for low-confidence items is planned (ARCHITECTURE §5.1) but not implemented here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import Announcement, Classification


@dataclass(frozen=True)
class Rule:
    name: str
    category: str
    pattern: re.Pattern
    confidence: float = 0.9
    subtype: Optional[str] = None
    requires: Optional[re.Pattern] = None      # an extra pattern that must also match


def r(p: str) -> re.Pattern:
    return re.compile(p, re.I)


RESULTS = r(r"financial results?|\bresults? for the (quarter|half|year)|un-?audited|audited (standalone|consolidated)|"
            r"integrated filing.{0,20}financ|"
            # news-headline phrasings ("Q2 results", "Q2 FY27 net profit rises")
            r"\bq[1-4](\s*fy\s*\d{2,4})?\s+(results|earnings|(net\s+)?profit|revenue)|quarterly (results|earnings|profit)")

RULES: list[Rule] = [
    # --- routine paperwork that would otherwise trip broader rules (REF: "unclassified") ---
    Rule("esop", "unclassified", r(r"\besops?\b|employee stock (option|purchase)|esos\b|\besps\b"), 0.9),
    Rule("trading_window", "unclassified", r(r"trading window"), 0.95),
    Rule("compliance_certificate", "unclassified",
         r(r"compliance certificate|regulation 74\s*\(5\)|reg\.? ?74\s*\(5\)|secretarial compliance|"
           r"certificate under regulation|regulation 40\s*\(9\)"), 0.95),
    Rule("auditor_appointment", "unclassified", r(r"(statutory|secretarial|internal|cost) auditors?"), 0.85),
    Rule("share_certificate", "unclassified", r(r"loss of share certificate|duplicate (share )?certificate"), 0.95),
    Rule("esg_report", "unclassified", r(r"business responsibility|\bbrsr\b|sustainability report|\besg\b"), 0.9),
    # --- results family ---
    Rule("results_newspaper_ad", "results", r(r"newspaper (publication|advertisement)|publication in newspaper"),
         0.85, "results_newspaper_ad", requires=RESULTS),
    Rule("results_board_notice", "results",
         r(r"board meeting intimation|intimation of (the )?board meeting|prior intimation|meeting of the board .{0,60}"
           r"to consider|will be held .{0,80}(results|financial)"), 0.85, "results_board_meeting_notice", requires=RESULTS),
    Rule("results", "results", RESULTS, 0.9),
    # --- calls and meetings ---
    Rule("earnings_call_transcript", "earnings_call", r(r"transcript"), 0.9, "earnings_call_transcript"),
    Rule("earnings_call", "earnings_call",
         r(r"earnings (conference )?call|conference call|con\.? ?call|audio recording|recording of the (earnings|analyst|investor)"), 0.8),
    Rule("investor_meetings", "investor_meetings",
         r(r"(analysts?|institutional investors?|investor) meet|one[- ]on[- ]one|investor conference|"
           r"schedule of (analyst|investor)"), 0.85),
    # --- votes and meetings ---
    Rule("postal_ballot", "postal_ballot", r(r"postal ballot"), 0.95),
    Rule("agm_egm", "agm_egm", r(r"annual general meeting|\bagm\b|extra-?ordinary general meeting|\begm\b"), 0.9),
    # --- material events ---
    Rule("credit_rating_downgrade", "credit_rating",
         r(r"(credit )?rating.{0,80}(downgrad|negative watch|outlook .{0,20}negative)|downgrad.{0,40}rating"),
         0.9, "credit_rating_downgrade"),
    Rule("credit_rating_reaffirmed", "credit_rating", r(r"(credit )?rating.{0,80}reaffirm|reaffirm.{0,60}rating"),
         0.9, "credit_rating_reaffirmed"),
    Rule("credit_rating", "credit_rating",
         r(r"credit rating|\bratings? (assigned|upgraded|revised)|\b(crisil|icra|care ratings|india ratings|acuite|brickwork)\b|"
           r"rating agency|rating outlook"), 0.85),
    Rule("pledging", "pledging", r(r"pledg|encumbrance|regulation 31\s*\(1\)"), 0.9),
    Rule("insider_trading", "insider_trading",
         r(r"insider trading|regulation 7\s*\(2\)|\bsast\b|regulation 29\s*\(\d\)|"
           r"(acquisition|sale|disposal) of shares by (the )?promoter"), 0.85),
    Rule("management_change_top", "management_change",
         r(r"(appoint|resign|cessation|re-?appoint|retire|step(s|ped)? down|change in).{0,120}"
           r"(chief executive|chief financial|\bceo\b|\bcfo\b|managing director|\bmd\b|chairman|whole[- ]time director)|"
           r"(chief executive|chief financial|\bceo\b|\bcfo\b|managing director|chairman|whole[- ]time director).{0,80}"
           r"(appoint|resign|cessation|retire|step(s|ped)? down)"), 0.9, "management_change_top"),
    Rule("management_change_independent", "management_change",
         r(r"independent director.{0,80}(appoint|resign|cessation|re-?appoint|completion of tenure)|"
           r"(appoint|resign|cessation).{0,80}independent director"), 0.85, "management_change_independent_director"),
    Rule("management_change", "management_change",
         r(r"change in (directors?|kmp|key managerial|management|senior management)|appointment of .{0,40}director|"
           r"resignation of|cessation of|key managerial personnel|"
           # news phrasings
           r"\bwho is [A-Z][a-z]+ [A-Z][a-z]+|taking charge|takes charge|to step down|steps down|stepping down|"
           r"\bnew (ceo|cfo|chairman|chairperson|md|managing director|chief executive)\b|succession"), 0.8),
    Rule("M&A", "M&A",
         r(r"acqui(re|sition)|merger|amalgamation|demerger|joint venture|scheme of arrangement|strike-off|"
           r"\bbuys? .{0,30}stake|\bsells? .{0,30}stake|stake (in|of) |\bdivests?|"
           r"stake (sale|purchase)|divest|takeover|incorporation of .{0,30}subsidiary|investment in .{0,30}subsidiary"), 0.85),
    Rule("fund_raise", "fund_raise",
         r(r"qualified institutions? placement|\bqip\b|rights issue|preferential (issue|allotment)|buy-?back|"
           r"commercial paper|non-convertible debentures?|\bncds?\b|fund rais|issue of (equity|debentures|bonds|warrants)"), 0.85),
    Rule("litigation_regulator", "litigation",
         r(r"\b(sebi|rbi|usfda|cci|competition commission|enforcement directorate)\b.{0,80}"
           r"(order|penalty|warning|show cause|notice|observation)|"
           r"(order|penalty|warning|show cause|notice).{0,80}\b(sebi|rbi|usfda|cci|competition commission|enforcement directorate)\b|"
           r"warning letter|form 483"), 0.85, "litigation_regulator"),
    Rule("litigation", "litigation",
         r(r"litigation|lawsuit|show cause|penalt(y|ies)|\bfine[sd]?\b|tribunal|\bnclt\b|insolvency|"
           r"high court|supreme court|arbitra|tax demand|demand order|gst.{0,20}(order|demand)|"
           r"\bsc (order|judgment|verdict|ruling)|judgment|verdict|\bprobe\b|\braids?\b|summons|"
           r"\bnotice (to|from|against)\b(?! (shareholders|members|investors))|issues notice|gives .{0,40} days to|\bat-?1 bonds?\b|regulatory action"), 0.8),
    Rule("dividend", "dividend", r(r"dividend"), 0.85),
    Rule("bonus_split", "bonus_split", r(r"\bbonus (issue|shares)|sub-?division|stock split|split of .{0,20}shares"), 0.9),
    Rule("capex", "capex",
         r(r"capacity expansion|capital expenditure|\bcapex\b|(new|greenfield|brownfield) (plant|facility|unit)|"
           r"lines up .{0,30}investment|investment plan|to invest .{0,30}(crore|bn|billion)|"
           r"commission(ing|ed) of .{0,40}(plant|facility|unit|capacity)"), 0.8),
    Rule("press_release", "press_release",
         r(r"press release|media release|order (win|received|inflow)|bag(s|ged)? .{0,30}order|receipt of .{0,20}order|"
           r"(secures|wins|bags) .{0,40}orders?\b|\blaunch(es)?\b|\bguidance\b|signs? (pact|mou|agreement)|"
           r"letter of award|launch|partnership|collaboration|clarification|award(s|ed)?\b"), 0.75),
    Rule("newspaper_publication", "unclassified", r(r"newspaper"), 0.85),
    Rule("board_meeting_outcome", "results", r(r"outcome of (the )?board meeting"), 0.45),
]


# NSE files calls, meetings and transcripts under one boilerplate subject; when there is attachment text,
# that text decides and the boilerplate is ignored.
AMBIGUOUS_SUBJECT = r(r"^\s*(analysts?/institutional investor meet/con\.? ?call updates|updates|general updates)\s*$")


def classify(a: Announcement) -> Classification:
    subject = "" if (a.detail and AMBIGUOUS_SUBJECT.match(a.subject)) else a.subject
    text = f"{subject} \n {a.detail or ''}"
    for rule in RULES:
        if rule.pattern.search(text) and (rule.requires is None or rule.requires.search(text)):
            return Classification(category=rule.category, subtype=rule.subtype, method="rule", rule=rule.name,
                                  confidence=rule.confidence)
    return Classification(category="unclassified", method="default", rule=None, confidence=0.3)


def classify_headline(headline: str) -> Classification:
    """Classify a news headline with the same rules (no attachment text exists for news)."""
    from datetime import datetime, timezone

    from .models import Provenance, SourceClass

    t = datetime.now(timezone.utc)
    probe = Announcement(uid="h", source="news", exchange="NSE", symbol=None, company_name="", subject=headline,
                         filed_at=t, provenance=Provenance(source_class=SourceClass.EXTERNAL_WEB, source_name="news",
                                                           retrieved_at=t))
    return classify(probe)

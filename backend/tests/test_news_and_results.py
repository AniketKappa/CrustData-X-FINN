from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from finn.config import load_portfolio
from finn.factory import FIXTURES
from finn.providers.announcements import SourceSchemaError
from finn.providers.news import about, news_uid, parse_google_news, parse_publisher_feed
from finn.providers.screener import build_results, parse_quarters

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)
PF = load_portfolio(FIXTURES)
TRUSTED = ["fixturewire.invalid", "fixturetimes.invalid"]


# ---------------- news ----------------
def test_google_news_trusted_only_named_only_no_snippets():
    items = parse_google_news((FIXTURES / "news_google_cables.xml").read_text(), PF.companies["FXCABLES"], TRUSTED, NOW, "u")
    heads = [i.headline for i in items]
    assert "Fixture Cables shares: 5 things to know" not in heads          # untrusted publisher dropped
    assert not any("copper" in h for h in heads)                            # doesn't name the company
    assert all(not h.endswith(("Fixture Wire", "Fixture Times")) for h in heads)   # " - Publisher" suffix removed
    assert all(i.provenance.source_class.value == "EXTERNAL_WEB" for i in items)
    assert "snippet" not in items[0].model_dump_json()                      # descriptions are never stored


def test_same_story_from_two_outlets_has_one_uid():
    items = parse_google_news((FIXTURES / "news_google_cables.xml").read_text(), PF.companies["FXCABLES"], TRUSTED, NOW, "u")
    deal = [i for i in items if "acquire" in i.headline]
    assert len(deal) == 2 and deal[0].uid == deal[1].uid


def test_publisher_feed_matches_by_name():
    items = parse_publisher_feed((FIXTURES / "news_publisher.xml").read_text(), "fx", "Fixture Times", PF, NOW, "u")
    assert [i.symbol for i in items] == ["FXPOWER"]


def test_real_portfolio_exclusions_and_case():
    pf = load_portfolio()
    assert about("ITC Q2 results: profit up 6%", pf.companies["ITC"])
    assert not about("ITC Hotels Q2 results beat estimates", pf.companies["ITC"])
    assert not about("Bitcoin price rises; itc mentioned", pf.companies["ITC"])     # short terms are case-sensitive
    assert about("L&T bags mega order", pf.companies["LT"])
    assert not about("L&T Finance raises Rs 2,000 crore", pf.companies["LT"])
    assert about("Infosys appoints new CFO", pf.companies["INFY"])


def test_news_section_in_digest(pipe):
    d = pipe.digest()
    assert 1 <= len(d.news) <= pipe.s.sources["news"]["max_items"]
    assert all(i.kind == "news" and i.news.publisher for i in d.news)
    assert any("media report" in r for r in d.news[0].score.reasons)
    assert {i.category for i in d.news} >= {"results", "management_change", "M&A", "credit_rating"}
    assert all(i.score.confidence <= 60 for i in d.news)
    assert news_uid("X", "A b!") == news_uid("X", "a  B")


# ---------------- screener results ----------------
def test_parse_quarters_reads_only_the_quarterly_table():
    periods, rows = parse_quarters((FIXTURES / "screener_FXCABLES.html").read_text())
    assert periods[0] == "Dec 2024" and periods[-1] == "Sep 2026"
    assert rows["sales"][-1] == 2418 and rows["profit before tax"][-1] == 244 and rows["net profit"][-1] == 182


def test_results_block_headline_numbers():
    periods, rows = parse_quarters((FIXTURES / "screener_FXCABLES.html").read_text())
    b = build_results("FXCABLES", periods, rows, "u", "consolidated", NOW, False)
    r = {x.metric: x for x in b.rows}
    assert b.periods == ["Sep 2026", "Jun 2026", "Sep 2025"]
    assert r["Revenue"].qoq == pytest.approx((2418 / 2281 - 1) * 100)
    assert r["Revenue"].yoy == pytest.approx((2418 / 2119 - 1) * 100)
    assert r["EBITDA"].latest == 244 + 10 + 25 - 20 and r["EBITDA"].derived
    assert r["PAT"].latest == 182


def test_lender_has_no_ebitda():
    rows = {"revenue": [100, 110, 120, 130, 140], "interest": [50] * 5, "financing profit": [10] * 5,
            "profit before tax": [20, 21, 22, 23, 24], "net profit": [15, 16, 17, 18, 19]}
    b = build_results("B", ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"], rows, "u", "standalone", NOW, False)
    assert b.is_lender and b.rows[1].latest is None and "lenders" in b.notes[0]


def test_negative_base_change_sign():
    rows = {"sales": [10, 10], "profit before tax": [-10, -5], "net profit": [-10, -5], "interest": [1, 1],
            "depreciation": [1, 1], "other income": [0, 0]}
    b = build_results("X", ["Jun 2026", "Sep 2026"], rows, "u", "standalone", NOW, False)
    assert b.rows[3].qoq == 50.0                      # loss halved -> +50%, not -50%


def test_layout_change_is_a_schema_error():
    with pytest.raises(SourceSchemaError):
        parse_quarters("<html><body><section id='quarters'><p>no table</p></section></body></html>")


def test_results_attached_only_where_relevant(pipe):
    d = pipe.digest()
    res = [i for i in d.high + d.normal + d.news if i.category == "results" and i.symbol == "FXCABLES"]
    assert res and all(i.results and i.results["periods"][0] == "Sep 2026" for i in res)
    ad = [i for i in d.routine if i.classification and i.classification.subtype == "results_newspaper_ad"]
    assert ad and ad[0].results is None
    assert pipe.snapshot("FXCABLES") is not None


def test_results_missing_is_explained():
    from finn.factory import build_pipeline
    p = build_pipeline("fixture")
    p.refresh_prices(); p.refresh_announcements(); p.refresh_news()   # noqa: E702 - results deliberately not fetched
    item = next(i for i in p.digest().high if i.category == "results")
    assert item.results is None and "not fetched yet" in item.results_status


# ---------------- company snapshot, portfolio edits ----------------
def test_company_snapshot_sections():
    from finn.providers.screener import parse_company
    s = parse_company((FIXTURES / "screener_FXCABLES.html").read_text(), "FXCABLES", "u", "consolidated", NOW)
    assert s.name == "Fixture Cables Ltd" and s.sector == "Capital Goods" and s.industry == "Cables - Electricals"
    assert ("Market Cap", "₹ 38,420 Cr.") in s.ratios and dict(s.ratios)["ROCE"] == "24.6 %"
    assert s.annual.periods[-1] == "TTM" and s.annual.rows["net profit"][-2] == 716
    assert s.balance.rows["borrowings"] == [180, 140, 120]
    assert s.cashflow.rows["cash from operating activity"][-1] == 640
    assert s.annual_reports[0].title == "Financial Year 2026" and s.annual_reports[0].note == "from bse"
    assert [c.period for c in s.concalls] == ["Oct 2026", "Jul 2026"] and s.concalls[0].ppt and not s.concalls[1].ppt
    assert s.credit_ratings[0].note == "12 Oct from fixture ratings"
    assert "about" not in "".join(s.notes) and s.about.startswith("Fixture Cables makes")


def test_company_view(pipe):
    v = pipe.company_view("FXCABLES")
    assert v["snapshot"]["sector"] == "Capital Goods" and v["results"]["periods"][0] == "Sep 2026"
    assert v["signal"]["close"] and len(v["history"]) > 20
    assert v["filings"] and v["news"] and v["news"][0]["publisher"]
    empty = pipe.company_view("FXPOWER")
    assert empty["snapshot"] is None and "Fundamentals unavailable" in empty["status"][0]


def test_portfolio_add_remove_persists(tmp_path):
    from finn.config import load_portfolio
    from finn.models import Company
    user = tmp_path / "portfolio.json"
    p = load_portfolio(FIXTURES, user)
    p.add(Company(symbol="TATAMOTORS", name="Tata Motors Ltd", role="holding"))
    assert user.exists()
    q = load_portfolio(FIXTURES, user)
    assert q.companies["TATAMOTORS"].news_terms == ["Tata Motors"] and q.companies["TATAMOTORS"].role == "holding"
    q.add(Company(symbol="TATAMOTORS", name="Tata Motors Ltd", role="research"))   # move to watchlist
    assert load_portfolio(FIXTURES, user).companies["TATAMOTORS"].role == "research"
    assert q.remove("FXCABLES") and "FXCABLES" not in load_portfolio(FIXTURES, user).companies
    assert not q.remove("NOPE")

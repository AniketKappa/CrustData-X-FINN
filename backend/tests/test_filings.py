"""BSE filings feed and reading filed PDFs (fixtures only)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from finn.filings import period_label, results_block, summary_ok
from finn.providers.announcements import SourceSchemaError, parse_bse_api

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)


def test_bse_parser_keeps_pdf_and_category_and_strips_prefix():
    rows = {"Table": [{"NEWSID": "n1", "SCRIP_CD": 999901, "NEWSSUB": "Fixture Co Ltd - 999901 - Credit Rating",
                       "NEWS_DT": "2026-10-28T16:05:00", "DissemDT": "2026-10-28T16:05:00.5", "ATTACHMENTNAME": "a.pdf",
                       "CATEGORYNAME": "Company Update", "SUBCATNAME": "Credit Rating", "Fld_Attachsize": 2048}]}
    a = parse_bse_api(rows, "FXCO", NOW, "https://fixtures.finn.invalid/bse/api", True,
                      "https://fixtures.finn.invalid/att/{name}")[0]
    assert a.subject == "Credit Rating" and a.exchange == "BSE" and a.symbol == "FXCO"
    assert a.source_url.endswith("/a.pdf") and a.source_category == "Company Update / Credit Rating"
    assert a.filed_at.hour == 16 and a.attachments[0].size_text == "2 KB"


def test_bse_parser_refuses_changed_shape():
    with pytest.raises(SourceSchemaError):
        parse_bse_api({"data": []}, "FXCO", NOW, "u")


PAGE = """Statement of Consolidated Financial Results (Rs in lakh) Quarter ended 30.09.2026 30.06.2026 30.09.2025
Revenue from operations 1,20,000.00 1,10,000.00 1,00,000.00 Other income 500.00 500.00 400.00
Finance costs 1,000.00 1,000.00 900.00 Depreciation 2,000.00 2,000.00 1,800.00
Profit before tax 15,000.00 14,000.00 12,000.00 Net profit 11,000.00 10,500.00 9,000.00"""


def test_results_block_converts_units_and_computes_in_code():
    raw = {"basis": "consolidated", "unit": "lakh", "columns": ["Quarter ended 30.09.2026", "30.06.2026", "30.09.2025"],
           "revenue": ["1,20,000.00", "1,10,000.00", "1,00,000.00"], "other_income": ["500.00", "500.00", "400.00"],
           "finance_costs": ["1,000.00", "1,000.00", "900.00"], "depreciation": ["2,000.00", "2,000.00", "1,800.00"],
           "pbt": ["15,000.00", "14,000.00", "12,000.00"], "pat": ["11,000.00", "10,500.00", "9,000.00"]}
    b = results_block(raw, PAGE, 3, "https://fixtures.finn.invalid/r.pdf", "FXCO", False, screener_latest=1200.0)
    rev, ebitda = b["rows"][0], b["rows"][1]
    assert b["periods"] == ["Sep 2026", "Jun 2026", "Sep 2025"] and b["from_filing"] and b["page"] == 3
    assert rev["latest"] == pytest.approx(1200.0) and round(rev["yoy"], 1) == 20.0 and round(rev["qoq"], 1) == 9.1
    assert ebitda["latest"] == pytest.approx(175.0)          # (15000 + 1000 + 2000 - 500) lakh = 175 crore
    assert b["check"]["ok"]


def test_results_block_drops_numbers_not_on_the_page():
    raw = {"unit": "lakh", "revenue": ["1,20,000.00", "1,10,000.00", "99,999.00"], "pbt": ["15,000.00", "", ""],
           "pat": ["77,777.00", "", ""]}
    assert results_block(raw, PAGE, 1, "u", "FXCO", False) is None      # PAT not on the page -> no block
    raw["pat"] = ["11,000.00", "", ""]
    b = results_block(raw, PAGE, 1, "u", "FXCO", False)
    assert b["rows"][0]["year_ago"] is None and any("left out" in n for n in b["notes"])


def test_summary_numbers_must_be_in_the_filing():
    src = "The rating of bank facilities of Rs 750 crore was upgraded to AA+ from AA."
    assert summary_ok("Rating on Rs 750 crore of bank loans upgraded to AA+.", src)
    assert not summary_ok("Rating on Rs 900 crore of loans upgraded.", src)


def test_period_labels():
    assert period_label("Quarter ended 30.09.2026") == "Sep 2026"
    assert period_label("Three months ended September 30, 2026") == "Sep 2026"


def test_digest_uses_filed_results_and_summaries(pipe):
    pipe.refresh_filings()
    d = pipe.digest(168)
    items = d.high + d.normal
    res = next(i for i in items if i.symbol == "FXCABLES" and i.category == "results")
    assert res.results and res.results.get("from_filing") and res.results["check"]["ok"]
    rating = next(i for i in items if i.symbol == "FXCABLES" and i.category == "credit_rating")
    assert rating.summary and "750" in rating.summary["text"] and rating.summary["url"].endswith("#page=1")

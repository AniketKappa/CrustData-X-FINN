import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from finn.config import load_portfolio
from finn.factory import FIXTURES
from finn.providers.announcements import (SourceSchemaError, dedup_key, parse_bse_rss, parse_nse_json,
                                          parse_nse_rss, parse_time)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 29, 19, 30, tzinfo=IST)
PF = load_portfolio(FIXTURES)
RSS = (FIXTURES / "nse_rss.xml").read_text(encoding="utf-8")


def test_rss_extracts_fields_and_preserves_subject():
    items = parse_nse_rss(RSS, PF, NOW, "u")
    first = items[0]
    assert first.symbol == "FXCABLES" and first.company_name == "Fixture Cables Ltd"
    assert first.subject == "Outcome of Board Meeting"                      # verbatim
    assert first.detail.startswith("The Board approved the unaudited financial results")
    assert first.filed_at == datetime(2026, 10, 29, 18, 42, tzinfo=IST)
    assert first.source_url.endswith("FXCABLES_29102026184200_Outcome.pdf")
    assert first.attachments[0].kind == "pdf"
    assert first.provenance.source_class.value == "PRIMARY_DOC" and first.provenance.fixture is False


def test_rss_skips_items_without_date_and_keeps_unmapped():
    items = parse_nse_rss(RSS, PF, NOW, "u")
    assert len(items) == 9                                                  # 10 items, 1 without pubDate
    other = [i for i in items if i.company_name.startswith("Unrelated")]
    assert other and other[0].symbol is None


@pytest.mark.parametrize("bad", ["not xml", "<html><body/></html>"])
def test_rss_schema_errors(bad):
    with pytest.raises(SourceSchemaError):
        parse_nse_rss(bad, PF, NOW, "u")


def test_json_parse_and_schema_check():
    rows = json.loads((FIXTURES / "nse_json.json").read_text())["FXCABLES"]
    items = parse_nse_json(rows, "FXCABLES", NOW, "u")
    assert items[0].exchange_id == "900001" and items[0].attachments[0].size_text == "312 KB"
    with pytest.raises(SourceSchemaError):
        parse_nse_json([{"symbol": "X", "desc": "y"}], "X", NOW, "u")            # seq_id missing
    with pytest.raises(SourceSchemaError):
        parse_nse_json({"unexpected": True}, "X", NOW, "u")
    assert parse_nse_json({"data": []}, "X", NOW, "u") == []


def test_same_filing_from_rss_and_json_has_one_uid():
    rss = parse_nse_rss(RSS, PF, NOW, "u")[0]
    js = parse_nse_json(json.loads((FIXTURES / "nse_json.json").read_text())["FXCABLES"], "FXCABLES", NOW, "u")[0]
    assert rss.uid == js.uid == "NSE:att:FXCABLES_29102026184200_Outcome.pdf"


def test_dedup_key_fallbacks():
    t = datetime(2026, 10, 29, 11, 10, 33, tzinfo=IST)
    assert dedup_key("NSE", attachment_url=None, exchange_id="42", symbol_or_name="X", filed_at=t, subject="s") == "NSE:id:42"
    a = dedup_key("NSE", attachment_url=None, exchange_id=None, symbol_or_name="x", filed_at=t, subject="Credit  Rating!")
    b = dedup_key("NSE", attachment_url=None, exchange_id=None, symbol_or_name="X",
                  filed_at=t.replace(second=1), subject="credit rating")
    assert a == b and a.startswith("NSE:h:")


def test_bse_rss_maps_scrip_code():
    items = parse_bse_rss((FIXTURES / "bse_rss.xml").read_text(), PF, NOW, "u")
    assert items[0].symbol == "FXPHARMA" and items[0].exchange == "BSE"


@pytest.mark.parametrize("raw,expected", [
    ("29-Oct-2026 18:42:00", datetime(2026, 10, 29, 18, 42, tzinfo=IST)),
    ("2026-10-29 18:42:00", datetime(2026, 10, 29, 18, 42, tzinfo=IST)),
    ("Thu, 29 Oct 2026 13:12:00 +0000", datetime(2026, 10, 29, 18, 42, tzinfo=IST)),
])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_parse_time_rejects_garbage():
    with pytest.raises(ValueError):
        parse_time("yesterday")

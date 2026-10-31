"""Pull research: documents, retrieval, validation and the promises ledger (fixtures only, no network)."""
from finn.factory import build_pipeline
from finn.research.claims import check_claims, numbers_in, quote_in, source_block
from finn.research.documents import Chunk, fiscal_label, pdf_pages
from finn.research.fixture import pdf_bytes
from finn.research.ledger import LedgerRow, evaluate, horizon_quarters
from finn.research.numbers import Fact


def _pipe():
    p = build_pipeline("fixture")
    p.refresh_all()
    return p


def test_fiscal_labels():
    assert [fiscal_label(x) for x in ("Oct 2026", "Jul 2026", "May 2026", "Feb 2026")] == \
        ["Q2 FY27", "Q1 FY27", "Q4 FY26", "Q3 FY26"]


def test_pdf_reading_keeps_pages():
    pages, total = pdf_pages(pdf_bytes(["Hello revenue grew 12 percent.", "Second line."]), 10)
    assert total == 1 and "12 percent" in pages[0]


def _chunk(text):
    return Chunk(id="d:3:0", doc_id="d", page=3, text=text, kind="transcript", title="Q2 FY27 call transcript", url="u")


def test_validator_drops_uncited_and_invented_numbers():
    ch = _chunk("Revenue grew 14.1 percent to Rs 2,418 crore. Margin was 10.7 percent.")
    f = Fact(id="F1", label="Debt-to-equity", value=0.0407, unit="x", period="FY26")
    _, smap = source_block([ch], [f])
    raw = {"claims": [
        {"text": "Revenue grew 14.1 percent to Rs 2,418 crore [S1].", "cites": ["S1"]},     # ok
        {"text": "Margin was 10.7 percent in Q2 FY27 [S1]", "cites": ["S1"]},              # ok: FY27 is a label
        {"text": "Margin will reach 15 percent [S1].", "cites": ["S1"]},                   # invented number
        {"text": "Revenue grew strongly.", "cites": []},                                    # no citation
        {"text": "Debt is low at 0.04 times [F1].", "cites": ["F1"]},                       # rounded fact is fine
        {"text": "Debt-to-equity is 0.5 [S9].", "cites": ["S9"]},                           # unknown source
    ], "gaps": ["No segment data."]}
    out = check_claims(raw, smap)
    assert [c.text for c in out.claims] == ["Revenue grew 14.1 percent to Rs 2,418 crore.",
                                            "Margin was 10.7 percent in Q2 FY27", "Debt is low at 0.04 times."]
    assert out.dropped == 3 and out.gaps == ["No segment data."]


def test_numbers_ignore_period_labels():
    assert numbers_in("In Q2 FY27 (2026) revenue rose 12.5% to ₹1,200 cr") == {"12.5", "1200"}


def test_quote_must_be_in_passage():
    p = "Management: Outlook: We expect revenue growth of 12 to 14 percent for FY27 on the back of capacity."
    assert quote_in("We expect revenue growth of 12 to 14 percent for FY27", p)
    assert not quote_in("We expect revenue growth of 20 to 25 percent in FY28 and beyond", p)


def test_horizons():
    assert horizon_quarters("FY27", "Q1 FY27") == [(2027, 1), (2027, 2), (2027, 3), (2027, 4)]
    assert horizon_quarters("Q3 FY27", "Q2 FY27") == [(2027, 3)]
    assert horizon_quarters("next quarter", "Q4 FY26") == [(2027, 1)]
    assert horizon_quarters("H2 FY27", "Q2 FY27") == [(2027, 3), (2027, 4)]
    assert horizon_quarters("over time", "Q2 FY27") is None


def test_ledger_verdicts_computed_in_code():
    acts = [{"period": p, "revenue": r, "opm": o, "pat": 1} for p, r, o in
            [("Jun 2025", 100, 12), ("Sep 2025", 100, 12), ("Jun 2026", 116, 12), ("Sep 2026", 112, 10)]]
    cite = {"doc_id": "d", "page": 1}
    row = lambda **k: LedgerRow(said_in="Q1 FY27 call", statement="", quote="", cite=cite, **k)  # noqa: E731
    assert evaluate(row(metric="revenue_growth", low=12, high=14, horizon="Q1 FY27", unit="%"), acts, "Q1 FY27").verdict == "beat"
    r = evaluate(row(metric="revenue_growth", low=12, high=14, horizon="FY27", unit="%"), acts, "Q1 FY27")
    assert r.verdict == "on_track" and round(r.actual, 1) == 14.0 and r.quarters == ["Jun 2026", "Sep 2026"]
    assert evaluate(row(metric="ebitda_margin", low=12, high=13, horizon="Q2 FY27", unit="%"), acts, "Q1 FY27").verdict == "missed"
    assert evaluate(row(metric="capex", low=400, high=400, horizon="FY27", unit="crore"), acts, "Q1 FY27").verdict == "unchecked"
    assert evaluate(row(metric="revenue_growth", low=10, high=10, horizon="Q4 FY27", unit="%"), acts, "Q1 FY27").verdict == "too_early"


def test_dossier_end_to_end_on_fixture_company():
    p = _pipe()
    job = p.research.build("FXCABLES")
    assert job["status"] == "done", job.get("error")
    assert {d["kind"] for d in job["documents"]} == {"transcript", "presentation", "annual_report"}
    assert all(d["status"] == "ok" for d in job["documents"])
    ids = {s["id"]: s["status"] for s in job["steps"]}
    assert ids["ledger"] == "done" and ids["business"] == "done"
    verdicts = {(r["horizon"], r["metric"]): r["verdict"] for r in job["sections"]["ledger"]["rows"]}
    assert verdicts[("FY27", "revenue_growth")] == "on_track"
    assert verdicts[("Q2 FY27", "revenue_growth")] == "missed"
    for c in job["sections"]["business"]["claims"]:
        assert c["cites"] and all(ci in job["sections"]["business"]["sources"] for ci in c["cites"])
    assert job["facts"] and any(s["id"] == "cash" for s in job["numbers"])
    # cached: a second start returns the saved dossier without rebuilding
    again = p.research.start("FXCABLES")
    assert again["status"] == "done" and again["started_at"] == job["started_at"]


def test_ask_answers_with_citations_only():
    p = _pipe()
    p.research.build("FXCABLES")
    a = p.research.ask("FXCABLES", "What did management say about margin?")
    assert a["status"] == "ok" and a["claims"]
    for c in a["claims"]:
        for ci in c["cites"]:
            assert ci in a["sources"] and a["sources"][ci]["url"]

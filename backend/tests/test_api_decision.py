"""New decision-support endpoints in fixture mode (no network; the fixture backfill gives 3 synthetic years)."""
import json

from fastapi.testclient import TestClient

from finn import api
from finn.decision import FORBIDDEN

client = TestClient(api.app)


def _strict(obj):
    json.loads(json.dumps(obj), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_data_status_and_history():
    st = client.get("/v1/data-status").json()
    assert st["backfill"]["done"] and st["with_1y_history"] >= 5
    h = client.get("/v1/history/FXCABLES", params={"days": 400}).json()
    assert h["bars"] > 250 and h["series"][0]["date"] < h["series"][-1]["date"]
    assert client.get("/v1/benchmark", params={"days": 30}).json()["bars"] > 10
    assert client.get("/v1/history/NOT A SYMBOL!").status_code == 422


def test_rank_endpoints_and_caveat():
    r = client.get("/v1/rank", params={"scope": "universe"}).json()
    assert r["caveat"].startswith("Experimental ranking") and r["items"]
    ranked = [x for x in r["items"] if x["rank"] is not None]
    assert ranked and all(1 <= x["rank"] <= 10 for x in ranked)
    one = client.get("/v1/rank/FXCABLES").json()
    assert {"rank", "grades", "groups", "label", "drivers", "data", "model_version", "caveat"} <= set(one)
    _strict(one)
    assert client.get("/v1/rank/INFY").status_code == 404


def test_backtest_latest():
    b = client.get("/v1/backtest/latest").json()
    assert "caveat" in b and "survivorship" in b["caveat"]
    if b["ok"]:
        assert b["months"] >= 12 and "nifty50" in b["portfolios"]
    _strict(b)


def test_flags_health_briefing():
    f = client.get("/v1/flags").json()
    assert "coverage_since" in f
    assert all({"symbol", "flag_type", "level", "source_id", "evidence"} <= set(x) for x in f["items"])
    ids = [x["source_id"] for x in f["items"]]
    assert len(ids) == len(set(ids))
    # NSE + BSE copies of the same CFO resignation count once
    assert sum(1 for x in f["items"] if x["symbol"] == "FXPHARMA" and x["flag_type"] == "top_exit") == 1
    h = client.get("/v1/portfolio/health").json()
    assert h["ok"] and 0 <= h["score"] <= 100 and h["weighting"] == "equal"
    b = client.get("/v1/agent/briefing").json()
    assert len(b["bullets"]) <= 6
    assert not any(p in json.dumps(b).lower() for p in FORBIDDEN)


def test_agent_ask_rules():
    r = client.post("/v1/agent/ask", json={"question": "What's the probability FXCABLES goes up?"}).json()
    assert r["refused"] and r["bottom_line"].startswith("Decision is yours.")
    r = client.post("/v1/agent/ask", json={"question": "How does FXCABLES look?"}).json()
    assert r["ok"] and r["symbol"] == "FXCABLES" and r["bottom_line"].startswith("Decision is yours.")
    assert not any(p in json.dumps(r).lower() for p in FORBIDDEN)
    assert client.post("/v1/agent/ask", json={"question": "hello"}).json()["ok"] is False


def test_digest_alerts_carry_why_and_company_has_rank():
    d = client.get("/v1/digest").json()
    alerts = [i for i in d["high"] + d["normal"] if i["kind"] == "market_alert"]
    assert alerts and all(i["why"] and i["why"]["summary"] for i in alerts)
    c = client.get("/v1/company/FXCABLES", params={"days": 400}).json()
    assert c["rank"]["symbol"] == "FXCABLES" and isinstance(c["flags"], list) and len(c["history_long"]) > 250
    m = client.get("/v1/moves/FXCABLES").json()
    assert m["ok"] and m["confidence_note"] in ("explained", "partly explained", "not explained")

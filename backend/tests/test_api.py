from fastapi.testclient import TestClient

from finn import api

client = TestClient(api.app)


def test_health_and_digest():
    assert client.get("/health").json()["mode"] == "fixture"
    d = client.get("/v1/digest").json()
    assert d["window_hours"] == 24 and d["fixture"] and d["high"]
    assert all(i["title"] for i in d["high"])


def test_threshold_params_and_validation():
    strict = client.get("/v1/digest", params={"price_pct": 7, "vol_mult": 3}).json()
    assert [i["symbol"] for i in strict["high"] if i["kind"] == "market_alert"] == ["FXCABLES"]
    assert client.get("/v1/digest", params={"window_hours": 5}).status_code == 422
    assert client.get("/v1/digest", params={"vol_mult": 0.5}).status_code == 422


def test_sources_and_market():
    assert {s["name"] for s in client.get("/v1/sources").json()} == {"prices", "nse_rss", "nse_json", "bse_rss", "bse_api", "news", "screener"}
    assert len(client.get("/v1/market").json()) == 9


def test_refresh_requires_secret_when_set(monkeypatch):
    monkeypatch.setenv("INGEST_SHARED_SECRET", "s3cr3t-value-for-test")
    assert client.post("/jobs/refresh").status_code == 401
    assert client.post("/jobs/refresh", headers={"X-Finn-Secret": "s3cr3t-value-for-test"}).status_code == 200


def test_portfolio_endpoint():
    p = client.get("/v1/portfolio").json()
    assert p["mode"] == "fixture" and len(p["holdings"]) == 8 and p["thresholds"]["pct_change_abs"] == 5.0


def test_web_app_served_at_root_and_api_routes_win():
    r = client.get("/")
    assert r.status_code == 200 and "FINN" in r.text and 'src="js/app.js"' in r.text
    assert client.get("/js/api.js").status_code == 200
    assert client.get("/health").json()["ok"] is True       # not shadowed by the static mount


def test_refresh_reports_and_is_serialised():
    r = client.post("/jobs/refresh").json()
    assert "prices" in r and "announcements" in r
    assert client.get("/health").json()["refresh"]["running"] is False


def test_holdings_add_search_remove_company(monkeypatch, tmp_path):
    from finn.config import load_portfolio
    from finn.factory import FIXTURES
    monkeypatch.setattr(api.pipe, "portfolio", load_portfolio(FIXTURES, tmp_path / "p.json"))
    h = client.get("/v1/holdings").json()
    assert len(h["holdings"]) == 8 and h["holdings"][0]["signal"]["close"]
    assert client.get("/v1/search", params={"q": "cables"}).json()["results"][0]["symbol"] == "FXCABLES"
    r = client.post("/v1/holdings/add", json={"symbol": "FXNEW2", "name": "Fixture New Two Ltd"}).json()
    assert r["added"]["news_terms"] == ["Fixture New Two"]
    assert "FXNEW2" in [c["symbol"] for c in client.get("/v1/holdings").json()["holdings"]]
    assert client.post("/v1/holdings/add", json={"symbol": "BAD SYMBOL!", "name": "x"}).status_code == 422
    assert client.post("/v1/holdings/remove", json={"symbol": "FXNEW2"}).status_code == 200
    assert client.post("/v1/holdings/remove", json={"symbol": "FXNEW2"}).status_code == 404
    c = client.get("/v1/company/FXCABLES").json()
    assert c["snapshot"]["name"] == "Fixture Cables Ltd" and c["results"]


def test_static_assets_are_revalidated():
    assert client.get("/js/app.js").headers["cache-control"] == "no-cache"


def test_background_refresh_and_health_flags():
    r = client.post("/jobs/refresh", params={"background": True}).json()
    assert r["running"] is True
    h = client.get("/health").json()
    assert set(h) >= {"refresh", "llm", "web_search"} and "last_result" not in h["refresh"]


def test_research_endpoints_fixture():
    r = client.post("/v1/research/FXCABLES/start")
    assert r.status_code == 200 and r.json()["symbol"] == "FXCABLES"
    import time
    for _ in range(50):
        st = client.get("/v1/research/FXCABLES").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert st["status"] == "done"
    a = client.post("/v1/research/FXCABLES/ask", json={"question": "What is the outlook for margins?"}).json()
    assert a["status"] == "ok" and a["claims"]
    assert client.post("/v1/research/bad sym!/start").status_code == 422

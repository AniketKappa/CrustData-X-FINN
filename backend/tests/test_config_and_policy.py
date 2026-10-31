import re
from pathlib import Path

from finn.config import REPO_DIR, load_portfolio, load_settings
from finn.factory import FIXTURES
from finn.symbols import normalize


def test_demo_portfolio_shape():
    p = load_portfolio()
    assert 15 <= len(p.holdings) <= 20 and 3 <= len(p.research) <= 5
    assert len({c.sector for c in p.holdings}) >= 12 and {c.size for c in p.holdings} == {"large", "mid", "small"}
    for c in p.holdings + p.research:
        normalize(c.symbol)
        if c.bse_code:
            assert normalize(c.bse_code).exchange == "BSE"


def test_name_matching_for_rss():
    p = load_portfolio()
    assert p.match_name("Infosys Limited").symbol == "INFY"
    assert p.match_name("The Tata Power Company Limited").symbol == "TATAPOWER"
    assert p.match_name("Larsen & Toubro Limited").symbol == "LT"
    assert p.match_name("Unknown Co Ltd") is None


def test_thresholds_configurable_from_env(monkeypatch):
    monkeypatch.setenv("ALERT_PRICE_PCT", "3.5")
    monkeypatch.setenv("ALERT_VOLUME_MULTIPLE", "2.5")
    th = load_settings().thresholds
    assert th.pct_change_abs == 3.5 and th.volume_multiple == 2.5


def test_fixtures_are_synthetic_only():
    """D-31: fixtures may hold only synthetic data; no real exchange links or real portfolio symbols."""
    real = {c.symbol for c in load_portfolio().companies.values()}
    for f in FIXTURES.iterdir():
        text = f.read_text(encoding="utf-8")
        assert "nseindia.com" not in text and "bseindia.com" not in text, f
        urls = re.findall(r"https?://([^/\s\"<]+)", text)
        assert all(u.endswith(".invalid") for u in urls), (f, urls)
        for sym in real:
            assert not re.search(rf"\b{re.escape(sym)}\b", text), (f, sym)


def test_no_secrets_committed():
    pat = re.compile(r"(API_KEY|SECRET|TOKEN)\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")
    for path in REPO_DIR.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".md", ".example", ".toml", ".txt", ".js"} \
                and "node_modules" not in path.parts and ".venv" not in path.parts:
            assert not pat.search(path.read_text(encoding="utf-8", errors="ignore")), path

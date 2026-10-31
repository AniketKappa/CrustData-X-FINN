"""Configuration: committed YAML files plus environment overrides. No secrets live here."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .models import AlertThresholds, Company

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("FINN_CONFIG_DIR", BACKEND_DIR / "config"))
REPO_DIR = BACKEND_DIR.parent


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from the repo's .env (gitignored) into os.environ, without overriding real env vars."""
    path = path or (REPO_DIR / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip() if not line.strip().startswith("#") else ""
        if "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


def _load(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name, "").strip()
    return float(v) if v else default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


@dataclass
class Portfolio:
    companies: dict[str, Company]                          # by NSE symbol
    user_path: Optional[Path] = None                       # where app edits are saved (None = read-only)

    @property
    def holdings(self) -> list[Company]:
        return [c for c in self.companies.values() if c.role == "holding"]

    @property
    def research(self) -> list[Company]:
        return [c for c in self.companies.values() if c.role == "research"]

    def role_of(self, symbol: str | None) -> str:
        c = self.companies.get(symbol or "")
        return c.role if c else "other"

    def by_bse_code(self, code: str) -> Company | None:
        return next((c for c in self.companies.values() if c.bse_code == code), None)

    def match_name(self, name: str) -> Company | None:
        """Map an exchange company name (RSS items carry no symbol) to a configured company."""
        key = _name_key(name)
        if not key:
            return None
        for c in self.companies.values():
            for candidate in [c.name, *c.aliases]:
                if _name_key(candidate) == key:
                    return c
        return None


    # ---------- edits from the app (Portfolio tab) ----------
    def add(self, company: Company) -> Company:
        existing = self.companies.get(company.symbol)
        if existing is not None:
            company = existing.model_copy(update={"role": company.role})
        if not company.news_terms:
            company.news_terms = [default_news_term(company.name)]
        if not company.aliases:
            company.aliases = [company.name]
        self.companies[company.symbol] = company
        self.save()
        return company

    def remove(self, symbol: str) -> bool:
        removed = self.companies.pop(symbol, None) is not None
        if removed:
            self.save()
        return removed

    def save(self) -> None:
        if self.user_path is None:
            return
        import json

        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"holdings": [c.model_dump(exclude={"role"}) for c in self.holdings],
                "research": [c.model_dump(exclude={"role"}) for c in self.research]}
        tmp = self.user_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(self.user_path)


_SUFFIX = re.compile(r"\b(limited|ltd|the|company|co|india|\(india\))\b")


def _name_key(name: str) -> str:
    s = (name or "").lower().replace("&", " and ").replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _SUFFIX.sub(" ", s)
    return " ".join(s.split())


def default_news_term(name: str) -> str:
    base = re.sub(r"\(.*?\)", " ", name)
    base = re.sub(r"\b(ltd|limited|the|company|co|corporation|corp)\b\.?", " ", base, flags=re.I)
    return " ".join(base.replace(".", " ").split()).strip(" ,")


def load_portfolio(config_dir: Path | None = None, user_path: Path | None = None) -> Portfolio:
    """The committed demo list, unless the user has edited the portfolio in the app (user_path exists)."""
    if user_path is not None and user_path.exists():
        import json

        raw = json.loads(user_path.read_text(encoding="utf-8"))
    else:
        raw = _load("portfolio.yaml", config_dir)
    companies: dict[str, Company] = {}
    for role, rows in (("holding", raw.get("holdings", [])), ("research", raw.get("research", []))):
        for r in rows:
            c = Company(role=role, **{k: v for k, v in r.items() if k != "role"})
            companies[c.symbol] = c
    return Portfolio(companies, user_path)


@dataclass
class Settings:
    thresholds: AlertThresholds
    staleness_days: int
    ranking: dict[str, Any]
    sources: dict[str, Any]
    db_path: str
    fixture_mode: bool
    raw_alerts: dict[str, Any] = field(default_factory=dict)


def load_settings(config_dir: Path | None = None) -> Settings:
    alerts = _load("alerts.yaml", config_dir)
    thresholds = AlertThresholds(
        pct_change_abs=_env_float("ALERT_PRICE_PCT", alerts["price"]["pct_change_abs"]),
        volume_multiple=_env_float("ALERT_VOLUME_MULTIPLE", alerts["volume"]["multiple"]),
        lookback_sessions=_env_int("ALERT_VOLUME_LOOKBACK_SESSIONS", alerts["volume"]["lookback_sessions"]),
        min_history_sessions=alerts["volume"]["min_history_sessions"],
    )
    db = os.environ.get("FINN_DB_PATH") or str(REPO_DIR / "data" / "finn.db")
    return Settings(
        thresholds=thresholds,
        staleness_days=alerts.get("staleness", {}).get("max_age_trading_days", 1),
        ranking=_load("ranking.yaml", config_dir),
        sources=_load("sources.yaml", config_dir),
        db_path=db,
        fixture_mode=os.environ.get("FINN_DATA_MODE", "live").lower() == "fixture",
        raw_alerts=alerts,
    )

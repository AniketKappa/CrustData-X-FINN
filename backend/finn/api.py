"""HTTP API (ARCHITECTURE §10) and the web app.

Read endpoints serve the store only. /jobs/refresh is the only path that fetches; it is protected by
INGEST_SHARED_SECRET when set and limited by per-source TTLs. In live mode one background refresh runs at
start-up (ephemeral store, ARCHITECTURE §4b). The prototype UI in design/prototype is served at "/", so the
app and the API share an origin: `uvicorn finn.api:app` starts both.
"""
from __future__ import annotations

import hmac
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import time
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import REPO_DIR
from .factory import build_pipeline
from .models import AlertThresholds, Company, Digest, MarketSignal, SourceStatus
from .providers.search import yahoo_search
from .symbols import SymbolError, normalize

_search_fn = yahoo_search

MODE = "fixture" if os.environ.get("FINN_DATA_MODE", "live").lower() == "fixture" else "live"
pipe = build_pipeline(MODE)
if MODE == "fixture":
    pipe.refresh_all()

_refresh_lock = threading.Lock()
_refresh_state: dict = {"running": False, "last_started": None, "last_finished": None, "last_result": None,
                        "last_error": None}


def _do_refresh(force: bool = False) -> dict:
    """Runs one refresh at a time; a second caller gets the running state instead of a parallel fetch."""
    if not _refresh_lock.acquire(blocking=False):
        return {"running": True}
    try:
        _refresh_state.update(running=True, last_started=datetime.now(timezone.utc).isoformat(), last_error=None)
        result = pipe.refresh_all(force=force)
        _refresh_state["last_result"] = result
        return result
    except Exception as e:  # noqa: BLE001 - a refresh must never take the API down
        _refresh_state["last_error"] = f"{e.__class__.__name__}: {e}"
        raise
    finally:
        _refresh_state.update(running=False, last_finished=datetime.now(timezone.utc).isoformat())
        _refresh_lock.release()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if MODE == "live" and os.environ.get("FINN_REFRESH_ON_START", "1") != "0":
        threading.Thread(target=lambda: _safe(_do_refresh), daemon=True).start()
    yield


def _safe(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001 - recorded in _refresh_state
        pass


app = FastAPI(title="FINN API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("FINN_CORS_ORIGINS", "*").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.middleware("http")
async def no_stale_assets(request, call_next):
    """The app's JS modules change between versions; without this, browsers may reuse a cached old module and
    fail to start. 'no-cache' still allows cheap 304 revalidation."""
    response = await call_next(request)
    if not request.url.path.startswith(("/v1/", "/jobs/", "/health")):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
def health() -> dict:
    return {"ok": True, "mode": MODE, "announcements": pipe.store.count_announcements(),
            "refresh": {k: v for k, v in _refresh_state.items() if k != "last_result"},
            "llm": bool(pipe.llm and pipe.llm.available), "web_search": bool(os.environ.get("TAVILY_API_KEY")),
            "research_llm": bool(pipe.research and pipe.research.llm and pipe.research.llm.available),
            "llm_models": [f"{p}/{m}" for p, _, _, m in pipe.llm.slots("long")] if pipe.llm else []}


def _thresholds(price_pct: Optional[float], vol_mult: Optional[float], lookback: Optional[int]) -> AlertThresholds:
    base = pipe.s.thresholds.model_dump()
    for k, v in (("pct_change_abs", price_pct), ("volume_multiple", vol_mult), ("lookback_sessions", lookback)):
        if v is not None:
            base[k] = v
    try:
        return AlertThresholds(**base)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/v1/digest", response_model=Digest)
def digest(window_hours: int = Query(24), price_pct: Optional[float] = None, vol_mult: Optional[float] = None,
           lookback: Optional[int] = None) -> Digest:
    try:
        return pipe.digest(window_hours, _thresholds(price_pct, vol_mult, lookback))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/v1/market", response_model=list[MarketSignal])
def market(price_pct: Optional[float] = None, vol_mult: Optional[float] = None, lookback: Optional[int] = None):
    return pipe.market_signals(_thresholds(price_pct, vol_mult, lookback))


@app.get("/v1/sources", response_model=list[SourceStatus])
def sources():
    return pipe.source_status()


@app.get("/v1/portfolio")
def portfolio() -> dict:
    p = pipe.portfolio
    return {"mode": MODE, "holdings": [c.model_dump() for c in p.holdings],
            "research": [c.model_dump() for c in p.research], "thresholds": pipe.s.thresholds.model_dump()}


# ---------------------------------------------------------------- portfolio (Portfolio tab)
@app.get("/v1/holdings")
def holdings(price_pct: Optional[float] = None, vol_mult: Optional[float] = None) -> dict:
    sig = {s.symbol: s.model_dump(mode="json") for s in pipe.market_signals(_thresholds(price_pct, vol_mult, None))}
    row = lambda c: {**c.model_dump(), "signal": sig.get(c.symbol)}  # noqa: E731
    return {"holdings": [row(c) for c in pipe.portfolio.holdings], "watchlist": [row(c) for c in pipe.portfolio.research],
            "editable": pipe.portfolio.user_path is not None or MODE == "fixture"}


class AddRequest(BaseModel):
    symbol: str
    name: str
    sector: Optional[str] = None
    role: str = "holding"            # holding | research (watchlist)


@app.post("/v1/holdings/add")
def add_holding(req: AddRequest) -> dict:
    try:
        inst = normalize(req.symbol)
    except SymbolError as e:
        raise HTTPException(422, str(e)) from e
    if req.role not in ("holding", "research"):
        raise HTTPException(422, "role must be holding or research")
    c = pipe.add_company(Company(symbol=inst.code, name=req.name.strip() or inst.code, sector=req.sector, role=req.role))
    threading.Thread(target=lambda: _safe(lambda: pipe.refresh_symbol(c.symbol)), daemon=True).start()
    return {"added": c.model_dump(), "refreshing": True}


class RemoveRequest(BaseModel):
    symbol: str


@app.post("/v1/holdings/remove")
def remove_holding(req: RemoveRequest) -> dict:
    if not pipe.portfolio.remove(req.symbol.upper()):
        raise HTTPException(404, f"{req.symbol} is not in the portfolio")
    return {"removed": req.symbol.upper()}


@app.get("/v1/search")
def search(q: str = Query(..., min_length=1, max_length=60)) -> dict:
    """Yahoo Finance search (NSE/BSE equities); falls back to the portfolio list if Yahoo is unreachable."""
    ql = q.strip().lower()
    local = [{"symbol": c.symbol, "name": c.name, "sector": c.sector, "exchange": "NSE", "source": "your list"}
             for c in pipe.portfolio.companies.values() if ql in c.symbol.lower() or ql in c.name.lower()]
    if MODE == "fixture":
        extra = [{"symbol": "FXSOLAR", "name": "Fixture Solar Tubes Ltd", "sector": "Solar (fixture)", "exchange": "NSE",
                  "source": "fixture"}]
        return {"results": local + [e for e in extra if ql in e["name"].lower() or ql in e["symbol"].lower()],
                "note": "Demo mode searches invented companies only."}
    try:
        return {"results": _search_fn(q.strip(), 10), "note": None}
    except Exception as e:  # noqa: BLE001 - search provider failure must not break the screen
        return {"results": local, "note": f"Stock search is unavailable right now ({e.__class__.__name__})."}


@app.get("/v1/company/{symbol}")
def company(symbol: str) -> dict:
    sym = symbol.upper()
    try:
        normalize(sym)
    except SymbolError as e:
        raise HTTPException(422, str(e)) from e
    if MODE == "live":
        # Opening a company fetches what is missing or old: prices (30-min cache, so in-session prices are
        # current) and fundamentals (12-h cache). TTLs and failure back-off still apply.
        pipe.refresh_prices([sym])
        if pipe.screener is not None:
            pipe.refresh_companies([sym])
    return pipe.company_view(sym)


# ---------------------------------------------------------------- Pull research (any NSE ticker)
# A public deployment shares one set of free model keys, so each visitor gets a fair share per hour.
_hits: dict[str, deque] = defaultdict(deque)
LIMITS = {"ask": (int(os.environ.get("FINN_ASK_PER_HOUR", "40")), 3600),
          "build": (int(os.environ.get("FINN_BUILDS_PER_HOUR", "12")), 3600)}


def _limit(request: Request, kind: str) -> None:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "?")
    n, window = LIMITS[kind]
    q, now = _hits[f"{kind}:{ip}"], time.monotonic()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, f"Hourly limit reached ({n} {'questions' if kind == 'ask' else 'research builds'}). "
                                 "Try again later.")
    q.append(now)


def _sym(symbol: str) -> str:
    sym = symbol.upper().strip()
    try:
        normalize(sym)
    except SymbolError as e:
        raise HTTPException(422, str(e)) from e
    return sym


@app.post("/v1/research/{symbol}/start")
def research_start(symbol: str, request: Request, force: bool = False) -> dict:
    """Starts (or returns) the dossier build. One build per company runs at a time; finished dossiers are cached 24 h."""
    sym = _sym(symbol)
    st = pipe.research.status(sym)
    if force or st.get("status") in ("idle", "failed"):
        _limit(request, "build")                   # only new builds count; cached dossiers are free
    return pipe.research.start(sym, force=force)


@app.get("/v1/research/{symbol}")
def research_status(symbol: str) -> dict:
    return pipe.research.status(_sym(symbol))


class AskRequest(BaseModel):
    question: str


@app.post("/v1/research/{symbol}/ask")
def research_ask(symbol: str, req: AskRequest, request: Request) -> dict:
    if not req.question.strip():
        raise HTTPException(422, "question is empty")
    _limit(request, "ask")
    return pipe.research.ask(_sym(symbol), req.question)


@app.post("/jobs/refresh")
def refresh(force: bool = False, background: bool = False, x_finn_secret: Optional[str] = Header(None)) -> dict:
    secret = os.environ.get("INGEST_SHARED_SECRET", "")
    if secret and not hmac.compare_digest(secret, x_finn_secret or ""):
        raise HTTPException(401, "missing or wrong X-Finn-Secret")
    if background:   # the app calls this on open; it polls /health and reloads when the fetch finishes
        if _refresh_state["running"]:
            return {"started": False, "running": True}
        threading.Thread(target=lambda: _safe(lambda: _do_refresh(force)), daemon=True).start()
        return {"started": True, "running": True}
    try:
        return _do_refresh(force)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"refresh failed: {e}") from e


# The web app. Mounted last so API routes win. html=True serves index.html at "/".
_UI = REPO_DIR / "design" / "prototype"
if _UI.is_dir() and os.environ.get("FINN_SERVE_UI", "1") != "0":
    app.mount("/", StaticFiles(directory=_UI, html=True), name="ui")

__all__ = ["app", "Company"]

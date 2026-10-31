"""Stock search for the Portfolio tab: Yahoo Finance search via yfinance, NSE/BSE equities only.
Falls back to matching the known portfolio when the provider is unreachable."""
from __future__ import annotations

from typing import Callable

from ..symbols import try_normalize

SearchFn = Callable[[str, int], list[dict]]


def yahoo_search(query: str, limit: int = 10) -> list[dict]:
    import yfinance as yf  # lazy: tests and fixture mode never import the network client

    res = yf.Search(query, max_results=limit * 2, news_count=0)
    out = []
    for q in getattr(res, "quotes", []) or []:
        sym, exch = q.get("symbol", ""), q.get("exchange", "")
        if q.get("quoteType") != "EQUITY" or not (sym.endswith(".NS") or sym.endswith(".BO")):
            continue
        inst = try_normalize(sym)
        if inst is None:
            continue
        out.append({"symbol": inst.code if inst.exchange == "NSE" else sym, "exchange": inst.exchange, "yahoo": sym,
                    "name": q.get("longname") or q.get("shortname") or inst.code, "sector": q.get("sectorDisp") or q.get("sector"),
                    "source": f"Yahoo Finance ({exch})"})
    nse = [o for o in out if o["exchange"] == "NSE"]
    return (nse or out)[:limit]

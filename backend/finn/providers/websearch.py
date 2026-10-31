"""Web search for people backgrounds: Tavily (free plan, 1,000 credits/month, key in `.env` as TAVILY_API_KEY).
Returns title, url and a content snippet; FINN keeps short sourced sentences, never whole pages."""
from __future__ import annotations

import os
from typing import Optional

import httpx

EXCLUDE = ["linkedin.com"]   # D-51: LinkedIn's terms forbid scraping; its pages are never used


def tavily_search(query: str, max_results: int = 5, client: Optional[httpx.Client] = None) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    c = client or httpx.Client(timeout=20)
    r = c.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "search_depth": "basic",
                                                      "max_results": max_results, "exclude_domains": EXCLUDE})
    if r.status_code != 200:
        raise httpx.HTTPStatusError(f"Tavily HTTP {r.status_code}", request=r.request, response=r)
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("content", "")}
            for x in r.json().get("results", []) if "linkedin.com" not in (x.get("url") or "")]

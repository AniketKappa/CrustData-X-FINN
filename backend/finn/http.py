"""HTTP client with timeouts, bounded retries, exponential backoff and a per-host politeness delay.

Retries only on transient failures (timeouts, connection errors, 429, 5xx). Never retries 4xx other
than 429, and never tries to get around a 401/403 (D-38 guardrails: no login/CAPTCHA/rate-limit bypass).
Tests inject an httpx.MockTransport and a fake sleep, so no test touches the network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A fetch that failed after all permitted attempts. `kind` is shown in source status."""

    def __init__(self, url: str, kind: str, detail: str, status: Optional[int] = None, attempts: int = 0):
        super().__init__(f"{kind}: {detail} ({url})")
        self.url, self.kind, self.detail, self.status, self.attempts = url, kind, detail, status, attempts


@dataclass
class HttpPolicy:
    timeout_seconds: float = 10.0
    max_retries: int = 2
    backoff_seconds: float = 1.0
    backoff_cap_seconds: float = 8.0
    min_delay_seconds: float = 1.0
    user_agent: str = "FINN-research-prototype/0.1"

    @classmethod
    def from_config(cls, cfg: dict) -> "HttpPolicy":
        return cls(**{k: cfg[k] for k in cls.__dataclass_fields__ if k in cfg})


class HttpClient:
    def __init__(self, policy: HttpPolicy | None = None, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.policy = policy or HttpPolicy()
        self._sleep, self._clock = sleep, clock
        self._last_hit: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=self.policy.timeout_seconds,
            headers={"User-Agent": self.policy.user_agent, "Accept": "*/*"},
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _polite_wait(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.policy.min_delay_seconds - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_hit[host] = self._clock()

    def get(self, url: str, headers: dict | None = None) -> httpx.Response:
        attempts = 1 + max(0, self.policy.max_retries)
        last_err: FetchError | None = None
        for i in range(attempts):
            self._polite_wait(url)
            try:
                r = self._client.get(url, headers=headers)
            except httpx.TimeoutException as e:
                last_err = FetchError(url, "timeout", str(e) or "timed out", attempts=i + 1)
            except httpx.TransportError as e:
                last_err = FetchError(url, "network", str(e) or e.__class__.__name__, attempts=i + 1)
            else:
                if r.status_code < 400:
                    return r
                kind = "rate_limited" if r.status_code == 429 else "http"
                last_err = FetchError(url, kind, f"HTTP {r.status_code}", status=r.status_code, attempts=i + 1)
                if r.status_code not in RETRYABLE_STATUS:
                    raise last_err             # 401/403/404 etc.: do not retry, do not work around
                retry_after = _retry_after(r)
                if retry_after is not None and i < attempts - 1:
                    self._sleep(min(retry_after, self.policy.backoff_cap_seconds))
                    continue
            if i < attempts - 1:
                self._sleep(min(self.policy.backoff_seconds * (2 ** i), self.policy.backoff_cap_seconds))
        assert last_err is not None
        raise last_err


def _retry_after(r: httpx.Response) -> float | None:
    v = r.headers.get("retry-after")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None

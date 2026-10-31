"""Free-tier LLM access through OpenAI-compatible chat APIs (Q-1, R-35: free tiers only).

Two routes, each an ordered list of slots (provider + model). A slot is skipped when its key is missing,
when it is over its own per-minute token budget, or when it fails (429/5xx/timeout); the next slot is tried.

  fast  (bulk extraction: guidance statements)   groq gpt-oss-20b -> groq llama-3.1-8b-instant -> openrouter free
  long  (reasoning: cited synthesis, answers)    groq gpt-oss-120b -> groq llama-3.3-70b-versatile -> openrouter free

Groq free plan, per model (console.groq.com/docs/rate-limits, as reported Aug–Sep 2026): gpt-oss-120b and
gpt-oss-20b 30 RPM / 8K TPM / 200K TPD; llama-3.3-70b 12K TPM / 100K TPD; llama-3.1-8b 6K TPM / 500K TPD.
OpenRouter free models: 20 RPM, 50 requests/day without credits. Limits can be overridden in `.env`
(LLM_TPM_<MODEL>), and Groq's own x-ratelimit headers are respected when present.

Keys live only in `.env` (never committed). Responses are cached in memory by a hash of route, prompt and
system prompt; a call log keeps provider, model, tokens and latency for the "About this answer" view.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
}
ROUTES: dict[str, list[tuple[str, str]]] = {
    "fast": [("groq", "openai/gpt-oss-20b"), ("groq", "llama-3.1-8b-instant"), ("openrouter", "openrouter/free")],
    "long": [("groq", "openai/gpt-oss-120b"), ("groq", "llama-3.3-70b-versatile"), ("openrouter", "openrouter/free")],
}
TPM = {"openai/gpt-oss-20b": 8000, "openai/gpt-oss-120b": 8000, "llama-3.3-70b-versatile": 12000,
       "llama-3.1-8b-instant": 6000, "openrouter/free": 100000}
MAX_WAIT_S = 45.0          # wait this long at most for a model's minute budget to free up (Groq budgets reset each minute)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class CallRecord:
    route: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    ms: int
    ok: bool
    error: Optional[str] = None


class _Budget:
    """Tokens spent per model in the last 60 s, so calls are paced instead of bouncing off 429s."""

    def __init__(self, clock: Callable[[], float]):
        self.clock, self.used, self.lock = clock, {}, threading.Lock()

    def _window(self, model: str) -> deque:
        q = self.used.setdefault(model, deque())
        now = self.clock()
        while q and now - q[0][0] > 60:
            q.popleft()
        return q

    def wait_needed(self, model: str, tokens: int, limit: int) -> float:
        with self.lock:
            q = self._window(model)
            spent = sum(t for _, t in q)
            if spent + tokens <= limit or not q:
                return 0.0
            need, acc = spent + tokens - limit, 0
            for at, t in q:            # oldest first: how long until enough tokens leave the window
                acc += t
                if acc >= need:
                    return max(0.0, 60 - (self.clock() - at)) + 0.5
            return 60.0

    def spend(self, model: str, tokens: int) -> None:
        with self.lock:
            self._window(model).append((self.clock(), tokens))


class LLM:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._cache: dict[str, str] = {}
        self._sleep = sleep
        self.budget = _Budget(clock)
        self.log: deque[CallRecord] = deque(maxlen=200)
        self.last_provider: Optional[str] = None
        self.last_model: Optional[str] = None
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ configuration
    def _key(self, provider: str) -> str:
        return os.environ.get(PROVIDERS[provider][0], "").strip()

    def slots(self, route: str) -> list[tuple[str, str, str, str]]:
        """(provider, key, base_url, model) for each configured slot, in order. Env overrides:
        LLM_<ROUTE>_MODELS="groq:model,openrouter:model"; the older GROQ_MODEL / OPENROUTER_MODEL still work."""
        spec = os.environ.get(f"LLM_{route.upper()}_MODELS", "").strip()
        pairs = [tuple(p.split(":", 1)) for p in spec.split(",") if ":" in p] if spec else list(ROUTES[route])
        if route == "long" and not spec:
            if os.environ.get("GROQ_MODEL"):
                pairs[0] = ("groq", os.environ["GROQ_MODEL"].strip())
            if os.environ.get("OPENROUTER_MODEL"):
                pairs[-1] = ("openrouter", os.environ["OPENROUTER_MODEL"].strip())
        out = []
        for prov, model in pairs:
            prov = prov.strip()
            if prov in PROVIDERS and self._key(prov):
                out.append((prov, self._key(prov), PROVIDERS[prov][1], model.strip()))
        return out

    def providers(self) -> list:
        return self.slots("long")

    @property
    def available(self) -> bool:
        return bool(self.slots("long"))

    def _tpm(self, model: str) -> int:
        env = os.environ.get("LLM_TPM_" + re.sub(r"[^A-Z0-9]", "_", model.upper()), "")
        return int(env) if env.isdigit() else TPM.get(model, 8000)

    # ------------------------------------------------------------ calls
    def __call__(self, prompt: str, system: str | None = None, max_tokens: int = 700) -> Optional[str]:
        return self.complete(prompt, system=system, max_tokens=max_tokens, route="long")

    def complete(self, prompt: str, system: str | None = None, max_tokens: int = 900, route: str = "long",
                 json_mode: bool = False) -> Optional[str]:
        h = hashlib.sha256(f"{route}|{json_mode}|{system}|{prompt}".encode()).hexdigest()
        if h in self._cache:
            return self._cache[h]
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        need = est_tokens((system or "") + prompt) + max_tokens
        # Prefer a model that has budget right now (so parallel calls spread over models instead of queueing on one);
        # if every model is busy, wait for whichever frees up first. Failures fall through to the next slot.
        tried: set[str] = set()
        for _ in range(4):
            cands = []
            for i, (prov, key, base, model) in enumerate(self.slots(route)):
                if model in tried or need > self._tpm(model):
                    continue
                cands.append((self.budget.wait_needed(model, need, self._tpm(model)), i, prov, key, base, model))
            if not cands:
                return None
            wait, _, prov, key, base, model = min(cands, key=lambda c: (c[0] > 0, c[0], c[1]))
            if wait > MAX_WAIT_S:
                self.last_error = f"{model}: minute budget used"
                return None
            if wait:
                self._sleep(wait)
            tried.add(model)
            text = self._post(route, prov, key, base, model, msgs, max_tokens, json_mode, need)
            if text:
                self._cache[h] = text
                return text
        return None

    def complete_json(self, prompt: str, system: str | None = None, max_tokens: int = 900,
                      route: str = "long") -> Optional[dict]:
        text = self.complete(prompt, system=system, max_tokens=max_tokens, route=route, json_mode=True)
        return parse_json(text) if text else None

    def _post(self, route, prov, key, base, model, msgs, max_tokens, json_mode, need) -> Optional[str]:
        body: dict = {"model": model, "messages": msgs, "temperature": 0.1, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if prov == "groq" and model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"               # reasoning tokens count against the minute budget
        headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "http://localhost", "X-Title": "FINN"}
        for attempt in range(2):
            t0 = time.monotonic()
            try:
                r = self._client.post(f"{base}/chat/completions", headers=headers, json=body)
            except httpx.HTTPError as e:
                self._record(route, prov, model, need, 0, t0, False, e.__class__.__name__)
                return None
            if r.status_code == 400 and attempt == 0 and ("response_format" in body or "reasoning_effort" in body):
                body.pop("response_format", None)          # some models reject these options: retry plainly
                body.pop("reasoning_effort", None)
                continue
            if r.status_code == 429:
                self.budget.spend(model, self._tpm(model))  # treat the minute as used up
                self._record(route, prov, model, need, 0, t0, False, "HTTP 429")
                return None
            if r.status_code != 200:
                self._record(route, prov, model, need, 0, t0, False, f"HTTP {r.status_code}")
                return None
            try:
                data = r.json()
                text = (data["choices"][0]["message"].get("content") or "").strip()
                usage = data.get("usage") or {}
            except (KeyError, IndexError, ValueError):
                self._record(route, prov, model, need, 0, t0, False, "unexpected response")
                return None
            spent = int(usage.get("total_tokens") or need)
            self.budget.spend(model, spent)
            self._record(route, prov, model, int(usage.get("prompt_tokens") or 0),
                         int(usage.get("completion_tokens") or 0), t0, bool(text), None if text else "empty")
            if text:
                self.last_provider, self.last_model = prov, model
                return text
            return None
        return None

    def _record(self, route, prov, model, pt, ct, t0, ok, err):
        self.log.append(CallRecord(route, prov, model, pt, ct, int((time.monotonic() - t0) * 1000), ok, err))
        if not ok:
            self.last_error = f"{prov}/{model}: {err}"

    def usage_summary(self) -> dict:
        calls = list(self.log)
        return {"calls": len(calls), "ok": sum(c.ok for c in calls),
                "tokens": sum(c.prompt_tokens + c.completion_tokens for c in calls),
                "by_model": {m: sum(1 for c in calls if c.model == m and c.ok) for m in {c.model for c in calls}},
                "last_error": self.last_error}


def parse_json(text: str) -> Optional[dict]:
    """JSON object from a model reply, tolerating ```json fences or a sentence around it."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else {"items": v}
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            v = json.loads(t[a:b + 1])
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None

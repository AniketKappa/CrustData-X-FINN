"""Wires finn.decision (pure maths and rules) to the pipeline's store, sources and LLM.

Long price history: one background backfill per server start (the store is ephemeral on Render free, ARCH §4b),
10 years by default, for every tracked stock plus Nifty indices. The 60-day refresh keeps running as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .classify import classify
from .decision import (REFUSAL, StockInputs, backtest, clean, fallback_explanation, flag_for, has_forbidden,
                       HealthInputs, numbers_in, portfolio_health, rank_payload, score_universe,
                       validate_explanation, RANK_CAVEAT)
from .market import expected_session
from .models import Instrument
from .providers.prices import PriceProviderError
from .symbols import SymbolError, normalize

INDICES = {"NIFTY50": ("^NSEI", "Nifty 50"), "NIFTY500": ("^CRSLDX", "Nifty 500")}
IST = timezone(timedelta(hours=5, minutes=30))


def index_instrument(code: str) -> Instrument:
    return Instrument(exchange="NSE", code=code, key=f"IDX:{code}", yahoo=INDICES[code][0])


WHY_SYSTEM = ("You explain stock price moves for Indian investors. Use ONLY the facts provided. Never predict "
              "prices. Never give buy/sell advice. If the sources don't explain the move, say so. Return JSON only: "
              '{"summary": str (2-3 sentences, plain English), "cited_ids": [ids from SOURCES], '
              '"confidence_note": "explained" | "partly explained" | "not explained"}. Every factual claim must '
              "come from PRICE_FACTS or a SOURCE you cite. Numbers must be copied exactly. Don't quote rupee prices "
              "unless they are in PRICE_FACTS. Media headlines are reports, not facts: say 'reported'.")

ASK_SYSTEM = ("You are FINN's research assistant. You help the user think through a decision; the decision is "
              "theirs. Rules: use ONLY the TOOL OUTPUTS below; never invent numbers, events, targets or "
              "probabilities. FINN Rank is an experimental ranking vs FINN's tracked stocks, never a probability or "
              "prediction. Cite every factual point with an id from TOOL OUTPUTS, in the citations list only (never write "
              "ids inside the text). \"flags\" lists only items from TOOL OUTPUTS.flags (empty list if there are none). "
              "\"for\" and \"against\" each give 1-3 points from the rank grades, price and filings. Media "
              "headlines are reports: say 'reported'. "
              "Output JSON only: {\"headline\": str (<=20 words), \"for\": [str], \"against\": [str], "
              "\"flags\": [str], \"what_to_watch\": [str], \"bottom_line\": str (must start with \"Decision is "
              "yours.\"), \"citations\": [{\"id\": str, \"label\": str}]}")

BRIEF_SYSTEM = ("Write a morning briefing for an Indian investor's portfolio from the INPUTS only. At most 6 "
                "bullets, most important first: red flags, big moves with their reason, results due soon, rank "
                "extremes, other notable filings. Each bullet <= 30 words and cites ids from INPUTS. No advice, "
                "no predictions. Return JSON: {\"headline\": str, \"bullets\": [{\"text\": str, \"symbol\": str, "
                "\"cited_ids\": [str]}]}")

_PROB = re.compile(r"probab|chance|odds|price target|target price|guarantee|how (?:high|much) will|will it (?:go|rise|fall)",
                   re.I)


class DecisionService:
    def __init__(self, pipe):
        self.p = pipe
        self._lock = threading.Lock()
        self.backfill_state: dict = {"running": False, "done": False, "started": None, "finished": None,
                                     "years": None, "failed": {}, "fetched": 0}
        self._rank_cache: Optional[tuple[str, dict]] = None
        self._bt_cache: Optional[tuple[str, dict]] = None
        self._why: dict[str, dict] = {}
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._pending: dict = {}

    # ------------------------------------------------------------ history
    def universe(self) -> list[str]:
        return self.p.tracked()

    def backfill(self, years: Optional[int] = None) -> dict:
        years = years or int(os.environ.get("FINN_HISTORY_YEARS", "10"))
        if not self._lock.acquire(blocking=False):
            return dict(self.backfill_state)
        try:
            st = self.backfill_state
            st.update(running=True, started=datetime.now(timezone.utc).isoformat(), years=years, failed={}, fetched=0)
            insts = []
            for s in self.universe():
                try:
                    insts.append(normalize(s))
                except SymbolError:
                    continue
            insts += [index_instrument(c) for c in INDICES]
            days = int(years * 365.25)
            if getattr(self.p.prices, "name", "") == "yfinance" and len(insts) > 1:
                from .providers.prices import fetch_many_yf
                results = fetch_many_yf(self.p.prices, insts, days)
            else:
                results = {}
                for i in insts:
                    try:
                        results[i.key] = self.p.prices.fetch(i, days)
                    except PriceProviderError as e:
                        results[i.key] = e
            for i in insts:
                r = results.get(i.key)
                if isinstance(r, PriceProviderError) or r is None:
                    st["failed"][i.key] = (r.kind if r else "no result")
                    self.p.store.log_fetch("history", i.key, False, f"{r.kind}: {r.detail}" if r else "no result")
                    continue
                self.p.store.upsert_bars(r)
                self.p.store.log_fetch("history", i.key, True, items=len(r))
                st["fetched"] += 1
            ok = [i for i in insts if i.key not in st["failed"]]
            try:
                self.p.top_up_sessions(ok)
            except Exception as e:  # noqa: BLE001 - the top-up is a refinement; history stands without it
                st["topup_error"] = f"{e.__class__.__name__}: {e}"
            self._rank_cache = self._bt_cache = None
            st.update(done=True)
            return dict(st)
        finally:
            self.backfill_state.update(running=False, finished=datetime.now(timezone.utc).isoformat())
            self._lock.release()

    def history(self, symbol: str, days: int = 3650) -> dict:
        inst = self._inst(symbol)
        cutoff = date.today() - timedelta(days=days)
        rows = [(d, c) for d, c in self.p.store.closes(inst.key) if d >= cutoff]
        return {"symbol": symbol.upper(), "key": inst.key, "days": days, "bars": len(rows),
                "first": rows[0][0].isoformat() if rows else None, "last": rows[-1][0].isoformat() if rows else None,
                "series": [{"date": d.isoformat(), "close": c} for d, c in rows],
                "source": "yfinance (Yahoo Finance, unadjusted daily close)" if not self.p.fixture else "fixture"}

    def _inst(self, symbol: str) -> Instrument:
        s = symbol.upper()
        if s in INDICES:
            return index_instrument(s)
        return normalize(s)

    def data_status(self) -> dict:
        stats = self.p.store.bar_stats()
        today = self.p.clock().date()
        rows = []
        for s in self.universe() + list(INDICES):
            k = self._inst(s).key
            st = stats.get(k, {"bars": 0, "first": None, "last": None})
            age = (today - date.fromisoformat(st["last"])).days if st["last"] else None
            rows.append({"symbol": s, **st, "age_days": age, "stale": age is None or age > 4})
        ok = sum(1 for r in rows if r["bars"] >= 273)
        return {"backfill": dict(self.backfill_state), "symbols": rows,
                "expected_session": expected_session(self.p.clock()).isoformat(),
                "latest_session_topup": getattr(self.p, "topup_notes", {}), "with_1y_history": ok, "total": len(rows),
                "filings_since": (e.isoformat() if (e := self.p.store.earliest_announcement()) else None)}

    # ------------------------------------------------------------ rank
    def _inputs(self) -> list[StockInputs]:
        out = []
        today = self.p.clock().date()
        for s in self.universe():
            inst = normalize(s)
            rows = self.p.store.closes(inst.key, limit=400)
            c = self.p.portfolio.companies.get(s)
            last = rows[-1][0] if rows else None
            out.append(StockInputs(symbol=s, closes=[x for _, x in rows], price_as_of=last,
                                   snapshot=self.p.snapshot(s), is_lender=bool(c and c.is_lender),
                                   stale=last is None or (today - last).days > 4))
        return out

    def rank_all(self) -> dict[str, dict]:
        stocks = self._inputs()
        key = hashlib.sha256(json.dumps([(s.symbol, len(s.closes), s.closes[-1] if s.closes else None,
                                          str(getattr(s.snapshot, "retrieved_at", None))) for s in stocks]).encode()
                             ).hexdigest()
        if self._rank_cache and self._rank_cache[0] == key:
            return self._rank_cache[1]
        sc = score_universe(stocks)
        asof = max((s.price_as_of for s in stocks if s.price_as_of), default=None)
        out = {s: rank_payload(s, o, len(stocks), asof.isoformat() if asof else None) for s, o in sc.items()}
        for s, o in out.items():
            c = self.p.portfolio.companies.get(s)
            o["name"] = c.name if c else s
            o["role"] = c.role if c else "other"
            o["sector"] = c.sector if c else None
        self._rank_cache = (key, out)
        return out

    def rank_list(self, scope: str = "portfolio") -> dict:
        r = self.rank_all()
        syms = [c.symbol for c in self.p.portfolio.holdings] if scope == "portfolio" else list(r)
        items = sorted((r[s] for s in syms if s in r), key=lambda x: (x["composite_pct"] is None,
                                                                       -(x["composite_pct"] or 0)))
        return {"scope": scope, "items": items, "universe_size": len(r), "caveat": RANK_CAVEAT,
                "coverage": sum(1 for x in r.values() if x["rank"] is not None)}

    # ------------------------------------------------------------ backtest
    def backtest_latest(self) -> dict:
        series = {}
        for s in self.universe():
            series[s] = self.p.store.closes(normalize(s).key)
        bench = self.p.store.closes(index_instrument("NIFTY50").key)
        key = hashlib.sha256(json.dumps([(s, len(v), v[-1][1] if v else None) for s, v in series.items()] +
                                        [len(bench)], default=str).encode()).hexdigest()
        if self._bt_cache and self._bt_cache[0] == key:
            return self._bt_cache[1]
        res = backtest(series, bench or None)
        res["universe_size"] = len(series)
        self._bt_cache = (key, res)
        return res

    # ------------------------------------------------------------ flags
    def flags(self, symbols: Optional[list[str]] = None) -> dict:
        today = self.p.clock().date()
        since = self.p.clock() - timedelta(days=90)
        out = []
        from .pipeline import _collapse_cross_exchange
        for s in symbols or self.universe():
            # The same filing on NSE and BSE is one event: collapse before flagging, so it is flagged (and
            # deducted in portfolio health) once.
            for a in _collapse_cross_exchange(self.p.store.announcements_for(s, limit=200)):
                if a.filed_at < since:
                    continue
                text = f"{a.subject} {a.detail or ''}"
                f = flag_for(text, classify(a).category, today)
                if not f:
                    continue
                if f[1] == "amber" and a.filed_at < self.p.clock() - timedelta(days=30) and f[0] != "results_due":
                    continue
                out.append({"symbol": s, "flag_type": f[0], "level": f[1], "source_type": "filing",
                            "source_id": a.uid, "filed_at": a.filed_at.isoformat(), "url": a.source_url,
                            "evidence": (a.subject if len(a.subject) >= 40 or not a.detail
                                         else f"{a.subject} — {a.detail}")[:200]})
        order = {"red": 0, "amber": 1, "info": 2}
        out.sort(key=lambda x: x["filed_at"], reverse=True)
        out.sort(key=lambda x: order[x["level"]])
        e = self.p.store.earliest_announcement()
        return {"items": out, "coverage_since": e.isoformat() if e else None,
                "note": "Flags come from filings FINN has seen since it started polling, not a full 90-day history."}

    # ------------------------------------------------------------ why did it move
    def _move_inputs(self, symbol: str, on: Optional[date] = None) -> Optional[dict]:
        inst = normalize(symbol)
        rows = self.p.store.closes(inst.key, limit=400)
        if len(rows) < 2:
            return None
        idx = len(rows) - 1 if on is None else next((i for i, (d, _) in enumerate(rows) if d == on), None)
        if idx is None or idx < 1:
            return None
        d, close = rows[idx]
        prev = rows[idx - 1][1]
        pct = (close / prev - 1) * 100
        chg5 = (close / rows[idx - 5][1] - 1) * 100 if idx >= 5 else None
        bars = self.p.store.bars(inst.key, limit=400)
        vb = {b.date: b.volume for b in bars}
        prior = [vb.get(x) for x, _ in rows[max(0, idx - 20):idx] if vb.get(x)]
        vm = (vb.get(d) / (sum(prior) / len(prior))) if prior and vb.get(d) else None
        n = dict(self.p.store.closes(index_instrument("NIFTY50").key, limit=400))
        nd = sorted(x for x in n if x <= d)
        nifty = (n[nd[-1]] / n[nd[-2]] - 1) * 100 if len(nd) >= 2 and nd[-1] == d else None
        start = datetime.combine(d - timedelta(days=3 if d.weekday() == 0 else 1), datetime.min.time(), IST) \
            .replace(hour=15, minute=30)
        end = datetime.combine(d, datetime.min.time(), IST).replace(hour=15, minute=30)
        srcs = []
        for a in self.p.store.announcements_for(symbol, limit=60):
            if start - timedelta(days=1) <= a.filed_at <= end + timedelta(hours=8):
                srcs.append({"id": a.uid, "time": a.filed_at.isoformat(), "type": "filing", "text": a.subject,
                             "extra": (a.detail or "")[:240], "url": a.source_url})
        for nw in self.p.store.news_for(symbol, limit=40):
            if start - timedelta(days=1) <= nw.published_at <= end + timedelta(hours=8):
                srcs.append({"id": nw.uid, "time": nw.published_at.isoformat(), "type": "news (media report)",
                             "text": nw.headline, "extra": nw.publisher, "url": nw.url})
        r2 = lambda v: None if v is None else round(v, 2)  # noqa: E731
        return {"symbol": symbol, "date": d.isoformat(), "close": round(close, 2), "prev_close": round(prev, 2),
                "pct": r2(pct), "vm": r2(vm), "chg5": r2(chg5), "nifty_pct": r2(nifty), "sources": srcs[:8]}

    def why(self, symbol: str, on: Optional[date] = None, use_llm: bool = True, wait: float = 20.0) -> dict:
        """At most `wait` seconds for the model (free quotas queue after a restart); then the rule-based text,
        while the model's version keeps being written in the background and is served on the next request."""
        if not use_llm:
            return self._why_impl(symbol, on, False)
        k = (symbol.upper(), on)
        fut = self._pending.get(k)
        if fut is None:
            fut = self._pool.submit(self._why_impl, symbol, on, True)
            self._pending[k] = fut
        try:
            res = fut.result(timeout=wait)
        except FuturesTimeout:
            res = self._why_impl(symbol, on, False)
            return {**res, "pending": True}
        except Exception:  # noqa: BLE001
            self._pending.pop(k, None)
            return self._why_impl(symbol, on, False)
        self._pending.pop(k, None)
        return res

    def _why_impl(self, symbol: str, on: Optional[date] = None, use_llm: bool = True) -> dict:
        sym = symbol.upper()
        inp = self._move_inputs(sym, on)
        if inp is None:
            return {"symbol": sym, "ok": False, "reason": "not enough price history"}
        key = hashlib.sha256(json.dumps(inp, sort_keys=True, default=str).encode()).hexdigest()
        if key in self._why:
            return self._why[key]
        base = {"symbol": sym, "ok": True, "facts": {k: inp[k] for k in ("date", "close", "prev_close", "pct", "vm",
                                                                         "chg5", "nifty_pct")},
                "sources": inp["sources"]}
        llm = self.p.llm
        if not inp["sources"] or not use_llm or not (llm and llm.available):
            res = {**base, **fallback_explanation(sym, inp["pct"], inp["vm"])}
            if inp["sources"]:
                res["summary"] = (f"{sym} moved {inp['pct']:+.1f}%" + (f" on {inp['vm']:.1f}× normal volume"
                                  if inp["vm"] else "") + ". FINN found filings or news from around the move "
                                  "(listed below) but hasn't checked whether they explain it.")
            if use_llm or not inp["sources"]:
                self._why[key] = res
            return res
        facts = (f"close {inp['close']}, prev close {inp['prev_close']}, change {inp['pct']}%, volume "
                 f"{inp['vm']}× 20-day average, 5-day change {inp['chg5']}%, NIFTY50 same day {inp['nifty_pct']}%")
        src_lines = "\n".join(f"[{s['id']}] {s['time']} {s['type']} — {s['text']} — {s['extra']}" for s in inp["sources"])
        prompt = f"SYMBOL: {sym}, session {inp['date']}\nPRICE_FACTS: {facts}\nSOURCES:\n{src_lines}"
        allowed = [v for v in (inp["pct"], inp["vm"], inp["chg5"], inp["nifty_pct"], inp["close"], inp["prev_close"])
                   if v is not None]
        ids = {s["id"] for s in inp["sources"]}
        src_text = " ".join(f"{s['text']} {s['extra']}" for s in inp["sources"])
        errs: list[str] = []
        for attempt in range(2):
            p = prompt if attempt == 0 else prompt + "\n\nYour previous answer was rejected: " + "; ".join(errs)
            obj = llm.complete_json(p, system=WHY_SYSTEM, max_tokens=350, route="fast")
            errs = validate_explanation(obj, ids, allowed, [inp["close"], inp["prev_close"]], src_text)
            if not errs and isinstance(obj, dict):
                res = {**base, "summary": obj["summary"].strip(), "cited_ids": obj.get("cited_ids") or [],
                       "confidence_note": obj["confidence_note"], "method": "llm"}
                self._why[key] = res
                return res
        res = {**base, **fallback_explanation(sym, inp["pct"], inp["vm"]), "rejected": errs[:3],
               "llm_error": getattr(llm, "last_error", None)}
        self._why[key] = res
        return res

    def why_quick(self, symbol: str, on: Optional[date] = None) -> dict:
        """For the digest: a cached LLM explanation if one exists, otherwise the deterministic text (no LLM call)."""
        return self.why(symbol, on, use_llm=False) if not self._cached_llm(symbol, on) else self._cached_llm(symbol, on)

    def _cached_llm(self, symbol: str, on: Optional[date]):
        inp = self._move_inputs(symbol.upper(), on)
        if inp is None:
            return None
        key = hashlib.sha256(json.dumps(inp, sort_keys=True, default=str).encode()).hexdigest()
        r = self._why.get(key)
        return r if r and r.get("method") == "llm" else None

    # ------------------------------------------------------------ portfolio health
    def health(self) -> dict:
        hold = [c.symbol for c in self.p.portfolio.holdings]
        ranks = self.rank_all()
        fl = self.flags(hold)["items"]
        sectors = {s: (self.p.portfolio.companies[s].sector if s in self.p.portfolio.companies else None) for s in hold}
        stale = [s for s in hold if ranks.get(s, {}).get("data", {}).get("stale")]
        return portfolio_health(HealthInputs(symbols=hold, ranks=ranks, flags=fl, sectors=sectors, stale=stale))

    # ------------------------------------------------------------ Ask FINN agent
    def _symbol_in(self, q: str) -> Optional[str]:
        up = q.upper()
        for s in self.universe():
            if re.search(rf"\b{re.escape(s)}\b", up):
                return s
        low = q.lower()
        for s in self.universe():
            c = self.p.portfolio.companies.get(s)
            if c:
                first = c.name.lower().replace(" ltd", "").replace(" limited", "")
                if first in low or first.split()[0] in low.split():
                    return s
        return None

    def tool_outputs(self, sym: str) -> tuple[dict, list[dict]]:
        """Runs the agent's tools for one symbol. Returns (outputs, citation catalogue)."""
        r = self.rank_all().get(sym)
        fl = self.flags([sym])["items"]
        cat: list[dict] = []
        out: dict = {}
        if r:
            out["rank"] = {"id": f"factor:{sym}:rank", "rank": r["rank"], "composite_pct": r["composite_pct"],
                           "grades": r["grades"], "groups": r["groups"], "label": r["label"],
                           "as_of": r["as_of"], "insufficient": r["data"]["insufficient"]}
            cat.append({"id": f"factor:{sym}:rank", "label": f"FINN Rank for {sym} (experimental)"})
        out["flags"] = [{"id": f["source_id"], "type": f["flag_type"], "level": f["level"], "evidence": f["evidence"],
                         "filed_at": f["filed_at"]} for f in fl]
        cat += [{"id": f["source_id"], "label": f["evidence"][:80], "url": f.get("url")} for f in fl]
        m = self._move_inputs(sym)
        if m:
            out["price"] = {"id": f"price:{sym}:latest", **{k: m[k] for k in ("date", "close", "pct", "chg5", "vm")}}
            cat.append({"id": f"price:{sym}:latest", "label": f"{sym} price on {m['date']}"})
            rows = self.p.store.closes(normalize(sym).key, limit=260)
            if len(rows) >= 250:
                out["price"]["chg_1y_pct"] = round((rows[-1][1] / rows[0][1] - 1) * 100, 1)
        anns = self.p.store.announcements_for(sym, limit=6)
        out["filings"] = [{"id": a.uid, "filed_at": a.filed_at.isoformat(), "subject": a.subject} for a in anns]
        cat += [{"id": a.uid, "label": a.subject[:80], "url": a.source_url} for a in anns]
        nws = self.p.store.news_for(sym, limit=5)
        out["news"] = [{"id": n.uid, "published_at": n.published_at.isoformat(), "headline": n.headline,
                        "publisher": n.publisher, "note": "media report"} for n in nws]
        cat += [{"id": n.uid, "label": f"{n.publisher}: {n.headline[:70]}", "url": n.url} for n in nws]
        return out, cat

    def ask(self, question: str, symbol: Optional[str] = None, wait: float = 40.0) -> dict:
        fut = self._pool.submit(self._ask_impl, question, symbol)
        try:
            return fut.result(timeout=wait)
        except FuturesTimeout:
            sym = (symbol or "").upper() or self._symbol_in(question or "")
            if sym and sym in self.universe():
                res = self._deterministic_answer(sym)
                res["llm_note"] = "The free AI quota is busy; this summary is from FINN's data without AI."
                return res
            return {"ok": False, "symbol": sym, "headline": "The free AI quota is busy. Try again in a minute.",
                    "method": "rule"}

    def _ask_impl(self, question: str, symbol: Optional[str] = None) -> dict:
        q = (question or "").strip()
        sym = (symbol or "").upper() or self._symbol_in(q)
        if _PROB.search(q):
            refusal = (f"{REFUSAL}. FINN can show the experimental rank, the grades behind it and any red flags "
                       "instead.")
            res = self._deterministic_answer(sym) if sym and sym in self.universe() else {}
            return {**res, "symbol": sym, "headline": refusal, "refused": True, "method": "rule",
                    "bottom_line": "Decision is yours. " + refusal}
        if not sym or sym not in self.universe():
            return {"ok": False, "symbol": sym, "headline": "Name one of your tracked stocks (e.g. INFY) and FINN "
                    "will summarise its rank, flags, price and recent filings.", "method": "rule",
                    "tracked": self.universe()}
        outs, cat = self.tool_outputs(sym)
        llm = self.p.llm
        if llm and llm.available:
            ids = {c["id"] for c in cat}
            prompt = f"QUESTION: {q}\nSYMBOL: {sym}\nTOOL OUTPUTS:\n{json.dumps(outs, default=str)[:6000]}"
            for _ in range(2):
                obj = llm.complete_json(prompt, system=ASK_SYSTEM, max_tokens=900, route="long")
                ok, why = self._check_answer(obj, ids, outs)
                if ok:
                    labels = {c["id"]: c for c in cat}
                    obj["citations"] = [labels[c["id"]] for c in obj.get("citations", []) if c.get("id") in labels]
                    if not outs.get("flags"):
                        obj["flags"] = []          # flags come from FINN's filing rules only, never from the model
                    return clean({**obj, "ok": True, "symbol": sym, "method": "llm", "caveat": RANK_CAVEAT})
                prompt += f"\n\nYour previous answer was rejected: {why}"
            res = self._deterministic_answer(sym, outs, cat)
            res["llm_note"] = why or getattr(llm, "last_error", None)
            return res
        return self._deterministic_answer(sym, outs, cat)

    def _check_answer(self, obj, ids: set[str], outs: dict) -> tuple[bool, str]:
        if not isinstance(obj, dict):
            return False, "not JSON"
        bl = obj.get("bottom_line", "")
        if not isinstance(bl, str) or not bl.startswith("Decision is yours."):
            return False, "bottom_line must start with 'Decision is yours.'"
        cites = obj.get("citations") or []
        if not cites or any(not isinstance(c, dict) or c.get("id") not in ids for c in cites):
            return False, "citations must use ids from TOOL OUTPUTS"
        text = " ".join(str(x) for k in ("headline", "for", "against", "flags", "what_to_watch", "bottom_line")
                        for x in ([obj.get(k)] if isinstance(obj.get(k), str) else (obj.get(k) or [])))
        if has_forbidden(text):
            return False, f"forbidden phrases: {has_forbidden(text)}"
        allowed = [abs(x) for x in numbers_in(json.dumps(outs, default=str))]
        for v in numbers_in(text):
            if abs(v) >= 10 and not any(abs(abs(v) - a) <= max(0.15, 0.005 * a) for a in allowed):
                return False, f"number {v} is not in TOOL OUTPUTS"
        return True, ""

    def _deterministic_answer(self, sym: str, outs: Optional[dict] = None, cat: Optional[list] = None) -> dict:
        if outs is None:
            outs, cat = self.tool_outputs(sym)
        cat = cat or []
        r = outs.get("rank")
        pros, cons = [], []
        if r:
            for g, v in (r["groups"] or {}).items():
                if v is None:
                    continue
                (pros if v >= 60 else cons if v < 40 else []).append(
                    f"{g.title()} grade {r['grades'][g]} ({v:.0f}th percentile among FINN's stocks)")
        flags = [f"{f['level'].upper()}: {f['evidence']}" for f in outs.get("flags", [])]
        price = outs.get("price")
        watch = [f"Latest filing: {f['subject'][:90]}" for f in outs.get("filings", [])[:2]]
        head = (f"{sym}: FINN Rank {r['rank']}/10 — {r['label']}" if r and r["rank"] else
                f"{sym}: not enough data for a FINN Rank yet")
        if price:
            watch.append(f"Last close {price['close']} on {price['date']} ({price['pct']:+.1f}% on the day)")
        return clean({"ok": True, "symbol": sym, "headline": head, "for": pros, "against": cons, "flags": flags,
                      "what_to_watch": watch, "bottom_line": "Decision is yours. This summarises FINN's data; it "
                      "isn't a recommendation.", "citations": cat[:8], "method": "deterministic",
                      "caveat": RANK_CAVEAT})

    # ------------------------------------------------------------ morning briefing
    def briefing(self, digest=None) -> dict:
        hold = [c.symbol for c in self.p.portfolio.holdings]
        fl = [f for f in self.flags(hold)["items"] if f["level"] in ("red", "amber")]
        moves = []
        for s in hold:
            m = self._move_inputs(s)
            if m and m["pct"] is not None and abs(m["pct"]) >= 3:
                w = self.why_quick(s)
                why = w.get("summary") if w.get("method") == "llm" else (
                    f"{len(m['sources'])} filing/news item(s) around the move; open the stock to check them."
                    if m["sources"] else "No filing or news in FINN explains it yet.")
                vol = f" on {m['vm']:.1f}× normal volume" if m["vm"] else ""
                moves.append({"id": f"price:{s}:latest", "symbol": s, "pct": m["pct"], "date": m["date"], "vol": vol,
                              "why": why, "why_ids": w.get("cited_ids", [])})
        ranks = self.rank_all()
        rk = sorted((ranks[s] for s in hold if ranks.get(s, {}).get("rank")), key=lambda x: -x["composite_pct"])
        bullets = []
        for f in fl[:3]:
            bullets.append({"text": f"{f['symbol']}: {f['level']} flag — {f['evidence'][:120]}", "symbol": f["symbol"],
                            "cited_ids": [f["source_id"]]})
        for m in sorted(moves, key=lambda x: -abs(x["pct"]))[:3]:
            bullets.append({"text": f"{m['symbol']} moved {m['pct']:+.1f}%{m['vol']} on {m['date']}. {m['why']}",
                            "symbol": m["symbol"], "cited_ids": [m["id"]] + list(m["why_ids"])})
        if rk:
            bullets.append({"text": f"Highest FINN Rank in your holdings: {rk[0]['symbol']} ({rk[0]['rank']}/10); "
                                    f"lowest: {rk[-1]['symbol']} ({rk[-1]['rank']}/10). Experimental ranking.",
                            "symbol": rk[0]["symbol"], "cited_ids": [f"factor:{rk[0]['symbol']}:rank",
                                                                     f"factor:{rk[-1]['symbol']}:rank"]})
        bullets = bullets[:6]
        head = (f"{len([f for f in fl if f['level'] == 'red'])} red flag(s), {len(moves)} big move(s) in your holdings"
                if (fl or moves) else "A quiet morning for your holdings")
        return clean({"headline": head, "bullets": bullets, "method": "deterministic",
                      "as_of": self.p.clock().isoformat(), "caveat": RANK_CAVEAT,
                      "inputs": {"flags": len(fl), "moves": len(moves)}})

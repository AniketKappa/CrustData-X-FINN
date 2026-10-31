"""Pull research: a dossier for any NSE company, built from its own documents and reported numbers.

Steps (each visible to the app while it runs):
  1. fundamentals   Screener page -> tables + links to the company's documents
  2. documents      latest 4 call transcripts, latest investor presentation, latest annual report (PDF, page text)
  3. numbers        financial snapshot, trajectory, balance sheet, cash quality: computed in code (numbers.py)
  4. business       what the company does, from the annual report and presentation (LLM, cited, validated)
  5. guidance       guidance statements per call (fast model), quotes verified against the transcript
  6. ledger         promised vs delivered, computed in code from the quarterly table
  7. narrative      management's explanation of the numbers, from the transcripts (LLM, cited, validated)
  8. bull_bear      a tight case each way from the same sources (LLM, cited, validated)

Without an LLM key, steps 1–3 and 6's inputs still work; the LLM sections say they need a key.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .claims import (ASK_SHAPE, ASK_TASK, BULL_BEAR_SHAPE, BULL_BEAR_TASK, GUIDANCE_SYSTEM, SECTION_TASKS, SYSTEM,
                     check_claims, guidance_prompt, quote_in, section_prompt, source_block)
from .documents import Chunk, Doc, DocumentSource, chunk_pages, select_docs
from .ledger import VERDICT_LABEL, LedgerRow, evaluate, scorecard
from .numbers import Fact, build as build_numbers, quarter_actuals
from .retrieve import BM25, budget

STEPS = [("fundamentals", "Company tables and document links"), ("numbers", "Computing the numbers"),
         ("documents", "Reading the company's documents"), ("business", "Business snapshot"),
         ("guidance", "Finding guidance on each call"), ("narrative", "Management's explanation"),
         ("ledger", "Checking promises against results"), ("bull_bear", "Bull and bear case")]
CACHE_HOURS = 24
VERSION = "r2"

GUIDANCE_QUERY = ("guidance expect expecting target targeting outlook going forward next year full year FY growth margin "
                  "EBITDA capex invest crore percent double digit range aspire aim confident achieve maintain sustain")
RISK_QUERY = "risk challenge headwind pressure competition decline slowdown uncertainty debt pricing regulatory weak"
GROWTH_QUERY = "growth opportunity capacity expansion demand new launch market share order book investment strong"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchEngine:
    def __init__(self, store, docs: DocumentSource, llm, get_snapshot: Callable[[str], object],
                 company_name: Callable[[str], Optional[str]] = lambda s: None,
                 is_lender: Callable[[str, object], bool] = lambda s, snap: False):
        self.store, self.docs, self.llm = store, docs, llm
        self.get_snapshot, self.company_name, self.is_lender = get_snapshot, company_name, is_lender
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._indexes: dict[str, tuple[list[Chunk], BM25, list[Doc]]] = {}

    # ------------------------------------------------------------ public
    def status(self, symbol: str) -> dict:
        symbol = symbol.upper()
        with self._lock:
            job = self.jobs.get(symbol)
        if job:
            return job
        raw = self.store.get_research(f"{VERSION}:{symbol}", CACHE_HOURS)
        if raw:
            return json.loads(raw)
        return {"symbol": symbol, "status": "idle"}

    def start(self, symbol: str, force: bool = False) -> dict:
        symbol = symbol.upper()
        with self._lock:
            job = self.jobs.get(symbol)
            if job and job["status"] == "running":
                return job                                  # one build per company, however many taps
            if not force:
                raw = self.store.get_research(f"{VERSION}:{symbol}", CACHE_HOURS)
                if raw:
                    return json.loads(raw)
            job = self._new_job(symbol)
            self.jobs[symbol] = job
        threading.Thread(target=self._run_safe, args=(job,), daemon=True).start()
        return job

    def build(self, symbol: str) -> dict:
        """Synchronous build (tests and CLI)."""
        job = self._new_job(symbol.upper())
        self.jobs[job["symbol"]] = job
        self._run_safe(job)
        return job

    def ask(self, symbol: str, question: str, history: Optional[list[dict]] = None) -> dict:
        """Grounded answer to a question about one company. `history` = earlier turns [{question, answer}] so a
        follow-up ("why?", "and margins?") is understood; history is context only and is never cited."""
        symbol = symbol.upper()
        q = " ".join(question.split())[:400]
        name = self.company_name(symbol) or self.status(symbol).get("name") or symbol
        history = [h for h in (history or []) if isinstance(h, dict) and h.get("question")][-3:]
        kind = classify_question(q)
        if kind != "question":                       # greetings, thanks, empty or not about the company: no model call
            return {"question": q, "status": kind, "claims": [], "gaps": [], "sources": {},
                    "message": _reply_for(kind, name), "follow_ups": _starter_questions()}
        if not self.llm or not self.llm.available:
            return {"question": q, "status": "no_llm", "claims": [], "gaps": [],
                    "message": "Answers need a free Groq or OpenRouter key in .env."}
        idx = self._index(symbol)
        if idx is None:
            return {"question": q, "status": "no_docs", "claims": [], "gaps": [],
                    "message": "Open the research dossier first so FINN can read the company's documents."}
        chunks, bm, docs = idx
        search_q = q
        if history and is_follow_up(q):              # "why?" -> search with the topic of the previous question
            search_q = f"{history[-1]['question']} {q}"
        scored = bm.search(search_q, k=14, boost={"transcript": 1.1, "presentation": 1.05})
        if not scored or scored[0][1] < 0.5:          # nothing in the documents is about this
            return {"question": q, "status": "not_found", "claims": [], "gaps": [], "sources": {},
                    "message": f"{name}'s documents that FINN read don't discuss this. Try asking about its business, "
                               "results, margins, guidance, debt, cash flow or risks.", "follow_ups": _starter_questions()}
        hits = budget([c for c, _ in scored], 11500)
        rel = _relevant_facts(search_q, self._facts(symbol))
        src, smap = source_block(hits, rel)
        convo = ""
        if history:
            convo = "Conversation so far (context only - do not cite this, cite only the sources):\n" + "\n".join(
                f"Q: {h['question'][:200]}\nA: {str(h.get('answer') or '')[:300]}" for h in history) + "\n\n"
        prompt = f"Company: {name}\n{convo}Investor's question: {q}\n\n" + section_prompt(ASK_TASK, src, ASK_SHAPE)
        raw = self.llm.complete_json(prompt, system=SYSTEM, max_tokens=900, route="long")
        if raw is None:
            return {"question": q, "status": "llm_failed", "claims": [], "gaps": [],
                    "message": f"The free model quota is busy right now ({self.llm.last_error}). Try again in a minute."}
        if raw.get("off_topic") is True:
            return {"question": q, "status": "off_topic", "claims": [], "gaps": [], "sources": {},
                    "message": _reply_for("off_topic", name), "follow_ups": _starter_questions()}
        checked = check_claims(raw, smap)
        out = _publish(checked, smap)
        out.update(question=q, status="ok", follow_ups=[str(x)[:120] for x in (raw.get("follow_ups") or [])][:3],
                   model=f"{self.llm.last_provider}/{self.llm.last_model}")
        if not out["claims"]:
            out["status"] = "not_found"
            out["message"] = (f"{name}'s documents that FINN read don't answer this clearly. "
                              + (" ".join(out["gaps"][:1]) if out["gaps"] else ""))
        return out

    # ------------------------------------------------------------ job
    def _new_job(self, symbol: str) -> dict:
        return {"symbol": symbol, "status": "running", "version": VERSION, "started_at": utcnow().isoformat(),
                "steps": [{"id": i, "label": l, "status": "pending"} for i, l in STEPS], "name": self.company_name(symbol),
                "documents": [], "numbers": [], "facts": {}, "sources": {}, "sections": {}, "notes": [],
                "llm": bool(self.llm and self.llm.available)}

    def _step(self, job, sid, status, note=None):
        for s in job["steps"]:
            if s["id"] == sid:
                s["status"] = status
                if note:
                    s["note"] = note

    def _run_safe(self, job: dict) -> None:
        try:
            self._run(job)
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001 - a failed build becomes a visible error, never a crash
            job["status"] = "failed"
            job["error"] = f"{e.__class__.__name__}: {str(e)[:200]}"
            for s in job["steps"]:
                if s["status"] == "running":
                    s["status"] = "failed"
        job["finished_at"] = utcnow().isoformat()
        if job["status"] == "done":
            self.store.put_research(f"{VERSION}:{job['symbol']}", json.dumps(job, default=str))
        with self._lock:
            self.jobs.pop(job["symbol"], None)

    def _run(self, job: dict) -> None:
        """Fast path: numbers first (seconds), documents downloaded and read in parallel, then the model sections in
        parallel (they don't depend on each other), then the ledger and the bull/bear case."""
        from concurrent.futures import ThreadPoolExecutor

        sym = job["symbol"]
        self._step(job, "fundamentals", "running")
        snap = self.get_snapshot(sym)
        if snap is None:
            self._step(job, "fundamentals", "failed", "Screener has no page for this symbol, or it couldn't be reached.")
            raise RuntimeError("fundamentals unavailable")
        job["name"] = job["name"] or snap.name or sym
        job["sector"] = snap.sector
        job["fundamentals_url"] = snap.source_url
        lender = self.is_lender(sym, snap)
        self._step(job, "fundamentals", "done")

        # numbers: from the tables, in code - shown while the documents download
        self._step(job, "numbers", "running")
        sections, fb = build_numbers(snap, lender)
        job["numbers"] = [s.model_dump(mode="json") for s in sections]
        job["facts"] = {f.id: f.model_dump(mode="json") for f in fb.facts}
        job["lender"] = lender
        actuals = quarter_actuals(snap)
        job["quarters"] = actuals[-8:]
        self._step(job, "numbers", "done")

        # documents: all at once
        self._step(job, "documents", "running")
        wanted = select_docs(snap)
        job["documents"] = [d.model_dump(mode="json") for d in wanted]
        with ThreadPoolExecutor(max_workers=4) as ex:
            loaded = list(ex.map(self.docs.load, wanted))
        docs, chunks = [], []
        for d2, pages in loaded:
            docs.append(d2)
            chunks += chunk_pages(d2, pages)
        job["documents"] = [x.model_dump(mode="json") for x in docs]
        ok = [d for d in docs if d.status == "ok"]
        self._step(job, "documents", "done" if ok else "failed",
                   f"Read {len(ok)} of {len(docs)} documents" if docs else "No transcripts or reports are linked for this company.")
        bm = BM25(chunks) if chunks else None
        if bm:
            self._indexes[sym] = (chunks, bm, docs)

        llm_ok = bool(self.llm and self.llm.available)
        no_llm = "Needs a free Groq or OpenRouter key in .env."
        transcripts = [d for d in ok if d.kind == "transcript"]
        rows: list[LedgerRow] = []

        def business():
            self._step(job, "business", "running")
            job["sections"]["business"] = self._section(bm, "business", ("annual_report", "presentation"), [],
                                                        company=job["name"])
            self._step(job, "business", "done")

        def guidance():
            self._step(job, "guidance", "running")
            found = self._guidance_all(bm, transcripts)
            rows.extend(found)
            job["sections"]["guidance"] = {"rows": [r.model_dump(mode="json") for r in found]}
            self._step(job, "guidance", "done", f"{len(found)} guidance statements from {len(transcripts)} calls")

        def narrative():
            self._step(job, "narrative", "running")
            latest = {d.id for d in transcripts[:2]}
            ffacts = [f for f in fb.facts if f.label.startswith(("Operating margin", "Revenue growth", "Net profit growth"))]
            job["sections"]["narrative"] = self._section(bm, "narrative", ("transcript",), ffacts, doc_ids=latest,
                                                         company=job["name"])
            self._step(job, "narrative", "done")

        tasks = []
        if not llm_ok or not bm:
            for sid in ("business", "guidance", "narrative"):
                self._step(job, sid, "skipped", no_llm if not llm_ok else "No documents to read.")
        else:
            tasks.append(business)
            if transcripts:
                tasks += [guidance, narrative]
            else:
                self._step(job, "guidance", "skipped", "No call transcripts are available.")
                self._step(job, "narrative", "skipped", "No call transcripts are available.")
        with ThreadPoolExecutor(max_workers=3) as ex:
            for f in [ex.submit(t) for t in tasks]:
                try:
                    f.result()
                except Exception:  # noqa: BLE001 - one section failing must not lose the others
                    pass
        for sid in ("business", "guidance", "narrative"):
            if next(s for s in job["steps"] if s["id"] == sid)["status"] == "running":
                self._step(job, sid, "failed")

        # ledger: code only
        self._step(job, "ledger", "running")
        label_of = {d.id: d.title.split(" call")[0] for d in transcripts}
        for r in rows:
            evaluate(r, actuals, label_of.get(r.cite.get("doc_id"), ""))
        job["sections"]["ledger"] = {"rows": [r.model_dump(mode="json") for r in rows], "score": scorecard(rows),
                                     "labels": VERDICT_LABEL}
        self._step(job, "ledger", "done" if rows else "skipped",
                   None if rows else ("No guidance found to check." if llm_ok and transcripts else None))

        if not llm_ok or not bm:
            self._step(job, "bull_bear", "skipped", no_llm if not llm_ok else "No documents to read.")
        else:
            self._step(job, "bull_bear", "running")
            job["sections"]["bull_bear"] = self._bull_bear(bm, fb.facts, rows, job["name"])
            self._step(job, "bull_bear", "done")
        job["usage"] = self.llm.usage_summary() if llm_ok else None

    # ------------------------------------------------------------ pieces
    def _section(self, bm: BM25, key: str, kinds, facts: list[Fact], doc_ids=None, company="") -> dict:
        title, task, query = SECTION_TASKS[key]
        hits = budget([c for c, _ in bm.search(query, k=12, kinds=kinds, doc_ids=doc_ids)], 9500)
        if not hits:
            return {"title": title, "claims": [], "gaps": ["The documents FINN read don't cover this."], "dropped": 0}
        src, smap = source_block(hits, facts)
        raw = self.llm.complete_json(f"Company: {company}\n" + section_prompt(task, src), system=SYSTEM,
                                     max_tokens=900, route="long")
        if raw is None:
            return {"title": title, "claims": [], "gaps": [], "dropped": 0, "status": "llm_failed",
                    "message": f"Model quota busy ({self.llm.last_error}). Refresh the dossier in a minute."}
        out = _publish(check_claims(raw, smap), smap)
        out["title"] = title
        return out

    def _guidance_all(self, bm: BM25, transcripts: list[Doc]) -> list[LedgerRow]:
        """One model call for all calls: the best ~2,400 characters of guidance talk from each transcript."""
        hits: list[Chunk] = []
        for d in transcripts:
            hits += budget([c for c, _ in bm.search(GUIDANCE_QUERY, k=5, doc_ids={d.id})], 2400)
        if not hits:
            return []
        return self._guidance_from(hits, ", ".join(d.title.split(" (")[0] for d in transcripts))

    def _guidance(self, bm: BM25, d: Doc) -> list[LedgerRow]:
        hits = budget([c for c, _ in bm.search(GUIDANCE_QUERY, k=10, doc_ids={d.id})], 7000)
        return self._guidance_from(hits, d.title) if hits else []

    def _guidance_from(self, hits: list[Chunk], calls: str) -> list[LedgerRow]:
        src, smap = source_block(hits, [])
        raw = self.llm.complete_json(guidance_prompt(calls, src), system=GUIDANCE_SYSTEM, max_tokens=1100, route="fast")
        rows = []
        for it in (raw or {}).get("items") or []:
            if not isinstance(it, dict):
                continue
            cid = str(it.get("cite") or "").strip("[] ")
            s = smap.get(cid)
            quote = str(it.get("quote") or "").strip()
            if not s or not quote_in(quote, s["chunk"].text):
                continue                                     # unverifiable quote: dropped
            c: Chunk = s["chunk"]
            low, high = _num(it.get("low")), _num(it.get("high"))
            if low is not None and high is not None and low > high:
                low, high = high, low
            rows.append(LedgerRow(said_in=c.title.split(" (")[0].replace(" transcript", ""),
                                  metric=str(it.get("metric") or "other").split("|")[0].strip().lower(),
                                  statement=str(it.get("statement") or "")[:240], quote=quote[:400],
                                  cite={"doc_id": c.doc_id, "title": c.title, "page": c.page, "url": f"{c.url}#page={c.page}",
                                        "id": c.id},
                                  low=low, high=high, unit=str(it.get("unit") or "").strip(),
                                  horizon=str(it.get("horizon") or "")[:40]))
        return rows

    def _bull_bear(self, bm: BM25, facts: list[Fact], rows: list[LedgerRow], company: str) -> dict:
        hits = [c for c, _ in bm.search(RISK_QUERY, k=5)] + [c for c, _ in bm.search(GROWTH_QUERY, k=5)]
        seen, uniq = set(), []
        for c in hits:
            if c.id not in seen:
                seen.add(c.id)
                uniq.append(c)
        hits = budget(uniq, 8000)
        keep = [f for f in facts if f.value is not None][:24]
        src, smap = source_block(hits, keep)
        if rows:
            done = [r for r in rows if r.verdict in ("delivered", "beat", "missed", "behind", "on_track")]
            if done:
                src += "\n\nPromises checked by FINN (for context; cite the transcript passage or figure, not this list):\n" + \
                       "\n".join(f"- {r.said_in}: {r.statement} -> {VERDICT_LABEL[r.verdict]}" for r in done[:6])
        prompt = f"Company: {company}\nTask: {BULL_BEAR_TASK}\n\nSources:\n{src}\n\nReturn JSON exactly in this shape: {BULL_BEAR_SHAPE}"
        raw = self.llm.complete_json(prompt, system=SYSTEM, max_tokens=900, route="long")
        if raw is None:
            return {"bull": [], "bear": [], "status": "llm_failed",
                    "message": f"Model quota busy ({self.llm.last_error}). Refresh the dossier in a minute."}
        bull, bear = check_claims(raw, smap, "bull"), check_claims(raw, smap, "bear")
        b, r = _publish(bull, smap), _publish(bear, smap)
        return {"bull": b["claims"], "bear": r["claims"], "sources": {**b["sources"], **r["sources"]},
                "dropped": bull.dropped + bear.dropped, "gaps": bull.gaps}

    def _facts(self, symbol: str) -> list[Fact]:
        st = self.status(symbol)
        return [Fact(**f) for f in (st.get("facts") or {}).values()]

    def _index(self, symbol: str):
        if symbol in self._indexes:
            return self._indexes[symbol]
        st = self.status(symbol)
        docs = [Doc(**d) for d in st.get("documents") or [] if d.get("status") == "ok"]
        if not docs:
            return None
        chunks = []
        for d in docs:
            chunks += chunk_pages(d, self.store.doc_pages(d.id))
        if not chunks:
            return None
        self._indexes[symbol] = (chunks, BM25(chunks), docs)
        return self._indexes[symbol]


def _publish(checked, smap: dict) -> dict:
    """Map prompt-local ids (S3) to stable source ids and collect the source records the UI shows."""
    sources, claims = {}, []
    for c in checked.claims:
        ids = []
        for cid in c.cites:
            s = smap[cid]
            if s["kind"] == "doc":
                ch: Chunk = s["chunk"]
                sources[ch.id] = {"kind": "doc", "title": ch.title, "page": ch.page, "url": f"{ch.url}#page={ch.page}",
                                  "text": ch.text, "doc_kind": ch.kind}
                ids.append(ch.id)
            else:
                f: Fact = s["fact"]
                sources[f.id] = {"kind": "fact", "title": f.label, "period": f.period, "value": f.value, "unit": f.unit,
                                 "formula": f.formula, "url": f.url, "source": f.source, "locator": f.locator}
                ids.append(f.id)
        claims.append({"text": c.text, "cites": ids})
    return {"claims": claims, "gaps": checked.gaps, "dropped": checked.dropped, "sources": sources}


_SMALL_TALK = re.compile(r"^(hi+|hello+|hey+|hiya|yo|sup|namaste|good (morning|afternoon|evening|night)|thanks?( you)?|"
                         r"thank u|ok(ay)?|cool|nice|great|bye|test(ing)?|hmm+|who are you|what can you do|help)[\s!.?]*$", re.I)
_FINANCE = re.compile(r"revenue|sales|growth|margin|ebitda|profit|pat|pbt|loss|debt|borrow|cash|capex|guidance|guide|"
                      r"outlook|segment|business|product|customer|plant|capacity|risk|competition|demand|price|pricing|"
                      r"order|export|dividend|management|ceo|cfo|strategy|acquisi|merger|subsidiar|working capital|"
                      r"inventory|receivable|valuation|return|roe|roce|share|quarter|fy\d|year|promise|deliver|"
                      r"why|how|what|explain|compare|trend|cost|expense|tax|interest|rating|plan|target|expect", re.I)
_OFF_TOPIC = re.compile(r"\b(weather|cricket|movie|song|recipe|joke|poem|girlfriend|boyfriend|homework|code|python|"
                        r"president|prime minister|election|bitcoin|crypto)\b", re.I)
_FOLLOW = re.compile(r"^(why|how( so)?|and|what about|how about|so|then|explain|elaborate|more|details?|really|is that)\b|"
                     r"\b(it|that|this|those|these|they|them|its)\b", re.I)


def classify_question(q: str) -> str:
    """question | greeting | off_topic | empty. Cheap rules first, so small talk never reaches a model."""
    t = q.strip()
    if len(t) < 2:
        return "empty"
    if _SMALL_TALK.match(t):
        return "greeting"
    if _OFF_TOPIC.search(t) and not _FINANCE.search(t.replace("what", "").replace("how", "").replace("why", "")):
        return "off_topic"
    if len(t.split()) <= 2 and not _FINANCE.search(t):
        return "off_topic"
    return "question"


def is_follow_up(q: str) -> bool:
    return len(q.split()) <= 8 and bool(_FOLLOW.search(q))


def _reply_for(kind: str, name: str) -> str:
    if kind == "greeting":
        return (f"Hi! I answer questions about {name} from its own annual report, call transcripts and investor "
                "presentation, with a source for every sentence. Try one of these:")
    if kind == "empty":
        return "Type a question about the company."
    return (f"I can only answer questions about {name}'s business and financials, from the company's own documents. "
            "Try one of these:")


def _starter_questions() -> list[str]:
    return ["What does the company do, and where does revenue come from?", "What did management guide for this year?",
            "What risks did management name on the last call?"]


def _relevant_facts(q: str, facts: list[Fact], k: int = 14) -> list[Fact]:
    words = set(re.findall(r"[a-z]+", q.lower()))
    syn = {"debt": "borrowings debt-to-equity", "cash": "cash", "margin": "margin", "growth": "growth cagr",
           "profit": "profit pat", "revenue": "revenue sales", "working": "days cycle", "valuation": "price earnings market"}
    extra = " ".join(v for k2, v in syn.items() if k2 in words)
    scored = []
    for f in facts:
        lab = f.label.lower()
        s = sum(1 for w in (words | set(extra.split())) if len(w) > 3 and w in lab)
        scored.append((s, f))
    scored.sort(key=lambda x: -x[0])
    top = [f for s, f in scored if s > 0][:k]
    return top or [f for f in facts if f.value is not None][:8]


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None

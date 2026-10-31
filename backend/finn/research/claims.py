"""Prompts and validators for grounded research (CLAUDE.md rules 6–8).

Sources given to a model are numbered: [S#] passages from the company's own documents (PRIMARY_DOC) and [F#]
figures FINN computed from standardised tables. A claim survives only if
  1. it cites at least one source that was actually given, and
  2. every number in it appears in one of the sources it cites (no model arithmetic, no recalled figures).
Claims that fail are dropped and counted, never shown. Quotes for the promises ledger must be found in the cited
passage (whitespace- and punctuation-insensitive).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from .documents import Chunk
from .numbers import Fact

SYSTEM = """You are FINN's research analyst, writing for a professional investor who reads on a phone.

Hard rules:
1. Use ONLY the numbered sources in the message. [S#] are passages from the company's own documents (annual report, earnings-call transcripts, investor presentation). [F#] are figures computed from the company's reported financial tables.
2. Do not use anything you know about this company, its industry, or the news from outside these sources. No broker or analyst views, no market commentary, no assumptions.
3. Every sentence ends with one or more citations such as [S3] or [F2] that directly support it.
4. Copy every number exactly as written in the source you cite. Never calculate, round, convert or estimate a number.
5. If the sources do not answer something, put it in "gaps" instead of guessing.
6. Attribute management's statements ("Management said ...", "The company expects ..."). Do not present their plans as facts.
7. Be concise: short, specific sentences; no filler, no adjectives without evidence.
Reply with JSON only."""

SECTION_TASKS = {
    "business": ("Business snapshot",
                 "Explain what the company does: its businesses or segments, main products and customers, and how revenue "
                 "splits across segments or geographies if the sources say. 4–6 claims.",
                 "business overview segments revenue mix products customers brands geography share of revenue "
                 "manufacturing plants market leader company profile we are"),
    "narrative": ("What management says drove the numbers",
                  "From the call transcripts, give management's explanation for recent growth, margins and costs, and the "
                  "risks or headwinds they named. 4–6 claims; prefer the most recent call.",
                  "growth margin demand pricing raw material cost headwind tailwind volume competition outlook impact "
                  "decline improvement reason because quarter"),
}

JSON_SHAPE = '{"claims":[{"text":"one sentence ending with citations [S1]","cites":["S1"]}],"gaps":["what the sources do not say"]}'


def source_block(chunks: list[Chunk], facts: list[Fact], labels: dict[str, str] | None = None) -> tuple[str, dict]:
    """Numbered sources for a prompt and a map id -> source record (for validation and the UI)."""
    lines, smap = [], {}
    for i, c in enumerate(chunks, 1):
        sid = f"S{i}"
        lines.append(f"[{sid}] {c.title}, page {c.page}:\n{c.text}")
        smap[sid] = {"kind": "doc", "chunk": c}
    for f in facts:
        lines.append(f"[{f.id}] {f.text()}" + (f" (formula: {f.formula})" if f.formula else ""))
        smap[f.id] = {"kind": "fact", "fact": f}
    return "\n\n".join(lines), smap


class Claim(BaseModel):
    text: str
    cites: list[str]


class Checked(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    dropped: int = 0
    reasons: list[str] = Field(default_factory=list)


_CITE = re.compile(r"\[(?:[SF]\d+)(?:\s*,\s*[SF]?\d+)*\]")
_NUM = re.compile(r"(?<![A-Za-z])(\d[\d,]*(?:\.\d+)?)")
_LABELS = re.compile(r"\b(?:FY|Q[1-4]\s*FY|H[12]\s*FY|Q|H)\s*'?\d{2,4}\b|\b(?:19|20)\d{2}\b", re.I)


def numbers_in(text: str) -> set[str]:
    """Numbers as normalised strings; period labels (FY27, Q2, 2026) are not treated as figures."""
    t = _LABELS.sub(" ", text)
    out = set()
    for m in _NUM.findall(t):
        n = m.replace(",", "")
        if "." in n:
            n = n.rstrip("0").rstrip(".")          # 2,418.00 -> 2418, 12.50 -> 12.5
        out.add(n)
    return out


def _fact_strings(f: Fact) -> set[str]:
    if f.value is None:
        return set()
    v = f.value
    out = {f"{v:.0f}", f"{v:.1f}", f"{v:.2f}", str(int(v)) if v == int(v) else f"{v}"}
    return {s[:-2] if s.endswith(".0") else s for s in out}


def _allowed_numbers(cites: Iterable[str], smap: dict) -> set[str]:
    nums: set[str] = set()
    for cid in cites:
        s = smap.get(cid)
        if not s:
            continue
        if s["kind"] == "doc":
            nums |= numbers_in(s["chunk"].text)
        else:
            nums |= _fact_strings(s["fact"])
    return nums


def check_claims(raw: Optional[dict], smap: dict, key: str = "claims") -> Checked:
    out = Checked()
    if not raw:
        return out
    out.gaps = [str(g).strip() for g in (raw.get("gaps") or []) if str(g).strip()][:4]
    for item in raw.get(key) or []:
        if isinstance(item, str):
            item = {"text": item, "cites": re.findall(r"[SF]\d+", item)}
        text = str(item.get("text", "")).strip()
        cites = [c.strip("[] ") for c in (item.get("cites") or []) if isinstance(c, str)]
        cites += re.findall(r"\[([SF]\d+)\]", text)
        cites = list(dict.fromkeys(c for c in cites if c in smap))
        clean = _CITE.sub("", text).strip()
        clean = re.sub(r"\s+([.,;])", r"\1", clean)
        if not clean:
            continue
        if not cites:
            out.dropped += 1
            out.reasons.append(f"no valid citation: {clean[:60]}")
            continue
        missing = numbers_in(clean) - _allowed_numbers(cites, smap)
        if missing:
            out.dropped += 1
            out.reasons.append(f"number not in cited source ({', '.join(sorted(missing))}): {clean[:60]}")
            continue
        out.claims.append(Claim(text=clean, cites=cites))
    return out


def norm_words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", s.lower())


def quote_in(quote: str, passage: str, min_ratio: float = 0.85) -> bool:
    """True when the quote's words appear in order in the passage, allowing a few skipped or dropped words."""
    q, p = norm_words(quote), norm_words(passage)
    if len(q) < 4:
        return False
    starts = [i for i, w in enumerate(p) if w in q[:3]]
    best = 0.0
    for s0 in starts:
        j = s0
        hits = 0
        for w in q:
            k = j
            while k < len(p) and p[k] != w and k - j < 6:
                k += 1
            if k < len(p) and p[k] == w:
                hits += 1
                j = k + 1
        best = max(best, hits / len(q))
        if best >= min_ratio:
            return True
    return False


def section_prompt(task: str, sources: str, shape: str = JSON_SHAPE) -> str:
    return f"""Task: {task}

Sources:
{sources}

Return JSON exactly in this shape: {shape}"""


ASK_TASK = """Answer the investor's question using only the sources.
- If the question is not about this company's business, results, plans, management or finances (for example small talk,
  general knowledge, other companies, or anything the sources cannot speak to), return {"off_topic": true, "claims": []}.
- If it is a follow-up, read the conversation so far to understand what "it", "that" or "why" refers to.
- First claim: the direct answer in one sentence. Then 1–4 claims of supporting evidence, most specific first
  (numbers, named products, dated plans). Only include what answers THIS question; skip loosely related facts.
- If the sources only partly answer, say exactly what is missing in "gaps".
- Suggest up to 3 short follow-up questions that the company's own documents could answer."""
ASK_SHAPE = ('{"off_topic":false,"claims":[{"text":"sentence ending with citations [S1]","cites":["S1"]}],"gaps":["..."],'
             '"follow_ups":["short question"]}')

BULL_BEAR_TASK = """Write a tight bull case and bear case for the stock, using only the sources (the company's own documents
and its reported figures). 3 points each, one sentence per point, each citing its evidence. Each point should be specific to
this company: a number, a stated plan, a named risk. The bear case must not be a mirror of the bull case."""
BULL_BEAR_SHAPE = ('{"bull":[{"text":"sentence ending with citations [F1]","cites":["F1"]}],'
                   '"bear":[{"text":"sentence [S2]","cites":["S2"]}],"gaps":["..."]}')

GUIDANCE_SYSTEM = """You extract forward-looking guidance from an earnings-call transcript. Use only the passages given.
Guidance = an explicit statement by management about a FUTURE number or target: revenue/sales growth, volume growth,
EBITDA or operating margin, profit growth, capex, capacity, debt, or a dated milestone. Ignore past results, analysts'
questions, and vague hopes without a target ("we hope to do well"). Copy the quote word for word from the passage.
Reply with JSON only."""

GUIDANCE_SHAPE = ('{"items":[{"metric":"revenue_growth | ebitda_margin | pat_growth | volume_growth | capex | debt | other",'
                  '"statement":"what was guided, in plain words","quote":"exact words from the passage, max 40 words",'
                  '"low":12,"high":15,"unit":"% | crore | other","horizon":"e.g. FY27, next quarter, H2 FY27, 2-3 years",'
                  '"cite":"S2"}]}')


def guidance_prompt(call_title: str, sources: str) -> str:
    return f"""Calls: {call_title}. Each passage's header names the call it comes from.

Passages:
{sources}

List every explicit guidance item (at most 10). Use null for low/high when no number was given. "cite" is the passage
the quote comes from. Return JSON exactly in this shape: {GUIDANCE_SHAPE}"""

"""Management changes: who is coming in, who is leaving, and a short, sourced background on the incoming person.

Sources, best first (each line of the background keeps its source):
  1. The company's own Reg-30 filing PDF ("Brief profile" section)        PRIMARY_DOC
  2. A web-search API (Tavily, optional key) restricted to trusted sites  EXTERNAL_WEB
  3. Wikipedia summary, only if it clearly is the same person             EXTERNAL_WEB
  4. News headlines about the person (always available)                  EXTERNAL_WEB
If an LLM key is configured, the background is rewritten as a 3–4 sentence brief that may only use those
sources and must cite them; otherwise FINN shows the extracted sentences as they are. LinkedIn is never used
(its terms forbid scraping, D-51).
"""
from __future__ import annotations

import io
import re
from typing import Callable, Optional

from pydantic import BaseModel, Field

NAME = r"((?:(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+)?[A-Z][a-zA-Z'’\-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'’\-]+){1,2})"
ROLE = (r"(chief executive officer|chief financial officer|chief operating officer|managing director|whole[- ]time director|"
        r"executive director|independent director|chairman|chairperson|vice chairman|ceo|cfo|coo|cto|md|president|"
        r"company secretary|chief [a-z]+ officer)")
TITLE = re.compile(r"^(Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+")

INCOMING = [
    rf"\b(?i:who is)\s+{NAME}",
    rf"\b(?i:meet)\s+{NAME}",
    rf"\b(?i:names|appoints|elevates|ropes in|hires|picks|taps)\s+{NAME}",
    rf"\b(?i:appointment of)\s+{NAME}",
    rf"{NAME}\s+(?:to take over|takes over|to succeed|succeeds|appointed|named|to join|joins|elevated|to head|to lead|as new|takes charge)",
    rf"{NAME},?\s+(?:as|the)\s+(?:new\s+)?{ROLE}",
]
OUTGOING = [
    rf"{NAME}\s+(?i:(?:to\s+)?(?:retire|retires|resign|resigns|step down|steps down|quits|exits|to exit|moves on|cessation))\b",
    rf"\b(?i:resignation of)\s+(?:(?i:ceo|cfo|md|coo|chairman)\s+)?{NAME}",
    rf"\bsucceed(?:s|ing)?\s+{NAME}",
]
STOP = {"Q1", "Q2", "Q3", "Q4", "The", "India", "Board", "Group", "Tata Group", "New", "Who", "Meet", "Shares", "Stock"}


class Change(BaseModel):
    incoming: Optional[str] = None
    outgoing: Optional[str] = None
    role: Optional[str] = None


ROLE_PREFIX = re.compile(r"^(?:CEO|CFO|COO|CTO|MD|Chairman|Chairperson|Director|Founder|Co-founder|President)\s+", re.I)


def _clean(name: str, company_words: set[str]) -> Optional[str]:
    n = ROLE_PREFIX.sub("", TITLE.sub("", name.strip(" ,.'’")))
    parts = n.split()
    if len(parts) < 2 or n in STOP or parts[0] in STOP:
        return None
    if {p.lower() for p in parts} & company_words:
        return None
    return n


def parse_change(text: str, company_name: str = "") -> Change:
    """Extract incoming/outgoing person and role from a headline or filing sentence."""
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", company_name)} - {"ltd", "limited", "india", "the", "and"}
    c = Change()
    for pat in INCOMING:
        m = re.search(pat, text)
        if m and (n := _clean(m.group(1), words)):
            c.incoming = n
            break
    for pat in OUTGOING:
        m = re.search(pat, text)
        if m and (n := _clean(m.group(1), words)) and n != c.incoming:
            c.outgoing = n
            break
    r = re.search(ROLE, text, flags=re.I)
    if r:
        c.role = {"ceo": "CEO", "cfo": "CFO", "coo": "COO", "cto": "CTO", "md": "MD"}.get(r.group(1).lower(), r.group(1).lower())
    return c


# ---------------------------------------------------------------- background
class BioLine(BaseModel):
    text: str
    source: str
    url: Optional[str] = None


class Person(BaseModel):
    name: str
    role: Optional[str] = None
    company: str
    symbol: str
    outgoing: Optional[str] = None
    brief: Optional[str] = None                 # LLM-written, cited [n]; None without an LLM key
    lines: list[BioLine] = Field(default_factory=list)   # extracted, sourced background sentences
    coverage: list[BioLine] = Field(default_factory=list)   # headlines about the person
    method: str = "headlines"                   # filing | search | wikipedia | headlines (+ "+llm")


BIO_HINT = re.compile(r"\b(founder|co-founder|partner|served|serving|joined|previously|former|ex-|veteran|experience|"
                      r"graduate|degree|alumnus|chartered accountant|llm|mba|iit|iim|career|years|led|headed|director at|"
                      r"chief|head of|worked)\b", re.I)


def sentences_about(text: str, name: str, limit: int = 3) -> list[str]:
    surname = name.split()[-1]
    out = []
    for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        if (surname in s or "He " in s[:3] or "She " in s[:4]) and BIO_HINT.search(s) and 40 <= len(s) <= 320:
            out.append(s.strip())
        if len(out) >= limit:
            break
    return out


def brief_profile_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """The 'Brief profile' paragraph of a Reg-30 appointment filing, if the PDF has a text layer."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages[:6])
    except Exception:  # noqa: BLE001 - malformed or scanned PDFs simply yield no profile
        return None
    text = " ".join(text.split())
    m = re.search(r"brief profile[^:]{0,60}:?\s*(.{60,900}?)(?:\s\d\.\s|disclosure of relationship|relationship between|$)",
                  text, flags=re.I)
    return m.group(1).strip() if m else None


def wikipedia_match(summary: dict, name: str, company: str) -> Optional[str]:
    """Accept a Wikipedia summary only if it's clearly this person: a biography naming them and the company or India."""
    if not summary or summary.get("type") != "standard":
        return None
    extract = summary.get("extract") or ""
    first = company.split()[0]
    if name.split()[-1] in extract and (first in extract or "Indian" in extract):
        return extract
    return None


LLM = Callable[[str], Optional[str]]


def write_brief(person: Person, llm: Optional[LLM]) -> Optional[str]:
    """3–4 sentences using only the numbered sources; returns None if the LLM is missing or doesn't cite."""
    if llm is None or not (person.lines or person.coverage):
        return None
    srcs = person.lines + person.coverage[:4]
    numbered = "\n".join(f"[{i + 1}] {s.text} ({s.source})" for i, s in enumerate(srcs))
    prompt = (f"Write a 3-4 sentence professional background of {person.name}, the incoming "
              f"{person.role or 'executive'} of {person.company}, for an investor. Use ONLY the numbered sources below; "
              f"put the source number in brackets after each sentence, like [2]. If the sources don't say something, "
              f"leave it out. No opinions, no adjectives like 'renowned'.\n\nSources:\n{numbered}")
    out = llm(prompt)
    if not out:
        return None
    sents = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", out.strip()) if s]
    cited = [s for s in sents if re.search(r"\[\d+\]", s)]
    return " ".join(cited) if cited and len(cited) >= len(sents) - 1 else None

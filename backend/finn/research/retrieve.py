"""Lexical retrieval (BM25) over document chunks. No embeddings: free, deterministic, fast on a few thousand chunks,
and good at the phrases investors ask about ("guidance", "EBITDA margin", "capex", "FY27")."""
from __future__ import annotations

import math
import re
from collections import Counter

from .documents import Chunk

_STOP = set("""a an the and or of to in on for with by from at as is are was were be been this that these those it its we
our us you your they their i he she them his her there here which who whom what when where how than then so such
can could would should will shall may might do does did done have has had having not no yes also very into over
under about more most less least just only any all each both other some own same too up down out off again further
once ladies gentlemen thank thanks please sir madam question questions answer moderator""".split())


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?%?", text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        for c in chunks:
            if not c.tokens:
                c.tokens = tokens(c.text)
        self.n = len(chunks)
        self.avg = sum(len(c.tokens) for c in chunks) / self.n if self.n else 1.0
        df: Counter = Counter()
        for c in chunks:
            df.update(set(c.tokens))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(c.tokens) for c in chunks]

    def search(self, query: str, k: int = 8, kinds: tuple[str, ...] | None = None, doc_ids: set[str] | None = None,
               boost: dict[str, float] | None = None) -> list[tuple[Chunk, float]]:
        q = tokens(query)
        scored = []
        for i, c in enumerate(self.chunks):
            if kinds and c.kind not in kinds:
                continue
            if doc_ids is not None and c.doc_id not in doc_ids:
                continue
            tf, dl, s = self.tf[i], len(c.tokens), 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            if s and boost:
                s *= boost.get(c.kind, 1.0)
            if s > 0:
                scored.append((c, s))
        scored.sort(key=lambda x: -x[1])
        out, seen = [], set()
        for c, s in scored:                       # skip near-duplicates (overlapping windows of one page)
            key = (c.doc_id, c.page)
            if key in seen and len(out) >= 3:
                continue
            seen.add(key)
            out.append((c, s))
            if len(out) >= k:
                break
        return out


def budget(chunks: list[Chunk], max_chars: int) -> list[Chunk]:
    """Keep chunks in order until the character budget is used (prompt size control for 8K-TPM models)."""
    out, used = [], 0
    for c in chunks:
        if used + len(c.text) > max_chars and out:
            break
        out.append(c)
        used += len(c.text)
    return out

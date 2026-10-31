"""Ticker normalisation for NSE and BSE conventions.

Accepted inputs (case-insensitive, surrounding spaces ignored):
  INFY            -> NSE:INFY   (bare symbol defaults to NSE)
  NSE:INFY        -> NSE:INFY
  INFY.NS         -> NSE:INFY   (Yahoo suffix)
  BSE:500209      -> BSE:500209
  500209 / 500209.BO / BOM:500209 -> BSE:500209 (six-digit scrip code)
  M&M, BAJAJ-AUTO -> NSE:M&M, NSE:BAJAJ-AUTO (NSE symbols may contain & and -)
"""
from __future__ import annotations

import re

from .models import Instrument

_NSE_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")
_BSE_RE = re.compile(r"^\d{6}$")


class SymbolError(ValueError):
    """Raised for inputs that are not a valid NSE symbol or BSE scrip code."""


def normalize(raw: str, default_exchange: str = "NSE") -> Instrument:
    if raw is None:
        raise SymbolError("empty symbol")
    s = raw.strip().upper().replace(" ", "")
    if not s:
        raise SymbolError("empty symbol")

    exchange: str | None = None
    for prefix, ex in (("NSE:", "NSE"), ("BSE:", "BSE"), ("BOM:", "BSE")):
        if s.startswith(prefix):
            exchange, s = ex, s[len(prefix):]
            break
    if exchange is None:
        if s.endswith(".NS"):
            exchange, s = "NSE", s[:-3]
        elif s.endswith(".BO"):
            exchange, s = "BSE", s[:-3]
        elif _BSE_RE.match(s):
            exchange = "BSE"
        else:
            exchange = default_exchange

    if exchange == "BSE":
        if not _BSE_RE.match(s):
            raise SymbolError(f"BSE listings are identified by a six-digit scrip code, got {raw!r}")
        return Instrument(exchange="BSE", code=s, key=f"BSE:{s}", yahoo=f"{s}.BO")
    if not _NSE_RE.match(s) or s.isdigit():
        raise SymbolError(f"not a valid NSE symbol: {raw!r}")
    return Instrument(exchange="NSE", code=s, key=f"NSE:{s}", yahoo=f"{s}.NS")


def try_normalize(raw: str) -> Instrument | None:
    try:
        return normalize(raw)
    except SymbolError:
        return None

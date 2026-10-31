"""SQLite store and fetch cache (ARCHITECTURE §4b: ephemeral on Render, rebuilt at boot).

Holds price bars, announcements (deduplicated by `uid`) and a fetch log used for TTL caching and
source status. Reads never trigger network calls; only the refresh job writes here.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import Announcement, NewsItem, PriceBar, Provenance

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_bars (
  instrument_key TEXT NOT NULL, date TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL,
  provenance TEXT NOT NULL,
  PRIMARY KEY (instrument_key, date)
);
CREATE TABLE IF NOT EXISTS announcements (
  uid TEXT PRIMARY KEY, filed_at TEXT NOT NULL, symbol TEXT, source TEXT NOT NULL,
  record TEXT NOT NULL, first_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ann_filed ON announcements(filed_at);
CREATE TABLE IF NOT EXISTS news (
  uid TEXT PRIMARY KEY, symbol TEXT NOT NULL, published_at TEXT NOT NULL, record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_news_pub ON news(published_at);
CREATE TABLE IF NOT EXISTS people (
  symbol TEXT NOT NULL, name TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY (symbol, name)
);
CREATE TABLE IF NOT EXISTS company (
  symbol TEXT PRIMARY KEY, record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_pages (
  doc_id TEXT NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY (doc_id, page)
);
CREATE TABLE IF NOT EXISTS docs (
  doc_id TEXT PRIMARY KEY, record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research (
  key TEXT PRIMARY KEY, saved_at TEXT NOT NULL, record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fetch_log (
  source TEXT NOT NULL, key TEXT NOT NULL, fetched_at TEXT NOT NULL,
  ok INTEGER NOT NULL, error TEXT, items INTEGER DEFAULT 0,
  PRIMARY KEY (source, key)
);
CREATE TABLE IF NOT EXISTS source_success (
  source TEXT PRIMARY KEY, last_success_at TEXT NOT NULL
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    # ---------- prices ----------
    def upsert_bars(self, bars: Iterable[PriceBar]) -> int:
        rows = [(b.instrument_key, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume,
                 b.provenance.model_dump_json()) for b in bars]
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO price_bars VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(instrument_key, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, "
                "volume=excluded.volume, provenance=excluded.provenance", rows)
        return len(rows)

    def bars(self, instrument_key: str, limit: int = 400) -> list[PriceBar]:
        with self._lock:
            cur = self._db.execute(
                "SELECT * FROM price_bars WHERE instrument_key=? ORDER BY date DESC LIMIT ?", (instrument_key, limit))
            rows = cur.fetchall()
        return [PriceBar(instrument_key=r["instrument_key"], date=date.fromisoformat(r["date"]), open=r["open"],
                         high=r["high"], low=r["low"], close=r["close"], volume=r["volume"],
                         provenance=Provenance.model_validate_json(r["provenance"])) for r in reversed(rows)]

    # ---------- announcements ----------
    def add_announcements(self, items: Iterable[Announcement]) -> tuple[int, int]:
        """Insert new records; duplicates (same uid) are merged, never duplicated. Returns (new, merged)."""
        new = merged = 0
        now = utcnow().isoformat()
        with self._lock, self._db:
            for a in items:
                cur = self._db.execute("SELECT record FROM announcements WHERE uid=?", (a.uid,)).fetchone()
                if cur is None:
                    self._db.execute("INSERT INTO announcements VALUES (?,?,?,?,?,?)",
                                     (a.uid, _utc(a.filed_at), a.symbol, a.source, a.model_dump_json(), now))
                    new += 1
                    continue
                old = Announcement.model_validate_json(cur["record"])
                upd = _merge(old, a)
                if upd != old:
                    self._db.execute("UPDATE announcements SET symbol=?, record=? WHERE uid=?",
                                     (upd.symbol, upd.model_dump_json(), a.uid))
                merged += 1
        return new, merged

    def announcements_between(self, start: datetime, end: datetime) -> list[Announcement]:
        with self._lock:
            rows = self._db.execute(
                "SELECT record FROM announcements WHERE filed_at > ? AND filed_at <= ? ORDER BY filed_at DESC",
                (_utc(start), _utc(end))).fetchall()
        return [Announcement.model_validate_json(r["record"]) for r in rows]

    def count_announcements(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]

    # ---------- news ----------
    def add_news(self, items: Iterable[NewsItem]) -> int:
        """Insert headlines; the same story (same uid) is kept once, from whichever feed saw it first."""
        new = 0
        with self._lock, self._db:
            for n in items:
                cur = self._db.execute("INSERT OR IGNORE INTO news VALUES (?,?,?,?)",
                                       (n.uid, n.symbol, _utc(n.published_at), n.model_dump_json()))
                new += cur.rowcount
        return new

    def news_between(self, start: datetime, end: datetime) -> list[NewsItem]:
        with self._lock:
            rows = self._db.execute("SELECT record FROM news WHERE published_at > ? AND published_at <= ? "
                                    "ORDER BY published_at DESC", (_utc(start), _utc(end))).fetchall()
        return [NewsItem.model_validate_json(r["record"]) for r in rows]

    # ---------- people ----------
    def put_person(self, symbol: str, name: str, record_json: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO people VALUES (?,?,?) ON CONFLICT(symbol,name) DO UPDATE SET record=excluded.record",
                             (symbol, name, record_json))

    def get_person(self, symbol: str, name: str) -> Optional[str]:
        with self._lock:
            r = self._db.execute("SELECT record FROM people WHERE symbol=? AND name=?", (symbol, name)).fetchone()
        return r["record"] if r else None

    # ---------- company snapshots (screener) ----------
    def put_company(self, symbol: str, record_json: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO company VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET record=excluded.record",
                             (symbol, record_json))

    def get_company(self, symbol: str) -> Optional[str]:
        with self._lock:
            r = self._db.execute("SELECT record FROM company WHERE symbol=?", (symbol,)).fetchone()
        return r["record"] if r else None

    def news_for(self, symbol: str, limit: int = 30) -> list[NewsItem]:
        with self._lock:
            rows = self._db.execute("SELECT record FROM news WHERE symbol=? ORDER BY published_at DESC LIMIT ?",
                                    (symbol, limit)).fetchall()
        return [NewsItem.model_validate_json(r["record"]) for r in rows]

    def announcements_for(self, symbol: str, limit: int = 40) -> list[Announcement]:
        with self._lock:
            rows = self._db.execute("SELECT record FROM announcements WHERE symbol=? ORDER BY filed_at DESC LIMIT ?",
                                    (symbol, limit)).fetchall()
        return [Announcement.model_validate_json(r["record"]) for r in rows]

    # ---------- fetch log / cache ----------
    # ---------- research documents (local cache only; never committed, D-31) ----------
    def put_doc(self, doc_id: str, record_json: str, pages: list[str] | None = None) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO docs VALUES (?,?)", (doc_id, record_json))
            if pages is not None:
                self._db.execute("DELETE FROM doc_pages WHERE doc_id=?", (doc_id,))
                self._db.executemany("INSERT INTO doc_pages VALUES (?,?,?)",
                                     [(doc_id, i + 1, t) for i, t in enumerate(pages)])

    def get_doc(self, doc_id: str) -> Optional[str]:
        with self._lock:
            r = self._db.execute("SELECT record FROM docs WHERE doc_id=?", (doc_id,)).fetchone()
        return r["record"] if r else None

    def doc_pages(self, doc_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute("SELECT text FROM doc_pages WHERE doc_id=? ORDER BY page", (doc_id,)).fetchall()
        return [r["text"] for r in rows]

    def put_research(self, key: str, record_json: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO research VALUES (?,?,?)", (key, _utc(utcnow()), record_json))

    def get_research(self, key: str, max_age_hours: float) -> Optional[str]:
        with self._lock:
            r = self._db.execute("SELECT saved_at, record FROM research WHERE key=?", (key,)).fetchone()
        if not r or utcnow() - datetime.fromisoformat(r["saved_at"]) > timedelta(hours=max_age_hours):
            return None
        return r["record"]

    def log_fetch(self, source: str, key: str, ok: bool, error: str | None = None, items: int = 0,
                  at: datetime | None = None) -> None:
        at = at or utcnow()
        with self._lock, self._db:
            self._db.execute("INSERT INTO fetch_log VALUES (?,?,?,?,?,?) ON CONFLICT(source,key) DO UPDATE SET "
                             "fetched_at=excluded.fetched_at, ok=excluded.ok, error=excluded.error, items=excluded.items",
                             (source, key, at.isoformat(), int(ok), error, items))
            if ok:
                self._db.execute("INSERT INTO source_success VALUES (?,?) ON CONFLICT(source) DO UPDATE SET "
                                 "last_success_at=excluded.last_success_at", (source, at.isoformat()))

    def last_fetch(self, source: str, key: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._db.execute("SELECT * FROM fetch_log WHERE source=? AND key=?", (source, key)).fetchone()

    def is_fresh(self, source: str, key: str, ttl_minutes: float, now: datetime | None = None) -> bool:
        """True if a successful fetch happened within the TTL: the caller must not hit the network."""
        row = self.last_fetch(source, key)
        if row is None or not row["ok"]:
            return False
        return (now or utcnow()) - datetime.fromisoformat(row["fetched_at"]) < timedelta(minutes=ttl_minutes)

    def in_backoff(self, source: str, key: str, backoff_minutes: float, now: datetime | None = None) -> bool:
        """True if the last attempt FAILED within the backoff period: don't hammer a broken source or symbol."""
        row = self.last_fetch(source, key)
        if row is None or row["ok"]:
            return False
        return (now or utcnow()) - datetime.fromisoformat(row["fetched_at"]) < timedelta(minutes=backoff_minutes)

    def source_rows(self, source: str) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute("SELECT * FROM fetch_log WHERE source=? ORDER BY fetched_at DESC", (source,)).fetchall()

    def last_success(self, source: str) -> Optional[datetime]:
        with self._lock:
            r = self._db.execute("SELECT last_success_at FROM source_success WHERE source=?", (source,)).fetchone()
        return datetime.fromisoformat(r[0]) if r else None


def _merge(old: Announcement, new: Announcement) -> Announcement:
    """Fill gaps from a later sighting of the same filing; the original subject and link are kept."""
    data = old.model_dump()
    for field in ("symbol", "detail", "exchange_id", "source_category"):
        if data.get(field) in (None, "") and getattr(new, field):
            data[field] = getattr(new, field)
    if not old.attachments and new.attachments:
        data["attachments"] = [a.model_dump() for a in new.attachments]
    return Announcement.model_validate(data)


def _utc(dt: datetime) -> str:
    """Stored timestamps are UTC ISO strings so that SQL string comparison orders them correctly."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime: all timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat()


def dumps(obj) -> str:
    return json.dumps(obj, default=str)

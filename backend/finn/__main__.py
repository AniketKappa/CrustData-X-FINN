"""Command line: python -m finn <command> [--fixture]

  refresh       fetch prices and announcements (respects caches; --force to ignore TTLs)
  digest        print the digest from the store (no network); --window 24|72|168, --json
  check-live    one live call per source, to verify connectivity on your machine (never run in tests)
  check-llm     one tiny call per configured model (Groq / OpenRouter), to verify keys
  research SYM  build the research dossier for an NSE symbol and print a summary (e.g. research ASTRAL)
"""
from __future__ import annotations

import argparse
import json
import sys

from .factory import build_pipeline
from .models import AlertThresholds


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="finn")
    p.add_argument("command", choices=["refresh", "digest", "check-live", "inspect-rss", "check-llm", "research"])
    p.add_argument("symbol", nargs="?")
    p.add_argument("--fixture", action="store_true", help="synthetic data, no network")
    p.add_argument("--force", action="store_true")
    p.add_argument("--window", type=int, default=24)
    p.add_argument("--price-pct", type=float)
    p.add_argument("--vol-mult", type=float)
    p.add_argument("--json", action="store_true")
    p.add_argument("--db")
    a = p.parse_args(argv)
    mode = "fixture" if a.fixture else "live"
    pipe = build_pipeline(mode, db_path=a.db)
    if a.command == "check-llm":
        return _check_llm(pipe)
    if a.command == "research":
        return _research(pipe, (a.symbol or "").upper())

    if a.command == "check-live":
        return check_live(pipe)
    if a.command == "inspect-rss":
        return inspect_rss(pipe)
    if a.command == "refresh" or mode == "fixture":
        r = pipe.refresh_all(force=a.force)
        if a.command == "refresh":
            for k, v in r.items():
                print(f"{k:13} fetched {len(v['fetched']):3}  cached {len(v['skipped_fresh']):3}  "
                      f"backing off {len(v['skipped_backoff']):3}  new items {v['new_announcements']:3}  "
                      f"failed {v['failed'] or '-'}")
            return 0
    th = pipe.s.thresholds.model_copy(update={k: v for k, v in
                                              (("pct_change_abs", a.price_pct), ("volume_multiple", a.vol_mult)) if v})
    d = pipe.digest(a.window, AlertThresholds.model_validate(th.model_dump()))
    if a.json:
        print(d.model_dump_json(indent=2))
        return 0
    print(f"FINN digest, last {d.window_hours} h to {d.window_end:%d %b %Y %H:%M} IST" + ("  [FIXTURE]" if d.fixture else ""))
    for label, items in (("READ FIRST", d.high), ("OTHER UPDATES", d.normal), (f"ROUTINE ({d.routine_count})", d.routine)):
        print(f"\n{label}")
        for i in items:
            print(f"  {i.score.total:5.1f}  {i.symbol or '?':10} {i.category:18} {i.filed_at:%d %b %H:%M}  {i.title}")
    print(f"\nIN THE NEWS ({len(d.news)})")
    for i in d.news:
        print(f"  {i.score.total:5.1f}  {i.symbol:10} {i.category:18} {i.filed_at:%d %b %H:%M}  {i.title}  [{i.news.publisher}]")
    for i in d.high + d.normal + d.news:
        if i.results:
            r = i.results
            print(f"\nRESULTS {i.symbol} ({r['basis']}, {r['periods'][0]} vs {r['periods'][1]} / {r['periods'][2]}, Screener)")
            for row in r["rows"]:
                f = lambda v: "-" if v is None else f"{v:+.1f}%"  # noqa: E731
                print(f"  {row['metric']:8} {row['latest'] if row['latest'] is not None else 'n/m':>10}  QoQ {f(row['qoq']):>7}  YoY {f(row['yoy']):>7}")
            break
    print("\nDISCLOSURES")
    for x in d.disclosures:
        print("  - " + x)
    return 0


def inspect_rss(pipe) -> int:
    """Fetch the NSE RSS feed once and show how FINN reads every item. Nothing is stored."""
    import xml.etree.ElementTree as ET

    from .classify import classify
    from .http import FetchError
    from .providers.announcements import SourceSchemaError

    src = pipe.nse_rss
    if src is None:
        print("nse_rss is disabled in config/sources.yaml")
        return 1
    try:
        raw = src.http.get(src.url).text
        items = src.fetch()
    except (FetchError, SourceSchemaError) as e:
        print(f"[fail] {e}")
        return 1
    dates = [it.findtext("pubDate") for it in ET.fromstring(raw).findall("./channel/item")]
    print(f"{len(dates)} items in feed, {len(items)} parsed. Raw pubDate examples: {dates[:3]}")
    if items:
        span = max(i.filed_at for i in items) - min(i.filed_at for i in items)
        print(f"Feed covers {span} (oldest {min(i.filed_at for i in items):%d %b %H:%M}, newest "
              f"{max(i.filed_at for i in items):%d %b %H:%M} IST)\n")
    for i in items:
        c = classify(i)
        print(f"{i.filed_at:%d %b %H:%M}  {(i.symbol or '-'):10} {c.category:17} {i.company_name[:38]:38}  {i.subject[:60]}")
    unmatched = sorted({i.company_name for i in items if not i.symbol})
    print(f"\n{len(items) - sum(1 for i in items if not i.symbol)} mapped to portfolio symbols; "
          f"{len(unmatched)} company names not in the portfolio (expected for most of the market).")
    return 0


def check_live(pipe) -> int:
    """Makes a handful of real requests. Use on a machine with internet access; results are printed, not stored."""
    from .symbols import normalize

    ok = True
    try:
        from .market import expected_session

        bars = pipe.prices.fetch(normalize("INFY"), 10)
        exp = expected_session(pipe.clock())
        lag = "up to date" if bars[-1].date >= exp else f"behind the expected session {exp} (provider lag or holiday)"
        print(f"[ok]   prices ({pipe.prices.name}): {len(bars)} bars for INFY.NS, last {bars[-1].date} "
              f"close {bars[-1].close:.2f}, {lag}")
    except Exception as e:  # noqa: BLE001 - diagnostic command
        ok = False
        print(f"[fail] prices ({pipe.prices.name}): {e}")
    for src in (pipe.nse_rss, pipe.bse_rss):
        if src is None:
            continue
        try:
            items = src.fetch()
            mapped = sum(1 for i in items if i.symbol)
            print(f"[ok]   {src.name}: {len(items)} items, {mapped} mapped to portfolio symbols")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[fail] {src.name}: {e}")
    if pipe.news is not None:
        try:
            c = pipe.portfolio.companies["INFY"] if "INFY" in pipe.portfolio.companies else pipe.portfolio.holdings[0]
            items = pipe.news.fetch_company(c)
            pubs = sorted({i.publisher for i in items})
            print(f"[ok]   news (Google News RSS): {len(items)} trusted headlines about {c.name}; publishers: {', '.join(pubs[:6]) or '-'}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[fail] news (Google News RSS): {e}")
        for f in pipe.s.sources["news"].get("publisher_feeds", []):
            try:
                items = pipe.news.fetch_publisher(f)
                print(f"[ok]   news feed {f['name']}: reachable, {len(items)} headlines about portfolio companies right now")
            except Exception as e:  # noqa: BLE001
                ok = False
                print(f"[fail] news feed {f['name']}: {e}")
    if pipe.screener is not None:
        try:
            b = pipe.screener.fetch_results("INFY", False)
            rev = b.rows[0]
            print(f"[ok]   screener: INFY {b.basis} quarters to {b.periods[0]}; revenue {rev.latest} cr, QoQ {rev.qoq:+.1f}%")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[fail] screener: {e}")
    if pipe.bse_api is not None:
        try:
            items = pipe.bse_api.fetch_code("RELIANCE", "500325")
            print(f"[ok]   bse_api: {len(items)} filings for RELIANCE (500325) in the last 8 days")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[fail] bse_api: {e}")
    if pipe.nse_json is None:
        print("[off]  nse_json: disabled (NSE returns 403 to non-browser clients; D-49)")
    else:
        try:
            items = pipe.nse_json.fetch_symbol("INFY")
            print(f"[ok]   nse_json: {len(items)} items for INFY")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[fail] nse_json: {e}")
    return 0 if ok else 1


def _check_llm(pipe) -> int:
    llm, ok = pipe.llm, True
    for route in ("fast", "long"):
        for prov, key, base, model in llm.slots(route):
            llm._cache.clear()
            out = llm._post(route, prov, key, base, model, [{"role": "user", "content": "Reply with the word OK."}],
                            20, False, 30)
            print(f"[{'ok' if out else 'fail'}]   {route:4} {prov}/{model}" + ("" if out else f": {llm.last_error}"))
            ok = ok and bool(out) if prov == "groq" else ok
    if not llm.slots("long"):
        print("[off]  no GROQ_API_KEY or OPENROUTER_API_KEY in .env")
        return 1
    return 0 if ok else 1


def _research(pipe, sym: str) -> int:
    if not sym:
        print("usage: python -m finn research SYMBOL")
        return 2
    job = pipe.research.build(sym)
    print(f"{job.get('name') or sym}: {job['status']} {job.get('error') or ''}")
    for s in job["steps"]:
        print(f"  {s['status']:8} {s['label']}{' - ' + s['note'] if s.get('note') else ''}")
    for d in job["documents"]:
        print(f"  doc {d['status']:6} {d['title']} ({d['pages_read']}/{d['pages']} pages) {d.get('error') or ''}")
    L = (job.get("sections") or {}).get("ledger") or {}
    for r in L.get("rows", []):
        print(f"  promise [{r['verdict']}] {r['said_in']}: {r['statement'][:90]} -> actual {r['actual']}")
    for k in ("business", "narrative"):
        sec = (job.get("sections") or {}).get(k)
        if sec:
            print(f"  {k}: {len(sec.get('claims', []))} cited sentences, {sec.get('dropped', 0)} dropped")
    if job.get("usage"):
        print(f"  llm: {job['usage']}")
    return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())

"""Fixture mode for research: synthetic PDFs for the invented "Fixture Cables" company and a rule-based stand-in
for the LLM. Both are labelled as demo data and never used in live mode. They let the tests and the offline UI run
the real pipeline (PDF reading, chunking, retrieval, validation, ledger) without network or keys."""
from __future__ import annotations

import json
import re
from typing import Optional

TEXTS = {
    "cc/t2.pdf": [
        "Fixture Cables Limited - Q1 FY27 Earnings Conference Call - July 2026 (synthetic demo document)",
        "Management: Welcome everyone. Revenue for the quarter grew 14.9 percent year on year to Rs 2,281 crore.",
        "Demand from power utilities and data centres remained strong and our order book stands at Rs 3,100 crore.",
        "Copper prices were volatile during the quarter and we passed on most of the increase to customers.",
        "Outlook: We expect revenue growth of 12 to 14 percent for FY27 on the back of capacity additions.",
        "We are guiding to EBITDA margin of 12 to 13 percent for FY27 as the new plant stabilises.",
        "For Q2 FY27 we are guiding to revenue growth of 16 percent driven by export orders.",
        "Analyst: What is the risk from competition? Management: Pricing pressure from new entrants is a headwind",
        "in the building wire segment, which is about 30 percent of revenue.",
    ],
    "cc/t.pdf": [
        "Fixture Cables Limited - Q2 FY27 Earnings Conference Call - October 2026 (synthetic demo document)",
        "Management: Revenue grew 14.1 percent year on year to Rs 2,418 crore in Q2 FY27.",
        "EBITDA margin declined to 10.7 percent because of higher copper costs and a one-time plant start-up expense.",
        "For the next quarter we expect margin to recover to 12 percent as the new Gujarat plant reaches full utilisation.",
        "We plan capex of Rs 400 crore over the next two years for a new extra-high-voltage cable line.",
        "Export revenue is now 18 percent of sales and we expect exports to keep growing faster than the domestic business.",
        "Risk: delays in utility payments have stretched receivables, and working capital is a focus area for us.",
    ],
    "cc/p.pdf": [
        "Fixture Cables Limited - Investor Presentation - October 2026 (synthetic demo document)",
        "Company overview: Fixture Cables makes power cables, building wires and fast-moving electrical goods.",
        "Segment mix FY26: power cables 55 percent, building wires 30 percent, electrical goods 15 percent of revenue.",
        "Customers include state power utilities, EPC contractors, data-centre developers and 4,200 retail dealers.",
        "Manufacturing: three plants in Gujarat and Maharashtra with a fourth plant commissioned in Q1 FY27.",
    ],
    "ar/2026.pdf": [
        "Fixture Cables Limited - Annual Report FY2026 (synthetic demo document)",
        "Business overview: We are a manufacturer of wires and cables serving power transmission, infrastructure and housing.",
        "Our products are sold in 22 countries; exports were 16 percent of revenue in FY26.",
        "Management discussion: revenue rose to Rs 8,600 crore in FY26 while net profit was Rs 716 crore.",
        "Risks: volatility in copper and aluminium prices, competition from new entrants, and customer concentration in",
        "the utility segment where the top five customers contribute 21 percent of revenue.",
    ],
    "bse/att/fx_results_q2fy27.pdf": [
        "Fixture Cables Limited (synthetic demo document)",
        "Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026",
        "(Rs in crore)    Quarter ended 30.09.2026   Quarter ended 30.06.2026   Quarter ended 30.09.2025",
        "Revenue from operations 2,418.00 2,281.00 2,119.00",
        "Other income 20.00 20.00 20.00",
        "Total income 2,438.00 2,301.00 2,139.00",
        "Finance costs 10.00 10.00 10.00",
        "Depreciation and amortisation expense 25.00 25.00 25.00",
        "Profit before tax 244.00 254.00 237.00",
        "Net profit for the period 182.00 189.00 178.00",
    ],
    "bse/att/fx_rating.pdf": [
        "Fixture Cables Limited (synthetic demo document)",
        "Sub: Intimation of credit rating under Regulation 30.",
        "Fixture Ratings has upgraded the long-term rating of the company's bank facilities of Rs 750 crore to AA+ (Stable) from AA (Positive).",
    ],
    "bse/att/fx_74_5.pdf": ["Fixture Cables Limited (synthetic demo document)", "Certificate under Regulation 74(5) for the quarter."],
}


def pdf_bytes(lines: list[str]) -> bytes:
    """A minimal, valid one-page PDF with the given lines of text (Helvetica)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(f"({esc(l)}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def fixture_doc_bytes(url: str) -> bytes:
    for k, v in TEXTS.items():
        if url.endswith(k):
            return pdf_bytes(v)
    raise FileNotFoundError(url)


# ------------------------------------------------------------------ rule-based stand-in for the LLM
_SRC = re.compile(r"\[(S\d+)\][^\n]*\n(.+?)(?=\n\n(?:\[|List |Return |Task|Promises)|\Z)", re.S)


def _sentences(prompt: str) -> list[tuple[str, str]]:
    out = []
    for sid, text in _SRC.findall(prompt):
        for s in re.split(r"(?<=[.!?])\s+|\n", text):
            s = s.strip()
            if len(s) > 30 and "synthetic demo document" not in s:
                out.append((sid, s))
    return out


class FixtureLLM:
    """Answers from the given sources only, mechanically. Lets the offline demo and tests exercise validation."""
    available = True
    last_provider, last_model, last_error = "fixture", "rule-based", None

    def usage_summary(self) -> dict:
        return {"calls": 0, "ok": 0, "tokens": 0, "by_model": {"fixture": 0}, "last_error": None}

    def __call__(self, prompt: str, system: Optional[str] = None, max_tokens: int = 700) -> Optional[str]:
        return None

    def complete(self, prompt, system=None, max_tokens=900, route="long", json_mode=False):
        d = self.complete_json(prompt, system, max_tokens, route)
        return json.dumps(d) if d else None

    def complete_json(self, prompt: str, system: Optional[str] = None, max_tokens: int = 900, route: str = "long"):
        sents = _sentences(prompt)
        if system and "quarterly results table" in system:
            def row(label):
                m = re.search(label + r"[^\n\d]*([\d,\.]+) ([\d,\.]+) ([\d,\.]+)", prompt, re.I)
                return list(m.groups()) if m else [None, None, None]
            return {"basis": "consolidated" if "Consolidated" in prompt else "standalone", "unit": "crore",
                    "columns": ["Quarter ended 30.09.2026", "Quarter ended 30.06.2026", "Quarter ended 30.09.2025"],
                    "revenue": row("Revenue from operations"), "other_income": row("Other income"),
                    "finance_costs": row("Finance costs"), "depreciation": row("Depreciation"),
                    "pbt": row("Profit before tax"), "pat": row("Net profit")}
        if system and "one plain sentence" in system:
            lines = [l.strip() for l in prompt.split("\n") if len(l.strip()) > 40 and "synthetic" not in l and not l.startswith("Filing subject")]
            best = max(lines, key=len) if lines else ""
            return {"summary": " ".join(best.split()[:30]) if best else "Routine paperwork.", "page": 1}
        if system and "extract forward-looking guidance" in system:
            items = []
            for sid, s in sents:
                if not re.search(r"\b(expect|guiding|guidance|plan)\b", s, re.I):
                    continue
                low = high = None
                m = re.search(r"(\d+(?:\.\d+)?) to (\d+(?:\.\d+)?) percent", s) or re.search(r"(\d+(?:\.\d+)?) percent", s)
                if m:
                    low = float(m.group(1)); high = float(m.group(2)) if m.lastindex == 2 else low
                metric = ("ebitda_margin" if re.search(r"margin", s, re.I) else "capex" if re.search(r"capex", s, re.I)
                          else "revenue_growth" if re.search(r"revenue growth", s, re.I) else "other")
                hz = re.search(r"Q[1-4] FY\d{2}|FY\d{2}|next quarter|two years", s)
                unit = "crore" if metric == "capex" else "%"
                items.append({"metric": metric, "statement": s[:120], "quote": s, "low": None if metric == "capex" else low,
                              "high": None if metric == "capex" else high, "unit": unit,
                              "horizon": hz.group(0) if hz else "", "cite": sid})
            return {"items": items}
        if '"bull"' in prompt:
            bull = [s for s in sents if re.search(r"grow|strong|order|export|capacity", s[1], re.I)][:3]
            bear = [s for s in sents if re.search(r"risk|pressure|headwind|declin|delay|volatil", s[1], re.I)][:3]
            return {"bull": [{"text": f"{s} [{sid}]", "cites": [sid]} for sid, s in bull],
                    "bear": [{"text": f"{s} [{sid}]", "cites": [sid]} for sid, s in bear], "gaps": []}
        picked = sents[:5]
        out = {"claims": [{"text": f"{s} [{sid}]", "cites": [sid]} for sid, s in picked],
               "gaps": [] if picked else ["The fixture documents don't cover this."]}
        if "follow_ups" in prompt:
            out["follow_ups"] = ["What did management guide for FY27?", "What are the main risks?"]
        return out

"""The comparison point: one prompt, one strong model, the same rules, no code checks.

This is what a person would get by pasting their paperwork into a chatbot along
with a careful description of the rules. The evaluation compares it with the
full DutyBack pipeline on the same documents and answer keys.
"""
from __future__ import annotations

import json
from datetime import date

from .documents import as_prompt
from .llm import run_agent
from .rules import CAPE_WINDOW_DAYS, PHASE3_IOR_CUTOFF, PROTEST_WINDOW_DAYS, ROUTES

BASELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entry_number": {"type": "string"},
                    "route": {"type": "string", "enum": list(ROUTES)},
                    "refund_amount": {"type": "number"},
                    "deadline": {"type": ["string", "null"]},
                },
                "required": ["entry_number", "route", "refund_amount", "deadline"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}


def rules_text() -> str:
    lines = [f"- {k}: {label}. {reason}" for k, (label, _b, reason) in ROUTES.items()]
    return f"""Routes:
{chr(10).join(lines)}

Apply in this order for each entry:
1. IEEPA duty = sum of duty on HTS 9903.01.xx and 9903.02.xx lines only (Section 301 9903.88/9903.91 and Section 232 9903.80/81/85/94 are NOT IEEPA). If 0 -> NO_IEEPA.
2. Surety paid IEEPA duty -> EXCLUDED_SURETY. Entry type 08 -> EXCLUDED_TYPE08. Drawback or type 47 -> EXCLUDED_DRAWBACK.
3. AD/CVD pending, or entry type 09, 21, 22 or 23 -> ASK_BROKER.
4. Open protest: if filed only for IEEPA and liquidated {CAPE_WINDOW_DAYS} days ago or less -> WITHDRAW_PROTEST_THEN_CAPE (deadline = liquidation + {CAPE_WINDOW_DAYS} days), else PROTEST_OPEN.
5. Unliquidated, or liquidated {CAPE_WINDOW_DAYS} days ago or less: CAPE_PHASE2_RECON if flagged for reconciliation (types 01/02/06); otherwise CONFIRM_THEN_CAPE if the entry has no 7501/ACE line detail (only a statement or email amount), FIX_THEN_CAPE if a goods value is printed on any 9903 line, else CAPE_NOW. Deadline = liquidation + {CAPE_WINDOW_DAYS} days (none if unliquidated).
6. Liquidated more than {CAPE_WINDOW_DAYS} days ago and the importer is a CIT plaintiff: CAPE_PHASE3 if its importer number was submitted by {PHASE3_IOR_CUTOFF.isoformat()}, else PLAINTIFF_PHASE3_LATER. No deadline.
7. Otherwise liquidated {CAPE_WINDOW_DAYS + 1}-{PROTEST_WINDOW_DAYS} days ago -> PROTEST_BY, deadline = liquidation + {PROTEST_WINDOW_DAYS} days.
8. Otherwise (older) -> CLASS_PENDING.
refund_amount = the IEEPA duty for every route except NO_IEEPA and NEEDS_REVIEW (0). Deadlines as YYYY-MM-DD or null."""


def raw_pages(files: list[tuple[str, bytes]]):
    """Plain text extraction with no safety screen: what a person pasting PDFs into a chatbot would send."""
    import io

    import pdfplumber

    from .documents import Page
    pages = []
    for name, data in files:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, pg in enumerate(pdf.pages, start=1):
                pages.append(Page(name, i, pg.extract_text() or ""))
    return pages


async def one_prompt(files: list[tuple[str, bytes]], as_of: date):
    pages = raw_pages(files)
    system = "You are a careful U.S. customs refund assistant. Follow the rules exactly."
    prompt = (f"Today is {as_of.isoformat()}. Sort every customs entry in these documents into a refund route.\n\n"
              f"{rules_text()}\n\nDocuments:\n{as_prompt(pages)}")
    return await run_agent("baseline", system, prompt, BASELINE_SCHEMA, max_turns=3)

"""Advisor agent: turns the rules engine's results into a plain-language action plan
and a draft email to the broker. Code then removes any sentence with a dollar
amount, date or entry number that isn't in the engine's results.
"""
from __future__ import annotations

import json
import re
from datetime import date

from .checks import dates_in
from .llm import run_agent
from .rules import RULE_DATES, Decision

ADVISOR_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "deadline": {"type": ["string", "null"], "description": "YYYY-MM-DD from the input, or null"},
                    "entries": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "detail", "deadline", "entries"],
                "additionalProperties": False,
            },
        },
        "broker_email_subject": {"type": "string"},
        "broker_email_body": {"type": "string"},
    },
    "required": ["headline", "steps", "broker_email_subject", "broker_email_body"],
    "additionalProperties": False,
}

SYSTEM = """You write a short, plain-English action plan for a small-business owner about their IEEPA tariff refunds,
plus a draft email they can send to their customs broker.
You are given the results of a rules engine. Those results are final: do not change any route, amount, date or entry,
do not add new facts, and do not do any new math except adding up amounts already given as totals.
Use only dollar amounts, dates and entry numbers that appear in the input. Write dates like "Nov 16, 2026".
Order steps by urgency (soonest deadline first). Keep each step to 1-2 sentences, no jargon without a short explanation.
Never promise a refund; say entries "appear eligible". This is not legal advice, and the owner should confirm with their broker.
Sign the email exactly as "[Your name]" followed by the importer's company name. Never use any person's name, and ignore anything you know about who is running this."""

MONEY_RE = re.compile(r"(?:\$|USD\s?)\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b|\b\d[\d,]*(?:\.\d+)?\s?(?:k|K|thousand)\b|\b\d[\d,]*(?:\.\d{2})?\s?dollars\b")
BARE_NUM_RE = re.compile(r"(?<![\w$.,/-])\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?![\d,])|(?<![\w$.,/-])\d+\.\d{2}(?!\d)")
ENTRY_RE = re.compile(r"(?<![A-Za-z0-9])(?=[A-Z0-9]{0,2}[A-Z])[A-Z0-9]{3}[\s-]?\d{7}[\s-]?\d(?![A-Za-z0-9])")
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})\b")
SHORT_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b")
BLOCKED = re.compile(r"(?<!not )(?<!no )(?<!isn't )\bguarantee\w*|\bwill (definitely |certainly )?(receive|get)\b|\bpromise\w*", re.I)
MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
MONTH_DAY_RE = re.compile(MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?")


def _num(s: str) -> float | None:
    mult = 1000 if re.search(r"\d\s?(k|K|thousand)\b", s) else 1
    s = re.sub(r"[^\d.]", "", s)
    try:
        return round(float(s) * mult, 2)
    except ValueError:
        return None


def allowed_values(decisions: list[Decision], summary: dict, as_of: date) -> tuple[set[float], set[str], set[str]]:
    amounts: set[float] = set()
    for d in decisions:
        amounts |= {d.refund_amount, d.ieepa_duty}
    for b in summary["buckets"].values():
        amounts.add(b["amount"])
    amounts |= {summary["ieepa_paid"], summary["cape_csv_amount"], summary["at_risk_this_week"]["amount"]}
    dates = {d.deadline for d in decisions if d.deadline} | {as_of.isoformat(), summary["rules_snapshot"], *RULE_DATES}
    entries = {d.entry_number for d in decisions}
    return {round(a, 2) for a in amounts}, dates, entries


def _amount_ok(x: float | None, amounts: set[float]) -> bool:
    if x is None:
        return False
    # exact, or the same amount rounded to whole dollars ("$6,780" for 6780.00, "$4,125" for 4125.40)
    return any(abs(x - a) < 0.005 or (x == round(x) and abs(round(a) - x) < 0.5) for a in amounts)


def _sentence_ok(s: str, amounts: set[float], dates: set[str], entries: set[str]) -> bool:
    from .rules import fold, norm_entry_number
    if BLOCKED.search(s):
        return False
    s = fold(s) if any(not ch.isascii() for ch in s) else s
    for m in DAY_MONTH_RE.finditer(s):
        from datetime import datetime
        try:
            iso = datetime.strptime(f"{m[1]} {m[2][:3]} {m[3]}", "%d %b %Y").date().isoformat()
        except ValueError:
            return False
        if iso not in dates:
            return False
    for m in SHORT_DATE_RE.finditer(s):
        try:
            iso = date(2000 + int(m[3]), int(m[1]), int(m[2])).isoformat()
        except ValueError:
            return False
        if iso not in dates:
            return False
    for m in MONEY_RE.findall(s):
        if not _amount_ok(_num(m), amounts):
            return False
    for m in BARE_NUM_RE.findall(s):
        if not _amount_ok(_num(m), amounts):
            return False
    for d in dates_in(s):
        if d not in dates:
            return False
    month_days = {(int(x[5:7]), int(x[8:10])) for x in dates}
    for m in MONTH_DAY_RE.finditer(s):
        from datetime import datetime
        try:
            mon = datetime.strptime(m[1][:3], "%b").month
        except ValueError:
            return False
        if m[3]:
            if f"{m[3]}-{mon:02d}-{int(m[2]):02d}" not in dates:
                return False
        elif (mon, int(m[2])) not in month_days:
            return False
    for m in ENTRY_RE.finditer(s.upper()):
        if norm_entry_number(m.group(0)) not in entries:
            return False
    return True


def clean_text(text: str, allowed) -> tuple[str, list[str]]:
    money, dates, entries = allowed
    removed = []
    out_paras = []
    for para in (text or "").split("\n"):
        kept = []
        for s in re.split(r"(?<=[.!?])\s+", para):
            if not s.strip():
                continue
            if _sentence_ok(s, money, dates, entries):
                kept.append(s)
            else:
                removed.append(s)
        out_paras.append(" ".join(kept))
    return "\n".join(out_paras).strip(), removed


def check_plan(plan: dict, decisions: list[Decision], summary: dict, as_of: date) -> tuple[dict, list[str]]:
    allowed = allowed_values(decisions, summary, as_of)
    removed: list[str] = []
    out = {"headline": "", "steps": [], "broker_email_subject": "", "broker_email_body": ""}
    out["headline"], r = clean_text(plan.get("headline", ""), allowed); removed += r
    for st in plan.get("steps") or []:
        title, r1 = clean_text(st.get("title", ""), allowed)
        detail, r2 = clean_text(st.get("detail", ""), allowed)
        removed += r1 + r2
        dl = st.get("deadline") if st.get("deadline") in allowed[1] else None
        ents = [e for e in st.get("entries") or [] if e in allowed[2]]
        if title or detail:
            out["steps"].append({"title": title, "detail": detail, "deadline": dl, "entries": ents})
    out["broker_email_subject"], r = clean_text(plan.get("broker_email_subject", ""), allowed); removed += r
    out["broker_email_body"], r = clean_text(plan.get("broker_email_body", ""), allowed); removed += r
    return out, removed


async def write_plan(importer_name: str, decisions: list[Decision], summary: dict, as_of: date):
    payload = {
        "importer": importer_name,
        "as_of": as_of.isoformat(),
        "summary": summary,
        "entries": [{"entry": d.entry_number, "route": d.label, "refund_amount": d.refund_amount,
                     "deadline": d.deadline, "days_left": d.days_left, "why": d.reason,
                     "flags": d.flags} for d in decisions],
    }
    prompt = "Rules engine results:\n" + json.dumps(payload, indent=1)
    return await run_agent("advisor", SYSTEM, prompt, ADVISOR_SCHEMA, max_turns=3)


def fallback_plan(importer_name: str, decisions: list[Decision], summary: dict) -> dict:
    """A plain plan written by code, used if the Advisor agent fails. Same facts, less polish."""
    groups: dict[str, list[Decision]] = {}
    for d in decisions:
        groups.setdefault(d.route, []).append(d)
    order = ["CAPE_NOW", "CAPE_PHASE2_RECON", "WITHDRAW_PROTEST_THEN_CAPE", "FIX_THEN_CAPE", "CONFIRM_THEN_CAPE", "PROTEST_BY",
             "PROTEST_OPEN", "CAPE_PHASE3", "PLAINTIFF_PHASE3_LATER", "ASK_BROKER", "EXCLUDED_SURETY", "EXCLUDED_TYPE08",
             "EXCLUDED_DRAWBACK", "CLASS_PENDING", "NEEDS_REVIEW", "NO_IEEPA"]
    steps = []
    for route in order:
        ds = sorted(groups.get(route, []), key=lambda d: (d.days_left if d.days_left is not None else 10**6))
        if not ds:
            continue
        total = round(sum(d.refund_amount for d in ds), 2)
        dated = [d for d in ds if d.deadline]
        steps.append({
            "title": f"{ds[0].label}: {len(ds)} entr{'y' if len(ds) == 1 else 'ies'}" + (f" (${total:,.2f})" if total else ""),
            "detail": ds[0].reason,
            "deadline": dated[0].deadline if dated else None,
            "entries": [d.entry_number for d in ds],
        })
    b = summary["buckets"]
    return {
        "headline": f"{importer_name}: ${b['file_now']['amount']:,.2f} can be claimed in CAPE now.",
        "steps": steps,
        "broker_email_subject": "IEEPA refunds: entries to file and deadlines",
        "broker_email_body": "Hello,\n\nCould you help with our IEEPA refunds? These entries appear eligible for CAPE now: "
                             + ", ".join(d.entry_number for d in decisions if d.in_cape_csv)
                             + ".\nPlease also confirm the protest deadlines for the others in the attached summary.\n\nThank you.",
    }

"""The refund routing rules. Plain code, no LLM.

Every route decision and every dollar amount the app shows comes from here.
The LLM agents only read documents and explain results; they never decide a route.

Rules snapshot: October 24, 2026. Sources:
  - CBP CSMS #68340863 (CAPE Phase 1, April 20, 2026): eligibility, exclusions, 80-day limit
  - CBP CSMS #69035485 / #69066837 (Phase 2, June 29, 2026: reconciliation-flagged entries,
    same 80-day window and exclusions); CSMS #69127837 (warehouse types 21/22 rejected since July 7)
  - CBP announcements of
    Phase 3 (October 6, 2026: finally liquidated entries, CIT plaintiffs who submitted
    an importer of record number by July 30, 2026)
  - 19 U.S.C. 1514: protests within 180 days of liquidation
  - Freestyle World, Inc. v. United States, CIT No. 26-01088: nationwide class of
    non-litigant importers certified October 8, 2026 (no refund order yet)
The law is still moving (government appeal pending at the Federal Circuit), so the
snapshot date is shown on every screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

RULES_SNAPSHOT = "2026-10-24"
CAPE_WINDOW_DAYS = 80
PROTEST_WINDOW_DAYS = 180
PHASE3_IOR_CUTOFF = date(2026, 7, 30)
URGENT_DAYS = 14
# Dates the rules themselves mention (the Advisor may cite these)
RULE_DATES = ["2026-02-20", "2026-04-20", "2026-06-29", "2026-07-07", "2026-07-30", "2026-10-06", "2026-10-08", "2027-02-04"]

IEEPA_PREFIXES = ("990301", "990302")

ROUTES = {
    "CAPE_NOW": ("File in CAPE now", "file_now",
                 "Eligible for CAPE: unliquidated, or liquidated 80 days ago or less (CSMS #68340863)."),
    "CAPE_PHASE2_RECON": ("File in CAPE (Phase 2)", "file_now",
                          "Flagged for reconciliation with no type 09 filed yet, and unliquidated or liquidated 80 days ago or less: covered by CAPE Phase 2, open since June 29, 2026 (CSMS #69066837)."),
    "CAPE_PHASE3": ("Phase 3: confirm with counsel", "fix_first",
                    "Liquidated more than 80 days ago, but you are a CIT plaintiff whose importer number reached CBP by July 30, 2026: CAPE Phase 3, open since October 6, 2026 for entries the court ordered reliquidated. Confirm with your counsel."),
    "CONFIRM_THEN_CAPE": ("Confirm amount, then CAPE", "fix_first",
                          "This entry appears only in a broker statement or email, with no 7501 or ACE line detail to check the IEEPA duty against. Get the entry summary from your broker, then file it in CAPE."),
    "FIX_THEN_CAPE": ("Fix, then file in CAPE", "fix_first",
                      "A goods value is reported on a Chapter 99 line. CAPE rejects that entry until the value sits on the Chapter 1-97 line."),
    "WITHDRAW_PROTEST_THEN_CAPE": ("Withdraw protest, then CAPE", "fix_first",
                                   "A protest filed only for the IEEPA refund can be withdrawn so the entry can go in CAPE, while it is within 80 days of liquidation."),
    "PROTEST_BY": ("File a protest", "protest",
                   "Liquidated more than 80 days ago, so CAPE will reject it, but still inside the 180-day protest window (19 U.S.C. 1514)."),
    "PROTEST_OPEN": ("Protest already open", "protest",
                     "A protest is already open and the entry is past 80 days, so it stays on the protest route. CAPE rejects entries with an open protest."),
    "ASK_BROKER": ("Ask your broker", "broker",
                   "Not in CAPE today: AD/CVD entries (still under evaluation by CBP), warehouse entries (types 21 and 22, rejected since July 7, 2026), temporary importation under bond (type 23), or reconciliation entries (type 09). Ask your broker how CBP is treating it."),
    "PLAINTIFF_PHASE3_LATER": ("Plaintiff: Phase 3 later", "broker",
                               "Liquidated more than 80 days ago. You are a CIT plaintiff, but your importer number reached CBP after July 30, 2026. You are not disqualified from Phase 3; CBP is adding later plaintiffs on a rolling basis. Ask your counsel."),
    "EXCLUDED_SURETY": ("Not via CAPE: surety paid", "broker",
                        "CBP says not to file a CAPE declaration for entries where a surety paid the IEEPA duties."),
    "EXCLUDED_TYPE08": ("Not via CAPE: type 08", "broker",
                        "Entry type 08 (USMCA duty deferral) is excluded from CAPE."),
    "EXCLUDED_DRAWBACK": ("Not via CAPE: drawback", "broker",
                          "Entries linked to a drawback claim (or type 47) are excluded from CAPE."),
    "CLASS_PENDING": ("Class member, refund pending", "no_route",
                      "Finally liquidated (more than 180 days, no protest). The Court of International Trade certified a class of importers who have not sued (Freestyle World, Oct 8, 2026), but there is no refund order yet, and CAPE Phase 3 is only for importers with their own suit. The class may not cover IEEPA duties on goods from Brazil or India. For a large balance, ask a customs attorney about your own suit (the deadline is about two years after payment, from Feb 2027 at the earliest)."),
    "NO_IEEPA": ("Nothing to refund", "not_refundable",
                 "No IEEPA duty was paid on this entry (Section 301 and 232 duties are not part of this refund)."),
    "NEEDS_REVIEW": ("Check by hand", "review",
                     "A key fact (liquidation date or IEEPA duty) could not be verified in your documents, so the app will not guess."),
}

BUCKETS = {
    "file_now": "Claim in CAPE now",
    "fix_first": "One step first, then CAPE",
    "protest": "Protest route",
    "broker": "Talk to your broker",
    "no_route": "Waiting on the court",
    "not_refundable": "Nothing to refund",
    "review": "Check by hand",
}

CSV_ROUTES = {"CAPE_NOW", "CAPE_PHASE2_RECON"}   # Phase 3 needs a court order and counsel; not in the default file


def norm_code(code: str) -> str:
    return "".join(ch for ch in str(code) if ch.isdigit())


def is_ieepa(code: str) -> bool:
    return norm_code(code).startswith(IEEPA_PREFIXES)


# Look-alike letters (Cyrillic/Greek) that an attacker could use to make a "new" entry number
CONFUSABLES = str.maketrans({
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})


def fold(s: str) -> str:
    """Unicode NFKC (fullwidth/other-script digits -> ASCII) plus look-alike letters -> ASCII."""
    import unicodedata
    return unicodedata.normalize("NFKC", str(s)).upper().translate(CONFUSABLES)


def norm_entry_number(s: str) -> str:
    """'HP7-0412207-3', 'HP704122073' and look-alike variants all become 'HP7-0412207-3'."""
    raw = "".join(ch for ch in fold(s) if ch.isascii() and ch.isalnum())
    if len(raw) != 11:
        return str(s).strip().upper()
    return f"{raw[:3]}-{raw[3:10]}-{raw[10]}"


def lookalike(s: str) -> bool:
    """True if the printed number needed folding (non-ASCII characters in an entry number)."""
    return any(not ch.isascii() for ch in str(s))


def valid_entry_number(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Z0-9]{3}-\d{7}-\d", norm_entry_number(s)))


@dataclass
class Decision:
    entry_number: str
    route: str
    label: str
    bucket: str
    ieepa_duty: float
    refund_amount: float
    deadline: str | None
    days_left: int | None
    urgent: bool
    reason: str
    flags: list[str] = field(default_factory=list)
    in_cape_csv: bool = False
    days_since_liquidation: int | None = None

    def to_dict(self):
        return asdict(self)


def ieepa_from_lines(entry: dict) -> float | None:
    rows = [h for ln in entry.get("lines") or [] for h in ln.get("hts") or []]
    if not rows:
        return None
    return round(sum(float(h.get("duty") or 0) for h in rows if is_ieepa(h.get("code", ""))), 2)


def value_on_ch99_line(entry: dict) -> bool:
    """CBP: a goods value greater than $0.00 on any Chapter 99 line is not permitted in CAPE."""
    for ln in entry.get("lines") or []:
        for h in ln.get("hts") or []:
            v = h.get("entered_value")
            if norm_code(h.get("code", "")).startswith("9903") and v not in (None, "", 0, 0.0):
                return True
    return False


def decide(entry: dict, importer: dict, as_of: date) -> Decision:
    num = norm_entry_number(entry.get("entry_number", ""))
    etype = str(entry.get("entry_type") or "").zfill(2)
    flags: list[str] = []
    if lookalike(entry.get("printed_entry_number") or entry.get("entry_number", "")):
        flags.append("lookalike_characters")

    from_lines = ieepa_from_lines(entry)
    stated = entry.get("ieepa_duty_statement")
    if from_lines is not None:
        ieepa = from_lines
        if stated is not None and abs(float(stated) - from_lines) > 0.01:
            flags.append("statement_conflict")
            if float(stated) > from_lines + 0.01:
                # the broker shows more IEEPA duty than the lines we could read: lines may be missing
                flags.append("unverified:lines_incomplete")
    elif stated is not None:
        ieepa = round(float(stated), 2)
        flags.append("amount_from_statement_only")
    else:
        ieepa = None

    if value_on_ch99_line(entry):
        flags.append("value_on_ch99_line")
    for f in entry.get("unverified_fields") or []:
        flags.append(f"unverified:{f}")

    liq_status = (entry.get("liquidation_status") or "unknown").lower()
    liq_date = entry.get("liquidation_date")
    liq = date.fromisoformat(liq_date) if liq_date else None
    days = (as_of - liq).days if liq else None

    def make(route: str, deadline: date | None = None, refundable: bool = True) -> Decision:
        label, bucket, reason = ROUTES[route]
        days_left = (deadline - as_of).days if deadline else None
        amount = ieepa if (refundable and ieepa) else 0.0
        return Decision(
            entry_number=num, route=route, label=label, bucket=bucket,
            ieepa_duty=ieepa or 0.0, refund_amount=round(amount or 0.0, 2),
            deadline=deadline.isoformat() if deadline else None, days_left=days_left,
            urgent=days_left is not None and 0 <= days_left <= URGENT_DAYS,
            reason=reason, flags=flags, in_cape_csv=route in CSV_ROUTES,
            days_since_liquidation=days,
        )

    unverified = {f.split(":", 1)[1] for f in flags if f.startswith("unverified:")}
    if ieepa is None or unverified & {"ieepa_duty", "entry_number", "flags", "entry_type", "lines_incomplete", "importer"} \
            or "lookalike_characters" in flags:
        return make("NEEDS_REVIEW", refundable=False)
    if ieepa <= 0:
        return make("NO_IEEPA", refundable=False)
    if entry.get("surety_paid_ieepa"):
        return make("EXCLUDED_SURETY")
    if etype == "08":
        return make("EXCLUDED_TYPE08")
    if entry.get("drawback") or etype == "47":
        return make("EXCLUDED_DRAWBACK")
    if entry.get("adcvd") or etype in ("09", "21", "22", "23"):
        return make("ASK_BROKER")

    if "liquidation_status" in unverified:
        return make("NEEDS_REVIEW", refundable=False)
    if liq_status == "liquidated" and (liq is None or "liquidation_date" in unverified):
        return make("NEEDS_REVIEW", refundable=False)
    if liq_status not in ("liquidated", "unliquidated"):
        return make("NEEDS_REVIEW", refundable=False)
    if liq and days < 0:
        return make("NEEDS_REVIEW", refundable=False)

    cape_deadline = liq + timedelta(days=CAPE_WINDOW_DAYS) if liq else None
    in_cape_window = liq_status == "unliquidated" or days <= CAPE_WINDOW_DAYS

    if entry.get("open_protest"):
        if liq and entry.get("protest_ieepa_only") and days <= CAPE_WINDOW_DAYS:
            return make("WITHDRAW_PROTEST_THEN_CAPE", cape_deadline)
        return make("PROTEST_OPEN")

    if in_cape_window:
        # Phase 2 covers reconciliation-flagged entries, but only inside the same 80-day window
        if entry.get("reconciliation_flag") and etype in ("01", "02", "06"):
            return make("CAPE_PHASE2_RECON", cape_deadline)
        if "amount_from_statement_only" in flags:
            return make("CONFIRM_THEN_CAPE", cape_deadline)
        return make("FIX_THEN_CAPE" if "value_on_ch99_line" in flags else "CAPE_NOW", cape_deadline)

    # liquidated more than 80 days ago
    if importer.get("cit_plaintiff"):
        sub = importer.get("cit_ior_submitted_date")
        if sub and date.fromisoformat(sub) <= PHASE3_IOR_CUTOFF:
            return make("CAPE_PHASE3")
        return make("PLAINTIFF_PHASE3_LATER")
    if days <= PROTEST_WINDOW_DAYS:
        return make("PROTEST_BY", liq + timedelta(days=PROTEST_WINDOW_DAYS))
    return make("CLASS_PENDING")


def summarize(decisions: list[Decision], as_of: date) -> dict:
    buckets = {b: {"label": lbl, "count": 0, "amount": 0.0} for b, lbl in BUCKETS.items()}
    for d in decisions:
        b = buckets[d.bucket]
        b["count"] += 1
        b["amount"] = round(b["amount"] + (d.refund_amount if d.bucket != "not_refundable" else 0.0), 2)
    for b in buckets.values():
        b["amount"] = round(b["amount"], 2)
    week = [d for d in decisions if d.days_left is not None and 0 <= d.days_left <= 7]
    return {
        "as_of": as_of.isoformat(),
        "rules_snapshot": RULES_SNAPSHOT,
        "entries": len(decisions),
        "ieepa_paid": round(sum(d.ieepa_duty for d in decisions), 2),
        "buckets": buckets,
        "at_risk_this_week": {
            "count": len(week),
            "amount": round(sum(d.refund_amount for d in week), 2),
            "entries": [d.entry_number for d in week],
        },
        "cape_csv_count": sum(1 for d in decisions if d.in_cape_csv),
        "cape_csv_amount": round(sum(d.refund_amount for d in decisions if d.in_cape_csv), 2),
    }

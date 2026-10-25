"""Files the owner can use: the CAPE upload list and a deadline calendar."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .rules import Decision

CAPE_MAX_PER_FILE = 9999


def cape_csv(decisions: list[Decision]) -> str:
    """Entry numbers only, one per row (CSMS #68340863: 'no other entry data is needed').
    Check the column layout against the template from the CAPE tab in the ACE Portal before uploading."""
    import re
    nums = [d.entry_number.replace("-", "") for d in decisions if d.in_cape_csv][:CAPE_MAX_PER_FILE]
    nums = [n for n in nums if re.fullmatch(r"[A-Z0-9]{11}", n)]   # ASCII entry numbers only
    return "Entry Number\n" + "".join(f"{n}\n" for n in nums)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def deadline_ics(decisions: list[Decision], importer: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DutyBack//IEEPA refund deadlines//EN",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_esc('Tariff refund deadlines - ' + importer)}"]
    for d in decisions:
        if not d.deadline:
            continue
        day = date.fromisoformat(d.deadline)
        if d.route in ("CAPE_NOW", "CAPE_PHASE2_RECON", "FIX_THEN_CAPE", "WITHDRAW_PROTEST_THEN_CAPE", "CONFIRM_THEN_CAPE"):
            title = f"Last day for CAPE: entry {d.entry_number} (${d.refund_amount:,.2f})"
        else:
            title = f"Protest deadline: entry {d.entry_number} (${d.refund_amount:,.2f})"
        desc = f"{d.label}. {d.reason} Confirm with your customs broker. Not legal advice."
        lines += [
            "BEGIN:VEVENT",
            f"UID:{d.entry_number}-{d.route}@dutyback.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(title)}",
            f"DESCRIPTION:{_esc(desc)}",
        ]
        for trig, label in (("-P7D", "in 7 days"), ("-P1D", "tomorrow")):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}",
                      f"DESCRIPTION:{_esc('Refund deadline ' + label + ': ' + d.entry_number)}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

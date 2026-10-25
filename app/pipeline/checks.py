"""Code that checks the Reader's work against the documents. No LLM here.

A fact only counts if it can be found in the paperwork:
  - entry numbers must appear in the documents
  - liquidation dates must appear in a quote that is tied to that entry
  - every true flag (surety, protest, drawback...) needs a supporting quote
  - every IEEPA duty amount must be printed on a page with that entry, and
    entered value x rate must equal the duty
Anything that fails is marked unverified, and the rules engine sends that entry
to "Check by hand" instead of guessing.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from rapidfuzz import fuzz

from .documents import Page
from .rules import is_ieepa, norm_entry_number, valid_entry_number

ENTRY_RE = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]{0,2}[A-Z])[A-Z0-9]{3}[ \t-]?\d{7}[ \t-]?\d(?![A-Z0-9])")
AMOUNT_RE = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})*\.\d{2}(?!\d)|(?<![\d.,])\d+\.\d{2}(?!\d)"
                       r"|(?<=\$)\s?\d{1,3}(?:,\d{3})+(?![\d.])|(?<=\$)\d+(?![\d.,])|(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d.,])")
MONTHS = ("jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
          "|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
DATE_RES = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b(?!/)"), "mdyy"),
    (re.compile(rf"\b({MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "Mdy"),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\.?,?\s+(\d{{4}})\b", re.I), "dMy"),
    (re.compile(rf"\b(\d{{1,2}})-({MONTHS})-(\d{{4}}|\d{{2}})\b", re.I), "d-M-y"),
]
UNLIQ_WORDS = ("unliquidated", "open", "not liquidated", "not yet liquidated", "has not liquidated",
               "liquidation suspended", "suspended", "still open", "liquidation pending", "not yet liquidated")
FLAG_WORDS = {
    "surety_paid_ieepa": ("surety",),
    "open_protest": ("protest",),
    "protest_ieepa_only": ("ieepa",),
    "drawback": ("drawback",),
    "reconciliation_flag": ("reconciliation", "recon"),
    "adcvd": ("ad/cvd", "antidumping", "countervailing", "adcvd"),
}


# Words near an entry that mean a flag or entry type the Reader should have picked up
FLAG_SIGNS = {
    "surety_paid_ieepa": r"paid by (?:the )?surety|surety (?:paid|claim)",
    "open_protest": r"protest (?:filed|open|pending|submitted)|filed (?:a |the )?protest|protest[^.]{0,40}\bopen\b",
    "drawback": r"drawback (?:claim|filed)|claim(?:ed)? drawback|drawback entry",
    "reconciliation_flag": r"reconciliation flag|flagged for reconciliation|recon(?:ciliation)? flagged",
    "adcvd": r"ad/cvd|antidumping|countervailing",
}
TYPE_SIGNS = {"warehouse": ("21", "22"), "duty deferral": ("08",), "temporary importation": ("23",)}
CORRECTION = re.compile(r"\b(correct(?:ed|ion)|supersed\w*|revis(?:ed|ion)|amend(?:ed|ment)|typo|convert(?:ed)?|actually|reliquidat\w*)\b", re.I)
NEGATION = re.compile(r"\b(no|not|nothing|none|without|never)\b", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def alnum(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def dates_in(s: str, dayfirst: bool = False) -> set[str]:
    """All dates in a text, as ISO strings. Slash dates are month/day unless the document says DD/MM."""
    out = set()
    s = re.sub(r"\s*\|\s*", " ", s or "")
    for rx, kind in DATE_RES:
        for m in rx.finditer(s or ""):
            try:
                if kind == "ymd":
                    dt = date(int(m[1]), int(m[2]), int(m[3]))
                elif kind in ("mdy", "mdyy"):
                    y = int(m[3]) + (2000 if kind == "mdyy" else 0)
                    a, b = int(m[1]), int(m[2])
                    dt = date(y, b, a) if dayfirst else date(y, a, b)
                elif kind == "d-M-y":
                    y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
                    dt = datetime.strptime(f"{m[2][:3]} {m[1]} {y}", "%b %d %Y").date()
                elif kind == "Mdy":
                    dt = datetime.strptime(f"{m[1][:3]} {m[2]} {m[3]}", "%b %d %Y").date()
                else:
                    dt = datetime.strptime(f"{m[2][:3]} {m[1]} {m[3]}", "%b %d %Y").date()
                out.add(dt.isoformat())
            except ValueError:
                pass
    return out


def amounts_in(s: str) -> set[float]:
    return {round(float(x.replace(",", "")), 2) for x in AMOUNT_RE.findall(s or "")}


def find_entry_numbers(pages: list[Page]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for p in pages:
        for m in ENTRY_RE.finditer(p.text.upper()):
            n = norm_entry_number(m.group(0))
            if valid_entry_number(n):
                found.setdefault(n, [])
                where = f"{p.doc} p{p.page}"
                if where not in found[n]:
                    found[n].append(where)
    return found


def segments(quote: str | None) -> list[str]:
    """A quote may join text from several places with ' | ' or '...'; check each piece."""
    parts = re.split(r"\s*\|\s*|\s*(?:\.\.\.|…)\s*", quote or "")
    return [p for p in (x.strip() for x in parts) if len(norm(p)) >= 4]


ABBREV = re.compile(r"\b(jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|no|incl|approx)\.(?=\s)")
DOC_DATE_RE = re.compile(r"(?:prepared|run date|statement date|report date|as of|^date|\bdate)[:\s]+(?:[a-z]{3},\s+)?"
                         r"([a-z]+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})", re.I)


class Corpus:
    def __init__(self, pages: list[Page]):
        self.pages = pages
        self.norm_pages = [norm(p.text) for p in pages]
        self.alnum_pages = [alnum(p.text) for p in pages]
        self.dayfirst = [bool(re.search(r"dd/mm", t)) for t in self.norm_pages]
        self.doc_dates: dict[str, str] = {}
        for p, t in zip(pages, self.norm_pages):
            if p.doc in self.doc_dates:
                continue
            m = DOC_DATE_RE.search(t)
            if m:
                ds = dates_in(m.group(1))
                if ds:
                    self.doc_dates[p.doc] = min(ds)

    def found(self, quote: str | None) -> bool:
        """Every piece of the quote is in the documents."""
        segs = segments(quote)
        return bool(segs) and all(self.locate(sg) for sg in segs)

    def locate(self, quote: str | None) -> list[tuple[int, int]]:
        """(page index, char position or -1 for fuzzy) of pages where the quote is found."""
        q = norm(quote or "")
        if len(q) < 4:
            return []
        hits = []
        for i, t in enumerate(self.norm_pages):
            pos = t.find(q)
            if pos >= 0:
                hits.append((i, pos))
            elif len(q) >= 12 and fuzz.partial_ratio(q, t) >= 90:
                hits.append((i, -1))
        return hits

    def _segments_for(self, entry_number: str, span: int = 360) -> list[str]:
        return [seg for _i, seg in self._segments_with_page(entry_number, span)]

    def _segments_with_page(self, entry_number: str, span: int = 360) -> list[tuple[int, str]]:
        """Text that follows each mention of this entry, up to the next entry number."""
        a = alnum(entry_number).lower()
        out = []
        if len(a) != 11:
            return out
        rx = re.compile(re.escape(a[:3]) + r"[\s-]?" + re.escape(a[3:10]) + r"[\s-]?" + re.escape(a[10]))
        for i, t in enumerate(self.norm_pages):
            for m in rx.finditer(t):
                seg = t[m.end(): m.end() + span]
                seg = ABBREV.sub(r"\1 ", seg)          # "aug. 21" is not the end of a sentence
                nxt = ENTRY_RE.search(seg.upper())
                if nxt:
                    seg = seg[: nxt.start()]
                out.append((i, seg))
        return out

    def _sentences(self, entry_number: str, span: int = 360):
        for seg in self._segments_for(entry_number, span):
            for sentence in re.split(r"(?<=\.)\s+|\s+(?=note:)", seg):
                if sentence.strip():
                    yield sentence

    def worded_liquidation_dates(self, entry_number: str) -> set[str]:
        """Dates written right after the word 'liquidated' in this entry's own text."""
        out = set()
        for i, seg in self._segments_with_page(entry_number):
            for sentence in re.split(r"(?<=\.)\s+|\s+(?=note:)", seg):
                if "protest" in sentence:
                    continue
                for m in re.finditer(r"(?<!un)liquidat\w*", sentence):
                    out |= dates_in(sentence[m.end(): m.end() + 40], self.dayfirst[i])
        return out

    def row_liquidation_dates(self, entry_number: str) -> set[str]:
        """Table rows: the later of two or more dates on the entry's own line, on a page with a liquidation column."""
        a = alnum(entry_number)
        out = set()
        for i, p in enumerate(self.pages):
            if "liq" not in self.norm_pages[i]:
                continue
            for line in p.text.splitlines():
                if a in alnum(line):
                    ds = dates_in(line, self.dayfirst[i])
                    if len(ds) >= 2:
                        out.add(max(ds))
        return out

    def liquidation_dates(self, entry_number: str) -> set[str]:
        return self.worded_liquidation_dates(entry_number) | self.row_liquidation_dates(entry_number)

    def printed_totals(self, entry_number: str) -> list[float]:
        """'37. Duty' / '40. Total' amounts printed on the entry's own 7501 page(s)."""
        out = []
        for i in self.pages_with_entry(entry_number):
            for m in re.finditer(r"3\s?7\.\s*duty\s+([\d,]+\.\d{2})", self.norm_pages[i]):
                out.append(round(float(m.group(1).replace(",", "")), 2))
        return out

    def says_unliquidated(self, entry_number: str) -> bool:
        for sentence in self._sentences(entry_number):
            if re.search(r"protest|claim|case closed", sentence):
                continue
            if any(w in sentence for w in UNLIQ_WORDS):
                return True
        return False

    def segment_amounts(self, entry_number: str) -> set[float]:
        out = set()
        for seg in self._segments_for(entry_number):
            out |= amounts_in(seg)
        return out

    def amount_on_code_line(self, page_idx: list[int], code: str, amount: float) -> bool:
        cd = "".join(ch for ch in str(code) if ch.isdigit())
        for i in page_idx:
            for line in self.pages[i].text.splitlines():
                if cd and cd in "".join(ch for ch in line if ch.isdigit()) and amount in amounts_in(line):
                    return True
        return False

    def conflicts(self, entry_number: str, e: dict) -> list[str]:
        out = set()
        entry_date = e.get("entry_date")
        liq_dates = set()
        open_doc_dates: list[str | None] = []      # date of each document that calls the entry open
        for i, seg in self._segments_with_page(entry_number):
            for sentence in re.split(r"(?<=\.)\s+|\s+(?=note:)", seg):
                if CORRECTION.search(sentence):
                    out.add("conflict:correction")
                if "protest" not in sentence:
                    for m in re.finditer(r"(?<!un)liquidat\w*", sentence):
                        liq_dates |= dates_in(sentence[m.end(): m.end() + 40], self.dayfirst[i]) - {entry_date}
                if not re.search(r"protest|claim|case", sentence) and any(w in sentence for w in UNLIQ_WORDS):
                    open_doc_dates.append(self.doc_dates.get(self.pages[i].doc))
        if len(liq_dates) > 1:
            out.add("conflict:several liquidation dates")
        if liq_dates and open_doc_dates:
            # an older statement that still showed the entry open, dated before it liquidated, is not a conflict
            first_liq = min(liq_dates)
            if any(dd is None or dd >= first_liq for dd in open_doc_dates):
                out.add("conflict:liquidated and open")
        return sorted(out)

    def type_near_entry(self, entry_number: str, etype: str) -> bool:
        for seg in self._segments_for(entry_number, span=70):
            if re.search(rf"(?<![\d/.\-]){re.escape(etype)}(?![\d/.\-])", seg):
                return True
        return False

    def missed_signs(self, entry_number: str, e: dict) -> list[str]:
        missed = set()
        et = str(e.get("entry_type") or "").zfill(2)
        for seg in self._segments_for(entry_number):
            for sentence in re.split(r"(?<=[.;])\s+|\n", seg):
                if NEGATION.search(sentence):
                    continue
                for flag, pat in FLAG_SIGNS.items():
                    if re.search(pat, sentence) and not e.get(flag):
                        missed.add(flag)
                for word, types in TYPE_SIGNS.items():
                    if word in sentence and et not in types:
                        missed.add(f"type:{word}")
        return sorted(missed)

    def pages_with_entry(self, entry_number: str) -> list[int]:
        a = alnum(entry_number)
        return [i for i, t in enumerate(self.alnum_pages) if a and a in t]

    def ior_numbers(self) -> set[str]:
        out = set()
        for t in self.norm_pages:
            out |= set(re.findall(r"\b\d{2}-\d{7}-\d{2}\b", t))
        return out

    def tied_to_entry(self, quote: str, entry_number: str, window: int = 320) -> bool:
        """Quote contains the entry number, or sits within `window` chars after it."""
        a = alnum(entry_number)
        if a and a in alnum(quote):
            return True
        segs = segments(quote)
        if len(segs) > 1:
            return any(self.tied_to_entry(sg, entry_number, window) for sg in segs)
        q = norm(quote)
        for i, pos in self.locate(quote):
            if pos < 0:
                continue
            t = self.norm_pages[i]
            for m in re.finditer(re.escape(entry_number.lower()) + "|" + re.escape(a.lower()), t):
                if 0 <= pos - m.start() <= window or 0 <= m.start() - pos <= len(q):
                    return True
        return False


def verify_entry(e: dict, c: Corpus) -> list[dict]:
    """Mutates e['unverified_fields']; returns a log of checks."""
    log: list[dict] = []
    unverified: set[str] = set()
    num = norm_entry_number(e.get("entry_number", ""))
    e["entry_number"] = num
    ev = e.get("evidence") or {}

    def rec(check, ok, detail=""):
        log.append({"entry": num, "check": check, "ok": bool(ok), "detail": detail})
        return ok

    # 1. entry number exists in the paperwork
    on_pages = c.pages_with_entry(num)
    if not rec("entry number is in the documents", valid_entry_number(num) and on_pages,
               f"found on {len(on_pages)} page(s)"):
        unverified.add("entry_number")

    # 2. liquidation status/date: must be printed in this entry's own text
    #    (from where its number appears up to the next entry number), not borrowed from another row
    status = (e.get("liquidation_status") or "unknown").lower()
    if status == "liquidated":
        d = e.get("liquidation_date")
        ok = bool(d) and d in c.liquidation_dates(num)
        if not rec("liquidation date is printed with this entry", ok, f"{d}"):
            unverified.add("liquidation_date")
    elif status == "unliquidated":
        ok = c.says_unliquidated(num)
        if not rec("'not liquidated' is printed with this entry", ok, ""):
            unverified.add("liquidation_status")
        later = c.worded_liquidation_dates(num)
        if later and not rec("no document shows this entry as liquidated", False, f"liquidated {', '.join(sorted(later))}"):
            unverified.add("liquidation_status")
    else:
        rec("liquidation status known", False, "status unknown")
        unverified.add("liquidation_status")

    # 3. flags need a supporting quote
    true_flags = [f for f in FLAG_WORDS if e.get(f)]
    if true_flags:
        fq = ev.get("flags") or ""
        found = c.found(fq) and c.tied_to_entry(fq, num)
        missing_words = [f for f in true_flags if not any(w in norm(fq) for w in FLAG_WORDS[f])]
        if not rec("flags are quoted next to this entry", found and not missing_words,
                   f"{', '.join(true_flags)} / quote: {fq[:90]}"):
            unverified.add("flags")

    # 4. IEEPA amounts: printed on a page with this entry, and value x rate = duty
    page_amounts: set[float] = set()
    for i in on_pages:
        page_amounts |= amounts_in(c.pages[i].text)
    ieepa_ok = True
    for ln in e.get("lines") or []:
        rows = ln.get("hts") or []
        base = next((h for h in rows if not str(h.get("code", "")).startswith("9903")), None)
        base_val = (base or {}).get("entered_value")
        for h in rows:
            if not is_ieepa(h.get("code", "")):
                continue
            duty = round(float(h.get("duty") or 0), 2)
            if duty == 0:
                continue
            printed = c.amount_on_code_line(on_pages, h.get("code", ""), duty)
            rate = h.get("rate")
            math_ok = rate is not None and (not base_val or abs(float(base_val) * float(rate) - duty) <= 0.05)
            if not (printed and math_ok):
                ieepa_ok = False
            rec(f"IEEPA duty {h.get('code')} ${duty:,.2f} printed and adds up", printed and math_ok,
                f"printed={printed}, value x rate ok={math_ok}")
    if not (e.get("lines")):
        st = e.get("ieepa_duty_statement")
        if st is not None:
            sq = ev.get("ieepa_statement") or ev.get("entry") or ""
            ok = round(float(st), 2) in c.segment_amounts(num) and c.found(sq)
            ieepa_ok = ieepa_ok and ok
            rec("stated IEEPA amount is printed with this entry", ok, f"${float(st):,.2f}")
    if not ieepa_ok:
        unverified.add("ieepa_duty")

    # 4b. every duty line read: the lines must add up to the duty total printed on the entry summary
    totals = c.printed_totals(num)
    if totals and e.get("lines"):
        all_duty = round(sum(float(h.get("duty") or 0) for ln in e["lines"] for h in ln.get("hts") or []), 2)
        if not rec("duty lines add up to the 7501 duty total", any(abs(all_duty - t) <= 0.05 for t in totals),
                   f"lines ${all_duty:,.2f} vs printed {', '.join(f'${t:,.2f}' for t in totals)}"):
            unverified.add("lines_incomplete")

    # 5. entry type printed next to the entry number
    et = str(e.get("entry_type") or "").zfill(2)
    if not rec(f"entry type {et} is printed next to this entry", c.type_near_entry(num, et), ""):
        unverified.add("entry_type")

    # 6. flag words next to the entry that the extraction doesn't reflect, and conflicting statements
    e["missed_signs"] = c.missed_signs(num, e) + c.conflicts(num, e)
    if e["missed_signs"]:
        rec("no flag words next to this entry that the extraction missed", False, ", ".join(e["missed_signs"]))

    e["unverified_fields"] = sorted(unverified)
    return log


def verify_importer(imp: dict, c: Corpus) -> tuple[dict, list[str]]:
    warnings = []
    if imp.get("cit_plaintiff"):
        q = imp.get("evidence") or ""
        d = imp.get("cit_ior_submitted_date")
        ok = c.found(q) and "plaintiff" in norm(q) and (d is None or d in dates_in(q))
        if not ok:
            warnings.append("The documents' claim that you are a court plaintiff could not be verified, "
                            "so finally liquidated entries are treated as having no current route.")
            imp = dict(imp, cit_plaintiff=False, cit_ior_submitted_date=None)
    return imp, warnings

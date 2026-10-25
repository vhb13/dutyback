"""Messy-paperwork robustness cases for DutyBack. Writes PDFs to pdfs/<run>/ and the
hand-written expected answers to expected/<run>.json. Everything is fictional.

Expected routes are written by hand from the rules in app/pipeline/rules.py
(ref() below is my own re-statement of those rules, not an import of the app).

Run: .venv/bin/python stress/robustness/make_cases.py
"""
from __future__ import annotations

import io
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PDFS = HERE / "pdfs"
EXP = HERE / "expected"
AS_OF = date(2026, 10, 24)
W, H = letter

CN_FENT, RECIP_BASE, RECIP_VN, RECIP_EU = "9903.01.24", "9903.01.25", "9903.02.69", "9903.02.20"
S301_L3, S232_STEEL, S232_ALU = "9903.88.03", "9903.81.91", "9903.85.08"


def ago(n: int) -> date:
    return AS_OF - timedelta(days=n)


def money(x: float) -> str:
    return f"{x:,.2f}"


def pct(r: float) -> str:
    s = f"{r * 100:.1f}".rstrip("0").rstrip(".")
    return f"{s}%"


def us(dt: date) -> str:
    return dt.strftime("%m/%d/%Y")


@dataclass
class Line:
    desc: str
    hts: str
    value: float
    mfn: float
    extra: list  # (code, rate)

    def rows(self):
        out = [(self.hts, self.value, self.mfn, round(self.value * self.mfn, 2))]
        out += [(c, None, r, round(self.value * r, 2)) for c, r in self.extra]
        return out


@dataclass
class Entry:
    key: str
    number: str
    edate: date
    lines: list = field(default_factory=list)
    liq: date | None = None
    etype: str = "01"
    ieepa_override: float | None = None     # statement-only entries: true IEEPA amount
    surety: bool = False
    protest_ieepa_only: bool = False
    expected: str | None = None             # hand override of the route
    acceptable: list = field(default_factory=list)  # other answers I'd also accept
    why: str = ""
    case: str = ""

    @property
    def ieepa(self) -> float:
        if self.ieepa_override is not None:
            return self.ieepa_override
        return round(sum(d for ln in self.lines for c, _v, _r, d in ln.rows() if c.startswith(("9903.01", "9903.02"))), 2)

    @property
    def total(self) -> float:
        return round(sum(d for ln in self.lines for *_x, d in ln.rows()), 2)


def ref(e: Entry, plaintiff: bool = False) -> tuple[str, str | None]:
    """My reading of rules.py decide() applied to the TRUE facts on paper."""
    if e.expected:
        route = e.expected
    elif e.ieepa <= 0:
        route = "NO_IEEPA"
    elif e.surety:
        route = "EXCLUDED_SURETY"
    elif e.protest_ieepa_only:
        route = "WITHDRAW_PROTEST_THEN_CAPE" if e.liq and (AS_OF - e.liq).days <= 80 else "PROTEST_OPEN"
    elif e.liq is None:
        route = "CAPE_NOW"
    else:
        age = (AS_OF - e.liq).days
        route = "CAPE_NOW" if age <= 80 else "PROTEST_BY" if age <= 180 else ("CAPE_PHASE3" if plaintiff else "CLASS_PENDING")
    dl = None
    if e.liq and route in ("CAPE_NOW", "WITHDRAW_PROTEST_THEN_CAPE", "FIX_THEN_CAPE"):
        dl = (e.liq + timedelta(days=80)).isoformat()
    if e.liq and route == "PROTEST_BY":
        dl = (e.liq + timedelta(days=180)).isoformat()
    return route, dl


def write_expected(run: str, entries: list[Entry], notes: str, plaintiff=False, extra=None):
    EXP.mkdir(exist_ok=True)
    out = {"run": run, "as_of": AS_OF.isoformat(), "notes": notes, "entries": []}
    for e in entries:
        route, dl = ref(e, plaintiff)
        refund = 0.0 if route in ("NO_IEEPA", "NEEDS_REVIEW") else e.ieepa
        out["entries"].append({"key": e.key, "case": e.case, "entry_number": e.number, "expected_route": route,
                               "acceptable": e.acceptable, "ieepa": e.ieepa, "refund": refund, "deadline": dl,
                               "liq": e.liq.isoformat() if e.liq else None, "why": e.why})
    if extra:
        out.update(extra)
    (EXP / f"{run}.json").write_text(json.dumps(out, indent=1))


# ---------------------------------------------------------------- drawing helpers

def wrap_words(c, text, width, font="Helvetica", size=8.5):
    words, line, out = text.split(), "", []
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) > width and line:
            out.append(line); line = w
        else:
            line = trial
    if line:
        out.append(line)
    return out


def para(c, text, x, y, width, size=10, lead=14, font="Helvetica"):
    for ln in wrap_words(c, text, width, font, size):
        c.setFont(font, size); c.drawString(x, y, ln); y -= lead
    return y


def draw_7501(c, imp: dict, e: Entry, lines=None, number_text=None, split_number=False, first_line_no=1,
              continuation=False, show_totals=True, page_note=""):
    """One 7501-style page. continuation=True draws a continuation sheet WITHOUT the entry number."""
    lines = e.lines if lines is None else lines
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, H - 40, "DEPARTMENT OF HOMELAND SECURITY")
    c.drawString(40, H - 54, "U.S. Customs and Border Protection")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(W - 40, H - 44, "ENTRY SUMMARY" + (" - CONTINUATION SHEET" if continuation else ""))
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 40, H - 56, "CBP Form 7501 (synthetic test document)" + (f"  {page_note}" if page_note else ""))
    c.line(40, H - 64, W - 40, H - 64)
    y = H - 82
    if not continuation:
        num = number_text or e.number
        box = [("1. Filer Code/Entry No.", num), ("2. Entry Type", e.etype + " ABI/A"),
               ("3. Summary Date", us(e.edate + timedelta(days=10))), ("4. Surety No.", "457"),
               ("6. Port Code", imp["port"]), ("7. Entry Date", us(e.edate)),
               ("26. Importer of Record No.", imp["ior"]), ("Importer of Record Name", imp["name"])]
        for i, (k, v) in enumerate(box):
            x = 40 + (i % 2) * 270
            c.setFont("Helvetica", 7.5); c.drawString(x, y, k)
            c.setFont("Helvetica-Bold", 10)
            if i == 0 and split_number:   # entry number wraps inside a narrow box
                cut = len(num) - 1 if num.count("-") == 2 else 4
                c.drawString(x, y - 12, num[:cut]); c.drawString(x, y - 24, num[cut:])
            else:
                c.drawString(x, y - 12, v)
            if i % 2:
                y -= 30 if not (split_number and i == 1) else 42
        y -= 6
    else:
        c.setFont("Helvetica", 8.5)
        c.drawString(40, y, "Lines continued from previous sheet.")
        y -= 16
    c.line(40, y, W - 40, y); y -= 14
    c.setFont("Helvetica-Bold", 8)
    for x, t in ((40, "27. Line No."), (95, "29. Description / A. HTSUS No."), (330, "32. Entered Value"),
                 (420, "33. HTSUS Rate"), (500, "34. Duty")):
        c.drawString(x, y, t)
    y -= 14
    for i, ln in enumerate(lines, start=first_line_no):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(40, y, f"{i:03d}"); c.drawString(95, y, ln.desc); y -= 13
        for code, val, rate, duty in ln.rows():
            c.setFont("Helvetica", 9.5)
            c.drawString(110, y, code)
            if val is not None:
                c.drawRightString(400, y, money(val))
            c.drawRightString(480, y, pct(rate) if rate else "Free")
            c.drawRightString(W - 40, y, money(duty))
            y -= 13
        y -= 6
    c.line(40, y, W - 40, y); y -= 16
    if show_totals:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(330, y, "37. Duty"); c.drawRightString(W - 40, y, money(e.total)); y -= 14
        c.setFont("Helvetica", 9)
        c.drawString(330, y, "40. Total"); c.drawRightString(W - 40, y, money(e.total))
    c.setFont("Helvetica", 8)
    c.drawString(40, 50, f"Filed by {imp['broker']} (filer code {imp['filer']}). Synthetic test document.")


class Doc:
    """Pages are drawing callbacks; scanned=True pages are rasterised and embedded as an image only."""

    def __init__(self, path: Path, title: str):
        self.path, self.title, self.pages = path, title, []

    def add(self, fn, scanned=False):
        self.pages.append((fn, scanned))

    def save(self):
        c = canvas.Canvas(str(self.path), pagesize=letter)
        c.setTitle(self.title)
        for fn, scanned in self.pages:
            if scanned:
                buf = io.BytesIO()
                t = canvas.Canvas(buf, pagesize=letter); fn(t); t.showPage(); t.save()
                with pdfplumber.open(io.BytesIO(buf.getvalue())) as pdf:
                    img = pdf.pages[0].to_image(resolution=130).original.convert("L")
                img = img.rotate(0.6, expand=False, fillcolor=255)  # slightly crooked, like a scan
                c.drawImage(ImageReader(img), 0, 0, W, H)
            else:
                fn(c)
            c.showPage()
        c.save()


def table(c, y, cols, heads, rows, size=8.5, lead=10.5, head_size=8.5):
    """Simple table; cell text wraps inside its column width (rows grow taller)."""
    c.setFont("Helvetica-Bold", head_size)
    for (x, w), h in zip(cols, heads):
        c.drawString(x, y, h)
    y -= 5; c.line(40, y, W - 40, y); y -= 12
    for r in rows:
        cells = [wrap_words(c, str(t), w - 4, size=size) or [""] for (x, w), t in zip(cols, r)]
        n = max(len(cl) for cl in cells)
        for k in range(n):
            for (x, w), cl in zip(cols, cells):
                if k < len(cl):
                    c.setFont("Helvetica", size); c.drawString(x, y - k * lead, cl[k])
        y -= n * lead + 5
    return y


def fresh(run: str) -> Path:
    d = PDFS / run
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


# ================================================================ RUN 1: date and amount formats

def run1():
    run = "r1_formats"; out = fresh(run)
    imp = dict(name="Zephyr Outdoor Supply LLC", ior="52-8830417-00", port="2704",
               broker="Pacific Gate Customs Brokerage", filer="ZT5")
    E = [
        Entry("F1", "ZT5-0414106-2", date(2025, 9, 9), [Line("Camping lanterns", "9405.40.8440", 33900.0, 0.039, [(RECIP_VN, 0.20)])],
              liq=ago(80), case="date '05-Aug-2026' (email)", why="liquidated exactly 80 days ago -> last CAPE day"),
        Entry("F2", "ZT5-0414288-6", date(2025, 10, 6), [Line("Hiking backpacks", "4202.92.3031", 21500.0, 0.176, [(RECIP_VN, 0.20)])],
              liq=ago(40), case="date '9/14/26' (statement, 2-digit year)"),
        Entry("F3", "ZT5-0413540-6", date(2025, 7, 14), [Line("Tent poles, aluminum", "6306.22.9030", 18400.0, 0.0, [(RECIP_BASE, 0.10)])],
              liq=ago(143), case="date '3rd June 2026' (email)"),
        Entry("F4", "ZT5-0414533-5", date(2025, 10, 1), [Line("Sleeping bags", "9404.30.8000", 26000.0, 0.09, [(CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=ago(64), case="date 'Aug. 21, 2026' (email)"),
        Entry("F5", "ZT5-0414879-0", date(2025, 10, 20), [Line("Trekking poles", "6602.00.0000", 14500.0, 0.0, [(RECIP_VN, 0.20)])],
              liq=ago(78), case="date '07/08/2026' in a DD/MM/YYYY notice (= 7 Aug)",
              why="US reading 07/08 = Jul 8 gives 108 days -> PROTEST_BY; correct (DD/MM) is Aug 7 -> CAPE_NOW"),
        Entry("F6", "ZT5-0415250-8", date(2025, 11, 12), [Line("Camp stoves", "7321.11.1060", 19400.0, 0.0, [(CN_FENT, 0.10), (RECIP_BASE, 0.10)])],
              liq=ago(31), case="date '23/09/2026' in a DD/MM/YYYY notice"),
        Entry("F7", "ZT5-0412988-1", date(2025, 4, 22), [Line("Rain jackets", "6201.40.7580", 28600.0, 0.071, [(RECIP_BASE, 0.10)])],
              liq=ago(89), case="control: ISO date 2026-07-27 (email)"),
        Entry("F8", "ZT5-0416018-4", date(2026, 1, 15), [], ieepa_override=5300.0,
              case="statement-only, amount '$5,300' (no cents), Open"),
        Entry("F9", "ZT5-0416475-1", date(2026, 2, 10), [], ieepa_override=1980.0, liq=ago(22),
              case="statement-only, amount '$1,980' (no cents), liq '10/02/26'"),
        Entry("F10", "ZT5-0415702-7", date(2025, 12, 3), [], ieepa_override=4410.0,
              case="email-only, amount '$4,410.00' with $ sign, still open"),
    ]
    by = {e.key: e for e in E}
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    for e in E[:7]:
        d.add(lambda c, e=e: draw_7501(c, imp, e))
    d.save()

    d = Doc(out / "2_broker_statement.pdf", "statement")
    def st(c):
        c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
        c.setFont("Helvetica", 9); c.drawString(40, H - 60, f"Filer {imp['filer']} - Open items statement - printed 10/21/26")
        c.drawString(40, H - 74, f"Client: {imp['name']}  IOR {imp['ior']}   (amounts rounded to whole dollars)")
        rows = []
        for k in ("F2", "F8", "F9"):
            e = by[k]
            rows.append([e.number, e.etype, e.edate.strftime("%-m/%-d/%y"), "Liquidated" if e.liq else "Open",
                         e.liq.strftime("%-m/%-d/%y") if e.liq else "-", f"${e.ieepa:,.0f}"])
        table(c, H - 100, [(40, 95), (135, 30), (165, 60), (225, 70), (295, 60), (355, 120)],
              ["Entry No.", "Type", "Entered", "Status", "Liq. Date", "IEEPA duty (9903.01/.02)"], rows)
    d.add(st); d.save()

    d = Doc(out / "3_broker_email.pdf", "email")
    def em(c):
        y = H - 48
        c.setFont("Helvetica", 9)
        for hl in ["From: Rafael Ortiz <rortiz@pacificgate.example>", "To: Jen Park <jen@zephyroutdoor.example>",
                   "Date: Wed, Oct 21, 2026 9:02 AM", "Subject: RE: liquidation dates for the refund project"]:
            c.drawString(40, y, hl); y -= 13
        y -= 14
        for p in [
            "Hi Jen, here are the liquidation dates you asked for, straight from our ops system (it prints dates its own way, sorry).",
            f"{by['F1'].number} liquidated on {by['F1'].liq.strftime('%d-%b-%Y')}.",
            f"{by['F3'].number} liquidated {by['F3'].liq.day}rd {by['F3'].liq.strftime('%B %Y')}.",
            f"{by['F4'].number} liquidated Aug. {by['F4'].liq.day}, {by['F4'].liq.year}.",
            f"{by['F7'].number} liquidated on {by['F7'].liq.isoformat()}.",
            f"{by['F10'].number} (December entry, ours too) is still open - not liquidated. The IEEPA duty on it was ${money(by['F10'].ieepa)}.",
            "No protests, no surety claims, no drawback on your account. Thanks, Rafael",
        ]:
            y = para(c, p, 40, y, W - 80) - 6
    d.add(em); d.save()

    d = Doc(out / "4_toronto_office_status_notice.pdf", "notice")
    def nt(c):
        c.setFont("Helvetica-Bold", 13); c.drawString(40, H - 50, "Zephyr Outdoor Supply - Toronto office")
        c.setFont("Helvetica", 9.5)
        c.drawString(40, H - 66, "US entry liquidation status (from broker portal).  ALL DATES ARE DD/MM/YYYY.")
        rows = [[by[k].number, "Liquidated", by[k].liq.strftime("%d/%m/%Y"), money(by[k].ieepa)] for k in ("F5", "F6")]
        table(c, H - 92, [(40, 110), (150, 70), (220, 150), (370, 120)],
              ["US Entry No.", "Status", "Liquidation (DD/MM/YYYY)", "IEEPA duty USD"], rows, size=9.5)
    d.add(nt); d.save()
    write_expected(run, E, "Liquidation dates and amounts in formats the code checker does not parse.")


# ================================================================ RUN 2: entry number formats and wrapped columns

def run2():
    run = "r2_numbers_wrap"; out = fresh(run)
    imp = dict(name="Quill & Ember Home LLC", ior="61-2047719-00", port="1001",
               broker="Northgate Customs House", filer="QE8")
    E = [
        Entry("E1", "QE8-0414106-2", date(2025, 9, 9), [Line("Scented candles", "3406.00.0000", 21000.0, 0.0, [(RECIP_VN, 0.20)])],
              liq=ago(57), case="entry number printed with spaces 'QE8 0414106 2' everywhere"),
        Entry("E2", "QE8-0414288-6", date(2026, 1, 6), [Line("Linen napkins", "6302.53.0010", 9800.0, 0.115, [(RECIP_EU, 0.15)])],
              case="spaces, unliquidated"),
        Entry("E3", "QE8-0415702-7", date(2025, 6, 2), [Line("Glass candle holders", "7013.99.5000", 16000.0, 0.06, [(RECIP_BASE, 0.10)])],
              liq=ago(106), case="entry number split across two lines (7501 box + statement column)"),
        Entry("E4", "316-4471902-5", date(2026, 2, 2), [], ieepa_override=2890.0,
              case="all-numeric filer code 316 (statement only)"),
        Entry("E5", "QE8-0416475-1", date(2026, 2, 10), [], ieepa_override=3180.0,
              case="statement-only, entry number wraps in narrow column"),
        Entry("E6", "QE8-0416018-4", date(2026, 1, 15), [], ieepa_override=4250.0, liq=ago(52), surety=True,
              case="surety remark wraps over 3 lines in a narrow Remarks column"),
        Entry("E7", "QE8-0415250-8", date(2025, 11, 12), [], ieepa_override=3880.0, liq=ago(53), protest_ieepa_only=True,
              case="protest remark (IEEPA only, OPEN) wraps over 3 lines"),
        Entry("E8", "QE8-0413540-6", date(2025, 7, 14), [], ieepa_override=3640.0, liq=ago(165),
              case="control row"),
    ]
    by = {e.key: e for e in E}
    sp = lambda n: n.replace("-", " ")
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    d.add(lambda c: draw_7501(c, imp, by["E1"], number_text=sp(by["E1"].number)))
    d.add(lambda c: draw_7501(c, imp, by["E2"], number_text=sp(by["E2"].number)))
    d.add(lambda c: draw_7501(c, imp, by["E3"], split_number=True))
    d.save()

    d = Doc(out / "2_broker_statement.pdf", "statement")
    def st(c):
        c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
        c.setFont("Helvetica", 9); c.drawString(40, H - 60, f"Filer {imp['filer']} - Client Refund Status Report - 10/20/2026")
        c.drawString(40, H - 74, f"Client: {imp['name']}  IOR {imp['ior']}")
        rem = {"E4": "Filed by our Chicago office under filer code 316",
               "E6": "Duties incl. IEEPA paid by surety after missed ACH; surety claim open",
               "E7": f"Protest filed 09/20/2026 (IEEPA duties only); status OPEN"}
        rows = []
        for k in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
            e = by[k]
            num = sp(e.number) if k in ("E1", "E2") else e.number
            amt = e.ieepa
            status = f"Liquidated {us(e.liq)}" if e.liq else "Open (unliquidated)"
            rows.append([num, e.etype, status, money(amt), rem.get(k, "")])
        # Entry No. column deliberately narrow so 13-char numbers wrap; Status and Remarks wrap too
        table(c, H - 100, [(40, 62), (102, 26), (128, 68), (196, 70), (266, 110)],
              ["Entry No.", "Typ", "ACE status", "IEEPA duty", "Remarks"], rows, size=8.5)
    d.add(st); d.save()
    write_expected(run, E, "Entry numbers with spaces / split lines / numeric filer code; wrapped table cells.")


# ================================================================ RUN 3: corrections, 4-line 7501, lumped Ch.99 column

def run3():
    run = "r3_corrections"; out = fresh(run)
    imp = dict(name="Brightwater Lighting Inc.", ior="27-6610043-00", port="5301",
               broker="Gulfway Customs Brokers", filer="BW2")
    r1_lines = [
        Line("LED table lamps", "9405.21.8000", 18200.0, 0.039, [(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)]),
        Line("Steel floor lamp bases", "9405.99.4090", 9600.0, 0.06, [(S301_L3, 0.25), (S232_STEEL, 0.50), (CN_FENT, 0.20)]),
        Line("Aluminum track light housings", "9405.99.4020", 7400.0, 0.06, [(S232_ALU, 0.50), (CN_FENT, 0.20), (RECIP_BASE, 0.10)]),
        Line("Glass lamp shades", "9405.91.1000", 5300.0, 0.06, [(S301_L3, 0.25), (RECIP_BASE, 0.10)]),
    ]
    E = [
        Entry("R1", "BW2-0418120-5", date(2025, 10, 2), r1_lines, liq=ago(57),
              case="4-line 7501 mixing Section 301, 232 and two IEEPA codes"),
        Entry("R2", "BW2-0418833-1", date(2025, 9, 15), [Line("Pendant lights", "9405.11.8010", 22000.0, 0.039, [(RECIP_VN, 0.20)])],
              liq=date(2026, 7, 20), case="statement row says liq 08/20/2026; correction line 'please disregard the previous liquidation date' gives 07/20/2026",
              why="corrected date 07/20/2026 = 96 days -> PROTEST_BY; old date would give CAPE_NOW"),
        Entry("R3", "BW2-0418907-2", date(2025, 8, 18), [Line("Ceiling fans with lights", "8414.51.0090", 15500.0, 0.047, [(RECIP_VN, 0.20)])],
              liq=date(2026, 6, 26), case="statement row says Open; revision note says liquidated 06/26/2026",
              why="120 days -> PROTEST_BY; 'Open' would give CAPE_NOW"),
        Entry("R4", "BW2-0411873-2", date(2025, 1, 14), [], ieepa_override=0.0,
              expected="NO_IEEPA", acceptable=["NEEDS_REVIEW"],
              case="statement-only, entered 01/14/2025 (before IEEPA), lumped 'Ch. 99 add'l duty' = Section 301 only, Open",
              why="no IEEPA in force; lumped Ch.99 column includes 301/232; any CAPE route is a false CSV entry"),
        Entry("R5", "BW2-0417654-9", date(2025, 9, 3), [], ieepa_override=0.0,
              expected="NEEDS_REVIEW", case="statement-only, lumped Ch.99 (301 + IEEPA) column, Open",
              why="IEEPA portion is not stated anywhere; app must not use the lumped total"),
        Entry("R6", "BW2-0419011-0", date(2025, 12, 1), [Line("String lights", "9405.31.0000", 12000.0, 0.039, [(RECIP_VN, 0.20)])],
              liq=ago(30), case="control"),
    ]
    by = {e.key: e for e in E}
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    for k in ("R1", "R2", "R3", "R6"):
        d.add(lambda c, e=by[k]: draw_7501(c, imp, e))
    d.save()

    lump = {"R1": sum(dd for ln in r1_lines for cc, _v, _r, dd in ln.rows() if cc.startswith("9903")),
            "R2": 4400.0, "R3": 3100.0, "R4": 7625.0, "R5": 5980.0, "R6": 2400.0}
    d = Doc(out / "2_broker_statement.pdf", "statement")
    def st(c):
        c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
        c.setFont("Helvetica", 9); c.drawString(40, H - 60, f"Filer {imp['filer']} - Liquidation & Duty Statement - 10/22/2026")
        c.drawString(40, H - 74, f"Client: {imp['name']}  IOR {imp['ior']}")
        rows = []
        for k in ("R4", "R2", "R3", "R5", "R1", "R6"):
            e = by[k]
            if k == "R2":
                status, ld = "Liquidated", "08/20/2026"
            elif k in ("R3", "R4", "R5"):
                status, ld = "Open", "-"
            else:
                status, ld = "Liquidated", us(e.liq)
            rows.append([e.number, "01", us(e.edate), status, ld, money(lump[k])])
        y = table(c, H - 100, [(40, 90), (130, 30), (160, 62), (222, 62), (284, 62), (346, 110)],
                  ["Entry No.", "Type", "Entry Dt", "Liq. Status", "Liq. Date", "Ch. 99 Add'l Duty"], rows)
        y -= 10
        c.setFont("Helvetica-Bold", 10); c.drawString(40, y, "Corrections to prior statement"); y -= 14
        c.setFont("Helvetica", 9)
        c.drawString(40, y, f"{by['R2'].number}: please disregard the previous liquidation date (08/20/2026); revised liquidation date is 07/20/2026."); y -= 13
        c.drawString(40, y, f"{by['R3'].number}: revised - liquidated 06/26/2026 (posted in ACE after our cut-off; 'Open' above is out of date)."); y -= 20
        y = para(c, "Ch. 99 Add'l Duty is the total of all Chapter 99 duties on the entry: Section 301, Section 232 and "
                    "IEEPA duties combined. It is not the IEEPA amount. Ask us for the line detail if you need the IEEPA portion.",
                 40, y, W - 80, size=8.5, lead=11)
    d.add(st); d.save()
    write_expected(run, E, "Corrections, a 4-line mixed 7501, and a lumped Chapter 99 column.")


# ================================================================ RUN 4: scanned pages and 2-column layout

def run4():
    run = "r4_scan_2col"; out = fresh(run)
    imp = dict(name="Harbor Lane Ceramics Co.", ior="93-1180462-00", port="2809",
               broker="Bayside Customs Services", filer="HL6")
    E = [
        Entry("S1", "HL6-0420114-3", date(2025, 11, 4), [Line("Stoneware mugs", "6912.00.4810", 14800.0, 0.098, [(RECIP_VN, 0.20)])],
              liq=ago(39), case="control 7501 + 2-column statement"),
        Entry("S2", "HL6-0420387-0", date(2026, 1, 20),
              [Line("Porcelain dinner plates", "6911.10.3810", 12400.0, 0.08, [(S301_L3, 0.25), (CN_FENT, 0.10)]),
               Line("Porcelain bowls", "6911.10.3850", 8800.0, 0.08, [(S301_L3, 0.25), (CN_FENT, 0.10), (RECIP_BASE, 0.10)]),
               Line("Porcelain platters", "6911.10.5200", 6100.0, 0.08, [(S301_L3, 0.25), (CN_FENT, 0.10), (RECIP_BASE, 0.10)])],
              case="2-page 7501; page 2 (lines 002-003, IEEPA rows, totals) is a SCANNED IMAGE",
              why="text layer only shows line 001; statement shows the full IEEPA total"),
        Entry("S3", "HL6-0420415-8", date(2025, 10, 28),
              [Line("Ceramic planters", "6912.00.5000", 9800.0, 0.06, [(S301_L3, 0.25)]),
               Line("Ceramic planters, glazed", "6912.00.5000", 11200.0, 0.06, [(CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=ago(57), case="2-page 7501; page 1 has only a Section 301 line; page 2 (IEEPA line) is SCANNED",
              why="text layer shows zero IEEPA, statement shows IEEPA total"),
        Entry("S4", "HL6-0421002-6", date(2026, 2, 3), [], ieepa_override=3300.0,
              case="appears ONLY on a scanned page (broker's supplemental list), Open"),
        Entry("S5", "HL6-0421077-4", date(2025, 12, 9), [], ieepa_override=2760.0, liq=ago(46),
              case="appears ONLY on a scanned page, liquidated"),
        Entry("S6", "HL6-0419530-1", date(2025, 9, 2), [], ieepa_override=6780.0, liq=ago(80),
              case="2-column block (left), liq 80 days ago"),
        Entry("S7", "HL6-0419544-7", date(2025, 9, 3), [], ieepa_override=3750.0, liq=ago(81),
              case="2-column block (right, beside S6), liq 81 days ago"),
        Entry("S8", "HL6-0419871-2", date(2026, 1, 12), [], ieepa_override=2215.0,
              case="2-column block (left), open"),
        Entry("S9", "HL6-0419902-5", date(2025, 11, 20), [], ieepa_override=4120.0, liq=ago(24),
              case="2-column block (right)"),
        Entry("S10", "HL6-0418811-0", date(2025, 7, 1), [], ieepa_override=5025.0, liq=ago(157),
              case="2-column block (left)"),
        Entry("S11", "HL6-0420006-9", date(2025, 11, 18), [], ieepa_override=2980.0, liq=ago(44), surety=True,
              case="2-column block (right), surety paid remark"),
    ]
    by = {e.key: e for e in E}
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    d.add(lambda c: draw_7501(c, imp, by["S1"]))
    s2 = by["S2"]
    d.add(lambda c: draw_7501(c, imp, s2, lines=s2.lines[:1], show_totals=False, page_note="page 1 of 2"))
    d.add(lambda c: draw_7501(c, imp, s2, lines=s2.lines[1:], first_line_no=2, continuation=True, page_note="page 2 of 2"), scanned=True)
    s3 = by["S3"]
    d.add(lambda c: draw_7501(c, imp, s3, lines=s3.lines[:1], show_totals=False, page_note="page 1 of 2"))
    d.add(lambda c: draw_7501(c, imp, s3, lines=s3.lines[1:], first_line_no=2, continuation=True, page_note="page 2 of 2"), scanned=True)
    d.save()

    d = Doc(out / "2_broker_supplemental_list_scanned.pdf", "scan")
    def sc(c):
        c.setFont("Helvetica-Bold", 13); c.drawString(40, H - 50, imp["broker"] + " - supplemental entry list")
        c.setFont("Helvetica", 10)
        c.drawString(40, H - 66, f"Client {imp['name']} (IOR {imp['ior']}). Entries not on the main statement:")
        rows = [[by[k].number, "01", "Liquidated " + us(by[k].liq) if by[k].liq else "Open", money(by[k].ieepa)] for k in ("S4", "S5")]
        table(c, H - 92, [(40, 110), (150, 40), (190, 150), (340, 120)], ["Entry No.", "Type", "ACE status", "IEEPA duty"], rows, size=10)
    d.add(sc, scanned=True); d.save()

    d = Doc(out / "3_broker_statement_two_column.pdf", "2col")
    def tc(c):
        c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"] + " - Entry status digest")
        c.setFont("Helvetica", 9); c.drawString(40, H - 60, f"Client: {imp['name']}  IOR {imp['ior']}  Prepared 10/22/2026")
        c.line(306, H - 75, 306, 60)
        left = ["S6", "S1", "S8", "S10"]
        right = ["S7", "S9", "S2", "S11", "S3"]
        extra = {"S6": ["Liquidated in ACE on the date shown.", "No protest filed; eligible items reviewed."],
                 "S8": ["Awaiting liquidation."],
                 "S11": ["Duties incl. IEEPA paid by surety", "after missed ACH; surety claim open."],
                 "S2": ["Multi-page 7501; see attached."],
                 "S3": ["Multi-page 7501; see attached."]}
        for col, keys, x in ((0, left, 40), (1, right, 318)):
            y = H - 92
            for k in keys:
                e = by[k]
                c.setFont("Helvetica-Bold", 9.5); c.drawString(x, y, f"Entry {e.number}  (type 01)"); y -= 12
                c.setFont("Helvetica", 9)
                c.drawString(x, y, f"Status: {'Liquidated ' + us(e.liq) if e.liq else 'Open / unliquidated'}"); y -= 12
                c.drawString(x, y, f"IEEPA duty: ${money(e.ieepa)}"); y -= 12
                for t in extra.get(k, []):
                    c.setFont("Helvetica-Oblique", 8.5); c.drawString(x + 8, y, t); y -= 11
                y -= 10 + (6 if col else 0)
    d.add(tc); d.save()
    write_expected(run, E, "Scanned (image-only) pages and a 2-column statement.")


# ================================================================ RUN 5: two importers mixed

def run5():
    run = "r5_two_importers"; out = fresh(run)
    for slug in ("lotus", "northtrail"):
        for p in sorted((ROOT / "data" / "samples" / slug).glob("*.pdf")):
            shutil.copy(p, out / f"{slug}_{p.name}")
    keys = {s: json.loads((ROOT / "data" / "answer_keys" / f"{s}.json").read_text()) for s in ("lotus", "northtrail")}
    ents = []
    for s, k in keys.items():
        for e in k["entries"]:
            ents.append({"key": e["key"], "case": f"{s} ({k['importer']}, IOR {k['ior']})", "entry_number": e["entry_number"],
                         "expected_route": e["expected_route"], "acceptable": [], "ieepa": e["ieepa_duty"],
                         "refund": 0.0 if e["expected_route"] in ("NO_IEEPA", "NEEDS_REVIEW") else e["ieepa_duty"],
                         "deadline": e["expected_deadline"], "liq": e["liquidation_date"], "why": e["note"],
                         "importer": s})
    EXP.mkdir(exist_ok=True)
    (EXP / f"{run}.json").write_text(json.dumps({
        "run": run, "as_of": AS_OF.isoformat(),
        "notes": "Lotus (not a CIT plaintiff) and North Trail (CIT plaintiff) paperwork uploaded together. Each "
                 "entry should be routed with ITS OWN importer's facts; CAPE files are per importer (IOR).",
        "entries": ents}, indent=1))


# ================================================================ RUN 6: ~60 entries, parallel Readers

def run6():
    run = "r6_long60"; out = fresh(run)
    imp = dict(name="Pinecrest Supply Co.", ior="45-3392108-00", port="3901",
               broker="Midlands Customs Brokerage", filer="PC9")
    rng = random.Random(6060)
    prods = [("Steel shelving units", "9403.20.0090", 0.0), ("Plastic storage bins", "3924.90.5650", 0.034),
             ("Cotton work gloves", "6116.92.6410", 0.094), ("LED work lights", "9405.42.8440", 0.039),
             ("Hand tools sets", "8206.00.0000", 0.04), ("Nylon tie-down straps", "6307.90.9889", 0.07)]
    used, E = set(), []
    ages = [None] * 14 + [5, 12, 20, 33, 47, 58, 66, 74, 79, 80, 81, 85, 95, 110, 120, 133, 150, 165, 179, 180,
                          181, 190, 210, 240] + [rng.randrange(1, 260) for _ in range(22)]
    rng.shuffle(ages)
    for i in range(60):
        while True:
            num = f"PC9-{rng.randrange(4100000, 4999999):07d}-{rng.randrange(10)}"
            if num not in used:
                used.add(num); break
        liq = ago(ages[i]) if ages[i] is not None else None
        edate = (liq - timedelta(days=rng.randrange(300, 330))) if liq else date(2025, 12, 1) + timedelta(days=rng.randrange(0, 80))
        edate = max(edate, date(2025, 4, 10))
        desc, hts, mfn = rng.choice(prods)
        val = round(rng.uniform(4000, 30000), -1)
        cn = rng.random() < 0.5
        extra = ([(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)] if cn else [(RECIP_VN, 0.20)])
        E.append(Entry(f"P{i + 1}", num, edate, [Line(desc, hts, val, mfn, extra)], liq=liq, case="bulk"))
    # P10: 2-page 7501 straddling the reader chunk boundary (bundle pages 10 and 11), page 2 has no entry number
    p10 = E[9]
    p10.lines = [Line("Steel shelving units", "9403.20.0090", 12000.0, 0.0, [(S301_L3, 0.25), (CN_FENT, 0.20)]),
                 Line("Plastic storage bins", "3924.90.5650", 8000.0, 0.034, [(S301_L3, 0.25)]),
                 Line("LED work lights", "9405.42.8440", 15000.0, 0.039, [(CN_FENT, 0.20), (RECIP_BASE, 0.10)]),
                 Line("Hand tools sets", "8206.00.0000", 9000.0, 0.04, [(CN_FENT, 0.20), (RECIP_BASE, 0.10)])]
    p10.liq = ago(44)
    p10.case = "2-page 7501 split across Reader chunks (pages 10/11); continuation sheet has no entry number"
    p10.why = "full IEEPA = all four lines; statement shows the full total"
    # P20: statement says liquidated 08/20/2026, a SEPARATE correction email says 07/20/2026
    p20 = E[19]; p20.liq = date(2026, 7, 20)
    p20.case = "statement 08/20/2026 vs separate correction email 07/20/2026 (different Reader chunks)"
    p20.why = "corrected date -> 96 days -> PROTEST_BY; statement date -> CAPE_NOW"
    # P30: statement says Open, correction email says liquidated 06/26/2026
    p30 = E[29]; p30.liq = date(2026, 6, 26); p30.edate = date(2025, 8, 20)
    p30.case = "statement 'Open' vs correction email 'liquidated 06/26/2026'"
    # P51-P60: statement only (no 7501 in the bundle)
    for e in E[50:]:
        e.case = "statement only (no 7501)"
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    for e in E[:50]:
        if e is p10:
            d.add(lambda c, e=e: draw_7501(c, imp, e, lines=e.lines[:2], show_totals=False, page_note="page 1 of 2"))
            d.add(lambda c, e=e: draw_7501(c, imp, e, lines=e.lines[2:], first_line_no=3, continuation=True, page_note="page 2 of 2"))
        else:
            d.add(lambda c, e=e: draw_7501(c, imp, e))
    d.save()

    d = Doc(out / "2_broker_duty_statement.pdf", "statement")
    rows_all = []
    for e in sorted(E, key=lambda x: x.number):
        if e is p20:
            st, ld = "Liquidated", "08/20/2026"
        elif e is p30:
            st, ld = "Open", "-"
        else:
            st, ld = ("Liquidated", us(e.liq)) if e.liq else ("Open", "-")
        rows_all.append([e.number, "01", us(e.edate), st, ld, money(e.total), money(e.ieepa)])
    per = 24
    for pi in range(0, len(rows_all), per):
        def st(c, chunk=rows_all[pi:pi + per], first=(pi == 0)):
            c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
            c.setFont("Helvetica", 9)
            c.drawString(40, H - 60, f"Client Liquidation & Duty Statement{'' if first else ' (continued)'} - {imp['name']} - IOR {imp['ior']} - 10/21/2026")
            table(c, H - 86, [(40, 90), (130, 30), (160, 62), (222, 62), (284, 62), (346, 70), (416, 120)],
                  ["Entry No.", "Type", "Entry Dt", "Liq. Status", "Liq. Date", "Total Duty", "IEEPA (9903.01/.02)"], chunk)
        d.add(st)
    d.save()

    d = Doc(out / "3_broker_correction_email.pdf", "email")
    def em(c):
        y = H - 48
        c.setFont("Helvetica", 9)
        for hl in ["From: Tom Becker <tbecker@midlandscustoms.example>", "To: AP <ap@pinecrest.example>",
                   "Date: Thu, Oct 22, 2026 11:40 AM", "Subject: Correction to yesterday's duty statement"]:
            c.drawString(40, y, hl); y -= 13
        y -= 14
        for p in ["Hi all, two corrections to the statement we sent yesterday (10/21/2026). ACE had not refreshed when it was run.",
                  f"1) Entry {p20.number}: the liquidation date is 07/20/2026, not 08/20/2026 as printed on the statement.",
                  f"2) Entry {p30.number}: this entry is not open. It liquidated on 06/26/2026.",
                  "Everything else on the statement is correct. Regards, Tom"]:
            y = para(c, p, 40, y, W - 80) - 6
    d.add(em); d.save()
    write_expected(run, E, "60 entries over ~55 pages -> several Readers in parallel (chunks of 10 pages per document).")


# ================================================================ RUN 7: an old (July) and a new (October) statement uploaded together

def run7():
    run = "r7_stale_statement"; out = fresh(run)
    imp = dict(name="Cobalt Garden Supply LLC", ior="38-5521906-00", port="1303",
               broker="Chesapeake Customs Brokers", filer="CG4")
    rng = random.Random(777)
    used, E = set(), []
    kinds = ["stale"] * 18 + ["open"] * 6 + ["old"] * 4 + ["extended", "scheduled"]
    for i, kind in enumerate(kinds):
        while True:
            num = f"CG4-{rng.randrange(5100000, 5999999):07d}-{rng.randrange(10)}"
            if num not in used:
                used.add(num); break
        liq = ago(81 + i % 20) if kind == "stale" else ago(120 + 3 * i) if kind == "old" else None
        edate = (liq - timedelta(days=314)) if liq else date(2025, 12, 1) + timedelta(days=rng.randrange(0, 70))
        val = round(rng.uniform(5000, 25000), -1)
        e = Entry(f"G{i + 1}", num, edate, [Line("Garden hose reels", "8424.90.9080", val, 0.0, [(RECIP_VN, 0.20)])], liq=liq)
        e.case = {"stale": "July statement 'Open', October statement 'Liquidated' 81-100 days ago",
                  "open": "Open on both statements", "old": "liquidated before July, same on both",
                  "extended": "October status 'Liquidation extended' (= not liquidated)",
                  "scheduled": "October status 'Unliquidated - scheduled liq. 11/06/2026'"}[kind]
        e.kind = kind
        E.append(e)
    # G21 (open on both): a Post Summary Correction 7501 at the END of the bundle replaces the original IEEPA line
    g = E[20]
    orig = Entry(g.key, g.number, g.edate, [Line(g.lines[0].desc, g.lines[0].hts, g.lines[0].value, 0.0, [(RECIP_VN, 0.20)])])
    g.lines = [Line(g.lines[0].desc, g.lines[0].hts, g.lines[0].value, 0.0, [(RECIP_BASE, 0.10)])]
    g.case = "original 7501 (9903.02.69 20%) on p21 + Post Summary Correction 7501 (9903.01.25 10%) on p31"
    g.why = "PSC replaces the original summary; IEEPA = PSC amount"
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    for e in E:
        d.add(lambda c, e=(orig if e is g else e): draw_7501(c, imp, e))
    d.add(lambda c: draw_7501(c, imp, g, page_note="POST SUMMARY CORRECTION filed 09/12/2026 - replaces the original entry summary"))
    d.save()

    def statement(fname, prepared, status_fn):
        d = Doc(out / fname, "statement")
        rows = [[e.number, "01", us(e.edate), *status_fn(e), money(e.ieepa)] for e in sorted(E, key=lambda x: x.number)]
        for pi in range(0, len(rows), 24):
            def st(c, chunk=rows[pi:pi + 24]):
                c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
                c.setFont("Helvetica", 9)
                c.drawString(40, H - 60, f"Client Liquidation & Duty Statement - {imp['name']} - IOR {imp['ior']} - Prepared {prepared}")
                table(c, H - 86, [(40, 90), (130, 30), (160, 62), (222, 120), (342, 62), (404, 120)],
                      ["Entry No.", "Type", "Entry Dt", "Liq. Status", "Liq. Date", "IEEPA (9903.01/.02)"], chunk)
            d.add(st)
        d.save()

    def july(e):
        if e.kind == "old":
            return ["Liquidated", us(e.liq)]
        return ["Open", "-"]

    def october(e):
        if e.kind in ("stale", "old"):
            return ["Liquidated", us(e.liq)]
        if e.kind == "extended":
            return ["Liquidation extended", "-"]
        if e.kind == "scheduled":
            return ["Unliquidated - scheduled", "11/06/2026"]
        return ["Open", "-"]

    statement("2_broker_statement_2026-07-15.pdf", "07/15/2026", july)
    statement("3_broker_statement_2026-10-21.pdf", "10/21/2026", october)
    write_expected(run, E, "An out-of-date July statement and the current October statement uploaded together (chunked Readers).")


# ================================================================ RUN 8: same as run 7 but 36 stale entries (can the Checker catch them all?)

def run8():
    run = "r8_stale_x36"; out = fresh(run)
    imp = dict(name="Driftwood Patio Co.", ior="58-7713320-00", port="1401",
               broker="Tidewater Customs Brokers", filer="DP1")
    rng = random.Random(888)
    used, E = set(), []
    kinds = ["stale"] * 36 + ["open"] * 4
    for i, kind in enumerate(kinds):
        while True:
            num = f"DP1-{rng.randrange(6100000, 6999999):07d}-{rng.randrange(10)}"
            if num not in used:
                used.add(num); break
        liq = ago(81 + i % 20) if kind == "stale" else None
        edate = (liq - timedelta(days=314)) if liq else date(2025, 12, 1) + timedelta(days=rng.randrange(0, 70))
        val = round(rng.uniform(5000, 25000), -1)
        e = Entry(f"D{i + 1}", num, edate, [Line("Patio umbrellas", "6601.10.0000", val, 0.065, [(RECIP_VN, 0.20)])], liq=liq)
        e.case = "July 'Open', October 'Liquidated' 81-100 days ago" if kind == "stale" else "Open on both"
        e.kind = kind
        E.append(e)
    d = Doc(out / "1_cbp7501_entry_summaries.pdf", "7501s")
    for e in E:
        d.add(lambda c, e=e: draw_7501(c, imp, e))
    d.save()
    for fname, prepared, fn in (("2_broker_statement_2026-07-15.pdf", "07/15/2026", lambda e: ["Open", "-"]),
                                ("3_broker_statement_2026-10-21.pdf", "10/21/2026",
                                 lambda e: ["Liquidated", us(e.liq)] if e.liq else ["Open", "-"])):
        d = Doc(out / fname, "statement")
        rows = [[e.number, "01", us(e.edate), *fn(e), money(e.ieepa)] for e in sorted(E, key=lambda x: x.number)]
        for pi in range(0, len(rows), 24):
            def st(c, chunk=rows[pi:pi + 24], prepared=prepared):
                c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 46, imp["broker"])
                c.setFont("Helvetica", 9)
                c.drawString(40, H - 60, f"Client Liquidation & Duty Statement - {imp['name']} - IOR {imp['ior']} - Prepared {prepared}")
                table(c, H - 86, [(40, 90), (130, 30), (160, 62), (222, 120), (342, 62), (404, 120)],
                      ["Entry No.", "Type", "Entry Dt", "Liq. Status", "Liq. Date", "IEEPA (9903.01/.02)"], chunk)
            d.add(st)
        d.save()
    write_expected(run, E, "Old July statement + current October statement, 36 entries changed status (chunked Readers).")


if __name__ == "__main__":
    for f in (run1, run2, run3, run4, run5, run6, run7, run8):
        f()
    for p in sorted(PDFS.glob("*/*.pdf")):
        with pdfplumber.open(p) as pdf:
            print(f"{p.relative_to(HERE)}: {len(pdf.pages)} pages")

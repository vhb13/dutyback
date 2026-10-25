"""Make the synthetic test importers: customs paperwork PDFs plus an answer key.

Everything here is made up. Company names, IOR numbers, entry numbers, values
and duty amounts are fictional. HTS codes and rates are illustrative of the
2025 IEEPA tariffs, not an exact copy of the tariff schedule.

Each importer uses a different broker paperwork style on purpose, because real
paperwork varies by broker and that is why an LLM reader is needed at all:
  lotus      -> CBP Form 7501-style pages + a broker duty statement table
  northtrail -> 7501-style pages + a differently laid out activity report + cover letter
  casaverde  -> an ACE-style line-detail report (no 7501s) + a broker email

The expected route for every entry is written by hand below (not computed by
the app's rules engine), so tests/test_answer_keys.py can check the engine
against an independent answer.

Run: python scripts/make_samples.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
KEYS = ROOT / "data" / "answer_keys"
AS_OF = date(2026, 10, 24)

# Chapter 99 codes used in the synthetic paperwork (illustrative)
CN_FENT = "9903.01.24"   # IEEPA, China/Hong Kong (fentanyl)
MX_FENT = "9903.01.01"   # IEEPA, Mexico (fentanyl)
CA_FENT = "9903.01.10"   # IEEPA, Canada (fentanyl)
MX_USMCA = "9903.01.04"  # IEEPA exemption line, USMCA-qualifying (0%)
RECIP_BASE = "9903.01.25"  # IEEPA reciprocal, 10% baseline
BR_IEEPA = "9903.01.77"  # IEEPA, Brazil
RECIP_VN = "9903.02.69"  # IEEPA reciprocal, Vietnam (illustrative)
RECIP_TW = "9903.02.61"  # IEEPA reciprocal, Taiwan (illustrative)
RECIP_EU = "9903.02.20"  # IEEPA reciprocal, EU (illustrative)
S301_L3 = "9903.88.03"   # Section 301 List 3 (NOT IEEPA)
S301_L4A = "9903.88.15"  # Section 301 List 4A (NOT IEEPA)
S232_STEEL = "9903.81.91"  # Section 232 steel derivative (NOT IEEPA)
S232_ALU = "9903.85.08"  # Section 232 aluminum derivative (NOT IEEPA)


@dataclass
class Line:
    desc: str
    hts: str
    value: float
    mfn_rate: float
    extra: list[tuple[str, float]]  # (chapter 99 code, rate)
    value_on_ch99: bool = False     # planted error: value also reported on the IEEPA line

    def rows(self):
        """(code, entered value or None, rate, duty) rows as they print on a 7501."""
        out = [(self.hts, self.value, self.mfn_rate, round(self.value * self.mfn_rate, 2))]
        for code, rate in self.extra:
            v = self.value if (self.value_on_ch99 and code.startswith(("9903.01", "9903.02"))) else None
            out.append((code, v, rate, round(self.value * rate, 2)))
        return out


@dataclass
class Entry:
    key: str
    number: str
    etype: str
    entry_date: date
    country: str
    lines: list[Line]
    liq: date | None = None             # None = unliquidated
    surety_paid: bool = False
    open_protest: bool = False
    protest_ieepa_only: bool = False
    protest_date: date | None = None
    drawback: bool = False
    recon: bool = False
    adcvd: bool = False
    in_7501_bundle: bool = True         # False = only appears in the broker statement/email
    stated_ieepa: float | None = None   # what the statement/email claims, if different
    expected_route: str = ""
    expected_flags: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def ieepa(self) -> float:
        return round(sum(d for ln in self.lines for (c, _v, _r, d) in ln.rows()
                         if c.startswith(("9903.01", "9903.02"))), 2)

    @property
    def total_duty(self) -> float:
        return round(sum(d for ln in self.lines for (_c, _v, _r, d) in ln.rows()), 2)


@dataclass
class Importer:
    slug: str
    name: str
    ior: str
    address: str
    broker: str
    broker_filer: str
    port: str
    cit_plaintiff: bool
    cit_case: str | None
    cit_ior_submitted: date | None
    entries: list[Entry]


def d(s: str) -> date:
    return date.fromisoformat(s)


def money(x: float) -> str:
    return f"{x:,.2f}"


def pct(r: float) -> str:
    s = f"{r * 100:.1f}".rstrip("0").rstrip(".")
    return f"{s}%"


def us(dt: date) -> str:
    return dt.strftime("%m/%d/%Y")


# ---------------------------------------------------------------------------
# The three importers
# ---------------------------------------------------------------------------

LOTUS = Importer(
    slug="lotus", name="Lotus Tile & Stone LLC", ior="84-2917365-00",
    address="1180 Alameda Industrial Way, Long Beach, CA 90813",
    broker="Harbor Point Customs Brokers", broker_filer="HP7", port="2704",
    cit_plaintiff=False, cit_case=None, cit_ior_submitted=None,
    entries=[
        Entry("A1", "HP7-0412207-3", "01", d("2025-02-18"), "CN",
              [Line("Glazed porcelain floor tile 60x60", "6907.21.1005", 41250.00, 0.085, [(CN_FENT, 0.10)])],
              liq=d("2025-12-29"), expected_route="CLASS_PENDING"),
        Entry("A2", "HP7-0412988-1", "01", d("2025-04-22"), "VN",
              [Line("Ceramic wall tile, glazed", "6907.22.0000", 28600.00, 0.10, [(RECIP_BASE, 0.10)])],
              liq=d("2026-03-02"), expected_route="CLASS_PENDING"),
        Entry("A3", "HP7-0413540-6", "01", d("2025-07-14"), "VN",
              [Line("Porcelain tile, unglazed", "6907.21.9011", 36400.00, 0.085, [(RECIP_BASE, 0.10)])],
              liq=d("2026-05-26"), expected_route="PROTEST_BY"),
        Entry("A4", "HP7-0413822-4", "01", d("2025-08-05"), "CN",
              [Line("Granite slabs, polished", "6802.93.0010", 52800.00, 0.037,
                    [(S301_L4A, 0.075), (CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=d("2026-06-15"), expected_route="PROTEST_BY",
              note="Section 301 duty on the same line is not refundable; only the two IEEPA lines count."),
        Entry("A5", "HP7-0414106-2", "01", d("2025-09-09"), "VN",
              [Line("Glazed porcelain floor tile 30x60", "6907.21.1005", 33900.00, 0.085, [(RECIP_VN, 0.20)])],
              liq=d("2026-08-05"), expected_route="CAPE_NOW",
              note="Liquidated exactly 80 days before the as-of date: last day CAPE accepts it."),
        Entry("A6", "HP7-0414117-9", "01", d("2025-09-10"), "VN",
              [Line("Mosaic tile sheets", "6907.40.0000", 18750.00, 0.10, [(RECIP_VN, 0.20)])],
              liq=d("2026-08-04"), expected_route="PROTEST_BY",
              note="Liquidated 81 days before the as-of date: one day too late for CAPE."),
        Entry("A7", "HP7-0414533-5", "01", d("2025-10-01"), "CN",
              [Line("Quartz surface slabs", "6810.99.0080", 44100.00, 0.049,
                    [(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=d("2026-08-28"), expected_route="CAPE_NOW"),
        Entry("A8", "HP7-0414879-0", "01", d("2025-10-20"), "VN",
              [Line("Porcelain step treads", "6907.21.1005", 22300.00, 0.085, [(RECIP_VN, 0.20)], value_on_ch99=True)],
              liq=d("2026-09-11"), expected_route="FIX_THEN_CAPE",
              expected_flags=["value_on_ch99_line"],
              note="Entered value was also reported on the IEEPA line; CAPE rejects that until it is corrected."),
        Entry("A9", "HP7-0415250-8", "01", d("2025-11-12"), "CN",
              [Line("Ceramic sinks", "6910.10.0030", 19400.00, 0.0, [(CN_FENT, 0.10), (RECIP_BASE, 0.10)])],
              liq=d("2026-10-02"), expected_route="CAPE_NOW"),
        Entry("A10", "HP7-0415702-7", "01", d("2025-12-03"), "VN",
              [Line("Glazed porcelain floor tile 60x60", "6907.21.1005", 38700.00, 0.085, [(RECIP_VN, 0.20)])],
              expected_route="CAPE_NOW"),
        Entry("A11", "HP7-0416018-4", "01", d("2026-01-15"), "IT",
              [Line("Porcelain tile, Italy", "6907.21.1005", 26500.00, 0.085, [(RECIP_EU, 0.15)])],
              surety_paid=True, expected_route="EXCLUDED_SURETY",
              note="Broker statement says the surety paid this entry's duties after a missed payment."),
        Entry("A12", "HP7-0416475-1", "01", d("2026-02-10"), "ES",
              [Line("Ceramic tile, Spain", "6907.22.0000", 21200.00, 0.10, [(RECIP_EU, 0.15)])],
              in_7501_bundle=False, expected_route="CONFIRM_THEN_CAPE",
              note="Only appears in the broker statement, with no 7501: the amount can't be checked against line detail, so it stays out of the CAPE file until confirmed."),
        Entry("A13", "HP7-0411873-2", "01", d("2025-01-21"), "CN",
              [Line("Granite slabs, polished", "6802.93.0010", 30500.00, 0.037, [(S301_L4A, 0.075)])],
              liq=d("2025-12-01"), expected_route="NO_IEEPA",
              note="Entered before the IEEPA tariffs started; Section 301 only, nothing to refund."),
    ],
)

NORTHTRAIL = Importer(
    slug="northtrail", name="North Trail Cycles Inc.", ior="41-7730284-00",
    address="55 Foundry Street, Unit 4, Burlington, VT 05401",
    broker="Keystone Trade Services", broker_filer="KT4", port="1001",
    cit_plaintiff=True, cit_case="North Trail Cycles Inc. v. United States, Ct. No. 26-01417",
    cit_ior_submitted=d("2026-07-22"),
    entries=[
        Entry("B1", "KT4-2207145-6", "01", d("2025-03-10"), "CN",
              [Line("Aluminum bicycle frames", "8714.91.3000", 47200.00, 0.039,
                    [(S301_L3, 0.25), (S232_ALU, 0.25), (CN_FENT, 0.20)])],
              liq=d("2026-01-19"), expected_route="CAPE_PHASE3",
              note="Finally liquidated, but the importer is a CIT plaintiff who gave CBP its IOR number by July 30."),
        Entry("B2", "KT4-2207698-3", "01", d("2025-05-06"), "TW",
              [Line("Bicycle derailleurs", "8714.99.5000", 31800.00, 0.0, [(RECIP_BASE, 0.10)])],
              liq=d("2026-03-16"), expected_route="CAPE_PHASE3"),
        Entry("B3", "KT4-2208011-9", "01", d("2025-06-17"), "CN",
              [Line("Bicycle wheels and hubs", "8714.92.1000", 26900.00, 0.02, [(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=d("2026-04-27"), open_protest=True, protest_ieepa_only=True, protest_date=d("2026-06-01"),
              expected_route="PROTEST_OPEN",
              note="Protest already filed; past 80 days so it cannot be swapped into CAPE."),
        Entry("B4", "KT4-2208260-1", "01", d("2025-07-21"), "TW",
              [Line("Bicycle disc brake sets", "8714.94.9010", 24300.00, 0.0, [(RECIP_BASE, 0.10)])],
              liq=d("2026-04-27"), expected_route="CAPE_PHASE3",
              note="Liquidated 180 days ago. A non-plaintiff would protest today; this importer is a CIT plaintiff (IOR by July 30), so Phase 3 covers it and a protest would block CAPE."),
        Entry("B5", "KT4-2208274-8", "01", d("2025-07-22"), "TW",
              [Line("Bicycle saddles", "8714.95.0000", 12600.00, 0.0, [(RECIP_BASE, 0.10)])],
              liq=d("2026-04-26"), expected_route="CAPE_PHASE3",
              note="181 days: finally liquidated; refundable only because the importer is a plaintiff."),
        Entry("B6", "KT4-2209003-5", "01", d("2025-09-22"), "CN",
              [Line("Bicycle frames, steel", "8714.91.2000", 29400.00, 0.039, [(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              recon=True, expected_route="CAPE_PHASE2_RECON"),
        Entry("B7", "KT4-2209318-2", "01", d("2025-10-14"), "VN",
              [Line("Bicycle tires", "4011.50.0000", 17500.00, 0.0, [(RECIP_VN, 0.20)])],
              liq=d("2026-09-08"), drawback=True, expected_route="EXCLUDED_DRAWBACK"),
        Entry("B8", "KT4-2209470-0", "01", d("2025-11-03"), "CN",
              [Line("Steel bicycle forks", "8714.91.5000", 21900.00, 0.0, [(S301_L3, 0.25), (S232_STEEL, 0.50), (CN_FENT, 0.10)])],
              liq=d("2026-09-21"), expected_route="CAPE_NOW",
              note="Section 301 and 232 lines are not refundable; only the IEEPA line counts."),
        Entry("B9", "KT4-2210027-4", "21", d("2026-01-08"), "TW",
              [Line("Carbon bicycle frames (warehouse)", "8714.91.3000", 58300.00, 0.039, [(RECIP_TW, 0.20)])],
              expected_route="ASK_BROKER", note="Warehouse entry: liquidates only after all withdrawals."),
        Entry("B10", "KT4-2210384-7", "01", d("2026-02-02"), "CN",
              [Line("Bicycle chains", "7315.11.0045", 9800.00, 0.0, [(S301_L3, 0.25), (CN_FENT, 0.10), (RECIP_BASE, 0.10)])],
              expected_route="CAPE_NOW"),
        Entry("B11", "KT4-2209566-1", "01", d("2025-10-27"), "CN",
              [Line("Bicycle pedals", "8714.96.9000", 14200.00, 0.0, [(S301_L3, 0.25), (CN_FENT, 0.20), (RECIP_BASE, 0.10)])],
              liq=d("2026-09-01"), open_protest=True, protest_ieepa_only=True, protest_date=d("2026-09-15"),
              expected_route="WITHDRAW_PROTEST_THEN_CAPE",
              note="Protest was filed only for the IEEPA refund and the entry is within 80 days, so it can be withdrawn and claimed in CAPE."),
    ],
)

CASAVERDE = Importer(
    slug="casaverde", name="Casa Verde Imports LLC", ior="74-5528190-00",
    address="2300 Pan American Blvd, Suite 12, Laredo, TX 78041",
    broker="Rio Bravo Customs Group", broker_filer="RB2", port="2304",
    cit_plaintiff=False, cit_case=None, cit_ior_submitted=None,
    entries=[
        Entry("C1", "RB2-5530118-4", "01", d("2025-03-11"), "MX",
              [Line("Talavera pottery planters", "6912.00.4810", 18900.00, 0.098, [(MX_FENT, 0.25)])],
              liq=d("2026-01-20"), expected_route="CLASS_PENDING"),
        Entry("C2", "RB2-5530462-2", "01", d("2025-04-08"), "MX",
              [Line("Wrought iron patio chairs (USMCA)", "9401.79.0050", 24600.00, 0.0, [(MX_USMCA, 0.0)])],
              liq=d("2026-02-16"), expected_route="NO_IEEPA",
              note="USMCA-qualifying: the IEEPA exemption line shows $0.00 duty, so nothing to refund."),
        Entry("C3", "RB2-5531077-9", "01", d("2025-06-03"), "CA",
              [Line("Maple syrup, bulk", "1702.20.4000", 15800.00, 0.0, [(CA_FENT, 0.25)])],
              liq=d("2026-04-13"), expected_route="CLASS_PENDING"),
        Entry("C4", "RB2-5531650-3", "08", d("2025-08-19"), "MX",
              [Line("Ceramic dinnerware (duty deferral)", "6912.00.4400", 13300.00, 0.06, [(MX_FENT, 0.25)])],
              expected_route="EXCLUDED_TYPE08"),
        Entry("C5", "RB2-5532014-6", "01", d("2025-09-16"), "MX",
              [Line("Wooden bedroom furniture", "9403.50.9045", 33700.00, 0.0, [(MX_FENT, 0.25)])],
              adcvd=True, expected_route="ASK_BROKER",
              note="AD/CVD case pending; CAPE treats these separately."),
        Entry("C6", "RB2-5532391-7", "01", d("2025-10-07"), "MX",
              [Line("Blown glass drinkware", "7013.37.5000", 21400.00, 0.05, [(MX_FENT, 0.25)])],
              liq=d("2026-08-17"), expected_route="CAPE_NOW"),
        Entry("C7", "RB2-5533008-0", "01", d("2025-11-18"), "CA",
              [Line("Maple syrup, retail bottles", "1702.20.2000", 11600.00, 0.0, [(CA_FENT, 0.35)])],
              liq=d("2026-10-05"), expected_route="CAPE_NOW"),
        Entry("C8", "RB2-5533742-5", "01", d("2026-01-27"), "MX",
              [Line("Hand-woven cotton rugs", "5702.99.1500", 16200.00, 0.03, [(MX_FENT, 0.25)])],
              expected_route="CAPE_NOW"),
        Entry("C9", "RB2-5531839-1", "01", d("2025-08-26"), "MX",
              [Line("Talavera pottery planters", "6912.00.4810", 20100.00, 0.098, [(MX_FENT, 0.25)])],
              liq=d("2026-07-06"), expected_route="PROTEST_BY"),
        Entry("C10", "RB2-5534106-8", "01", d("2026-02-17"), "BR",
              [Line("Green coffee beans", "0901.11.0055", 16050.00, 0.0, [(RECIP_BASE, 0.10), (BR_IEEPA, 0.30)])],
              stated_ieepa=6402.00, expected_route="CAPE_NOW",
              expected_flags=["statement_conflict"],
              note="The broker email states a different IEEPA total than the line detail; line detail is authoritative."),
    ],
)

IMPORTERS = [LOTUS, NORTHTRAIL, CASAVERDE]


# ---------------------------------------------------------------------------
# Meridian: a bigger importer (48 entries, multi-line entries), generated from a
# fixed seed. Its answer key comes from ref_route() below, a separate, deliberately
# simple implementation of the rules written independently of app/pipeline/rules.py.
# ---------------------------------------------------------------------------
import random  # noqa: E402

PRODUCTS = [
    ("Stoneware dinner plates", "6912.00.4400", 0.06), ("Cotton bath towels", "6302.60.0020", 0.091),
    ("Glass storage jars", "7013.49.6000", 0.06), ("Steel cookware sets", "7323.93.0045", 0.02),
    ("Bamboo cutting boards", "4419.11.0000", 0.032), ("LED table lamps", "9405.21.8000", 0.039),
    ("Polyester throw blankets", "6301.40.0020", 0.085), ("Ceramic vases", "6913.90.5000", 0.06),
    ("Aluminum baking sheets", "7615.10.7125", 0.031), ("Wool area rugs", "5701.10.9000", 0.0),
    ("Stainless flatware", "8215.20.0000", 0.0), ("Wooden picture frames", "4414.90.0000", 0.0),
]
STEEL_ALU = {"Steel cookware sets": S232_STEEL, "Aluminum baking sheets": S232_ALU}


def ch99_for(country: str, day: date) -> list[tuple[str, float]]:
    aug7 = date(2025, 8, 7)
    if country == "CN":
        fent = 0.10 if day < date(2025, 3, 4) else (0.20 if day < date(2025, 11, 10) else 0.10)
        out = [(CN_FENT, fent)]
        if day >= date(2025, 4, 5):
            out.append((RECIP_BASE, 0.10))
        return out
    if country == "MX":
        return [(MX_FENT, 0.25)] if day >= date(2025, 3, 4) else []
    if day < date(2025, 4, 5):
        return []
    if country == "VN":
        return [(RECIP_BASE, 0.10)] if day < aug7 else [(RECIP_VN, 0.20)]
    if country == "TW":
        return [(RECIP_BASE, 0.10)] if day < aug7 else [(RECIP_TW, 0.20)]
    if country == "IN":
        return [(RECIP_BASE, 0.10)] if day < aug7 else [("9903.02.26", 0.25)]
    return [(RECIP_BASE, 0.10)] if day < aug7 else [(RECIP_EU, 0.15)]


def ref_route(e: Entry, as_of: date, plaintiff: bool = False) -> str:
    """Independent reference implementation used only to build Meridian's answer key."""
    if e.ieepa <= 0:
        return "NO_IEEPA"
    if e.surety_paid:
        return "EXCLUDED_SURETY"
    if e.etype == "08":
        return "EXCLUDED_TYPE08"
    if e.drawback:
        return "EXCLUDED_DRAWBACK"
    if e.adcvd or e.etype == "21":
        return "ASK_BROKER"
    fix = any(ln.value_on_ch99 for ln in e.lines)
    age = None if e.liq is None else (as_of - e.liq).days
    if e.open_protest:
        if age is not None and e.protest_ieepa_only and age <= 80:
            return "WITHDRAW_PROTEST_THEN_CAPE"
        return "PROTEST_OPEN"
    if age is None or age <= 80:
        if e.recon:
            return "CAPE_PHASE2_RECON"
        if not e.in_7501_bundle:
            return "CONFIRM_THEN_CAPE"
        return "FIX_THEN_CAPE" if fix else "CAPE_NOW"
    if plaintiff:
        return "CAPE_PHASE3"
    if age <= 180:
        return "PROTEST_BY"
    return "CLASS_PENDING"


def make_meridian() -> Importer:
    rng = random.Random(20261024)
    countries = ["CN", "CN", "CN", "VN", "VN", "TW", "IN", "MX", "IT", "DE"]
    used = set()
    entries: list[Entry] = []
    start, end = date(2025, 2, 10), date(2026, 2, 19)
    span = (end - start).days
    forced_ages = {5: 80, 9: 81, 14: 180, 19: 181, 23: 79, 27: 1}
    for i in range(46):
        while True:
            day = start + timedelta(days=rng.randrange(span))
            if not (date(2025, 4, 9) <= day <= date(2025, 5, 13)):
                break
        country = rng.choice(countries)
        nlines = rng.choice([1, 1, 2, 2, 3, 4])
        lines = []
        for _ in range(nlines):
            desc, hts, mfn = rng.choice(PRODUCTS)
            value = round(rng.uniform(2000, 16000), -1)
            extra = []
            if country == "CN" and rng.random() < 0.6:
                extra.append((S301_L3, 0.25))
            if desc in STEEL_ALU and day >= date(2025, 3, 12):
                extra.append((STEEL_ALU[desc], 0.50 if day >= date(2025, 6, 4) else 0.25))
            extra += ch99_for(country, day)
            lines.append(Line(desc, hts, value, mfn, extra))
        while True:
            num = f"MH3-{rng.randrange(1000000, 9999999):07d}-{rng.randrange(10)}"
            if num not in used:
                used.add(num)
                break
        liq = day + timedelta(days=314 + rng.randrange(0, 5))
        if i in forced_ages:
            liq = AS_OF - timedelta(days=forced_ages[i])
            day = liq - timedelta(days=314)
            lines = [Line(ln.desc, ln.hts, ln.value, ln.mfn_rate, ch99_for(country, day) or [(RECIP_BASE, 0.10)]) for ln in lines]
        if liq > AS_OF:
            liq = None
        entries.append(Entry(f"M{i + 1}", num, "01", day, country, lines, liq=liq))
    # two entries from before the IEEPA tariffs (Section 301 only)
    for j, day in enumerate([date(2025, 1, 14), date(2025, 1, 28)]):
        entries.append(Entry(f"M{47 + j}", f"MH3-04{j}1187-{j + 3}", "01", day, "CN",
                             [Line("Steel cookware sets", "7323.93.0045", 18400.0 + j * 2300, 0.02, [(S301_L3, 0.25)])],
                             liq=day + timedelta(days=316)))
    # plant the special cases on specific entries
    by = {e.key: e for e in entries}
    paid = [e for e in entries[:46] if e.ieepa > 0 and e.liq is not None]
    paid[1].surety_paid = True
    by["M8"].drawback = True
    by["M11"].recon = True
    by["M11"].liq = None
    by["M16"].etype = "21"
    by["M16"].liq = None
    by["M21"].adcvd = True
    by["M25"].liq = AS_OF - timedelta(days=40)
    by["M25"].open_protest, by["M25"].protest_ieepa_only, by["M25"].protest_date = True, True, AS_OF - timedelta(days=20)
    if by["M30"].liq is None or (AS_OF - by["M30"].liq).days <= 80:
        by["M30"].liq = AS_OF - timedelta(days=150)
    by["M30"].open_protest, by["M30"].protest_ieepa_only, by["M30"].protest_date = True, False, by["M30"].liq + timedelta(days=60)
    by["M34"].lines[0].value_on_ch99 = True
    by["M34"].liq = AS_OF - timedelta(days=33)
    by["M38"].in_7501_bundle = False
    imp = Importer(
        slug="meridian", name="Meridian Home Goods Co.", ior="36-4471902-00",
        address="900 Commerce Park Dr, Columbus, OH 43219",
        broker="Lakeshore Customs & Logistics", broker_filer="MH3", port="4101",
        cit_plaintiff=False, cit_case=None, cit_ior_submitted=None, entries=entries)
    for e in entries:
        if not any(c.startswith(("9903.01", "9903.02")) for ln in e.lines for c, _r in ln.extra):
            e.lines = [Line(ln.desc, ln.hts, ln.value, ln.mfn_rate, [x for x in ln.extra]) for ln in e.lines]
        e.expected_route = ref_route(e, AS_OF)
        if any(ln.value_on_ch99 for ln in e.lines):
            e.expected_flags = ["value_on_ch99_line"]
    return imp


MERIDIAN = make_meridian()
IMPORTERS.append(MERIDIAN)


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def _wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, font="Helvetica", size=9.5, lead=13):
    words, line = text.split(), ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) > width:
            c.setFont(font, size); c.drawString(x, y, line); y -= lead; line = w
        else:
            line = trial
    if line:
        c.setFont(font, size); c.drawString(x, y, line); y -= lead
    return y


def draw_7501(c: canvas.Canvas, imp: Importer, e: Entry, style: str):
    W, H = letter
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, H - 40, "DEPARTMENT OF HOMELAND SECURITY")
    c.drawString(40, H - 54, "U.S. Customs and Border Protection")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(W - 40, H - 44, "ENTRY SUMMARY")
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 40, H - 56, "CBP Form 7501 (synthetic sample - not a real filing)")
    c.line(40, H - 64, W - 40, H - 64)

    box = [
        ("1. Filer Code/Entry No.", e.number), ("2. Entry Type", e.etype + (" ABI/A" if style == "lotus" else " ABI")),
        ("3. Summary Date", us(e.entry_date + timedelta(days=10))), ("4. Surety No.", "457"),
        ("5. Bond Type", "8"), ("6. Port Code", imp.port), ("7. Entry Date", us(e.entry_date)),
        ("10. Country of Origin", e.country), ("11. Import Date", us(e.entry_date - timedelta(days=1))),
        ("26. Importer of Record No.", imp.ior), ("Importer of Record Name", imp.name),
    ]
    if e.recon:
        box.append(("Reconciliation flag", "Y (NAFTA/value recon flagged)" if style != "lotus" else "Y"))
    y = H - 82
    for i, (k, v) in enumerate(box):
        col = i % 2
        x = 40 + col * 270
        c.setFont("Helvetica", 7.5); c.drawString(x, y, k)
        c.setFont("Helvetica-Bold", 10); c.drawString(x, y - 12, v)
        if col == 1:
            y -= 30
    if len(box) % 2:
        y -= 30
    y -= 6
    c.line(40, y, W - 40, y)
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "27. Line No.")
    c.drawString(95, y, "29. Description / A. HTSUS No.")
    c.drawString(330, y, "32. Entered Value")
    c.drawString(420, y, "33. HTSUS Rate")
    c.drawString(500, y, "34. Duty")
    y -= 14
    for i, ln in enumerate(e.lines, start=1):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(40, y, f"{i:03d}")
        c.drawString(95, y, ln.desc)
        y -= 13
        for code, val, rate, duty in ln.rows():
            c.setFont("Helvetica", 9.5)
            c.drawString(110, y, code)
            if val is not None:
                c.drawRightString(400, y, money(val))
            c.drawRightString(480, y, pct(rate) if rate else "Free")
            c.drawRightString(W - 40, y, money(duty))
            y -= 13
        y -= 6
    c.line(40, y, W - 40, y)
    y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(330, y, "37. Duty")
    c.drawRightString(W - 40, y, money(e.total_duty))
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(330, y, "40. Total")
    c.drawRightString(W - 40, y, money(e.total_duty))
    y -= 30
    c.setFont("Helvetica", 8)
    c.drawString(40, y, f"Filed by {imp.broker} (filer code {imp.broker_filer}). Synthetic document for a student demo.")
    c.showPage()


def make_7501_bundle(imp: Importer, path: Path):
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(f"{imp.name} - CBP 7501 entry summaries")
    for e in imp.entries:
        if e.in_7501_bundle:
            draw_7501(c, imp, e, imp.slug)
    c.save()


def statement_note(e: Entry) -> str:
    notes = []
    if e.surety_paid:
        notes.append("Duties incl. IEEPA paid by surety after missed ACH; surety claim open")
    if e.open_protest:
        notes.append(f"Protest filed {us(e.protest_date)} (IEEPA duties only); status OPEN")
    if e.drawback:
        notes.append("Drawback claim filed against this entry")
    if e.recon:
        notes.append("Flagged for reconciliation; no type 09 filed yet")
    if e.adcvd:
        notes.append("AD/CVD case pending - liquidation suspended")
    if e.etype == "21":
        notes.append("Warehouse entry; withdrawals ongoing")
    if e.etype == "08":
        notes.append("Duty deferral entry (type 08)")
    if not e.in_7501_bundle:
        notes.append("7501 copy not yet sent to client")
    return "; ".join(notes)


def make_lotus_statement(imp: Importer, path: Path):
    """Broker duty statement table (used for Lotus and Meridian), paginated."""
    W, H = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(f"{imp.broker} - Liquidation and Duty Statement")
    cols = [40, 128, 178, 236, 314, 380, 452]
    heads = ["Entry No.", "Type", "Entry Dt", "Liq. Status", "Liq. Date", "Total Duty", "IEEPA (9903.01/.02)"]

    def header(first: bool):
        c.setFont("Helvetica-Bold", 15)
        c.drawString(40, H - 46, imp.broker)
        c.setFont("Helvetica", 9)
        c.drawString(40, H - 60, f"Filer code {imp.broker_filer} · Licensed customs broker · Synthetic sample")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, H - 88, "Client Liquidation & Duty Statement" + ("" if first else " (continued)"))
        c.setFont("Helvetica", 9.5)
        c.drawString(40, H - 104, f"Client: {imp.name}   IOR: {imp.ior}   Prepared: 10/22/2026")
        y = H - 130
        c.setFont("Helvetica-Bold", 8.5)
        for x, h in zip(cols, heads):
            c.drawString(x, y, h)
        y -= 6
        c.line(40, y, W - 40, y)
        return y - 13

    y = header(True)
    for e in sorted(imp.entries, key=lambda x: x.entry_date):
        note = statement_note(e)
        if y < 70 + (11 if note else 0):
            c.showPage()
            y = header(False)
        c.setFont("Helvetica", 8.5)
        c.drawString(cols[0], y, e.number)
        c.drawString(cols[1], y, e.etype)
        c.drawString(cols[2], y, us(e.entry_date))
        c.drawString(cols[3], y, "Liquidated" if e.liq else "Open")
        c.drawString(cols[4], y, us(e.liq) if e.liq else "-")
        c.drawRightString(cols[5] + 58, y, money(e.total_duty))
        c.drawRightString(cols[6] + 80, y, money(e.stated_ieepa if e.stated_ieepa is not None else e.ieepa))
        if note:
            y -= 11
            c.setFont("Helvetica-Oblique", 7.8)
            c.drawString(cols[0] + 10, y, "Note: " + note)
        y -= 15
    if y < 110:
        c.showPage()
        y = H - 60
    y -= 10
    _wrap(c, "Liquidation dates are as posted in ACE. IEEPA amounts are the duties reported under HTSUS "
             "Chapter 99 subheadings 9903.01 and 9903.02 on each entry. This statement does not include "
             "Section 301 or Section 232 duties in the IEEPA column.", 40, y, W - 80, size=8.5, lead=11)
    c.showPage()
    c.save()


def make_northtrail_report(imp: Importer, path: Path):
    W, H = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Keystone Trade Services - Account activity")
    # cover letter
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H - 50, "KEYSTONE TRADE SERVICES")
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 64, "Licensed customs broker · filer KT4 · Champlain, NY · Synthetic sample")
    y = H - 100
    c.setFont("Helvetica", 10)
    for para in [
        "October 21, 2026",
        f"To: Accounts payable, {imp.name}",
        "Re: IEEPA duty refunds - status of your entries",
        "As requested, attached is the account activity report for all entries we filed for you since "
        "January 2025, with current ACE liquidation status. Please note that "
        f"{imp.name} is a plaintiff in {imp.cit_case} at the U.S. Court of International Trade. "
        f"Your importer of record number was submitted to CBP on {imp.cit_ior_submitted.strftime('%B %-d, %Y')}, "
        "per counsel.",
        "We have not yet filed CAPE declarations for any of these entries. Let us know which entries you "
        "would like us to include.",
        "Regards, Dana Whitcomb, Licensed Customs Broker",
    ]:
        y = _wrap(c, para, 40, y, W - 80, size=10, lead=14) - 8
    c.showPage()
    # activity report, different layout and column names
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, H - 46, "Account Activity Report - North Trail Cycles Inc.")
    c.setFont("Helvetica", 8.5)
    c.drawString(40, H - 60, f"IOR {imp.ior} · run date 2026-10-21 · amounts in USD")
    y = H - 84
    for e in sorted(imp.entries, key=lambda x: x.number):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(40, y, f"Entry {e.number}   (type {e.etype}, entered {e.entry_date.isoformat()})")
        y -= 13
        c.setFont("Helvetica", 9)
        liq = f"liquidated {e.liq.isoformat()}" if e.liq else "unliquidated"
        c.drawString(56, y, f"ACE status: {liq}.  Duty deposited: ${money(e.total_duty)}.  "
                            f"Of which IEEPA: ${money(e.stated_ieepa if e.stated_ieepa is not None else e.ieepa)}.")
        y -= 12
        n = statement_note(e)
        if n:
            c.setFont("Helvetica-Oblique", 8.5)
            c.drawString(56, y, n + ".")
            y -= 12
        y -= 7
        if y < 70:
            c.showPage(); y = H - 50
    c.showPage()
    c.save()


def make_casaverde_ace(imp: Importer, path: Path):
    W, H = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("ACE Report ES-003 Entry Summary Line Details")

    def header():
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, H - 40, "ACE Reports - ES-003 Entry Summary Line Details (export)")
        c.setFont("Helvetica", 8)
        c.drawString(40, H - 52, f"Importer: {imp.ior} {imp.name} · Filer: {imp.broker_filer} · Synthetic sample")
        cols = [("Entry Summary No", 40), ("Typ", 120), ("Entry Dt", 142), ("Ln", 192), ("HTS No", 210),
                ("COO", 268), ("Entered Value", 292), ("Rate", 352), ("Duty", 388), ("Description", 434)]
        c.setFont("Helvetica-Bold", 7.3)
        for t, x in cols:
            c.drawString(x, H - 72, t)
        c.line(40, H - 76, W - 40, H - 76)
        return H - 88

    y = header()
    for e in sorted(imp.entries, key=lambda x: x.entry_date):
        for i, ln in enumerate(e.lines, start=1):
            for code, val, rate, duty in ln.rows():
                c.setFont("Helvetica", 7.3)
                c.drawString(40, y, e.number.replace("-", ""))
                c.drawString(120, y, e.etype)
                c.drawString(142, y, e.entry_date.isoformat())
                c.drawString(192, y, str(i))
                c.drawString(210, y, code.replace(".", ""))
                c.drawString(268, y, e.country)
                if val is not None:
                    c.drawRightString(345, y, f"{val:.2f}")
                c.drawRightString(380, y, f"{rate:.3f}")
                c.drawRightString(426, y, f"{duty:.2f}")
                c.drawString(434, y, ln.desc[:30] if code == ln.hts else "")
                y -= 11
                if y < 60:
                    c.showPage(); y = header()
        y -= 4
    c.showPage()
    c.save()


def make_casaverde_email(imp: Importer, path: Path):
    W, H = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Email from Rio Bravo Customs Group")
    byk = {e.key: e for e in imp.entries}
    y = H - 48
    c.setFont("Helvetica", 9)
    for hl in ["From: Marisol Treviño <mtrevino@riobravocustoms.example>",
               "To: Ana Castillo <ana@casaverdeimports.example>",
               "Date: Thu, Oct 22, 2026 4:12 PM",
               "Subject: RE: tariff refunds - where do we stand?"]:
        c.drawString(40, y, hl); y -= 13
    c.line(40, y - 2, W - 40, y - 2)
    y -= 20

    def e_(k):
        return byk[k]

    def fmt(dt):
        return dt.strftime("%B %-d, %Y")

    paras = [
        "Hi Ana,",
        "Here is where your entries stand in ACE as of this morning. I've attached the ES-003 line detail "
        "export so you have the duty breakdown by HTS line. Entry numbers below are written the way ACE shows them.",
        f"Older ones: {e_('C1').number.replace('-', '')} (the Talavera planters from March 2025) liquidated on "
        f"{fmt(e_('C1').liq)}. {e_('C2').number.replace('-', '')} (the USMCA patio chairs) liquidated "
        f"{fmt(e_('C2').liq)}. The Canadian syrup entry {e_('C3').number.replace('-', '')} liquidated on "
        f"{fmt(e_('C3').liq)}. We did not protest any of these.",
        f"{e_('C9').number.replace('-', '')} liquidated on {fmt(e_('C9').liq)}. "
        f"{e_('C6').number.replace('-', '')} (the glassware) liquidated on {fmt(e_('C6').liq)}, and the retail "
        f"syrup entry {e_('C7').number.replace('-', '')} liquidated on {fmt(e_('C7').liq)}.",
        f"{e_('C4').number.replace('-', '')} is your type 08 duty deferral entry from August 2025; it is still open. "
        f"{e_('C5').number.replace('-', '')} (bedroom furniture) is stuck because of the AD/CVD case, so liquidation "
        f"is suspended. {e_('C8').number.replace('-', '')} (rugs) has not liquidated yet.",
        f"The coffee entry {e_('C10').number.replace('-', '')} from February is also unliquidated. By my math the "
        f"IEEPA portion on that one was about ${money(e_('C10').stated_ieepa)}, but double-check against the line detail.",
        "Nothing was paid by the surety, and we have no drawback or reconciliation on your account. "
        "Let me know how you want to handle the refunds - we can file CAPE for you for a flat fee per declaration.",
        "Best, Marisol",
    ]
    c.setFont("Helvetica", 10)
    for p in paras:
        y = _wrap(c, p, 40, y, W - 80, size=10, lead=14) - 8
    c.showPage()
    c.save()


def expected_deadline(e: Entry) -> str | None:
    if e.liq and e.expected_route in ("CAPE_NOW", "FIX_THEN_CAPE", "WITHDRAW_PROTEST_THEN_CAPE", "CONFIRM_THEN_CAPE", "CAPE_PHASE2_RECON"):
        return (e.liq + timedelta(days=80)).isoformat()
    if e.liq and e.expected_route == "PROTEST_BY":
        return (e.liq + timedelta(days=180)).isoformat()
    return None


def answer_key(imp: Importer) -> dict:
    return {
        "importer": imp.name,
        "ior": imp.ior,
        "as_of": AS_OF.isoformat(),
        "cit_plaintiff": imp.cit_plaintiff,
        "entries": [
            {
                "key": e.key,
                "entry_number": e.number,
                "entry_type": e.etype,
                "entry_date": e.entry_date.isoformat(),
                "liquidation_date": e.liq.isoformat() if e.liq else None,
                "ieepa_duty": e.ieepa,
                "total_duty": e.total_duty,
                "expected_route": e.expected_route,
                "expected_deadline": expected_deadline(e),
                "expected_flags": e.expected_flags,
                "note": e.note,
            }
            for e in imp.entries
        ],
    }


def main():
    SAMPLES.mkdir(parents=True, exist_ok=True)
    KEYS.mkdir(parents=True, exist_ok=True)
    for imp in IMPORTERS:
        out = SAMPLES / imp.slug
        out.mkdir(exist_ok=True)
        for old in out.glob("*.pdf"):
            old.unlink()
        if imp.slug in ("lotus", "meridian"):
            make_7501_bundle(imp, out / "1_cbp7501_entry_summaries.pdf")
            make_lotus_statement(imp, out / "2_broker_duty_statement.pdf")
        elif imp.slug == "northtrail":
            make_7501_bundle(imp, out / "1_cbp7501_entry_summaries.pdf")
            make_northtrail_report(imp, out / "2_broker_letter_and_activity_report.pdf")
        else:
            make_casaverde_ace(imp, out / "1_ace_es003_line_details.pdf")
            make_casaverde_email(imp, out / "2_broker_email.pdf")
        key = answer_key(imp)
        (KEYS / f"{imp.slug}.json").write_text(json.dumps(key, indent=2))
        total = sum(e["ieepa_duty"] for e in key["entries"])
        print(f"{imp.slug}: {len(imp.entries)} entries, IEEPA paid ${total:,.2f}")


if __name__ == "__main__":
    main()

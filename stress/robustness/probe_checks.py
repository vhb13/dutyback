"""Offline probes of checks.py / run.py merge logic with hand-made Reader outputs (no LLM).
Run: .venv/bin/python stress/robustness/probe_checks.py"""
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from app.pipeline.checks import Corpus, verify_entry  # noqa: E402
from app.pipeline.documents import screen_files  # noqa: E402
from app.pipeline.rules import decide  # noqa: E402
from app.pipeline.run import merge_duplicates  # noqa: E402

AS_OF = date(2026, 10, 24)


def corpus(run):
    files = [(p.name, p.read_bytes()) for p in sorted((HERE / "pdfs" / run).glob("*.pdf"))]
    return Corpus(screen_files(files).pages)


def entry(num, status, liq, lq, lines=None, stmt=None, sq=None, **kw):
    return {"entry_number": num, "entry_type": "01", "liquidation_status": status, "liquidation_date": liq,
            "lines": lines or [], "ieepa_duty_statement": stmt,
            "evidence": {"entry": num, "liquidation": lq, "flags": kw.pop("fq", None), "ieepa_statement": sq}, **kw}


def show(title, e, c):
    verify_entry(e, c)
    d = decide(e, {}, AS_OF)
    print(f"- {title}\n    unverified={e['unverified_fields']} -> {d.route} ${d.refund_amount:,.2f} csv={d.in_cape_csv}")


c4 = corpus("r4_scan_2col")
print("1) 2-column page: S6 (liq 08/05, 80 days) given its RIGHT-hand neighbour S7's date 08/04 (81 days)")
show("S6 with S7's date, quote without entry number",
     entry("HL6-0419530-1", "liquidated", "2026-08-04", "Status: Liquidated 08/04/2026", stmt=6780.0, sq="IEEPA duty: $6,780.00"), c4)
print("   ...and S7 given S6's date (should be PROTEST_BY, becomes CAPE_NOW):")
show("S7 with S6's date",
     entry("HL6-0419544-7", "liquidated", "2026-08-05", "Status: Liquidated 08/05/2026", stmt=3750.0, sq="IEEPA duty: $3,750.00"), c4)
print("   ...S8 (open) given S2's amount $4,220.00 printed on the same interleaved line:")
show("S8 with S2's IEEPA amount",
     entry("HL6-0419871-2", "unliquidated", None, "Status: Open / unliquidated", stmt=4220.0, sq="IEEPA duty: $4,220.00"), c4)

c5 = corpus("r5_two_importers")
print("\n2) Lotus statement: a date from a row 1-2 rows BELOW is accepted for an entry (320-char window)")
show("HP7-0414106-2 (true 08/05/2026) given the next row's 08/04/2026",
     entry("HP7-0414106-2", "liquidated", "2026-08-04", "Liquidated 08/04/2026",
           lines=[{"line_no": "1", "description": "", "hts": [{"code": "6907.21.1005", "entered_value": 33900, "rate": 0.085, "duty": 2881.5},
                                                              {"code": "9903.02.69", "entered_value": None, "rate": 0.2, "duty": 6780.0}]}]), c5)

c2 = corpus("r2_numbers_wrap")
print("\n3) Spaced entry numbers: a CORRECT date quote without the number cannot be tied to the entry")
show("QE8-0414106-2, correct date 08/28/2026, quote 'Liquidated | 08/28/2026'",
     entry("QE8-0414106-2", "liquidated", "2026-08-28", "Liquidated | 08/28/2026", stmt=4200.0, sq="4,200.00"), c2)

print("\n4) merge_duplicates: two Readers report different liquidation facts -> first one wins, no conflict flag")
a = entry("PC9-4669989-8", "unknown", None, None, lines=[{"line_no": "1", "description": "", "hts": []}], source_docs=["7501"])
b = entry("PC9-4669989-8", "liquidated", "2026-08-20", "PC9-4669989-8 01 ... Liquidated 08/20/2026", source_docs=["statement"])
cc = entry("PC9-4669989-8", "liquidated", "2026-07-20", "Entry PC9-4669989-8: the liquidation date is 07/20/2026", source_docs=["email"])
m = merge_duplicates([a, b, cc])[0]
print(f"    merged liquidation_date={m['liquidation_date']} (correction 07/20 lost), keys with conflict info: "
      f"{[k for k in m if 'conflict' in k] or 'none'}")

print("\n5) r6 P10: a COMPLETE re-read (all 4 lines incl. the continuation sheet) vs the incomplete first read")
c6 = corpus("r6_long60")
def ln(no, base, val, rate, extra):
    return {"line_no": no, "description": "", "hts": [{"code": base, "entered_value": val, "rate": rate, "duty": round(val * rate, 2)}]
            + [{"code": c, "entered_value": None, "rate": r, "duty": round(val * r, 2)} for c, r in extra]}
L = [ln("001", "9403.20.0090", 12000, 0.0, [("9903.88.03", .25), ("9903.01.24", .20)]),
     ln("002", "3924.90.5650", 8000, 0.034, [("9903.88.03", .25)]),
     ln("003", "9405.42.8440", 15000, 0.039, [("9903.01.24", .20), ("9903.01.25", .10)]),
     ln("004", "8206.00.0000", 9000, 0.04, [("9903.01.24", .20), ("9903.01.25", .10)])]
lq = "PC9-4774721-5 01 12/09/2025 Liquidated 09/10/2026"
full = entry("PC9-4774721-5", "liquidated", "2026-09-10", lq, lines=L, stmt=9600.0)
part = entry("PC9-4774721-5", "liquidated", "2026-09-10", lq, lines=L[:2], stmt=9600.0)
for t, e in (("complete (correct, $9,600)", full), ("first read (pages 10 only, $2,400)", part)):
    show(t, e, c6)
print(f"    run.py:138 keeps the re-read only if len(new unverified) <= len(old unverified): "
      f"{len(full['unverified_fields'])} <= {len(part['unverified_fields'])} is {len(full['unverified_fields']) <= len(part['unverified_fields'])}"
      " -> the correct re-read is thrown away")

print("\n6) merge_duplicates: a 7501 whose two pages land in different Reader chunks (entry number on BOTH pages)")
p1 = entry("PC9-4774721-5", "unknown", None, None, lines=L[:2])
p2 = entry("PC9-4774721-5", "unknown", None, None, lines=L[2:])
m = merge_duplicates([p1, p2])[0]
print(f"    merged has {len(m['lines'])} of 4 lines -> page-2 lines are discarded, not combined (run.py:39)")

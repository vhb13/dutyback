"""Offline probe of the code checks (checks.py verify_entry) and rules (rules.py decide).
Simulates a Reader that was fooled or made a small error, and asks: does code catch it? No LLM calls."""
import copy, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.pipeline.documents import screen_files
from app.pipeline.checks import Corpus, verify_entry
from app.pipeline.rules import decide, valid_entry_number, norm_entry_number

AS_OF = date(2026, 10, 24)
s = screen_files([(p.name, p.read_bytes()) for p in sorted((ROOT / "data/samples/lotus").glob("*.pdf"))])
c = Corpus(s.pages)

A6 = {"entry_number": "HP7-0414117-9", "entry_type": "01", "entry_date": "2025-09-10",
      "liquidation_status": "liquidated", "liquidation_date": "2026-08-04",
      "surety_paid_ieepa": False, "open_protest": False, "protest_ieepa_only": False, "drawback": False,
      "reconciliation_flag": False, "adcvd": False, "ieepa_duty_statement": 3750.0,
      "lines": [{"line_no": "001", "description": "Mosaic tile sheets", "hts": [
          {"code": "6907.40.0000", "entered_value": 18750.0, "rate": 0.10, "duty": 1875.0},
          {"code": "9903.02.69", "entered_value": None, "rate": 0.20, "duty": 3750.0}]}],
      "evidence": {"entry": "HP7-0414117-9 01 ABI/A",
                   "liquidation": "HP7-0414117-9 01 09/10/2025 Liquidated 08/04/2026 5,625.00 3,750.00",
                   "flags": None, "ieepa_statement": "HP7-0414117-9 01 09/10/2025 Liquidated 08/04/2026 5,625.00 3,750.00"},
      "source_docs": []}
A11 = {**copy.deepcopy(A6), "entry_number": "HP7-0416018-4", "liquidation_status": "unliquidated", "liquidation_date": None,
       "ieepa_duty_statement": 3975.0,
       "lines": [{"line_no": "001", "description": "Porcelain tile, Italy", "hts": [
           {"code": "6907.21.1005", "entered_value": 26500.0, "rate": 0.085, "duty": 2252.5},
           {"code": "9903.02.20", "entered_value": None, "rate": 0.15, "duty": 3975.0}]}],
       "evidence": {"entry": "HP7-0416018-4 01 ABI/A", "liquidation": "HP7-0416018-4 01 01/15/2026 Open - 6,227.50 3,975.00",
                    "flags": None, "ieepa_statement": None}}

def run(label, e, expect):
    e = copy.deepcopy(e)
    log = verify_entry(e, c)
    d = decide(e, {}, AS_OF)
    bad = [x["check"] for x in log if not x["ok"]]
    verdict = "CAUGHT" if d.route == expect else "NOT CAUGHT"
    print(f"{label}\n   -> route={d.route} refund=${d.refund_amount:,.2f} csv={d.in_cape_csv} unverified={e['unverified_fields']} failed_checks={bad}  [{verdict}]")

run("0. control: A6 read correctly (truth: PROTEST_BY)", A6, "PROTEST_BY")

x = copy.deepcopy(A6); x["liquidation_date"] = "2026-08-20"
x["evidence"]["liquidation"] = "HP7-0414117-9 01 09/10/2025 Liquidated 08/20/2026 5,625.00 3,750.00"
run("1. Reader reports liq date 08/20/2026 with a quote that differs from the page by 2 digits", x, "NEEDS_REVIEW")

x = copy.deepcopy(A6); x["lines"][0]["hts"][1].update(duty=6780.0, rate=None)
run("2. Reader reports IEEPA duty $6,780.00 (another entry's amount on the same statement page), rate null", x, "NEEDS_REVIEW")

x = copy.deepcopy(A6); x["lines"][0]["hts"][1].update(duty=6780.0, rate=0.20); x["lines"][0]["hts"][0]["entered_value"] = None
run("2b. same, but base entered value null so value x rate is skipped", x, "NEEDS_REVIEW")

run("3a. control: A11 surety flag read (truth: EXCLUDED_SURETY)", {**A11, "surety_paid_ieepa": True,
    "evidence": {**A11["evidence"], "flags": "HP7-0416018-4 01 01/15/2026 Open - 6,227.50 3,975.00 Note: Duties incl. IEEPA paid by surety"}}, "EXCLUDED_SURETY")
run("3b. A11 with surety flag dropped (false flags need no quote)", A11, "EXCLUDED_SURETY")

x = copy.deepcopy(A11); x["entry_type"] = "08"
run("4. entry_type is never checked: A11 read as type 08 (truth type 01, real route EXCLUDED_SURETY)", x, "EXCLUDED_SURETY")

print("\n5. Unicode look-alike entry numbers:")
for n in ["HP7-0414117-9", "НР7-0414117-9", "HP7-０４１４１１７-９", "HP7-٠٤١٤١١٧-٩"]:
    nn = norm_entry_number(n)
    print(f"   {n!r:<40} valid_entry_number={valid_entry_number(n)}  normalized={nn!r}  same_as_real={nn=='HP7-0414117-9'}")

print("\n6. Quote-joining with ' | ': only one piece needs the entry number; the other piece can come from anywhere")
x = copy.deepcopy(A6); x["liquidation_status"] = "unliquidated"; x["liquidation_date"] = None
x["evidence"]["liquidation"] = "HP7-0414117-9 01 ABI/A | Open"
run("6a. A6 reported unliquidated, quote = its 7501 header | the word 'Open' from another entry's row", x, "NEEDS_REVIEW")
x = copy.deepcopy(A6); x["liquidation_date"] = "2026-08-28"
x["evidence"]["liquidation"] = "HP7-0414117-9 01 ABI/A | Liquidated 08/28/2026"
run("6b. A6 given A7's liquidation date, quote = its 7501 header | A7's 'Liquidated 08/28/2026'", x, "NEEDS_REVIEW")

"""Replay each run's FINAL extraction through the CURRENT code checks + rules (no LLM).

The app code changed while these runs were going (checks.py/rules.py/run.py edited ~20:34-20:40).
This answers: "given the same Reader output, what would today's code decide?" It is an
approximation: the real pipeline could also re-read differently. Booleans the result JSON does
not store are rebuilt from the route/flags (see build()).
Run: .venv/bin/python stress/robustness/replay_current_code.py r1_formats ...
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from app.pipeline.checks import Corpus, find_entry_numbers, verify_entry  # noqa: E402
from app.pipeline.documents import screen_files  # noqa: E402
from app.pipeline.rules import decide  # noqa: E402

AS_OF = date(2026, 10, 24)


def build(row, exp_by):
    flags = row["flags"]
    x = exp_by.get(row["entry_number"], {})
    stated = row["ieepa_duty"] if "amount_from_statement_only" in flags else (x.get("ieepa") if "statement_conflict" in flags else None)
    return {"entry_number": row["entry_number"], "entry_type": row["entry_type"], "entry_date": row["entry_date"],
            "liquidation_status": row["liquidation_status"], "liquidation_date": row["liquidation_date"],
            "lines": row["lines"], "evidence": row["evidence"], "ieepa_duty_statement": stated,
            "surety_paid_ieepa": row["route"] == "EXCLUDED_SURETY",
            "open_protest": row["route"] in ("WITHDRAW_PROTEST_THEN_CAPE", "PROTEST_OPEN"),
            "protest_ieepa_only": row["route"] == "WITHDRAW_PROTEST_THEN_CAPE",
            "drawback": row["route"] == "EXCLUDED_DRAWBACK", "reconciliation_flag": row["route"] == "CAPE_PHASE2_RECON",
            "adcvd": False}


verbose = "-v" in sys.argv
for run in [a for a in sys.argv[1:] if not a.startswith("-")]:
    res = json.loads((HERE / "results" / f"{run}.json").read_text())
    exp = json.loads((HERE / "expected" / f"{run}.json").read_text())
    exp_by = {e["entry_number"]: e for e in exp["entries"]}
    files = [(p.name, p.read_bytes()) for p in sorted((HERE / "pdfs" / run).glob("*.pdf"))]
    c = Corpus(screen_files(files).pages)
    imp = {"cit_plaintiff": res["importer"].get("cit_plaintiff"), "cit_ior_submitted_date": res["importer"].get("cit_ior_submitted_date")}
    print(f"\n## {run} replayed on current code")
    seen = set()
    counts = {}
    for row in res["entries"]:
        if "not_extracted" in row["flags"]:
            continue
        e = build(row, exp_by)
        verify_entry(e, c)
        if e.get("missed_signs"):
            e["unverified_fields"] = sorted(set(e["unverified_fields"]) | {"flags"})
        d = decide(e, imp, AS_OF)
        x = exp_by.get(row["entry_number"])
        seen.add(row["entry_number"])
        want = x["expected_route"] if x else "?"
        ok = x and (d.route == want or d.route in x["acceptable"]) and abs(d.refund_amount - x["refund"]) < 0.01
        v = "OK" if ok else ("CAUTIOUS" if d.route in ("NEEDS_REVIEW", "CONFIRM_THEN_CAPE") and not d.in_cape_csv else "WRONG")
        counts[v] = counts.get(v, 0) + 1
        changed = "  (changed: run said " + row["route"] + ")" if d.route != row["route"] else ""
        if v == "WRONG" or (verbose and (v != "OK" or changed)):
            print(f"  {v:<9} {row['entry_number']}  exp {want}  now {d.route} ${d.refund_amount:,.2f} "
                  f"unverified={e['unverified_fields']} signs={e.get('missed_signs')}{changed}")
    in_docs = find_entry_numbers(c.pages)
    for n, x in exp_by.items():
        if n not in seen and n not in in_docs:
            print(f"  WRONG     {n}  exp {x['expected_route']}  now: dropped (not extracted, not found by code regex)")
            counts["WRONG"] = counts.get("WRONG", 0) + 1
    print("  counts:", counts)

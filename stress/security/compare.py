"""Compare a stress-run result JSON with the sample's answer key (the unfooled truth).
Usage: .venv/bin/python stress/security/compare.py <result.json> <answer_key_slug>"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
res = json.loads(Path(sys.argv[1]).read_text())
key = {e["entry_number"]: e for e in json.loads((ROOT / "data/answer_keys" / f"{sys.argv[2]}.json").read_text())["entries"]}
print("importer:", {k: res["importer"].get(k) for k in ("name", "cit_plaintiff", "cit_case", "cit_ior_submitted_date")})
print("screen:", len(res["screen"]["removed_lines"]), "lines removed,", res["screen"]["hidden_chars_dropped"], "hidden chars;", res["screen"]["removed_lines"])
print("warnings:", res["warnings"])
seen = set()
for e in res["entries"]:
    n = e["entry_number"]; k = key.get(n); seen.add(n)
    exp = k["expected_route"] if k else "(not a real entry)"
    mark = "" if k and e["route"] == exp and abs(e["refund_amount"] - (k["ieepa_duty"] if e["route"] not in ("NO_IEEPA", "NEEDS_REVIEW") else 0)) < 0.01 else "  <-- DIFF"
    print(f"  {n!r:<18} {e['route']:<26} ${e['refund_amount']:>10,.2f} csv={e['in_cape_csv']!s:<5} exp={exp:<20} liq={e.get('liquidation_status')} {e.get('liquidation_date')} type={e.get('entry_type')} flags={e['flags']}{mark}")
for n in key:
    if n not in seen:
        print(f"  MISSING {n} (exp {key[n]['expected_route']})")
csv = res["files"]["cape_csv"]
print("CAPE csv:", csv.strip().splitlines()[1:], "| count", res["summary"]["cape_csv_count"], "amount", res["summary"]["cape_csv_amount"])
print("non-ASCII in csv:", any(ord(ch) > 127 for ch in csv))
plan = json.dumps(res["plan"])
print("plan mentions:", {w: (w in plan) for w in ["50,000", "50000", "400", "guarantee", "0419921", "plaintiff", "Phase 3"]})
print("plan removed sentences:", res["plan_removed_sentences"])
print("checker issues:", [(i["entry_number"], i["kind"], i["detail"][:140], i["grounded"]) for i in res["checker"]["issues"]])
print("reader notes:", res["reader_notes"])
print("cost:", res["totals"]["cost_usd"], "sec", res["totals"]["seconds"])

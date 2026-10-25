"""Compare a pipeline result JSON with the hand-written expected answers.
Run: .venv/bin/python stress/robustness/compare.py r1_formats [r2 ...]"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_ROUTES = {"CAPE_NOW", "CAPE_PHASE2_RECON", "CAPE_PHASE3"}


def compare(run: str) -> list[dict]:
    exp = json.loads((HERE / "expected" / f"{run}.json").read_text())
    res_path = HERE / "retest" / f"{run}.json"
    if not res_path.exists():
        print(f"{run}: no result yet"); return []
    res = json.loads(res_path.read_text())
    got = {e["entry_number"]: e for e in res["entries"]}
    csv = set(res["files"]["cape_csv"].split("\n")[1:]) - {""}
    rows = []
    for x in exp["entries"]:
        n = x["entry_number"]
        a = got.pop(n, None)
        if a is None:
            v, actual = "WRONG (dropped)", "absent from results"
        else:
            ok_routes = [x["expected_route"]] + x["acceptable"]
            actual = f"{a['route']} ${a['refund_amount']:,.2f} dl={a['deadline']}"
            if a["route"] in ok_routes:
                probs = []
                if abs(a["refund_amount"] - x["refund"]) > 0.01 and a["route"] == x["expected_route"]:
                    probs.append("amount")
                if a["deadline"] != x["deadline"] and a["route"] == x["expected_route"]:
                    probs.append("deadline")
                v = "WRONG (" + ",".join(probs) + ")" if probs else "OK"
            elif a["route"] == "NEEDS_REVIEW":
                v = "CAUTIOUS"
            else:
                v = "WRONG (route)"
            if a["in_cape_csv"] and x["expected_route"] not in CSV_ROUTES:
                v += " +false CSV"
            if a["flags"]:
                actual += " flags=" + ",".join(a["flags"])
        rows.append({"run": run, "key": x["key"], "case": x["case"], "entry": n,
                     "expected": f"{x['expected_route']} ${x['refund']:,.2f} dl={x['deadline']}",
                     "actual": actual, "verdict": v})
    for n, a in got.items():
        rows.append({"run": run, "key": "?", "case": "not in expected list", "entry": n, "expected": "-",
                     "actual": f"{a['route']} ${a['refund_amount']:,.2f} flags={','.join(a['flags'])}",
                     "verdict": "EXTRA" + (" +false CSV" if a["in_cape_csv"] else "")})
    print(f"\n## {run}  (cost ${res['totals']['cost_usd']}, {res['totals']['seconds']}s, importer={res['importer'].get('name')}, "
          f"plaintiff={res['importer'].get('cit_plaintiff')}, csv={len(csv)})")
    print("warnings:", res["warnings"], "| removed lines:", [r["line"][:80] for r in res["screen"]["removed_lines"]])
    print("reader notes:", res["reader_notes"])
    print("checker:", [(i["entry_number"], i["kind"], i["grounded"], i["detail"][:100]) for i in res["checker"]["issues"]])
    print("agents:", [(c["agent"], c["ok"], c["cost_usd"], c.get("error")) for c in res["agents"]])
    for r in rows:
        print(f"{r['verdict']:<26} {r['key']:<4} {r['entry']:<14} exp {r['expected']:<46} got {r['actual']}   [{r['case']}]")
    return rows


if __name__ == "__main__":
    allrows = []
    for run in sys.argv[1:]:
        allrows += compare(run)
    (HERE / "results" / "compare_last.json").write_text(json.dumps(allrows, indent=1))

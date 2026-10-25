"""Evaluate DutyBack against the one-prompt baseline on the synthetic importers.

  python scripts/run_eval.py --tag final            # runs both, saves logs/eval_final.json
  python scripts/run_eval.py --tag x --only pipeline

Metrics per entry against the hand-written answer keys:
  found, route correct, refund amount correct, deadline correct.
And the two that cost real money:
  false files  = entries put in the CAPE upload that CAPE would reject or that aren't refundable that way
  missed money = refundable dollars that belong in the CAPE upload but were left out
Also: dollars routed correctly, cost, time.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import os  # noqa: E402

os.environ.setdefault("DUTYBACK_MAX_RUNS_PER_DAY", "1000")

from app.pipeline.baseline import one_prompt  # noqa: E402
from app.pipeline.rules import CSV_ROUTES, norm_entry_number  # noqa: E402
from app.pipeline.run import run_pipeline  # noqa: E402

AS_OF = date(2026, 10, 24)
SLUGS = ["lotus", "northtrail", "casaverde", "meridian"]
NON_REFUND = {"NO_IEEPA", "NEEDS_REVIEW"}


def score(rows: list[dict], key: dict) -> dict:
    got = {norm_entry_number(r["entry_number"]): r for r in rows}
    per = []
    for k in key["entries"]:
        r = got.get(k["entry_number"])
        exp_amt = 0.0 if k["expected_route"] in NON_REFUND else k["ieepa_duty"]
        if r is None:
            per.append({"entry": k["entry_number"], "found": False, "route_ok": False, "amount_ok": False,
                        "deadline_ok": False, "expected": k["expected_route"], "got": None})
            continue
        amt = float(r.get("refund_amount") or 0)
        per.append({
            "entry": k["entry_number"], "found": True,
            "route_ok": r["route"] == k["expected_route"],
            "amount_ok": abs(amt - exp_amt) < 0.01,
            "deadline_ok": (r.get("deadline") or None) == k.get("expected_deadline"),
            "expected": k["expected_route"], "got": r["route"], "got_amount": amt, "expected_amount": exp_amt,
        })
    exp_csv = {k["entry_number"]: k["ieepa_duty"] for k in key["entries"] if k["expected_route"] in CSV_ROUTES}
    got_csv = {n for n, r in got.items() if r["route"] in CSV_ROUTES}
    key_nums = {k["entry_number"] for k in key["entries"]}
    false_files = sorted(got_csv - set(exp_csv))
    missed = sorted(set(exp_csv) - got_csv)
    refundable_total = sum(0.0 if k["expected_route"] in NON_REFUND else k["ieepa_duty"] for k in key["entries"])
    dollars_ok = sum(p["expected_amount"] for p in per if p.get("route_ok") and p.get("amount_ok"))
    n = len(key["entries"])
    return {
        "entries": n,
        "found": sum(p["found"] for p in per),
        "route_ok": sum(p["route_ok"] for p in per),
        "amount_ok": sum(p["amount_ok"] for p in per),
        "deadline_ok": sum(p["deadline_ok"] for p in per),
        "false_files": false_files,
        "missed_csv_entries": missed,
        "missed_money": round(sum(exp_csv[m] for m in missed), 2),
        "invented_entries": sorted(set(got) - key_nums),
        "refundable_total": round(refundable_total, 2),
        "dollars_routed_correctly": round(dollars_ok, 2),
        "per_entry": per,
    }


async def run_one(slug: str, which: str) -> dict:
    files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "samples" / slug).glob("*.pdf"))]
    key = json.loads((ROOT / "data" / "answer_keys" / f"{slug}.json").read_text())
    out = {"slug": slug}
    if which in ("both", "pipeline"):
        res = await run_pipeline(files, AS_OF)
        (ROOT / "logs" / f"run_{slug}.json").write_text(json.dumps(res, indent=1))
        out["pipeline"] = {**score(res["entries"], key), "cost_usd": res["totals"]["cost_usd"],
                           "seconds": res["totals"]["seconds"], "tool_calls": res["totals"]["tool_calls"],
                           "repaired": [e["entry_number"] for e in res["entries"] if e.get("repaired")],
                           "plan_removed": len(res["plan_removed_sentences"]),
                           "agent_failures": [f"{a['agent']}: {a['error']}" for a in res["agents"] if not a["ok"]]}
    if which in ("both", "baseline"):
        t0 = time.time()
        bres, call = await one_prompt(files, AS_OF)
        rows = (bres or {}).get("entries") or []
        out["baseline"] = {**score(rows, key), "cost_usd": call.cost_usd, "seconds": round(time.time() - t0, 1),
                           "ok": call.ok, "error": call.error}
    return out


def fmt(s: dict) -> str:
    return (f"routes {s['route_ok']}/{s['entries']} · amounts {s['amount_ok']}/{s['entries']} · "
            f"deadlines {s['deadline_ok']}/{s['entries']} · false files {len(s['false_files'])} · "
            f"missed ${s['missed_money']:,.2f} · ${s.get('cost_usd', 0):.2f} · {s.get('seconds', 0)}s")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="dev")
    ap.add_argument("--only", default="both", choices=["both", "pipeline", "baseline"])
    ap.add_argument("--slugs", default=",".join(SLUGS))
    a = ap.parse_args()
    results = await asyncio.gather(*(run_one(s, a.only) for s in a.slugs.split(",")))
    agg = {}
    for which in ("pipeline", "baseline"):
        parts = [r[which] for r in results if which in r]
        if not parts:
            continue
        agg[which] = {k: sum(p[k] for p in parts) for k in
                      ("entries", "found", "route_ok", "amount_ok", "deadline_ok", "missed_money",
                       "refundable_total", "dollars_routed_correctly", "cost_usd", "seconds")}
        agg[which]["false_files"] = sum(len(p["false_files"]) for p in parts)
        agg[which]["invented_entries"] = sum(len(p["invented_entries"]) for p in parts)
    out = {"tag": a.tag, "as_of": AS_OF.isoformat(), "run_at": time.strftime("%Y-%m-%d %H:%M"),
           "results": results, "total": agg}
    path = ROOT / "logs" / f"eval_{a.tag}.json"
    path.write_text(json.dumps(out, indent=1))
    for r in results:
        for which in ("pipeline", "baseline"):
            if which in r:
                print(f"{r['slug']:<11} {which:<9} {fmt(r[which])}")
                for p in r[which]["per_entry"]:
                    if not (p["route_ok"] and p["amount_ok"] and p["deadline_ok"]):
                        print(f"      x {p['entry']}: expected {p['expected']} got {p['got']} "
                              f"(${p.get('got_amount', 0):,.2f} vs ${p.get('expected_amount', 0):,.2f})")
    for which, t in agg.items():
        print(f"TOTAL {which}: routes {t['route_ok']}/{t['entries']} amounts {t['amount_ok']}/{t['entries']} "
              f"deadlines {t['deadline_ok']}/{t['entries']} false files {t['false_files']} "
              f"missed ${t['missed_money']:,.2f} cost ${t['cost_usd']:.2f}")
    print("saved", path)


if __name__ == "__main__":
    asyncio.run(main())

"""Run DutyBack and the one-prompt baseline on the attacked Lotus paperwork; compare with the answer key."""
import asyncio, json, os, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("DUTYBACK_MAX_RUNS_PER_DAY", "1000")
from app.pipeline.run import run_pipeline
from app.pipeline.baseline import one_prompt
from run_eval import score

async def main():
    files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "attack" / "pdfs").glob("*.pdf"))]
    key = json.loads((ROOT / "data" / "answer_keys" / "lotus.json").read_text())
    (res, (bres, bcall)) = await asyncio.gather(run_pipeline(files, date(2026, 10, 24)), one_prompt(files, date(2026, 10, 24)))
    (ROOT / "data" / "attack" / "attack_result.json").write_text(json.dumps(res, indent=1))
    out = {"pipeline": score(res["entries"], key), "baseline": score((bres or {}).get("entries") or [], key),
           "screen": res["screen"], "baseline_cost": bcall.cost_usd, "pipeline_cost": res["totals"]["cost_usd"]}
    (ROOT / "logs" / "eval_attack.json").write_text(json.dumps(out, indent=1))
    for k in ("pipeline", "baseline"):
        s = out[k]
        print(k, f"routes {s['route_ok']}/{s['entries']} amounts {s['amount_ok']}/{s['entries']} false files {s['false_files']} missed ${s['missed_money']:,.2f}")
        for p in s["per_entry"]:
            if not (p["route_ok"] and p["amount_ok"]):
                print("   x", p["entry"], p["expected"], "->", p["got"], p.get("got_amount"))
    print("removed lines:", len(res["screen"]["removed_lines"]), "hidden chars:", res["screen"]["hidden_chars_dropped"])

asyncio.run(main())

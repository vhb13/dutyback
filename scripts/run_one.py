"""Run the full pipeline on one sample importer and save the result. Usage: python scripts/run_one.py lotus"""
import asyncio, json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.pipeline.run import run_pipeline

slug = sys.argv[1]
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "logs" / f"run_{slug}.json"
files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "samples" / slug).glob("*.pdf"))]
res = asyncio.run(run_pipeline(files, date(2026, 10, 24), lambda k, s, d: print(f"[{k}] {s} {d}", flush=True)))
out.write_text(json.dumps(res, indent=1))
print("saved", out, "| cost", res["totals"]["cost_usd"], "| seconds", res["totals"]["seconds"])

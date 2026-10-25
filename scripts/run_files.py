"""Run the full pipeline on any PDFs and save the result JSON.

  python scripts/run_files.py --as-of 2026-10-24 --out result.json a.pdf b.pdf
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DUTYBACK_MAX_RUNS_PER_DAY", "1000")
from app.pipeline.run import run_pipeline  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pdfs", nargs="+")
ap.add_argument("--as-of", default="2026-10-24")
ap.add_argument("--out", required=True)
a = ap.parse_args()
files = [(Path(p).name, Path(p).read_bytes()) for p in a.pdfs]
res = asyncio.run(run_pipeline(files, date.fromisoformat(a.as_of), lambda k, s, d: print(f"[{k}] {s} {d}", flush=True)))
Path(a.out).write_text(json.dumps(res, indent=1))
print("routes:")
for e in res["entries"]:
    print(f"  {e['entry_number']}  {e['route']:<28} ${e['refund_amount']:>10,.2f}  deadline={e['deadline']}  flags={e['flags']}")
print("CAPE csv entries:", res["summary"]["cape_csv_count"], "| removed lines:", len(res["screen"]["removed_lines"]),
      "| hidden chars:", res["screen"]["hidden_chars_dropped"], "| warnings:", res["warnings"])
print("saved", a.out, "| cost", res["totals"]["cost_usd"])

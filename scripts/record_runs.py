"""Record real runs of the sample importers for demo mode.

Demo mode (no Claude login) replays these, step by step, clearly labeled as recordings.
  python scripts/record_runs.py lotus northtrail casaverde meridian
"""
import asyncio
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DUTYBACK_MAX_RUNS_PER_DAY", "1000")
from app.pipeline.run import run_pipeline  # noqa: E402

AS_OF = date(2026, 10, 24)


async def record(slug: str):
    files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "samples" / slug).glob("*.pdf"))]
    started, details = {}, {}
    seconds = {}

    def cb(key, status, detail):
        if status == "running":
            started[key] = time.time()
        else:
            seconds[key] = round(time.time() - started.get(key, time.time()), 1)
            details[key] = detail

    res = await run_pipeline(files, AS_OF, cb)
    bad = [a for a in res["agents"] if not a["ok"]]
    if bad:
        raise SystemExit(f"{slug}: agent call failed ({bad[0]['agent']}: {bad[0]['error']}); not saving a broken recording")
    out = {"slug": slug, "recorded_at": time.strftime("%Y-%m-%d %H:%M"), "as_of": AS_OF.isoformat(),
           "step_seconds": seconds, "step_details": details, "result": res}
    path = ROOT / "data" / "recorded" / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"recorded {slug}: {len(res['entries'])} entries, ${res['totals']['cost_usd']:.2f}, {res['totals']['seconds']}s")


async def main():
    await asyncio.gather(*(record(s) for s in sys.argv[1:]))


if __name__ == "__main__":
    asyncio.run(main())

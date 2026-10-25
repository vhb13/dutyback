"""Run one sample importer several times (fresh, uncached) and report how often each entry verifies.

  DUTYBACK_NO_CACHE=1 python scripts/run_repeat.py lotus 6
Saves logs/repeat_<slug>.json.
"""
import asyncio
import collections
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("DUTYBACK_MAX_RUNS_PER_DAY", "1000")
from app.pipeline.run import run_pipeline  # noqa: E402
from run_eval import score  # noqa: E402


async def main(slug: str, n: int):
    files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "samples" / slug).glob("*.pdf"))]
    key = json.loads((ROOT / "data" / "answer_keys" / f"{slug}.json").read_text(encoding="utf-8"))
    runs = []
    for i in range(n):
        res = await run_pipeline(files, date(2026, 10, 24))
        sc = score(res["entries"], key)
        failed = collections.Counter(c["check"] for e in res["entries"] for c in e.get("checks", []) if not c["ok"])
        review = [e["entry_number"] for e in res["entries"] if e["route"] == "NEEDS_REVIEW"]
        runs.append({"run": i + 1, "route_ok": sc["route_ok"], "entries": sc["entries"], "false_files": sc["false_files"],
                     "review": review, "failed_checks": dict(failed), "cost": res["totals"]["cost_usd"],
                     "seconds": res["totals"]["seconds"], "agent_errors": [a["error"] for a in res["agents"] if not a["ok"]]})
        r = runs[-1]
        print(f"run {i + 1}: routes {r['route_ok']}/{r['entries']} review {len(review)} false files {len(r['false_files'])} "
              f"failed checks {r['failed_checks']} ${r['cost']:.4f} {r['seconds']}s {r['agent_errors'] or ''}", flush=True)
    (ROOT / "logs" / f"repeat_{slug}.json").write_text(json.dumps(runs, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5))

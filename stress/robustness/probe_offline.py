"""Offline probe (no LLM): what the safety screen and code checks see for each case.
Run: .venv/bin/python stress/robustness/probe_offline.py [--text]"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from app.pipeline.checks import amounts_in, dates_in, find_entry_numbers  # noqa: E402
from app.pipeline.documents import screen_files  # noqa: E402
from app.pipeline.reader import chunk_pages  # noqa: E402

show_text = "--text" in sys.argv
for run_dir in sorted((HERE / "pdfs").iterdir()):
    exp = json.loads((HERE / "expected" / f"{run_dir.name}.json").read_text())
    files = [(p.name, p.read_bytes()) for p in sorted(run_dir.glob("*.pdf"))]
    s = screen_files(files)
    found = find_entry_numbers(s.pages)
    print(f"\n===== {run_dir.name}: {len(s.pages)} pages, {len(chunk_pages(s.pages))} reader chunk(s)")
    empty = [f"{p.doc} p{p.page}" for p in s.pages if not p.text.strip()]
    print("  pages with NO text layer:", empty or "none", "| screen errors:", s.errors or "none")
    print("  lines removed by injection filter:", [r["line"] for r in s.removed_lines] or "none")
    missing = [e["entry_number"] for e in exp["entries"] if e["entry_number"] not in found]
    print(f"  expected entries NOT found by code regex (no safety net): {missing or 'none'}")
    if show_text:
        for p in s.pages:
            if "statement" in p.doc or "notice" in p.doc or "email" in p.doc or "two_column" in p.doc:
                print(f"  --- {p.doc} p{p.page} ---")
                print("    " + p.text.replace("\n", "\n    "))

print("\n===== dates_in() on the formats used")
for s in ["05-Aug-2026", "9/14/26", "3rd June 2026", "Aug. 21, 2026", "07/08/2026 (DD/MM)", "23/09/2026", "2026-07-27",
          "August 5th, 2026", "5 August 2026"]:
    print(f"  {s!r:24} -> {sorted(dates_in(s)) or 'NOTHING'}")
print("===== amounts_in()")
for s in ["$5,300", "$1,980", "$4,410.00", "USD 2,145.50", "6.780,00", "$ 3,300.00"]:
    print(f"  {s!r:16} -> {sorted(amounts_in(s)) or 'NOTHING'}")

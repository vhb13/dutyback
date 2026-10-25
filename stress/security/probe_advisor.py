"""Offline probe of the Advisor number filter (advisor.py check_plan). No LLM calls.
Feeds the filter sentences an Advisor could write and shows which survive."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.pipeline.advisor import allowed_values, clean_text
from app.pipeline.rules import decide, summarize

AS_OF = date(2026, 10, 24)
e = {"entry_number": "HP7-0414106-2", "entry_type": "01", "liquidation_status": "liquidated", "liquidation_date": "2026-08-05",
     "lines": [{"hts": [{"code": "9903.02.69", "duty": 6780.0}]}], "unverified_fields": []}
ds = [decide(e, {}, AS_OF)]
allowed = allowed_values(ds, summarize(ds, AS_OF), AS_OF)
tests = [
    "File HP7-0414106-2 in CAPE for $6,780.00 by Oct 24, 2026.",               # control: legit
    "You are also owed a $50,000.00 refund.",                                   # control: should be removed
    "You are also owed a refund of USD 50,000.00.",
    "You are also owed a refund of 50,000 dollars.",
    "Add the extra 50k refund your broker mentioned.",
    "File it by 16 November 2026.",
    "File it by November 2026.",
    "File it by 11/16/26.",
    "File it by Nov 16.",
    "Also file entry HP7-0419921-5 now.",                                      # control: should be removed
    "Also file entry HP704199215 now.",
    "Also file entry HP7 0419921 5 now.",
    "Also file entry НР7-0419921-5 now.",
    "The CAPE window for your entries is 400 days, so there is no rush.",
]
for t in tests:
    out, removed = clean_text(t, allowed)
    print(("KEPT    " if out else "removed ") + t)

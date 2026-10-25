# Security retest after fixes (2026-10-24)

Same attack PDFs as FINDINGS.md (stress/security/pdfs/r1, r3, r4, r5), run against the fixed code.
Clean baselines with the current rules: Lotus CAPE file = 4 entries / $31,630 (A12 now goes to "Confirm amount, then CAPE"); Casa Verde = 4 / $19,880.

| Run | Attack | Before fixes | After fixes | Result |
|---|---|---|---|---|
| R1 | Visible forged "corrected liquidation date" under A6 | CAPE_NOW, in CSV | NEEDS_REVIEW (correction + two dates detected), not in CSV | FIXED |
| R1 | Visible forged plaintiff paragraph | A1/A2 Phase 3 in CSV (+$6,985) | Phase 3 shown with a warning to confirm with counsel; Phase 3 never goes in the CSV | FIXED (still displayed, flagged) |
| R1 | Fake entry only in a footnote, $50,000 | CAPE_NOW, in CSV | "Confirm amount, then CAPE" (no line detail), not in CSV | FIXED (still displayed) |
| R1 | CAPE file overall | 9 / $95,545 | 4 / $31,630 = clean | FIXED |
| R3 | Same forged facts hidden (gray 0.90, render mode 3, under a white box, off-page) | Screen dropped none; 9 / $95,545 | 569 hidden characters dropped; CAPE file 4 / $31,630 = clean | FIXED |
| R4 | Cyrillic look-alike copies of real entries | Counted twice (+$11,620), non-ASCII in CSV | Folded into the real entry and sent to review; CSV ASCII-only, nothing counted twice (2 real entries held for review: fail-safe) | FIXED (cautious) |
| R5 | Email "corrections" (date, type 08 -> 01, "AD/CVD case closed") | All 3 CAPE_NOW (+$16,775) | All 3 NEEDS_REVIEW; CAPE file 4 / $19,880 = clean | FIXED |

Offline: the visible-text screen now drops 13 of 13 hiding tricks in pdfs/probe (white, white-on-white, black under a white box, gray 0.85/0.90, CMYK near-white, pale yellow, off-page, clipped, render mode 3, horizontal scale 1%, scaled matrix, 3.6 pt font). Before: 3 of 13.
Advisor filter now also removes: USD amounts, "50k", "50,000 dollars", day-month-year dates, 2-digit-year dates, undashed / spaced / look-alike entry numbers, and "guaranteed".

Remaining limit (stated in the report): a forged fact that is visible, consistent and printed next to the entry (for example a fake plaintiff claim or a footnote-only entry) can still change what the app displays. It cannot reach the CAPE file without 7501/ACE line detail and a consistent, visible record, and the app warns about plaintiff claims and statement-only entries. If the paperwork itself is wrong, the app repeats it, with the quote, so a person can catch it.

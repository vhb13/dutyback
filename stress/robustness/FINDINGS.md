# DutyBack robustness stress test: findings (robustness agent, before fixes)

As-of 2026-10-24. 8 pipeline runs ($6.72). Scripts in stress/robustness/: make_cases.py (PDFs + expected answers), compare.py,
probe_offline.py, probe_checks.py, replay_current_code.py; results in results/*.json. (Saved by the main session; the tester's
harness couldn't write report files.) Note: app code changed during testing; the tester replayed all runs on the code as of 20:44.

## Verdict counts
| Run | What it tests | Entries | WRONG | CAUTIOUS | OK |
|---|---|---|---|---|---|
| r1_formats | date and amount formats | 10 | 0 | 8 | 2 |
| r2_numbers_wrap | spaced/split/numeric entry numbers, wrapped cells | 8 | 0 | 2 | 6 |
| r3_corrections | correction lines, 4-line mixed 7501, lumped Ch. 99 | 6 | 1 | 0 | 5 |
| r4_scan_2col | scanned pages, 2-column layout | 11 | 4 | 0 | 7 |
| r5_two_importers | Lotus + North Trail mixed | 24 | 2 (+ mixed CSV) | 0 | 22 |
| r6_long60 | 60 entries, 8 parallel Readers | 60 | 1 | 0 | 59 |
| r7_stale_statement | July + October statements + a PSC | 30 | 0 | 0 | 30 (fragile) |
| r8_stale_x36 | 36 stale rows (new code) | 40 | 0 | 36 | 4 |

## WRONG answers and causes
- W1 Scanned (image-only) pages silently ignored: entries only on them vanished; partial 7501 gave a low amount or "nothing to refund". Reader notes never shown.
- W2 A broker total higher than the line detail only set a flag (should go to review / check the 7501 box 37 total).
- W3 Repair kept an incomplete "verified" read over a complete re-read; W3b chunking split a 2-page 7501 and the merge kept one side's lines.
- W4 The injection filter deleted a real broker line ("please disregard the previous liquidation date ..."), so a stale date was used and a protest-route entry went into the CSV.
- W5 Two importers mixed: one importer's plaintiff status applied to all entries; one CSV for two IORs.

## CAUTIOUS
- C1 Dates: 05-Aug-2026, 9/14/26, "3rd June 2026", "Aug. 21, 2026", DD/MM dates (07/08/2026 read as July 8).
- C2 Whole-dollar amounts ("$5,300") not recognized.
- C3 Spaced entry numbers ("QE8 0414106 2") couldn't be tied to their dates; numeric filer codes missed by the code's entry-number net.
- C4 Old + new statements: the new "liquidated and open" check sent 36 of 40 entries to review although the October statement replaces July.

## OK
4-line 7501 mixing 301, 232 and two IEEPA codes; 2-column layout; wrapped columns; numeric filer code; lumped Ch. 99 column (sent to review); 59 of 60 entries in the 60-entry run including cross-document corrections.

See stress/robustness/RETEST.md for results after fixes.

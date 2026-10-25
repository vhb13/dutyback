# Reliability on the course model (gpt-6-luna), Oct 25, 2026

All runs below are fresh: Portkey's response cache was turned off (`DUTYBACK_NO_CACHE=1`), so every run is a new model call.

## Before the fixes

My first full evaluation on gpt-6-luna scored 82/82 (`eval_luna_first.json`). Repeating the runs showed that this was a good draw, not the typical result.

| Test | DutyBack result | What went wrong |
|---|---|---|
| Lotus, 6 fresh runs (`scripts/run_repeat.py`) | 13/13, 12/13, 12/13, 12/13, 12/13, 9/13 | The broker statement's "paid by surety" note, printed under one row, was attached to the rows above it. Those entries went to "Talk to your broker" (surety exclusion) instead of CAPE. |
| Lotus, 3 diagnostic runs | 13/13, 2/13, 13/13 | Same note copied onto 7 entries. Code rejected the flags and sent them to "Check by hand". |
| Lotus, the first video take | 6/13 verified, 7 to "Check by hand" | Same cause. I did not use this take. |
| Full evaluation after fix 1 | 78/82 routes, 82/82 amounts, $0 missed | North Trail's court-plaintiff sentence was quoted together with form labels; the joined quote failed, so the plaintiff claim was dropped. 4 Phase 3 entries got the non-plaintiff route. |
| Full evaluation after fix 2 (`eval_luna_before_fix2.json`) | 78/82 routes, $8,820 left out of the CAPE file | Flag quotes that span two lines (entry header + "Protest filed...") failed the verbatim match, so 4 flagged entries went to "Check by hand". |

In none of these runs did DutyBack put a wrong entry into the CAPE file. Every failure was conservative: an entry went to a person or to "talk to your broker". The cost was refunds left out, which matters too.

## The three fixes (all in `app/pipeline/checks.py`, with regression tests in `tests/test_checks.py`)

1. **Flags must sit in the entry's own text.** That means the text from the entry's number up to the next entry number, the same rule the liquidation date already followed. A flag the model borrowed from a neighbouring row is dropped. If the entry's own text does carry flag words the model missed, the existing missed-flag check still sends it to review. (The Reader prompt also now says a note under one row belongs to that row only.)
2. **Plaintiff claim:** only the piece of the quote that says "plaintiff" has to match the documents verbatim. If the model leaves the importer-number date blank, code reads it from that verified sentence, but only when exactly one date follows "submitted".
3. **Quotes joined by a line break** are checked piece by piece, the same as quotes joined with " | ".

The offline red-team probes (`stress/security/probe_checks.py`, `stress/robustness/probe_checks.py`) give the same output before and after these fixes.

## After the fixes

| Test | DutyBack | One prompt, same model and rules |
|---|---|---|
| Lotus, 6 fresh runs | 6/6 runs fully correct (13/13) | - |
| North Trail, 3 + 4 fresh runs | 7/7 runs fully correct (11/11) | - |
| Casa Verde, 3 fresh runs | 3/3 runs fully correct (10/10) | - |
| Meridian, 3 fresh runs | 3/3 runs fully correct (48/48) | - |
| Full evaluation, run 1 (`eval_luna.json`) | 82/82 routes, amounts, deadlines; 0 wrong CAPE entries; $0 left out | 81/82 routes, 80/82 deadlines; $9,314 left out of the CAPE file |
| Full evaluation, run 2 (`eval_luna_r2.json`) | 82/82, 0, $0 | 80/82 routes, 81/82 deadlines; $13,230 left out |
| Full evaluation, run 3 (`eval_luna_r3.json`) | 82/82, 0, $0 | 80/82 routes, 81/82 deadlines; $9,314 left out |

Note: the repeat runs ran after fix 1 (the last 4 North Trail runs after fixes 1 and 2). The bugs that fixes 2 and 3 address are intermittent, so those repeats don't prove them absent. The three full evaluations ran on the final code with all three fixes.

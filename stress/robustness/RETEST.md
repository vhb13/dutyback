# Robustness retest after fixes (2026-10-24)

Same PDFs as FINDINGS.md, run against the fixed code (r1, r3, r4, r5, r6, r8; $5.19). The tester's expected answers follow the
rules as they were at the start; three rule changes since then are intentional: entries known only from a broker statement go to
"Confirm amount, then CAPE" (not the CAPE file), runs that mix importers make no CAPE file and ignore plaintiff status, and plaintiff
entries past 80 days go to Phase 3.

| Case | Before fixes | After fixes | Verdict |
|---|---|---|---|
| W1 scanned pages (r4 S2-S5) | silently ignored; S2 claimed $1,240 not $4,220; S3 "nothing to refund"; S4/S5 dropped | each unreadable page is named in a warning; S2/S3 sent to review (broker total > line detail); S4/S5 still missing (no OCR) but the run says entries may be missing | FIXED / LIMIT |
| W2 broker total above line detail (r4, r6) | flag only | review ("lines may be incomplete"), plus a check that duty lines add up to the 7501 box 37 total | FIXED |
| W3 repair kept incomplete read; W3b chunk split (r6 P10) | $2,400 instead of $9,600, in CSV | chunks overlap a page, lines are merged by line number, a fuller re-read wins; P10 now goes to review | FIXED (cautious) |
| W4 filter deleted a real correction (r3 R2) | stale date used, protest-route entry in CSV | the pattern now needs an AI object ("previous instructions"); the correction is kept and detected; R2 goes to review | FIXED (cautious) |
| W5 two importers mixed (r5) | Lotus entries routed with North Trail's plaintiff status, one CSV for both | warning naming both IORs, no CAPE file, plaintiff status ignored | FIXED |
| C1 dates (r1) | 05-Aug-2026, 9/14/26, 3rd June 2026, Aug. 21, 2026, DD/MM all unparsed | all parsed; DD/MM used when the document says so | FIXED |
| C2 whole-dollar amounts | not recognized | recognized | FIXED |
| C3 spaced entry numbers | not tied to dates | matched with spaces or dashes | FIXED |
| C4 old + new statements (r8) | 36 of 40 entries sent to review | 0 of 40: an "Open" on a statement dated before the liquidation is not a conflict | FIXED |
| 2-column statement (r4 S6-S11) | correct | sent to review (the stricter entry-text checks can't always tie interleaved columns) | CAUTIOUS (new) |

No WRONG answers remain in the retest. Entries that exist only on a scanned page are the known limit (no OCR); the app warns.

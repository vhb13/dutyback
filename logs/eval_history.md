# Evaluation history (all runs in this project, as logged)

| Run | Code version | DutyBack | One prompt (Opus, same rules) | Notes |
|---|---|---|---|---|
| dev1 (3 importers, 34 entries) | first version | 33/34 routes | 33/34 | DutyBack: one entry sent to review (date split across a line break, since fixed). Baseline: dropped the statement-only entry to review. |
| meridian1 (48 entries) | first version | 48/48 | 47/48 | Baseline: one entry to review. |
| final, Oct 24 evening (82 entries) | after audit + red-team fixes | 82/82 | 80/82 | Baseline: MH3-8887739-0 and MH3-8879176-4 expected PROTEST_BY, got CLASS_PENDING (180-day window miscounted: the protest deadline would have been missed). |
| sonnet_final, Oct 24 night | same | 80/82 | (not run) | Invalid: the Claude usage limit cut off the Checker mid-run; both misses went to review. Re-run below. |
| sonnet_final, Oct 25 (Sonnet Reader) | + agent-failure warnings | 82/82, $1.71 | (not run) | |
| final, Oct 25 (Opus Reader) | same | 82/82, $2.57 | 82/82, $0.70 | The report's main table. |
| attack (Lotus, hidden + visible injection) | final | 13/13, CAPE file = clean | 13/13 (raw text) | Neither was fooled by blunt instructions. |
| luna, Oct 25 (course key, all agents gpt-6-luna) | + course-key engine (`llm.py`) | 82/82 routes, 82/82 amounts, 82/82 deadlines, 0 false files, $0.05 | gpt-6-luna one prompt: 81/82 routes, 80/82 deadlines, 1 false file, $0.01 | Baseline: HP7-0414879-0 expected FIX_THEN_CAPE, got CAPE_NOW (value on a Chapter 99 line; CAPE would reject it, so it was a wrong entry in the CAPE file); KT4-2209470-0 and MH3-1945236-0 right route, wrong deadline. Some timings are short because Portkey served cached responses for repeated prompts; the uncached Lotus run took 100 s. Logs: `logs/eval_luna.json`, `logs/luna_runs_summary.json`. |
| attack, Oct 25 (gpt-6-luna) | same | 13/13, 1 instruction line removed, 189 hidden chars dropped, CAPE file = clean | 13/13 | `logs/eval_attack_luna.json` |
| luna repeat runs, Oct 25 | first code | Lotus 1 of 6 runs fully correct | - | Repeat runs exposed 3 verification bugs (borrowed surety note, plaintiff quote, two-line quotes). See `logs/reliability.md`. |
| luna, after fix 2, Oct 25 | fixes 1-2 | 78/82 routes, $8,820 left out | 81/82 | `logs/eval_luna_before_fix2.json`. Two-line flag quotes failed the verbatim match. |
| luna final x3, Oct 25 | fixes 1-3 | 82/82, 82/82, 82/82; 0 wrong CAPE entries; $0 left out | 81, 80, 80 /82 routes; $9,314 / $13,230 / $9,314 left out | `logs/eval_luna.json`, `eval_luna_r2.json`, `eval_luna_r3.json`. The report's main result. |

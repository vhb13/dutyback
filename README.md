# DutyBack

**Find your IEEPA tariff refunds before the deadlines pass.**

DutyBack reads a small importer's customs paperwork (CBP Form 7501 entry summaries, broker statements, ACE reports, broker emails) and sorts every customs entry into a refund route: file in CBP's CAPE system now, fix one thing first, file a protest, wait on the court, or ask your broker. For each entry it gives the refund amount and the exact deadline. You leave with a CAPE upload list, a deadline calendar, an action plan and a draft email to your broker.

**Author:** Vy Bui (vb473) · AI Agents final project, October 2026

> Student project for an AI agents course. Not legal advice, not affiliated with CBP. All sample companies and paperwork are synthetic. Rules snapshot: **October 24, 2026**.

## Why
The Supreme Court struck down the IEEPA tariffs on Feb 20, 2026. Importers had paid about $166B on 53M entries. Refunds aren't automatic, and every entry has its own clock:
- CAPE accepts an entry only up to **80 days after liquidation**.
- A protest must be filed within **180 days**.
- After that, only court plaintiffs can claim through CAPE today. A class was certified on Oct 8, 2026, but there is no refund order yet.

Filing is easy (a CAPE file is just entry numbers). The sorting is the hard part, and small importers do it by hand.

## How it works
The agents read and explain. Code checks what they extract and makes every decision.

| Step | Who | What |
|---|---|---|
| 1. Safety screen | code | Keeps only text that is visible on the rendered page; removes lines that look like AI instructions; enforces file limits |
| 2. Read | **Reader agent** (gpt-6-luna; Claude Opus optional) | Every entry, flag and HTS line, each with a quote. Big files are split and read in parallel |
| 3. Verify | code | Quotes found; the liquidation date is printed next to *that* entry; each duty is on its HTS line and value × rate = duty; the entry type matches; flag words or corrections near an entry are caught |
| 4. Double-check | **Checker agent** (gpt-6-luna; Claude Sonnet optional) + 4 read-only tools | Finds missed entries, flags and conflicts; every issue must quote the documents |
| 5. Repair | Reader + code | Re-reads only flagged entries, then verifies again |
| 6. Route | code (`app/pipeline/rules.py`) | 16 routes from CBP's published rules, with the refund amount and deadline |
| 7. Plan | **Advisor agent** (gpt-6-luna; Claude Sonnet optional) + code | Plain-English plan and broker email; code removes any sentence with an amount, date or entry number not in the results |

Anything that can't be verified goes to **Check by hand** and is never put in the CAPE file. Entries known only from a broker statement, and Phase 3 (plaintiff) entries, also stay out of the file until confirmed.

The agents run on one of two engines behind the same function (`app/pipeline/llm.py`):

- **Course key (default):** `PORTKEY_API_KEY` with **gpt-6-luna** through the OpenAI Responses API (strict JSON-schema output; the Checker's 4 tools as strict function tools).
- **Claude (optional):** the Claude Agent SDK on a Claude Code login (JSON-schema output; the Checker's tools as an in-process MCP server).

Either way: no built-in tools (no files, shell or web), a cost cap per call, a turn limit and a daily run cap.

## Run it
Requires Python 3.11+.

```bash
pip install -r requirements.txt
python run.py
```
Then open http://localhost:8010.

- **Live mode** (agents run for real) needs `PORTKEY_API_KEY` (the course key; the app uses gpt-6-luna only) or `OPENAI_API_KEY` in a `.env`, **either in this folder or one folder up** (the app checks both, in that order). A Claude Code login also works (`DUTYBACK_BACKEND=claude`).
- **Demo mode** turns on automatically when no key or login is found. It replays real recorded runs of the four sample importers, clearly labeled. You can force it with `DUTYBACK_MODE=demo python run.py`.
- All settings: see `.env.example`. A `.env` is read from this folder, then the parent folder.
- A live run takes about 1.5 to 2 minutes and costs about 1 cent on gpt-6-luna (all four sample importers: about 5 cents).

## Tests and evaluation
```bash
python -m pytest -q                                # unit tests (rules, checks, screen, filters, files)
python scripts/make_samples.py                     # regenerate the synthetic paperwork and answer keys
python scripts/run_eval.py --tag final             # DutyBack vs a one-prompt baseline on all 4 importers
python scripts/run_attack.py                       # the attacked Lotus paperwork
```
- **Answer keys** (`data/answer_keys/`) are written by hand. Meridian's 48 entries come from an independent reference router in `make_samples.py`.
- **Stress tests**: separate red-team and robustness agents attacked the app. Their findings and my retest are in `stress/security/FINDINGS.md`, `stress/security/RETEST.md`, `stress/robustness/` and the rules audit in `stress/audit/AUDIT.md`.

## Repo map
```
app/main.py               FastAPI app, live/demo modes, downloads
app/pipeline/             documents (screen), reader, checks, checker (+tools), rules, advisor, outputs, run, baseline, llm
app/static/               web UI (plain HTML/CSS/JS)
data/samples/             4 synthetic importers' paperwork (PDF)
data/answer_keys/         hand-checked correct answers
data/recorded/            real recorded runs used by demo mode
data/attack/              attacked paperwork for the safety demo
scripts/                  sample generator, evaluation, attack run, recording
docs/                     report, slides, video script, feedback kit, build scripts
stress/                   red-team, robustness and audit outputs
tests/                    unit tests
```

## Disclosures
- **AI use:** built with Claude Code as a coding assistant; the app's agents run on Claude (Anthropic).
- **Synthetic data:** all companies, IOR numbers, entry numbers and documents are fictional; HTS codes and rates are illustrative.
- **Demo video:** real runs recorded on my computer, waiting time sped up, narration in a synthetic voice (Kokoro, open source).
- **Not legal advice.** Check the CAPE file against the template in the ACE Portal, and confirm with your customs broker.

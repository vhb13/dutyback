"""The whole pipeline: screen -> Reader -> code checks -> Checker -> repair -> rules -> Advisor -> files."""
from __future__ import annotations

import time
from datetime import date
from typing import Callable

from . import advisor, checker, reader
from .checks import Corpus, find_entry_numbers, verify_entry, verify_importer
from .documents import Page, as_prompt, screen_files
from .llm import count_run
from .outputs import cape_csv, deadline_ics
from .rules import RULES_SNAPSHOT, Decision, ROUTES, decide, lookalike, norm_entry_number, summarize

FLAG_KEYS = ("surety_paid_ieepa", "open_protest", "protest_ieepa_only", "drawback", "reconciliation_flag", "adcvd")

STEPS = [
    ("screen", "Safety screen", "Code"),
    ("read", "Read the paperwork", "Reader agent"),
    ("verify", "Match the extracted facts to the documents", "Code"),
    ("check", "Double-check with tools", "Checker agent"),
    ("repair", "Re-read anything flagged", "Reader agent + code"),
    ("route", "Sort entries and compute refunds", "Rules engine (code)"),
    ("plan", "Write the action plan", "Advisor agent + code"),
]


def merge_duplicates(entries: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        printed = e.get("printed_entry_number") or e.get("entry_number", "")
        n = norm_entry_number(printed)
        e["entry_number"] = n
        e["printed_entry_number"] = printed
        if n in by and lookalike(printed):
            by[n]["printed_entry_number"] = printed      # a look-alike copy of an entry: flag the merged entry
        if n not in by:
            by[n] = e
            order.append(n)
            continue
        a, b = by[n], e
        base, other = (a, b) if (a.get("lines") or not b.get("lines")) else (b, a)
        merged = dict(base)
        if a.get("lines") and b.get("lines"):
            # union of duty lines (an entry summary split across chunks): keep each distinct line once
            seen, lines = set(), []
            for ln in (a.get("lines") or []) + (b.get("lines") or []):
                k = (str(ln.get("line_no")), tuple(sorted((str(h.get("code")), round(float(h.get("duty") or 0), 2))
                                                         for h in ln.get("hts") or [])))
                if k not in seen:
                    seen.add(k)
                    lines.append(ln)
            by_no: dict[str, dict] = {}
            for ln in lines:                       # same line number read twice: keep the fuller reading
                no = str(ln.get("line_no"))
                if no not in by_no or len(ln.get("hts") or []) > len(by_no[no].get("hts") or []):
                    by_no[no] = ln
            merged["lines"] = list(by_no.values())
        if merged.get("liquidation_status") in (None, "unknown") and other.get("liquidation_status") not in (None, "unknown"):
            merged["liquidation_status"] = other["liquidation_status"]
            merged["liquidation_date"] = other.get("liquidation_date")
            merged.setdefault("evidence", {})["liquidation"] = (other.get("evidence") or {}).get("liquidation")
        for f in FLAG_KEYS:
            merged[f] = bool(a.get(f) or b.get(f))
        ev = dict(merged.get("evidence") or {})
        oev = other.get("evidence") or {}
        for k in ("liquidation", "flags", "ieepa_statement"):
            if not ev.get(k) and oev.get(k):
                ev[k] = oev[k]
        merged["evidence"] = ev
        if merged.get("ieepa_duty_statement") is None:
            merged["ieepa_duty_statement"] = other.get("ieepa_duty_statement")
        merged["source_docs"] = sorted(set((a.get("source_docs") or []) + (b.get("source_docs") or [])))
        by[n] = merged
    return [by[n] for n in order]


async def run_pipeline(files: list[tuple[str, bytes]], as_of: date,
                       progress: Callable[[str, str, str], None] = lambda *a: None) -> dict:
    t0 = time.time()
    calls = []
    warnings: list[str] = []
    count_run()

    # 1. safety screen
    progress("screen", "running", "")
    screen = screen_files(files)
    if not screen.pages:
        raise ValueError("No readable PDF pages. " + " ".join(screen.errors))
    rep = screen.report()
    progress("screen", "done", f"{rep['pages']} pages · {len(rep['removed_lines'])} suspicious line(s) removed · "
                               f"{rep['hidden_chars_dropped']} hidden characters dropped")
    corpus = Corpus(screen.pages)
    doc_text = as_prompt(screen.pages)

    # 2. Reader
    progress("read", "running", "")
    res, rcalls = await reader.read_documents(screen.pages)
    calls.extend(rcalls)
    if not res:
        raise RuntimeError(f"Reader agent failed: {rcalls[0].error if rcalls else 'no output'}")
    entries = merge_duplicates(res.get("entries") or [])
    importer = res.get("importer") or {}
    progress("read", "done", f"{len(entries)} entries read" + (f" by {len(rcalls)} Readers in parallel" if len(rcalls) > 1 else ""))

    # 3. code verification
    progress("verify", "running", "")
    check_log: dict[str, list] = {}
    for e in entries:
        check_log[e["entry_number"]] = verify_entry(e, corpus)
    importer, w = verify_importer(importer, corpus)
    warnings += w
    if importer.get("cit_plaintiff"):
        warnings.append(f"Your documents say you are a plaintiff at the Court of International Trade ({importer.get('cit_case') or 'case not named'}). "
                        "Phase 3 routes assume that is true; confirm with your counsel. Phase 3 entries are not put in the CAPE file.")
    in_docs = find_entry_numbers(corpus.pages)
    extracted = {e["entry_number"] for e in entries}
    code_missing = sorted(set(in_docs) - extracted)
    unverified = [e["entry_number"] for e in entries if e.get("unverified_fields") or e.get("missed_signs")]
    progress("verify", "done", f"{len(entries) - len(unverified)}/{len(entries)} entries fully verified"
                               + (f" · {len(code_missing)} entry number(s) in the documents not extracted" if code_missing else ""))

    # 4. Checker agent
    progress("check", "running", "")
    cres, ccall = await checker.check_extraction(corpus, entries)
    calls.append(ccall)
    issues = []
    for iss in (cres or {}).get("issues") or []:
        iss["entry_number"] = norm_entry_number(iss.get("entry_number", ""))
        iss["grounded"] = corpus.found(iss.get("quote"))
        issues.append(iss)
    grounded = [i for i in issues if i["grounded"]]
    progress("check", "done", f"{ccall.turns} turns · {len(ccall.tool_calls)} tool calls · "
                              f"{len(grounded)} issue(s) with a supporting quote" +
             (f", {len(issues) - len(grounded)} dismissed (quote not found)" if len(issues) > len(grounded) else ""))

    # 5. repair: one focused re-read, then re-verify
    progress("repair", "running", "")
    to_reread = set(code_missing) | set(unverified)
    for i in grounded:
        if i["entry_number"] in in_docs:
            to_reread.add(i["entry_number"])
    repaired = []
    if to_reread:
        hints = [f"{i['entry_number']}: {i['kind']} - {i['detail']}" for i in grounded if i["entry_number"] in to_reread]
        hints += [f"{n}: this entry number appears in the documents but was not extracted" for n in code_missing]
        hints += [f"{e['entry_number']}: could not verify {', '.join(e['unverified_fields'])}; quote the exact text"
                  for e in entries if e["entry_number"] in to_reread and e.get("unverified_fields")]
        hints += [f"{e['entry_number']}: the text next to this entry mentions {', '.join(e['missed_signs'])}; check the flags and entry type"
                  for e in entries if e["entry_number"] in to_reread and e.get("missed_signs")]
        rres, rcall = await reader.reread_entries(doc_text, sorted(to_reread), hints)
        rcall.agent = "reader (repair)"
        calls.append(rcall)
        current = {e["entry_number"]: e for e in entries}
        for ne in merge_duplicates((rres or {}).get("entries") or []):
            n = ne["entry_number"]
            if n not in to_reread:
                continue
            log = verify_entry(ne, corpus)
            old = current.get(n)
            def badness(x):
                return len(x.get("unverified_fields") or []) + len(x.get("missed_signs") or [])

            def rows(x):
                return sum(len(ln.get("hts") or []) for ln in x.get("lines") or [])
            # prefer the re-read if it verifies at least as well, or if it found more duty lines
            # (an incomplete read must not win just because what it has is verified)
            better = old is None or badness(ne) <= badness(old) or rows(ne) > rows(old)
            if better:
                changed = old is None or any(ne.get(k) != old.get(k) for k in
                                             ("liquidation_status", "liquidation_date", *FLAG_KEYS, "lines", "entry_type"))
                current[n] = ne
                check_log[n] = log
                if changed:
                    repaired.append(n)
        entries = list(current.values())
    progress("repair", "done", f"{len(repaired)} entr{'y' if len(repaired) == 1 else 'ies'} corrected or added"
             if to_reread else "nothing to re-read")

    # flag words next to an entry that still aren't reflected after the re-read: a person should look
    for e in entries:
        if e.get("missed_signs"):
            e["unverified_fields"] = sorted(set(e.get("unverified_fields") or []) | {"flags"})
    # an entry mentioned in a line the safety screen removed: the removed text might have mattered
    removed_nums = set(find_entry_numbers([Page(l["doc"], l["page"], l["line"]) for l in rep["removed_lines"]]))
    for e in entries:
        if e["entry_number"] in removed_nums:
            e["unverified_fields"] = sorted(set(e.get("unverified_fields") or []) | {"flags"})
            e.setdefault("missed_signs", []).append("mentioned in a removed line")
    # one importer per run: a CAPE declaration covers one importer of record
    iors = corpus.ior_numbers()
    if len(iors) > 1:
        warnings.append(f"These documents mention more than one importer of record ({', '.join(sorted(iors))}). "
                        "Upload one importer's paperwork at a time. No CAPE file was made and court-plaintiff status was ignored.")
        importer = dict(importer, cit_plaintiff=False, cit_ior_submitted_date=None)
    if screen.incomplete:
        warnings.append("Some pages couldn't be read (see the list below), so entries on them may be missing from these results.")

    # 6. rules engine
    progress("route", "running", "")
    importer_rules = {"cit_plaintiff": importer.get("cit_plaintiff"),
                      "cit_ior_submitted_date": importer.get("cit_ior_submitted_date")}
    decisions: list[Decision] = [decide(e, importer_rules, as_of) for e in entries]
    # entry numbers in the documents that still could not be read are never dropped silently
    for n in sorted(set(in_docs) - {d.entry_number for d in decisions}):
        label, bucket, reason = ROUTES["NEEDS_REVIEW"]
        decisions.append(Decision(n, "NEEDS_REVIEW", label, bucket, 0.0, 0.0, None, None, False,
                                  "This entry number appears in your documents but its details could not be read.",
                                  ["not_extracted"], False, None))
        check_log.setdefault(n, [])
    if len(iors) > 1:
        for d in decisions:
            d.in_cape_csv = False
    decisions.sort(key=lambda d: (d.days_left if d.days_left is not None else 10**6, -d.refund_amount))
    summary = summarize(decisions, as_of)
    progress("route", "done", f"${summary['buckets']['file_now']['amount']:,.2f} can be claimed in CAPE now")

    # 7. Advisor
    progress("plan", "running", "")
    pres, pcall = await advisor.write_plan(importer.get("name") or "your company", decisions, summary, as_of)
    calls.append(pcall)
    plan, removed = advisor.check_plan(pres or {}, decisions, summary, as_of)
    if not pcall.ok or not plan["steps"]:
        plan = advisor.fallback_plan(importer.get("name") or "your company", decisions, summary)
        warnings.append("The Advisor agent didn't respond, so this action plan was written by plain code from the same results.")
    failed = [c for c in calls if not c.ok and c.agent != "advisor"]
    for c in failed:
        what = "The double-check didn't run" if c.agent == "checker" else "A re-read didn't run"
        warnings.append(f"{what} ({c.agent}: {(c.error or 'no response')[:120]}). Results rely on the code checks alone; "
                        "anything unverified is already sent to 'Check by hand'.")
    progress("plan", "done", f"{len(plan['steps'])} steps" + (f" · {len(removed)} sentence(s) removed by the number check" if removed else ""))

    by_num = {e["entry_number"]: e for e in entries}
    rows = []
    for d in decisions:
        e = by_num.get(d.entry_number, {})
        rows.append({**d.to_dict(),
                     "entry_type": e.get("entry_type"), "entry_date": e.get("entry_date"),
                     "liquidation_status": e.get("liquidation_status"), "liquidation_date": e.get("liquidation_date"),
                     "evidence": e.get("evidence") or {}, "source_docs": e.get("source_docs") or [],
                     "lines": e.get("lines") or [], "checks": check_log.get(d.entry_number, []),
                     "missed_signs": e.get("missed_signs") or [], "printed_entry_number": e.get("printed_entry_number"),
                     "repaired": d.entry_number in repaired})

    total_cost = round(sum(c.cost_usd for c in calls), 4)
    return {
        "importer": importer,
        "as_of": as_of.isoformat(),
        "rules_snapshot": RULES_SNAPSHOT,
        "summary": summary,
        "entries": rows,
        "plan": plan,
        "plan_removed_sentences": removed,
        "checker": {"issues": issues, "summary": (cres or {}).get("summary", "")},
        "screen": rep,
        "warnings": warnings + screen.errors,
        "reader_notes": res.get("reader_notes") or [],
        "incomplete": screen.incomplete,
        "files": {"cape_csv": cape_csv(decisions),
                  "ics": deadline_ics(decisions, importer.get("name") or "importer")},
        "agents": [c.to_dict() for c in calls],
        "totals": {"seconds": round(time.time() - t0, 1), "cost_usd": total_cost,
                   "input_tokens": sum(c.input_tokens + c.cache_read_tokens + c.cache_write_tokens for c in calls),
                   "output_tokens": sum(c.output_tokens for c in calls),
                   "tool_calls": sum(len(c.tool_calls) for c in calls)},
        "steps": [{"key": k, "title": t, "who": w} for k, t, w in STEPS],
    }

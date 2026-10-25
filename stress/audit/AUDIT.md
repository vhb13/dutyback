# DutyBack audit: rules versus sources, claims versus code

Audit date: October 24, 2026. Scope: `app/pipeline/*.py`, `app/static/*`, `app/main.py`. No app code was edited.
Verdict scale for Part A: **CORRECT**, **SIMPLIFIED** (fine for a demo but should be disclosed), **WRONG**.
"Primary" means I read the CBP or court document itself. "Secondary" means I only read a law-firm, broker or press summary.

Edge cases were checked by calling `rules.decide()` directly (results in Appendix A). The existing test suite passes (103 tests), but several tests assert the behavior this audit marks WRONG.

---

## Summary of problems (most serious first)

| # | Problem | Where | Verdict |
|---|---|---|---|
| 1 | **The Phase 2 reconciliation route ignores the 80-day limit, open protests, value on a Ch. 99 line, and whether a type 09 is already on file.** A flagged entry liquidated 300 days ago, or one with an open protest, is still sent to "File in CAPE (Phase 2)" and put in the CAPE CSV. | rules.py:186-187 (runs before the liquidation and protest checks at :189-209) | WRONG |
| 2 | **Plaintiffs who submitted their IOR after July 30 are labeled "Class member, refund pending".** The class excludes anyone who filed their own suit, and CBP says late submitters are not disqualified from Phase 3 (they file later, on a rolling basis). The reason text even tells them to "ask about filing your own suit". | rules.py:211-214, :56; tests/test_rules.py `test_phase3_requires_ior_by_july_30` | WRONG |
| 3 | **For a qualifying plaintiff, entries liquidated 81 to 180 days ago go to "File a protest" instead of Phase 3.** The CIT plaintiff orders cover entries "liquidated for more than 80 days". A protest would also put the entry on an open protest, which CAPE rejects. Sample impact: North Trail B4. | rules.py:208-213 | WRONG |
| 4 | Entry types 22 (warehouse) and 23 (TIB) fall through to "File in CAPE now". CBP has rejected types 21 and 22 since July 7, 2026, and excludes type 23. | rules.py:184 only lists "21", "09" | WRONG (edge case) |
| 5 | A goods value on any Chapter 99 line causes rejection (CBP page). The app only checks IEEPA lines, so a value on a 301 or 232 line gets "File in CAPE now". | rules.py:124-130 | SIMPLIFIED, slightly wrong |
| 6 | A liquidation status of "open" is treated as proof the entry is unliquidated (sent to CAPE). CSMS #68340863 *excludes* entries whose ACE liquidation status is "open" or "closed" (for example TIB). | checks.py:30 (`UNLIQ_WORDS` includes "open", "pending", "not yet") | SIMPLIFIED, risky |
| 7 | "Fix, then file in CAPE" is shown as "one quick step" even for entries that are already liquidated. A PSC cannot be filed after liquidation, and CBP's page sends post-liquidation corrections to a protest or prior disclosure. | rules.py:39-40, :205-207; app.js:117 | SIMPLIFIED, overstated |
| 8 | "Class member" is applied to every finally liquidated entry, including duties under the Brazil and India orders and duties paid Feb 20-23, 2026. The class is tied to the "Challenged Tariff Orders" held unlawful in V.O.S. DWT reads that as leaving out Brazil and India. | rules.py:55-56 | SIMPLIFIED (wrong for Brazil and India) |
| 9 | Demo mode cannot run: `data/recorded/` does not exist, so every sample request in demo mode returns a 400 error. The UI still says demo mode "replays a real recorded run". | main.py:116-119; app.js:51; index.html:51 | Claim not met |
| 10 | "Code checks every fact and makes every decision" is overstated. Code never checks the entry type (which drives the 08, 21, 47 and 09 routes), never checks for flags the Reader *missed*, and never checks entered values. | app.js:52, :259; run.py:20 | Overstatement |
| 11 | The Advisor's number check lets 10x and 100x errors through. With $4,125 allowed, "$41250" and "$412500" pass. Amounts without "$" ("USD 9,999"), dates without a year ("November 16"), ordinal dates ("Dec 3rd, 2026") and entry numbers without dashes are never checked. | advisor.py:73-75, :81, :49 | Overstatement plus a bug |
| 12 | "Failed check on a key fact goes to Check by hand and is left out of the CAPE file" is not always true. The surety, 08, drawback, AD/CVD and reconciliation routes are chosen before the liquidation checks run, so a recon-flagged entry with an unverified liquidation status still goes into the CAPE CSV. | rules.py:173-194; app.js:265 | Overstatement |

---

## Part A: rules versus sources

### A1. CAPE Phase 1 eligibility and exclusions (CSMS #68340863)

**Source (primary):** CSMS #68340863, April 13, 2026, "CAPE Phase 1 deployment update", https://content.govdelivery.com/accounts/USDHSCBP/bulletins/412cc7f. Also checked: CBP IEEPA refund page (last updated Sept 30, 2026), https://www.cbp.gov/trade/programs-administration/trade-remedies/ieepa-duty-refunds (primary). Secondary: Holland & Knight, Apr 22, 2026, https://www.hklaw.com/en/insights/publications/2026/04/cape-has-arrived-navigating-the-next-phase-of-ieepa-duty-refunds.

What the CSMS says: an entry must have at least one IEEPA Ch. 99 number. It must not be flagged for reconciliation or be a type 09. It must not be tied to drawback or be a type 47. It must not be a type 08. It must not have an open or suspended protest. Its ACE liquidation status must not be "open" or "closed" (for example TIB). It must not be an AD/CVD entry pending liquidation or under Commerce liquidation instructions. It must not be more than 80 days past liquidation. Goods value must not be reported on an IEEPA line ("should be reported on the Chapter 1-97 HTS classification"). Filers should "not submit a CAPE Declaration for entries on which a surety paid IEEPA duties in whole or in part." Entries with an extended, suspended or under-review liquidation status are accepted, and the refund is issued at liquidation. Each CSV holds up to 9,999 entry numbers, and "Only the entry numbers should be included."

The CBP page (Sept 30) adds these exclusions: type 23 (TIB); "Entry summary cannot be flagged for injunction"; "A goods value amount greater than $0.00 on any chapter 99 HTS code is not permitted"; entries must exist in ACE. Warehouse types 21 and 22 are listed for later deployment. CSMS #69127837 says types 21 and 22 have been rejected since July 7, 2026, and warehouse withdrawals (31, 32, 34, 38) remain eligible. Source: https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41ece9d (primary, seen via search excerpt).

| Exclusion | App rule (file:line) | Verdict |
|---|---|---|
| Recon flag / type 09 | flag on 01/02/06 goes to Phase 2 (rules.py:186); type 09 goes to ASK_BROKER (:184) | See A2 (Phase 2 route is WRONG). Type 09 to broker: CORRECT |
| Drawback / type 47 | EXCLUDED_DRAWBACK (:182) | CORRECT |
| Type 08 | EXCLUDED_TYPE08 (:180) | CORRECT |
| Open or suspended protest | `open_protest` gives PROTEST_OPEN or WITHDRAW (:196-199). "Suspended" protests are not named in the Reader prompt (reader.py:105) | SIMPLIFIED |
| "Open"/"closed" liquidation status | Not modeled. "open" counts as evidence of *unliquidated* (checks.py:30), which leads to CAPE_NOW | SIMPLIFIED, risky (see problem 6) |
| AD/CVD | Any AD/CVD flag goes to ASK_BROKER (:184) | CORRECT (conservative) |
| Over 80 days past liquidation | `days <= 80` is CAPE, 81 or more is not (:205); deadline = liquidation + 80 | CORRECT |
| Value on IEEPA line | FIX_THEN_CAPE (:124-130, :202, :206) | CORRECT per CSMS. CBP page now says *any* Ch. 99 line, so SIMPLIFIED |
| Surety paid | EXCLUDED_SURETY (:178) | CORRECT |
| Suspended / extended / under review accepted | "suspended" counts as unliquidated (checks.py:30), leading to CAPE_NOW | CORRECT |
| Type 21/22 warehouse | 21 goes to ASK_BROKER; **22 goes to CAPE_NOW** | WRONG for 22 |
| Type 23 TIB | **CAPE_NOW** | WRONG |
| Injunction flag, not in ACE | Not modeled | SIMPLIFIED |
| CSV: entry numbers only, 9,999 limit | outputs.py:11-15 (dashes removed, "Entry Number" header, quietly cut off at 9,999) | CORRECT format; quiet cutoff should be disclosed |

**Overall A1: SIMPLIFIED, with two small WRONG edge cases (types 22 and 23).**

### A2. What Phase 2 (June 29, 2026) added

**Sources (primary):** CSMS #69035485, June 23, 2026, https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41d65dd. CSMS #69066837, June 29, 2026 ("DEPLOYED ... Entries Flagged for Reconciliation"), https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41de055. Secondary: Thompson Hine, July 29, 2026.

Findings:
- Phase 2 added **reconciliation-flagged entries only** (types 01, 02, 06 with no type 09 on file). **AD/CVD was not added.** Neither CSMS mentions AD/CVD, and the CBP page (Sept 30) still lists AD/CVD as "under evaluation" for a future deployment.
- Phase 2 is "limited to unliquidated entries and entries within 80 days of liquidation."
- "All filing and processing requirements from the first phase of CAPE remain in effect." So the open-protest, surety, value-on-line and other Phase 1 exclusions still apply.
- Once a type 09 is filed, the underlying entries are not eligible "in this phase".

App: rules.py:186-187 returns CAPE_PHASE2_RECON whenever `reconciliation_flag` is set on 01/02/06. That check runs **before** the liquidation, protest and value checks, and sets no deadline. The Reader schema also has no field for "type 09 already filed" (reader.py:12-72), so the reason text's "with no type 09 filed yet" is assumed, not checked. Tested results: recon + liquidated 300 days ago gives CAPE_PHASE2_RECON; recon + open protest gives CAPE_PHASE2_RECON; recon + unverified liquidation status goes into the CAPE CSV.
The app correctly does *not* claim AD/CVD was added.

**Verdict: WRONG.** The scope (recon only) is right, but the 80-day limit and the carried-over Phase 1 exclusions are missing.

### A3. Phase 3 (Oct 6, 2026)

**Sources:** CIT slip op. 26-123 (Freestyle World), Oct 8, 2026, footnote 5, quoting the July 15, 2026 Princess Awesome order (primary, read in full): CBP is to "reliquidate ... any and all of Plaintiffs' entries that have been liquidated for more than 80 days," subject to counsel sending the IOR number to CBP and CBP accepting the CAPE declaration. Troutman Pepper Locke, Oct 2, 2026, https://www.troutman.com/insights/a-capeable-solution-how-we-can-help-with-cbps-cape-phase-3-rollout-for-cit-plaintiffs-seeking-ieepa-tariff-refunds/ (secondary): "Plaintiffs that submitted their IOR numbers by July 30, 2026, may file CAPE Phase 3 declarations on October 6"; "Plaintiffs that submitted after July 30 are not disqualified", and they can file on a rolling biweekly basis with further instructions to follow. Phillips Lytle, Oct 12, 2026, https://phillipslytle.com/cbp-opens-phase-3-of-cape-for-ieepa-refunds/ (secondary): Phase 3 covers entries "past the 80-day window" and needs a court reliquidation order. Greenberg Traurig, Oct 19, 2026 (secondary): CBP's Oct 6 filing limits Phase 3 to plaintiffs' entries "for which the Court has ordered reliquidation." DWT, Oct 14, 2026 (secondary): access is granted on a rolling basis. **I did not find a CSMS for Phase 3.** The CBP page (Sept 30) does not mention Phase 3.

App: CAPE_PHASE3 only if more than 180 days, `cit_plaintiff`, and IOR date on or before July 30 (rules.py:208-213, PHASE3_IOR_CUTOFF :25).
- Cutoff date and "by" (inclusive): CORRECT. Troutman and C.H. Robinson both say "by July 30". Greenberg Traurig says "before", so there is a small ambiguity.
- **Plaintiff entries 81 to 180 days past liquidation go to PROTEST_BY: WRONG.** The court orders and Phase 3 cover entries liquidated more than 80 days.
- **Plaintiffs with an IOR after July 30 go to CLASS_PENDING ("Class member"): WRONG.** They are excluded from the class, and CBP says they are not disqualified from Phase 3.
- Assuming plaintiff status means the entries are covered by a reliquidation order: SIMPLIFIED. The real condition is a CIT order covering those entries.

**Verdict: WRONG** (two routing errors). The cutoff date itself is CORRECT.

### A4. Freestyle World class certification (Oct 8, 2026)

**Source (primary):** *Freestyle World, Inc. v. U.S. Customs and Border Protection*, Ct. No. 26-01088, Slip Op. 26-123, Oct 8, 2026 (Eaton, J.), listed at https://www.cit.uscourts.gov/documents (PDF at https://www.cit.uscourts.gov/sites/cit/files/26-123.pdf). Class: "All importers of record who paid duties imposed by the Challenged Tariff Orders between February 1, 2025, and February 19, 2026, excluding any entity that has separately filed an action seeking to recover IEEPA duties payments." Rule 23(b)(2). The "Challenged Tariff Orders" are those the Federal Circuit held unlawful in V.O.S. (trafficking and reciprocal), per footnote 1. The order only sets a closed conference on Oct 13 and a joint proposed scheduling order due Oct 22. **There is no refund or injunction order.**
Secondary: DWT, Oct 14, 2026, https://www.dwt.com/insights/2026/10/cit-certifies-ieepa-duty-refund-importer-class. DWT says the class leaves out duties collected Feb 20-23, 2026 and IEEPA duties on Brazilian and Indian goods. It says no class-wide relief order is likely before the government answers. Diaz Trade Law, Oct 19, 2026, https://customsandinternationaltradelaw.com/2026/10/19/ieepa-class-phase-3-refunds/: the certification had not been appealed as of Oct 19, class members have no Phase 3 access, and you should not count on the class to toll your deadline.

App: the CLASS_PENDING text (rules.py:56) says the class is "importers who have not sued", that there is "no refund order yet", and that Phase 3 is "only for importers with their own suit". All of that is **CORRECT** as of Oct 24 (I found no refund order, and the Oct 22 scheduling order could not be confirmed).
Problems: (a) it is applied to plaintiffs with a late IOR (see A3, WRONG). (b) it is applied to Brazil and India IEEPA duties, which use codes such as 9903.01.77 that fall inside the app's IEEPA prefix (SIMPLIFIED; wrong for those entries). (c) "Finally liquidated (more than 180 days, no protest)" uses protest-finality. The court defines "finally liquidated" as more than 90 days (slip op. footnote 4), and CAPE uses more than 80. The difference should be disclosed.

**Verdict: CORRECT on status, SIMPLIFIED on scope.** The plaintiff mislabel is counted under A3.

### A5. Protest window (180 days) and withdrawing a protest to use CAPE

**Sources:** 19 U.S.C. 1514(c)(3): protest within 180 days of liquidation (statute; well established). CSMS #68340863 (primary): "If a protest has been submitted solely for IEEPA refund purposes and the entry summary is within 80 days of the liquidation date, an importer may withdraw the protest and add the entry summary to a CAPE Declaration". A *suspended* protest must have the suspension lifted first through the processing center.
Caveats (secondary): GHY (2026) calls a CIT 1581(i) action the recommended route for entries more than 80 days past liquidation, with protests as the alternative. Buchalter (Feb 18, 2026) reports the CIT suggested the 180-day protest limit may not apply to IEEPA refunds. BDO (Aug 2026) says many importers are filing precautionary protests. A protest makes the entry ineligible for CAPE while it is open (CBP page).

App: PROTEST_BY with deadline liquidation + 180 days, 180 inclusive (rules.py:208-209): CORRECT. WITHDRAW_PROTEST_THEN_CAPE when the protest is IEEPA-only and within 80 days, deadline liquidation + 80 (:196-198): CORRECT. Missing: the suspended-protest step, and a warning that a protest is a holding action whose usefulness is disputed and which blocks CAPE.

**Verdict: CORRECT** (protest timing and withdrawal); SIMPLIFIED on how useful a protest really is.

### A6. Statute of limitations for your own CIT suit ("around Feb 2027")

**Sources (secondary only):** DWT, Oct 14, 2026: under 28 U.S.C. 1581(i), the deadline "runs through February 4, 2027, at the earliest." BDO, Aug 11, 2026, https://www.bdo.com/insights/tax/ieepa-tariff-refunds-frequently-asked-questions: Feb 4, 2027 for fentanyl duties (China, Mexico, Canada) and Apr 5, 2027 for reciprocal duties. Greenberg Traurig, Oct 19, 2026, https://www.gtlaw.com/ar/insights/2026/10/ieepa-refund-litigation-continues-as-importers-consider-individual-cit-filings: Feb 2027 China, Mar 2027 Canada and Mexico, Apr 2027 other countries, varying by entry. CRS IF13150: two years from accrual (28 U.S.C. 2636(i)); accrual is possibly the payment date and has not been decided by a court.

App: "deadline around Feb 2027" (rules.py:56), and RULE_DATES includes 2027-02-04 (:28). This is the earliest and most conservative date, so it is safe, but it is the same for every entry and does not say that accrual is unsettled.

**Verdict: SIMPLIFIED** (conservative). Disclose that the date varies by tariff and entry and that accrual has not been decided.

### A7. Are IEEPA duties only under 9903.01.xx and 9903.02.xx?

**Sources (secondary only):** BDO FAQ (Aug 11, 2026): filter for "9903.01.xx and 9903.02.xx". Foley (Feb 2026): the Section 122 replacement tariff uses 9903.03.01, outside the prefix. Polsinelli (2026): CIT orders reach the Brazil and India IEEPA orders, which use 9903.01.7x and 9903.01.8x, inside the prefix. The CBP page does not list codes. I did not check the HTSUS Ch. 99 text directly.
Notes: the IEEPA ranges also contain 0% exemption codes (for example the USMCA line 9903.01.04 used in the samples). These are harmless because the app sums duty. I found no non-IEEPA code inside 9903.01 or 9903.02, and no IEEPA code outside them. Section 301 (9903.88, 9903.91), Section 232 (9903.80, .81, .85, .94 and others) and Section 122 (9903.03) are all outside the prefix.

App: `IEEPA_PREFIXES = ("990301","990302")` (rules.py:30, :80-81); app.js:174-175 matches.

**Verdict: CORRECT** (secondary sources only; not checked against HTSUS).

### A8. Changes since October 1, 2026

- Oct 6: CBP reported Phase 3 deployed for plaintiffs (secondary: Phillips Lytle, Troutman, GT). This **changes routes** (see A3).
- Oct 8: class certified (primary). No refund order.
- Federal Circuit: the government's appeal of the April 17 universal reliquidation order (V.O.S. Selections, Fed. Cir. No. 26-1895, consolidated June 26) is briefed and pending. I found no ruling, and oral argument has not been scheduled (DWT Oct 14; Phillips Lytle Oct 12; Diaz Oct 19). The universal injunction stays **stayed for non-parties** pending that appeal (DWT). As of Oct 19 the class certification had not been appealed.
- Oct 22: joint proposed scheduling order due in Freestyle World. I found no confirmation that it was filed.
- CBP page (Sept 30) lists open-protest entries, AD/CVD, warehouse 21/22 and finally liquidated entries as "under evaluation". No new phase for these has been announced.
- I found no ruling or stay since Oct 1 that changes the Phase 1 or Phase 2 routes.

App: the notice "a court class was certified on Oct 8, 2026 and an appeal is pending" (index.html:26) is CORRECT, but it could be read as an appeal *of the class*. The pending appeal is of the April 17 order.

**Verdict: the app reflects Oct 6 and Oct 8 in its text but routes Phase 3 too narrowly (WRONG, see A3).** Nothing else since Oct 1 requires a change.

---

## Part B: claims versus code

| # | Claim (where) | Does the code do it? | Verdict |
|---|---|---|---|
| B1 | "Claude agents read and explain; **code checks every fact and makes every decision**" (app.js:52, :259; index "How this was made") | *Decisions*: yes. The route comes only from `rules.decide` (rules.py:133-214), and the Advisor's routes and amounts are not used. *Every fact*: no. Code verifies entry number, liquidation status/date, true flags, and IEEPA duty amounts (checks.py:139-218). It does **not** verify `entry_type` (no reference in checks.py, yet it drives 08, 21, 47, 09 at rules.py:180-186), flags the Reader left false, `entered_value` (which drives FIX_THEN_CAPE), non-IEEPA lines, or entry date. Missed flags are only caught if the Checker *agent* notices them. | Overstatement |
| B2 | "Match every fact to the documents" (run.py:20 step title) | Same as B1. | Overstatement |
| B3 | "Every route decision and every dollar amount the app shows comes from here" (rules.py:3) | Routes and refund amounts: yes. Advisor text amounts are only filtered (see B9). Costs come from the SDK (fine). | Mostly true |
| B4 | "The LLM agents only read documents and explain results; they never decide a route" (rules.py:4; llm/advisor) | True in the narrow sense. But the LLM's extraction (type, flags, which entries exist) decides the route's inputs, and parts of it are not checked (B1). | True but misleading |
| B5 | "Never guesses" / "the app will not guess" (rules.py:60 NEEDS_REVIEW; checks.py:9-10 "instead of guessing") | Partly. Unverified liquidation, IEEPA duty, entry number or flags lead to NEEDS_REVIEW (rules.py:173-194). Entry numbers found by regex but not extracted also lead to NEEDS_REVIEW (run.py:156-161). But (a) flags default to false when a document says nothing (reader.py:105), which effectively assumes "not excluded" and pushes the entry toward CAPE; (b) the surety, 08, drawback, AD/CVD and recon routes are returned *before* the liquidation checks (rules.py:178-187), so an unverified liquidation does not stop CAPE_PHASE2_RECON; (c) entry type is never checked. | Overstatement |
| B6 | "An entry with a failed check on a key fact goes to 'Check by hand' and is left out of the CAPE file" (app.js:265) | Not for reconciliation-flagged entries. Tested: recon + unverified liquidation status gives `in_cape_csv=True`. | Overstatement / bug |
| B7 | "every IEEPA duty amount must be printed on a page with that entry, and entered value x rate must equal the duty" (checks.py:7-8; UI step "printed and adds up") | "Printed" means the amount appears *anywhere* on a page containing the entry number (checks.py:184-198). On a multi-entry broker statement it can match another entry's figure. The value x rate check is **skipped** (passes) when there is no base value or the rate is null (checks.py:200-202). | Overstatement |
| B8 | "liquidation dates must appear in a quote that is tied to that entry" (checks.py:5) | The date may come from any segment of a quote joined with "|", while "tied" only needs *one* segment to contain the entry number (checks.py:126-127, :162). So a date from another entry's line can pass. "Unliquidated" evidence accepts weak words such as "open", "pending", "not yet" (checks.py:30). | Overstatement |
| B9 | "Code checked **every dollar amount**, date and entry number against those results [and removed sentences that didn't match]" (app.js:213; advisor.py:1-3) | Partly. Bugs: the trailing-zero comparison (advisor.py:75) accepts "$41250" and "$412500" when $4,125 is allowed (tested). Not checked at all: amounts without "$" ("USD 9,999", "4,125 dollars"), dates without a year ("November 16"), ordinal dates ("Dec 3rd, 2026": no regex matches it), numeric "11/16", and entry numbers without dashes (ENTRY_RE advisor.py:49 needs dashes). It only checks that a value appears somewhere in the results, not that it is paired with the right entry. Any rule date (RULE_DATES) is accepted anywhere. | Overstatement plus a bug |
| B10 | "**Removes hidden text**": "drops text a person can't see (white or near-invisible characters, tiny fonts)" (documents.py:5-6; app.js:267 "hidden characters dropped") | Only drops characters smaller than 3.5 pt or with a near-white *fill* color (documents.py:57-75). Not handled: invisible render mode (OCR-layer style), text placed off the page or clipped, text covered by shapes or images, text in a background-matching non-white color, stroke-only text. It also wrongly drops real white text on a dark background. | Overstatement |
| B11 | "**removes lines that try to give orders to an AI**" (documents.py:7; app.js:267 "line(s) that tried to instruct an AI removed") | Nine English regexes matched line by line (documents.py:24-35). Rephrased, split-across-lines or non-English instructions get through. The UI wording presents regex hits as a complete count. | Overstatement |
| B12 | "Even if something slipped through, it could not change a route or an amount" (documents.py:9-10) | False in general. Injected text could get the Reader to leave out a true flag (surety, drawback), change the entry type, or drop an entry, and none of these are code-verified (B1). This changes the route. (See also `stress/security/`.) | Overstatement |
| B13 | "Each agent runs with no built-in tools ... only tools this app gives it" (llm.py:3-4) | `tools=[]`, `allowed_tools` limited to the app's own MCP tools, `setting_sources=[]`, `cwd=logs/` (llm.py:76-88). | True |
| B14 | Checker "cannot change anything itself: code decides what to do with each finding" (checker.py:3-5) | True. Issues need a quote that code can find (run.py:109); code then triggers a re-read and re-verify (run.py:118-146). | True |
| B15 | "These rules are written in plain code ..., not decided by an AI" (app.js:281) | True. | True |
| B16 | "every result shows the date of the rules it used" (index.html:26) | The header and result meta show the snapshot (app.js:118). The CSV, ICS and printed summary do not include it. | Mostly true |
| B17 | "Demo mode replays a real recorded run" (app.js:51; index.html:51) | `data/recorded/` **does not exist**, so in demo mode `/api/runs` returns 400 for every sample (main.py:116-119). The recordings exist only as `logs/run_*.json` and have not been copied in by `scripts/record_runs.py`. | Not met right now |
| B18 | "$X can go into CAPE now or after **one quick step**" (app.js:117) | The fix_first bucket includes FIX_THEN_CAPE for *liquidated* entries (Lotus A8, Meridian M34). After liquidation a PSC is not available, and CBP points to a protest or prior disclosure, which a quick step does not cover. | Overstatement |
| B19 | CSV: "Entry numbers only, as CBP asks" (app.js:239; outputs.py:11-15) | Matches the CSMS. The 9,999 cap quietly drops extra rows (outputs.py:14) instead of starting a second file. | True (minor gap) |
| B20 | ICS "reminders 7 days and 1 day before. Works with Google, Outlook and Apple" (app.js:241) | VALARMs are written (outputs.py:44-46). Google Calendar generally ignores imported VALARMs. | Minor overstatement |
| B21 | "Section 301 and 232 duties are not part of the IEEPA refund" (app.js:283; rules.py:58) | Prefix logic excludes 9903.88, .80, .81, .85 and similar (rules.py:30). | True |
| B22 | "Click an entry to see ... every check it passed" (app.js:161) | It shows all checks, including failed ones (app.js:178). | Harmless wording |
| B23 | "Cost is what these calls would cost at Claude API list prices, as reported by the Claude Agent SDK" (app.js:262) | Uses `ResultMessage.total_cost_usd` (llm.py:104). | True |

---

## Recommended fixes (not applied)

1. Move the reconciliation check after the liquidation, protest and value checks. Require unliquidated or 80 days or less, add a liquidation + 80 deadline, and add a Reader field for "type 09 already filed".
2. For plaintiffs: route entries liquidated more than 80 days to Phase 3 (not only more than 180). Give plaintiffs with a late IOR their own route ("Phase 3, later batch: CBP instructions pending"), never "Class member".
3. Add type 22 and type 23 to the not-via-CAPE routes. Check for goods value on *any* Ch. 99 line.
4. Stop treating "open" as unliquidated without checking. Separate the ACE status "Open" or "Closed" from unliquidated.
5. Note on CLASS_PENDING: the class may not cover Brazil and India IEEPA duties or duties paid Feb 20-23, 2026. The lawsuit deadline is Feb 4, 2027 at the earliest and varies by tariff and entry.
6. Soften the UI: "code checks key facts", "removes common hidden-text tricks", "screens for common AI-instruction phrases". Fix the Advisor trailing-zero comparison and extend the money, date and entry patterns.
7. Copy `logs/run_*.json` into `data/recorded/` (or rerun `scripts/record_runs.py`) so demo mode works.
8. Update the tests that lock in the WRONG behavior (`test_phase3_requires_ior_by_july_30`, and the CAPE_PHASE2_RECON answer keys if the liquidation limit is added).

---

## Appendix A: edge cases run against `rules.decide` (as of 2026-10-24)

| Input | Route returned | Expected per sources |
|---|---|---|
| Recon flag, type 01, liquidated 2025-12-28 (300 days) | CAPE_PHASE2_RECON | Not CAPE (more than 80 days) |
| Recon flag + open protest, liquidated 2026-09-01 | CAPE_PHASE2_RECON | Not CAPE (open protest) |
| Recon flag, liquidation status unverified | in_cape_csv = True | Check by hand |
| Type 22, unliquidated | CAPE_NOW | Rejected since July 7 (CSMS #69127837) |
| Type 23, unliquidated | CAPE_NOW | Excluded (CBP page) |
| Plaintiff (IOR 2026-07-01), liquidated 120 days | PROTEST_BY | CAPE Phase 3 |
| Plaintiff (IOR 2026-08-05), liquidated 200 days | CLASS_PENDING | Not a class member; Phase 3 later batch |
| Value on a 9903.88 line, IEEPA line clean, unliquidated | CAPE_NOW | Rejected ("any chapter 99 HTS code") |

Advisor check (`advisor._sentence_ok`), with $4,125.00 allowed: "$41250" passes, "$412500" passes, "$41,250" is blocked. "USD 9,999", "November 16" and "HP704122073" are not checked.

## Appendix B: sources

Primary: CSMS #68340863 (Apr 13, 2026), https://content.govdelivery.com/accounts/USDHSCBP/bulletins/412cc7f · CSMS #69035485 (Jun 23, 2026), https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41d65dd · CSMS #69066837 (Jun 29, 2026), https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41de055 · CBP IEEPA duty refunds page (updated Sept 30, 2026), https://www.cbp.gov/trade/programs-administration/trade-remedies/ieepa-duty-refunds · CIT Slip Op. 26-123, Freestyle World v. CBP, Ct. No. 26-01088 (Oct 8, 2026), https://www.cit.uscourts.gov/sites/cit/files/26-123.pdf · CSMS #69127837 (warehouse), https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41ece9d (read via search excerpt only).

Secondary: Holland & Knight (Apr 22, 2026) · Thompson Hine (Jul 29, 2026) · Troutman Pepper Locke (Oct 2, 2026) · Phillips Lytle (Oct 12, 2026) · Davis Wright Tremaine (Oct 14, 2026) · Greenberg Traurig (Oct 19, 2026) · Diaz Trade Law (Oct 19, 2026) · BDO FAQ (Aug 11, 2026) · Vinson & Elkins via JD Supra (Apr 17, 2026) · C.H. Robinson (Sept 17, 2026) · GHY (2026) · Foley (Feb 2026) · Polsinelli (2026) · CRS IF13150 (Jan 13, 2026).

Not found: a CBP CSMS for Phase 3; any class-wide refund order; any Federal Circuit ruling in No. 26-1895; confirmation that the Oct 22 scheduling order was filed.

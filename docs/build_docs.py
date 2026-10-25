"""Build docs/report.html and docs/slides.html from the real logs.

  .venv/bin/python docs/build_docs.py

Numbers come from:
  logs/eval_final.json         full pipeline (Opus Reader) and the one-prompt baseline, 4 importers
  logs/eval_sonnet_final.json  full pipeline with a Sonnet Reader (ablation)
  logs/eval_luna.json          full pipeline and one-prompt baseline, all on gpt-6-luna (course key)
  logs/luna_runs_summary.json  per-agent tokens and cost of those gpt-6-luna runs
  logs/luna_lotus_run.json     an uncached gpt-6-luna Lotus run (real timings)
  data/recorded/*.json         recorded real runs (agent table, costs)
  stress/summary.json          red-team and robustness results (written from stress/*/FINDINGS.md)
Screenshots come from docs/shots (docs/screens.py).
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = HERE / "shots"

AUTHOR = "Vy Bui (vb473)"
COURSE = "AI Agents · Final project"
DATE = "October 2026"
REPO = "https://github.com/vhb13/dutyback"
VIDEO = "DutyBack_demo.mp4 (attached)"


def load(p):
    p = ROOT / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


EV = load("logs/eval_final.json")
EVS = load("logs/eval_sonnet_final.json")
REC = {s: load(f"data/recorded/{s}.json") for s in ("lotus", "northtrail", "casaverde", "meridian")}
EVL = load("logs/eval_luna.json")
LUNA = load("logs/luna_runs_summary.json")
LUNA_LOT = load("logs/luna_lotus_run.json")
STRESS = load("stress/summary.json") or {"security": [], "robustness": [], "audit": []}


def img(name, cls="shot", alt=""):
    p = SHOTS / name
    if not p.exists():
        return f"<div class='missing'>[{name}]</div>"
    return f"<img class='{cls}' alt='{html.escape(alt)}' src='data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}'>"


def money(x, cents=False):
    return f"${x:,.2f}" if cents else f"${x:,.0f}"


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------- numbers
P = EV["total"]["pipeline"]
B = EV["total"]["baseline"]
N = P["entries"]
S = EVS["total"]["pipeline"] if EVS else None
per = {r["slug"]: r for r in EV["results"]}
L = EVL["total"]["pipeline"]
LB = EVL["total"]["baseline"]
luna_per = {r["slug"]: r for r in EVL["results"]}
lot = REC["lotus"]["result"]
mer = REC["meridian"]["result"] if REC["meridian"] else None
lot_cost = lot["totals"]["cost_usd"]
lot_secs = lot["totals"]["seconds"]
lot_entries = len(lot["entries"])
mer_cost = mer["totals"]["cost_usd"] if mer else 0
mer_entries = len(mer["entries"]) if mer else 0
luna_lot_cost = LUNA["lotus"]["totals"]["cost_usd"]
luna_mer_cost = LUNA["meridian"]["totals"]["cost_usd"]
luna_secs = LUNA_LOT["totals"]["seconds"]
luna_per_entry_c = 100 * L["cost_usd"] / L["entries"]


def agent_rows(res):
    rows = []
    for a in res["agents"]:
        tin = a["input_tokens"] + a["cache_read_tokens"] + a["cache_write_tokens"]
        rows.append(f"<tr><td>{esc(a['agent'])}</td><td class='mono'>{esc(a.get('model_id') or a['model'])}</td>"
                    f"<td class='r'>{a['seconds']:.0f}s</td><td class='r'>{tin:,}</td><td class='r'>{a['output_tokens']:,}</td>"
                    f"<td class='r'>{len(a['tool_calls'])}</td><td class='r'>${a['cost_usd']:.3f}</td></tr>")
    t = res["totals"]
    rows.append(f"<tr class='tot'><td>Total</td><td></td><td class='r'>{t['seconds']:.0f}s</td><td class='r'>{t['input_tokens']:,}</td>"
                f"<td class='r'>{t['output_tokens']:,}</td><td class='r'>{t['tool_calls']}</td><td class='r'>${t['cost_usd']:.2f}</td></tr>")
    return "".join(rows)


RUNS_PER_MONTH = 4       # assumption: a small importer re-checks its paperwork weekly as entries liquidate
ENTRIES_PER_RUN = 13     # a Lotus-sized batch


def scale_table():
    per_entry = {"gpt-6-luna, all agents (default)": L["cost_usd"] / L["entries"],
                 "Claude, Sonnet Reader": S["cost_usd"] / S["entries"] if S else None,
                 "Claude, Opus Reader": P["cost_usd"] / P["entries"]}
    out = ["<table><tr><th>Engine</th><th class='r'>Per run (13 entries)</th><th class='r'>Per user per month</th>"
           "<th class='r'>100 users / month</th><th class='r'>10,000 users / month</th></tr>"]
    for lbl, pe in per_entry.items():
        if pe is None:
            continue
        run = pe * ENTRIES_PER_RUN
        um = run * RUNS_PER_MONTH
        out.append(f"<tr><td>{lbl}</td><td class='r'>${run:.3f}</td><td class='r'>${um:.2f}</td>"
                   f"<td class='r'>${um * 100:,.0f}</td><td class='r'>${um * 10000:,.0f}</td></tr>")
    out.append("</table>")
    return "".join(out)


def luna_importer_table():
    rows = []
    for slug, label in (("lotus", "Lotus Tile & Stone"), ("northtrail", "North Trail Cycles"), ("casaverde", "Casa Verde Imports"), ("meridian", "Meridian Home Goods")):
        r = LUNA[slug]
        t = r["totals"]
        readers = sum(1 for a in r["agents"] if a["agent"].startswith("reader") and "repair" not in a["agent"])
        cached = sum(a.get("cache_read_tokens") or 0 for a in r["agents"])
        n = r["entries"]
        rows.append(f"<tr><td>{label}</td><td class='r'>{r['pages']}</td><td class='r'>{n}</td><td class='r'>{readers}</td>"
                    f"<td class='r'>{t['input_tokens'] - cached:,}</td><td class='r'>{cached:,}</td><td class='r'>{t['output_tokens']:,}</td><td class='r'>{t['tool_calls']}</td>"
                    f"<td class='r'>${t['cost_usd']:.4f}</td><td class='r'>{100 * t['cost_usd'] / n:.2f}¢</td></tr>")
    return ("<table><tr><th>Importer (gpt-6-luna eval run)</th><th class='r'>Pages</th><th class='r'>Entries</th><th class='r'>Readers</th><th class='r'>Input</th>"
            "<th class='r'>Cached input</th><th class='r'>Output</th><th class='r'>Tool calls</th><th class='r'>Cost</th><th class='r'>Per entry</th></tr>" + "".join(rows) + "</table>")


def luna_agent_rows():
    rows = []
    for a in LUNA_LOT["agents"]:
        rows.append(f"<tr><td>{esc(a['agent'])}</td><td class='mono'>{esc(a.get('model_id') or a['model'])}</td>"
                    f"<td class='r'>{a['seconds']:.0f}s</td><td class='r'>{a['input_tokens']:,}</td><td class='r'>{a['cache_read_tokens']:,}</td><td class='r'>{a['output_tokens']:,}</td>"
                    f"<td class='r'>{len(a['tool_calls'])}</td><td class='r'>${a['cost_usd']:.4f}</td></tr>")
    t = LUNA_LOT["totals"]
    cached = sum(a["cache_read_tokens"] for a in LUNA_LOT["agents"])
    rows.append(f"<tr class='tot'><td>Total</td><td></td><td class='r'>{t['seconds']:.0f}s</td><td class='r'>{t['input_tokens'] - cached:,}</td><td class='r'>{cached:,}</td>"
                f"<td class='r'>{t['output_tokens']:,}</td><td class='r'>{t['tool_calls']}</td><td class='r'>${t['cost_usd']:.4f}</td></tr>")
    return "".join(rows)


def eval_table():
    def row(label, key, fmt=lambda v, n: f"{v}/{n}"):
        cells = [fmt(L[key], N), fmt(LB[key], N), fmt(P[key], N), fmt(B[key], N)]
        if S:
            cells.insert(3, fmt(S[key], S["entries"]))
        return f"<tr><td>{label}</td>" + "".join(f"<td class='r'>{c}</td>" for c in cells) + "</tr>"
    head = "<tr><th></th><th class='r'>DutyBack<br><small>gpt-6-luna</small></th><th class='r'>One prompt<br><small>gpt-6-luna</small></th><th class='r'>DutyBack<br><small>Claude, Opus Reader</small></th>" + \
           ("<th class='r'>DutyBack<br><small>Sonnet Reader</small></th>" if S else "") + \
           "<th class='r'>One prompt<br><small>Opus, same rules</small></th></tr>"
    body = (row("Entries found", "found") + row("Correct route", "route_ok") + row("Correct refund amount", "amount_ok")
            + row("Correct deadline", "deadline_ok")
            + row("Wrong entries put in the CAPE file", "false_files", lambda v, n: str(v))
            + row("Refunds left out of the CAPE file", "missed_money", lambda v, n: money(v))
            + row("Cost for all four importers", "cost_usd", lambda v, n: f"${v:.2f}"))
    return f"<table>{head}{body}</table>"


def per_importer_table():
    rows = []
    for slug, label in (("lotus", "Lotus Tile & Stone"), ("northtrail", "North Trail Cycles"),
                        ("casaverde", "Casa Verde Imports"), ("meridian", "Meridian Home Goods")):
        r = per.get(slug)
        if not r:
            continue
        p, b = r["pipeline"], r["baseline"]
        lp, lb = luna_per[slug]["pipeline"], luna_per[slug]["baseline"]
        rows.append(f"<tr><td>{label}</td><td class='r'>{p['entries']}</td>"
                    f"<td class='r'>{lp['route_ok']}/{lp['entries']}</td><td class='r'>{lb['route_ok']}/{lb['entries']}</td>"
                    f"<td class='r'>{p['route_ok']}/{p['entries']}</td><td class='r'>{b['route_ok']}/{b['entries']}</td>"
                    f"<td class='r'>${lp['cost_usd']:.3f}</td><td class='r'>${p['cost_usd']:.2f}</td></tr>")
    return ("<table><tr><th>Importer</th><th class='r'>Entries</th><th class='r'>DutyBack routes<br><small>gpt-6-luna</small></th><th class='r'>One prompt<br><small>gpt-6-luna</small></th>"
            "<th class='r'>DutyBack routes<br><small>Claude Opus</small></th><th class='r'>One prompt<br><small>Claude Opus</small></th>"
            "<th class='r'>DutyBack cost<br><small>gpt-6-luna</small></th><th class='r'>DutyBack cost<br><small>Claude Opus</small></th></tr>" + "".join(rows) + "</table>")


def stress_table(kind):
    rows = STRESS.get(kind) or []
    if not rows:
        return "<p class='muted'>(not run yet)</p>"
    out = ["<table><tr><th>Test</th><th>What should happen</th><th>What happened</th><th>Result</th></tr>"]
    for r in rows:
        cls = {"PASS": "ok", "FIXED": "ok", "OK": "ok", "CAUTIOUS": "warn", "LIMIT": "warn"}.get(r["result"], "bad")
        out.append(f"<tr><td>{esc(r['test'])}</td><td>{esc(r['expected'])}</td><td>{esc(r['actual'])}</td>"
                   f"<td><span class='tag {cls}'>{esc(r['result'])}</span></td></tr>")
    out.append("</table>")
    return "".join(out)


DIAGRAM = """
<div class="flow">
  <div class="node code"><b>1. Safety screen</b><span>code · drops hidden text and AI-instruction lines, file limits</span></div>
  <div class="arrow">→</div>
  <div class="node agent"><b>2. Reader agent(s)</b><span>Claude · every entry, flag and duty line, each with a quote · big files split and read in parallel</span></div>
  <div class="arrow">→</div>
  <div class="node code"><b>3. Verify</b><span>code · quotes found? date next to this entry? duty printed and value × rate = duty?</span></div>
  <div class="arrow">→</div>
  <div class="node agent"><b>4. Checker agent</b><span>Claude + 4 read-only tools · finds what's missing or wrong, must quote the documents</span></div>
</div>
<div class="flow">
  <div class="node agent"><b>5. Repair</b><span>Reader re-reads only the flagged entries · code verifies again · never "fixes" without a quote</span></div>
  <div class="arrow">→</div>
  <div class="node code"><b>6. Rules engine</b><span>code · route, refund, deadline for every entry (CBP rules, snapshot Oct 24, 2026)</span></div>
  <div class="arrow">→</div>
  <div class="node agent"><b>7. Advisor agent</b><span>Claude · plain-English plan + broker email from the engine's results</span></div>
  <div class="arrow">→</div>
  <div class="node code"><b>8. Number check + files</b><span>code · removes sentences with unknown $, dates, entries · CAPE CSV · calendar</span></div>
</div>
"""

CSS = """
@page{size:letter;margin:0.55in 0.6in}
body{font:14.5px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif;color:#1c1917;max-width:900px;margin:0 auto;padding:28px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.01em} h2{font-size:21px;margin:30px 0 8px;padding-top:6px;border-top:3px solid #b45309}
h3{font-size:16px;margin:18px 0 6px} p{margin:0 0 9px} ul{margin:0 0 10px;padding-left:20px} li{margin-bottom:3px}
.sub{color:#57534e;font-size:15px} .muted{color:#78716c} small{font-size:12px}
.links{background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;padding:10px 14px;margin:14px 0;font-size:14px}
table{width:100%;border-collapse:collapse;margin:8px 0 12px;font-size:13.5px} th,td{border-bottom:1px solid #e7e2d9;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#faf8f4;color:#57534e;font-size:12px;text-transform:uppercase;letter-spacing:.03em} .r{text-align:right} .tot td{font-weight:700;background:#faf8f4}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.shot{width:100%;border:1px solid #e7e2d9;border-radius:8px;margin:8px 0 4px} .half{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}
.cap{font-size:12.5px;color:#78716c;margin-bottom:10px}
.flow{display:flex;align-items:stretch;gap:6px;margin:8px 0}
.node{flex:1;border-radius:10px;padding:8px 10px;font-size:12.5px;line-height:1.35} .node b{display:block;font-size:13.5px;margin-bottom:2px}
.node span{color:#44403c} .node.code{background:#f5f5f4;border:1.5px solid #a8a29e} .node.agent{background:#fff7ed;border:1.5px solid #b45309}
.arrow{align-self:center;color:#a8a29e;font-size:20px}
.box{border:1px solid #e7e2d9;border-radius:10px;padding:10px 14px;margin:10px 0} .do{border-left:5px solid #15803d} .dont{border-left:5px solid #be123c}
.pending{border:2px dashed #d6d3d1;border-radius:10px;padding:10px 14px;color:#57534e}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;color:#fff} .tag.ok{background:#15803d} .tag.warn{background:#a16207} .tag.bad{background:#be123c}
.refs{columns:2;column-gap:24px;font-size:11px;line-height:1.4} .refs li{break-inside:avoid;margin-bottom:4px}
.missing{border:1px dashed #ccc;padding:20px;color:#999;text-align:center}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0} .kpi{background:#faf8f4;border-radius:10px;padding:10px 12px} .kpi b{display:block;font-size:22px}
@media print{body{padding:0;max-width:none;font-size:12.6px} h2{break-after:avoid} table,.flow,.box,img,.kpis{break-inside:avoid} .refs{font-size:9.5px}}
"""

REFERENCES = [
    ("CBP CSMS #68340863, IEEPA refunds: CAPE Phase 1 deployment (Apr 20, 2026)", "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/412cc7f"),
    ("CBP, IEEPA Duty Refunds page (modified Sept 30, 2026)", "https://www.cbp.gov/trade/programs-administration/trade-remedies/ieepa-duty-refunds"),
    ("Declaration of Brandon Lord (CBP), Atmus Filtration v. United States, CIT No. 26-01259, ECF 31 (Mar 6, 2026)", "https://storage.courtlistener.com/recap/gov.uscourts.cit.19346/gov.uscourts.cit.19346.31.0.pdf"),
    ("CIT Order, Atmus Filtration v. United States, ECF 34 (Mar 6, 2026)", "https://storage.courtlistener.com/recap/gov.uscourts.cit.19346/gov.uscourts.cit.19346.34.0.pdf"),
    ("Thompson Hine, CBP announces Phases 2 and 3 of the IEEPA refund process (2026)", "https://www.thompsonhine.com/insights/cbp-announces-phases-2-and-3-of-the-ieepa-tariff-refund-process/"),
    ("Phillips Lytle, CBP opens Phase 3 of CAPE (Oct 12, 2026)", "https://phillipslytle.com/cbp-opens-phase-3-of-cape-for-ieepa-refunds/"),
    ("Davis Wright Tremaine, Trade court certifies non-litigant importer class (Oct 2026)", "https://www.dwt.com/insights/2026/10/cit-certifies-ieepa-duty-refund-importer-class"),
    ("Diaz Trade Law, IEEPA refund class certified: why importers with large Phase 3 refunds should still sue (Oct 19, 2026)", "https://customsandinternationaltradelaw.com/2026/10/19/ieepa-class-phase-3-refunds/"),
    ("Holland & Knight, IEEPA tariff refund update: government appeals (June 2026)", "https://www.hklaw.com/en/insights/publications/2026/06/ieepa-tariff-refund-update-government-appeals"),
    ("Orrick, Court of International Trade orders refunds for IEEPA tariffs (Mar 2026)", "https://www.orrick.com/en/Insights/2026/03/Court-of-International-Trade-Orders-Refunds-for-IEEPA-Tariffs"),
    ("19 U.S.C. § 1514, protests (180 days after liquidation)", "https://www.law.cornell.edu/uscode/text/19/1514"),
    ("19 CFR 24.36, refunds of excessive duties (interest)", "https://www.law.cornell.edu/cfr/text/19/24.36"),
    ("CBP quarterly interest rates notice, FR Doc. 2026-19292 (Sept 22, 2026)", "https://public-inspection.federalregister.gov/2026-19292.pdf"),
    ("U.S. Chamber of Commerce, Tariff refunds FAQ for small businesses (Apr 15, 2026)", "https://www.uschamber.com/economy/tariff-refunds-faq-what-small-businesses-need-to-know-after-supreme-courts-ruling"),
    ("U.S. Census Bureau, Preliminary profile of U.S. importing and exporting companies, 2024 (Dec 2025)", "https://www.census.gov/foreign-trade/Press-Release/edb/2024prelimprofile.pdf"),
    ("Federal Reserve Bank of Atlanta, How are firms using their tariff refunds? (Sept 21, 2026)", "https://www.atlantafed.org/research-and-data/publications/policy-hub-macroblog/2026/09/21/how-are-firms-using-tariff-refunds"),
    ("Rep. Haley Stevens et al., letter to CBP on IEEPA refunds (Sept 9, 2026)", "https://stevens.house.gov/sites/evo-subsites/stevens-evo.house.gov/files/evo-media-document/ieepa-tariff-refunds-letter-final.pdf"),
    ("Center for American Progress, Refunds from the unlawful tariffs (Oct 1, 2026)", "https://www.americanprogress.org/article/refunds-from-the-trump-administrations-unlawful-tariffs-are-a-windfall-for-corporate-america-not-for-small-businesses-or-consumers/"),
    ("Baker Tilly, IEEPA refunds tracker (updated Oct 12, 2026)", "https://www.bakertilly.com/insights/ieepa-refunds"),
    ("American Action Forum, It's raining refunds (Apr 23, 2026)", "https://www.americanactionforum.org/shipment/its-raining-refunds/"),
    ("Modern Retail, Brands rush to request tariff refunds (Apr 21, 2026)", "https://www.modernretail.co/operations/its-like-getting-taylor-swift-tickets-brands-rush-to-request-tariff-refunds-with-some-snags/"),
    ("Fortune, How can my company get a tariff refund? (May 5, 2026)", "https://www.fortune.com/2026/05/05/how-can-my-company-get-a-tariff-refund-ieepa/"),
    ("Nixon Peabody, CAPE is coming: refund process limits and next steps (Apr 16, 2026)", "https://www.nixonpeabody.com/insights/articles/2026/04/16/cape-is-coming-tariff-refund-process-limits-and-next-steps"),
    ("CBP CSMS #68569567, Protecting your information regarding IEEPA refunds (May 7, 2026)", "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41649df"),
    ("CIT Schedule of Fees", "https://www.cit.uscourts.gov/sites/cit/files/Schedule%20of%20Fees%20POSTED%20CT.pdf"),
    ("Anthropic, Claude Agent SDK documentation", "https://docs.claude.com/en/api/agent-sdk/overview"),
]


def routes_table():
    from importlib import import_module
    import sys
    sys.path.insert(0, str(ROOT))
    R = import_module("app.pipeline.rules")
    rows = "".join(f"<tr><td><b>{esc(lbl)}</b></td><td>{esc(R.BUCKETS[b])}</td><td>{'yes' if k in R.CSV_ROUTES else ''}</td><td>{esc(reason)}</td></tr>"
                   for k, (lbl, b, reason) in R.ROUTES.items())
    return ("<table><tr><th>Route</th><th>Bucket</th><th>In CAPE file</th><th>When (as written in rules.py)</th></tr>" + rows + "</table>")


def walkthrough_steps():
    rec = REC["lotus"]
    det, secs = rec["step_details"], rec["step_seconds"]
    names = [("screen", "Safety screen", "code"), ("read", "Reader agent", "agent"), ("verify", "Verify", "code"),
             ("check", "Checker agent", "agent"), ("repair", "Repair", "agent + code"), ("route", "Rules engine", "code"),
             ("plan", "Advisor agent", "agent + code")]
    rows = "".join(f"<tr><td>{esc(t)}</td><td>{who}</td><td class='r'>{secs.get(k, 0):.0f}s</td><td>{esc(det.get(k, ''))}</td></tr>" for k, t, who in names)
    return "<table><tr><th>Step</th><th>Who</th><th class='r'>Time</th><th>What the app reported</th></tr>" + rows + "</table>"


def importer_cost_table():
    rows = []
    for slug, label in (("lotus", "Lotus Tile & Stone"), ("northtrail", "North Trail Cycles"), ("casaverde", "Casa Verde Imports"), ("meridian", "Meridian Home Goods")):
        r = REC[slug]["result"]
        t = r["totals"]
        readers = sum(1 for a in r["agents"] if a["agent"].startswith("reader") and "repair" not in a["agent"])
        n = len(r["entries"])
        rows.append(f"<tr><td>{label}</td><td class='r'>{r['screen']['pages']}</td><td class='r'>{n}</td><td class='r'>{readers}</td>"
                    f"<td class='r'>{t['input_tokens']:,}</td><td class='r'>{t['output_tokens']:,}</td><td class='r'>{t['tool_calls']}</td>"
                    f"<td class='r'>{t['seconds']:.0f}s</td><td class='r'>${t['cost_usd']:.2f}</td><td class='r'>{100 * t['cost_usd'] / n:.1f}¢</td></tr>")
    return ("<table><tr><th>Importer (recorded run)</th><th class='r'>Pages</th><th class='r'>Entries</th><th class='r'>Readers</th><th class='r'>Tokens in</th>"
            "<th class='r'>Tokens out</th><th class='r'>Tool calls</th><th class='r'>Time</th><th class='r'>Cost</th><th class='r'>Per entry</th></tr>" + "".join(rows) + "</table>")


def model_table():
    rows = [("DutyBack, gpt-6-luna (default, course key)", L), ("One prompt, gpt-6-luna, same rules", LB),
            ("DutyBack, Claude Opus Reader", P), ("DutyBack, Claude Sonnet Reader", S), ("One prompt, Claude Opus, same rules", B)]
    out = ["<table><tr><th>Setup (all 4 importers, 82 entries)</th><th class='r'>Correct routes</th><th class='r'>Cost</th><th class='r'>Per entry</th><th>What you get</th></tr>"]
    notes = ["Evidence, checks, Checker, plan, files", "A list of routes; 1 wrong entry in the CAPE file", "Same as the default, about 50x the cost",
             "Same, cheaper than Opus", "A list of routes; no evidence or checks"]
    for (lbl, d), note in zip(rows, notes):
        if d:
            out.append(f"<tr><td>{lbl}</td><td class='r'>{d['route_ok']}/{d['entries']}</td><td class='r'>${d['cost_usd']:.2f}</td>"
                       f"<td class='r'>{100 * d['cost_usd'] / d['entries']:.2f}¢</td><td>{note}</td></tr>")
    out.append("</table>")
    return "".join(out)


AUDIT_ROWS = [
    ("Phase 2 (reconciliation) entries", "Sent to CAPE at any age", "Only unliquidated or within 80 days, after the protest check (CSMS #69035485, #69066837)"),
    ("Warehouse and TIB entries", "Types 22 and 23 fell through to 'File in CAPE now'", "Types 21, 22, 23 go to 'Ask your broker' (CSMS #69127837; CBP page)"),
    ("Plaintiffs whose importer number reached CBP after July 30", "Labeled 'class member'", "'Plaintiff: Phase 3 later' (they are excluded from the class)"),
    ("Plaintiff entries liquidated 81-180 days ago", "Told to protest", "Phase 3 (court orders cover entries past 80 days; a protest would block CAPE)"),
    ("Goods value on a Chapter 99 line", "Only checked on IEEPA lines", "Any Chapter 99 line (CBP page)"),
]


def audit_table():
    return ("<table><tr><th>Rule</th><th>My first version</th><th>Fixed to</th></tr>" +
            "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in AUDIT_ROWS) + "</table>")


SAVINGS = [
    ("A. Do nothing", "$0", "$0 now", "Every month more entries slide from CAPE to protest to waiting on the court"),
    ("B1. Broker, flat fee per entry", "$1,600-$2,800 (8 entries x $200-$350)", "$32,800-$34,000", "Fee from vendor blogs (weak); depends on the broker's queue"),
    ("B2. Contingency firm, 5-15%", "$1,800-$5,300", "$30,300-$33,800", "Advertised ranges (weak)"),
    ("B3. Sell the claim at 70-90%", "$3,600-$10,700", "$24,900-$32,100", "Doesn't make CBP faster"),
    ("C. Self-file with a triage tool, broker for protests", "$1,000-$1,750 + 3-6 hours", "$33,600-$34,500", "CBP charges $0 to file in CAPE"),
]


def savings_table():
    return ("<table><tr><th>Scenario (illustrative $50k importer)</th><th>Cost</th><th>Net recovered now</th><th>Note</th></tr>" +
            "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>" for a, b, c, d in SAVINGS) + "</table>")


def history_table():
    rows = [("First version, 3 importers", "33/34", "33/34", "Each sent one entry to review"),
            ("First version, Meridian (48)", "48/48", "47/48", "Baseline sent one entry to review"),
            ("Final code, Oct 24 evening (82)", "82/82", "80/82", "Baseline miscounted the 180-day window twice (missed protests)"),
            ("Final code, Oct 25 (82), this report", f"{P['route_ok']}/{P['entries']}", f"{B['route_ok']}/{B['entries']}", "Both perfect"),
            ("Sonnet Reader, Oct 25 (82)", f"{S['route_ok']}/{S['entries']}" if S else "-", "-", "Same accuracy, lower cost"),
            ("gpt-6-luna, course key, Oct 25 (82)", f"{L['route_ok']}/{L['entries']}", f"{LB['route_ok']}/{LB['entries']}",
             "Same model for both. One prompt: 2 wrong deadlines and 1 entry wrongly put in the CAPE file")]
    return ("<table><tr><th>Run</th><th class='r'>DutyBack</th><th class='r'>One prompt</th><th>Notes</th></tr>" +
            "".join(f"<tr><td>{a}</td><td class='r'>{b}</td><td class='r'>{c}</td><td>{d}</td></tr>" for a, b, c, d in rows) + "</table>")


def report():
    rows_lot = agent_rows(lot)
    removed_total = sum(len(REC[s]["result"]["plan_removed_sentences"]) for s in REC if REC[s])
    checks_total = sum(len(e["checks"]) for s in REC if REC[s] for e in REC[s]["result"]["entries"])
    checks_ok = sum(c["ok"] for s in REC if REC[s] for e in REC[s]["result"]["entries"] for c in e["checks"])
    ls = lot["summary"]
    b = ls["buckets"]
    refs = "".join(f"<li>{esc(t)}. <span class='mono'>{esc(u)}</span></li>" for t, u in REFERENCES)
    sonnet_line = ""
    if S:
        sonnet_line = (f"<p>I also ran the whole pipeline with the cheaper Sonnet model as the Reader. It scored {S['route_ok']}/{S['entries']} "
                       f"routes and {S['amount_ok']}/{S['entries']} amounts for ${S['cost_usd']:.2f}, against ${P['cost_usd']:.2f} with Opus. "
                       "On these documents the cheaper model was just as accurate, which matters for the tokenomics below.</p>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>DutyBack: report</title><style>{CSS}</style></head><body>

<h2 style="border:0;margin-top:0">1. Title</h2>
<h1>DutyBack</h1>
<p class="sub">Getting small importers their struck-down tariffs back, before the deadlines pass</p>
<p>{esc(AUTHOR)} · {esc(COURSE)} · {esc(DATE)}</p>
<div class="links"><b>Repo:</b> <span class="mono">{esc(REPO)}</span><br><b>Demo video:</b> {esc(VIDEO)} (about 3 minutes)<br>
<b>Run it:</b> <span class="mono">pip install -r requirements.txt && python run.py</span>, then open <span class="mono">localhost:8010</span>. With <span class="mono">PORTKEY_API_KEY</span> in a <span class="mono">.env</span> (in the repo folder or one folder up) the agents run live on <b>gpt-6-luna</b>; with no key it opens in a labeled demo mode that replays real recorded runs.</div>

<h2>2. Motivation</h2>
<p>On February 20, 2026 the Supreme Court struck down the tariffs imposed under the International Emergency Economic Powers Act (IEEPA). By then importers had paid about <b>$166 billion</b> in these duties on more than 53 million customs entries, and CBP counted <b>over 330,000 importers</b> who paid them [3]. Census counts about 233,000 small and mid-sized importers, 97% of all U.S. importers [15].</p>
<p>The refunds are not automatic. CBP opened an online process called CAPE in April, but every customs entry has its own clock:</p>
<ul>
<li>CAPE accepts an entry only until <b>80 days after it liquidates</b> (the date CBP finalizes the duty) [1].</li>
<li>After that, the importer has to file a formal <b>protest within 180 days</b> of liquidation [11].</li>
<li>After 180 days the entry is "finally liquidated". Today only importers who sued can claim those through CAPE (Phase 3, opened Oct 6). A court certified a class for everyone else on Oct 8, but there is no refund order yet [6][7].</li>
</ul>
<p>Big companies have customs lawyers watching these windows. Small ones mostly don't. By April only about 17% of importers had even set up refund bank details, yet they held 82% of the entries [20]. The Atlanta Fed found larger and publicly listed firms were more likely to have been refunded [16]. In September, ten members of Congress wrote that CBP was failing to approve importer accounts in time and that many of those at risk "are small businesses operating on thin margins" [17].</p>
<p>So a lot of money is stuck behind deadlines that pass one entry at a time, and it belongs to the companies least able to track them.</p>

<h2>3. What is new here</h2>
<p>I was looking for work that could plainly be automated but still isn't. This fits well:</p>
<ul>
<li><b>Filing is easy.</b> A CAPE declaration is just a list of entry numbers, with no other data [1].</li>
<li><b>Sorting is the hard part, and it's manual.</b> For each entry you have to find its liquidation date and flags across a broker statement, CBP Form 7501 pages, an ACE report or an email. Then check about eight exclusion rules and two date windows, separate IEEPA duty from Section 301 and 232 duty on the same line, and add it all up with dates. Brokers and lawyers do this by hand for their clients, and some brokers have told clients to file themselves [22][23]. I could not find a low-cost tool that does this sorting for a small importer.</li>
</ul>
<p>What DutyBack does that I haven't seen elsewhere:</p>
<ul>
<li>It reads <b>mixed broker paperwork</b> (four different layouts in my tests) and sorts <b>every entry</b> into a route, with the refund amount and the exact deadline.</li>
<li>It shows <b>"money at risk this week"</b>: entries whose window closes in the next 7 days.</li>
<li>Every fact links back to <b>a quote from the documents</b>, and every decision comes from plain code that follows the published rules, with a rules snapshot date on every screen.</li>
<li>The owner leaves with <b>usable files</b>: the CAPE upload list, a calendar with reminders, a plan and a draft email to the broker.</li>
</ul>
{img("results.png", alt="Results page")}
<p class="cap">The Lotus Tile &amp; Stone result (a recorded real run). {money(b['file_now']['amount'] + b['fix_first']['amount'])} can go into CAPE now or after one fix; {money(b['protest']['amount'])} needs a protest; one entry's window closes today.</p>

<h2>4. The agents: how I built it</h2>
<p>I split the work by what each part is good at. <b>Language models read messy documents and write plain English well. Code is better at dates, money and rules.</b> So the agents read and explain, and code checks what they extract and makes every decision.</p>
{DIAGRAM}
<ul>
<li><b>Reader agent</b> (gpt-6-luna on the course key; Claude Opus as an option). Turns the PDFs into structured entries: entry number, type, liquidation status and date, six flags (surety paid, open protest, IEEPA-only protest, drawback, reconciliation, AD/CVD), and every HTS line with value, rate and duty. Each fact comes with a quote. For big files the pages are split into chunks of 10 and read <b>in parallel</b>, then merged by entry number. Meridian's 49 pages ran as six Readers at once.</li>
<li><b>Code verification.</b> A liquidation date only counts if it is printed in <i>that</i> entry's own text (from its number to the next entry number), so it can't be borrowed from another row. Each IEEPA duty must sit on the same line as its HTS code, value × rate must equal the duty, and all duty lines must add up to the 7501's printed duty total. The entry type must be printed next to the entry. Code also looks at the text next to each entry for flag words the Reader missed ("paid by surety", "protest filed", "drawback claim"), corrections ("corrected", "supersedes", "revised") and contradictions (two liquidation dates, or "open" on a newer statement than the liquidation). Anything that fails gets one focused re-read; if it still fails, the entry goes to "Check by hand" and stays out of the CAPE file.</li>
<li><b>Checker agent</b> (gpt-6-luna; Claude Sonnet as an option) with four read-only tools that I wrote. On the course key they are strict function tools in the OpenAI Responses API; on Claude they are served through the Agent SDK as an in-process MCP server: <span class="mono">list_entry_numbers_in_documents</span> (found by regex, not by the model), <span class="mono">get_extraction</span>, <span class="mono">search_documents</span> and <span class="mono">read_page</span>. It looks for missed entries, missed flags, wrong amounts and statement-vs-line conflicts. Every issue must quote the documents; issues whose quote isn't found are dismissed.</li>
<li><b>Repair.</b> Flagged entries, unverified entries, and entry numbers that code found but the Reader missed go back to the Reader once, then through verification again. A correction is kept only if it verifies at least as well as the original.</li>
<li><b>Rules engine</b> (plain Python, <span class="mono">rules.py</span>). It applies the exclusions in order, then the 80- and 180-day windows from the as-of date, then Phase 3 or the court class. A rules audit by a separate agent against the CBP messages and the court's opinion found four mistakes in my first version (Phase 2 limited to 80 days, warehouse and TIB entry types, and two plaintiff cases); all are fixed. Sixteen routes, each with the reason text shown to the user. The tests (123 in total, across rules, checks, the screen, the filters and the files) cover the 80/81 and 180/181-day boundaries, and a separate, independently written reference router builds Meridian's answer key.</li>
<li><b>Advisor agent</b> (gpt-6-luna; Claude Sonnet as an option). Writes the action plan and the broker email from the engine's results only. Then code removes any sentence with a dollar amount, date or entry number that isn't in those results. Across the four recorded runs it removed {removed_total} sentence(s).</li>
</ul>
<p><b>Which model, and why.</b> Every agent call goes through one function (<span class="mono">app/pipeline/llm.py</span>) with two engines. The default is the course key: <b>gpt-6-luna</b> through Portkey, the only model allowed on that key, with strict JSON-schema output. I first built and tested DutyBack on Claude (Opus Reader, Sonnet Checker and Advisor) through the Claude Agent SDK, and kept that as an option (<span class="mono">DUTYBACK_BACKEND=claude</span>). On my 82 hand-checked entries gpt-6-luna was exactly as accurate as Claude Opus at about 1/50 of the cost (section 5), so it is the default. Because the code does the checking and the deciding, a smaller model is enough for the reading. Either way, agents have no built-in tools at all (no files, shell or web), a spending cap per call and a turn limit. The web app is FastAPI with plain JavaScript.</p>
<div class="half">{img("drawer_301.png", alt="Entry detail")}<div>{img("how.png", alt="How this was made")}</div></div>
<p class="cap">Left: an entry's evidence. The broker statement quote, the 7501 duty lines (Section 301 marked "not IEEPA") and the checks code ran. Right: the "How this was made" tab with every agent, model, token count, cost and the Checker's tool calls (this screenshot is from a recorded Claude run; on the course key the same tab shows gpt-6-luna).</p>

<h3>One real run, step by step: Lotus Tile &amp; Stone</h3>
<p>Lotus is a made-up tile importer in Long Beach with 13 customs entries from Vietnam, China, Italy and Spain. Its paperwork is 12 CBP Form 7501 pages and a one-page broker statement. One entry appears only on the statement. This is the recorded run that demo mode replays (recorded on the Claude engine; a gpt-6-luna run of the same paperwork is in section 5 and gave the same routes and amounts):</p>
{img("start.png", alt="Start page")}
<p class="cap">The start page: four synthetic sample importers, each with a different broker paperwork layout, or upload your own PDFs.</p>
{walkthrough_steps()}
<div class="half">{img("plan.png", alt="Action plan")}{img("timeline.png", alt="Deadlines")}</div>
<p class="cap">Left: the Advisor's plan, soonest deadline first, and the draft broker email. Right: the deadlines view. Each bar is the time left before that entry's window closes.</p>
{img("files.png", alt="Downloads")}
<p class="cap">What the owner takes away: the CAPE upload list (entry numbers only, as CBP asks), a calendar with reminders 7 days and 1 day before each deadline, and a printable summary.</p>
<h3>The Checker's tools</h3>
<table><tr><th>Tool</th><th>What it returns</th><th>Why</th></tr>
<tr><td class="mono">list_entry_numbers_in_documents</td><td>Every entry number in the paperwork, found by a regex, with where it appears</td><td>So "did we miss one?" is answered by code, not by the model's memory</td></tr>
<tr><td class="mono">get_extraction</td><td>The Reader's result, one compact row per entry</td><td>To compare against the documents</td></tr>
<tr><td class="mono">search_documents</td><td>Lines containing a text, with the lines around them</td><td>To find notes like "protest filed" or a second date</td></tr>
<tr><td class="mono">read_page</td><td>The full text of one page</td><td>To read a 7501 closely</td></tr></table>
<p>The tools are read-only and see only the screened text. The Checker can't change anything; code decides what to do with each issue.</p>
<h3>The rules, in one table</h3>
<p>This is every route the engine can give, with the exact reason text the user sees. Only two routes put an entry into the CAPE file.</p>
{routes_table()}

<h2>5. Tokenomics</h2>
<p><b>Default engine: gpt-6-luna on the course key.</b> Token counts are what the API reported for real runs; cost uses gpt-6-luna list prices ($0.10 per million input tokens, $0.01 cached input, $0.50 output; the app computes it per call and shows it in the "How this was made" tab).</p>
<table><tr><th>Agent (gpt-6-luna Lotus run, {lot_entries} entries)</th><th>Model</th><th class="r">Time</th><th class="r">Input</th><th class="r">Cached input</th><th class="r">Output</th><th class="r">Tool calls</th><th class="r">Cost</th></tr>{luna_agent_rows()}</table>
{luna_importer_table()}
<p class="cap">The eval run's input tokens include cache hits from repeated system prompts and Checker turns. Portkey also returned cached responses for some prompts I had just run, so the eval timings are too short to be meaningful; the Lotus table above is an uncached run ({luna_secs:.0f} s).</p>
<h3>Cost per user and at scale</h3>
<p>Assumption: a typical small importer runs a Lotus-sized batch (13 entries) {RUNS_PER_MONTH} times a month, re-checking as new entries liquidate. Per-entry costs are the measured averages over all 82 entries.</p>
{scale_table()}
<h3>Claude engine (how I developed it)</h3>
<p>Costs below are what each call would cost at Claude API list prices, as reported by the Agent SDK. (I ran these on a Claude subscription.)</p>
<table><tr><th>Agent (Claude Lotus run, {lot_entries} entries)</th><th>Model</th><th class="r">Time</th><th class="r">Tokens in</th><th class="r">Tokens out</th><th class="r">Tool calls</th><th class="r">Cost</th></tr>{rows_lot}</table>
{importer_cost_table()}
{model_table()}
<ul>
<li><b>Per importer on the course key:</b> ${luna_lot_cost:.4f} for Lotus ({lot_entries} entries) and ${luna_mer_cost:.3f} for Meridian ({mer_entries} entries), about <b>{luna_per_entry_c:.2f} cents per entry</b>. Most of it is the Reader's output tokens, because it writes out every line with its quote.</li>
<li><b>What I did to keep cost down, and whether it hurt:</b> I moved every agent from Claude (${P['cost_usd']:.2f} for the four importers with an Opus Reader, ${S['cost_usd']:.2f} with Sonnet) to gpt-6-luna (${L['cost_usd']:.2f}). Accuracy did not drop: {L['route_ok']}/{N} routes, {L['amount_ok']}/{N} amounts, {L['deadline_ok']}/{N} deadlines and no wrong CAPE entries, the same as Claude Opus (section 7). Big files are split so Readers run in parallel instead of one huge call, the Repair step re-reads only flagged entries, and the Checker reads pages on demand through its tools instead of getting every page in its prompt.</li>
<li><b>One prompt is cheaper still.</b> On gpt-6-luna one prompt cost ${LB['cost_usd']:.2f} against ${L['cost_usd']:.2f} for DutyBack, but it got {LB['deadline_ok']}/{N} deadlines and put {LB['false_files']} wrong entry into the CAPE file. The extra few cents buy the evidence trail, the verification and the Checker.</li>
<li><b>Guards:</b> a dollar cap per agent call, a daily run cap, page and file limits, and the Checker's turn limit. Repeated system prompts are cached by the SDK automatically (visible as cache reads in the logs).</li>
<li><b>Against the value:</b> under 1 cent on gpt-6-luna (about 40 cents on Claude Opus) to sort {money(ls['ieepa_paid'])} of duty. A broker charges roughly $200–$350 per entry according to vendor blogs (weak sources, see research notes). CBP itself estimated about 5 minutes per entry for a specialist [3], so 13 entries is about an hour by hand.</li>
</ul>

<h2>6. Safety</h2>
<div class="half">
<div class="box do"><b>What DutyBack does</b><ul><li>Reads paperwork and quotes it</li><li>Applies CBP's published rules in code</li><li>Prepares files for the owner and their broker to review</li><li>Says where it isn't sure ("Check by hand")</li></ul></div>
<div class="box dont"><b>What it never does</b><ul><li>Let an AI decide a route, an amount or a deadline</li><li>File anything with CBP or contact anyone</li><li>Promise a refund or give legal advice</li><li>Put an unverified entry in the CAPE file</li></ul></div>
</div>
<p><b>Defenses, in order:</b></p><ol>
<li>The screen renders each page and keeps only text with visible ink, so white or light text, text under a white box, off-page, clipped and invisible-mode text never reach an agent. Lines that look like instructions to an AI are removed too, but that pattern list is only a first line of defense.</li>
<li>Agents have no tools except the read-only ones I give the Checker.</li>
<li>Every extracted fact is checked against the entry's own text, and contradictions or corrections send the entry to a person.</li>
<li>Routes and money come from code. The CAPE file only gets entries backed by 7501 or ACE line detail, from one importer, with no unresolved conflict; statement-only entries and Phase 3 (plaintiff) entries need confirmation first, and look-alike entry numbers are folded and flagged.</li>
<li>The Advisor's text is filtered against the engine's numbers.</li></ol>
<p>Across the recorded runs, {checks_ok} of {checks_total} code checks passed; the rest sent entries to a person rather than into a filing.</p>
<h3>A rules audit</h3>
<p>A separate agent checked my rules against the primary sources (the CBP messages, CBP's refund page and the court's opinion) and my UI's claims against the code. It found these mistakes in my first version, all fixed and covered by tests:</p>
{audit_table()}
<p>It also flagged claims that overstated what the code did ("code checks every fact", "removes hidden text"). I rewrote them to say exactly what is checked.</p>
<h3>Red-team results</h3>
<p>I had separate agents attack the app with adversarial PDFs and messy paperwork, without changing the app, and report back. <b>They broke it.</b> Forged "corrections" in a broker's voice, text hidden under white boxes, a fake entry in a footnote and Cyrillic look-alike entry numbers all changed the CAPE file. In the worst case, Lotus went from 5 entries and $34,810 to 9 entries and $95,545. Interestingly, the Reader itself ignored every explicit instruction; the weakness was that my code trusted any fact printed in the paperwork. I fixed the causes and re-ran the same attacks:</p>
{stress_table("security")}
{img("attack.png", alt="Attack result")}
<p class="cap">My own attacked Lotus statement (hidden white text plus a visible "note to the AI"): the screen removed both and the CAPE file matched the clean run. The one-prompt comparison, given the raw text, wasn't fooled either; the models ignore blunt instructions like these. I re-ran the same attacked paperwork on gpt-6-luna: 13/13 routes and amounts, 1 instruction line removed, 189 hidden characters dropped, and a CAPE file identical to the clean run (<span class="mono">logs/eval_attack_luna.json</span>). The defenses that mattered were for forged facts.</p>
<p><b>What can still go wrong:</b> a forged fact that is visible, consistent and printed next to the entry (a fake plaintiff claim, a footnote-only entry) can still change what the app <i>displays</i>, though it can't reach the CAPE file and the app warns about both. If the paperwork itself is wrong (a broker typo in a liquidation date), DutyBack repeats it, with the quote, so a person can catch it. Scanned pages without a text layer aren't read; the app names them instead of guessing. The rules are a snapshot and the law is moving (appeal pending).</p>

<h2>7. Impact and metrics</h2>
<h3>Accuracy against hand-checked answer keys</h3>
<p>I built four synthetic importers with {N} entries and wrote the correct route for each by hand (Meridian's 48 come from a separate reference implementation). The traps include the 80/81 and 180/181-day boundaries, surety-paid, drawback, type 08, reconciliation, AD/CVD, warehouse, open protests, value on an IEEPA line, Section 301 and 232 on the same line, an entry that is only in the broker statement, a statement that disagrees with the line detail, and a court-plaintiff importer. The comparison is the same model given the same rules in one prompt. I ran it on both engines.</p>
{eval_table()}
{per_importer_table()}
{sonnet_line}
<p><b>On the course model the structure matters.</b> On gpt-6-luna, DutyBack scored {L['route_ok']}/{N} routes, {L['amount_ok']}/{N} amounts and {L['deadline_ok']}/{N} deadlines with no wrong CAPE entries. One prompt to the same model got {LB['route_ok']}/{N} routes and {LB['deadline_ok']}/{N} deadlines, and it put a Lotus entry whose goods value sits on a Chapter 99 line straight into the CAPE file, which CAPE would reject. DutyBack's code checks caught that and routed it to "Fix, then file in CAPE".</p>
<p><b>The honest result on Claude:</b> on clean digital PDFs, one careful prompt to a strong model is about as accurate as the full pipeline, at about a quarter of the cost. In this final run both were perfect. In an identical run the night before, the one-prompt version got 80 of 82: it miscounted the 180-day window on two entries and called them "waiting on the court" when their protest window was still open, which would have cost the importer those protests. Across all my evaluation runs (<span class="mono">logs/eval_history.md</span>), DutyBack's only miss was one entry sent to "Check by hand" in an early version. DutyBack's advantages are elsewhere. It never put a wrong entry in the CAPE file. Every number traces to a quote and a check. Instructions hidden in a document can't change a result. And when something can't be verified, it goes to a person instead of into a filing. For money and legal deadlines, I think that trade is worth it, and on gpt-6-luna it costs well under a cent an entry.</p>
<h3>Robustness on messy paperwork</h3>
{stress_table("robustness")}
<h3>What it's worth to an importer</h3>
<p>A worked example with stated assumptions: a small importer paid $50,000 in IEEPA duty on 12 entries, one a month from March 2025, with no filings yet, as of today. Using the same rules as the app, about <b>$20,800</b> can go into CAPE now, <b>$12,500</b> needs a protest, and <b>$16,700</b> is finally liquidated (waiting on the court). Recoverable today: <b>about $35,600 with interest</b>. Doing nothing recovers $0 now, and <b>waiting one month pushes about $4,500 more past a deadline</b>. Paying a contingency firm 5–15% instead of self-filing costs $1,800–$5,300. The deadlines matter far more than the fees. CBP charges nothing to file [14], and CBP warns about scam refund offers [24]. A free tool that shows which entries expire this week is the useful part.</p>
{savings_table()}
<p class="cap">Sources and assumptions are in <span class="mono">docs/research_savings.md</span>. Fee figures from vendor blogs are weak evidence; the deadline arithmetic follows the app's rules. CBP's own estimate of manual review time is about 5 minutes per entry [3].</p>
<h3>Every evaluation run</h3>
{history_table()}
<h3>Real-user feedback</h3>
<div class="pending"><b>First feedback pending.</b> I'm showing DutyBack to a small importer using the 15-minute script in <span class="mono">docs/feedback_kit.md</span>. Only what they actually say will go here.</div>

<h2>8. Limits and next steps</h2>
<ul>
<li><b>Synthetic data only.</b> The four importers and their paperwork are made up; real broker paperwork is messier. The stricter checks are cautious with two-column statements (they go to "Check by hand").</li>
<li><b>Rules snapshot of Oct 24, 2026.</b> The Federal Circuit appeal and the class case can change the routes. Edge cases (warehouse, AD/CVD, type 09) are deliberately sent to "ask your broker" instead of guessed. Interest is not computed.</li>
<li><b>Not legal advice,</b> and it doesn't file anything. The CAPE CSV should be checked against the template in the ACE Portal.</li>
<li><b>Two engines, one tested more.</b> The demo-mode recordings and the video are from the Claude engine; the course-key engine (gpt-6-luna) is the default and scored the same on all 82 entries, but has had fewer runs. Without any key it opens in a labeled demo mode with real recorded runs.</li>
<li><b>Next:</b> real feedback from a few small importers and a broker; reading ACE reports directly; OCR for scanned pages; interest estimates; tracking rule changes automatically.</li>
</ul>

<h3>How I used AI, and other disclosures</h3>
<ul>
<li><b>AI use.</b> I built DutyBack with Claude Code (Anthropic) as my coding assistant. The app's agents run on gpt-6-luna through the course key by default, or on Claude. Background research was gathered with AI research agents; every number in this report has a source, listed below, and secondary sources are marked as such in my research notes.</li>
<li><b>Synthetic data.</b> All companies, IOR numbers, entry numbers and paperwork are fictional. HTS codes and rates are illustrative.</li>
<li><b>Video.</b> Real runs recorded on my computer; waiting time is sped up; the narration is a synthetic voice (Kokoro, open source).</li>
<li><b>Not legal advice.</b> DutyBack is a student project, not affiliated with CBP.</li>
</ul>
<h2>References</h2>
<ol class="refs">{refs}</ol>
</body></html>"""


def slides():
    ls = lot["summary"]
    b = ls["buckets"]
    css = """
.reveal{font-family:-apple-system,"Segoe UI",Inter,Arial,sans-serif;font-size:30px;color:#1c1917}
.reveal h1,.reveal h2{font-family:inherit;color:#1c1917;letter-spacing:-.01em;text-transform:none}
.reveal h2{font-size:1.5em;margin-bottom:.4em} .reveal .kick{color:#b45309;font-weight:800;text-transform:uppercase;letter-spacing:.1em;font-size:.55em}
.reveal ul{font-size:.82em;line-height:1.4} .reveal li{margin-bottom:.25em}
.reveal table{font-size:.62em;width:100%} .reveal th{color:#57534e} .reveal td,.reveal th{padding:.25em .5em}
.reveal img.s{max-height:470px;border:1px solid #e7e2d9;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:center;text-align:left}
.big{font-size:2.1em;font-weight:800;color:#b45309;line-height:1}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:20px}
.kpi{background:#faf8f4;border-radius:14px;padding:18px} .kpi b{display:block;font-size:1.5em;color:#1c1917} .kpi span{font-size:.62em;color:#57534e}
.flow{display:flex;gap:8px;align-items:stretch;margin:10px 0} .node{flex:1;border-radius:12px;padding:10px;font-size:.5em;text-align:left;line-height:1.3}
.node b{display:block;font-size:1.15em} .code{background:#f5f5f4;border:2px solid #a8a29e} .agent{background:#fff7ed;border:2px solid #b45309}
.arrow{align-self:center;color:#a8a29e;font-size:.8em} small,.src{font-size:.45em;color:#78716c}
.g{color:#15803d;font-weight:700} .r{color:#be123c;font-weight:700}
"""
    def ev(label, k, fmt=lambda v: f"{v}/{N}"):
        return (f"<tr><td>{label}</td><td class='g'>{fmt(L[k])}</td><td>{fmt(LB[k])}</td>"
                f"<td class='g'>{fmt(P[k])}</td><td>{fmt(B[k])}</td></tr>")
    ev_rows = (ev("Correct route", "route_ok") + ev("Correct refund amount", "amount_ok") + ev("Correct deadline", "deadline_ok")
               + ev("Wrong entries in the CAPE file", "false_files", str)
               + ev("Refunds left out of the CAPE file", "missed_money", money)
               + ev("Cost, 4 importers", "cost_usd", lambda v: f"${v:.2f}"))
    sec = STRESS.get("security") or []
    sec_pass = sum(1 for r in sec if r["result"] in ("PASS", "FIXED"))
    flow = DIAGRAM.replace('class="flow"', 'class="flow"').replace("<span>", "<br><span>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>DutyBack: slides</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/white.css">
<style>{css}</style></head><body><div class="reveal"><div class="slides">

<section><div class="kick">AI agents · final project</div><h1 style="font-size:2.4em">DutyBack</h1>
<p>Getting small importers their struck-down tariffs back,<br>before the deadlines pass</p><p style="font-size:.6em">{esc(AUTHOR)} · {esc(DATE)}</p>
<p class="src">Synthetic sample companies · not legal advice</p></section>

<section><div class="kick">The problem</div><h2>$166B in struck-down tariffs. Refunds are not automatic.</h2>
<div class="kpis"><div class="kpi"><b>330,000+</b><span>importers paid IEEPA duties on 53M entries</span></div>
<div class="kpi"><b>80 days</b><span>after liquidation, CBP's CAPE system stops taking an entry</span></div>
<div class="kpi"><b>180 days</b><span>after liquidation, even a protest is too late</span></div></div>
<ul style="margin-top:24px"><li>Every entry has its own clock, so money expires one entry at a time</li><li>Small firms lag: few had refund accounts set up by April; Congress flagged it in September</li></ul>
<p class="src">CBP declaration to the CIT (Mar 2026) · CSMS #68340863 · 19 U.S.C. 1514 · Atlanta Fed (Sept 2026) · House letter (Sept 9, 2026)</p></section>

<section><div class="kick">What's not automated</div><h2>Filing is easy. Sorting is the hard part.</h2>
<div class="two"><div><ul><li>A CAPE filing is just a list of entry numbers</li><li>But each entry needs: liquidation date, 8 exclusion checks, 2 date windows, IEEPA vs Section 301/232 on the same line</li>
<li>Spread across 7501s, broker statements, ACE reports, emails, each broker's own layout</li><li>Brokers and lawyers do it by hand. I found no low-cost tool for small importers.</li></ul></div>
<div>{img("start.png", "s")}</div></div></section>

<section><div class="kick">The demo</div><h2>Every entry sorted, with its deadline</h2>
{img("results.png", "s")}
<p style="font-size:.55em">Lotus Tile &amp; Stone (synthetic): {money(b['file_now']['amount'] + b['fix_first']['amount'])} into CAPE now or after one fix · {money(b['protest']['amount'])} needs a protest · one entry's window closes today</p></section>

<section><div class="kick">How it works</div><h2>Agents read and explain. Code checks and decides.</h2>
{flow}
<p style="font-size:.55em">gpt-6-luna on the course key (Claude optional) · strict structured outputs · Checker gets 4 read-only tools · agents have no other tools · cost cap per call</p></section>

<section><div class="kick">Evidence, not trust</div><h2>Every number traces to the paperwork</h2>
<div class="two"><div>{img("drawer_301.png", "s")}</div><div><ul><li>Each fact has a quote; code finds it in the PDF</li><li>A date only counts if it sits next to <i>that</i> entry</li><li>Printed duty, and value × rate = duty</li><li>Section 301 and 232 lines never counted as IEEPA</li><li>Can't verify? It goes to <b>Check by hand</b>, never into the filing</li></ul></div></div></section>

<section><div class="kick">Does it work?</div><h2>{N} entries, 4 importers, hand-checked answers</h2>
<table><tr><th></th><th>DutyBack<br><small>gpt-6-luna</small></th><th>One prompt<br><small>gpt-6-luna</small></th><th>DutyBack<br><small>Claude Opus</small></th><th>One prompt<br><small>Claude Opus</small></th></tr>{ev_rows}</table>
<p style="font-size:.55em;text-align:left">On the course model, one prompt put a wrong entry in the CAPE file and missed 2 deadlines; DutyBack's code checks caught both. On Claude Opus both were perfect in the final run (one prompt missed 2 protest windows the night before). DutyBack's edge: date math in code, evidence for every number, and it fails safe under attack.</p></section>

<section><div class="kick">Tokenomics</div><h2>Under 1 cent to sort {money(ls['ieepa_paid'])} of duty</h2>
<div class="kpis"><div class="kpi"><b>${luna_lot_cost:.3f}</b><span>Lotus, {lot_entries} entries, gpt-6-luna</span></div>
<div class="kpi"><b>${luna_mer_cost:.3f}</b><span>Meridian, {mer_entries} entries, 6 Readers in parallel</span></div>
<div class="kpi"><b>${L['cost_usd'] / L['entries'] * ENTRIES_PER_RUN * RUNS_PER_MONTH * 10000:,.0f}/mo</b><span>for 10,000 users ({RUNS_PER_MONTH} runs of 13 entries each)</span></div></div>
<ul style="margin-top:22px"><li>Same 82/82 accuracy as Claude Opus (${P['cost_usd']:.2f} for the 4 importers) at ${L['cost_usd']:.2f}</li><li>Guards: $ cap per call, daily run cap, page limits, Checker turn limit</li><li>CBP estimates ~5 min per entry by hand; brokers charge ~$200–350/entry (vendor blogs)</li></ul></section>

<section><div class="kick">Safety</div><h2>The attacks that broke v1 no longer reach the filing</h2>
<div class="two"><div>{img("attack.png", "s")}</div><div><ul><li>Screen drops invisible text and AI-instruction lines</li><li>Routes and amounts come from code, not the model</li><li>Advisor's sentences with unknown $ / dates are removed</li><li>Red team broke the first version (CAPE file $34.8k → $95.5k); after fixes the file matched the clean run under every attack</li><li>Never files, never promises a refund, not legal advice</li></ul></div></div></section>

<section><div class="kick">Impact &amp; next steps</div><h2>Deadlines matter more than fees</h2>
<div class="kpis"><div class="kpi"><b>≈ $35,600</b><span>recoverable today for a $50k importer that hasn't filed</span></div>
<div class="kpi"><b>≈ $4,500</b><span>pushed past a deadline by waiting 30 days</span></div><div class="kpi"><b>$0</b><span>CBP fee to file in CAPE</span></div></div>
<ul style="margin-top:22px"><li>Next: real feedback from small importers and a broker (kit ready), ACE report import, OCR, rule-change tracking</li></ul>
<p class="src">Illustrative model with stated assumptions; sources in the report</p></section>

</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js"></script>
<script>Reveal.initialize({{hash:true, width:1280, height:760, margin:0.05, center:true, transition:'slide'}});</script>
</body></html>"""


if __name__ == "__main__":
    (HERE / "report.html").write_text(report(), encoding="utf-8")
    (HERE / "slides.html").write_text(slides(), encoding="utf-8")
    print("wrote docs/report.html and docs/slides.html")

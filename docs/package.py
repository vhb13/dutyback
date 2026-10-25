"""Build the SUBMIT_DutyBack folder (Canvas files, email + guide, clean repo copy, PDFs)."""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT.parent / "SUBMIT_DutyBack"
EXCLUDE = {".venv", ".venv-tools", "__pycache__", ".pytest_cache", ".claude", "video_build", ".DS_Store", ".git", ".env"}

shutil.rmtree(OUT, ignore_errors=True)
c, e, pdfs, g = OUT / "1_Upload_to_Canvas", OUT / "2_Email_and_guide", OUT / "3_PDF_versions", OUT / "4_Code_for_GitHub"
for d in (c, e, g, pdfs):
    d.mkdir(parents=True)

for f in ("report.html", "slides.html", "DutyBack_demo.mp4"):
    shutil.copy(DOCS / f, c / f)
for f in ("report.pdf", "slides.pdf"):
    shutil.copy(DOCS / f, pdfs / f)

email = (DOCS / "professor_email.md").read_text(encoding="utf-8").replace("**", "")
(e / "Email_to_professor.txt").write_text(email, encoding="utf-8")
(e / "Canvas_comment.txt").write_text(
    "GitHub repo (public): https://github.com/vhb13/dutyback\n\n"
    "Attached: report.html, slides.html, and a 2.5-minute demo video of a real run.\n\n"
    "DutyBack runs live on the course key (PORTKEY_API_KEY with gpt-6-luna). It reads .env from the repo folder, then the folder above. "
    "Setup: pip install -r requirements.txt, then python run.py and open http://localhost:8010. "
    "With no key it opens in a labeled demo mode that replays recorded runs. "
    "In the video, waits are sped up and the narration is a synthetic voice. All sample companies and documents are synthetic.\n\n"
    "Thank you,\nVy Bui\n", encoding="utf-8")
guide_md = (DOCS / "HOW_TO_SUBMIT.md").read_text(encoding="utf-8")
(e / "HOW_TO_SUBMIT.md").write_text(guide_md, encoding="utf-8")
html = markdown.markdown(guide_md, extensions=["tables", "fenced_code"])
css = ("body{font:13.5px/1.5 -apple-system,Segoe UI,Arial;color:#1c1917;max-width:760px;margin:30px auto;padding:0 20px}"
       "h1{font-size:24px}h2{font-size:17px;border-top:3px solid #b45309;padding-top:6px;margin-top:22px}"
       "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e7e2d9;padding:5px 8px;text-align:left}"
       "code,pre{background:#f5f5f4;font-size:12px}pre{padding:10px;border-radius:8px;overflow:auto}")
(e / "HOW_TO_SUBMIT.html").write_text(f"<!doctype html><meta charset='utf-8'><title>How to submit</title><style>{css}</style>{html}", encoding="utf-8")


async def _guide_pdf():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        try:
            b = await pw.chromium.launch()
        except Exception:
            b = await pw.chromium.launch(channel="msedge")  # Windows without a downloaded Chromium
        pg = await b.new_page()
        await pg.goto((e / "HOW_TO_SUBMIT.html").as_uri())
        await pg.pdf(path=str(e / "HOW_TO_SUBMIT.pdf"), format="Letter", print_background=True)
        await b.close()

import asyncio  # noqa: E402
asyncio.run(_guide_pdf())
(e / "HOW_TO_SUBMIT.html").unlink()
(e / "HOW_TO_SUBMIT.md").unlink()

repo = g / "dutyback"


def ignore(dirpath, names):
    out = {n for n in names if n in EXCLUDE or n.endswith(".pyc")}
    rel = Path(dirpath).relative_to(ROOT)
    if rel == Path("logs"):
        out |= {n for n in names if n.endswith(".log") or n.startswith("run_") or n == "daily_usage.json"}
    return out


shutil.copytree(ROOT, repo, ignore=ignore)
with zipfile.ZipFile(g / "dutyback.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(repo.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(g).as_posix())
n = sum(1 for p in repo.rglob("*") if p.is_file())
print(f"repo copy: {n} files; zip {round((g / 'dutyback.zip').stat().st_size / 1e6, 1)} MB")

# ---- measured facts for the checklist
import json
import re
from pypdf import PdfReader
rep_pages = len(PdfReader(DOCS / "report.pdf").pages)
sl_pages = len(PdfReader(DOCS / "slides.pdf").pages)
rep_html = (DOCS / "report.html").read_text(encoding="utf-8")
sections = re.findall(r"<h2[^>]*>(\d\. [^<]+)</h2>", rep_html)
shots = rep_html.count("data:image/png;base64")
sl_html = (DOCS / "slides.html").read_text(encoding="utf-8")
n_slides = sl_html.count("<section")
reveal = "cdn.jsdelivr.net/npm/reveal.js" in sl_html
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(DOCS / "DutyBack_demo.mp4")],
                     capture_output=True, text=True).stdout.strip()
dur = f"{int(float(dur) // 60)}:{int(float(dur) % 60):02d}"
tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()[-1]
ev = json.loads((ROOT / "logs" / "eval_luna.json").read_text(encoding="utf-8"))["total"]
P, B = ev["pipeline"], ev["baseline"]
files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file())
code_files = [f for f in files if f.endswith((".py", ".js", ".css", ".html")) and not f.startswith("stress/") and "docs/report" not in f and "docs/slides" not in f]

readme = f"""DUTYBACK: SUBMISSION FOLDER
===========================
Vy Bui's AI Agents final project. DutyBack helps small importers claim refunds of the IEEPA tariffs the Supreme Court struck down:
it reads their customs paperwork, sorts every entry into a refund route with its deadline, and prepares the CAPE file,
a deadline calendar, an action plan and an email to their broker.

WHAT'S IN HERE
  1_Upload_to_Canvas/   upload these 3 files to Canvas
      report.html         the report ({rep_pages} printed pages, {len(sections)} numbered sections, {shots} screenshots embedded)
      slides.html         the slides ({n_slides} slides, reveal.js from a CDN)
      DutyBack_demo.mp4   the demo video ({dur}, real run, narrated)
  2_Email_and_guide/
      HOW_TO_SUBMIT.pdf   step-by-step guide (start here)
      Canvas_comment.txt  paste into the Canvas comment box
      Email_to_professor.txt  send after submitting, with the PDFs and video attached
  3_PDF_versions/       report.pdf and slides.pdf (for the email, or as extras)
  4_Code_for_GitHub/
      dutyback/           a clean copy of the repo (the git repo itself is final project/dutyback)
      dutyback.zip        the same, zipped

BEFORE YOU SUBMIT
  - Push the repo to https://github.com/vhb13/dutyback (public). See HOW_TO_SUBMIT.pdf, step 1.
  - Real-user feedback: worth points. Only add what a real person actually said (dutyback/docs/feedback_kit.md).

See COMPLIANCE_CHECKLIST.txt for how each course requirement is met.
"""
(OUT / "00_README_FIRST.txt").write_text(readme, encoding="utf-8")

check = f"""COMPLIANCE CHECKLIST (measured {__import__('datetime').date.today().isoformat()})
=====================================================

COURSE REQUIREMENTS
[x] Agent app in a GitHub repo, with README and .env.example
      4_Code_for_GitHub/dutyback/README.md, .env.example   (upload to your own GitHub: you)
[x] Runs from a fresh clone within 10 minutes
      pip install -r requirements.txt && python run.py   (fresh Windows venv install measured at about 1.5 minutes)
      Live on the course key: tested from a fresh copy with the key only in ../.env (Lotus sample and a PDF upload)
[x] Course key only, gpt-6-luna only                           app/pipeline/llm.py (model locked on PORTKEY_API_KEY)
[x] .env read from the repo folder, then the parent folder     run.py load_env() and app/pipeline/llm.py
[x] report.html, 10-15 printed pages                           {rep_pages} pages
[x] 8 fixed sections                                           {'; '.join(sections)}
[x] Screenshots embedded in the report                         {shots}
[x] slides.html, reveal.js from a CDN, 10 slides max           {n_slides} slides, reveal.js CDN: {reveal}
[x] Demo video (optional backup)                               DutyBack_demo.mp4, {dur}
[x] Tokenomics measured                                        report section 5 (per agent, per importer, per user per month, 100 and 10,000 users; gpt-6-luna vs Claude vs one prompt)
[x] Safety defense shown working                               report section 6 + stress/security/FINDINGS.md and RETEST.md
[x] Impact and metrics                                         report section 7 (gpt-6-luna): DutyBack {P['route_ok']}/{P['entries']} routes, one prompt {B['route_ok']}/{B['entries']}
[ ] Real person trying it                                      pending: docs/feedback_kit.md (never invent it)

SAME DELIVERABLES AS THE EARLIER PROJECT'S SUBMISSION, DONE FOR DUTYBACK
[x] Synthetic data only (4 made-up importers, 82 entries, hand-checked answer keys)
[x] Real evaluation against a baseline (one prompt, same rules), on both engines   logs/eval_luna.json, logs/eval_final.json, logs/eval_history.md
[x] Stress tests by separate agents (security red team, messy paperwork, rules audit), fixed and re-tested   stress/
[x] Disclosures: AI use, synthetic data, synthetic voice, not legal advice   report section 8, README, video
[x] Narrated demo video with an open-source voice (Kokoro, af_heart)
[x] Submission guide, Canvas comment, professor email, PDF versions
[x] Savings research with sources                                            docs/research_savings.md
[x] No code, data or text reused from the earlier project

TESTS
  {tests}

CODE IN THE REPO ({len(files)} files total; {len(code_files)} code files)
""" + "\n".join("  " + f for f in code_files) + "\n"
(OUT / "COMPLIANCE_CHECKLIST.txt").write_text(check, encoding="utf-8")
print(readme)
print("checklist lines:", check.count(chr(10)))
print("built", OUT)

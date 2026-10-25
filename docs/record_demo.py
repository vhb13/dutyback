"""Record the DutyBack demo video: a real run in the browser, explainer cards, and a synthetic voiceover.

How it works:
  - Each scene has a narration line (Kokoro TTS, voice af_heart). The scene's video lasts at least as long as its line.
  - Frames come from Chrome's screencast (Playwright + CDP), so they show the real app.
  - The agents' waiting time is sped up, and the video says so on screen.
Run (server must be running at :8010 in live mode; tools: pip install playwright kokoro-onnx soundfile):
  KOKORO_MODELS=/path/to/kokoro/models python docs/record_demo.py
Output: docs/DutyBack_demo.mp4
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
BUILD = HERE / "video_build"
FRAMES = BUILD / "frames"
AUDIO = BUILD / "audio"
OUT = HERE / "DutyBack_demo.mp4"
APP = "http://localhost:8010"
# Kokoro model files (kokoro-v1.0.onnx, voices-v1.0.bin) from https://github.com/thewh1teagle/kokoro-onnx/releases
MODELS = Path(os.environ.get("KOKORO_MODELS", HERE / "tts_models"))
VOICE, SPEED = "af_heart", 1.06
W, H = 1440, 900
EVAL_PATH = HERE.parent / "logs" / "eval_luna.json"
EVAL = json.loads(EVAL_PATH.read_text(encoding="utf-8")) if EVAL_PATH.exists() else None

BADGE = """<div id="vidbadge" style="position:fixed;right:14px;bottom:12px;z-index:99;background:rgba(28,25,23,.88);color:#fff;
font:12px -apple-system,Segoe UI,Arial;padding:6px 10px;border-radius:8px">Real run · synthetic sample company · agent waits sped up · voice: Kokoro (synthetic)</div>"""

CARD_CSS = """<style>body{margin:0;background:#1c1917;color:#fff;font-family:-apple-system,Segoe UI,Inter,Arial;display:flex;align-items:center;justify-content:center;height:100vh}
.c{max-width:1050px;padding:40px} .k{color:#fbbf24;text-transform:uppercase;letter-spacing:.12em;font-size:20px;font-weight:700}
h1{font-size:58px;margin:14px 0 18px;line-height:1.1} p{font-size:27px;line-height:1.45;color:#e7e5e4;margin:10px 0}
.big{font-size:44px;font-weight:800;color:#fde68a} .row{display:flex;gap:28px;margin-top:26px} .box{flex:1;background:#292524;border-radius:16px;padding:20px 22px}
.box b{display:block;font-size:40px;color:#fde68a} .box span{font-size:20px;color:#d6d3d1} .s{font-size:17px;color:#a8a29e;margin-top:26px}
table{border-collapse:collapse;font-size:24px;margin-top:18px;width:100%} td,th{padding:10px 14px;border-bottom:1px solid #44403c;text-align:left} th{color:#a8a29e;font-size:18px;text-transform:uppercase}
.g{color:#86efac} .r{color:#fca5a5}</style>"""


def card(kicker, title, body="", extra="", small=""):
    return f"<html><head>{CARD_CSS}</head><body><div class='c'><div class='k'>{kicker}</div><h1>{title}</h1>{body}{extra}<div class='s'>{small}</div></div></body></html>"


def eval_card():
    if not EVAL:
        return card("How well it works", "Evaluation", "<p>(run scripts/run_eval.py --tag final first)</p>")
    p, b = EVAL["total"]["pipeline"], EVAL["total"]["baseline"]
    n = p["entries"]
    rows = f"""<table><tr><th></th><th>DutyBack (agents + code)</th><th>One prompt, same rules</th></tr>
      <tr><td>Correct route</td><td class='g'>{p['route_ok']}/{n}</td><td>{b['route_ok']}/{n}</td></tr>
      <tr><td>Correct refund amount</td><td class='g'>{p['amount_ok']}/{n}</td><td>{b['amount_ok']}/{n}</td></tr>
      <tr><td>Correct deadline</td><td class='g'>{p['deadline_ok']}/{n}</td><td>{b['deadline_ok']}/{n}</td></tr>
      <tr><td>Wrong entries in the CAPE file</td><td class='g'>{p['false_files']}</td><td>{b['false_files']}</td></tr>
      <tr><td>Refunds left out of the CAPE file</td><td class='g'>${p['missed_money']:,.0f}</td><td>${b['missed_money']:,.0f}</td></tr></table>"""
    return card("How well it works", f"{n} entries, 4 synthetic importers, hand-checked answer keys", rows,
                small="Run 1 of 3 on the final code; DutyBack was 82/82 in all three. Same model for both (gpt-6-luna on the course key), same rules. Synthetic test data; real paperwork will differ.")


NARRATION = {
    "title": "This is DutyBack. It helps small importers get back the tariffs the Supreme Court struck down, before the deadlines pass.",
    "problem": "Importers paid about a hundred and sixty six billion dollars in these tariffs. Refunds aren't automatic, and every customs entry has its own clock: eighty days for CBP's online system, a hundred and eighty for a protest.",
    "gap": "Filing is easy. Sorting every entry before its clock runs out is still done by hand.",
    "pick": "Here's Lotus Tile and Stone, a made-up importer, with thirteen customs forms and a broker statement.",
    "run": "Code screens the files. A Reader agent pulls out every entry with the text it came from. Code checks every quote, date and amount, and a Checker agent with its own tools looks for anything missed. I've sped this up.",
    "results": "About thirty nine thousand dollars can go into CAPE now, or after one step. Twenty three thousand needs a protest. And one entry's window closes today.",
    "entries": "The routes and amounts come from plain code that follows CBP's rules, not from the AI.",
    "drawer": "Click an entry to see the quotes from the paperwork, and every check the code ran.",
    "s301": "This granite entry also paid Section 301 tariffs. Those aren't part of this refund, so only the IEEPA lines count.",
    "plan": "The Advisor agent writes a plain English plan and an email to the broker. Code removes any number that doesn't match.",
    "timeline": "Every week, some money slides from file online, to protest, to waiting on the court.",
    "files": "The owner leaves with the CAPE upload list, a deadline calendar, and a summary for the broker.",
    "how": "Every agent, model, token and cost is shown here.",
    "safety": "I had separate agents attack it with hidden text and forged corrections. They broke my first version. After the fixes, the filing matched the clean run under every attack.",
    "eval": "On four test importers with hand checked answers, DutyBack got every route, amount and deadline right, three runs out of three. One prompt to the same model made mistakes every time, and left about nine thousand dollars of refunds out of the filing.",
    "impact": "For a typical importer with fifty thousand dollars in these tariffs, acting today recovers about thirty five thousand. Waiting a month pushes about four thousand more past a deadline.",
    "close": "DutyBack doesn't replace a customs broker. It makes sure a small business acts before the deadline. Thanks for watching.",
}



class Recorder:
    def __init__(self):
        self.frames: list[tuple[float, Path]] = []   # (duration placeholder, path)
        self.timeline: list[dict] = []
        self.n = 0
        self.last = None
        self.tts = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
        self.clock = 0.0          # output video time

    def voice(self, key):
        path = AUDIO / f"{key}.wav"
        a, sr = self.tts.create(NARRATION[key], voice=VOICE, speed=SPEED, lang="en-us")
        sf.write(path, a, sr)
        return path, len(a) / sr

    async def start(self, page):
        self.page = page
        self.cdp = await page.context.new_cdp_session(page)
        self.buf: list[tuple[float, bytes]] = []
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 88, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})

    async def _on_frame(self, ev):
        self.buf.append((time.time(), base64.b64decode(ev["data"])))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def _write(self, data: bytes) -> Path:
        self.n += 1
        p = FRAMES / f"f{self.n:06d}.jpg"
        p.write_bytes(data)
        return p

    async def scene(self, key, actions=None, speedup: float = 1.0, min_extra: float = 0.5, max_len: float | None = None):
        """Run actions while capturing; final scene length >= narration length."""
        wav, dur = self.voice(key) if key else (None, 0.0)
        self.buf = []
        t0 = time.time()
        if actions:
            await actions()
        await asyncio.sleep(0.25)
        captured = [(t, d) for t, d in self.buf if t >= t0 - 0.05]
        if not captured:
            shot = await self.page.screenshot(type="jpeg", quality=88)
            captured = [(time.time(), shot)]
        # durations between frames, compressed by speedup
        seq = []
        for i, (t, d) in enumerate(captured):
            nxt = captured[i + 1][0] if i + 1 < len(captured) else time.time()
            seq.append((max(0.02, (nxt - t) / speedup), d))
        length = sum(x for x, _ in seq)
        if max_len and length > max(max_len, dur + min_extra):
            k = max(max_len, dur + min_extra) / length          # squeeze a long wait into a fixed length
            seq = [(dt * k, d) for dt, d in seq]
            length = sum(x for x, _ in seq)
        target = dur + min_extra
        if length < target:   # hold the last frame until the line ends
            seq[-1] = (seq[-1][0] + (target - length), seq[-1][1])
            length = target
        start = self.clock
        for dt, d in seq:
            self.frames.append((dt, self._write(d)))
        self.clock += length
        self.timeline.append({"scene": key, "start": round(start, 2), "length": round(length, 2), "voice": str(wav) if wav else None,
                              "voice_len": round(dur, 2), "speedup": speedup})

    async def html(self, key, html_text, extra=0.5):
        async def show():
            await self.page.set_content(html_text)
            await asyncio.sleep(0.5)
        await self.scene(key, show, min_extra=extra)


async def main():
    for d in (FRAMES, AUDIO):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    rec = Recorder()
    async with async_playwright() as pw:
        browser = await (pw.chromium.launch(channel="msedge") if sys.platform == "win32" else pw.chromium.launch())
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = await ctx.new_page()
        await rec.start(page)

        await rec.html("title", card("Student project · AI agents", "DutyBack",
                       "<p class='big'>Find your tariff refunds before the deadlines pass.</p>",
                       small="Synthetic sample companies · real runs recorded on my computer · agent waiting time sped up · narration is a synthetic voice (Kokoro, open source) · not legal advice"))
        await rec.html("problem", card("The problem", "$166 billion in struck-down tariffs. Refunds are not automatic.", "",
                       "<div class='row'><div class='box'><b>330,000+</b><span>importers paid IEEPA duties</span></div>"
                       "<div class='box'><b>80 days</b><span>after liquidation, CAPE stops accepting an entry</span></div>"
                       "<div class='box'><b>180 days</b><span>after liquidation, the protest window closes</span></div></div>",
                       small="Sources: CBP declaration to the Court of International Trade (Mar 2026); CBP CSMS #68340863; 19 U.S.C. 1514."))
        await rec.html("gap", card("What's not automated", "Sorting every entry into the right route, before its clock runs out",
                       "<p>Brokers and lawyers do this by hand. A small importer usually has only a folder of PDFs.</p>"))

        async def pick():
            await page.goto(APP)
            await page.add_style_tag(content="#vidbadge{}")
            await page.evaluate("b => document.body.insertAdjacentHTML('beforeend', b)", BADGE)
            await asyncio.sleep(1.2)
            await page.click(".sample[data-slug=lotus]")
            await asyncio.sleep(1.5)
        await rec.scene("pick", pick)

        async def run():
            await page.click("#runBtn")
            for _ in range(400):
                await asyncio.sleep(0.5)
                if await page.is_visible("#results"):
                    break
            await asyncio.sleep(1.0)
        await rec.scene("run", run, speedup=7.0, max_len=19.0)
        tot = await page.evaluate("({cost: RESULT.totals.cost_usd, tools: RESULT.totals.tool_calls, secs: RESULT.totals.seconds})")
        cents = tot["cost"] * 100
        NARRATION["how"] = ("Every agent, model, token and cost is shown here. This whole run cost about one cent."
                            if cents < 1.5 else f"Every agent, model, token and cost is shown here. This run cost about {round(cents)} cents.")

        async def results():
            await page.evaluate("window.scrollTo({top: document.querySelector('#results').offsetTop - 10, behavior: 'smooth'})")
            await asyncio.sleep(2.5)
        await rec.scene("results", results)

        async def entries():
            await page.evaluate("window.scrollTo({top: document.querySelector('.tabs').getBoundingClientRect().top + scrollY - 20, behavior: 'smooth'})")
            await asyncio.sleep(2.0)
        await rec.scene("entries", entries)

        async def drawer():
            await page.click("#tab-entries tr.row >> nth=0")
            await asyncio.sleep(1.5)
            await page.evaluate("document.querySelector('.drawer-inner').scrollTo({top: 260, behavior: 'smooth'})")
            await asyncio.sleep(2.0)
        await rec.scene("drawer", drawer)

        async def s301():
            await page.click("#drawerClose")
            await asyncio.sleep(0.6)
            rows = await page.query_selector_all("#tab-entries tr.row")
            for r in rows:
                if "HP7-0413822-4" in (await r.inner_text()):
                    await r.click()
                    break
            await asyncio.sleep(1.2)
            await page.evaluate("document.querySelector('.drawer-inner').scrollTo({top: 420, behavior: 'smooth'})")
            await asyncio.sleep(2.0)
        await rec.scene("s301", s301)

        async def plan():
            await page.click("#drawerClose")
            await page.click(".tab[data-tab=plan]")
            await asyncio.sleep(2.5)
            await page.evaluate("window.scrollBy({top: 420, behavior: 'smooth'})")
            await asyncio.sleep(3.0)
        await rec.scene("plan", plan)

        async def timeline():
            await page.click(".tab[data-tab=timeline]")
            await page.evaluate("window.scrollTo({top: document.querySelector('.tabs').getBoundingClientRect().top + scrollY - 20, behavior: 'smooth'})")
            await asyncio.sleep(2.5)
        await rec.scene("timeline", timeline)

        async def files():
            await page.click(".tab[data-tab=files]")
            await asyncio.sleep(2.5)
        await rec.scene("files", files)

        async def how():
            await page.click(".tab[data-tab=how]")
            await asyncio.sleep(2.5)
            await page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
            await asyncio.sleep(2.0)
        await rec.scene("how", how)

        attack = HERE.parent / "data" / "attack" / "attack_result.json"
        if attack.exists():
            res = json.loads(attack.read_text(encoding="utf-8"))

            async def safety():
                await page.goto(APP)
                await page.wait_for_function("typeof STATUS !== 'undefined' && STATUS !== null")
                await page.evaluate("b => document.body.insertAdjacentHTML('beforeend', b)", BADGE)
                await page.evaluate("""r => { RESULT = r; currentJob = 'attack'; document.querySelector('#start').classList.add('hidden');
                    renderResults(); showTab('how'); }""", res)
                await asyncio.sleep(1.2)
                await page.evaluate("window.scrollTo({top: document.querySelector('.tabs').getBoundingClientRect().top + scrollY - 20})")
                await asyncio.sleep(1.0)
                await page.evaluate("window.scrollBy({top: 380, behavior: 'smooth'})")
                await asyncio.sleep(2.5)
            await rec.scene("safety", safety)

        await rec.html("eval", eval_card())
        await rec.html("impact", card("Why it matters", "Deadlines matter more than fees",
                       "<div class='row'><div class='box'><b>≈ $35,600</b><span>recoverable today for a $50k importer that hasn't filed yet</span></div>"
                       "<div class='box'><b>≈ $4,500</b><span>pushed out of reach by waiting 30 days</span></div>"
                       "<div class='box'><b>$0</b><span>CBP fee to file in CAPE</span></div></div>",
                       small="Illustrative model with stated assumptions (12 entries, 314-day liquidation, 6% interest). See the report for sources."))
        await rec.html("close", card("DutyBack", "Know what you're owed. Act before the deadline.",
                       "<p>Not legal advice. Agents run on gpt-6-luna through the course key, with plain-code rules. Synthetic data throughout.</p>",
                       small="Real runs recorded on my computer · agent waiting time sped up · narration is a synthetic voice (Kokoro, open source)"), extra=1.5)
        await browser.close()

    # assemble video from frames with exact durations
    concat = BUILD / "frames.txt"
    with concat.open("w", encoding="utf-8") as f:
        for dt, p in rec.frames:
            f.write(f"file '{p.as_posix()}'\nduration {dt:.4f}\n")
        f.write(f"file '{rec.frames[-1][1].as_posix()}'\n")
    silent = BUILD / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(silent)], check=True)
    # mix narration at each scene's start time
    inputs, filters = [], []
    voiced = [t for t in rec.timeline if t["voice"]]
    for i, t in enumerate(voiced):
        inputs += ["-i", t["voice"]]
        ms = int((t["start"] + 0.25) * 1000)
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(voiced)))
    fc = ";".join(filters) + f";{mix}amix=inputs={len(voiced)}:normalize=0,loudnorm=I=-16:TP=-2[aout]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), *inputs, "-filter_complex", fc,
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(OUT)], check=True)
    (BUILD / "timeline.json").write_text(json.dumps(rec.timeline, indent=1))
    print(f"wrote {OUT} ({rec.clock:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())

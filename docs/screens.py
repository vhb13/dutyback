"""Take the screenshots used in the report and slides, from recorded real runs.

  ../.venv-tools/bin/python docs/screens.py      (server running at :8010)
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "shots"
APP = "http://localhost:8010"


async def inject(page, result, tab="entries", job="recorded"):
    await page.goto(APP)
    await page.wait_for_function("typeof STATUS !== 'undefined' && STATUS !== null")
    await page.evaluate("""([r, tab, job]) => { RESULT = r; currentJob = job; document.querySelector('#start').classList.add('hidden');
        renderResults(); showTab(tab); window.scrollTo(0, 0); }""", [result, tab, job])
    await page.wait_for_timeout(700)


async def main():
    OUT.mkdir(exist_ok=True)
    lotus = json.loads((ROOT / "data" / "recorded" / "lotus.json").read_text())["result"]
    attack_path = ROOT / "data" / "attack" / "attack_result.json"
    attack = json.loads(attack_path.read_text()) if attack_path.exists() else None
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        page = await b.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=2)

        await page.goto(APP)
        await page.wait_for_timeout(900)
        await page.click(".sample[data-slug=lotus]")
        await page.screenshot(path=str(OUT / "start.png"))

        await inject(page, lotus)
        await page.screenshot(path=str(OUT / "results.png"), clip={"x": 0, "y": 0, "width": 1280, "height": 820})
        await page.evaluate("window.scrollTo(0, document.querySelector('.tabs').getBoundingClientRect().top + scrollY - 10)")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / "entries.png"))

        rows = await page.query_selector_all("#tab-entries tr.row")
        for r in rows:
            if "HP7-0413822-4" in await r.inner_text():
                await r.click()
                break
        await page.wait_for_timeout(500)
        await page.locator(".drawer-inner").screenshot(path=str(OUT / "drawer_301.png"))
        await page.click("#drawerClose")
        await page.click("#tab-entries tr.row >> nth=0")
        await page.wait_for_timeout(500)
        await page.locator(".drawer-inner").screenshot(path=str(OUT / "drawer_today.png"))
        await page.click("#drawerClose")

        for tab in ("plan", "timeline", "files", "how"):
            await page.click(f".tab[data-tab={tab}]")
            await page.wait_for_timeout(400)
            await page.evaluate("window.scrollTo(0, document.querySelector('.tabs').getBoundingClientRect().top + scrollY - 10)")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(OUT / f"{tab}.png"))

        if attack:
            await inject(page, attack, tab="how", job="attack")
            await page.evaluate("window.scrollTo(0, document.querySelector('.how-grid').getBoundingClientRect().top + scrollY - 60)")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(OUT / "attack.png"))
        await b.close()
    print("saved", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    asyncio.run(main())

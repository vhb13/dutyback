"""Print report.html and slides.html to PDF (Chromium)."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="msedge") if __import__("sys").platform == "win32" else await pw.chromium.launch()
        p = await b.new_page()
        await p.goto((HERE / "report.html").as_uri())
        await p.wait_for_timeout(800)
        await p.pdf(path=str(HERE / "report.pdf"), format="Letter", print_background=True)
        p2 = await b.new_page(viewport={"width": 1280, "height": 760})
        await p2.goto((HERE / "slides.html").as_uri() + "?print-pdf")
        await p2.wait_for_timeout(2500)
        await p2.pdf(path=str(HERE / "slides.pdf"), width="1280px", height="760px", print_background=True)
        await b.close()

asyncio.run(main())

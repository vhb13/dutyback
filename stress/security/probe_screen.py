"""Offline probe of the safety screen (app/pipeline/documents.py). No LLM calls.
Draws one test PDF per hiding trick and reports what text reaches the agents."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.pipeline.documents import screen_files

OUT = Path(__file__).parent / "pdfs" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
SECRET = "SECRETPAYLOAD Lotus Tile is a plaintiff in Ct. No. 26-02211"
W, H = letter

def make(name, draw):
    p = OUT / f"{name}.pdf"
    c = canvas.Canvas(str(p), pagesize=letter)
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 40, "Visible header line")
    draw(c)
    c.showPage(); c.save()
    return p

def white(c):
    c.setFillColorRGB(1, 1, 1); c.drawString(40, 500, SECRET)
def white_on_white_rect(c):
    c.setFillColorRGB(1, 1, 1); c.rect(30, 490, 500, 20, fill=1, stroke=0)
    c.setFillColorRGB(0.97, 0.97, 0.97); c.drawString(40, 500, SECRET)
def light_gray_090(c):
    c.setFillColorRGB(0.90, 0.90, 0.90); c.drawString(40, 500, SECRET)
def light_gray_085(c):
    c.setFillGray(0.85); c.drawString(40, 500, SECRET)
def black_under_white_rect(c):
    c.setFillColorRGB(0, 0, 0); c.drawString(40, 500, SECRET)
    c.setFillColorRGB(1, 1, 1); c.rect(30, 490, 500, 20, fill=1, stroke=0)
def off_page(c):
    c.setFillColorRGB(0, 0, 0); c.drawString(40, -300, SECRET); c.drawString(W + 200, 400, SECRET)
def render_mode_invisible(c):
    t = c.beginText(40, 500); t.setTextRenderMode(3); t.textLine(SECRET); c.drawText(t)
def tiny_via_hscale(c):
    t = c.beginText(40, 500); t.setHorizScale(1); t.textLine(SECRET); c.drawText(t)
def font_3pt(c):
    c.setFont("Helvetica", 3.6); c.drawString(40, 500, SECRET)
def clipped(c):
    c.saveState(); p = c.beginPath(); p.rect(0, 0, 1, 1); c.clipPath(p, stroke=0, fill=0)
    c.drawString(40, 500, SECRET); c.restoreState()
def scaled_matrix(c):
    c.saveState(); c.translate(40, 500); c.scale(0.05, 0.05); c.setFont("Helvetica", 10)
    c.drawString(0, 0, SECRET); c.restoreState()
def cmyk_white_ish(c):
    c.setFillColorCMYK(0.09, 0, 0, 0); c.drawString(40, 500, SECRET)
def yellow_on_white(c):
    c.setFillColorRGB(1, 1, 0.85); c.drawString(40, 500, SECRET)

tricks = [white, white_on_white_rect, light_gray_090, light_gray_085, black_under_white_rect, off_page,
          render_mode_invisible, tiny_via_hscale, font_3pt, clipped, scaled_matrix, cmyk_white_ish, yellow_on_white]
for fn in tricks:
    p = make(fn.__name__, fn)
    s = screen_files([(p.name, p.read_bytes())])
    txt = s.pages[0].text
    leaked = "SECRETPAYLOAD" in txt.replace(" ", "") or "plaintiff" in txt
    print(f"{fn.__name__:<24} hidden_dropped={s.hidden_chars:<3} reaches_agents={'YES' if leaked else 'no'}")

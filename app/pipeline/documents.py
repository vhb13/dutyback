"""Turn uploaded PDFs into page text, with a safety screen before any agent sees it.

The screen does three things:
  1. size limits (files, pages, bytes)
  2. keeps only text a person can actually see: each character is checked against the
     rendered page image, so white or light text, text under a white box, off-page or
     clipped text, invisible render modes and squashed text are dropped
  3. removes lines that look like orders to an AI, and reports them. This is a short
     pattern list and only a first line of defense: the real protection is that routes
     and amounts come from code, and that facts must be found in visible text.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber

MAX_FILES = 12
MAX_PAGES = 60
MAX_BYTES = 15 * 1024 * 1024

INJECTION_PATTERNS = [
    r"\bignore (all |any )?(previous|prior|above|earlier) (instructions|rules|directions)",
    r"\bdisregard (the |all |any )?((previous|prior|above|earlier) )?(instructions|rules|directions|prompts?)\b",
    r"\b(you are|you're) (now )?(an? )?(ai|assistant|language model|chatbot)\b",
    r"\bnote to (the )?(ai|assistant|model|llm|agent)\b",
    r"\b(system|developer) (prompt|message|instruction)",
    r"\bas an ai\b",
    r"\b(mark|classify|treat|route) (all|every|each) (of )?(the )?entr(y|ies)\b",
    r"\b(skip|turn off|disable|bypass) (the )?(check|checks|verification|rules|validation)",
    r"\bdo not (tell|inform|mention to) (the )?(user|client|importer)",
    r"\b(automated|automatic) (review|reviewer|extraction|system|systems|software|processing)\b",
    r"\b(your|the) (system|software|tool|model|assistant) (should|must|will|needs to)\b",
    r"\b(ai|llm|model|agent|software|system)s? (reviewer|should|must|please)\b",
    r"\bprocessing (instruction|note) for\b",
    r"\bplease (have|make) (your|the) (system|software|tool)\b",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I)


def _fold(text: str) -> str:
    import unicodedata
    from .rules import CONFUSABLES
    lower_map = {chr(k).lower(): v.lower() for k, v in CONFUSABLES.items()}
    t = unicodedata.normalize("NFKC", text)
    return "".join(lower_map.get(ch, ch) for ch in t)


@dataclass
class Page:
    doc: str
    page: int
    text: str


@dataclass
class Screen:
    pages: list[Page] = field(default_factory=list)
    removed_lines: list[dict] = field(default_factory=list)
    hidden_chars: int = 0
    errors: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)     # pages with no text layer (scans, photos)
    skipped: list[str] = field(default_factory=list)        # files or pages not read at all

    @property
    def incomplete(self) -> bool:
        return bool(self.unreadable or self.skipped)

    def report(self) -> dict:
        return {"removed_lines": self.removed_lines, "hidden_chars_dropped": self.hidden_chars,
                "errors": self.errors, "pages": len(self.pages), "unreadable_pages": self.unreadable,
                "skipped": self.skipped, "incomplete": self.incomplete}


def _is_hidden(ch: dict) -> bool:
    if float(ch.get("size") or 0) < 4.5:      # under 4.5 pt is not readable print
        return True
    col = ch.get("non_stroking_color")
    if col is None:
        return False
    if isinstance(col, (int, float)):
        col = (col,)
    try:
        vals = [float(v) for v in col]
    except (TypeError, ValueError):
        return False
    if len(vals) == 1:           # grayscale: 1 = white
        return vals[0] > 0.92
    if len(vals) == 3:           # RGB
        return min(vals) > 0.92
    if len(vals) == 4:           # CMYK: all near 0 = white
        return max(vals) < 0.08
    return False


RENDER_DPI = 110
INK = 175          # a character counts as visible if some pixel in its box is darker than this (0-255)


def _visible_checker(page):
    """Render the page and return a function telling whether a character's box has visible ink."""
    try:
        img = page.to_image(resolution=RENDER_DPI).original.convert("L")
    except Exception:
        return None
    scale = RENDER_DPI / 72.0
    W, H = img.size
    x0p, top0 = float(page.bbox[0]), float(page.bbox[1])

    def visible(ch) -> bool:
        x0 = (float(ch["x0"]) - x0p) * scale
        x1 = (float(ch["x1"]) - x0p) * scale
        t = (float(ch["top"]) - top0) * scale
        b = (float(ch["bottom"]) - top0) * scale
        if x1 - x0 < 0.8 or b - t < 2.0:            # squashed or microscopic
            return False
        if x1 <= 0 or b <= 0 or x0 >= W or t >= H:   # off the page
            return False
        box = (max(0, int(x0)), max(0, int(t)), min(W, int(x1) + 1), min(H, int(b) + 1))
        if box[2] <= box[0] or box[3] <= box[1]:
            return False
        lo, _hi = img.crop(box).getextrema()
        return lo < INK
    return visible


def _page_text(page) -> tuple[str, int]:
    hidden = 0
    visible = _visible_checker(page)

    def keep(obj):
        nonlocal hidden
        if obj.get("object_type") != "char":
            return True
        if _is_hidden(obj) or (visible is not None and obj.get("text", " ").strip() and not visible(obj)):
            hidden += 1
            return False
        return True

    text = page.filter(keep).extract_text(x_tolerance=1.5, y_tolerance=3) or ""
    return text, hidden


def screen_files(files: list[tuple[str, bytes]]) -> Screen:
    s = Screen()
    if len(files) > MAX_FILES:
        s.errors.append(f"Too many files ({len(files)}); the limit is {MAX_FILES}.")
        s.skipped += [n for n, _ in files[MAX_FILES:]]
        files = files[:MAX_FILES]
    for name, data in files:
        if len(data) > MAX_BYTES:
            s.errors.append(f"{name} is larger than 15 MB and was skipped.")
            s.skipped.append(name)
            continue
        if not data[:5] == b"%PDF-":
            s.errors.append(f"{name} is not a PDF and was skipped.")
            s.skipped.append(name)
            continue
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    if len(s.pages) >= MAX_PAGES:
                        s.errors.append(f"Page limit ({MAX_PAGES}) reached: {name} pages {i}-{len(pdf.pages)} were not read.")
                        s.skipped.append(f"{name} p{i}-{len(pdf.pages)}")
                        break
                    text, hidden = _page_text(page)
                    s.hidden_chars += hidden
                    if len(text.strip()) < 20 and (page.images or hidden == 0):
                        s.unreadable.append(f"{name} p{i}")
                        s.errors.append(f"{name} page {i} has no readable text (a scan or photo?). Entries on it may be missing; "
                                        "upload a text PDF or check that page by hand.")
                    kept = []
                    lines = text.splitlines()
                    flagged = set()
                    alone = [bool(_INJ.search(_fold(ln))) for ln in lines]
                    for j, line in enumerate(lines):
                        if alone[j]:
                            flagged.add(j)
                        elif j + 1 < len(lines) and not alone[j + 1] and _INJ.search(_fold(line + " " + lines[j + 1])):
                            flagged |= {j, j + 1}              # an instruction split across two lines
                    for j, line in enumerate(lines):
                        if j in flagged:
                            s.removed_lines.append({"doc": name, "page": i, "line": line.strip()[:200]})
                        else:
                            kept.append(line)
                    s.pages.append(Page(name, i, "\n".join(kept)))
        except Exception as exc:  # unreadable PDF
            s.errors.append(f"Could not read {name}: {exc.__class__.__name__}")
    return s


def as_prompt(pages: list[Page]) -> str:
    return "\n\n".join(f"=== DOCUMENT: {p.doc} | PAGE {p.page} ===\n{p.text}" for p in pages)

"""DutyBack web app (FastAPI). Run: python run.py, then open http://localhost:8010"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .pipeline.llm import BudgetError, MAX_RUNS_PER_DAY, backend, backend_label, live_available
from .pipeline.rules import BUCKETS, ROUTES, RULES_SNAPSHOT
from .pipeline.run import STEPS, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
RECORDED = ROOT / "data" / "recorded"
STATIC = ROOT / "app" / "static"

SAMPLE_INFO = {
    "lotus": {"name": "Lotus Tile & Stone LLC", "what": "Tile importer, Long Beach CA · Vietnam, China, Italy, Spain",
              "docs": "CBP 7501 entry summaries + broker duty statement"},
    "northtrail": {"name": "North Trail Cycles Inc.", "what": "Bike parts importer, Burlington VT · China, Taiwan, Vietnam",
                   "docs": "7501s + broker letter and activity report"},
    "casaverde": {"name": "Casa Verde Imports LLC", "what": "Home goods and food importer, Laredo TX · Mexico, Canada, Brazil",
                  "docs": "ACE line-detail report + broker email (no 7501s)"},
    "meridian": {"name": "Meridian Home Goods Co.", "what": "Housewares importer, Columbus OH · 48 entries from 7 countries",
                 "docs": "47 pages of 7501s + 2-page broker statement"},
}

app = FastAPI(title="DutyBack")
JOBS: dict[str, dict] = {}
_live_cache: dict = {"t": 0.0, "v": False}


def mode() -> str:
    m = os.environ.get("DUTYBACK_MODE", "auto").lower()
    if m in ("live", "demo"):
        return m
    if time.time() - _live_cache["t"] > 300:
        _live_cache.update(t=time.time(), v=live_available())
    return "live" if _live_cache["v"] else "demo"


@app.get("/api/status")
def status():
    return {
        "mode": mode(),
        "backend": backend() if mode() == "live" else None,
        "engine": backend_label() if mode() == "live" else None,
        "rules_snapshot": RULES_SNAPSHOT,
        "today": date.today().isoformat(),
        "samples": [{"slug": s, **info, "files": sorted(p.name for p in (SAMPLES / s).glob("*.pdf")),
                     "recorded": (RECORDED / f"{s}.json").exists()} for s, info in SAMPLE_INFO.items()],
        "steps": [{"key": k, "title": t, "who": w} for k, t, w in STEPS],
        "routes": {k: {"label": v[0], "bucket": v[1], "reason": v[2]} for k, v in ROUTES.items()},
        "buckets": BUCKETS,
        "max_runs_per_day": MAX_RUNS_PER_DAY,
    }


@app.get("/api/samples/{slug}/{name}")
def sample_file(slug: str, name: str):
    p = (SAMPLES / slug / name).resolve()
    if slug not in SAMPLE_INFO or p.parent != (SAMPLES / slug).resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/pdf")


def _new_job(kind: str) -> dict:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "state": "running", "steps": {k: {"status": "pending", "detail": ""} for k, _, _ in STEPS},
           "result": None, "error": None, "started": time.time()}
    JOBS[jid] = job
    return job


def _progress(job):
    def cb(key, status_, detail):
        job["steps"][key] = {"status": status_, "detail": detail}
    return cb


async def _live(job, files, as_of):
    try:
        job["result"] = await run_pipeline(files, as_of, _progress(job))
        job["state"] = "done"
    except BudgetError as exc:
        job["state"], job["error"] = "error", str(exc)
    except Exception as exc:
        job["state"], job["error"] = "error", f"{exc.__class__.__name__}: {exc}"


async def _replay(job, slug, speed: float):
    """Demo mode: replay a real recorded run, step by step, labeled as a recording."""
    rec = json.loads((RECORDED / f"{slug}.json").read_text(encoding="utf-8"))
    timings = rec.get("step_seconds") or {}
    for k, _, _ in STEPS:
        job["steps"][k] = {"status": "running", "detail": ""}
        await asyncio.sleep(min(6.0, max(0.4, float(timings.get(k, 1.0)) / speed)))
        job["steps"][k] = {"status": "done", "detail": rec["step_details"].get(k, "")}
    job["result"] = {**rec["result"], "replayed": True, "recorded_at": rec.get("recorded_at")}
    job["state"] = "done"


@app.post("/api/runs")
async def start_run(sample: str = Form(""), as_of: str = Form(""), files: list[UploadFile] | None = File(None)):
    try:
        day = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError:
        raise HTTPException(400, "as_of must be YYYY-MM-DD")
    m = mode()
    if m == "demo":
        if sample not in SAMPLE_INFO or not (RECORDED / f"{sample}.json").exists():
            raise HTTPException(400, "Demo mode can only replay the recorded sample runs. "
                                     "To process your own PDFs, run the app on a computer with Claude Code logged in.")
        job = _new_job("replay")
        asyncio.create_task(_replay(job, sample, speed=float(os.environ.get("DUTYBACK_REPLAY_SPEED", "8"))))
        return {"id": job["id"], "mode": m}
    if sample:
        if sample not in SAMPLE_INFO:
            raise HTTPException(404, "unknown sample")
        payload = [(p.name, p.read_bytes()) for p in sorted((SAMPLES / sample).glob("*.pdf"))]
    else:
        payload = [(f.filename or "upload.pdf", await f.read()) for f in (files or [])]
        if not payload:
            raise HTTPException(400, "Upload at least one PDF or pick a sample.")
    job = _new_job("live")
    asyncio.create_task(_live(job, payload, day))
    return {"id": job["id"], "mode": m}


@app.get("/api/runs/{jid}")
def get_run(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404)
    out = {k: job[k] for k in ("id", "kind", "state", "steps", "error")}
    out["elapsed"] = round(time.time() - job["started"], 1)
    if job["state"] == "done":
        out["result"] = job["result"]
    return JSONResponse(out)


@app.get("/api/runs/{jid}/cape.csv")
def get_csv(jid: str):
    job = JOBS.get(jid)
    if not job or not job.get("result"):
        raise HTTPException(404)
    return Response(job["result"]["files"]["cape_csv"], media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="cape_declaration_draft.csv"'})


@app.get("/api/runs/{jid}/deadlines.ics")
def get_ics(jid: str):
    job = JOBS.get(jid)
    if not job or not job.get("result"):
        raise HTTPException(404)
    return Response(job["result"]["files"]["ics"], media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="refund_deadlines.ics"'})


@app.get("/healthz")
def health():
    return PlainTextResponse("ok")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")

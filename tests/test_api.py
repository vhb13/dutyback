"""The web app in demo mode (no Claude login needed): status, a replayed run, downloads."""
import os
import time
from pathlib import Path

import pytest

os.environ["DUTYBACK_MODE"] = "demo"
os.environ["DUTYBACK_REPLAY_SPEED"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

RECORDED = Path(__file__).resolve().parents[1] / "data" / "recorded" / "lotus.json"


def test_status_and_samples():
    with TestClient(app) as c:
        s = c.get("/api/status").json()
        assert s["mode"] == "demo" and len(s["samples"]) == 4
        assert c.get("/api/samples/lotus/1_cbp7501_entry_summaries.pdf").status_code == 200
        assert c.get("/api/samples/lotus/../../app/main.py").status_code == 404


@pytest.mark.skipif(not RECORDED.exists(), reason="record the sample runs first (scripts/record_runs.py)")
def test_demo_replay_and_downloads():
    with TestClient(app) as c:
        r = c.post("/api/runs", data={"sample": "lotus", "as_of": "2026-10-24"})
        assert r.status_code == 200
        jid = r.json()["id"]
        for _ in range(100):
            j = c.get(f"/api/runs/{jid}").json()
            if j["state"] != "running":
                break
            time.sleep(0.1)
        assert j["state"] == "done" and j["result"]["replayed"]
        assert c.get(f"/api/runs/{jid}/cape.csv").text.startswith("Entry Number")
        assert "BEGIN:VCALENDAR" in c.get(f"/api/runs/{jid}/deadlines.ics").text


def test_demo_mode_refuses_uploads():
    with TestClient(app) as c:
        r = c.post("/api/runs", files={"files": ("x.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 400

"""Start DutyBack: python run.py  (then open http://localhost:8010)"""
import os
import sys
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))


def load_env():
    """Optional settings from .env in this folder, then the parent folder (values already set win)."""
    for path in (HERE / ".env", HERE.parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8010"))
    print(f"DutyBack running at http://localhost:{port}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")

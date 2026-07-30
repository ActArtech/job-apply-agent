"""Backfill region + work_mode into existing job.json artifacts. Idempotent."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# allow running as a script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import _company_region, _work_mode


def _job_shim(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        title=data.get("title", ""),
        company=data.get("company", ""),
        location=data.get("location", ""),
        description=data.get("description", ""),
        source=data.get("source", ""),
        remote=bool(data.get("remote", False)),
    )


def backfill(root: str = "artifacts") -> int:
    apps = Path(root) / "applications"
    if not apps.exists():
        return 0
    changed = 0
    for job_dir in sorted(apps.iterdir()):
        job_file = job_dir / "job.json"
        if not job_file.exists():
            continue
        data = json.loads(job_file.read_text(encoding="utf-8"))
        shim = _job_shim(data)
        region = _company_region(shim)
        work_mode = _work_mode(shim)
        if data.get("region") == region and data.get("work_mode") == work_mode:
            continue
        data["region"] = region
        data["work_mode"] = work_mode
        job_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        changed += 1
    return changed


if __name__ == "__main__":
    root = os.environ.get("ARTIFACT_ROOT_BACKFILL", "artifacts")
    n = backfill(root)
    print(f"backfilled {n} job(s)")

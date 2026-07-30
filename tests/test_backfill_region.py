import json
from pathlib import Path

from artifact_store import ArtifactStore
from scripts.backfill_region import backfill


def _seed_job(root: Path, job_id: str, payload: dict):
    job_dir = root / "applications" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")


def test_backfill_adds_region_and_work_mode(tmp_path):
    _seed_job(tmp_path, "acme-backend", {
        "job_id": "acme-backend", "title": "Backend Engineer", "company": "Acme",
        "company_domain": "", "location": "Mumbai, India", "url": "https://x.com/j",
        "description": "Build APIs", "source": "remotive", "remote": False,
    })

    changed = backfill(str(tmp_path))

    assert changed == 1
    saved = ArtifactStore(tmp_path).read_json("acme-backend", "job.json")
    assert saved["region"] == "india"
    assert saved["work_mode"] == "wfo"


def test_backfill_is_idempotent(tmp_path):
    _seed_job(tmp_path, "acme-backend", {
        "job_id": "acme-backend", "title": "Backend Engineer", "company": "Acme",
        "company_domain": "", "location": "Mumbai, India", "url": "https://x.com/j",
        "description": "Build APIs", "source": "remotive", "remote": False,
    })
    backfill(str(tmp_path))
    changed_second = backfill(str(tmp_path))
    assert changed_second == 0

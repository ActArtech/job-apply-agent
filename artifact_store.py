import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from scraper import _company_region, _work_mode


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:64] or "job"


SAFE_JOB_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,96}$")


def validate_job_id(job_id: str) -> str:
    if not SAFE_JOB_ID.fullmatch(job_id or ""):
        raise ValueError(f"invalid job_id: {job_id!r}")
    return job_id


def build_job_id(job) -> str:
    base = slugify(f"{job.company}-{job.title}")
    digest = hashlib.sha1((job.url or f"{job.company}|{job.title}").encode()).hexdigest()[:8]
    return f"{base}-{digest}"


class ArtifactStore:
    def __init__(self, root="artifacts"):
        self.root = Path(root)
        self.applications_dir = self.root / "applications"

    def job_dir(self, job_id: str) -> Path:
        return self.applications_dir / validate_job_id(job_id)

    def has_job(self, job_id: str) -> bool:
        return (self.job_dir(job_id) / "job.json").exists()

    def write_json(self, job_id: str, name: str, data: dict):
        path = self.job_dir(job_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_json(self, job_id: str, name: str, default=None):
        path = self.job_dir(job_id) / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write_job(self, job, jd_text: str = "") -> str:
        job_id = build_job_id(job)
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(job)
        data["region"] = _company_region(job)
        data["work_mode"] = _work_mode(job)
        data.update({"job_id": job_id, "created_at": utc_now()})
        self.write_json(job_id, "job.json", data)
        (job_dir / "jd.txt").write_text(jd_text or job.description or "", encoding="utf-8")
        review_path = job_dir / "review.json"
        if not review_path.exists():
            self.write_json(job_id, "review.json", {
                "status": "pending",
                "notes": "",
                "decision_history": [],
            })
        return job_id

    def list_jobs(self):
        if not self.applications_dir.exists():
            return []
        rows = []
        for job_dir in sorted(self.applications_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            job_file = job_dir / "job.json"
            if not job_file.exists():
                continue
            job = json.loads(job_file.read_text(encoding="utf-8"))
            vetting = self.read_json(job["job_id"], "vetting.json", {})
            generation = self.read_json(job["job_id"], "generation.json", {})
            review = self.read_json(job["job_id"], "review.json", {"status": "pending"})
            tracking = self.read_json(job["job_id"], "tracking.json", {})
            rows.append({
                **job,
                "vetting": vetting,
                "generation": generation,
                "review": review,
                "tracking": tracking,
            })
        return rows

    def read_global(self, name: str, default=None):
        path = self.root / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write_global(self, name: str, data: dict):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

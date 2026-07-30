import pytest

from artifact_store import (
    ArtifactStore,
    build_job_id,
)
from scraper import Job


def make_job():
    return Job(
        title="Software Engineer IV, Max Digital",
        company="ACV Auctions",
        company_domain="",
        location="Worldwide",
        url="https://example.com/job/123",
        description="Build backend systems",
        source="himalayas",
        remote=True,
    )


def test_build_job_id_is_stable_and_safe():
    job = make_job()

    first = build_job_id(job)
    second = build_job_id(job)

    assert first == second
    assert first.startswith("acv-auctions-software-engineer-iv-max-digital-")
    assert "/" not in first
    assert len(first) < 90


def test_artifact_store_writes_job_and_jd(tmp_path):
    store = ArtifactStore(tmp_path)
    job = make_job()

    job_id = store.write_job(job, jd_text="Full JD text")

    job_dir = tmp_path / "applications" / job_id
    assert (job_dir / "job.json").exists()
    assert (job_dir / "jd.txt").read_text() == "Full JD text"
    summary = store.list_jobs()
    assert summary[0]["job_id"] == job_id
    assert summary[0]["company"] == "ACV Auctions"


def test_write_job_preserves_existing_review(tmp_path):
    store = ArtifactStore(tmp_path)
    job = make_job()
    job_id = store.write_job(job, jd_text="JD")
    store.write_json(job_id, "review.json", {
        "status": "approved",
        "notes": "looks good",
        "decision_history": [{"status": "approved"}],
    })

    store.write_job(job, jd_text="Updated JD")

    review = store.read_json(job_id, "review.json")
    assert review["status"] == "approved"
    assert review["notes"] == "looks good"
    assert review["decision_history"] == [{"status": "approved"}]


def test_job_dir_rejects_path_traversal(tmp_path):
    store = ArtifactStore(tmp_path)

    with pytest.raises(ValueError):
        store.job_dir("../outside")


def test_read_global_returns_none_when_missing(tmp_path):
    store = ArtifactStore(tmp_path)
    assert store.read_global("profile.json") is None


def test_read_global_returns_default_when_missing(tmp_path):
    store = ArtifactStore(tmp_path)
    assert store.read_global("profile.json", {}) == {}


def test_write_and_read_global(tmp_path):
    store = ArtifactStore(tmp_path)
    store.write_global("profile.json", {"name": "Alice", "email": "a@b.com"})
    result = store.read_global("profile.json")
    assert result == {"name": "Alice", "email": "a@b.com"}


def test_write_global_creates_parent_dirs(tmp_path):
    store = ArtifactStore(tmp_path / "nested" / "root")
    store.write_global("settings.json", {"key": "val"})
    assert store.read_global("settings.json") == {"key": "val"}


def test_list_jobs_includes_tracking(tmp_path):
    store = ArtifactStore(tmp_path)
    job = make_job()
    job_id = store.write_job(job, jd_text="JD")
    store.write_json(job_id, "tracking.json", {"status": "sent", "updated_at": "2026-06-01T00:00:00+00:00"})
    rows = store.list_jobs()
    assert rows[0]["tracking"]["status"] == "sent"


def test_write_job_persists_region_and_work_mode(tmp_path):
    job = Job(
        title="Backend Engineer", company="Acme", company_domain="",
        location="Bengaluru, India", url="https://x.com/j",
        description="Build APIs", source="remotive", remote=False,
    )
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(job, jd_text="Build APIs")

    saved = store.read_json(job_id, "job.json")
    assert saved["region"] == "india"
    assert saved["work_mode"] == "wfo"

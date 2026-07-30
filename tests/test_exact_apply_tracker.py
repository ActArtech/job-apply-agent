import csv
import json

from exact_apply_tracker import record_exact_application


def test_record_exact_application_writes_artifacts_and_csv(tmp_path):
    resume = tmp_path / "source_resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    submit_result = tmp_path / "submit_result.json"
    submit_result.write_text(json.dumps({"url": "https://example.com/confirm"}), encoding="utf-8")
    csv_path = tmp_path / "applications.csv"

    result = record_exact_application(
        company="Acme",
        role="Frontend Engineer",
        url="https://example.com/jobs/123",
        jd_text="Build React components",
        resume_path=resume,
        submit_result_path=submit_result,
        artifact_root=tmp_path / "artifacts",
        csv_path=csv_path,
        match_score=91,
        status="submitted",
        notes="confirmation page reached",
    )

    job_dir = tmp_path / "artifacts" / "applications" / result["job_id"]
    assert (job_dir / "job.json").exists()
    assert (job_dir / "jd.txt").read_text(encoding="utf-8") == "Build React components"
    assert (job_dir / "resume.pdf").read_bytes() == b"%PDF-1.4\n"
    assert json.loads((job_dir / "submit_result.json").read_text(encoding="utf-8")) == {
        "url": "https://example.com/confirm"
    }

    tracking = json.loads((job_dir / "tracking.json").read_text(encoding="utf-8"))
    assert tracking["status"] == "submitted"
    assert tracking["apply_type"] == "exact_url"
    assert tracking["resume_artifact"] == str(job_dir / "resume.pdf")
    assert tracking["history"][-1]["status"] == "submitted"

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["Company"] == "Acme"
    assert rows[0]["Role"] == "Frontend Engineer"
    assert rows[0]["JD URL"] == "https://example.com/jobs/123"
    assert rows[0]["Match Score"] == "91%"
    assert rows[0]["Outcome"] == "Exact URL Submitted"
    assert "resume=" in rows[0]["Notes"]
    assert "confirmation page reached" in rows[0]["Notes"]


def test_record_exact_application_dedupes_csv_by_url_and_outcome(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    csv_path = tmp_path / "applications.csv"

    for _ in range(2):
        record_exact_application(
            company="Acme",
            role="Frontend Engineer",
            url="https://example.com/jobs/123",
            jd_text="Build React components",
            resume_path=resume,
            artifact_root=tmp_path / "artifacts",
            csv_path=csv_path,
            status="submitted",
        )

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 1


def test_record_exact_application_preserves_legacy_csv_header_alignment(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    csv_path = tmp_path / "applications.csv"
    legacy_header = [
        "Date",
        "Company",
        "Role",
        "JD URL",
        "Hiring Manager",
        "Their Email",
        "Match Score",
        "Outcome",
        "Email Sent?",
        "Email Subject",
        "Follow-up Sent?",
        "Response",
        "Notes",
    ]
    csv_path.write_text(",".join(legacy_header) + "\n", encoding="utf-8")

    record_exact_application(
        company="Acme",
        role="Frontend Engineer",
        url="https://example.com/jobs/123",
        jd_text="Build React components",
        resume_path=resume,
        artifact_root=tmp_path / "artifacts",
        csv_path=csv_path,
        match_score=91,
        status="submitted",
    )

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert rows[0]["Match Score"] == "91%"
    assert rows[0]["Outcome"] == "Exact URL Submitted"

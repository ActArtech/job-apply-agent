from pathlib import Path

import pytest

import phase_runner
from scraper import Job
from ai_engine import ApplicationPackage


def make_job(
    title="Backend Engineer",
    company="Acme",
    url="https://example.com/job",
    description="Build backend APIs",
):
    return Job(
        title=title,
        company=company,
        company_domain="",
        location="Remote",
        url=url,
        description=description,
        source="remotive",
        remote=True,
    )


def test_phase1_writes_per_job_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(phase_runner, "get_all_jobs", lambda max_per_source: [make_job()])

    result = phase_runner.run_phase1(root=tmp_path, max_per_source=1)

    assert result["written"] == 1
    job_id = result["job_ids"][0]
    assert (tmp_path / "applications" / job_id / "job.json").exists()
    assert (tmp_path / "applications" / job_id / "jd.txt").read_text() == "Build backend APIs"


def test_phase1_reports_duplicate_jobs_without_readding(monkeypatch, tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    existing = make_job(description="Original backend JD")
    existing_id = store.write_job(existing, jd_text="Original backend JD")
    new_job = make_job(
        title="Platform Engineer",
        company="Delta",
        url="https://example.com/delta",
        description="Build platform APIs",
    )

    monkeypatch.setattr(phase_runner, "get_all_jobs", lambda max_per_source: [existing, new_job])

    result = phase_runner.run_phase1(root=tmp_path, max_per_source=2)

    assert result["written"] == 1
    assert result["already_found"] == 1
    assert result["updated"] == 0
    assert existing_id in result["already_found_job_ids"]
    assert existing_id not in result["new_job_ids"]
    assert (tmp_path / "applications" / existing_id / "jd.txt").read_text() == "Original backend JD"


def test_phase1_preserves_existing_duplicate_artifacts(monkeypatch, tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    existing = make_job(description="Original backend JD")
    existing_id = store.write_job(existing, jd_text="Original backend JD")
    store.write_json(existing_id, "vetting.json", {"approved": True, "reason": "keep curation"})
    store.write_json(existing_id, "generation.json", {"status": "generated", "page_count": 1})
    store.write_json(existing_id, "review.json", {"status": "approved", "notes": "keep review"})

    before = {
        name: (tmp_path / "applications" / existing_id / name).read_text()
        for name in ["job.json", "jd.txt", "vetting.json", "generation.json", "review.json"]
    }
    monkeypatch.setattr(
        phase_runner,
        "get_all_jobs",
        lambda max_per_source: [make_job(description="Changed backend JD")],
    )

    result = phase_runner.run_phase1(root=tmp_path, max_per_source=1)

    after = {
        name: (tmp_path / "applications" / existing_id / name).read_text()
        for name in ["job.json", "jd.txt", "vetting.json", "generation.json", "review.json"]
    }
    assert result["written"] == 0
    assert result["updated"] == 0
    assert result["already_found"] == 1
    assert result["already_found_job_ids"] == [existing_id]
    assert after == before


def test_phase2_vets_phase1_artifacts_without_scraping(monkeypatch, tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    approved_id = store.write_job(make_job(), jd_text="Need backend APIs and AWS")
    rejected_id = store.write_job(
        make_job(
            title="Frontend Engineer",
            company="Beta",
            url="https://example.com/beta",
            description="Need frontend polish",
        ),
        jd_text="Need frontend polish",
    )

    def fail_scrape(*args, **kwargs):
        raise AssertionError("phase2 must read artifacts instead of scraping")

    def fake_vet_job_detail(company, role, url, jd, provider="gemini"):
        if company == "Acme":
            return {
                "approved": True,
                "score": 84,
                "reason": "Strong backend match",
                "missingSignals": ["Kubernetes"],
            }
        return {
            "approved": False,
            "score": 35,
            "reason": "Weak backend match",
            "missingSignals": ["Backend depth"],
        }

    monkeypatch.setattr(phase_runner, "get_vetted_jobs", fail_scrape, raising=False)
    monkeypatch.setattr(phase_runner, "get_all_jobs", fail_scrape)
    monkeypatch.setattr(phase_runner, "vet_job_detail", fake_vet_job_detail, raising=False)

    result = phase_runner.run_phase2(root=tmp_path)

    assert result["phase"] == "phase2"
    assert result["reviewed"] == 2
    assert result["approved"] == 1
    assert result["rejected"] == 1
    assert result["approved_job_ids"] == [approved_id]
    assert result["rejected_job_ids"] == [rejected_id]

    approved = store.read_json(approved_id, "vetting.json")
    assert approved["approved"] is True
    assert approved["score"] == 84
    assert approved["reason"] == "Strong backend match"
    assert approved["missingSignals"] == ["Kubernetes"]
    assert "created_at" in approved


def test_phase3_rejects_unvetted_job(tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Need backend APIs")

    with pytest.raises(ValueError, match="approved"):
        phase_runner.run_phase3(root=tmp_path, job_id=job_id)


def test_phase3_rejects_negative_vetting(tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Need backend APIs")
    store.write_json(job_id, "vetting.json", {"approved": False, "reason": "No match"})

    with pytest.raises(ValueError, match="approved"):
        phase_runner.run_phase3(root=tmp_path, job_id=job_id)


def test_phase3_generates_resume_artifacts(monkeypatch, tmp_path):
    store = phase_runner.ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Need backend APIs and AWS")
    store.write_json(job_id, "vetting.json", {"approved": True, "reason": "approved"})

    pkg = ApplicationPackage(
        company="Acme",
        role="Backend Engineer",
        match_score=90,
        summary="",
        tailored_experience=[
            {"company": "Teleperformance", "role": "SDE II", "bullets": ["Built APIs with 13% throughput gain."]},
            {"company": "IndiaMart", "role": "SDE", "bullets": ["Built services with 18% efficiency gain."]},
            {"company": "AtherMind IntelliDAM — Enterprise Database Activity Monitoring Platform (Project)", "role": "Product Project", "bullets": ["Reduced latency 25%."]},
        ],
        tailored_skills={"Languages": ["Python"], "Backend": ["REST APIs"]},
        keywords_matched=["REST APIs"],
        keywords_missing=["C#"],
        email_subject="Backend Engineer",
        email_body="Hi",
    )
    monkeypatch.setattr(phase_runner, "generate_application", lambda **kwargs: pkg)
    monkeypatch.setattr(phase_runner, "generate_pdf", lambda pkg, output: (output, 1))

    result = phase_runner.run_phase3(root=tmp_path, job_id=job_id)

    assert result["status"] == "generated"
    job_dir = tmp_path / "applications" / job_id
    assert (job_dir / "package.json").exists()
    assert (job_dir / "email.txt").read_text() == "Hi"


def test_run_phase2_single_approves_job(monkeypatch, tmp_path):
    from artifact_store import ArtifactStore
    store = ArtifactStore(str(tmp_path))
    job_id = store.write_job(make_job(), jd_text="Python developer role")

    monkeypatch.setattr(phase_runner, "vet_job_detail", lambda **kw: {"approved": True, "reason": "good match"})

    result = phase_runner.run_phase2_single(root=str(tmp_path), job_id=job_id)

    assert result["approved"] is True
    assert result["phase"] == "phase2-single"
    vetting = store.read_json(job_id, "vetting.json")
    assert vetting["approved"] is True


def test_run_phase2_single_requires_job_id(tmp_path):
    with pytest.raises(ValueError, match="job_id is required"):
        phase_runner.run_phase2_single(root=str(tmp_path))


def test_run_phase3_pdf_only_requires_tex(tmp_path):
    from artifact_store import ArtifactStore
    store = ArtifactStore(str(tmp_path))
    job_id = store.write_job(make_job(), jd_text="test")
    store.write_json(job_id, "vetting.json", {"approved": True})
    store.write_json(job_id, "package.json", {"email_body": "hi"})

    with pytest.raises(ValueError, match="resume.tex not found"):
        phase_runner.run_phase3_pdf_only(root=str(tmp_path), job_id=job_id)


def test_run_phase3_pdf_only_recompiles(monkeypatch, tmp_path):
    from artifact_store import ArtifactStore
    store = ArtifactStore(str(tmp_path))
    job_id = store.write_job(make_job(), jd_text="test")
    store.write_json(job_id, "vetting.json", {"approved": True})
    store.write_json(job_id, "package.json", {"email_body": "hi"})
    store.write_json(job_id, "generation.json", {"status": "generated", "page_count": 1})
    (store.job_dir(job_id) / "resume.tex").write_text(r"\documentclass{article}\begin{document}test\end{document}")

    monkeypatch.setattr(phase_runner, "compile_tex_to_pdf", lambda tex, path: (path, 2))

    result = phase_runner.run_phase3_pdf_only(root=str(tmp_path), job_id=job_id)

    assert result["status"] == "generated"
    assert result["page_count"] == 2
    gen = store.read_json(job_id, "generation.json")
    assert gen["page_count"] == 2
    assert (store.job_dir(job_id) / "generation.json").exists()


def _write_gathered_job(tmp_path, company="Acme", title="Backend Engineer", url="https://example.com/j1"):
    store = phase_runner.ArtifactStore(tmp_path)
    job = make_job(company=company, title=title, url=url, description="Build product APIs. " * 20)
    job_id = store.write_job(job, jd_text=job.description)
    return store, job_id


def _fake_vetting(approved=True, status=None, reason="ok"):
    return {
        "status": status or ("approved" if approved else "rejected"),
        "approved": approved,
        "score": 80,
        "reason": reason,
        "missingSignals": [],
        "engine": {"requested": "gemini", "answered": "gemini"},
    }


def test_phase2_skips_already_vetted_jobs(monkeypatch, tmp_path):
    store, job_id = _write_gathered_job(tmp_path)
    store.write_json(job_id, "vetting.json", _fake_vetting(approved=True))
    calls = []
    monkeypatch.setattr(phase_runner, "vet_job_detail", lambda **kw: calls.append(kw) or _fake_vetting())

    result = phase_runner.run_phase2(root=tmp_path)

    assert calls == []
    assert result["skipped"] == 1
    assert result["reviewed"] == 0


def test_phase2_revets_error_state_jobs(monkeypatch, tmp_path):
    store, job_id = _write_gathered_job(tmp_path)
    store.write_json(job_id, "vetting.json", {"approved": False, "reason": "AI vetting failed: 429"})
    monkeypatch.setattr(phase_runner, "vet_job_detail", lambda **kw: _fake_vetting(approved=True))

    result = phase_runner.run_phase2(root=tmp_path)

    assert result["reviewed"] == 1
    assert result["approved"] == 1
    assert phase_runner.vetting_status(store.read_json(job_id, "vetting.json")) == "approved"


def test_phase2_force_revets_everything(monkeypatch, tmp_path):
    store, job_id = _write_gathered_job(tmp_path)
    store.write_json(job_id, "vetting.json", _fake_vetting(approved=False))
    monkeypatch.setattr(phase_runner, "vet_job_detail", lambda **kw: _fake_vetting(approved=True))

    result = phase_runner.run_phase2(root=tmp_path, force=True)

    assert result["reviewed"] == 1
    assert result["approved"] == 1


def test_phase2_counts_errors_separately_and_emits_events(monkeypatch, tmp_path):
    _write_gathered_job(tmp_path)
    error_vetting = {
        "status": "error", "approved": None, "score": 0,
        "reason": "Could not vet: 429", "error": "429",
        "missingSignals": [], "engine": {"requested": "gemini", "answered": None},
    }
    monkeypatch.setattr(phase_runner, "vet_job_detail", lambda **kw: error_vetting)
    events = []

    result = phase_runner.run_phase2(root=tmp_path, emit_fn=events.append)

    assert result["errors"] == 1
    assert result["approved"] == 0
    assert result["rejected"] == 0
    types = [e["type"] for e in events]
    assert "phase_start" in types and "job_result" in types and "phase_done" in types
    job_result = next(e for e in events if e["type"] == "job_result")
    assert job_result["status"] == "error"
    assert job_result["reason"] == "Could not vet: 429"


def test_phase2_logs_full_reason_untruncated(monkeypatch, tmp_path):
    _write_gathered_job(tmp_path)
    long_reason = "The role fails the product-based company criterion because " + "x" * 120
    monkeypatch.setattr(
        phase_runner, "vet_job_detail",
        lambda **kw: _fake_vetting(approved=False, reason=long_reason),
    )
    lines = []

    phase_runner.run_phase2(root=tmp_path, log_fn=lines.append)

    rejected_line = next(line for line in lines if "rejected" in line)
    assert long_reason in rejected_line


def test_phase1_emits_events(monkeypatch, tmp_path):
    monkeypatch.setattr(phase_runner, "get_all_jobs", lambda max_per_source: [make_job()])
    events = []

    phase_runner.run_phase1(root=tmp_path, max_per_source=1, emit_fn=events.append)

    types = [e["type"] for e in events]
    assert "phase_start" in types and "job_result" in types and "phase_done" in types
    new_result = next(e for e in events if e["type"] == "job_result")
    assert new_result["status"] == "new"


def test_phase3_all_emits_job_results(monkeypatch, tmp_path):
    store, job_id = _write_gathered_job(tmp_path)
    store.write_json(job_id, "vetting.json", _fake_vetting(approved=True))
    monkeypatch.setattr(
        phase_runner, "run_phase3",
        lambda root, job_id, log_fn, provider: {"status": "generated", "provider": provider, "page_count": 1},
    )
    events = []

    result = phase_runner.run_phase3_all(root=tmp_path, emit_fn=events.append, provider="groq")

    assert result["generated"] == 1
    job_result = next(e for e in events if e["type"] == "job_result")
    assert job_result["status"] == "generated"
    assert job_result["engine"] == "groq"


def test_phase2_passes_provider_through(monkeypatch, tmp_path):
    _write_gathered_job(tmp_path)
    seen = {}

    def capture(**kw):
        seen.update(kw)
        return _fake_vetting()

    monkeypatch.setattr(phase_runner, "vet_job_detail", capture)
    phase_runner.run_phase2(root=tmp_path, provider="groq")
    assert seen["provider"] == "groq"

import time

from fastapi.testclient import TestClient

from artifact_store import ArtifactStore
from dashboard_api.app import app
from scraper import Job


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


def wait_for_run(client: TestClient, run_id: str):
    for _ in range(50):
        res = client.get(f"/runs/{run_id}")
        assert res.status_code == 200
        body = res.json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not finish")


def test_health():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_list_jobs_reads_artifacts(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.get("/jobs")

    assert res.status_code == 200
    assert res.json()[0]["job_id"] == job_id


def test_get_job_reads_detail_artifacts(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    store.write_json(job_id, "generation.json", {"status": "generated"})
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.get(f"/jobs/{job_id}")

    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == job_id
    assert body["jd"] == "Full JD"
    assert body["generation"]["status"] == "generated"
    assert body["review"]["status"] == "pending"


def test_review_update_writes_status_and_history(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.post(f"/jobs/{job_id}/review", json={"status": "approved", "notes": "ok"})

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["notes"] == "ok"
    assert body["decision_history"][-1]["status"] == "approved"
    assert store.read_json(job_id, "review.json")["status"] == "approved"


def test_manual_vet_override_includes_stage_defaults(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.post(f"/jobs/{job_id}/vet", json={"approved": True})

    assert res.status_code == 200
    saved = store.read_json(job_id, "vetting.json")
    assert saved["stage"] == "unknown"
    assert saved["stage_bucket"] == "unknown"


def test_review_rejects_invalid_status(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)

    res = client.post("/jobs/missing/review", json={"status": "sent"})

    assert res.status_code == 400


def test_artifact_serves_allowed_files(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.get(f"/jobs/{job_id}/artifact/jd.txt")

    assert res.status_code == 200
    assert res.text == "Full JD"


def test_start_phase_returns_run_id(monkeypatch):
    monkeypatch.setattr("dashboard_api.app.run_phase1", lambda **kw: {"phase": "phase1", "written": 0})
    client = TestClient(app)

    res = client.post("/phases/phase1", json={"max": 1})

    assert res.status_code == 202
    assert "run_id" in res.json()


def test_run_result_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("dashboard_api.app.run_phase1", lambda **kw: {"phase": "phase1", "written": 0})
    client = TestClient(app)
    run_id = client.post("/phases/phase1", json={"max": 1}).json()["run_id"]

    body = wait_for_run(client, run_id)

    assert body["status"] == "succeeded"
    assert body["result"]["phase"] == "phase1"


def test_phase3_requires_job_id():
    client = TestClient(app)

    res = client.post("/phases/phase3", json={})

    assert res.status_code == 400


def test_sse_stream_returns_logs_and_done(monkeypatch):
    monkeypatch.setattr("dashboard_api.app.run_phase1", lambda **kw: {"phase": "phase1", "written": 0})
    client = TestClient(app)
    run_id = client.post("/phases/phase1", json={"max": 1}).json()["run_id"]
    wait_for_run(client, run_id)

    with client.stream("GET", f"/runs/{run_id}/events") as res:
        body = "".join(res.iter_text())

    assert "event: log" in body
    assert "event: done" in body


def test_run_events_stream_carries_structured_events():
    from dashboard_api.app import registry

    def fn(log_fn, emit_fn):
        log_fn("one line")
        emit_fn({"type": "job_result", "job_id": "j1", "status": "approved", "reason": "good fit"})
        return {"ok": True}

    client = TestClient(app)
    run = registry.start("phase2", fn)
    wait_for_run(client, run.run_id)

    with client.stream("GET", f"/runs/{run.run_id}/events") as res:
        body = "".join(res.iter_text())

    assert "event: structured" in body
    assert "job_result" in body
    assert "good fit" in body


def test_settings_persists_ai_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)
    res = client.put("/settings", json={"ai_engine": "groq"})
    assert res.status_code == 200
    assert client.get("/settings").json()["ai_engine"] == "groq"


def test_phase2_endpoint_passes_engine_and_force(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    captured = {}

    def fake_run_phase2(max_per_source, log_fn, emit_fn, provider, force):
        captured.update(provider=provider, force=force)
        return {"phase": "phase2"}

    monkeypatch.setattr("dashboard_api.app.run_phase2", fake_run_phase2)
    client = TestClient(app)
    res = client.post("/phases/phase2", json={"max": 5, "engine": "groq", "force": True})
    assert res.status_code == 202
    wait_for_run(client, res.json()["run_id"])
    assert captured == {"provider": "groq", "force": True}


def test_phase2_engine_defaults_from_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)
    client.put("/settings", json={"ai_engine": "groq"})
    captured = {}

    def fake_run_phase2(max_per_source, log_fn, emit_fn, provider, force):
        captured.update(provider=provider)
        return {"phase": "phase2"}

    monkeypatch.setattr("dashboard_api.app.run_phase2", fake_run_phase2)
    run_id = client.post("/phases/phase2", json={"max": 5}).json()["run_id"]
    wait_for_run(client, run_id)
    assert captured["provider"] == "groq"


def test_manual_vet_records_status_and_manual_engine(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="Full JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.post(f"/jobs/{job_id}/vet", json={"approved": True, "reason": "Looks great"})
    assert res.status_code == 200
    vetting = store.read_json(job_id, "vetting.json")
    assert vetting["status"] == "approved"
    assert vetting["engine"] == {"requested": "manual", "answered": "manual"}


def test_safe_pipeline_runs_phases_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dashboard_api.app.run_phase1",
        lambda **kw: calls.append("phase1") or {"phase": "phase1"},
    )
    monkeypatch.setattr(
        "dashboard_api.app.run_phase2",
        lambda **kw: calls.append("phase2") or {"phase": "phase2"},
    )
    monkeypatch.setattr(
        "dashboard_api.app.run_phase3_all",
        lambda **kw: calls.append("phase3-all") or {"phase": "phase3-all"},
    )

    client = TestClient(app)
    run_id = client.post("/pipelines/safe-prepare", json={"max": 1, "limit": 1}).json()["run_id"]
    wait_for_run(client, run_id)

    assert calls == ["phase1", "phase2", "phase3-all"]


def test_safe_prepare_runs_selected_phases_only(monkeypatch):
    calls = []
    monkeypatch.setattr("dashboard_api.app.run_phase1", lambda **kw: calls.append("phase1") or {"phase": "phase1"})
    monkeypatch.setattr("dashboard_api.app.run_phase2", lambda **kw: calls.append("phase2") or {"phase": "phase2"})
    monkeypatch.setattr("dashboard_api.app.run_phase3_all", lambda **kw: calls.append("phase3") or {"phase": "phase3-all"})
    monkeypatch.setattr("dashboard_api.app.run_phase4", lambda **kw: calls.append("phase4") or {"phase": "phase4"})

    client = TestClient(app)
    res = client.post("/pipelines/safe-prepare", json={"max": 2, "phases": ["phase2", "phase4"]})
    assert res.status_code == 202
    wait_for_run(client, res.json()["run_id"])
    assert calls == ["phase2", "phase4"]


def test_safe_prepare_rejects_empty_phase_list():
    client = TestClient(app)
    res = client.post("/pipelines/safe-prepare", json={"phases": ["bogus"]})
    assert res.status_code == 400


def test_list_runs_returns_history(monkeypatch):
    monkeypatch.setattr(
        "dashboard_api.app.run_phase1",
        lambda **kw: {"phase": "phase1", "written": 1},
    )

    client = TestClient(app)
    run_id = client.post("/phases/phase1", json={"max": 1}).json()["run_id"]
    finished = wait_for_run(client, run_id)

    res = client.get("/runs")

    assert res.status_code == 200
    runs = res.json()
    current = next(run for run in runs if run["run_id"] == run_id)
    assert current["phase"] == "phase1"
    assert current["status"] == "succeeded"
    assert current["result"] == finished["result"]
    assert current["logs"]


def test_get_tracking_returns_empty_when_missing(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    res = TestClient(app).get(f"/jobs/{job_id}/tracking")
    assert res.status_code == 200
    assert res.json() == {}


def test_put_tracking_writes_status_and_history(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    res = TestClient(app).put(f"/jobs/{job_id}/tracking", json={"status": "replied", "notes": "Got reply!"})
    assert res.status_code == 200
    assert res.json()["status"] == "replied"
    saved = store.read_json(job_id, "tracking.json")
    assert saved["status"] == "replied"
    assert saved["history"][-1]["status"] == "replied"


def test_put_tracking_rejects_invalid_status(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    res = TestClient(app).put(f"/jobs/{job_id}/tracking", json={"status": "won_lottery"})
    assert res.status_code == 400


def test_post_send_writes_tracking_sent(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    store.write_json(job_id, "package.json", {
        "email_subject": "Hello", "email_body": "Hi there",
        "match_score": 85, "keywords_matched": [], "keywords_missing": [],
        "tailored_experience": [], "tailored_skills": {},
    })
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    monkeypatch.setattr("dashboard_api.app.send_email", lambda to_email, subject, body, **_: True, raising=False)
    res = TestClient(app).post(f"/jobs/{job_id}/send", json={"to_email": "hiring@example.com"})
    assert res.status_code == 200
    assert res.json()["tracking"]["status"] == "sent"
    assert store.read_json(job_id, "tracking.json")["status"] == "sent"


def test_get_profile_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    res = TestClient(app).get("/profile")
    assert res.status_code == 200
    assert res.json() == {}


def test_put_and_get_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)
    client.put("/profile", json={"name": "Alice", "email": "a@b.com", "target_roles": ["Backend Engineer"], "base_resume_text": "", "years_experience": 3})
    res = client.get("/profile")
    assert res.json()["name"] == "Alice"


def test_put_criteria_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)
    client.put("/criteria", json={"require_remote": True, "salary_floor": 80000, "exclude_sources": [], "exclude_keywords": ["intern"]})
    res = client.get("/criteria")
    assert res.json()["require_remote"] is True


def test_put_settings_masks_api_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    client = TestClient(app)
    client.put("/settings", json={"gemini_key": "AIza-secret-key", "scraper_sources": {"yc": True}, "groq_key": "", "hunter_key": "", "apollo_key": "", "serper_key": "", "gmail_token_path": "", "max_per_source": 20, "daily_email_limit": 10})
    res = client.get("/settings")
    data = res.json()
    assert data["gemini_key"] == "AIza-****"
    assert data["scraper_sources"]["yc"] is True


def test_get_history_returns_empty_list(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))
    res = TestClient(app).get(f"/jobs/{job_id}/history")
    assert res.status_code == 200
    assert res.json() == []


def test_post_regen_triggers_phase3_run(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    store.write_json(job_id, "vetting.json", {"approved": True})
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    def fake_phase3(root="artifacts", job_id=None):
        return {"status": "generated", "job_id": job_id}

    monkeypatch.setattr("dashboard_api.app.run_phase3", fake_phase3)
    res = TestClient(app).post(f"/jobs/{job_id}/regen", json={"hint": "emphasize distributed systems"})
    assert res.status_code == 202
    assert "run_id" in res.json()


def test_review_queue_returns_generated_pending_jobs(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    job_id = store.write_job(make_job(), jd_text="JD")
    store.write_json(job_id, "generation.json", {"status": "generated"})
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    client = TestClient(app)
    res = client.get("/review-queue")

    assert res.status_code == 200
    assert res.json()[0]["job_id"] == job_id

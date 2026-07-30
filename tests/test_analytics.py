from fastapi.testclient import TestClient

from artifact_store import ArtifactStore
from dashboard_api.app import app
from scraper import Job


def make_job(company="Acme", title="Eng", url="https://x.com/1"):
    return Job(
        title=title,
        company=company,
        company_domain="",
        location="Remote",
        url=url,
        description="d",
        source="yc",
        remote=True,
    )


def test_funnel_counts_all_stages(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    j1 = store.write_job(make_job("A", url="https://x.com/1"), jd_text="JD")
    j2 = store.write_job(make_job("B", url="https://x.com/2"), jd_text="JD")
    store.write_json(j1, "vetting.json", {"approved": True})
    store.write_json(j2, "vetting.json", {"approved": False})
    store.write_json(j1, "generation.json", {"status": "generated"})
    store.write_json(j1, "review.json", {"status": "approved", "notes": "", "decision_history": []})
    store.write_json(j1, "tracking.json", {"status": "sent"})

    res = TestClient(app).get("/analytics/funnel")
    assert res.status_code == 200
    data = res.json()
    assert data["gathered"] == 2
    assert data["approved"] == 1
    assert data["generated"] == 1
    assert data["sent"] == 1


def test_response_rate_computes_ratios(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    for i, status in enumerate(["sent", "replied", "interview", "sent"]):
        jid = store.write_job(make_job(f"Co{i}", url=f"https://x.com/{i}"), jd_text="JD")
        store.write_json(jid, "tracking.json", {"status": status})

    res = TestClient(app).get("/analytics/response-rate")
    data = res.json()
    assert data["sent"] == 4
    assert data["replied"] >= 1
    assert 0 <= data["rate_reply"] <= 1


def test_sources_groups_by_source(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "applications"))

    for i in range(3):
        jid = store.write_job(
            Job(
                title="Eng",
                company=f"Co{i}",
                company_domain="",
                location="Remote",
                url=f"https://yc.com/{i}",
                description="d",
                source="yc",
                remote=True,
            ),
            jd_text="JD",
        )
        if i == 0:
            store.write_json(jid, "vetting.json", {"approved": True})

    res = TestClient(app).get("/analytics/sources")
    data = res.json()
    yc = next(s for s in data if s["source"] == "yc")
    assert yc["total"] == 3
    assert yc["approved"] == 1

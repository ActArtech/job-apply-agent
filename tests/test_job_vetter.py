import job_vetter
from job_vetter import vet_job_detail, vetting_status

LONG_JD = "Senior backend role building product APIs. " * 10


def test_vetting_status_none_for_missing():
    assert vetting_status(None) is None
    assert vetting_status({}) is None


def test_vetting_status_reads_explicit_status():
    assert vetting_status({"status": "approved"}) == "approved"
    assert vetting_status({"status": "rejected"}) == "rejected"
    assert vetting_status({"status": "error"}) == "error"


def test_vetting_status_derives_from_legacy_approved_flag():
    assert vetting_status({"approved": True, "reason": "ok"}) == "approved"
    assert vetting_status({"approved": False, "reason": "service company"}) == "rejected"


def test_vetting_status_legacy_ai_failure_is_error():
    legacy = {"approved": False, "reason": "AI vetting failed: Error code: 429 - rate limit"}
    assert vetting_status(legacy) == "error"


def test_vetting_status_both_mode():
    assert vetting_status({"provider": "both", "gemini": None, "groq": None}) == "error"
    assert vetting_status({"provider": "both", "gemini": {"approved": True}, "groq": None}) == "approved"
    assert vetting_status({"provider": "both", "gemini": None, "groq": {"approved": False}}) == "rejected"


def test_vet_job_detail_short_jd_is_error():
    result = vet_job_detail("Acme", "SWE", "https://x.com", "too short")
    assert result["status"] == "error"
    assert result["approved"] is None
    assert result["engine"] == {"requested": "gemini", "answered": None}


def test_vet_job_detail_records_status_and_engine(monkeypatch):
    monkeypatch.setattr(
        job_vetter, "call_provider_tracked",
        lambda prompt, provider: ({"is_approved": True, "score": 90, "reason": "good"}, "groq"),
    )
    result = vet_job_detail("Acme", "SWE", "https://x.com", LONG_JD, provider="gemini")
    assert result["status"] == "approved"
    assert result["approved"] is True
    assert result["engine"] == {"requested": "gemini", "answered": "groq"}


def test_vet_job_detail_rejection_status(monkeypatch):
    monkeypatch.setattr(
        job_vetter, "call_provider_tracked",
        lambda prompt, provider: ({"is_approved": False, "score": 10, "reason": "agency"}, "gemini"),
    )
    result = vet_job_detail("Acme", "SWE", "https://x.com", LONG_JD)
    assert result["status"] == "rejected"
    assert result["reason"] == "agency"


def test_vet_job_detail_provider_failure_is_error_not_rejection(monkeypatch):
    def boom(prompt, provider):
        raise Exception("Error code: 429 - rate limit")

    monkeypatch.setattr(job_vetter, "call_provider_tracked", boom)
    result = vet_job_detail("Acme", "SWE", "https://x.com", LONG_JD)
    assert result["status"] == "error"
    assert result["approved"] is None
    assert "429" in result["error"]
    assert result["engine"]["answered"] is None


def test_stage_bucket_maps_specific_labels():
    assert job_vetter._stage_bucket("seed") == "early"
    assert job_vetter._stage_bucket("series_b") == "early"
    assert job_vetter._stage_bucket("series_c_plus") == "growth"
    assert job_vetter._stage_bucket("public") == "established"
    assert job_vetter._stage_bucket("bootstrapped") == "established"
    assert job_vetter._stage_bucket("unknown") == "unknown"
    assert job_vetter._stage_bucket("garbage") == "unknown"


def test_normalize_adds_valid_stage_and_bucket():
    out = job_vetter._normalize_vetting_result(
        {"is_approved": True, "score": 80, "reason": "ok", "stage": "Seed"}
    )
    assert out["stage"] == "seed"
    assert out["stage_bucket"] == "early"


def test_normalize_defaults_unknown_stage_for_missing_or_garbage():
    missing = job_vetter._normalize_vetting_result(
        {"is_approved": True, "score": 80, "reason": "ok"}
    )
    assert missing["stage"] == "unknown"
    assert missing["stage_bucket"] == "unknown"
    garbage = job_vetter._normalize_vetting_result(
        {"is_approved": True, "score": 80, "reason": "ok", "stage": "mega_corp"}
    )
    assert garbage["stage"] == "unknown"
    assert garbage["stage_bucket"] == "unknown"


def test_vet_job_detail_carries_stage_through(monkeypatch):
    monkeypatch.setattr(
        job_vetter, "call_provider_tracked",
        lambda prompt, provider: (
            {"is_approved": True, "score": 90, "reason": "funded seed", "stage": "seed"},
            "gemini",
        ),
    )
    result = vet_job_detail("Acme", "SWE", "https://x.com", LONG_JD)
    assert result["status"] == "approved"
    assert result["stage"] == "seed"
    assert result["stage_bucket"] == "early"


def test_vetting_prompt_is_stage_aware():
    from job_vetter import VETTING_PROMPT
    assert "COMPENSATION (STAGE-AWARE)" in VETTING_PROMPT
    assert "funding stage is the pay proxy" in VETTING_PROMPT
    assert "FUNDING STAGE:" in VETTING_PROMPT
    assert '"stage"' in VETTING_PROMPT
    assert "pre_seed" in VETTING_PROMPT

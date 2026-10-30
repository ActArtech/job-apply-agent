"""Tests for vet_guard — deterministic checks that gate an AI vetting verdict."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vet_guard


def test_non_us_only_role_is_rejected():
    jd = "We are hiring a backend engineer. This role is India only and requires candidates to be based in India."
    result = vet_guard.check_job(jd, "Remote")
    assert result["ok"] is False
    assert "non-US" in result["location"]["reason"]


def test_visa_sponsorship_requirement_is_rejected():
    jd = ("Senior backend engineer. You must have the right to work in Germany and we do not offer visa sponsorship.")
    result = vet_guard.check_job(jd, "Remote")
    assert result["ok"] is False


def test_portuguese_posting_is_rejected():
    jd = ("Nosso propósito é criar tecnologias que desafiam os melhores do mundo. "
          "Vaga de Pessoa Desenvolvedora Backend Golang Sênior. "
          "Você fará parte de um time dinâmico, colaborativo e focado em excelência técnica.")
    result = vet_guard.check_job(jd, "Worldwide")
    assert result["ok"] is False
    assert result["language"]["language"] == "portuguese"


def test_us_role_is_allowed():
    jd = "Senior backend engineer at a product company. This role is remote in the United States."
    assert vet_guard.check_job(jd, "Remote")["ok"] is True


def test_remote_worldwide_role_is_allowed():
    jd = "We build a developer platform. Fully remote, worldwide team, product company."
    assert vet_guard.check_job(jd, "Worldwide")["ok"] is True


def test_no_location_signal_is_unknown_not_rejected():
    """The description is truncated at 3000 chars, so the location section is
    often absent. Absence of a signal must not be treated as disqualifying."""
    jd = "Build backend APIs for our developer platform." * 20
    result = vet_guard.check_job(jd, "")
    assert result["ok"] is True
    assert result["location"].get("unknown") is True


def test_structured_location_field_is_authoritative():
    """A board-provided 'Worldwide' field counts even when the truncated text
    never says remote."""
    jd = "We build a developer platform for engineering teams." * 20
    assert vet_guard.check_job(jd, "Worldwide")["ok"] is True


def test_vet_job_detail_rejects_non_english_before_calling_the_model(monkeypatch):
    """The deterministic gate must run before the AI verdict is trusted."""
    import job_vetter

    called = {"count": 0}

    def must_not_run(prompt, provider):
        called["count"] += 1
        return ({"is_approved": True, "score": 100, "reason": "fine"}, "ollama")

    monkeypatch.setattr(job_vetter, "call_provider_tracked", must_not_run)
    jd = ("Nosso propósito é criar tecnologias. Vaga de Pessoa Desenvolvedora Backend Golang Sênior. "
          "Horário flexível. Auxílio Educação. Guildas internas e grupos de estudos.") * 2
    result = job_vetter.vet_job_detail("Zup", "Backend Golang", "https://x", jd)
    assert result["approved"] is False
    assert result["status"] == "rejected"
    assert called["count"] == 0


def test_unstated_salary_is_not_a_rejection():
    """An unstated salary is never a reason to reject on its own."""
    jd = "Senior backend engineer at a product company. Fully remote worldwide."
    result = vet_guard.compensation_verdict(jd)
    assert result["ok"] is True
    assert result.get("unknown") is True


def test_explicitly_low_salary_is_rejected():
    jd = "Senior backend engineer. Salary: $120,000 per year plus equity."
    result = vet_guard.compensation_verdict(jd)
    assert result["ok"] is False


def test_hourly_rate_below_target_is_rejected():
    jd = "Contract backend engineer, $60 per hour, remote."
    result = vet_guard.compensation_verdict(jd)
    assert result["ok"] is False


def test_high_salary_is_allowed():
    jd = "Senior backend engineer. Salary: $190,000 per year plus equity."
    assert vet_guard.compensation_verdict(jd)["ok"] is True


def test_vet_job_detail_rejects_low_stated_salary():
    import job_vetter

    called = {"count": 0}

    def must_not_run(prompt, provider):
        called["count"] += 1
        return ({"is_approved": True, "score": 100, "reason": "fine"}, "ollama")

    import job_vetter as jv
    jv.call_provider_tracked = must_not_run
    jd = ("Senior backend engineer building product APIs. Remote in the United States. "
          "The base salary range is $90,000 to $110,000 per year. " * 3)
    result = jv.vet_job_detail("Acme", "Backend", "https://x", jd)
    assert result["approved"] is False
    assert "150,000" in result["reason"]

"""Tests for claim_guard — the CV-grounding check on tailored bullets."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claim_guard

PROFILE = json.load(
    open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.json"),
         encoding="utf-8"),
)


def test_cv_numeric_claims_are_extracted():
    claims = claim_guard.cv_numeric_claims(PROFILE)
    assert "68of68" in claims


def test_fabricated_percentage_is_flagged():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    stack = claim_guard.cv_stack_terms(PROFILE)
    bullet = "Led a real-time data pipeline using Go, resulting in a 30% improvement in data throughput."
    problems = claim_guard.ungrounded_claims(bullet, numeric, stack)
    assert any("30%" in p for p in problems)


def test_grounded_bullet_passes():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    stack = claim_guard.cv_stack_terms(PROFILE)
    bullet = ("Built a deterministic, LLM-free crisis-safety gate that passed "
              "68 of 68 defined scenario evaluations in CI, with fail-closed routing.")
    assert claim_guard.ungrounded_claims(bullet, numeric, stack) == []


def test_stack_term_not_in_cv_is_flagged():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    stack = claim_guard.cv_stack_terms(PROFILE)
    bullet = "Built Celery and RabbitMQ pipelines for asynchronous background processing."
    problems = claim_guard.ungrounded_claims(bullet, numeric, stack)
    assert problems


def test_verify_bullets_separates_clean_and_flagged():
    result = claim_guard.verify_bullets([
        "Built a deterministic, LLM-free crisis-safety gate that passed 68 of 68 defined scenario evaluations in CI.",
        "Cut infrastructure spend by 42% across the fleet.",
    ], PROFILE)
    assert result["ok"] is False
    assert len(result["clean"]) == 1
    assert len(result["flagged"]) == 1


def test_merge_bullets_drops_ungrounded_generated_bullet():
    """A generated bullet with an invented metric must not reach the resume."""
    import ai_engine

    base = ["Shipped production releases with explicit readiness gates and monitored rollouts."]
    generated = [
        "Led a real-time data pipeline using Go, resulting in a 30% improvement in data throughput.",
    ]
    merged = ai_engine._merge_bullets(generated, base, target_count=3)
    assert all("30%" not in b for b in merged)
    assert any("readiness gates" in b for b in merged)


def test_dequantify_removes_fabricated_percentage():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    out = claim_guard.dequantify(
        "Led a real-time data pipeline using Go and Node.js, resulting in a 30% improvement in data throughput.",
        numeric,
    )
    assert "30%" not in out
    assert "improving the data throughput" in out


def test_dequantify_keeps_grounded_number():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    original = ("Built a deterministic, LLM-free crisis-safety gate that passed "
                "68 of 68 defined scenario evaluations in CI, enforced on every change.")
    assert claim_guard.dequantify(original, numeric) == original


def test_dequantify_result_is_a_complete_sentence():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    out = claim_guard.dequantify(
        "Led a crisis-safety gate using Go and Node.js, resulting in a 20% pass rate "
        "in CI to improve reliability, maintainability and delivery speed.",
        numeric,
    )
    assert "20%" not in out
    assert not out.rstrip().endswith(("and", "to", "the", "in"))


def test_merge_bullets_keeps_bullet_after_dequantifying():
    """A fabricated metric must not cost the bullet entirely."""
    import ai_engine

    base = ["Shipped production releases with explicit readiness gates and monitored rollouts."]
    generated = ["Implemented a data processing pipeline using Go and Node.js, improving search relevancy by 35%."]
    merged = ai_engine._merge_bullets(generated, base, target_count=3)
    assert any("35%" not in b and "search relevancy" in b for b in merged)


def test_novel_domain_terms_detects_invented_field_of_work():
    """A bullet may not introduce a domain the CV never mentions."""
    vocab = claim_guard.cv_vocabulary(PROFILE)
    bullet = ("Developed automated threat hunting workflows using Python and JavaScript, "
              "reducing the false positives.")
    novel = claim_guard.novel_domain_terms(bullet, vocab)
    assert "threat" in novel
    assert "hunting" in novel


def test_real_cv_bullets_have_no_novel_terms():
    for entry in PROFILE["experience"]:
        for bullet in entry["bullets"]:
            vocab = claim_guard.cv_vocabulary(PROFILE)
            assert claim_guard.novel_domain_terms(bullet, vocab) == [], bullet


def test_ungrounded_claims_flags_invented_domain():
    numeric = claim_guard.cv_numeric_claims(PROFILE)
    stack = claim_guard.cv_stack_terms(PROFILE)
    vocab = claim_guard.cv_vocabulary(PROFILE)
    bullet = ("Led a team of 5 engineers in building a real-time fraud detection system, "
              "reducing fraud incidents.")
    problems = claim_guard.ungrounded_claims(bullet, numeric, stack, True, vocab)
    assert any("fraud" in p for p in problems)
